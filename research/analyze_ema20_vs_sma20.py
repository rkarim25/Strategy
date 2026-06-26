"""
EMA20 vs SMA20 for Guarded A5/B25 strategies on SPX, NDX, and LQQ3.L.

Compares website-default rules with SMA20 replaced by EMA20 in base trend,
lead guard, and recovery logic. SPX/NDX use full 0/1/2/3x tiers with ETP P&L;
LQQ3 uses max 1x on real 3QQQ from 2012-12-13.

Also includes simple SMA20 vs EMA20 1x/cash baselines for context.

Writes output/ema20_vs_sma20/comparison.csv and summary.json.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED
from backtest_lqq3_guarded import LQQ3_START, LQQ3_TICKER, download_panel as download_lqq3_panel
from backtest_ndx_guarded import download_ndx_panel
from backtest_spx_guarded import download_spx_panel
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from etp_leverage import NDX_ETP, SPX_ETP, build_etp_return_panel
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW

OUTPUT_DIR = Path("output") / "ema20_vs_sma20"

MaKind = Literal["sma", "ema"]


def make_engine() -> PortfolioEngine:
    # signal_delay_days=0 matches published website backtests (same-bar execution).
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=0,
    )


def ma_line(close: pd.Series, kind: MaKind, window: int = BASE_SMA_WINDOW) -> pd.Series:
    if kind == "sma":
        return close.rolling(window, min_periods=window).mean()
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def trend_cash_leverage(
    prices: pd.DataFrame,
    *,
    kind: MaKind,
    window: int = BASE_SMA_WINDOW,
    leverage: float = 1.0,
) -> pd.Series:
    close = prices["spx_close"].astype(float)
    ma = ma_line(close, kind, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > ma] = leverage
    return lev


def guarded_lead_leverage_ma(
    prices: pd.DataFrame,
    *,
    ma_kind: MaKind,
    max_leverage: float = 3.0,
    trigger_a: float = DEFAULT_GUARDED["trigger_a"],
    trigger_b: float = DEFAULT_GUARDED["trigger_b"],
    lead_pct_below_ma: float = DEFAULT_GUARDED["lead_pct_below_sma20"],
    x_return: float = DEFAULT_GUARDED["x_return"],
    y_return: float = DEFAULT_GUARDED["y_return"],
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    ma20 = ma_line(close, ma_kind)
    base_guard = (close > ma20).fillna(False)
    recovery_guard = (close >= ma20 * (1.0 - lead_pct_below_ma)).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0

    def cap(value: float) -> float:
        return float(min(max(value, 0.0), max_leverage))

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev = 1.0 if base_ok else 0.0
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(3.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = cap(3.0)
                continue
            if px / entry_close - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(2.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = cap(3.0)
        elif dd <= -trigger_a and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = cap(2.0)
        else:
            if dd <= -trigger_a and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = cap(base_lev)

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
        "max_leverage": max_leverage,
        "ma_kind": ma_kind,
    }
    return lev, counts


def run_row(
    asset: str,
    prices: pd.DataFrame,
    strategy: str,
    lev: pd.Series,
    *,
    etp_returns: pd.DataFrame | None = None,
    extra: dict | None = None,
) -> dict:
    run_kw: dict = {"name": strategy}
    if etp_returns is not None:
        run_kw["etp_returns"] = etp_returns
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    row = {
        "asset": asset,
        "strategy": strategy,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats.get("cagr"),
        "ann_volatility": stats.get("volatility"),
        "sharpe": stats.get("sharpe"),
        "max_drawdown": stats.get("max_drawdown"),
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": int(result.rebalance_count),
        "trading_costs": result.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        "pct_invested": cash["pct_sessions_invested"],
    }
    if extra:
        row.update(extra)
    return row


def guarded_strategy_label(ma_kind: MaKind, max_leverage: float) -> str:
    ma = "SMA20" if ma_kind == "sma" else "EMA20"
    if max_leverage >= 3.0:
        return f"Guarded A5/B25 {ma} Lead (full 0/1/2/3x)"
    return f"Guarded A5/B25 {ma} Lead (max 1x)"


def trend_label(ma_kind: MaKind) -> str:
    return f"{'SMA20' if ma_kind == 'sma' else 'EMA20'} 1x/cash"


def score_ema_vs_sma(sma: dict, ema: dict) -> dict:
    """Score guarded EMA vs SMA on CAGR, Sharpe, max DD (higher=better), rebalances (lower=better)."""
    wins = {"ema": 0, "sma": 0, "ties": 0}
    details: list[dict] = []

    def add(metric: str, sma_val: float, ema_val: float, *, lower_better: bool = False) -> None:
        if sma_val is None or ema_val is None:
            return
        if abs(ema_val - sma_val) < 1e-12:
            winner = "tie"
            wins["ties"] += 1
        elif (ema_val < sma_val) if lower_better else (ema_val > sma_val):
            winner = "ema"
            wins["ema"] += 1
        else:
            winner = "sma"
            wins["sma"] += 1
        details.append(
            {
                "metric": metric,
                "sma": sma_val,
                "ema": ema_val,
                "delta_ema_minus_sma": ema_val - sma_val,
                "winner": winner,
            }
        )

    add("cagr", float(sma["cagr"]), float(ema["cagr"]))
    add("sharpe", float(sma["sharpe"]), float(ema["sharpe"]))
    add("max_drawdown", float(sma["max_drawdown"]), float(ema["max_drawdown"]))
    add("rebalances", float(sma["rebalances"]), float(ema["rebalances"]), lower_better=True)

    dd_worse_ema = float(ema["max_drawdown"]) < float(sma["max_drawdown"]) - 0.005
    dd_better_ema = float(ema["max_drawdown"]) > float(sma["max_drawdown"]) + 0.005

    if wins["ema"] >= 3 and not dd_worse_ema:
        verdict = "EMA20 better"
    elif wins["sma"] >= 3 and not dd_better_ema:
        verdict = "SMA20 better"
    elif wins["ema"] > wins["sma"] and not dd_worse_ema:
        verdict = "EMA20 slightly better (mixed)"
    elif wins["sma"] > wins["ema"] and not dd_better_ema:
        verdict = "SMA20 slightly better (mixed)"
    else:
        verdict = "Mixed — tradeoffs"

    return {
        "verdict": verdict,
        "ema_wins": wins["ema"],
        "sma_wins": wins["sma"],
        "ties": wins["ties"],
        "metric_details": details,
    }


def run_asset_spx_ndx(
    asset: str,
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    *,
    max_leverage: float,
) -> list[dict]:
    rows: list[dict] = []
    for kind in ("sma", "ema"):
        lev = trend_cash_leverage(prices, kind=kind)
        rows.append(run_row(asset, prices, trend_label(kind), lev))

    for kind in ("sma", "ema"):
        lev, counts = guarded_lead_leverage_ma(prices, ma_kind=kind, max_leverage=max_leverage)
        rows.append(
            run_row(
                asset,
                prices,
                guarded_strategy_label(kind, max_leverage),
                lev,
                etp_returns=etp_panel,
                extra=counts,
            )
        )
    return rows


def run_asset_lqq3(prices: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for kind in ("sma", "ema"):
        lev = trend_cash_leverage(prices, kind=kind)
        rows.append(run_row("LQQ3.L", prices, trend_label(kind), lev))

    for kind in ("sma", "ema"):
        lev, counts = guarded_lead_leverage_ma(prices, ma_kind=kind, max_leverage=1.0)
        rows.append(
            run_row(
                "LQQ3.L",
                prices,
                guarded_strategy_label(kind, 1.0),
                lev,
                extra=counts,
            )
        )
    return rows


def build_summary(df: pd.DataFrame) -> dict:
    verdicts: dict[str, dict] = {}
    for asset in df["asset"].unique():
        sub = df[df["asset"] == asset]
        guarded = sub[sub["strategy"].str.contains("Guarded A5/B25")]
        sma_g = guarded[guarded["strategy"].str.contains("SMA20")].iloc[0]
        ema_g = guarded[guarded["strategy"].str.contains("EMA20")].iloc[0]
        verdicts[asset] = {
            "guarded_comparison": score_ema_vs_sma(sma_g.to_dict(), ema_g.to_dict()),
            "baseline_comparison": score_ema_vs_sma(
                sub[sub["strategy"] == "SMA20 1x/cash"].iloc[0].to_dict(),
                sub[sub["strategy"] == "EMA20 1x/cash"].iloc[0].to_dict(),
            ),
        }

    ema_guarded_wins = sum(
        1 for v in verdicts.values() if v["guarded_comparison"]["verdict"].startswith("EMA20 better")
    )
    sma_guarded_wins = sum(
        1 for v in verdicts.values() if v["guarded_comparison"]["verdict"].startswith("SMA20 better")
    )

    if ema_guarded_wins == len(verdicts):
        overall = "EMA20 wins on all assets — consider website update"
    elif sma_guarded_wins == len(verdicts):
        overall = "SMA20 wins on all assets — keep SMA20 default"
    else:
        overall = "Mixed across assets — keep SMA20 default on website"

    ranked = df.sort_values(["asset", "cagr"], ascending=[True, False])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "guarded_params": DEFAULT_GUARDED,
            "ma_window": BASE_SMA_WINDOW,
            "ema_method": "ewm(span=20, adjust=False, min_periods=20)",
            "spx_ndx_leverage": "full 0/1/2/3x via listed ETP daily returns",
            "lqq3_window": f"{LQQ3_START} onward (real LQQ3.L)",
            "signal_delay_days": 0,
            "signal_delay_note": "Matches website backtest convention (same-bar execution).",
        },
        "per_asset_verdicts": verdicts,
        "overall_recommendation": overall,
        "ranked_by_cagr": ranked[["asset", "strategy", "cagr", "sharpe", "max_drawdown", "rebalances"]]
        .to_dict(orient="records"),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    print("Loading SPX panel...", flush=True)
    spx = download_spx_panel()
    spx_etp = build_etp_return_panel(spx, SPX_ETP)
    print(f"  {len(spx)} days: {spx.index[0].date()} -> {spx.index[-1].date()}", flush=True)
    rows.extend(run_asset_spx_ndx("SPX", spx, spx_etp, max_leverage=3.0))

    print("Loading NDX panel...", flush=True)
    ndx = download_ndx_panel()
    ndx_etp = build_etp_return_panel(ndx, NDX_ETP)
    print(f"  {len(ndx)} days: {ndx.index[0].date()} -> {ndx.index[-1].date()}", flush=True)
    rows.extend(run_asset_spx_ndx("NDX", ndx, ndx_etp, max_leverage=3.0))

    print(f"Loading LQQ3 panel from {LQQ3_START}...", flush=True)
    lqq3 = download_lqq3_panel(LQQ3_TICKER, start=LQQ3_START)
    print(f"  {len(lqq3)} days: {lqq3.index[0].date()} -> {lqq3.index[-1].date()}", flush=True)
    rows.extend(run_asset_lqq3(lqq3))

    df = pd.DataFrame(rows).sort_values(["asset", "strategy"]).reset_index(drop=True)
    out_csv = OUTPUT_DIR / "comparison.csv"
    df.to_csv(out_csv, index=False)

    summary = build_summary(df)
    out_json = OUTPUT_DIR / "summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 100)
    print("EMA20 vs SMA20 — GUARDED A5/B25")
    print("=" * 100)
    for asset in df["asset"].unique():
        sub = df[df["asset"] == asset]
        print(f"\n--- {asset} ({sub.iloc[0]['start_date']} to {sub.iloc[0]['end_date']}) ---")
        for _, r in sub.iterrows():
            print(
                f"  {r['strategy']:<45} "
                f"CAGR {r['cagr'] * 100:6.2f}%  "
                f"Sharpe {r['sharpe']:5.2f}  "
                f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
                f"Rebal {int(r['rebalances']):4d}  "
                f"End ${r['end_$']:,.0f}"
            )
        v = summary["per_asset_verdicts"][asset]["guarded_comparison"]
        print(f"  >> Guarded verdict: {v['verdict']} (EMA wins {v['ema_wins']}, SMA wins {v['sma_wins']})")

    print(f"\nOverall: {summary['overall_recommendation']}")
    print(f"\nWrote {out_csv}")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
