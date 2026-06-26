"""Counter-cyclical leverage scaling sweep.

Core concept: increase leverage when the market has fallen significantly and
appears poised to turn (fear/oversold), reduce leverage when the market appears
hot/extended (greed/overbought). This is mean-reversion with dynamic leverage.

All signal logic is self-contained; no existing files are modified.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from core.data_manager import load_backtest_data
from core.engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    ANNUAL_CASH_INFLOW_PCT,
    PortfolioEngine,
)
from core.etp_leverage import SPX_ETP, build_etp_return_panel
from core.indicators import sma, rsi, bollinger_bands, spx_drawdown_from_peak
from core.metrics import comprehensive_stats

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "spx_counter_cyclical"
OUTPUT_CSV = OUTPUT_DIR / "spx_counter_cyclical_results.csv"

# ---------------------------------------------------------------------------
# Constants (matching existing sweeps)
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0
SIGNAL_DELAY_DAYS = 1


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

def make_engine() -> PortfolioEngine:
    """Standard engine: no DD protection, ETP mode, honest execution."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=SIGNAL_DELAY_DAYS,
    )


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SweepResult:
    strategy: str
    cagr: float
    ann_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    end_value: float
    trades: int
    pct_cash: float
    avg_leverage: float


# ---------------------------------------------------------------------------
# COUNTER-CYCLICAL SIGNAL FUNCTIONS
# ---------------------------------------------------------------------------

# --- RSI-Based Leverage Scaling ---

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
                lev.iloc[i] = leverage
                break
    return lev


# --- Drawdown-from-Peak Leverage Scaling ---

def dd_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
) -> pd.Series:
    """Return leverage (0-3) based on market drawdown from running peak.

    Tracks running peak of close price (not portfolio value).
    zones: list of (dd_threshold, leverage) sorted by threshold ascending.
    Example: [(0.10, 1), (0.20, 2), (1.00, 3)]
    Means: DD 0-10% → 1x, 10-20% → 2x, >20% → 3x.
    DD is expressed as positive magnitude (0.10 = 10% below peak).
    """
    close = prices["spx_close"]
    lev = pd.Series(0.0, index=prices.index)
    peak = 0.0

    for i in range(len(prices)):
        c = close.iloc[i]
        if pd.isna(c):
            continue
        if c > peak:
            peak = c
        if peak <= 0:
            continue
        dd = (peak - c) / peak  # positive magnitude
        for threshold, leverage in zones:
            if dd < threshold:
                lev.iloc[i] = leverage
                break
    return lev


# --- Bollinger Band Leverage Scaling ---

def bb_leverage_signal(
    prices: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
    zones: list[tuple[str, float]] | None = None,
) -> pd.Series:
    """Return leverage based on position within Bollinger Bands.

    zones: list of (position, leverage). Supported positions:
      "below_lower", "between", "above_upper".
    Default: below_lower → 3, between → 1, above_upper → 0.
    """
    if zones is None:
        zones = [("below_lower", 3.0), ("between", 1.0), ("above_upper", 0.0)]

    close = prices["spx_close"]
    bb_lower, bb_mid, bb_upper = bollinger_bands(close, window, num_std)
    lev = pd.Series(0.0, index=prices.index)

    zone_map = {pos: lev_val for pos, lev_val in zones}

    for i in range(len(prices)):
        c = close.iloc[i]
        low = bb_lower.iloc[i]
        up = bb_upper.iloc[i]
        if pd.isna(c) or pd.isna(low) or pd.isna(up):
            continue
        if c < low:
            lev.iloc[i] = zone_map.get("below_lower", 1.0)
        elif c > up:
            lev.iloc[i] = zone_map.get("above_upper", 0.0)
        else:
            lev.iloc[i] = zone_map.get("between", 1.0)
    return lev


# --- VIX-Based Leverage Scaling ---

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
                lev.iloc[i] = leverage
                break
    return lev


# --- Distance-from-SMA Leverage Scaling ---

