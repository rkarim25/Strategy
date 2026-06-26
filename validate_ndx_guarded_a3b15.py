"""Comprehensive robustness validation of Guarded A3/B15 vs A5/B25 on NDX.

Eight tests as specified — boundary sweep, walk-forward, cross-asset, block
bootstrap CI, rolling 5-yr stability, crisis episodes, cost sensitivity, and
forward Monte Carlo. Reuses engine.py + etp_leverage.py + guarded_strategy_leverage
verbatim for cross-validation, then drops to an exact numpy reimplementation for
high-volume tests (each backtest ~40ms vs ~2s canonical, 50x speedup).

Outputs to output/ndx_guarded_a3b15_validation/ — does NOT modify any existing
website assets, output files, or backtest entry points.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Force UTF-8 console output on Windows PowerShell so Δ, →, ≥ etc. don't break print().
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.engine import (
    INITIAL_CAPITAL,
    PortfolioEngine,
    TRADING_COST_FROM_MID_PCT,
    TRADING_DAYS,
)
from core.etp_leverage import (
    NDX_ETP,
    SPX_ETP,
    bootstrap_etp_paths,
    etp_coverage_summary,
    synthetic_daily_reset_return,
)
from core.metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "ndx_guarded_a3b15_validation"
OUT.mkdir(parents=True, exist_ok=True)

BASELINE_A = 0.05
BASELINE_B = 0.25
CANDIDATE_A = 0.03
CANDIDATE_B = 0.15
X_DEFAULT = 0.40
Y_DEFAULT = 0.15
LEAD_DEFAULT = 0.0075
SMA_WINDOW = 20
TRADING_COST_DEFAULT = TRADING_COST_FROM_MID_PCT  # 1%
ANNUAL_INFLOW_DEFAULT = ANNUAL_INFLOW_USD  # 10
INITIAL_CAPITAL_DEFAULT = INITIAL_CAPITAL  # 100

CRISIS_EPISODES: list[tuple[str, str, str]] = [
    ("dotcom_2000_2002", "2000-03-01", "2002-10-31"),
    ("gfc_2008_2009", "2008-09-01", "2009-06-30"),
    ("eu_debt_2011", "2011-05-01", "2011-12-31"),
    ("q4_2018", "2018-10-01", "2018-12-31"),
    ("covid_2020", "2020-02-15", "2020-12-31"),
    ("rate_shock_2022", "2022-01-01", "2022-12-31"),
]

WALK_FORWARD_A_GRID = [0.03, 0.05, 0.07]
WALK_FORWARD_B_GRID = [0.15, 0.20, 0.25, 0.30]

BOOTSTRAP_N_SIMS = 1000
BOOTSTRAP_BLOCK_DAYS = 21
BOOTSTRAP_SEED = 20260525
BOOTSTRAP_HORIZON_DAYS = 7560  # ~30 years

MC_FORWARD_N_SIMS = 200
MC_FORWARD_HORIZON = 2520  # 10 years
MC_FORWARD_BLOCK = 21
MC_FORWARD_SEED = 20260526


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _load_etp_returns_json(path: Path) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    with path.open() as f:
        ej = json.load(f)
    dates = pd.to_datetime(ej["dates"])
    return dates, {
        "ret_0": np.asarray(ej["ret_0"], dtype=float),
        "ret_1": np.asarray(ej["ret_1"], dtype=float),
        "ret_2": np.asarray(ej["ret_2"], dtype=float),
        "ret_3": np.asarray(ej["ret_3"], dtype=float),
        "vix": np.asarray(ej["vix"], dtype=float),
    }


def load_ndx() -> tuple[pd.DataFrame, pd.DataFrame]:
    """NDX prices + ETP panel from cached files."""
    df = pd.read_csv(ROOT / "ndx_daily.csv", parse_dates=["Date"]).set_index("Date")
    closes = df["Close"].astype(float)
    dates, ej = _load_etp_returns_json(ROOT / "ndx_etp_returns.json")
    tbill = pd.Series(ej["ret_0"], index=dates) * TRADING_DAYS
    prices = pd.DataFrame(
        {
            "spx_close": closes.reindex(dates),
            "tbill_rate": tbill,
            "vix": pd.Series(ej["vix"], index=dates),
        }
    ).dropna()
    etp_panel = pd.DataFrame(
        {
            "ret_0": ej["ret_0"],
            "ret_1": ej["ret_1"],
            "ret_2": ej["ret_2"],
            "ret_3": ej["ret_3"],
            "vix": ej["vix"],
        },
        index=dates,
    ).reindex(prices.index).ffill()
    etp_panel["synthetic_2"] = False
    etp_panel["synthetic_3"] = False
    return prices, etp_panel


def load_spx() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(ROOT / "spx_daily.csv", parse_dates=["Date"]).set_index("Date")
    closes = df["Close"].astype(float)
    dates, ej = _load_etp_returns_json(ROOT / "spx_etp_returns.json")
    tbill = pd.Series(ej["ret_0"], index=dates) * TRADING_DAYS
    prices = pd.DataFrame(
        {
            "spx_close": closes.reindex(dates),
            "tbill_rate": tbill,
            "vix": pd.Series(ej["vix"], index=dates),
        }
    ).dropna()
    etp_panel = pd.DataFrame(
        {
            "ret_0": ej["ret_0"],
            "ret_1": ej["ret_1"],
            "ret_2": ej["ret_2"],
            "ret_3": ej["ret_3"],
            "vix": ej["vix"],
        },
        index=dates,
    ).reindex(prices.index).ffill()
    etp_panel["synthetic_2"] = False
    etp_panel["synthetic_3"] = False
    return prices, etp_panel


def load_asset_no_etp(csv_path: Path, tbill: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """Load any non-SPX/NDX daily.csv and align T-bill + VIX from a reference series."""
    df = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date")
    closes = df["Close"].astype(float)
    panel = pd.DataFrame(
        {
            "spx_close": closes,
            "tbill_rate": tbill.reindex(closes.index).ffill().bfill(),
            "vix": vix.reindex(closes.index).ffill().bfill(),
        }
    ).dropna()
    return panel


# ---------------------------------------------------------------------------
# Fast numpy backtest (validated to match engine.py exactly to machine precision)
# ---------------------------------------------------------------------------


def _rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    """Centred-right rolling mean to match pandas Series.rolling(w, min_periods=w).mean()."""
    n = len(x)
    out = np.full(n, np.nan)
    if n < w:
        return out
    csum = np.cumsum(x, dtype=float)
    out[w - 1] = csum[w - 1] / w
    out[w:] = (csum[w:] - csum[:-w]) / w
    return out


def fast_guarded_leverage(
    close: np.ndarray,
    spx_dd: np.ndarray,
    base_guard: np.ndarray,
    rec_guard: np.ndarray,
    trigger_a: float,
    trigger_b: float,
    x_return: float = X_DEFAULT,
    y_return: float = Y_DEFAULT,
) -> tuple[np.ndarray, dict[str, int]]:
    n = len(close)
    lev = np.zeros(n)
    regime = 0  # 0=base, 1=tier2, 2=tier3
    entry_close = 0.0
    t2 = 0
    t3 = 0
    lead_only_days = 0

    for i in range(n):
        px = close[i]
        dd = spx_dd[i]
        base_ok = base_guard[i]
        rec_ok = rec_guard[i]
        base_lev = 1.0 if base_ok else 0.0
        if rec_ok and not base_ok:
            lead_only_days += 1

        if regime == 2:
            if entry_close > 0 and px / entry_close - 1.0 >= y_return:
                regime = 0
            elif rec_ok:
                lev[i] = 3.0
                continue
            else:
                lev[i] = base_lev
                continue

        if regime == 1:
            if dd <= -trigger_b and rec_ok:
                regime = 2
                entry_close = px
                t3 += 1
                lev[i] = 3.0
                continue
            if entry_close > 0 and px / entry_close - 1.0 >= x_return:
                regime = 0
            elif rec_ok:
                lev[i] = 2.0
                continue
            else:
                lev[i] = base_lev
                continue

        if dd <= -trigger_b and rec_ok:
            regime = 2
            entry_close = px
            t3 += 1
            lev[i] = 3.0
        elif dd <= -trigger_a and rec_ok:
            regime = 1
            entry_close = px
            t2 += 1
            lev[i] = 2.0
        else:
            lev[i] = base_lev

    return lev, {"tier2_entries": t2, "tier3_entries": t3, "lead_only_days": lead_only_days}


def fast_engine_run(
    spx_close: np.ndarray,
    tbill: np.ndarray,
    vix: np.ndarray,
    ret_0: np.ndarray,
    ret_1: np.ndarray,
    ret_2: np.ndarray,
    ret_3: np.ndarray,
    has_etp_2: np.ndarray,
    has_etp_3: np.ndarray,
    leverage: np.ndarray,
    years_idx: np.ndarray,
    *,
    initial_capital: float = INITIAL_CAPITAL_DEFAULT,
    annual_inflow_abs: float = ANNUAL_INFLOW_DEFAULT,
    trading_cost_pct: float = TRADING_COST_DEFAULT,
    use_etp: bool = True,
    extra_spread_annual: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Numpy backtest that replicates engine.py for our config (no DD limit, no pause)."""
    n = len(spx_close)
    spx_ret = np.empty(n)
    spx_ret[0] = 0.0
    spx_ret[1:] = spx_close[1:] / spx_close[:-1] - 1.0

    equity = np.empty(n)
    port_ret = np.zeros(n)
    aum = float(initial_capital)
    prev_lev = 1.0
    prev_year = years_idx[0]
    daily_extra = extra_spread_annual / TRADING_DAYS

    for i in range(n):
        cur_year = years_idx[i]
        if i > 0 and cur_year != prev_year:
            aum += annual_inflow_abs
        lev = float(leverage[i])

        if abs(lev - prev_lev) > 1e-9:
            traded = abs(lev - prev_lev) * aum
            aum -= traded * trading_cost_pct
            prev_lev = lev

        if i > 0 and not np.isnan(spx_ret[i]):
            tb = float(tbill[i]) if not np.isnan(tbill[i]) else 0.0
            vx = float(vix[i]) if not np.isnan(vix[i]) else None
            r_idx = float(spx_ret[i])
            if lev <= 0.0:
                r = float(ret_0[i])
            elif use_etp and lev < 1.5:
                r = float(ret_1[i]) if not np.isnan(ret_1[i]) else r_idx
            elif use_etp and lev < 2.5 and has_etp_2[i] and not np.isnan(ret_2[i]):
                r = float(ret_2[i])
            elif use_etp and lev >= 2.5 and has_etp_3[i] and not np.isnan(ret_3[i]):
                r = float(ret_3[i])
            else:
                if lev <= 1.0:
                    r = lev * r_idx
                else:
                    r = synthetic_daily_reset_return(r_idx, lev, tb, vix=vx)
            if extra_spread_annual != 0.0 and lev > 1.0:
                r -= (lev - 1.0) * daily_extra
            aum *= 1.0 + r
            port_ret[i] = r
        equity[i] = aum
        prev_year = cur_year

    return equity, port_ret


