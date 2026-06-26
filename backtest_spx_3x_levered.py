"""Backtest and Monte Carlo for S&P 500 3x Levered strategies (B1–B4).

Generates all backtest data for the SPX 3x Levered tab:
  - spx_3x_levered_site_data.json
  - spx_3x_levered_etp_returns.json
  - output/spx_3x_levered/spx_3x_levered_comparison.csv
  - output/spx_3x_levered/spx_3x_levered_monte_carlo_paths.csv

Strategies:
  B1 – SMA200 ±3% Band + RSI>30 Exit 3x (default)
  B2 – SMA200 ±3% Band + RSI>30 Exit 2x
  B3 – SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x
  B4 – SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x

Benchmarks:
  Buy & Hold SPY 1x / SSO 2x / UPRO 3x
  SMA200 ±3% Band 3x (plain)
  SMA200 ±3% Band 2x (plain)
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from core.engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    ANNUAL_CASH_INFLOW_PCT,
    PortfolioEngine,
)
from core.etp_leverage import (
    MC_ETP_METHOD,
    SPX_ETP,
    bootstrap_etp_paths,
    build_etp_return_panel,
    etp_coverage_summary,
    export_etp_returns_json,
)
from core.indicators import sma, rsi
from core.metrics import comprehensive_stats
from core.price_cleaning import clean_close_series

ROOT = Path(__file__).resolve().parent
SPX_TICKER = "^GSPC"
TBILL_TICKER = "^IRX"
VIX_TICKER = "^VIX"
YEARS = 30
OUTPUT_DIR = ROOT / "output" / "spx_3x_levered"
SITE_DATA_JSON = ROOT / "spx_3x_levered_site_data.json"
ETP_JSON = ROOT / "spx_3x_levered_etp_returns.json"

N_SIMS = 200
HORIZON_DAYS = 2520  # 10 years
BLOCK_DAYS = 21
SEED = 20260619

# ---------------------------------------------------------------------------
# Strategy specs
# ---------------------------------------------------------------------------

B1_SPEC = {
    "strategy": "SMA200 ±3% Band + RSI>30 Exit 3x",
    "sma_window": 200,
    "band_pct": 0.03,
    "rsi_window": 14,
    "rsi_exit": 30,
    "base_leverage": 3.0,
    "scale_mode": "fixed",
}

B2_SPEC = {
    "strategy": "SMA200 ±3% Band + RSI>30 Exit 2x",
    "sma_window": 200,
    "band_pct": 0.03,
    "rsi_window": 14,
    "rsi_exit": 30,
    "base_leverage": 2.0,
    "scale_mode": "fixed",
}

B3_SPEC = {
    "strategy": "SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x",
    "sma_window": 200,
    "band_pct": 0.03,
    "rsi_window": 14,
    "rsi_exit": 30,
    "base_leverage": 3.0,
    "scale_mode": "rsi",
    "rsi_zones": [(30, 3), (50, 2), (70, 1), (100, 0)],
}

B4_SPEC = {
    "strategy": "SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x",
    "sma_window": 200,
    "band_pct": 0.03,
    "rsi_window": 14,
    "rsi_exit": 30,
    "base_leverage": 3.0,
    "scale_mode": "vix",
    "vix_zones": [(30, 3), (20, 2), (0, 1)],
}

DEFAULT_SPEC = B1_SPEC

# ---------------------------------------------------------------------------
# Signal functions (self-contained, adapted from sweep_spx_pareto.py and
# sweep_spx_counter_cyclical.py)
# ---------------------------------------------------------------------------


def sma_band_signal(
    prices: pd.DataFrame,
    window: int = 200,
    band_pct: float = 0.03,
) -> pd.Series:
    """SMA crossover with hysteresis band — returns 0 (cash) or 1 (long).

    Rules:
      - price > SMA × (1 + band_pct)  →  long (1)
      - price < SMA × (1 - band_pct)  →  cash (0)
      - price within band              →  hold previous state
    """
    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    upper_mult = 1.0 + band_pct
    lower_mult = 1.0 - band_pct

    for i in range(len(prices)):
        if i < window:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        if pd.isna(c) or pd.isna(sma_val):
            lev.iloc[i] = current
            continue
        if c > sma_val * upper_mult:
            current = 1.0
        elif c < sma_val * lower_mult:
            current = 0.0
        # else: within band → hold current
        lev.iloc[i] = current
    return lev


def rsi_exit_filter_on_series(
    lev_series: pd.Series,
    prices: pd.DataFrame,
    rsi_threshold: float = 30.0,
    rsi_period: int = 14,
) -> pd.Series:
    """Block exit when RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash (0) but RSI is below the threshold
    (deeply oversold), stay at the previous non-zero leverage instead.
    Entry is controlled normally by the base signal.
    Works with dynamic leverage (1-3x), preserving the current leverage level.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    result = lev_series.copy()
    in_position = False
    current_lev = 0.0

    for i in range(len(result)):
        bl = lev_series.iloc[i]
        rsi_val = r.iloc[i]

        if pd.isna(bl):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                in_position = True
                current_lev = bl
                result.iloc[i] = bl
            # else: stay cash (already 0.0)
        else:
            if bl == 0.0:  # base signal says exit
                if pd.notna(rsi_val) and rsi_val < rsi_threshold:
                    # Oversold — block exit, stay at current leverage
                    result.iloc[i] = current_lev
                else:
                    in_position = False
                    current_lev = 0.0
                    result.iloc[i] = 0.0
            else:
                # Update current leverage (may have changed)
                current_lev = bl
                result.iloc[i] = bl
    return result