def sma_distance_leverage_signal(
    prices: pd.DataFrame,
    window: int = 200,
    zones: list[tuple[float, float]] | None = None,
) -> pd.Series:
    """Return leverage based on price/SMA ratio.

    zones: list of (ratio_threshold, leverage) sorted by threshold ascending.
    Example: [(0.90, 3), (0.95, 2), (1.05, 1), (float('inf'), 0)]
    Means: ratio < 0.90 → 3x, 0.90 ≤ ratio < 0.95 → 2x,
           0.95 ≤ ratio < 1.05 → 1x, ratio ≥ 1.05 → 0.
    """
    if zones is None:
        zones = [(0.90, 3.0), (0.95, 2.0), (1.05, 1.0), (float("inf"), 0.0)]

    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)

    for i in range(len(prices)):
        c = close.iloc[i]
        sma_val = s.iloc[i]
        if pd.isna(c) or pd.isna(sma_val) or sma_val <= 0:
            continue
        ratio = c / sma_val
        for threshold, leverage in zones:
            if ratio < threshold:
                lev.iloc[i] = leverage
                break
    return lev


# ---------------------------------------------------------------------------
# WRAPPER / HYBRID FUNCTIONS
# ---------------------------------------------------------------------------

# --- Trend Filter (SMA200) on a pre-computed leverage series ---