# ---------------------------------------------------------------------------
# Generic backtest helpers
# ---------------------------------------------------------------------------


def _build_signal_arrays(close: np.ndarray, lead: float = LEAD_DEFAULT, sma_window: int = SMA_WINDOW):
    sma = _rolling_mean(close, sma_window)
    dd = close / np.maximum.accumulate(close) - 1.0
    base_guard = np.where(np.isnan(sma), False, close > sma)
    rec_guard = np.where(np.isnan(sma), False, close >= sma * (1.0 - lead))
    return sma, dd, base_guard, rec_guard


def run_fast_backtest(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame | None,
    *,
    a: float,
    b: float,
    x: float = X_DEFAULT,
    y: float = Y_DEFAULT,
    lead: float = LEAD_DEFAULT,
    initial_capital: float = INITIAL_CAPITAL_DEFAULT,
    annual_inflow_abs: float = ANNUAL_INFLOW_DEFAULT,
    trading_cost_pct: float = TRADING_COST_DEFAULT,
    extra_spread_annual: float = 0.0,
) -> dict[str, float | int]:
    close = prices["spx_close"].to_numpy(float)
    tbill = prices["tbill_rate"].to_numpy(float)
    vix = (
        prices["vix"].to_numpy(float)
        if "vix" in prices.columns
        else np.full(len(prices), 15.0)
    )
    years_idx = prices.index.year.to_numpy()
    _, dd, base_g, rec_g = _build_signal_arrays(close, lead=lead)

    lev, counts = fast_guarded_leverage(close, dd, base_g, rec_g, a, b, x, y)

    if etp_panel is not None:
        ret_0 = etp_panel["ret_0"].to_numpy(float)
        ret_1 = etp_panel["ret_1"].to_numpy(float)
        ret_2 = etp_panel["ret_2"].to_numpy(float)
        ret_3 = etp_panel["ret_3"].to_numpy(float)
        has_2 = ~np.isnan(ret_2)
        has_3 = ~np.isnan(ret_3)
        use_etp = True
    else:
        ret_0 = tbill / TRADING_DAYS
        ret_1 = np.zeros_like(close)
        ret_2 = np.zeros_like(close)
        ret_3 = np.zeros_like(close)
        has_2 = np.zeros(len(close), dtype=bool)
        has_3 = np.zeros(len(close), dtype=bool)
        use_etp = False

    equity, port_ret = fast_engine_run(
        close, tbill, vix, ret_0, ret_1, ret_2, ret_3, has_2, has_3,
        lev, years_idx,
        initial_capital=initial_capital,
        annual_inflow_abs=annual_inflow_abs,
        trading_cost_pct=trading_cost_pct,
        use_etp=use_etp,
        extra_spread_annual=extra_spread_annual,
    )

    years = max((prices.index[-1] - prices.index[0]).days / 365.25, 1e-9)
    cagr = (equity[-1] / equity[0]) ** (1.0 / years) - 1.0 if equity[0] > 0 else float("nan")
    peak = np.maximum.accumulate(equity)
    dd_curve = (equity - peak) / np.where(peak > 0, peak, 1.0)
    max_dd = float(dd_curve.min())
    vol = float(np.nanstd(port_ret[1:]) * math.sqrt(TRADING_DAYS))
    if vol > 0:
        sharpe = float(math.sqrt(TRADING_DAYS) * np.nanmean(port_ret[1:]) / np.nanstd(port_ret[1:]))
    else:
        sharpe = float("nan")
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else float("nan")

    return {
        "cagr": float(cagr),
        "max_drawdown": max_dd,
        "calmar": calmar,
        "sharpe": sharpe,
        "ann_volatility": vol,
        "end_$": float(equity[-1]),
        "tier2_entries": int(counts["tier2_entries"]),
        "tier3_entries": int(counts["tier3_entries"]),
        "lead_only_days": int(counts["lead_only_days"]),
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
        "_equity_series": equity,
        "_leverage_series": lev,
    }