def rsi_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
    rsi_period: int = 14,
) -> pd.Series:
    """Return leverage (0-3) based on RSI zone.

    zones: list of (rsi_threshold, leverage) sorted by threshold ascending.
    Example: [(30, 3), (50, 2), (70, 1), (100, 0)]
    Means: RSI ≤ 30 → 3x, 30 < RSI ≤ 50 → 2x, 50 < RSI ≤ 70 → 1x, RSI > 70 → 0.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    lev = pd.Series(0.0, index=prices.index)

    for i in range(len(prices)):
        rsi_val = r.iloc[i]
        if pd.isna(rsi_val):
            continue
        for threshold, leverage in zones:
            if rsi_val <= threshold:
                lev.iloc[i] = float(leverage)
                break
    return lev


def vix_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
) -> pd.Series:
    """Return leverage (0-3) based on VIX level.

    zones: list of (vix_threshold, leverage) sorted by threshold DESCENDING.
    Example: [(30, 3), (20, 2), (0, 1)]
    Means: VIX > 30 → 3x, 20 < VIX ≤ 30 → 2x, VIX ≤ 20 → 1x.
    """
    vix_series = prices["vix"].ffill().fillna(0.0)
    lev = pd.Series(0.0, index=prices.index)

    for i in range(len(prices)):
        v = vix_series.iloc[i]
        if pd.isna(v):
            continue
        for threshold, leverage in zones:
            if v > threshold:
                lev.iloc[i] = float(leverage)
                break
    return lev


def band_trend_hybrid(
    prices: pd.DataFrame,
    sma_window: int,
    band_pct: float,
    cc_lev: pd.Series,
) -> pd.Series:
    """SMA band hysteresis for trend detection + leverage scaling.

    When the band signal says "long" (price > SMA×(1+band) or within band and
    previously long), use cc_lev to determine leverage (1-3x).
    When band says "cash", return 0.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    lev = pd.Series(0.0, index=prices.index)
    in_market = False
    upper_mult = 1.0 + band_pct
    lower_mult = 1.0 - band_pct

    for i in range(len(prices)):
        if i < sma_window:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        if pd.isna(c) or pd.isna(sma_val):
            lev.iloc[i] = cc_lev.iloc[i] if in_market else 0.0
            continue
        if c > sma_val * upper_mult:
            in_market = True
        elif c < sma_val * lower_mult:
            in_market = False
        # else: within band → hold current state

        if in_market:
            cc_val = cc_lev.iloc[i]
            lev.iloc[i] = cc_val if not pd.isna(cc_val) and cc_val > 0.0 else 1.0
        else:
            lev.iloc[i] = 0.0
    return lev


# ---------------------------------------------------------------------------
# Strategy leverage computation
# ---------------------------------------------------------------------------


