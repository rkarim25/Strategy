"""
SPX vs Nasdaq rotation + Guarded A5/B25 (0-3x) on the active index.

Compares rotation rules vs buy-and-hold Guarded on Nasdaq only (3x cap).
Uses ETP daily returns for 1x/2x/3x (UK listings) when available, engine costs, inflows.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from analyze_multi_asset_guarded_scan import panel_for_close
from core.engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    trading_cost,
)
from core.etp_leverage import (
    NDX_ETP,
    SPX_ETP,
    build_etp_return_panel,
    daily_return_for_leverage,
    etp_coverage_summary,
)
from core.metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW

OUTPUT_DIR = Path("output") / "spx_ndx_rotation_guarded"
MAX_LEV = 3.0
SWITCH_COST_PCT = TRADING_COST_FROM_MID_PCT  # full notional on asset switch
YEARS = 30


@dataclass(frozen=True)
class StrategySpec:
    name: str
    category: str
    description: str


def download_data(
    years: int = YEARS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    raw = yf.download(
        ["^GSPC", "^NDX", "^IRX", "^VIX"],
        start=start.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    closes = raw["Close"].sort_index().ffill()
    tbill = closes["^IRX"] / 100.0
    vix = closes["^VIX"].ffill()
    panel_spx = panel_for_close(closes["^GSPC"].dropna(), tbill)
    panel_ndx = panel_for_close(closes["^NDX"].dropna(), tbill)
    idx = panel_spx.index.intersection(panel_ndx.index)
    panel_spx = panel_spx.loc[idx]
    panel_ndx = panel_ndx.loc[idx]
    return panel_spx, panel_ndx, tbill.loc[idx], vix.loc[idx]


def apply_hysteresis(pick: pd.Series, confirm_days: int) -> pd.Series:
    if confirm_days <= 0:
        return pick.copy()
    out = pd.Series(index=pick.index, dtype=object)
    current = pick.iloc[0]
    pending = None
    streak = 0
    for dt, target in pick.items():
        if target == current:
            pending = None
            streak = 0
            out.loc[dt] = current
            continue
        if pending != target:
            pending = target
            streak = 1
        else:
            streak += 1
        if streak >= confirm_days:
            current = pending
            pending = None
            streak = 0
        out.loc[dt] = current
    return out


def regime_score(lev: pd.Series) -> pd.Series:
    return lev.clip(0, 3).astype(float)


def pick_rs(panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame, sma_window: int) -> pd.Series:
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    ratio = ndx / spx
    rs_ma = ratio.rolling(sma_window, min_periods=sma_window).mean()
    pick = np.where(ratio > rs_ma, "NDX", "SPX")
    return pd.Series(pick, index=spx.index)


def pick_return_spread(
    panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame, lookback: int, *, cash_if_negative: bool
) -> pd.Series:
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    spx_m = spx / spx.shift(lookback) - 1.0
    ndx_m = ndx / ndx.shift(lookback) - 1.0
    picks = []
    for dt in spx.index:
        s, n = spx_m.loc[dt], ndx_m.loc[dt]
        if pd.isna(s) or pd.isna(n):
            picks.append("SPX")
            continue
        if cash_if_negative and s <= 0 and n <= 0:
            picks.append("CASH")
        elif n > s:
            picks.append("NDX")
        else:
            picks.append("SPX")
    return pd.Series(picks, index=spx.index)


def pick_guarded_regime(
    lev_spx: pd.Series, lev_ndx: pd.Series, panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame
) -> pd.Series:
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    spx_m6 = spx / spx.shift(126) - 1.0
    ndx_m6 = ndx / ndx.shift(126) - 1.0
    picks = []
    for dt in lev_spx.index:
        ls, ln = lev_spx.loc[dt], lev_ndx.loc[dt]
        inv_spx = ls > 0
        inv_ndx = ln > 0
        if not inv_spx and not inv_ndx:
            picks.append("CASH")
        elif inv_spx and not inv_ndx:
            picks.append("SPX")
        elif inv_ndx and not inv_spx:
            picks.append("NDX")
        else:
            ss, ns = regime_score(pd.Series([ls])).iloc[0], regime_score(pd.Series([ln])).iloc[0]
            if ns > ss:
                picks.append("NDX")
            elif ss > ns:
                picks.append("SPX")
            else:
                picks.append("NDX" if ndx_m6.loc[dt] >= spx_m6.loc[dt] else "SPX")
    return pd.Series(picks, index=lev_spx.index)


def pick_trend_sma200(panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame) -> pd.Series:
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    spx_ok = spx > spx.rolling(200, min_periods=200).mean()
    ndx_ok = ndx > ndx.rolling(200, min_periods=200).mean()
    picks = []
    for dt in spx.index:
        s, n = bool(spx_ok.loc[dt]), bool(ndx_ok.loc[dt])
        if n:
            picks.append("NDX")
        elif s:
            picks.append("SPX")
        else:
            picks.append("CASH")
    return pd.Series(picks, index=spx.index)


def pick_rs_with_trend_filter(
    panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame, rs_sma: int
) -> pd.Series:
    raw = pick_rs(panel_spx, panel_ndx, rs_sma)
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    sma20_spx = spx.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    sma20_ndx = ndx.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    picks = []
    for dt, p in raw.items():
        if p == "NDX" and ndx.loc[dt] < sma20_ndx.loc[dt]:
            picks.append("CASH")
        elif p == "SPX" and spx.loc[dt] < sma20_spx.loc[dt]:
            picks.append("CASH")
        else:
            picks.append(p)
    return pd.Series(picks, index=raw.index)


def pick_dual_momentum_12m(panel_spx: pd.DataFrame, panel_ndx: pd.DataFrame) -> pd.Series:
    return pick_return_spread(panel_spx, panel_ndx, 252, cash_if_negative=True)


def pick_ndx_home_bias(
    panel_spx: pd.DataFrame,
    panel_ndx: pd.DataFrame,
    lookback: int,
    hurdle: float,
    hysteresis_days: int = 10,
) -> pd.Series:
    """Default NDX unless SPX lookback return exceeds Nasdaq by hurdle (fraction)."""
    spx = panel_spx["spx_close"]
    ndx = panel_ndx["spx_close"]
    m_s = spx / spx.shift(lookback) - 1.0
    m_n = ndx / ndx.shift(lookback) - 1.0
    picks = []
    for dt in spx.index:
        s, n = m_s.loc[dt], m_n.loc[dt]
        if pd.isna(s) or pd.isna(n):
            picks.append("NDX")
        elif s > n + hurdle:
            picks.append("SPX")
        else:
            picks.append("NDX")
    raw = pd.Series(picks, index=spx.index)
    return apply_hysteresis(raw, hysteresis_days) if hysteresis_days > 0 else raw


def pick_ndx_unless_vol_stress_and_spx_leads(
    panel_spx: pd.DataFrame,
    panel_ndx: pd.DataFrame,
    vix: pd.Series,
    *,
    lookback: int = 126,
    hurdle: float = 0.03,
    vix_ceiling: float = 28.0,
) -> pd.Series:
    """Stay NDX unless VIX is below ceiling and SPX beats NDX over lookback by hurdle."""
    home = pick_ndx_home_bias(panel_spx, panel_ndx, lookback, hurdle, hysteresis_days=10)
    picks = []
    for dt in home.index:
        if home.loc[dt] == "SPX" and float(vix.loc[dt]) > vix_ceiling:
            picks.append("NDX")
        else:
            picks.append(home.loc[dt])
    return pd.Series(picks, index=home.index)


def simulate_rotation(
    pick: pd.Series,
    panel_spx: pd.DataFrame,
    panel_ndx: pd.DataFrame,
    lev_spx: pd.Series,
    lev_ndx: pd.Series,
    *,
    etp_spx: pd.DataFrame,
    etp_ndx: pd.DataFrame,
    initial: float = INITIAL_CAPITAL,
    annual_inflow: float = ANNUAL_INFLOW_USD,
) -> tuple[pd.Series, pd.Series, dict]:
    spx_ret = panel_spx["spx_close"].pct_change()
    ndx_ret = panel_ndx["spx_close"].pct_change()
    tbill = panel_spx["tbill_rate"]

    equity = pd.Series(index=pick.index, dtype=float)
    applied_lev = pd.Series(index=pick.index, dtype=float)
    aum = initial
    prev_asset = pick.iloc[0]
    prev_lev = 0.0
    prev_year = None
    switches = 0
    switch_cost_total = 0.0
    rebalance_count = 0
    trading_costs = 0.0
    days_spx = days_ndx = days_cash = 0

    for i, dt in enumerate(pick.index):
        if prev_year is not None and dt.year != prev_year:
            aum += annual_inflow

        asset = pick.loc[dt]
        if asset == "SPX":
            days_spx += 1
            target_lev = float(lev_spx.loc[dt])
            asset_ret = spx_ret.loc[dt]
        elif asset == "NDX":
            days_ndx += 1
            target_lev = float(lev_ndx.loc[dt])
            asset_ret = ndx_ret.loc[dt]
        else:
            days_cash += 1
            target_lev = 0.0
            asset_ret = np.nan

        if asset != prev_asset:
            cost = trading_cost(aum)
            aum -= cost
            switch_cost_total += cost
            switches += 1
            prev_lev = 0.0

        if abs(target_lev - prev_lev) > 1e-9:
            traded = abs(target_lev - prev_lev) * aum
            cost = trading_cost(traded)
            aum -= cost
            trading_costs += cost
            rebalance_count += 1
            prev_lev = target_lev

        if i > 0:
            tb = float(tbill.loc[dt]) if not pd.isna(tbill.loc[dt]) else 0.0
            if asset == "CASH" or pd.isna(asset_ret):
                r = tb / 252.0
            elif asset == "SPX":
                r = daily_return_for_leverage(
                    target_lev, float(asset_ret), tb, etp_spx.loc[dt]
                )
            else:
                r = daily_return_for_leverage(
                    target_lev, float(asset_ret), tb, etp_ndx.loc[dt]
                )
            aum *= 1.0 + r

        equity.loc[dt] = aum
        applied_lev.loc[dt] = target_lev
        prev_asset = asset
        prev_year = dt.year

    daily = equity.pct_change().fillna(0.0)
    meta = {
        "switches": switches,
        "switch_cost_total": switch_cost_total,
        "trading_costs": trading_costs,
        "rebalance_count": rebalance_count,
        "pct_days_spx": 100.0 * days_spx / len(pick),
        "pct_days_ndx": 100.0 * days_ndx / len(pick),
        "pct_days_cash": 100.0 * days_cash / len(pick),
    }
    return equity, daily, meta


def stats_from_equity(equity: pd.Series, daily: pd.Series) -> dict:
    st = comprehensive_stats(equity, daily)
    return {
        "cagr_pct": round(st["cagr"] * 100, 2),
        "ann_volatility_pct": round(st["volatility"] * 100, 2),
        "sharpe": round(float(st["sharpe"]), 3) if st["sharpe"] == st["sharpe"] else None,
        "max_drawdown_pct": round(st["max_drawdown"] * 100, 2),
        "calmar": round(float(st["calmar"]), 3) if st["calmar"] == st["calmar"] else None,
        "end_$": round(float(equity.iloc[-1]), 2),
    }


def pareto_frontier(
    rotation: pd.DataFrame, bench: dict, *, cagr_col: str = "cagr_pct", dd_col: str = "max_drawdown_pct"
) -> dict:
    """Best CAGR with DD no worse than benchmark; best DD with CAGR >= benchmark."""
    dd_floor = bench["max_drawdown_pct"]
    cagr_floor = bench["cagr_pct"]
    dd_ok = rotation[rotation[dd_col] >= dd_floor]
    cagr_ok = rotation[rotation[cagr_col] >= cagr_floor]
    out: dict = {}
    if len(dd_ok):
        best = dd_ok.loc[dd_ok[cagr_col].idxmax()]
        out["best_cagr_subject_to_dd"] = best.to_dict()
    if len(cagr_ok):
        best = cagr_ok.loc[cagr_ok[dd_col].idxmax()]
        out["best_dd_subject_to_cagr"] = best.to_dict()
    return out


def build_strategy_list() -> tuple[
    list[tuple[StrategySpec, pd.Series]],
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
]:
    panel_spx, panel_ndx, _, vix = download_data()
    lev_spx, _ = guarded_lead_leverage(panel_spx, max_leverage=MAX_LEV)
    lev_ndx, _ = guarded_lead_leverage(panel_ndx, max_leverage=MAX_LEV)

    specs: list[tuple[StrategySpec, pd.Series]] = []

    def add(name: str, cat: str, desc: str, pick: pd.Series) -> None:
        specs.append((StrategySpec(name, cat, desc), pick))

    add(
        "Benchmark: Guarded Nasdaq only (3x)",
        "benchmark",
        "Always NDX; Guarded A5/B25 full leverage",
        pd.Series("NDX", index=panel_spx.index),
    )
    add(
        "Benchmark: Guarded S&P 500 only (3x)",
        "benchmark",
        "Always SPX; Guarded A5/B25 full leverage",
        pd.Series("SPX", index=panel_spx.index),
    )

    for w in (20, 50, 100, 200):
        p = pick_rs(panel_spx, panel_ndx, w)
        add(
            f"RS NDX/SPX > SMA{w}",
            "relative_strength",
            f"Hold stronger relative index by {w}d ratio trend",
            p,
        )
        for h in (5, 10):
            add(
                f"RS > SMA{w} + hysteresis {h}d",
                "relative_strength",
                f"RS pick; switch after {h} consecutive days",
                apply_hysteresis(p, h),
            )

    for lb, label in ((63, "3m"), (126, "6m"), (252, "12m")):
        add(
            f"Momentum spread {label}",
            "momentum",
            f"Higher {label} total return; cash if both negative",
            pick_return_spread(panel_spx, panel_ndx, lb, cash_if_negative=True),
        )

    add(
        "Guarded regime picker",
        "guarded_overlay",
        "Invested side(s) by Guarded; if both, higher tier then 6m return",
        pick_guarded_regime(lev_spx, lev_ndx, panel_spx, panel_ndx),
    )
    add(
        "Guarded regime + hysteresis 5d",
        "guarded_overlay",
        "Regime picker with 5d switch confirmation",
        apply_hysteresis(pick_guarded_regime(lev_spx, lev_ndx, panel_spx, panel_ndx), 5),
    )

    add(
        "Trend SMA200 (NDX priority)",
        "trend",
        "NDX if above SMA200 else SPX if above else cash",
        pick_trend_sma200(panel_spx, panel_ndx),
    )

    for w in (20, 50):
        add(
            f"RS > SMA{w} + SMA20 filter",
            "combo",
            "RS pick only if chosen index above its SMA20 else cash",
            pick_rs_with_trend_filter(panel_spx, panel_ndx, w),
        )

    add(
        "Dual momentum 12m",
        "momentum",
        "12m winner; cash if both negative",
        pick_dual_momentum_12m(panel_spx, panel_ndx),
    )
    add(
        "Dual momentum 6m + hysteresis 5d",
        "momentum",
        "6m winner; cash if both negative; 5d switch confirmation",
        apply_hysteresis(
            pick_return_spread(panel_spx, panel_ndx, 126, cash_if_negative=True), 5
        ),
    )
    add(
        "NDX home bias 12m (SPX must beat +3%)",
        "ndx_bias",
        "Default NDX unless SPX 12m return exceeds Nasdaq by 3pp; 10d hysteresis",
        pick_ndx_home_bias(panel_spx, panel_ndx, 252, 0.03, hysteresis_days=10),
    )
    add(
        "NDX home bias 6m + vol filter VIX<28",
        "ndx_bias",
        "NDX home 6m +3pp hurdle; ignore SPX switch when VIX above 28",
        pick_ndx_unless_vol_stress_and_spx_leads(
            panel_spx, panel_ndx, vix, lookback=126, hurdle=0.03, vix_ceiling=28.0
        ),
    )

    # Best-of blended signals
    rs50 = pick_rs(panel_spx, panel_ndx, 50)
    reg = pick_guarded_regime(lev_spx, lev_ndx, panel_spx, panel_ndx)
    combo = []
    for dt in panel_spx.index:
        if rs50.loc[dt] == reg.loc[dt]:
            combo.append(rs50.loc[dt])
        elif reg.loc[dt] == "CASH":
            combo.append(rs50.loc[dt])
        else:
            combo.append(reg.loc[dt])
    add(
        "Combo RS50 + regime agree else regime",
        "combo",
        "RS50 when agrees with regime pick else follow regime",
        pd.Series(combo, index=panel_spx.index),
    )

    for hurdle in (0.0, 0.03, 0.05, 0.08):
        add(
            f"NDX home bias 6m (SPX must beat +{hurdle*100:.0f}%)",
            "ndx_bias",
            f"Default NDX unless SPX 6m return exceeds Nasdaq by {hurdle*100:.0f}pp",
            pick_ndx_home_bias(panel_spx, panel_ndx, 126, hurdle, hysteresis_days=10),
        )

    rs50h = apply_hysteresis(pick_rs(panel_spx, panel_ndx, 50), 10)
    picks_ndx_tie = []
    ratio = panel_ndx["spx_close"] / panel_spx["spx_close"]
    rs_ma50 = ratio.rolling(50, min_periods=50).mean()
    for dt in panel_spx.index:
        p = rs50h.loc[dt]
        if ratio.loc[dt] >= rs_ma50.loc[dt] * 0.998:
            picks_ndx_tie.append("NDX")
        else:
            picks_ndx_tie.append(p)
    add(
        "RS50 hyst10 NDX tie-break",
        "ndx_bias",
        "RS50 with hysteresis; near ratio ties go to NDX",
        pd.Series(picks_ndx_tie, index=panel_spx.index),
    )

    # Only leave NDX when its Guarded is cash but SPX Guarded is invested
    picks_exit = []
    for dt in panel_spx.index:
        if lev_ndx.loc[dt] <= 0 and lev_spx.loc[dt] > 0:
            picks_exit.append("SPX")
        else:
            picks_exit.append("NDX")
    add(
        "NDX unless Guarded NDX cash & SPX invested",
        "guarded_overlay",
        "Stay on Nasdaq unless flat there but S&P Guarded wants exposure",
        pd.Series(picks_exit, index=panel_spx.index),
    )

    return specs, panel_spx, panel_ndx, lev_spx, lev_ndx


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading data and Guarded leverage series...", flush=True)
    specs, panel_spx, panel_ndx, lev_spx, lev_ndx = build_strategy_list()
    print("Building ETP return panels (XS2D/3USL, LQQ/LQQ3)...", flush=True)
    etp_spx = build_etp_return_panel(panel_spx, SPX_ETP)
    etp_ndx = build_etp_return_panel(panel_ndx, NDX_ETP)

    rows: list[dict] = []
    ndx_bench_stats: dict | None = None

    for spec, pick in specs:
        eq, daily, meta = simulate_rotation(
            pick,
            panel_spx,
            panel_ndx,
            lev_spx,
            lev_ndx,
            etp_spx=etp_spx,
            etp_ndx=etp_ndx,
        )
        st = stats_from_equity(eq, daily)
        row = {
            "strategy": spec.name,
            "category": spec.category,
            "description": spec.description,
            **st,
            **meta,
        }
        rows.append(row)
        if spec.name.startswith("Benchmark: Guarded Nasdaq"):
            ndx_bench_stats = st

    df = pd.DataFrame(rows)
    df["beats_ndx_cagr"] = False
    df["beats_ndx_sharpe"] = False
    df["beats_ndx_calmar"] = False
    df["beats_ndx_max_dd"] = False
    df["beats_ndx_cagr_and_max_dd"] = False
    if ndx_bench_stats:
        df["beats_ndx_cagr"] = df["cagr_pct"] > ndx_bench_stats["cagr_pct"]
        df["beats_ndx_sharpe"] = df["sharpe"] > ndx_bench_stats["sharpe"]
        df["beats_ndx_calmar"] = df["calmar"] > ndx_bench_stats["calmar"]
        df["beats_ndx_max_dd"] = df["max_drawdown_pct"] > ndx_bench_stats["max_drawdown_pct"]
        df["beats_ndx_cagr_and_max_dd"] = df["beats_ndx_cagr"] & df["beats_ndx_max_dd"]

    df = df.sort_values(
        ["beats_ndx_cagr_and_max_dd", "beats_ndx_cagr", "sharpe"],
        ascending=False,
    )
    df.to_csv(OUTPUT_DIR / "rotation_results.csv", index=False)

    rotation = df[~df["category"].eq("benchmark")].copy()
    best_sharpe = rotation.loc[rotation["sharpe"].idxmax()]
    best_cagr = rotation.loc[rotation["cagr_pct"].idxmax()]
    best_dd = rotation.loc[rotation["max_drawdown_pct"].idxmax()]
    beats_sharpe_cagr = rotation[rotation["beats_ndx_sharpe"] & rotation["beats_ndx_cagr"]]
    beats_cagr_dd = rotation[rotation["beats_ndx_cagr_and_max_dd"]].sort_values(
        ["sharpe", "cagr_pct"], ascending=False
    )
    pareto = pareto_frontier(rotation, ndx_bench_stats) if ndx_bench_stats else {}

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assumptions": {
            "guarded": DEFAULT_GUARDED,
            "max_leverage": MAX_LEV,
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "sleeve_trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "asset_switch_cost_pct": SWITCH_COST_PCT,
            "levered_pnl": "Listed 2x/3x ETP daily returns (XS2D/3USL, LQQ/LQQ3); synthetic daily-reset before ETP inception",
            "etp_coverage_spx": etp_coverage_summary(etp_spx),
            "etp_coverage_ndx": etp_coverage_summary(etp_ndx),
            "window": {
                "start": str(panel_spx.index[0].date()),
                "end": str(panel_spx.index[-1].date()),
                "days": int(len(panel_spx)),
            },
        },
        "nasdaq_benchmark": ndx_bench_stats,
        "best_by_sharpe": best_sharpe.to_dict(),
        "best_by_cagr": best_cagr.to_dict(),
        "best_max_drawdown": best_dd.to_dict(),
        "pareto_vs_nasdaq_benchmark": pareto,
        "beats_nasdaq_cagr_and_max_dd": beats_cagr_dd[
            ["strategy", "cagr_pct", "max_drawdown_pct", "sharpe", "end_$"]
        ].to_dict(orient="records"),
        "beats_nasdaq_cagr_and_sharpe": beats_sharpe_cagr[
            ["strategy", "cagr_pct", "max_drawdown_pct", "sharpe", "end_$"]
        ].to_dict(orient="records"),
        "top_10_by_sharpe": rotation.nlargest(10, "sharpe")[
            [
                "strategy",
                "cagr_pct",
                "ann_volatility_pct",
                "sharpe",
                "max_drawdown_pct",
                "end_$",
                "pct_days_ndx",
                "switches",
            ]
        ].to_dict(orient="records"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nWindow: {panel_spx.index[0].date()} -> {panel_spx.index[-1].date()}\n")
    print("=== Benchmarks ===")
    print(
        df[df["category"] == "benchmark"][
            ["strategy", "cagr_pct", "ann_volatility_pct", "sharpe", "max_drawdown_pct", "end_$"]
        ].to_string(index=False)
    )
    print("\n=== Top 12 rotation strategies (by Sharpe) ===")
    cols = [
        "strategy",
        "cagr_pct",
        "ann_volatility_pct",
        "sharpe",
        "max_drawdown_pct",
        "end_$",
        "pct_days_ndx",
        "pct_days_spx",
        "pct_days_cash",
        "switches",
    ]
    print(rotation.nlargest(12, "sharpe")[cols].to_string(index=False))

    print("\n=== Beats Nasdaq on BOTH CAGR and max DD (not worse) ===")
    if len(beats_cagr_dd):
        print(beats_cagr_dd[cols].head(10).to_string(index=False))
    else:
        print("(none)")
        if pareto:
            print("\n=== Pareto vs Nasdaq benchmark ===")
            for key, row in pareto.items():
                print(f"{key}: {row['strategy']}  CAGR={row['cagr_pct']}%  DD={row['max_drawdown_pct']}%  Sharpe={row['sharpe']}")

    print("\n=== Beats Nasdaq on BOTH CAGR and Sharpe ===")
    if len(beats_sharpe_cagr):
        print(beats_sharpe_cagr[cols].to_string(index=False))
    else:
        print("(none)")

    print(f"\nWrote {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