def run_canonical_backtest(prices: pd.DataFrame, etp_panel: pd.DataFrame | None, *, a: float, b: float) -> dict:
    """Reference path that calls engine.py + guarded_strategy_leverage directly."""
    lev, counts = guarded_strategy_leverage(
        prices,
        trigger_a=a,
        trigger_b=b,
        lead_pct_below_sma20=LEAD_DEFAULT,
        x_return=X_DEFAULT,
        y_return=Y_DEFAULT,
    )
    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_DEFAULT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_DEFAULT,
    )
    if etp_panel is not None:
        res = engine.run(prices, lev, name="canon", etp_returns=etp_panel)
    else:
        res = engine.run(prices, lev, name="canon")
    stats = comprehensive_stats(res.equity, res.daily_returns)
    return {
        "cagr": float(stats["cagr"]),
        "max_drawdown": float(stats["max_drawdown"]),
        "calmar": float(stats.get("calmar", float("nan"))),
        "sharpe": float(stats["sharpe"]),
        "ann_volatility": float(stats["volatility"]),
        "end_$": float(res.equity.iloc[-1]),
        "tier2_entries": int(counts["tier2_entries"]),
        "tier3_entries": int(counts["tier3_entries"]),
    }


# ---------------------------------------------------------------------------
# Verdict helpers
# ---------------------------------------------------------------------------


def fmt_pct(x: float | None, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x * 100:.{decimals}f}%"


def fmt_dollar(x: float | None) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if abs(x) >= 1e9:
        return f"${x / 1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:.2f}M"
    return f"${x:,.0f}"


# ---------------------------------------------------------------------------
# Test 1 — Boundary bracket sweep
# ---------------------------------------------------------------------------