def compute_strategy_leverage(
    prices: pd.DataFrame,
    spec: dict,
) -> tuple[pd.Series, dict]:
    """Compute the leverage series and usage counts for a strategy spec."""
    sma_w = int(spec["sma_window"])
    band_p = float(spec["band_pct"])
    rsi_w = int(spec["rsi_window"])
    rsi_exit = float(spec["rsi_exit"])
    scale_mode = str(spec["scale_mode"])

    if scale_mode == "fixed":
        # B1 / B2: fixed leverage with band + RSI exit filter
        base_signal = sma_band_signal(prices, sma_w, band_p)  # 0 or 1
        base_lev = base_signal * float(spec["base_leverage"])  # 0 or L
        final_lev = rsi_exit_filter_on_series(base_lev, prices, rsi_exit, rsi_w)
    elif scale_mode == "rsi":
        # B3: RSI-scaled leverage gated by band + RSI exit filter
        rsi_zones = [(float(t), float(l)) for t, l in spec["rsi_zones"]]
        rsi_lev = rsi_leverage_signal(prices, rsi_zones, rsi_w)
        hybrid_lev = band_trend_hybrid(prices, sma_w, band_p, rsi_lev)
        final_lev = rsi_exit_filter_on_series(hybrid_lev, prices, rsi_exit, rsi_w)
    elif scale_mode == "vix":
        # B4: VIX-scaled leverage gated by band + RSI exit filter
        vix_zones = [(float(t), float(l)) for t, l in spec["vix_zones"]]
        vix_lev = vix_leverage_signal(prices, vix_zones)
        hybrid_lev = band_trend_hybrid(prices, sma_w, band_p, vix_lev)
        final_lev = rsi_exit_filter_on_series(hybrid_lev, prices, rsi_exit, rsi_w)
    else:
        raise ValueError(f"Unknown scale_mode: {scale_mode}")

    # Compute usage counts
    n = len(final_lev)
    pct_cash = float((final_lev <= 0.0).mean() * 100.0) if n > 0 else 0.0
    pct_1x = float(((final_lev > 0.0) & (final_lev < 1.5)).mean() * 100.0) if n > 0 else 0.0
    pct_2x = float(((final_lev >= 1.5) & (final_lev < 2.5)).mean() * 100.0) if n > 0 else 0.0
    pct_3x = float((final_lev >= 2.5).mean() * 100.0) if n > 0 else 0.0
    avg_lev = float(final_lev[final_lev > 0.0].mean()) if (final_lev > 0.0).any() else 0.0

    # Count trades (signal changes where leverage crosses 0)
    trades = int((final_lev.diff().fillna(0.0) != 0.0).sum())

    counts = {
        "pct_days_cash": pct_cash,
        "pct_days_1x": pct_1x,
        "pct_days_2x": pct_2x,
        "pct_days_3x": pct_3x,
        "avg_leverage": avg_lev,
        "total_trades": trades,
    }
    return final_lev, counts


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------