def trend_filter_on_series(
    cc_lev: pd.Series,
    prices: pd.DataFrame,
    sma_window: int = 200,
) -> pd.Series:
    """Only allow counter-cyclical leverage when price > SMA(sma_window).

    When price <= SMA, force cash (0). Also cash during SMA warmup.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    lev = cc_lev.copy()
    # Force cash when below SMA
    mask_below = close <= s
    lev[mask_below] = 0.0
    # Force cash during warmup
    lev.iloc[:sma_window] = 0.0
    return lev


# --- SMA Band Trend + Counter-Cyclical Hybrid ---

def band_trend_hybrid(
    prices: pd.DataFrame,
    sma_window: int,
    band_pct: float,
    cc_lev: pd.Series,
) -> pd.Series:
    """SMA band hysteresis for trend detection + counter-cyclical leverage scaling.

    When the band signal says "long" (price > SMA*(1+band) or within band and
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


# --- RSI Exit Filter on a pre-computed leverage series ---

def rsi_exit_filter_on_series(
    lev_series: pd.Series,
    prices: pd.DataFrame,
    rsi_threshold: float = 30.0,
    rsi_period: int = 14,
) -> pd.Series:
    """Don't exit if RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash (0) but RSI is below the threshold
    (deeply oversold), we stay at the previous non-zero leverage instead.
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
                # Update current leverage (may have changed, e.g. 2x → 3x)
                current_lev = bl
                result.iloc[i] = bl
    return result


# --- SMA Band Signal (reused for benchmarks) ---

def sma_band_signal(
    prices: pd.DataFrame, window: int, band_pct: float, leverage: float
) -> pd.Series:
    """SMA crossover with hysteresis band to reduce whipsaws."""
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
            current = leverage
        elif c < sma_val * lower_mult:
            current = 0.0
        lev.iloc[i] = current
    return lev


# --- RSI Exit Filter Wrapper for fixed-leverage band signals (reused for benchmarks) ---

def rsi_exit_filter_wrapper(
    base_signal_fn: Callable[[pd.DataFrame, int, float, float], pd.Series],
    prices: pd.DataFrame,
    window: int,
    band_pct: float,
    leverage: float,
    rsi_period: int = 14,
    rsi_threshold: float = 30.0,
) -> pd.Series:
    """Don't exit if RSI < threshold (oversold). Avoid selling into panic."""
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    base_lev = base_signal_fn(prices, window, band_pct, leverage)
    result = base_lev.copy()
    in_position = False

    for i in range(len(result)):
        bl = base_lev.iloc[i]
        rsi_val = r.iloc[i]
        if pd.isna(bl):
            continue
        if not in_position:
            if bl > 0.0:
                in_position = True
                result.iloc[i] = leverage
        else:
            if bl == 0.0:
                if pd.notna(rsi_val) and rsi_val < rsi_threshold:
                    result.iloc[i] = leverage
                else:
                    in_position = False
                    result.iloc[i] = 0.0
            else:
                result.iloc[i] = leverage
    return result


# ---------------------------------------------------------------------------
# Strategy catalogue builder
# ---------------------------------------------------------------------------

def build_catalogue(
    prices: pd.DataFrame,
) -> list[tuple[str, pd.Series]]:
    """Return list of (name, leverage_series) tuples for all strategies."""
    catalogue: list[tuple[str, pd.Series]] = []

    # ===================================================================
    # Benchmarks
    # ===================================================================
    catalogue.append(("Buy & Hold SPY 1x", pd.Series(1.0, index=prices.index)))
    catalogue.append(("Buy & Hold SSO 2x", pd.Series(2.0, index=prices.index)))
    catalogue.append(("Buy & Hold UPRO 3x", pd.Series(3.0, index=prices.index)))

    # SMA200 ±3% Band baselines
    catalogue.append(
        ("SMA200 ±3% Band 2x", sma_band_signal(prices, 200, 0.03, 2.0))
    )
    catalogue.append(
        ("SMA200 ±3% Band 3x", sma_band_signal(prices, 200, 0.03, 3.0))
    )

    # SMA200 ±3% Band + RSI>30 Exit baselines
    catalogue.append(
        (
            "SMA200 ±3% Band + RSI>30 Exit 2x",
            rsi_exit_filter_wrapper(sma_band_signal, prices, 200, 0.03, 2.0, rsi_threshold=30.0),
        )
    )
    catalogue.append(
        (
            "SMA200 ±3% Band + RSI>30 Exit 3x",
            rsi_exit_filter_wrapper(sma_band_signal, prices, 200, 0.03, 3.0, rsi_threshold=30.0),
        )
    )

    # ===================================================================
    # Category 1: RSI-Based Leverage Scaling
    # ===================================================================
    # RSI Leverage Scale 1-3x
    rsi_1_3x = rsi_leverage_signal(prices, [(30, 3.0), (50, 2.0), (70, 1.0), (100, 0.0)])
    catalogue.append(("RSI Leverage Scale 1-3x", rsi_1_3x))

    # RSI Leverage Scale 1-3x (aggressive)
    rsi_1_3x_agg = rsi_leverage_signal(prices, [(25, 3.0), (40, 2.0), (60, 1.0), (100, 0.0)])
    catalogue.append(("RSI Leverage Scale 1-3x (aggressive)", rsi_1_3x_agg))

    # RSI Leverage Scale 1-2x
    rsi_1_2x = rsi_leverage_signal(prices, [(30, 2.0), (50, 1.0), (100, 0.0)])
    catalogue.append(("RSI Leverage Scale 1-2x", rsi_1_2x))

    # RSI Leverage Scale 1-3x + SMA200 Trend Filter
    rsi_1_3x_tf = trend_filter_on_series(rsi_1_3x, prices, 200)
    catalogue.append(("RSI Leverage Scale 1-3x + SMA200 Filter", rsi_1_3x_tf))

    # ===================================================================
    # Category 2: Drawdown-from-Peak Leverage Scaling
    # ===================================================================
    # DD Scale 1-3x
    dd_1_3x = dd_leverage_signal(prices, [(0.10, 1.0), (0.20, 2.0), (1.00, 3.0)])
    catalogue.append(("DD Scale 1-3x", dd_1_3x))

    # DD Scale 1-3x (aggressive)
    dd_1_3x_agg = dd_leverage_signal(prices, [(0.05, 1.0), (0.15, 2.0), (1.00, 3.0)])
    catalogue.append(("DD Scale 1-3x (aggressive)", dd_1_3x_agg))

    # DD Scale 1-3x + SMA200 Trend Filter
    dd_1_3x_tf = trend_filter_on_series(dd_1_3x, prices, 200)
    catalogue.append(("DD Scale 1-3x + SMA200 Filter", dd_1_3x_tf))

    # DD Scale 1-3x + RSI>30 Exit
    dd_1_3x_rsi_exit = rsi_exit_filter_on_series(dd_1_3x, prices, rsi_threshold=30.0)
    catalogue.append(("DD Scale 1-3x + RSI>30 Exit", dd_1_3x_rsi_exit))

    # DD Scale 1-2x
    dd_1_2x = dd_leverage_signal(prices, [(0.10, 1.0), (1.00, 2.0)])
    catalogue.append(("DD Scale 1-2x", dd_1_2x))

    # ===================================================================
    # Category 3: Bollinger Band Leverage Scaling
    # ===================================================================
    # BB Leverage Scale 1-3x (20,2)
    bb_1_3x = bb_leverage_signal(prices, 20, 2.0, [("below_lower", 3.0), ("between", 1.0), ("above_upper", 0.0)])
    catalogue.append(("BB Leverage Scale 1-3x (20,2)", bb_1_3x))

    # BB Leverage Scale 1-3x (20,2) + SMA200 Filter
    bb_1_3x_tf = trend_filter_on_series(bb_1_3x, prices, 200)
    catalogue.append(("BB Leverage Scale 1-3x (20,2) + SMA200 Filter", bb_1_3x_tf))

    # BB Leverage Scale 1-2x (20,2)
    bb_1_2x = bb_leverage_signal(prices, 20, 2.0, [("below_lower", 2.0), ("between", 1.0), ("above_upper", 0.0)])
    catalogue.append(("BB Leverage Scale 1-2x (20,2)", bb_1_2x))

    # BB Leverage Scale 1-3x (20,1.5) — wider bands
    bb_1_3x_wide = bb_leverage_signal(prices, 20, 1.5, [("below_lower", 3.0), ("between", 1.0), ("above_upper", 0.0)])
    catalogue.append(("BB Leverage Scale 1-3x (20,1.5)", bb_1_3x_wide))

    # ===================================================================
    # Category 4: VIX-Based Leverage Scaling
    # ===================================================================
    # VIX Leverage Scale 1-3x
    vix_1_3x = vix_leverage_signal(prices, [(30, 3.0), (20, 2.0), (0, 1.0)])
    catalogue.append(("VIX Leverage Scale 1-3x", vix_1_3x))

    # VIX Leverage Scale 1-3x + SMA200 Filter
    vix_1_3x_tf = trend_filter_on_series(vix_1_3x, prices, 200)
    catalogue.append(("VIX Leverage Scale 1-3x + SMA200 Filter", vix_1_3x_tf))

    # VIX Leverage Scale 1-2x
    vix_1_2x = vix_leverage_signal(prices, [(25, 2.0), (0, 1.0)])
    catalogue.append(("VIX Leverage Scale 1-2x", vix_1_2x))

    # VIX Leverage Scale 1-3x (extreme)
    vix_1_3x_ext = vix_leverage_signal(prices, [(35, 3.0), (25, 2.0), (15, 1.0), (0, 0.0)])
    catalogue.append(("VIX Leverage Scale 1-3x (extreme)", vix_1_3x_ext))

    # ===================================================================
    # Category 5: Distance-from-SMA Leverage Scaling
    # ===================================================================
    # SMA200 Distance Scale 1-3x
    sma200_dist_1_3x = sma_distance_leverage_signal(
        prices, 200, [(0.90, 3.0), (0.95, 2.0), (1.05, 1.0), (float("inf"), 0.0)]
    )
    catalogue.append(("SMA200 Distance Scale 1-3x", sma200_dist_1_3x))

    # SMA200 Distance Scale 1-3x (tighter)
    sma200_dist_tight = sma_distance_leverage_signal(
        prices, 200, [(0.95, 3.0), (1.00, 2.0), (1.05, 1.0), (float("inf"), 0.0)]
    )
    catalogue.append(("SMA200 Distance Scale 1-3x (tighter)", sma200_dist_tight))

    # SMA50 Distance Scale 1-3x
    sma50_dist_1_3x = sma_distance_leverage_signal(
        prices, 50, [(0.90, 3.0), (0.95, 2.0), (1.05, 1.0), (float("inf"), 0.0)]
    )
    catalogue.append(("SMA50 Distance Scale 1-3x", sma50_dist_1_3x))

    # ===================================================================
    # Category 6: Combined Counter-Cyclical + Trend (Hybrid)
    # SMA200 ±3% Band as trend filter, then scale leverage counter-cyclically
    # ===================================================================
    # SMA200 ±3% Band + RSI Leverage Scale 1-3x
    cat6_rsi = band_trend_hybrid(prices, 200, 0.03, rsi_1_3x)
    catalogue.append(("SMA200 ±3% Band + RSI Leverage Scale 1-3x", cat6_rsi))

    # SMA200 ±3% Band + DD Leverage Scale 1-3x
    cat6_dd = band_trend_hybrid(prices, 200, 0.03, dd_1_3x)
    catalogue.append(("SMA200 ±3% Band + DD Leverage Scale 1-3x", cat6_dd))

    # SMA200 ±3% Band + BB Leverage Scale 1-3x
    cat6_bb = band_trend_hybrid(prices, 200, 0.03, bb_1_3x)
    catalogue.append(("SMA200 ±3% Band + BB Leverage Scale 1-3x", cat6_bb))

    # SMA200 ±3% Band + VIX Leverage Scale 1-3x
    cat6_vix = band_trend_hybrid(prices, 200, 0.03, vix_1_3x)
    catalogue.append(("SMA200 ±3% Band + VIX Leverage Scale 1-3x", cat6_vix))

    # SMA200 ±3% Band + SMA Distance Scale 1-3x
    cat6_smadist = band_trend_hybrid(prices, 200, 0.03, sma200_dist_1_3x)
    catalogue.append(("SMA200 ±3% Band + SMA Distance Scale 1-3x", cat6_smadist))

    # ===================================================================
    # Category 7: SMA200 ±3% Band + RSI>30 Exit + Counter-Cyclical Leverage
    # ===================================================================
    # SMA200 ±3% Band + RSI>30 Exit + RSI Leverage Scale 1-3x
    cat7_rsi = rsi_exit_filter_on_series(cat6_rsi, prices, rsi_threshold=30.0)
    catalogue.append(("SMA200 ±3% Band + RSI>30 Exit + RSI Leverage Scale 1-3x", cat7_rsi))

    # SMA200 ±3% Band + RSI>30 Exit + DD Leverage Scale 1-3x
    cat7_dd = rsi_exit_filter_on_series(cat6_dd, prices, rsi_threshold=30.0)
    catalogue.append(("SMA200 ±3% Band + RSI>30 Exit + DD Leverage Scale 1-3x", cat7_dd))

    # SMA200 ±3% Band + RSI>30 Exit + BB Leverage Scale 1-3x
    cat7_bb = rsi_exit_filter_on_series(cat6_bb, prices, rsi_threshold=30.0)
    catalogue.append(("SMA200 ±3% Band + RSI>30 Exit + BB Leverage Scale 1-3x", cat7_bb))

    # SMA200 ±3% Band + RSI>30 Exit + VIX Leverage Scale 1-3x
    cat7_vix = rsi_exit_filter_on_series(cat6_vix, prices, rsi_threshold=30.0)
    catalogue.append(("SMA200 ±3% Band + RSI>30 Exit + VIX Leverage Scale 1-3x", cat7_vix))

    return catalogue


# ---------------------------------------------------------------------------
# Run one strategy
# ---------------------------------------------------------------------------

def run_one(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    name: str,
    leverage: pd.Series,
) -> SweepResult:
    """Run a single strategy through the engine and return metrics."""
    engine = make_engine()

    result = engine.run(prices, leverage, name=name, etp_returns=etp_panel)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )

    # Count cash days and compute average leverage when invested
    lev_applied = result.leverage.astype(float).fillna(0.0)
    n = len(lev_applied)
    pct_cash = 100.0 * float((lev_applied <= 0.0).sum()) / n if n else 0.0

    invested = lev_applied[lev_applied > 0.0]
    avg_lev = float(invested.mean()) if len(invested) > 0 else 0.0

    return SweepResult(
        strategy=name,
        cagr=stats.get("cagr", float("nan")),
        ann_volatility=stats.get("volatility", float("nan")),
        sharpe=stats.get("sharpe", float("nan")),
        sortino=stats.get("sortino", float("nan")),
        max_drawdown=stats.get("max_drawdown", float("nan")),
        end_value=float(result.equity.iloc[-1]) if len(result.equity) else float("nan"),
        trades=result.rebalance_count,
        pct_cash=pct_cash,
        avg_leverage=avg_lev,
    )


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("S&P 500 Counter-Cyclical Leverage Scaling — SWEEP")
    print("=" * 72)

    # 1. Download data
    print("\n[1/4] Downloading market data (30y SPX + T-bills + VIX)...")
    prices = load_backtest_data(years=30)
    print(f"  -> {len(prices)} trading days, {prices.index[0].date()} to {prices.index[-1].date()}")

    # 2. Build ETP panel
    print("\n[2/4] Building ETP return panel (SPY/SSO/UPRO)...")
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    print(f"  -> {len(etp_panel.columns)} ETP columns, {len(etp_panel)} rows")

    # 3. Build catalogue
    print("\n[3/4] Building counter-cyclical strategy catalogue...")
    catalogue = build_catalogue(prices)
    print(f"  -> {len(catalogue)} strategies to test\n")

    # 4. Run all strategies
    print("[4/4] Running counter-cyclical sweep...\n")
    results: list[SweepResult] = []
    for i, (name, leverage) in enumerate(catalogue):
        pct = (i + 1) / len(catalogue) * 100
        print(f"  [{i+1:3d}/{len(catalogue)} {pct:5.1f}%] {name}...", end=" ", flush=True)
        try:
            r = run_one(prices, etp_panel, name, leverage)
            results.append(r)
            cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
            dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
            sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
            print(f"CAGR={cagr_s}  MaxDD={dd_s}  Sharpe={sh_s}  Trades={r.trades}  AvgLev={r.avg_leverage:.1f}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # 5. Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "strategy", "cagr", "ann_volatility", "sharpe", "sortino",
        "max_drawdown", "end_value", "trades", "pct_cash", "avg_leverage",
    ]
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow({k: getattr(r, k, None) for k in fieldnames})

    print(f"\n{'=' * 72}")
    print(f"Results written to: {OUTPUT_CSV}")
    print(f"{'=' * 72}\n")

    # -------------------------------------------------------------------
    # 6. Print formatted report
    # -------------------------------------------------------------------

    # --- Full results table ---
    print("=" * 130)
    print("COUNTER-CYCLICAL RESULTS — All Strategies Ranked by CAGR")
    print("=" * 130)
    sorted_by_cagr = sorted(
        results, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999, reverse=True
    )
    print(f"{'Rank':<5} {'Strategy':<58} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'%Cash':>7} {'AvgLev':>7} {'EndVal':>10} {'Trades':>7}")
    print("-" * 130)
    for rank, r in enumerate(sorted_by_cagr, 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        vol_s = f"{r.ann_volatility*100:.1f}%" if not pd.isna(r.ann_volatility) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        cash_s = f"{r.pct_cash:.1f}%" if not pd.isna(r.pct_cash) else "N/A"
        ev_s = f"${r.end_value:,.0f}" if not pd.isna(r.end_value) else "N/A"
        al_s = f"{r.avg_leverage:.1f}"
        print(f"{rank:<5} {r.strategy:<58} {cagr_s:>8} {dd_s:>8} {vol_s:>8} {sh_s:>7} {so_s:>7} {cash_s:>7} {al_s:>7} {ev_s:>10} {r.trades:>7}")

    # --- Comparison: Counter-Cyclical vs Baselines ---
    print(f"\n{'=' * 130}")
    print("COMPARISON: Counter-Cyclical vs Current Best Baselines")
    print(f"{'=' * 130}")

    baseline_names = [
        "SMA200 ±3% Band + RSI>30 Exit 3x",
        "SMA200 ±3% Band + RSI>30 Exit 2x",
        "SMA200 ±3% Band 3x",
        "SMA200 ±3% Band 2x",
    ]

    for bn in baseline_names:
        bl = next((r for r in results if r.strategy == bn), None)
        if bl is None:
            continue
        print(f"\n  Baseline: {bl.strategy}")
        print(f"    CAGR={bl.cagr*100:.2f}%  MaxDD={bl.max_drawdown*100:.1f}%  "
              f"AnnVol={bl.ann_volatility*100:.1f}%  Sharpe={bl.sharpe:.3f}  "
              f"Sortino={bl.sortino:.3f}  EndVal=${bl.end_value:,.0f}  Trades={bl.trades}")
        print(f"  {'-' * 110}")

        # Find counter-cyclical strategies that beat this baseline
        cc_strats = [
            r for r in results
            if r.strategy not in baseline_names
            and "Buy & Hold" not in r.strategy
        ]
        improvements = []
        for v in cc_strats:
            better_cagr = v.cagr > bl.cagr if not pd.isna(v.cagr) else False
            better_dd = v.max_drawdown > bl.max_drawdown if not pd.isna(v.max_drawdown) else False
            better_sharpe = v.sharpe > bl.sharpe if not pd.isna(v.sharpe) else False
            better_sortino = v.sortino > bl.sortino if not pd.isna(v.sortino) else False
            if better_cagr or better_dd or better_sharpe or better_sortino:
                improvements.append((v, better_cagr, better_dd, better_sharpe, better_sortino))

        if improvements:
            print(f"  Counter-cyclical improvements ({len(improvements)} found):")
            for v, bc, bd, bs, bso in sorted(improvements, key=lambda x: x[0].cagr, reverse=True):
                flags = []
                if bc: flags.append("CAGR+")
                if bd: flags.append("DD-")
                if bs: flags.append("Sharpe+")
                if bso: flags.append("Sortino+")
                print(f"    {v.strategy}: CAGR={v.cagr*100:.2f}% DD={v.max_drawdown*100:.1f}% "
                      f"Sharpe={v.sharpe:.3f} Sortino={v.sortino:.3f} "
                      f"AvgLev={v.avg_leverage:.1f} [{', '.join(flags)}]")
        else:
            print(f"  No counter-cyclical strategies beat this baseline.")

    # --- Benchmark reference ---
    print(f"\n{'=' * 130}")
    print("BENCHMARK REFERENCE")
    print(f"{'=' * 130}")
    for bench_name in ["Buy & Hold SPY 1x", "Buy & Hold SSO 2x", "Buy & Hold UPRO 3x"]:
        b = next((r for r in results if r.strategy == bench_name), None)
        if b:
            print(f"  {b.strategy}: CAGR={b.cagr*100:.2f}% DD={b.max_drawdown*100:.1f}% "
                  f"Sharpe={b.sharpe:.3f} Sortino={b.sortino:.3f} EndVal=${b.end_value:,.0f}")

    # --- Category Winners ---
    print(f"\n{'=' * 130}")
    print("WINNERS BY COUNTER-CYCLICAL CATEGORY")
    print(f"{'=' * 130}")

    def best_in_cat(subset, key_fn=lambda r: r.cagr, reverse=True):
        valid = [r for r in subset if not pd.isna(key_fn(r))]
        return max(valid, key=key_fn) if valid else None

    def fmt_res(r):
        if r is None:
            return "N/A"
        return (f"{r.strategy} | CAGR={r.cagr*100:.2f}% MaxDD={r.max_drawdown*100:.1f}% "
                f"Vol={r.ann_volatility*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f} "
                f"AvgLev={r.avg_leverage:.1f}")

    # Category 1: RSI-Based
    cat1 = [r for r in results if "RSI Leverage Scale" in r.strategy and "SMA200" not in r.strategy
            and "RSI>30" not in r.strategy]
    print(f"  Best RSI-Based:                  {fmt_res(best_in_cat(cat1))}")

    # Category 2: DD-Based
    cat2 = [r for r in results if "DD Scale" in r.strategy and "SMA200" not in r.strategy
            and "RSI>30" not in r.strategy]
    print(f"  Best DD-Based:                   {fmt_res(best_in_cat(cat2))}")

    # Category 3: BB-Based
    cat3 = [r for r in results if "BB Leverage Scale" in r.strategy and "SMA200" not in r.strategy]
    print(f"  Best BB-Based:                   {fmt_res(best_in_cat(cat3))}")

    # Category 4: VIX-Based
    cat4 = [r for r in results if "VIX Leverage Scale" in r.strategy and "SMA200" not in r.strategy]
    print(f"  Best VIX-Based:                  {fmt_res(best_in_cat(cat4))}")

    # Category 5: SMA Distance
    cat5 = [r for r in results if "Distance Scale" in r.strategy and "SMA200 ±3%" not in r.strategy]
    print(f"  Best SMA Distance:               {fmt_res(best_in_cat(cat5))}")

    # Category 6: Hybrid (Band + CC)
    cat6 = [r for r in results if "SMA200 ±3% Band +" in r.strategy
            and "RSI>30 Exit" not in r.strategy
            and "Scale" in r.strategy]
    print(f"  Best Hybrid (Band+CC):           {fmt_res(best_in_cat(cat6))}")

    # Category 7: Hybrid + RSI>30 Exit
    cat7 = [r for r in results if "RSI>30 Exit +" in r.strategy and "Scale" in r.strategy]
    print(f"  Best Hybrid+RSI>30 Exit:         {fmt_res(best_in_cat(cat7))}")

    # --- Composite Score Ranking ---
    print(f"\n{'=' * 130}")
    print("TOP 10 BY COMPOSITE SCORE (Sortino * (1+CAGR) / (1+|MaxDD|))")
    print(f"{'=' * 130}")
    scored = []
    for r in results:
        if pd.isna(r.sortino) or pd.isna(r.cagr) or pd.isna(r.max_drawdown):
            continue
        score = r.sortino * (1.0 + r.cagr) / (1.0 + abs(r.max_drawdown))
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    for rank, (score, r) in enumerate(scored[:10], 1):
        print(f"  #{rank}: {r.strategy} | Score={score:.3f} | CAGR={r.cagr*100:.2f}% "
              f"DD={r.max_drawdown*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f}")

    print(f"\n{'=' * 130}")
    print("Counter-cyclical sweep complete.")
    print(f"{'=' * 130}")


if __name__ == "__main__":
    main()