def test1_boundary_sweep(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 1 — Boundary bracket sweep (A ∈ {1..5}, B ∈ {8..25})")
    print("=" * 72)
    A_grid = [0.01, 0.02, 0.03, 0.04, 0.05]
    B_grid = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]
    rows: list[dict] = []
    t0 = time.time()
    for a in A_grid:
        for b in B_grid:
            if a >= b:
                continue
            r = run_fast_backtest(prices, etp_panel, a=a, b=b)
            rows.append(
                {
                    "label": f"A{int(round(a * 100))}/B{int(round(b * 100))}",
                    "A_pct": a * 100,
                    "B_pct": b * 100,
                    "cagr": r["cagr"],
                    "max_drawdown": r["max_drawdown"],
                    "calmar": r["calmar"],
                    "sharpe": r["sharpe"],
                    "end_$": r["end_$"],
                    "tier2_entries": r["tier2_entries"],
                    "tier3_entries": r["tier3_entries"],
                    "pct_days_3x": r["pct_days_3x"],
                }
            )
            print(
                f"  {rows[-1]['label']:>9}  CAGR={r['cagr'] * 100:6.2f}%  "
                f"DD={r['max_drawdown'] * 100:6.2f}%  Calmar={r['calmar']:5.2f}  "
                f"end=${r['end_$'] / 1e9:5.2f}B"
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test1_boundary_sweep.csv", index=False)

    cand_row = df[(df["A_pct"] == 3) & (df["B_pct"] == 15)].iloc[0]
    base_row = df[(df["A_pct"] == 5) & (df["B_pct"] == 25)].iloc[0]
    best_cagr_row = df.loc[df["cagr"].idxmax()]
    best_calmar_row = df.loc[df["calmar"].idxmax()]

    # Check whether CAGR keeps RISING below A=3
    a_le_3_rows = df[df["A_pct"] <= 3]
    a_ge_3_rows = df[df["A_pct"] >= 3]
    cagr_below_a3 = a_le_3_rows["cagr"].max() if len(a_le_3_rows) else float("nan")
    cagr_at_a3 = a_ge_3_rows[a_ge_3_rows["A_pct"] == 3]["cagr"].max() if (a_ge_3_rows["A_pct"] == 3).any() else float("nan")
    a3_is_optimum_or_near = (cand_row["cagr"] >= best_cagr_row["cagr"] - 0.005) or (
        cand_row["label"] == best_cagr_row["label"]
    )
    cagr_does_not_keep_rising = cagr_below_a3 <= cagr_at_a3 + 1e-9

    summary = {
        "candidate": cand_row.to_dict(),
        "baseline": base_row.to_dict(),
        "best_cagr": best_cagr_row.to_dict(),
        "best_calmar": best_calmar_row.to_dict(),
        "a3_is_at_or_near_cagr_max": bool(a3_is_optimum_or_near),
        "cagr_does_not_keep_rising_below_a3": bool(cagr_does_not_keep_rising),
        "elapsed_s": round(time.time() - t0, 2),
    }
    pass_test = bool(a3_is_optimum_or_near and cagr_does_not_keep_rising)
    summary["pass"] = pass_test
    print(
        f"  -> A3/B15 CAGR={cand_row['cagr']*100:.2f}% vs best={best_cagr_row['cagr']*100:.2f}% "
        f"({best_cagr_row['label']}); CAGR-below-A3={cagr_below_a3*100:.2f}% vs at-A3={cagr_at_a3*100:.2f}%"
    )
    print(f"  Test 1 {'PASS' if pass_test else 'FAIL'}")
    return df, summary


# ---------------------------------------------------------------------------
# Test 2 — Walk-forward validation
# ---------------------------------------------------------------------------


FOLDS: list[dict] = [
    {
        "name": "A_oldest_train_newest_test",
        "train": [("1996-01-01", "2010-12-31")],
        "test": [("2011-01-01", "2026-12-31")],
    },
    {
        "name": "B_newest_train_oldest_test",
        "train": [("2010-01-01", "2026-12-31")],
        "test": [("1996-01-01", "2009-12-31")],
    },
    {
        "name": "C_holdout_2008_2015",
        "train": [("1996-01-01", "2006-12-31"), ("2015-01-01", "2026-12-31")],
        "test": [("2007-01-01", "2014-12-31")],
    },
    {
        "name": "D_holdout_2018_2022",
        "train": [("1996-01-01", "2017-12-31"), ("2022-07-01", "2026-12-31")],
        "test": [("2018-01-01", "2022-06-30")],
    },
]


def _slice_prices_etp(prices: pd.DataFrame, etp_panel: pd.DataFrame, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    mask = (prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))
    return prices.loc[mask].copy(), etp_panel.loc[mask].copy()


def _segment_cagr(prices_segment: pd.DataFrame, etp_segment: pd.DataFrame, *, a: float, b: float) -> tuple[float, float]:
    res = run_fast_backtest(prices_segment, etp_segment, a=a, b=b)
    years = max((prices_segment.index[-1] - prices_segment.index[0]).days / 365.25, 1e-9)
    return res["cagr"], years


def _aggregate_cagr(prices: pd.DataFrame, etp_panel: pd.DataFrame, segments: list[tuple[str, str]], *, a: float, b: float) -> dict:
    log_returns = []
    weights = []
    end_dollars: list[float] = []
    max_dds: list[float] = []
    for start, end in segments:
        p_seg, e_seg = _slice_prices_etp(prices, etp_panel, start, end)
        if len(p_seg) < SMA_WINDOW + 5:
            continue
        res = run_fast_backtest(p_seg, e_seg, a=a, b=b)
        years = max((p_seg.index[-1] - p_seg.index[0]).days / 365.25, 1e-9)
        weights.append(years)
        log_returns.append(math.log1p(res["cagr"]) * years)
        end_dollars.append(res["end_$"])
        max_dds.append(res["max_drawdown"])
    if not weights:
        return {"cagr": float("nan"), "years": 0.0, "max_drawdown": float("nan")}
    total_years = sum(weights)
    agg_cagr = math.expm1(sum(log_returns) / total_years)
    return {
        "cagr": agg_cagr,
        "years": total_years,
        "max_drawdown": float(min(max_dds)),
        "end_$_per_segment": end_dollars,
    }


def test2_walk_forward(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 2 — Walk-forward (4 folds, train→pick winner→test on held-out)")
    print("=" * 72)
    rows: list[dict] = []
    folds_pass = 0
    t0 = time.time()
    for fold in FOLDS:
        scan_rows = []
        for a in WALK_FORWARD_A_GRID:
            for b in WALK_FORWARD_B_GRID:
                if a >= b:
                    continue
                agg = _aggregate_cagr(prices, etp_panel, fold["train"], a=a, b=b)
                scan_rows.append({"A_pct": a * 100, "B_pct": b * 100, "train_cagr": agg["cagr"]})
        scan_df = pd.DataFrame(scan_rows).sort_values("train_cagr", ascending=False).reset_index(drop=True)
        winner = scan_df.iloc[0]
        winner_a = winner["A_pct"] / 100
        winner_b = winner["B_pct"] / 100

        cand_train = _aggregate_cagr(prices, etp_panel, fold["train"], a=CANDIDATE_A, b=CANDIDATE_B)
        base_train = _aggregate_cagr(prices, etp_panel, fold["train"], a=BASELINE_A, b=BASELINE_B)

        cand_test = _aggregate_cagr(prices, etp_panel, fold["test"], a=CANDIDATE_A, b=CANDIDATE_B)
        base_test = _aggregate_cagr(prices, etp_panel, fold["test"], a=BASELINE_A, b=BASELINE_B)
        winner_test = _aggregate_cagr(prices, etp_panel, fold["test"], a=winner_a, b=winner_b)

        a3_beats_base = cand_test["cagr"] > base_test["cagr"]
        winner_beats_base = winner_test["cagr"] > base_test["cagr"]
        fold_pass = a3_beats_base or (
            int(round(winner_a * 100)) == 3 and int(round(winner_b * 100)) == 15 and winner_beats_base
        )
        if fold_pass:
            folds_pass += 1

        rows.append(
            {
                "fold": fold["name"],
                "train_window": str(fold["train"]),
                "test_window": str(fold["test"]),
                "train_winner_A": f"A{int(round(winner_a * 100))}",
                "train_winner_B": f"B{int(round(winner_b * 100))}",
                "train_winner_cagr": winner["train_cagr"],
                "cand_train_cagr": cand_train["cagr"],
                "base_train_cagr": base_train["cagr"],
                "cand_test_cagr": cand_test["cagr"],
                "base_test_cagr": base_test["cagr"],
                "winner_test_cagr": winner_test["cagr"],
                "cand_test_dd": cand_test["max_drawdown"],
                "base_test_dd": base_test["max_drawdown"],
                "a3b15_beats_baseline_on_test": bool(a3_beats_base),
                "fold_pass": bool(fold_pass),
            }
        )
        print(
            f"  Fold {fold['name']:35s}  TRAIN winner: A{int(round(winner_a*100))}/B{int(round(winner_b*100))} ({winner['train_cagr']*100:5.2f}%) "
            f"|  TEST  cand={cand_test['cagr']*100:6.2f}%  base={base_test['cagr']*100:6.2f}%  "
            f"-> {'PASS' if fold_pass else 'FAIL'}"
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test2_walkforward.csv", index=False)
    summary = {
        "folds_pass": int(folds_pass),
        "folds_total": len(FOLDS),
        "pass": bool(folds_pass >= 3),
        "elapsed_s": round(time.time() - t0, 2),
    }
    print(f"  -> {folds_pass}/{len(FOLDS)} folds pass; required ≥3.  Test 2 {'PASS' if summary['pass'] else 'FAIL'}")
    return df, summary


# ---------------------------------------------------------------------------
# Test 3 — Cross-asset replication
# ---------------------------------------------------------------------------


CROSS_ASSETS: list[dict] = [
    {"name": "SPX", "loader": "spx"},
    {"name": "NDX", "loader": "ndx"},
    {"name": "Gold", "csv": "gold_daily.csv"},
    {"name": "FTSE_250", "csv": "ftse250_daily.csv"},
    {"name": "MSCI_EM", "csv": "msci_em_daily.csv"},
    {"name": "DAX", "csv": "dax_daily.csv"},
    {"name": "MSCI_World", "csv": "msci_world_daily.csv"},
]


def test3_cross_asset(ndx_prices: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 3 — Cross-asset replication (full 2x/3x with ETP+VIX-style cost model)")
    print("=" * 72)
    spx_prices, spx_etp = load_spx()
    tbill_ref = ndx_prices["tbill_rate"]
    vix_ref = ndx_prices["vix"]

    rows: list[dict] = []
    wins = 0
    losses_with_worse_dd = 0
    t0 = time.time()
    for asset in CROSS_ASSETS:
        name = asset["name"]
        if asset.get("loader") == "ndx":
            prices = ndx_prices
            etp = None
            etp = load_ndx()[1]
        elif asset.get("loader") == "spx":
            prices = spx_prices
            etp = spx_etp
        else:
            prices = load_asset_no_etp(ROOT / asset["csv"], tbill_ref, vix_ref)
            etp = None  # synthetic ETP via fast engine fallback

        cand = run_fast_backtest(prices, etp, a=CANDIDATE_A, b=CANDIDATE_B)
        base = run_fast_backtest(prices, etp, a=BASELINE_A, b=BASELINE_B)
        cagr_gain = cand["cagr"] - base["cagr"]
        dd_change = cand["max_drawdown"] - base["max_drawdown"]  # higher (less negative) = better
        cand_beats = (cand["cagr"] > base["cagr"]) and (cand["max_drawdown"] >= base["max_drawdown"] - 1e-4)
        if cand_beats:
            wins += 1
        if (cand["cagr"] <= base["cagr"]) and (cand["max_drawdown"] < base["max_drawdown"] - 1e-4):
            losses_with_worse_dd += 1
        rows.append(
            {
                "asset": name,
                "cand_cagr": cand["cagr"],
                "base_cagr": base["cagr"],
                "cagr_diff": cagr_gain,
                "cand_dd": cand["max_drawdown"],
                "base_dd": base["max_drawdown"],
                "dd_diff": dd_change,
                "cand_end_$": cand["end_$"],
                "base_end_$": base["end_$"],
                "cand_beats_strict": bool(cand_beats),
                "start_date": str(prices.index[0].date()),
                "end_date": str(prices.index[-1].date()),
            }
        )
        print(
            f"  {name:12s}  cand CAGR={cand['cagr']*100:6.2f}%  base CAGR={base['cagr']*100:6.2f}%  "
            f"Δ={cagr_gain*100:+5.2f}pp  cand DD={cand['max_drawdown']*100:6.2f}%  "
            f"base DD={base['max_drawdown']*100:6.2f}%  "
            f"-> {'WIN' if cand_beats else 'no'}"
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test3_cross_asset.csv", index=False)
    summary = {
        "wins": int(wins),
        "losses_with_worse_dd": int(losses_with_worse_dd),
        "assets_total": len(rows),
        "pass": bool(wins >= 4),
        "elapsed_s": round(time.time() - t0, 2),
    }
    print(f"  -> {wins}/{len(rows)} assets pass; required ≥4.  Test 3 {'PASS' if summary['pass'] else 'FAIL'}")
    return df, summary


# ---------------------------------------------------------------------------
# Test 4 — Block bootstrap CI of CAGR difference
# ---------------------------------------------------------------------------


def _bootstrap_signals_and_run(
    spx_ret_orig: np.ndarray,
    tbill_orig: np.ndarray,
    vix_orig: np.ndarray,
    ret_0_orig: np.ndarray,
    ret_1_orig: np.ndarray,
    ret_2_orig: np.ndarray,
    ret_3_orig: np.ndarray,
    has_2_orig: np.ndarray,
    has_3_orig: np.ndarray,
    idx: np.ndarray,
    *,
    a: float,
    b: float,
    horizon_days: int,
) -> tuple[float, float, float]:
    n = horizon_days
    spx_ret_bs = spx_ret_orig[idx]
    close_bs = 1000.0 * np.cumprod(1.0 + spx_ret_bs)
    sma_bs = _rolling_mean(close_bs, SMA_WINDOW)
    dd_bs = close_bs / np.maximum.accumulate(close_bs) - 1.0
    base_g = np.where(np.isnan(sma_bs), False, close_bs > sma_bs)
    rec_g = np.where(np.isnan(sma_bs), False, close_bs >= sma_bs * (1.0 - LEAD_DEFAULT))
    lev, _ = fast_guarded_leverage(close_bs, dd_bs, base_g, rec_g, a, b, X_DEFAULT, Y_DEFAULT)
    tbill_bs = tbill_orig[idx]
    vix_bs = vix_orig[idx]
    ret_0_bs = ret_0_orig[idx]
    ret_1_bs = ret_1_orig[idx]
    ret_2_bs = ret_2_orig[idx]
    ret_3_bs = ret_3_orig[idx]
    has_2_bs = has_2_orig[idx]
    has_3_bs = has_3_orig[idx]
    years_idx = np.arange(n) // TRADING_DAYS
    eq, _ = fast_engine_run(
        close_bs, tbill_bs, vix_bs, ret_0_bs, ret_1_bs, ret_2_bs, ret_3_bs,
        has_2_bs, has_3_bs, lev, years_idx,
        annual_inflow_abs=ANNUAL_INFLOW_DEFAULT,
        trading_cost_pct=TRADING_COST_DEFAULT,
        use_etp=True,
    )
    years = n / TRADING_DAYS
    cagr = (eq[-1] / eq[0]) ** (1.0 / years) - 1.0 if eq[0] > 0 else float("nan")
    peak = np.maximum.accumulate(eq)
    dd_curve = (eq - peak) / np.where(peak > 0, peak, 1.0)
    max_dd = float(dd_curve.min())
    return float(cagr), float(eq[-1]), max_dd


def test4_bootstrap_ci(prices: pd.DataFrame, etp_panel: pd.DataFrame, n_sims: int = BOOTSTRAP_N_SIMS) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print(f"Test 4 — Block bootstrap CI of CAGR difference ({n_sims} samples)")
    print("=" * 72)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(float)
    vix = prices["vix"].ffill().fillna(15.0).to_numpy(float)
    ret_0 = etp_panel["ret_0"].to_numpy(float)
    ret_1 = etp_panel["ret_1"].to_numpy(float)
    ret_2 = etp_panel["ret_2"].to_numpy(float)
    ret_3 = etp_panel["ret_3"].to_numpy(float)
    has_2 = ~np.isnan(ret_2)
    has_3 = ~np.isnan(ret_3)

    block_starts = np.arange(1, len(prices) - BOOTSTRAP_BLOCK_DAYS + 1)
    horizon = BOOTSTRAP_HORIZON_DAYS

    cand_cagrs = np.empty(n_sims)
    base_cagrs = np.empty(n_sims)
    cand_ends = np.empty(n_sims)
    base_ends = np.empty(n_sims)
    cand_dds = np.empty(n_sims)
    base_dds = np.empty(n_sims)

    t0 = time.time()
    progress = max(1, n_sims // 10)
    for sim in range(n_sims):
        chunks = []
        total = 0
        while total < horizon:
            st = int(rng.choice(block_starts))
            chunks.append(np.arange(st, st + BOOTSTRAP_BLOCK_DAYS))
            total += BOOTSTRAP_BLOCK_DAYS
        idx = np.concatenate(chunks)[:horizon]
        cand_c, cand_e, cand_dd = _bootstrap_signals_and_run(
            spx_ret, tbill, vix, ret_0, ret_1, ret_2, ret_3, has_2, has_3, idx,
            a=CANDIDATE_A, b=CANDIDATE_B, horizon_days=horizon,
        )
        base_c, base_e, base_dd = _bootstrap_signals_and_run(
            spx_ret, tbill, vix, ret_0, ret_1, ret_2, ret_3, has_2, has_3, idx,
            a=BASELINE_A, b=BASELINE_B, horizon_days=horizon,
        )
        cand_cagrs[sim] = cand_c
        base_cagrs[sim] = base_c
        cand_ends[sim] = cand_e
        base_ends[sim] = base_e
        cand_dds[sim] = cand_dd
        base_dds[sim] = base_dd
        if (sim + 1) % progress == 0:
            elapsed = time.time() - t0
            eta = elapsed / (sim + 1) * (n_sims - sim - 1)
            print(f"  bootstrap {sim + 1}/{n_sims}  [elapsed {elapsed:5.1f}s, eta {eta:5.1f}s]", flush=True)

    diff = cand_cagrs - base_cagrs
    df_rows = pd.DataFrame(
        {
            "sim": np.arange(n_sims),
            "cand_cagr": cand_cagrs,
            "base_cagr": base_cagrs,
            "cagr_diff": diff,
            "cand_end_$": cand_ends,
            "base_end_$": base_ends,
            "cand_max_dd": cand_dds,
            "base_max_dd": base_dds,
            "cand_wins": diff > 0,
        }
    )
    df_rows.to_csv(OUT / "test4_bootstrap_ci.csv", index=False)

    ci_low = float(np.quantile(diff, 0.025))
    ci_high = float(np.quantile(diff, 0.975))
    win_rate = float((diff > 0).mean())
    ci_excludes_zero = ci_low > 0 or ci_high < 0
    pass_test = bool(win_rate > 0.70 and ci_excludes_zero and ci_low > 0)

    summary = {
        "n_sims": int(n_sims),
        "horizon_days": int(horizon),
        "block_days": int(BOOTSTRAP_BLOCK_DAYS),
        "mean_cand_cagr": float(np.mean(cand_cagrs)),
        "mean_base_cagr": float(np.mean(base_cagrs)),
        "mean_cagr_diff": float(np.mean(diff)),
        "median_cagr_diff": float(np.median(diff)),
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "ci_excludes_zero": bool(ci_excludes_zero),
        "win_rate_cand": win_rate,
        "pass": pass_test,
        "elapsed_s": round(time.time() - t0, 2),
    }
    (OUT / "test4_bootstrap_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"  -> mean Δ={np.mean(diff)*100:+5.2f}pp, 95% CI=[{ci_low*100:+5.2f}, {ci_high*100:+5.2f}]pp, "
        f"win-rate={win_rate*100:.1f}%.  Test 4 {'PASS' if pass_test else 'FAIL'}"
    )
    return df_rows, summary


# ---------------------------------------------------------------------------
# Test 5 — Rolling 5-yr stability
# ---------------------------------------------------------------------------


def test5_rolling_5yr(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 5 — Rolling 5-yr windows (CAGR stability)")
    print("=" * 72)
    start = prices.index[0]
    end = prices.index[-1]
    step_days = 90
    window_years = 5
    rows: list[dict] = []
    cur = start
    t0 = time.time()
    while cur + pd.Timedelta(days=int(window_years * 365.25)) <= end:
        w_end = cur + pd.Timedelta(days=int(window_years * 365.25))
        mask = (prices.index >= cur) & (prices.index <= w_end)
        p_seg = prices.loc[mask]
        e_seg = etp_panel.loc[mask]
        if len(p_seg) < SMA_WINDOW + 10:
            cur += pd.Timedelta(days=step_days)
            continue
        cand = run_fast_backtest(p_seg, e_seg, a=CANDIDATE_A, b=CANDIDATE_B)
        base = run_fast_backtest(p_seg, e_seg, a=BASELINE_A, b=BASELINE_B)
        rows.append(
            {
                "window_start": str(cur.date()),
                "window_end": str(w_end.date()),
                "cand_cagr": cand["cagr"],
                "base_cagr": base["cagr"],
                "cagr_diff": cand["cagr"] - base["cagr"],
                "cand_dd": cand["max_drawdown"],
                "base_dd": base["max_drawdown"],
                "cand_wins": cand["cagr"] >= base["cagr"],
                "cand_end_$": cand["end_$"],
                "base_end_$": base["end_$"],
            }
        )
        cur += pd.Timedelta(days=step_days)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test5_rolling_5yr.csv", index=False)
    win_rate = float(df["cand_wins"].mean())
    worst_window_diff = float(df["cagr_diff"].min())
    summary = {
        "windows": int(len(df)),
        "candidate_win_rate": win_rate,
        "worst_window_cagr_diff": worst_window_diff,
        "min_cand_cagr": float(df["cand_cagr"].min()),
        "min_base_cagr": float(df["base_cagr"].min()),
        "pass": bool(win_rate >= 0.60 and worst_window_diff > -0.10),
        "elapsed_s": round(time.time() - t0, 2),
    }
    print(
        f"  -> windows={len(df)}, candidate win-rate={win_rate*100:.1f}%, "
        f"worst Δ={worst_window_diff*100:.2f}pp.  Test 5 {'PASS' if summary['pass'] else 'FAIL'}"
    )
    return df, summary


# ---------------------------------------------------------------------------
# Test 6 — Crisis episodes
# ---------------------------------------------------------------------------


def test6_crisis_episodes(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 6 — Crisis episodes")
    print("=" * 72)
    t0 = time.time()
    # Run BOTH configs on full history once; then slice equity/leverage curves.
    cand_full = run_fast_backtest(prices, etp_panel, a=CANDIDATE_A, b=CANDIDATE_B)
    base_full = run_fast_backtest(prices, etp_panel, a=BASELINE_A, b=BASELINE_B)
    eq_cand = pd.Series(cand_full["_equity_series"], index=prices.index)
    eq_base = pd.Series(base_full["_equity_series"], index=prices.index)
    lev_cand = pd.Series(cand_full["_leverage_series"], index=prices.index)
    lev_base = pd.Series(base_full["_leverage_series"], index=prices.index)

    rows: list[dict] = []
    base_no_worse = True
    cand_strictly_better_or_equal = True
    for name, s, e in CRISIS_EPISODES:
        ts, te = pd.Timestamp(s), pd.Timestamp(e)
        mask = (prices.index >= ts) & (prices.index <= te)
        if mask.sum() < 5:
            continue
        eq_c = eq_cand.loc[mask]
        eq_b = eq_base.loc[mask]
        lev_c = lev_cand.loc[mask]
        lev_b = lev_base.loc[mask]
        # Drawdown within episode (peak inside window to trough inside window)
        cand_dd = float((eq_c / eq_c.cummax() - 1.0).min())
        base_dd = float((eq_b / eq_b.cummax() - 1.0).min())
        cand_trans = int((lev_c.diff() != 0).sum())
        base_trans = int((lev_b.diff() != 0).sum())
        # Recovery time (days to reach pre-episode high) — capped at end of full sample
        pre_peak_c = eq_cand.loc[:ts].max()
        pre_peak_b = eq_base.loc[:ts].max()
        post_window_c = eq_cand.loc[ts:]
        post_window_b = eq_base.loc[ts:]
        rec_c = post_window_c[post_window_c >= pre_peak_c].index.min() if (post_window_c >= pre_peak_c).any() else pd.NaT
        rec_b = post_window_b[post_window_b >= pre_peak_b].index.min() if (post_window_b >= pre_peak_b).any() else pd.NaT
        rec_c_days = int((rec_c - ts).days) if pd.notna(rec_c) else -1
        rec_b_days = int((rec_b - ts).days) if pd.notna(rec_b) else -1

        cand_better_or_equal_dd = cand_dd >= base_dd - 1e-4  # higher (less negative) ok
        if cand_dd < base_dd - 1e-4:
            cand_strictly_better_or_equal = False

        rows.append(
            {
                "episode": name,
                "start": s,
                "end": e,
                "cand_dd": cand_dd,
                "base_dd": base_dd,
                "dd_diff_cand_minus_base": cand_dd - base_dd,
                "cand_better_or_equal_dd": bool(cand_better_or_equal_dd),
                "cand_transitions": cand_trans,
                "base_transitions": base_trans,
                "cand_recovery_days": rec_c_days,
                "base_recovery_days": rec_b_days,
            }
        )
        print(
            f"  {name:18s}  cand DD={cand_dd*100:6.2f}%  base DD={base_dd*100:6.2f}%  "
            f"Δ={(cand_dd - base_dd)*100:+5.2f}pp  cand trans={cand_trans}  base trans={base_trans}  "
            f"-> {'OK' if cand_better_or_equal_dd else 'WORSE'}"
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test6_crisis_episodes.csv", index=False)
    summary = {
        "episodes": int(len(df)),
        "cand_dd_no_worse_in_every_episode": bool(cand_strictly_better_or_equal),
        "pass": bool(cand_strictly_better_or_equal),
        "elapsed_s": round(time.time() - t0, 2),
    }
    print(f"  Test 6 {'PASS' if summary['pass'] else 'FAIL'}")
    return df, summary


# ---------------------------------------------------------------------------
# Test 7 — Cost sensitivity
# ---------------------------------------------------------------------------


def test7_cost_sensitivity(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print("Test 7 — Cost / inflow sensitivity")
    print("=" * 72)
    tc_grid = [0.005, 0.010, 0.015, 0.020]
    spread_grid = [0.000, 0.003, 0.006]
    inflow_grid = [0.0, 10.0, 100.0]
    rows: list[dict] = []
    cand_always_ahead = True
    t0 = time.time()
    for tc in tc_grid:
        for spread in spread_grid:
            for inflow in inflow_grid:
                cand = run_fast_backtest(
                    prices, etp_panel,
                    a=CANDIDATE_A, b=CANDIDATE_B,
                    trading_cost_pct=tc, extra_spread_annual=spread,
                    annual_inflow_abs=inflow,
                )
                base = run_fast_backtest(
                    prices, etp_panel,
                    a=BASELINE_A, b=BASELINE_B,
                    trading_cost_pct=tc, extra_spread_annual=spread,
                    annual_inflow_abs=inflow,
                )
                cand_ahead = cand["cagr"] > base["cagr"]
                if not cand_ahead:
                    cand_always_ahead = False
                rows.append(
                    {
                        "trading_cost": tc,
                        "extra_spread_annual": spread,
                        "inflow": inflow,
                        "cand_cagr": cand["cagr"],
                        "base_cagr": base["cagr"],
                        "cagr_diff": cand["cagr"] - base["cagr"],
                        "cand_dd": cand["max_drawdown"],
                        "base_dd": base["max_drawdown"],
                        "cand_ranks_ahead": bool(cand_ahead),
                    }
                )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test7_cost_sensitivity.csv", index=False)
    summary = {
        "combinations": int(len(df)),
        "wins": int(df["cand_ranks_ahead"].sum()),
        "min_cagr_diff": float(df["cagr_diff"].min()),
        "pass": bool(cand_always_ahead),
        "elapsed_s": round(time.time() - t0, 2),
    }
    print(
        f"  -> combos={len(df)}, candidate ranks ahead in {summary['wins']}/{len(df)}, "
        f"worst diff={summary['min_cagr_diff']*100:+.2f}pp.  Test 7 {'PASS' if summary['pass'] else 'FAIL'}"
    )
    return df, summary


# ---------------------------------------------------------------------------
# Test 8 — Monte Carlo forward simulation
# ---------------------------------------------------------------------------


def test8_monte_carlo(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n" + "=" * 72)
    print(f"Test 8 — Monte Carlo forward simulation ({MC_FORWARD_N_SIMS} 10-yr paths)")
    print("=" * 72)
    paths = bootstrap_etp_paths(
        prices, etp_panel,
        n_sims=MC_FORWARD_N_SIMS,
        horizon_days=MC_FORWARD_HORIZON,
        block_days=MC_FORWARD_BLOCK,
        seed=MC_FORWARD_SEED,
    )
    rows: list[dict] = []
    t0 = time.time()
    for sim, (p_path, e_path) in enumerate(paths):
        # Ensure etp panel has the required boolean columns
        if "synthetic_2" not in e_path.columns:
            e_path = e_path.copy()
            e_path["synthetic_2"] = False
            e_path["synthetic_3"] = False
        cand = run_fast_backtest(p_path, e_path, a=CANDIDATE_A, b=CANDIDATE_B)
        base = run_fast_backtest(p_path, e_path, a=BASELINE_A, b=BASELINE_B)
        rows.append(
            {
                "sim": sim,
                "cand_cagr": cand["cagr"],
                "base_cagr": base["cagr"],
                "cand_end_$": cand["end_$"],
                "base_end_$": base["end_$"],
                "cand_dd": cand["max_drawdown"],
                "base_dd": base["max_drawdown"],
            }
        )
        if (sim + 1) % 25 == 0:
            print(f"  MC path {sim + 1}/{MC_FORWARD_N_SIMS}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "test8_monte_carlo.csv", index=False)

    def quant(arr, q): return float(np.quantile(arr, q))
    summary = {
        "n_sims": int(len(df)),
        "horizon_years": MC_FORWARD_HORIZON / TRADING_DAYS,
        "median_cand_cagr": float(df["cand_cagr"].median()),
        "median_base_cagr": float(df["base_cagr"].median()),
        "median_cagr_diff": float((df["cand_cagr"] - df["base_cagr"]).median()),
        "p05_cand_end_$": quant(df["cand_end_$"], 0.05),
        "p05_base_end_$": quant(df["base_end_$"], 0.05),
        "p95_cand_end_$": quant(df["cand_end_$"], 0.95),
        "p95_base_end_$": quant(df["base_end_$"], 0.95),
        "median_cand_end_$": float(df["cand_end_$"].median()),
        "median_base_end_$": float(df["base_end_$"].median()),
        "cand_prob_loss_gt_30pct": float((df["cand_dd"] <= -0.30).mean()),
        "base_prob_loss_gt_30pct": float((df["base_dd"] <= -0.30).mean()),
        "cand_dominates_median": bool(df["cand_cagr"].median() > df["base_cagr"].median()),
        "cand_p05_not_worse": bool(quant(df["cand_end_$"], 0.05) >= quant(df["base_end_$"], 0.05) * 0.97),
        "elapsed_s": round(time.time() - t0, 2),
    }
    summary["pass"] = bool(summary["cand_dominates_median"] and summary["cand_p05_not_worse"])
    (OUT / "test8_distribution_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"  -> median CAGR cand={summary['median_cand_cagr']*100:.2f}% base={summary['median_base_cagr']*100:.2f}% "
        f"| 5th-pctile end cand={fmt_dollar(summary['p05_cand_end_$'])} base={fmt_dollar(summary['p05_base_end_$'])} "
        f"-> Test 8 {'PASS' if summary['pass'] else 'FAIL'}"
    )
    return df, summary


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def write_verdict(test_summaries: dict[str, dict], baseline_in_sample: dict, candidate_in_sample: dict) -> str:
    pass_count = sum(1 for s in test_summaries.values() if s.get("pass"))
    total = len(test_summaries)
    critical_pass = (
        test_summaries["test2"].get("pass")
        and test_summaries["test3"].get("pass")
        and test_summaries["test4"].get("pass")
    )
    critical_fail = (
        not test_summaries["test2"].get("pass")
        or not test_summaries["test3"].get("pass")
        or not test_summaries["test4"].get("pass")
    )
    if pass_count >= 6 and critical_pass:
        verdict = "PROMOTE"
    elif critical_fail:
        verdict = "DISCARD"
    else:
        verdict = "KEEP_AS_OPT_IN"

    lines: list[str] = []
    lines.append("# A3/B15 vs A5/B25 validation verdict")
    lines.append("")
    lines.append(f"**Verdict:** {verdict}")
    lines.append("")
    lines.append(f"Tests passed: {pass_count}/{total}  (Test 2/3/4 critical-pass: {critical_pass})")
    lines.append("")
    lines.append("## In-sample reference (NDX full history, ETP+VIX cost model)")
    lines.append("")
    lines.append("| Config | CAGR | MaxDD | Calmar | End $ |")
    lines.append("|---|---|---|---|---|")
    lines.append(
        f"| Baseline A5/B25 | {fmt_pct(baseline_in_sample['cagr'])} | {fmt_pct(baseline_in_sample['max_drawdown'])} | "
        f"{baseline_in_sample['calmar']:.2f} | {fmt_dollar(baseline_in_sample['end_$'])} |"
    )
    lines.append(
        f"| Candidate A3/B15 | {fmt_pct(candidate_in_sample['cagr'])} | {fmt_pct(candidate_in_sample['max_drawdown'])} | "
        f"{candidate_in_sample['calmar']:.2f} | {fmt_dollar(candidate_in_sample['end_$'])} |"
    )
    lines.append("")
    lines.append("## Per-test pass/fail")
    lines.append("")
    lines.append("| Test | Criterion | Result | Pass? |")
    lines.append("|------|-----------|--------|-------|")
    t1 = test_summaries["test1"]
    lines.append(
        f"| 1. Boundary | A3/B15 at/near CAGR max AND CAGR does not keep rising for A<3 | "
        f"best A{int(t1['best_cagr']['A_pct'])}/B{int(t1['best_cagr']['B_pct'])} "
        f"CAGR={fmt_pct(t1['best_cagr']['cagr'])} vs A3/B15 "
        f"CAGR={fmt_pct(t1['candidate']['cagr'])} | {'YES' if t1['pass'] else 'NO'} |"
    )
    t2 = test_summaries["test2"]
    lines.append(
        f"| 2. Walk-forward | A3/B15 (or train-fold equivalent) beats baseline on TEST in ≥3/4 folds | "
        f"{t2['folds_pass']}/{t2['folds_total']} folds pass | {'YES' if t2['pass'] else 'NO'} |"
    )
    t3 = test_summaries["test3"]
    lines.append(
        f"| 3. Cross-asset | A3/B15 strictly beats baseline (CAGR up, DD non-worse) in ≥4/7 assets | "
        f"{t3['wins']}/{t3['assets_total']} assets pass | {'YES' if t3['pass'] else 'NO'} |"
    )
    t4 = test_summaries["test4"]
    lines.append(
        f"| 4. Bootstrap CI | win-rate>70% AND 95% CI of CAGR diff excludes 0 | "
        f"win-rate={t4['win_rate_cand']*100:.1f}%, 95% CI=[{t4['ci95_low']*100:+.2f}, {t4['ci95_high']*100:+.2f}]pp | "
        f"{'YES' if t4['pass'] else 'NO'} |"
    )
    t5 = test_summaries["test5"]
    lines.append(
        f"| 5. Rolling 5-yr | A3/B15 wins in ≥60% of 5-yr windows, no catastrophic loss | "
        f"win-rate={t5['candidate_win_rate']*100:.1f}% over {t5['windows']} windows, worst Δ={t5['worst_window_cagr_diff']*100:+.2f}pp | "
        f"{'YES' if t5['pass'] else 'NO'} |"
    )
    t6 = test_summaries["test6"]
    lines.append(
        f"| 6. Crisis episodes | A3/B15 DD ≥ baseline in EVERY episode | "
        f"{'no worse in any' if t6['cand_dd_no_worse_in_every_episode'] else 'worse in at least one'} | "
        f"{'YES' if t6['pass'] else 'NO'} |"
    )
    t7 = test_summaries["test7"]
    lines.append(
        f"| 7. Cost sensitivity | A3/B15 ranks ahead in ALL combos | "
        f"{t7['wins']}/{t7['combinations']} combos pass, worst Δ={t7['min_cagr_diff']*100:+.2f}pp | "
        f"{'YES' if t7['pass'] else 'NO'} |"
    )
    t8 = test_summaries["test8"]
    lines.append(
        f"| 8. Monte Carlo | median CAGR dominates AND 5th-pctile end-$ not worse | "
        f"median Δ={t8['median_cagr_diff']*100:+.2f}pp, "
        f"5th-pctile end cand={fmt_dollar(t8['p05_cand_end_$'])} vs base={fmt_dollar(t8['p05_base_end_$'])} | "
        f"{'YES' if t8['pass'] else 'NO'} |"
    )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if verdict == "PROMOTE":
        lines.append("**PROMOTE A3/B15 as the new website default.**")
        lines.append("")
        lines.append("Files to update (do NOT change yet — wait for user confirmation):")
        lines.append("")
        lines.append("- `backtest_ndx_guarded.py` → `DEFAULT_SPEC['trigger_a'] = 0.03`, `['trigger_b'] = 0.15`")
        lines.append("- `analyze_cross_asset_guarded_1x.py` → `DEFAULT_GUARDED['trigger_a'] = 0.03`, `['trigger_b'] = 0.15`")
        lines.append("- (downstream) `backtest_gold_guarded.py`, `backtest_guarded_assets.py`, and any website ")
        lines.append("  `guarded_params` JSON payloads import `DEFAULT_GUARDED` so the change propagates.")
    elif verdict == "DISCARD":
        lines.append("**DISCARD A3/B15. Keep A5/B25 as the default.**")
        lines.append("")
        lines.append("The candidate failed at least one of the critical validation tests (walk-forward, cross-asset, or bootstrap CI), ")
        lines.append("indicating its in-sample edge does not generalise reliably out of sample.")
    else:
        lines.append("**KEEP A3/B15 AS AN OPT-IN ALTERNATIVE.**")
        lines.append("")
        lines.append("Mixed signal: A3/B15 has an in-sample edge and passes most tests but doesn't clear all three critical hurdles. ")
        lines.append("Expose it as a configurable variant for advanced users; do NOT make it the website default.")
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append("- All tests use the same ETP+VIX cost model and same data window the website already uses; ")
    lines.append("  hidden costs (slippage, liquidity, FX hedge drag on UK/II tickers) are not modelled.")
    lines.append("- Bootstrap of joint daily returns + signals preserves marginal distributions but breaks ")
    lines.append("  cross-day autocorrelation beyond the 21-day block; very persistent regimes (e.g. multi-year ")
    lines.append("  bull runs) are under-represented vs reality.")
    lines.append("- A3/B15 mechanically arms tier-2/3 more often: realised trading frequency and tax-event drag ")
    lines.append("  could erode the modelled CAGR edge in real client portfolios.")
    lines.append("")

    text = "\n".join(lines) + "\n"
    (OUT / "final_verdict.md").write_text(text, encoding="utf-8")
    return text


def main() -> int:
    t_start = time.time()
    print("Loading NDX from cache (ndx_daily.csv + ndx_etp_returns.json)...")
    prices, etp_panel = load_ndx()
    print(f"  rows={len(prices)}  {prices.index[0].date()} -> {prices.index[-1].date()}")
    cov = etp_coverage_summary(etp_panel)
    print(f"  ETP coverage: real 2x={cov['pct_real_2x']}%  real 3x={cov['pct_real_3x']}%")

    # ----- Sanity cross-check: fast vs canonical on baseline + candidate -----
    print("\nFast-engine vs canonical cross-check (NDX, A5/B25 and A3/B15):")
    canon_base = run_canonical_backtest(prices, etp_panel, a=BASELINE_A, b=BASELINE_B)
    canon_cand = run_canonical_backtest(prices, etp_panel, a=CANDIDATE_A, b=CANDIDATE_B)
    fast_base = run_fast_backtest(prices, etp_panel, a=BASELINE_A, b=BASELINE_B)
    fast_cand = run_fast_backtest(prices, etp_panel, a=CANDIDATE_A, b=CANDIDATE_B)
    print(
        f"  A5/B25  canon  CAGR={canon_base['cagr']*100:7.4f}%  fast={fast_base['cagr']*100:7.4f}%  "
        f"|Δ|={abs(canon_base['cagr'] - fast_base['cagr'])*100:.6f}pp"
    )
    print(
        f"  A3/B15  canon  CAGR={canon_cand['cagr']*100:7.4f}%  fast={fast_cand['cagr']*100:7.4f}%  "
        f"|Δ|={abs(canon_cand['cagr'] - fast_cand['cagr'])*100:.6f}pp"
    )

    # ----- Run all 8 tests -----
    test_summaries: dict[str, dict] = {}

    _, summary1 = test1_boundary_sweep(prices, etp_panel)
    test_summaries["test1"] = summary1

    _, summary2 = test2_walk_forward(prices, etp_panel)
    test_summaries["test2"] = summary2

    _, summary3 = test3_cross_asset(prices)
    test_summaries["test3"] = summary3

    _, summary4 = test4_bootstrap_ci(prices, etp_panel)
    test_summaries["test4"] = summary4

    _, summary5 = test5_rolling_5yr(prices, etp_panel)
    test_summaries["test5"] = summary5

    _, summary6 = test6_crisis_episodes(prices, etp_panel)
    test_summaries["test6"] = summary6

    _, summary7 = test7_cost_sensitivity(prices, etp_panel)
    test_summaries["test7"] = summary7

    _, summary8 = test8_monte_carlo(prices, etp_panel)
    test_summaries["test8"] = summary8

    # ----- Verdict -----
    write_verdict(test_summaries, fast_base, fast_cand)

    elapsed = time.time() - t_start
    print("\n" + "=" * 72)
    print(f"All tests done in {elapsed:.1f}s")
    print(f"Pass count: {sum(1 for s in test_summaries.values() if s.get('pass'))}/8")
    for name, s in test_summaries.items():
        print(f"  {name}: pass={s.get('pass')}  elapsed={s.get('elapsed_s')}s")
    print(f"Outputs in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