def download_spx_panel(years: int = YEARS) -> pd.DataFrame:
    """Download SPX total return, T-bill rate, and VIX from yfinance."""
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    raw = yf.download(
        [SPX_TICKER, TBILL_TICKER, VIX_TICKER],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No data returned from yfinance.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": SPX_TICKER})

    panel = pd.DataFrame(
        {
            "spx_close": closes[SPX_TICKER].astype(float),
            "tbill_rate": closes[TBILL_TICKER].astype(float) / 100.0,
            "vix": closes[VIX_TICKER].astype(float),
        }
    )
    panel = panel.sort_index().ffill().dropna(subset=["spx_close", "tbill_rate"])
    panel["vix"] = panel["vix"].ffill().fillna(15.0)
    panel["spx_close"] = clean_close_series(panel["spx_close"])
    if len(panel) < 260:
        raise ValueError(f"Not enough SPX rows: {len(panel)}")
    return panel


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


def make_engine() -> PortfolioEngine:
    """Standard engine: no DD protection, ETP mode, honest execution."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=ANNUAL_CASH_INFLOW_PCT,
        signal_delay_days=1,
    )


# ---------------------------------------------------------------------------
# Strategy runner
# ---------------------------------------------------------------------------


def run_strategy(
    prices: pd.DataFrame,
    spec: dict,
    *,
    etp_returns: pd.DataFrame | None = None,
) -> dict:
    """Run a strategy spec through PortfolioEngine and return stats + counts."""
    lev, counts = compute_strategy_leverage(prices, spec)
    run_kw: dict = {"name": str(spec["strategy"])}
    if etp_returns is not None:
        run_kw["etp_returns"] = etp_returns
    else:
        run_kw["etp_bundle"] = SPX_ETP
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": spec["strategy"],
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats.get("sortino"),
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "win_rate": stats.get("win_rate"),
        "profit_factor": stats.get("profit_factor"),
        "beta": stats.get("beta"),
        "alpha": stats.get("alpha"),
        **counts,
    }


def buy_hold_row(
    prices: pd.DataFrame,
    leverage: float,
    label: str,
    etp_returns: pd.DataFrame | None = None,
) -> dict:
    """Run a buy-and-hold strategy at fixed leverage."""
    lev = pd.Series(float(leverage), index=prices.index)
    run_kw: dict = {"name": label}
    if leverage > 1.0 and etp_returns is not None:
        run_kw["etp_returns"] = etp_returns
    elif leverage > 1.0:
        run_kw["etp_bundle"] = SPX_ETP
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    n = len(prices)
    return {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats.get("sortino"),
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "win_rate": stats.get("win_rate"),
        "profit_factor": stats.get("profit_factor"),
        "beta": stats.get("beta"),
        "alpha": stats.get("alpha"),
        "pct_days_cash": 0.0 if leverage > 0 else 100.0,
        "pct_days_1x": 100.0 if 0 < leverage < 1.5 else 0.0,
        "pct_days_2x": 100.0 if 1.5 <= leverage < 2.5 else 0.0,
        "pct_days_3x": 100.0 if leverage >= 2.5 else 0.0,
        "avg_leverage": float(leverage) if leverage > 0 else 0.0,
        "total_trades": 0,
    }


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


def monte_carlo(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    spec: dict = DEFAULT_SPEC,
) -> tuple[pd.DataFrame, dict]:
    """Run block-bootstrap Monte Carlo for a strategy spec."""
    rows: list[dict] = []
    paths = bootstrap_etp_paths(
        prices,
        etp_panel,
        n_sims=N_SIMS,
        horizon_days=HORIZON_DAYS,
        block_days=BLOCK_DAYS,
        seed=SEED,
    )
    for sim, (path, path_etp) in enumerate(paths):
        if sim % 25 == 0:
            print(f"  Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        row = run_strategy(path, spec, etp_returns=path_etp)
        row["simulation"] = sim
        rows.append(row)
    df = pd.DataFrame(rows)

    cagr = df["cagr"].dropna()
    max_dd = df["max_drawdown"].dropna()
    end_val = df["end_$"].dropna()

    summary = {
        "strategy": spec["strategy"],
        "paths": N_SIMS,
        "block_size_days": BLOCK_DAYS,
        "horizon_years": HORIZON_DAYS / 252.0,
        "seed": SEED,
        "median_cagr": float(cagr.median()) if len(cagr) else None,
        "cagr_ci_95": [
            float(cagr.quantile(0.025)) if len(cagr) else None,
            float(cagr.quantile(0.975)) if len(cagr) else None,
        ],
        "median_max_dd": float(max_dd.median()) if len(max_dd) else None,
        "max_dd_ci_95": [
            float(max_dd.quantile(0.025)) if len(max_dd) else None,
            float(max_dd.quantile(0.975)) if len(max_dd) else None,
        ],
        "prob_dd_exceeds_35pct": float((max_dd <= -0.35).mean()) if len(max_dd) else None,
        "prob_dd_exceeds_50pct": float((max_dd <= -0.50).mean()) if len(max_dd) else None,
        "prob_dd_exceeds_70pct": float((max_dd <= -0.70).mean()) if len(max_dd) else None,
        "prob_positive_cagr": float((cagr > 0).mean()) if len(cagr) else None,
        "prob_cagr_exceeds_10pct": float((cagr > 0.10).mean()) if len(cagr) else None,
        "prob_cagr_exceeds_20pct": float((cagr > 0.20).mean()) if len(cagr) else None,
        "median_sharpe": float(df["sharpe"].median()) if "sharpe" in df.columns else None,
        "median_end_$": float(end_val.median()) if len(end_val) else None,
        "prob_end_below_start": float((end_val < INITIAL_CAPITAL).mean()) if len(end_val) else None,
    }
    return df, summary


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def pct(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x) * 100:.2f}%"


def money(x: float | None) -> str | None:
    if x is None:
        return None
    return f"${float(x):,.0f}"


def fmt3(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x):.3f}"


def fmt2(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x):.2f}"


# ---------------------------------------------------------------------------
# Signal history builder
# ---------------------------------------------------------------------------


def build_signal_history(
    prices: pd.DataFrame,
    spec: dict,
) -> list[dict]:
    """Build daily signal history for the Signal page table and charts.

    One entry per trading day with: date, signal, leverage, spx_close,
    sma200, rsi14, action.
    """
    close = prices["spx_close"]
    sma_w = int(spec["sma_window"])
    rsi_w = int(spec["rsi_window"])
    band_p = float(spec["band_pct"])
    rsi_exit = float(spec["rsi_exit"])

    s = sma(close, sma_w)
    r = rsi(close, rsi_w)

    # Compute the B1 signal for action tracking
    base_signal = sma_band_signal(prices, sma_w, band_p)
    base_lev = base_signal * float(spec["base_leverage"])
    final_lev = rsi_exit_filter_on_series(base_lev, prices, rsi_exit, rsi_w)

    upper_mult = 1.0 + band_p
    lower_mult = 1.0 - band_p

    history: list[dict] = []
    prev_lev = 0.0
    prev_action = "start"

    for i in range(len(prices)):
        dt = prices.index[i]
        c = float(close.iloc[i]) if not pd.isna(close.iloc[i]) else None
        sma_val = float(s.iloc[i]) if not pd.isna(s.iloc[i]) else None
        rsi_val = float(r.iloc[i]) if not pd.isna(r.iloc[i]) else None
        lev_val = float(final_lev.iloc[i]) if not pd.isna(final_lev.iloc[i]) else 0.0

        # Determine signal label
        if lev_val <= 0.0:
            signal_label = "cash"
        else:
            signal_label = "long"

        # Determine action
        if i == 0:
            action = "start"
        elif prev_lev <= 0.0 and lev_val > 0.0:
            # Check if RSI exit was blocking
            bs = float(base_lev.iloc[i]) if not pd.isna(base_lev.iloc[i]) else 0.0
            if bs <= 0.0 and lev_val > 0.0:
                action = "rsi_exit_blocked"
            else:
                action = "enter_long"
        elif prev_lev > 0.0 and lev_val <= 0.0:
            action = "exit_to_cash"
        elif prev_lev > 0.0 and lev_val > 0.0 and abs(lev_val - prev_lev) > 0.01:
            action = "leverage_change"
        else:
            action = "hold"

        history.append({
            "date": dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10],
            "signal": signal_label,
            "leverage": round(lev_val, 1),
            "spx_close": round(c, 2) if c is not None else None,
            "sma200": round(sma_val, 2) if sma_val is not None else None,
            "rsi14": round(rsi_val, 2) if rsi_val is not None else None,
            "action": action,
        })
        prev_lev = lev_val

    return history


def build_price_sma_data(prices: pd.DataFrame, spec: dict) -> dict:
    """Build price + SMA200 + band data for the price chart."""
    close = prices["spx_close"]
    sma_w = int(spec["sma_window"])
    band_p = float(spec["band_pct"])

    s = sma(close, sma_w)
    upper_mult = 1.0 + band_p
    lower_mult = 1.0 - band_p

    dates: list[str] = []
    spx_close_list: list[float | None] = []
    sma200_list: list[float | None] = []
    upper_band_list: list[float | None] = []
    lower_band_list: list[float | None] = []

    for i in range(len(prices)):
        dt = prices.index[i]
        dates.append(dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10])
        c = float(close.iloc[i]) if not pd.isna(close.iloc[i]) else None
        sma_val = float(s.iloc[i]) if not pd.isna(s.iloc[i]) else None
        spx_close_list.append(round(c, 2) if c is not None else None)
        sma200_list.append(round(sma_val, 2) if sma_val is not None else None)
        upper_band_list.append(round(sma_val * upper_mult, 2) if sma_val is not None else None)
        lower_band_list.append(round(sma_val * lower_mult, 2) if sma_val is not None else None)

    return {
        "dates": dates,
        "spx_close": spx_close_list,
        "sma200": sma200_list,
        "sma200_upper_band": upper_band_list,
        "sma200_lower_band": lower_band_list,
    }


def build_equity_curve(
    prices: pd.DataFrame,
    default_lev: pd.Series,
    etp_panel: pd.DataFrame,
) -> dict:
    """Build daily equity curves for strategy, B&H 1x, and B&H 3x."""
    # Strategy equity
    strat_result = make_engine().run(
        prices, default_lev,
        name="B1",
        etp_returns=etp_panel,
    )
    strat_eq = strat_result.equity

    # B&H 1x
    bh1_lev = pd.Series(1.0, index=prices.index)
    bh1_result = make_engine().run(prices, bh1_lev, name="B&H 1x")
    bh1_eq = bh1_result.equity

    # B&H 3x
    bh3_lev = pd.Series(3.0, index=prices.index)
    bh3_result = make_engine().run(
        prices, bh3_lev,
        name="B&H 3x",
        etp_returns=etp_panel,
    )
    bh3_eq = bh3_result.equity

    dates: list[str] = []
    strat_list: list[float] = []
    bh1_list: list[float] = []
    bh3_list: list[float] = []

    for i in range(len(prices)):
        dt = prices.index[i]
        dates.append(dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10])
        strat_list.append(round(float(strat_eq.iloc[i]), 2) if i < len(strat_eq) and not pd.isna(strat_eq.iloc[i]) else None)
        bh1_list.append(round(float(bh1_eq.iloc[i]), 2) if i < len(bh1_eq) and not pd.isna(bh1_eq.iloc[i]) else None)
        bh3_list.append(round(float(bh3_eq.iloc[i]), 2) if i < len(bh3_eq) and not pd.isna(bh3_eq.iloc[i]) else None)

    return {
        "dates": dates,
        "strategy_equity": strat_list,
        "buy_hold_1x_equity": bh1_list,
        "buy_hold_3x_equity": bh3_list,
    }


# ---------------------------------------------------------------------------
# Site data payload builder
# ---------------------------------------------------------------------------


def build_site_payload(
    prices: pd.DataFrame,
    comparison: list[dict],
    default_row: dict,
    mc_summary: dict,
    etp_panel: pd.DataFrame,
    signal_history: list[dict],
    price_sma_data: dict,
    equity_curve: dict,
) -> dict:
    """Assemble the full site_data.json payload."""
    bh1 = next(r for r in comparison if r["strategy"] == "Buy & Hold SPY 1x")
    bh2 = next(r for r in comparison if r["strategy"] == "Buy & Hold SSO 2x")
    bh3 = next(r for r in comparison if r["strategy"] == "Buy & Hold UPRO 3x")

    # Try to load original guarded from existing site data
    original_guarded = None
    guarded_json_path = ROOT / "spx_guarded_site_data.json"
    if guarded_json_path.exists():
        try:
            guarded_data = json.loads(guarded_json_path.read_text(encoding="utf-8"))
            original_guarded = guarded_data.get("original_guarded")
        except Exception:
            pass

    return {
        "generated": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_start": prices.index[0].date().isoformat(),
        "data_end": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "default_backtest": {
            **default_row,
            "cagr_pct": pct(default_row["cagr"]),
            "max_drawdown_pct": pct(default_row["max_drawdown"]),
            "ann_volatility_pct": pct(default_row["ann_volatility"]),
            "sharpe_fmt": fmt3(default_row["sharpe"]),
            "sortino_fmt": fmt3(default_row.get("sortino")),
            "end_value_fmt": money(default_row["end_$"]),
            "calmar_fmt": fmt2(default_row.get("calmar")),
            "win_rate_pct": pct(default_row.get("win_rate")),
            "profit_factor_fmt": fmt2(default_row.get("profit_factor")),
            "beta_fmt": fmt2(default_row.get("beta")),
            "alpha_pct": pct(default_row.get("alpha")),
        },
        "comparison_table": [
            {
                **row,
                "cagr_pct": pct(row["cagr"]),
                "ann_volatility_pct": pct(row.get("ann_volatility")),
                "max_drawdown_pct": pct(row["max_drawdown"]),
                "sharpe_fmt": fmt3(row.get("sharpe")),
                "sortino_fmt": fmt3(row.get("sortino")),
                "end_value_fmt": money(row.get("end_$")),
                "calmar_fmt": fmt2(row.get("calmar")),
                "win_rate_pct": pct(row.get("win_rate")),
                "profit_factor_fmt": fmt2(row.get("profit_factor")),
                "beta_fmt": fmt2(row.get("beta")),
                "alpha_pct": pct(row.get("alpha")),
                "cash_pct": pct(row.get("pct_days_cash", 0.0) / 100.0),
                "avg_leverage_fmt": fmt2(row.get("avg_leverage")),
            }
            for row in comparison
        ],
        "buy_and_hold_1x": {
            **bh1,
            "cagr_pct": pct(bh1["cagr"]),
            "max_drawdown_pct": pct(bh1["max_drawdown"]),
            "ann_volatility_pct": pct(bh1["ann_volatility"]),
            "sharpe_fmt": fmt3(bh1["sharpe"]),
            "end_value_fmt": money(bh1["end_$"]),
        },
        "buy_and_hold_2x": {
            **bh2,
            "cagr_pct": pct(bh2["cagr"]),
            "max_drawdown_pct": pct(bh2["max_drawdown"]),
            "ann_volatility_pct": pct(bh2["ann_volatility"]),
            "sharpe_fmt": fmt3(bh2["sharpe"]),
            "end_value_fmt": money(bh2["end_$"]),
        },
        "buy_and_hold_3x": {
            **bh3,
            "cagr_pct": pct(bh3["cagr"]),
            "max_drawdown_pct": pct(bh3["max_drawdown"]),
            "ann_volatility_pct": pct(bh3["ann_volatility"]),
            "sharpe_fmt": fmt3(bh3["sharpe"]),
            "end_value_fmt": money(bh3["end_$"]),
        },
        "original_guarded": original_guarded,
        "monte_carlo": {
            **mc_summary,
            "median_cagr_pct": pct(mc_summary.get("median_cagr")),
            "cagr_ci_95_pct": [
                pct(mc_summary.get("cagr_ci_95", [None, None])[0]),
                pct(mc_summary.get("cagr_ci_95", [None, None])[1]),
            ],
            "median_max_dd_pct": pct(mc_summary.get("median_max_dd")),
            "max_dd_ci_95_pct": [
                pct(mc_summary.get("max_dd_ci_95", [None, None])[0]),
                pct(mc_summary.get("max_dd_ci_95", [None, None])[1]),
            ],
            "median_sharpe_fmt": fmt3(mc_summary.get("median_sharpe")),
            "median_end_value_fmt": money(mc_summary.get("median_end_$")),
            "prob_dd_exceeds_35pct_fmt": pct(mc_summary.get("prob_dd_exceeds_35pct")),
            "prob_dd_exceeds_50pct_fmt": pct(mc_summary.get("prob_dd_exceeds_50pct")),
            "prob_dd_exceeds_70pct_fmt": pct(mc_summary.get("prob_dd_exceeds_70pct")),
            "prob_positive_cagr_fmt": pct(mc_summary.get("prob_positive_cagr")),
            "prob_cagr_exceeds_10pct_fmt": pct(mc_summary.get("prob_cagr_exceeds_10pct")),
            "prob_cagr_exceeds_20pct_fmt": pct(mc_summary.get("prob_cagr_exceeds_20pct")),
            "prob_end_below_start_fmt": pct(mc_summary.get("prob_end_below_start")),
            "method": MC_ETP_METHOD,
        },
        "price_sma_data": price_sma_data,
        "signal_history": signal_history,
        "equity_curve": equity_curve,
        "levered_pnl_model": (
            "Listed 2x/3x ETP daily returns (SPY/SSO/UPRO, same US calendar as the index; "
            "implement via UCITS XS2D.L 2x / 3USL.L 3x); "
            "VIX-linked synthetic daily-reset before ETP inception. "
            f"Monte Carlo: {MC_ETP_METHOD}"
        ),
        "etp_coverage": etp_coverage_summary(etp_panel),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading S&P 500, T-bill, and VIX data...", flush=True)
    prices = download_spx_panel()
    print(
        f"Loaded {len(prices)} sessions: "
        f"{prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    print("Building S&P ETP return panel (SPY/SSO/UPRO)...", flush=True)
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    export_etp_returns_json(etp_panel, SPX_ETP, ETP_JSON)
    print(f"  ETP coverage: {etp_coverage_summary(etp_panel)}", flush=True)

    # -----------------------------------------------------------------------
    # Run all 9 strategies
    # -----------------------------------------------------------------------
    print("\nRunning strategy backtests...", flush=True)

    # Benchmarks: Buy & Hold
    comparison: list[dict] = [
        buy_hold_row(prices, 1.0, "Buy & Hold SPY 1x", etp_panel),
        buy_hold_row(prices, 2.0, "Buy & Hold SSO 2x", etp_panel),
        buy_hold_row(prices, 3.0, "Buy & Hold UPRO 3x", etp_panel),
    ]

    # Benchmarks: Plain SMA200 band (no RSI filter)
    for lev_val, label in [(3.0, "SMA200 ±3% Band 3x"), (2.0, "SMA200 ±3% Band 2x")]:
        base_signal = sma_band_signal(prices, 200, 0.03)
        plain_lev = base_signal * lev_val
        result = make_engine().run(
            prices, plain_lev,
            name=label,
            etp_returns=etp_panel,
        )
        stats = comprehensive_stats(result.equity, result.daily_returns)
        n = len(prices)
        comparison.append({
            "strategy": label,
            "cagr": stats["cagr"],
            "ann_volatility": stats["volatility"],
            "sharpe": stats["sharpe"],
            "sortino": stats.get("sortino"),
            "max_drawdown": stats["max_drawdown"],
            "calmar": stats.get("calmar"),
            "end_$": float(result.equity.iloc[-1]),
            "rebalances": result.rebalance_count,
            "trading_costs_total": result.trading_costs_total,
            "funding_costs_total": result.funding_costs_total,
            "win_rate": stats.get("win_rate"),
            "profit_factor": stats.get("profit_factor"),
            "beta": stats.get("beta"),
            "alpha": stats.get("alpha"),
            "pct_days_cash": float((plain_lev <= 0.0).mean() * 100.0),
            "pct_days_1x": 0.0,
            "pct_days_2x": 100.0 if lev_val == 2.0 else 0.0,
            "pct_days_3x": 100.0 if lev_val == 3.0 else 0.0,
            "avg_leverage": float((plain_lev[plain_lev > 0.0].mean())) if (plain_lev > 0.0).any() else 0.0,
            "total_trades": int((plain_lev.diff().fillna(0.0) != 0.0).sum()),
        })

    # Best strategies: B1, B2, B3, B4
    for spec in [B1_SPEC, B2_SPEC, B3_SPEC, B4_SPEC]:
        row = run_strategy(prices, spec, etp_returns=etp_panel)
        comparison.append(row)
        print(f"  {spec['strategy']}: CAGR={pct(row['cagr'])}, "
              f"Max DD={pct(row['max_drawdown'])}, "
              f"Sharpe={fmt3(row['sharpe'])}, "
              f"End={money(row['end_$'])}", flush=True)

    # Default row is B1
    default_row = next(
        r for r in comparison
        if r["strategy"] == DEFAULT_SPEC["strategy"]
    )

    # -----------------------------------------------------------------------
    # Write comparison CSV
    # -----------------------------------------------------------------------
    csv_path = OUTPUT_DIR / "spx_3x_levered_comparison.csv"
    csv_cols = [
        "strategy", "cagr", "ann_volatility", "sharpe", "sortino",
        "max_drawdown", "calmar", "end_$", "rebalances",
        "trading_costs_total", "funding_costs_total",
        "win_rate", "profit_factor", "beta", "alpha",
        "pct_days_cash", "pct_days_1x", "pct_days_2x", "pct_days_3x",
        "avg_leverage", "total_trades",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        for row in comparison:
            writer.writerow({k: row.get(k) for k in csv_cols})
    print(f"\nWrote comparison CSV: {csv_path}", flush=True)

    # -----------------------------------------------------------------------
    # Build signal history, price/SMA data, and equity curve
    # -----------------------------------------------------------------------
    print("\nBuilding signal history...", flush=True)
    signal_history = build_signal_history(prices, DEFAULT_SPEC)
    print(f"  {len(signal_history)} daily entries", flush=True)

    print("Building price/SMA data...", flush=True)
    price_sma_data = build_price_sma_data(prices, DEFAULT_SPEC)

    print("Building equity curves...", flush=True)
    default_lev, _ = compute_strategy_leverage(prices, DEFAULT_SPEC)
    equity_curve = build_equity_curve(prices, default_lev, etp_panel)

    # -----------------------------------------------------------------------
    # Monte Carlo
    # -----------------------------------------------------------------------
    print("\nRunning Monte Carlo (200 paths × 10yr, 21-day blocks)...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices, etp_panel, DEFAULT_SPEC)
    mc_paths.to_csv(
        OUTPUT_DIR / "spx_3x_levered_monte_carlo_paths.csv",
        index=False,
    )
    print(
        f"  Median CAGR: {pct(mc_summary.get('median_cagr'))}, "
        f"Median Max DD: {pct(mc_summary.get('median_max_dd'))}",
        flush=True,
    )

    # -----------------------------------------------------------------------
    # Build and write site data JSON
    # -----------------------------------------------------------------------
    print("\nBuilding site data payload...", flush=True)
    payload = build_site_payload(
        prices, comparison, default_row, mc_summary, etp_panel,
        signal_history, price_sma_data, equity_curve,
    )

    # Write to both locations
    site_json_str = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    SITE_DATA_JSON.write_text(site_json_str, encoding="utf-8")
    (OUTPUT_DIR / "spx_3x_levered_site_data.json").write_text(
        site_json_str, encoding="utf-8"
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    bh1_row = comparison[0]
    print("\n=== S&P 500 3x Levered (ETP-based) ===", flush=True)
    print(
        f"Default (B1): CAGR={pct(default_row['cagr'])}, "
        f"Max DD={pct(default_row['max_drawdown'])}, "
        f"Sharpe={fmt3(default_row['sharpe'])}, "
        f"Sortino={fmt3(default_row.get('sortino'))}",
        flush=True,
    )
    print(
        f"End value: {money(default_row['end_$'])}  "
        f"vs B&H 1x CAGR={pct(bh1_row['cagr'])} / "
        f"DD={pct(bh1_row['max_drawdown'])}",
        flush=True,
    )
    print(
        f"\nMonte Carlo median CAGR: {pct(mc_summary.get('median_cagr'))}, "
        f"median max DD: {pct(mc_summary.get('median_max_dd'))}",
        flush=True,
    )
    print(
        f"P(DD < -35%): {pct(mc_summary.get('prob_dd_exceeds_35pct'))}, "
        f"P(DD < -50%): {pct(mc_summary.get('prob_dd_exceeds_50pct'))}",
        flush=True,
    )
    print(f"\nWrote {SITE_DATA_JSON.name} and {ETP_JSON.name}", flush=True)
    print(f"Wrote {csv_path.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
