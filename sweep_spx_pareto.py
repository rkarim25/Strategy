"""Pareto-optimization sweep: improve the 4 best baseline strategies on any
metric (CAGR, Max DD, Sharpe, Sortino, Ann Vol) without worsening any other,
while also lowering average leverage.

Tests 8 categories of filters and leverage-scaling mechanisms:
  1. Trend Quality Filters (SMA slope, SMA cross, ADX)
  2. Signal Persistence / Patience Filters (2-day, 3-day)
  3. Adaptive/Volatility-Scaled Bands (ATR, VIX)
  4. Dual-Band Asymmetric Entry/Exit
  5. Leverage Scaling by Trend Strength
  6. Combined Best Filters
  7. Refinements on B3/B4 (Counter-Cyclical Hybrids)
  8. RSI Threshold Tuning

All signal logic is self-contained; no existing files are modified.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    ANNUAL_CASH_INFLOW_PCT,
    PortfolioEngine,
)
from etp_leverage import SPX_ETP, build_etp_return_panel
from indicators import sma, rsi
from metrics import comprehensive_stats

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "spx_pareto"
OUTPUT_CSV = OUTPUT_DIR / "spx_pareto_results.csv"

# ---------------------------------------------------------------------------
# Constants (matching existing sweeps)
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0
SIGNAL_DELAY_DAYS = 1
TRADING_DAYS_PER_YEAR = 252

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


# ===================================================================
# ADX COMPUTATION (from scratch — Wilder's smoothing)
# ===================================================================


def compute_adx(prices: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute ADX using close-only approximation of True Range and DM.

    Since we only have close data:
      - TR  ≈ |close[t] - close[t-1]|
      - +DM ≈ max(close[t] - close[t-1], 0)  if close[t] > close[t-1] else 0
      - -DM ≈ max(close[t-1] - close[t], 0)  if close[t] < close[t-1] else 0

    Uses Wilder's smoothing (EMA with alpha = 1/window).
    Returns ADX series (0-100).
    """
    close = prices["spx_close"]
    n = len(close)

    # True Range approximation
    tr = pd.Series(0.0, index=prices.index)
    plus_dm = pd.Series(0.0, index=prices.index)
    minus_dm = pd.Series(0.0, index=prices.index)

    for i in range(1, n):
        c_prev = close.iloc[i - 1]
        c_curr = close.iloc[i]
        if pd.isna(c_prev) or pd.isna(c_curr):
            continue
        diff = c_curr - c_prev
        tr.iloc[i] = abs(diff)
        if diff > 0:
            plus_dm.iloc[i] = diff
        elif diff < 0:
            minus_dm.iloc[i] = -diff

    # Wilder's smoothing: first value is simple average, then EMA
    alpha = 1.0 / window

    tr_smooth = pd.Series(np.nan, index=prices.index)
    pdm_smooth = pd.Series(np.nan, index=prices.index)
    mdm_smooth = pd.Series(np.nan, index=prices.index)

    # Find first valid window
    first_valid = None
    for i in range(window, n):
        if tr.iloc[i] > 0 and not pd.isna(tr.iloc[i]):
            first_valid = i
            break

    if first_valid is None:
        return pd.Series(0.0, index=prices.index)

    # Initial values: sum over first 'window' valid bars
    init_tr = 0.0
    init_pdm = 0.0
    init_mdm = 0.0
    count = 0
    for i in range(1, first_valid + 1):
        if not pd.isna(tr.iloc[i]):
            init_tr += tr.iloc[i]
            init_pdm += plus_dm.iloc[i]
            init_mdm += minus_dm.iloc[i]
            count += 1
    if count == 0:
        return pd.Series(0.0, index=prices.index)

    tr_smooth.iloc[first_valid] = init_tr
    pdm_smooth.iloc[first_valid] = init_pdm
    mdm_smooth.iloc[first_valid] = init_mdm

    # Wilder's smoothing for remaining bars
    for i in range(first_valid + 1, n):
        prev_tr = tr_smooth.iloc[i - 1]
        prev_pdm = pdm_smooth.iloc[i - 1]
        prev_mdm = mdm_smooth.iloc[i - 1]
        if pd.isna(prev_tr):
            continue
        tr_smooth.iloc[i] = prev_tr - prev_tr / window + tr.iloc[i]
        pdm_smooth.iloc[i] = prev_pdm - prev_pdm / window + plus_dm.iloc[i]
        mdm_smooth.iloc[i] = prev_mdm - prev_mdm / window + minus_dm.iloc[i]

    # +DI, -DI, DX, ADX
    plus_di = pd.Series(np.nan, index=prices.index)
    minus_di = pd.Series(np.nan, index=prices.index)
    dx = pd.Series(np.nan, index=prices.index)
    adx = pd.Series(np.nan, index=prices.index)

    for i in range(first_valid, n):
        tr_val = tr_smooth.iloc[i]
        pdm_val = pdm_smooth.iloc[i]
        mdm_val = mdm_smooth.iloc[i]
        if pd.isna(tr_val) or tr_val == 0:
            continue
        plus_di.iloc[i] = 100.0 * pdm_val / tr_val
        minus_di.iloc[i] = 100.0 * mdm_val / tr_val
        di_sum = plus_di.iloc[i] + minus_di.iloc[i]
        if di_sum > 0:
            dx.iloc[i] = 100.0 * abs(plus_di.iloc[i] - minus_di.iloc[i]) / di_sum

    # ADX = Wilder's smoothed DX
    # First ADX value: average of first 'window' DX values after first_valid
    adx_start = first_valid + window - 1
    if adx_start >= n:
        adx_start = n - 1

    init_adx = 0.0
    adx_count = 0
    for i in range(first_valid, adx_start + 1):
        if not pd.isna(dx.iloc[i]):
            init_adx += dx.iloc[i]
            adx_count += 1
    if adx_count > 0:
        adx.iloc[adx_start] = init_adx

    for i in range(adx_start + 1, n):
        prev_adx = adx.iloc[i - 1]
        curr_dx = dx.iloc[i]
        if pd.isna(prev_adx):
            if not pd.isna(curr_dx):
                adx.iloc[i] = curr_dx
            continue
        if pd.isna(curr_dx):
            adx.iloc[i] = prev_adx
        else:
            adx.iloc[i] = prev_adx - prev_adx / window + curr_dx

    return adx.fillna(0.0)


# ===================================================================
# BASE SIGNAL FUNCTIONS (reused / adapted)
# ===================================================================


def sma_band_signal(
    prices: pd.DataFrame, window: int, band_pct: float, leverage: float
) -> pd.Series:
    """SMA crossover with hysteresis band to reduce whipsaws.

    Rules:
      - price > sma * (1 + band)  →  long at `leverage`
      - price < sma * (1 - band)  →  cash (0.0)
      - price within band          →  hold previous position
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
            current = leverage
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
    """Don't exit if RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash (0) but RSI is below the threshold
    (deeply oversold), we stay at the previous non-zero leverage instead.
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


def rsi_entry_filter_on_series(
    lev_series: pd.Series,
    prices: pd.DataFrame,
    rsi_threshold: float = 70.0,
    rsi_period: int = 14,
) -> pd.Series:
    """Block long entry if RSI > threshold (overbought). Wait for pullback."""
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    result = lev_series.copy()
    in_position = False

    for i in range(len(result)):
        bl = lev_series.iloc[i]
        rsi_val = r.iloc[i]

        if pd.isna(bl):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                if pd.notna(rsi_val) and rsi_val > rsi_threshold:
                    # Overbought — block entry, stay cash
                    result.iloc[i] = 0.0
                else:
                    in_position = True
                    result.iloc[i] = bl
            # else: stay cash
        else:
            if bl == 0.0:  # base signal says exit
                in_position = False
                result.iloc[i] = 0.0
            else:
                result.iloc[i] = bl
    return result


# ===================================================================
# NEW FILTER / WRAPPER FUNCTIONS
# ===================================================================


# --- Category 1: Trend Quality Filters ---


def sma_slope_filter_wrapper(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    sma_window: int = 200,
    lookback: int = 5,
    min_slope: float = 0.0,
) -> pd.Series:
    """Only allow long when SMA slope over `lookback` days exceeds `min_slope`
    (annualized). When condition fails, force cash (0.0).

    SMA slope = (SMA[t] - SMA[t-lookback]) / SMA[t-lookback] × (252/lookback)
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    result = base_lev.copy()
    warmup = sma_window + lookback

    for i in range(len(result)):
        if i < warmup:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            continue  # already cash
        sma_now = s.iloc[i]
        sma_past = s.iloc[i - lookback]
        if pd.isna(sma_now) or pd.isna(sma_past) or sma_past <= 0:
            result.iloc[i] = 0.0
            continue
        slope = (sma_now - sma_past) / sma_past * (TRADING_DAYS_PER_YEAR / lookback)
        if slope <= min_slope:
            result.iloc[i] = 0.0
    return result


def sma_cross_filter_wrapper(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    fast: int = 50,
    slow: int = 200,
) -> pd.Series:
    """Only allow long when SMA(fast) > SMA(slow) — golden cross territory."""
    close = prices["spx_close"]
    s_fast = sma(close, fast)
    s_slow = sma(close, slow)
    result = base_lev.copy()
    warmup = max(fast, slow)

    for i in range(len(result)):
        if i < warmup:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            continue
        if pd.isna(s_fast.iloc[i]) or pd.isna(s_slow.iloc[i]):
            result.iloc[i] = 0.0
            continue
        if s_fast.iloc[i] <= s_slow.iloc[i]:
            result.iloc[i] = 0.0
    return result


def adx_filter_wrapper(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    threshold: float = 20.0,
    adx_window: int = 14,
) -> pd.Series:
    """Only allow long when ADX > threshold (trending market, not choppy)."""
    adx_series = compute_adx(prices, adx_window)
    result = base_lev.copy()
    warmup = adx_window * 3  # ADX needs significant warmup

    for i in range(len(result)):
        if i < warmup:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            continue
        adx_val = adx_series.iloc[i]
        if pd.isna(adx_val) or adx_val <= threshold:
            result.iloc[i] = 0.0
    return result


# --- Category 2: Signal Persistence / Patience Filters ---


def persistence_filter_wrapper(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    days: int = 2,
) -> pd.Series:
    """Require the raw signal to persist for `days` consecutive days before
    the filtered signal changes. Uses a state machine.

    Tracks consecutive days above/below zero. Only flips filtered position
    when the counter reaches `days`.
    """
    result = base_lev.copy()
    n = len(result)

    # State machine
    filtered_pos = 0.0  # current filtered position (0=cash, >0=long)
    filtered_lev = 0.0  # the leverage level to use when long
    consecutive_above = 0
    consecutive_below = 0

    for i in range(n):
        bl = base_lev.iloc[i]
        if pd.isna(bl):
            result.iloc[i] = filtered_lev if filtered_pos > 0 else 0.0
            continue

        if bl > 0.0:
            consecutive_above += 1
            consecutive_below = 0
            if consecutive_above >= days and filtered_pos == 0.0:
                # Enter: signal persisted long enough
                filtered_pos = bl
                filtered_lev = bl
        else:
            consecutive_below += 1
            consecutive_above = 0
            if consecutive_below >= days and filtered_pos > 0.0:
                # Exit: cash signal persisted long enough
                filtered_pos = 0.0
                filtered_lev = 0.0

        result.iloc[i] = filtered_lev

    return result


# --- Category 3: Adaptive/Volatility-Scaled Bands ---


def _close_based_atr(close: pd.Series, window: int = 20) -> pd.Series:
    """Approximate ATR using absolute daily percentage changes smoothed with EMA."""
    daily_pct_change = close.pct_change().abs()
    avg_pct_range = daily_pct_change.ewm(span=window, min_periods=window, adjust=False).mean()
    atr_dollar = avg_pct_range * close
    return atr_dollar


def atr_band_signal(
    prices: pd.DataFrame,
    sma_window: int = 200,
    atr_window: int = 20,
    atr_multiple: float = 1.5,
    leverage: float = 3.0,
) -> pd.Series:
    """SMA band where band width = atr_multiple × ATR(atr_window) / SMA.

    Dynamic band: upper = SMA × (1 + atr_multiple × ATR/SMA),
                  lower = SMA × (1 - atr_multiple × ATR/SMA).
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    atr_series = _close_based_atr(close, atr_window)

    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    warmup = max(sma_window, atr_window)

    for i in range(len(prices)):
        if i < warmup:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        atr_val = atr_series.iloc[i]
        if pd.isna(c) or pd.isna(sma_val) or pd.isna(atr_val) or sma_val <= 0:
            lev.iloc[i] = current
            continue

        # Dynamic band: atr_multiple * ATR / SMA
        band_pct = atr_multiple * atr_val / sma_val
        band_pct = max(0.005, min(0.15, band_pct))

        upper_mult = 1.0 + band_pct
        lower_mult = 1.0 - band_pct

        if c > sma_val * upper_mult:
            current = leverage
        elif c < sma_val * lower_mult:
            current = 0.0
        # else: within band → hold current
        lev.iloc[i] = current

    return lev


def vix_scaled_band_signal(
    prices: pd.DataFrame,
    sma_window: int = 200,
    base_band: float = 0.03,
    vix_median: float = 20.0,
    leverage: float = 3.0,
) -> pd.Series:
    """SMA band where band width = base_band × (VIX / vix_median).

    When VIX is high, band widens → harder to whipsaw.
    When VIX is low, band tightens → more responsive.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    vix_series = prices["vix"].ffill().fillna(vix_median)

    lev = pd.Series(0.0, index=prices.index)
    current = 0.0

    for i in range(len(prices)):
        if i < sma_window:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        vix_val = vix_series.iloc[i]
        if pd.isna(c) or pd.isna(sma_val) or pd.isna(vix_val) or vix_median <= 0:
            lev.iloc[i] = current
            continue

        band_pct = base_band * (vix_val / vix_median)
        band_pct = max(0.005, min(0.15, band_pct))

        upper_mult = 1.0 + band_pct
        lower_mult = 1.0 - band_pct

        if c > sma_val * upper_mult:
            current = leverage
        elif c < sma_val * lower_mult:
            current = 0.0
        lev.iloc[i] = current

    return lev


# --- Category 4: Dual-Band Asymmetric Entry/Exit ---


def dual_band_signal(
    prices: pd.DataFrame,
    sma_window: int = 200,
    entry_band: float = 0.05,
    exit_band: float = 0.02,
    leverage: float = 3.0,
) -> pd.Series:
    """Asymmetric band: enter when price > SMA × (1+entry_band),
    exit when price < SMA × (1-exit_band). Within the dead zone, hold previous.

    Enter cautiously (wide band), exit quickly (tight band).
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    upper_mult = 1.0 + entry_band
    lower_mult = 1.0 - exit_band

    for i in range(len(prices)):
        if i < sma_window:
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
        # else: within dead zone → hold current
        lev.iloc[i] = current
    return lev


# --- Category 5: Leverage Scaling by Trend Strength ---


def slope_leverage_scale(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    sma_window: int = 200,
    lookback: int = 5,
) -> pd.Series:
    """Scale leverage 1-3 based on SMA slope when base signal says long.

    Slope > 10% ann → 3x, 0-10% → 2x, <0 → 1x.
    If base signal says cash, return 0.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    result = base_lev.copy()
    warmup = sma_window + lookback

    for i in range(len(result)):
        if i < warmup:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            result.iloc[i] = 0.0
            continue
        sma_now = s.iloc[i]
        sma_past = s.iloc[i - lookback]
        if pd.isna(sma_now) or pd.isna(sma_past) or sma_past <= 0:
            result.iloc[i] = 1.0
            continue
        slope = (sma_now - sma_past) / sma_past * (TRADING_DAYS_PER_YEAR / lookback)
        if slope > 0.10:
            result.iloc[i] = 3.0
        elif slope > 0.0:
            result.iloc[i] = 2.0
        else:
            result.iloc[i] = 1.0
    return result


def adx_leverage_scale(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    adx_window: int = 14,
) -> pd.Series:
    """Scale leverage 1-3 based on ADX when base signal says long.

    ADX > 25 → 3x, 20-25 → 2x, <20 → 1x.
    """
    adx_series = compute_adx(prices, adx_window)
    result = base_lev.copy()
    warmup = adx_window * 3

    for i in range(len(result)):
        if i < warmup:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            result.iloc[i] = 0.0
            continue
        adx_val = adx_series.iloc[i]
        if pd.isna(adx_val):
            result.iloc[i] = 1.0
        elif adx_val > 25.0:
            result.iloc[i] = 3.0
        elif adx_val > 20.0:
            result.iloc[i] = 2.0
        else:
            result.iloc[i] = 1.0
    return result


def mild_rsi_leverage_scale(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    rsi_window: int = 14,
) -> pd.Series:
    """Scale leverage 1-3 based on RSI zones when base signal says long.

    RSI 40-60 → 3x (steady trend), 60-70 or 30-40 → 2x, >70 or <30 → 1x.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_window)
    result = base_lev.copy()

    for i in range(len(result)):
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            result.iloc[i] = 0.0
            continue
        rsi_val = r.iloc[i]
        if pd.isna(rsi_val):
            result.iloc[i] = 1.0
        elif 40.0 <= rsi_val <= 60.0:
            result.iloc[i] = 3.0
        elif (60.0 < rsi_val <= 70.0) or (30.0 <= rsi_val < 40.0):
            result.iloc[i] = 2.0
        else:
            result.iloc[i] = 1.0
    return result


def distance_leverage_scale(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    sma_window: int = 200,
) -> pd.Series:
    """Scale leverage 1-3 based on price/SMA ratio when base signal says long.

    ratio 1.00-1.05 → 3x, 1.05-1.10 → 2x, >1.10 → 1x.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    result = base_lev.copy()

    for i in range(len(result)):
        if i < sma_window:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            result.iloc[i] = 0.0
            continue
        sma_val = s.iloc[i]
        c = close.iloc[i]
        if pd.isna(sma_val) or pd.isna(c) or sma_val <= 0:
            result.iloc[i] = 1.0
            continue
        ratio = c / sma_val
        if ratio <= 1.05:
            result.iloc[i] = 3.0
        elif ratio <= 1.10:
            result.iloc[i] = 2.0
        else:
            result.iloc[i] = 1.0
    return result


# ===================================================================
# COUNTER-CYCLICAL LEVERAGE SIGNALS (for B3/B4 refinements)
# ===================================================================


def rsi_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
    rsi_period: int = 14,
) -> pd.Series:
    """Return leverage (0-3) based on RSI zone.

    zones: list of (rsi_threshold, leverage) sorted by threshold ascending.
    Example: [(30, 3), (50, 2), (70, 1), (100, 0)]
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


def vix_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
) -> pd.Series:
    """Return leverage (0-3) based on VIX level.

    zones: list of (vix_threshold, leverage) sorted by threshold DESCENDING.
    Example: [(30, 3), (20, 2), (0, 1)]
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


def band_trend_hybrid(
    prices: pd.DataFrame,
    sma_window: int,
    band_pct: float,
    cc_lev: pd.Series,
) -> pd.Series:
    """SMA band hysteresis for trend detection + counter-cyclical leverage scaling.

    When the band signal says "long", use cc_lev to determine leverage (1-3x).
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


# ===================================================================
# Strategy catalogue builder
# ===================================================================


def build_catalogue(
    prices: pd.DataFrame,
) -> list[tuple[str, pd.Series]]:
    """Return list of (name, leverage_series) tuples for all Pareto strategies."""
    catalogue: list[tuple[str, pd.Series]] = []

    # ===================================================================
    # Benchmarks (re-run for consistency)
    # ===================================================================
    catalogue.append(("Buy & Hold SPY 1x", pd.Series(1.0, index=prices.index)))

    # Plain SMA200 ±3% Band (no RSI filter)
    catalogue.append(
        ("SMA200 ±3% Band 2x (plain)", sma_band_signal(prices, 200, 0.03, 2.0))
    )
    catalogue.append(
        ("SMA200 ±3% Band 3x (plain)", sma_band_signal(prices, 200, 0.03, 3.0))
    )

    # --- B1-B4 Baselines ---
    # B1: SMA200 ±3% Band + RSI>30 Exit 3x
    b1_base = sma_band_signal(prices, 200, 0.03, 3.0)
    b1 = rsi_exit_filter_on_series(b1_base, prices, rsi_threshold=30.0)
    catalogue.append(("B1: SMA200 ±3% Band + RSI>30 Exit 3x", b1))

    # B2: SMA200 ±3% Band + RSI>30 Exit 2x
    b2_base = sma_band_signal(prices, 200, 0.03, 2.0)
    b2 = rsi_exit_filter_on_series(b2_base, prices, rsi_threshold=30.0)
    catalogue.append(("B2: SMA200 ±3% Band + RSI>30 Exit 2x", b2))

    # B3: SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x
    rsi_1_3x = rsi_leverage_signal(prices, [(30, 3.0), (50, 2.0), (70, 1.0), (100, 0.0)])
    b3_hybrid = band_trend_hybrid(prices, 200, 0.03, rsi_1_3x)
    b3 = rsi_exit_filter_on_series(b3_hybrid, prices, rsi_threshold=30.0)
    catalogue.append(("B3: SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x", b3))

    # B4: SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x
    vix_1_3x = vix_leverage_signal(prices, [(30, 3.0), (20, 2.0), (0, 1.0)])
    b4_hybrid = band_trend_hybrid(prices, 200, 0.03, vix_1_3x)
    b4 = rsi_exit_filter_on_series(b4_hybrid, prices, rsi_threshold=30.0)
    catalogue.append(("B4: SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x", b4))

    # ===================================================================
    # Category 1: Trend Quality Filters (on B1/B2 base)
    # ===================================================================

    # --- SMA200 Slope > 0 ---
    # B1 + Slope>0
    cat1_slope_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.0)
    catalogue.append(("B1 + SMA200 Slope>0", cat1_slope_b1))
    # B2 + Slope>0
    cat1_slope_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.0)
    catalogue.append(("B2 + SMA200 Slope>0", cat1_slope_b2))

    # --- SMA200 Slope > 5% ann ---
    cat1_slope5_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.05)
    catalogue.append(("B1 + SMA200 Slope>5%", cat1_slope5_b1))
    cat1_slope5_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.05)
    catalogue.append(("B2 + SMA200 Slope>5%", cat1_slope5_b2))

    # --- SMA200 Slope > 10% ann ---
    cat1_slope10_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.10)
    catalogue.append(("B1 + SMA200 Slope>10%", cat1_slope10_b1))
    cat1_slope10_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.10)
    catalogue.append(("B2 + SMA200 Slope>10%", cat1_slope10_b2))

    # --- SMA50 > SMA200 (golden cross) ---
    cat1_cross_b1 = sma_cross_filter_wrapper(b1, prices, 50, 200)
    catalogue.append(("B1 + SMA50>SMA200", cat1_cross_b1))
    cat1_cross_b2 = sma_cross_filter_wrapper(b2, prices, 50, 200)
    catalogue.append(("B2 + SMA50>SMA200", cat1_cross_b2))

    # --- ADX > 20 ---
    cat1_adx20_b1 = adx_filter_wrapper(b1, prices, 20.0, 14)
    catalogue.append(("B1 + ADX>20", cat1_adx20_b1))
    cat1_adx20_b2 = adx_filter_wrapper(b2, prices, 20.0, 14)
    catalogue.append(("B2 + ADX>20", cat1_adx20_b2))

    # --- ADX > 25 ---
    cat1_adx25_b1 = adx_filter_wrapper(b1, prices, 25.0, 14)
    catalogue.append(("B1 + ADX>25", cat1_adx25_b1))
    cat1_adx25_b2 = adx_filter_wrapper(b2, prices, 25.0, 14)
    catalogue.append(("B2 + ADX>25", cat1_adx25_b2))

    # ===================================================================
    # Category 2: Signal Persistence / Patience Filters (on B1/B2 base)
    # ===================================================================

    # --- 2-Day Persistence ---
    cat2_p2_b1 = persistence_filter_wrapper(b1, prices, 2)
    catalogue.append(("B1 + 2-Day Persist", cat2_p2_b1))
    cat2_p2_b2 = persistence_filter_wrapper(b2, prices, 2)
    catalogue.append(("B2 + 2-Day Persist", cat2_p2_b2))

    # --- 3-Day Persistence ---
    cat2_p3_b1 = persistence_filter_wrapper(b1, prices, 3)
    catalogue.append(("B1 + 3-Day Persist", cat2_p3_b1))
    cat2_p3_b2 = persistence_filter_wrapper(b2, prices, 3)
    catalogue.append(("B2 + 3-Day Persist", cat2_p3_b2))

    # ===================================================================
    # Category 3: Adaptive/Volatility-Scaled Band (on B1/B2 base)
    # ===================================================================

    # --- ATR-Scaled Band ×1.0 ---
    cat3_atr10_3x = atr_band_signal(prices, 200, 20, 1.0, 3.0)
    cat3_atr10_3x_rsi = rsi_exit_filter_on_series(cat3_atr10_3x, prices, 30.0)
    catalogue.append(("SMA200 ATR×1.0 Band + RSI>30 Exit 3x", cat3_atr10_3x_rsi))
    cat3_atr10_2x = atr_band_signal(prices, 200, 20, 1.0, 2.0)
    cat3_atr10_2x_rsi = rsi_exit_filter_on_series(cat3_atr10_2x, prices, 30.0)
    catalogue.append(("SMA200 ATR×1.0 Band + RSI>30 Exit 2x", cat3_atr10_2x_rsi))

    # --- ATR-Scaled Band ×1.5 ---
    cat3_atr15_3x = atr_band_signal(prices, 200, 20, 1.5, 3.0)
    cat3_atr15_3x_rsi = rsi_exit_filter_on_series(cat3_atr15_3x, prices, 30.0)
    catalogue.append(("SMA200 ATR×1.5 Band + RSI>30 Exit 3x", cat3_atr15_3x_rsi))
    cat3_atr15_2x = atr_band_signal(prices, 200, 20, 1.5, 2.0)
    cat3_atr15_2x_rsi = rsi_exit_filter_on_series(cat3_atr15_2x, prices, 30.0)
    catalogue.append(("SMA200 ATR×1.5 Band + RSI>30 Exit 2x", cat3_atr15_2x_rsi))

    # --- ATR-Scaled Band ×2.0 ---
    cat3_atr20_3x = atr_band_signal(prices, 200, 20, 2.0, 3.0)
    cat3_atr20_3x_rsi = rsi_exit_filter_on_series(cat3_atr20_3x, prices, 30.0)
    catalogue.append(("SMA200 ATR×2.0 Band + RSI>30 Exit 3x", cat3_atr20_3x_rsi))
    cat3_atr20_2x = atr_band_signal(prices, 200, 20, 2.0, 2.0)
    cat3_atr20_2x_rsi = rsi_exit_filter_on_series(cat3_atr20_2x, prices, 30.0)
    catalogue.append(("SMA200 ATR×2.0 Band + RSI>30 Exit 2x", cat3_atr20_2x_rsi))

    # --- VIX-Scaled Band ---
    cat3_vix_3x = vix_scaled_band_signal(prices, 200, 0.03, 20.0, 3.0)
    cat3_vix_3x_rsi = rsi_exit_filter_on_series(cat3_vix_3x, prices, 30.0)
    catalogue.append(("SMA200 VIX-Scaled ±3% Band + RSI>30 Exit 3x", cat3_vix_3x_rsi))
    cat3_vix_2x = vix_scaled_band_signal(prices, 200, 0.03, 20.0, 2.0)
    cat3_vix_2x_rsi = rsi_exit_filter_on_series(cat3_vix_2x, prices, 30.0)
    catalogue.append(("SMA200 VIX-Scaled ±3% Band + RSI>30 Exit 2x", cat3_vix_2x_rsi))

    # ===================================================================
    # Category 4: Dual-Band Asymmetric Entry/Exit (on B1/B2 base)
    # ===================================================================

    # --- Entry ±5% / Exit ±2% ---
    cat4_e5x2_3x = dual_band_signal(prices, 200, 0.05, 0.02, 3.0)
    cat4_e5x2_3x_rsi = rsi_exit_filter_on_series(cat4_e5x2_3x, prices, 30.0)
    catalogue.append(("SMA200 Entry±5% Exit±2% + RSI>30 Exit 3x", cat4_e5x2_3x_rsi))
    cat4_e5x2_2x = dual_band_signal(prices, 200, 0.05, 0.02, 2.0)
    cat4_e5x2_2x_rsi = rsi_exit_filter_on_series(cat4_e5x2_2x, prices, 30.0)
    catalogue.append(("SMA200 Entry±5% Exit±2% + RSI>30 Exit 2x", cat4_e5x2_2x_rsi))

    # --- Entry ±4% / Exit ±2% ---
    cat4_e4x2_3x = dual_band_signal(prices, 200, 0.04, 0.02, 3.0)
    cat4_e4x2_3x_rsi = rsi_exit_filter_on_series(cat4_e4x2_3x, prices, 30.0)
    catalogue.append(("SMA200 Entry±4% Exit±2% + RSI>30 Exit 3x", cat4_e4x2_3x_rsi))
    cat4_e4x2_2x = dual_band_signal(prices, 200, 0.04, 0.02, 2.0)
    cat4_e4x2_2x_rsi = rsi_exit_filter_on_series(cat4_e4x2_2x, prices, 30.0)
    catalogue.append(("SMA200 Entry±4% Exit±2% + RSI>30 Exit 2x", cat4_e4x2_2x_rsi))

    # --- Entry ±3% / Exit ±1.5% ---
    cat4_e3x15_3x = dual_band_signal(prices, 200, 0.03, 0.015, 3.0)
    cat4_e3x15_3x_rsi = rsi_exit_filter_on_series(cat4_e3x15_3x, prices, 30.0)
    catalogue.append(("SMA200 Entry±3% Exit±1.5% + RSI>30 Exit 3x", cat4_e3x15_3x_rsi))
    cat4_e3x15_2x = dual_band_signal(prices, 200, 0.03, 0.015, 2.0)
    cat4_e3x15_2x_rsi = rsi_exit_filter_on_series(cat4_e3x15_2x, prices, 30.0)
    catalogue.append(("SMA200 Entry±3% Exit±1.5% + RSI>30 Exit 2x", cat4_e3x15_2x_rsi))

    # ===================================================================
    # Category 5: Leverage Scaling by Trend Strength (on B1/B2 base)
    # ===================================================================

    # --- SMA Slope Leverage Scale ---
    # B1 base (3x band signal) → scale by slope
    cat5_slope_scale_b1 = slope_leverage_scale(b1_base, prices, 200, 5)
    cat5_slope_scale_b1_rsi = rsi_exit_filter_on_series(cat5_slope_scale_b1, prices, 30.0)
    catalogue.append(("B1 + Slope Leverage Scale (max 3x)", cat5_slope_scale_b1_rsi))
    # B2 base (2x band signal) → scale by slope (max 2x effectively, but slope can give 1-3)
    cat5_slope_scale_b2 = slope_leverage_scale(b2_base, prices, 200, 5)
    cat5_slope_scale_b2_rsi = rsi_exit_filter_on_series(cat5_slope_scale_b2, prices, 30.0)
    catalogue.append(("B2 + Slope Leverage Scale (max 3x)", cat5_slope_scale_b2_rsi))

    # --- ADX Leverage Scale ---
    cat5_adx_scale_b1 = adx_leverage_scale(b1_base, prices, 14)
    cat5_adx_scale_b1_rsi = rsi_exit_filter_on_series(cat5_adx_scale_b1, prices, 30.0)
    catalogue.append(("B1 + ADX Leverage Scale (max 3x)", cat5_adx_scale_b1_rsi))
    cat5_adx_scale_b2 = adx_leverage_scale(b2_base, prices, 14)
    cat5_adx_scale_b2_rsi = rsi_exit_filter_on_series(cat5_adx_scale_b2, prices, 30.0)
    catalogue.append(("B2 + ADX Leverage Scale (max 3x)", cat5_adx_scale_b2_rsi))

    # --- Mild RSI Leverage Scale ---
    cat5_rsi_scale_b1 = mild_rsi_leverage_scale(b1_base, prices, 14)
    cat5_rsi_scale_b1_rsi = rsi_exit_filter_on_series(cat5_rsi_scale_b1, prices, 30.0)
    catalogue.append(("B1 + Mild RSI Leverage Scale (max 3x)", cat5_rsi_scale_b1_rsi))
    cat5_rsi_scale_b2 = mild_rsi_leverage_scale(b2_base, prices, 14)
    cat5_rsi_scale_b2_rsi = rsi_exit_filter_on_series(cat5_rsi_scale_b2, prices, 30.0)
    catalogue.append(("B2 + Mild RSI Leverage Scale (max 3x)", cat5_rsi_scale_b2_rsi))

    # --- Distance Leverage Scale ---
    cat5_dist_scale_b1 = distance_leverage_scale(b1_base, prices, 200)
    cat5_dist_scale_b1_rsi = rsi_exit_filter_on_series(cat5_dist_scale_b1, prices, 30.0)
    catalogue.append(("B1 + Distance Leverage Scale (max 3x)", cat5_dist_scale_b1_rsi))
    cat5_dist_scale_b2 = distance_leverage_scale(b2_base, prices, 200)
    cat5_dist_scale_b2_rsi = rsi_exit_filter_on_series(cat5_dist_scale_b2, prices, 30.0)
    catalogue.append(("B2 + Distance Leverage Scale (max 3x)", cat5_dist_scale_b2_rsi))

    # ===================================================================
    # Category 6: Combined Best Filters (on B1/B2 base)
    # ===================================================================

    # --- Slope>0 + 2-Day Persist ---
    cat6_s0p2_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.0)
    cat6_s0p2_b1 = persistence_filter_wrapper(cat6_s0p2_b1, prices, 2)
    catalogue.append(("B1 + Slope>0 + 2-Day Persist", cat6_s0p2_b1))
    cat6_s0p2_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.0)
    cat6_s0p2_b2 = persistence_filter_wrapper(cat6_s0p2_b2, prices, 2)
    catalogue.append(("B2 + Slope>0 + 2-Day Persist", cat6_s0p2_b2))

    # --- Slope>0 + ADX>20 ---
    cat6_s0a20_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.0)
    cat6_s0a20_b1 = adx_filter_wrapper(cat6_s0a20_b1, prices, 20.0, 14)
    catalogue.append(("B1 + Slope>0 + ADX>20", cat6_s0a20_b1))
    cat6_s0a20_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.0)
    cat6_s0a20_b2 = adx_filter_wrapper(cat6_s0a20_b2, prices, 20.0, 14)
    catalogue.append(("B2 + Slope>0 + ADX>20", cat6_s0a20_b2))

    # --- Slope>0 + SMA50>SMA200 ---
    cat6_s0cr_b1 = sma_slope_filter_wrapper(b1, prices, 200, 5, 0.0)
    cat6_s0cr_b1 = sma_cross_filter_wrapper(cat6_s0cr_b1, prices, 50, 200)
    catalogue.append(("B1 + Slope>0 + SMA50>SMA200", cat6_s0cr_b1))
    cat6_s0cr_b2 = sma_slope_filter_wrapper(b2, prices, 200, 5, 0.0)
    cat6_s0cr_b2 = sma_cross_filter_wrapper(cat6_s0cr_b2, prices, 50, 200)
    catalogue.append(("B2 + Slope>0 + SMA50>SMA200", cat6_s0cr_b2))

    # --- Slope>0 + Slope Leverage Scale ---
    cat6_s0ls_b1 = sma_slope_filter_wrapper(b1_base, prices, 200, 5, 0.0)
    cat6_s0ls_b1 = slope_leverage_scale(cat6_s0ls_b1, prices, 200, 5)
    cat6_s0ls_b1 = rsi_exit_filter_on_series(cat6_s0ls_b1, prices, 30.0)
    catalogue.append(("B1 + Slope>0 + Slope Leverage Scale", cat6_s0ls_b1))
    cat6_s0ls_b2 = sma_slope_filter_wrapper(b2_base, prices, 200, 5, 0.0)
    cat6_s0ls_b2 = slope_leverage_scale(cat6_s0ls_b2, prices, 200, 5)
    cat6_s0ls_b2 = rsi_exit_filter_on_series(cat6_s0ls_b2, prices, 30.0)
    catalogue.append(("B2 + Slope>0 + Slope Leverage Scale", cat6_s0ls_b2))

    # --- ADX>20 + ADX Leverage Scale ---
    cat6_a20ls_b1 = adx_filter_wrapper(b1_base, prices, 20.0, 14)
    cat6_a20ls_b1 = adx_leverage_scale(cat6_a20ls_b1, prices, 14)
    cat6_a20ls_b1 = rsi_exit_filter_on_series(cat6_a20ls_b1, prices, 30.0)
    catalogue.append(("B1 + ADX>20 + ADX Leverage Scale", cat6_a20ls_b1))
    cat6_a20ls_b2 = adx_filter_wrapper(b2_base, prices, 20.0, 14)
    cat6_a20ls_b2 = adx_leverage_scale(cat6_a20ls_b2, prices, 14)
    cat6_a20ls_b2 = rsi_exit_filter_on_series(cat6_a20ls_b2, prices, 30.0)
    catalogue.append(("B2 + ADX>20 + ADX Leverage Scale", cat6_a20ls_b2))

    # ===================================================================
    # Category 7: Refinements on B3/B4 (Counter-Cyclical Hybrids)
    # ===================================================================

    # --- B3 + SMA200 Slope>0 ---
    cat7_b3_s0 = sma_slope_filter_wrapper(b3, prices, 200, 5, 0.0)
    catalogue.append(("B3 + SMA200 Slope>0", cat7_b3_s0))

    # --- B3 + ADX>20 ---
    cat7_b3_a20 = adx_filter_wrapper(b3, prices, 20.0, 14)
    catalogue.append(("B3 + ADX>20", cat7_b3_a20))

    # --- B3 + 2-Day Persist ---
    cat7_b3_p2 = persistence_filter_wrapper(b3, prices, 2)
    catalogue.append(("B3 + 2-Day Persist", cat7_b3_p2))

    # --- B4 + SMA200 Slope>0 ---
    cat7_b4_s0 = sma_slope_filter_wrapper(b4, prices, 200, 5, 0.0)
    catalogue.append(("B4 + SMA200 Slope>0", cat7_b4_s0))

    # --- B4 + ADX>20 ---
    cat7_b4_a20 = adx_filter_wrapper(b4, prices, 20.0, 14)
    catalogue.append(("B4 + ADX>20", cat7_b4_a20))

    # --- B4 + 2-Day Persist ---
    cat7_b4_p2 = persistence_filter_wrapper(b4, prices, 2)
    catalogue.append(("B4 + 2-Day Persist", cat7_b4_p2))

    # ===================================================================
    # Category 8: RSI Threshold Tuning (on B1/B2 base)
    # ===================================================================

    # --- RSI>25 Exit (looser) ---
    cat8_r25_b1 = rsi_exit_filter_on_series(b1_base, prices, rsi_threshold=25.0)
    catalogue.append(("B1 + RSI>25 Exit", cat8_r25_b1))
    cat8_r25_b2 = rsi_exit_filter_on_series(b2_base, prices, rsi_threshold=25.0)
    catalogue.append(("B2 + RSI>25 Exit", cat8_r25_b2))

    # --- RSI>35 Exit (tighter) ---
    cat8_r35_b1 = rsi_exit_filter_on_series(b1_base, prices, rsi_threshold=35.0)
    catalogue.append(("B1 + RSI>35 Exit", cat8_r35_b1))
    cat8_r35_b2 = rsi_exit_filter_on_series(b2_base, prices, rsi_threshold=35.0)
    catalogue.append(("B2 + RSI>35 Exit", cat8_r35_b2))

    # --- RSI>30 Exit + RSI<65 Entry ---
    cat8_r30e65_b1 = rsi_exit_filter_on_series(b1_base, prices, rsi_threshold=30.0)
    cat8_r30e65_b1 = rsi_entry_filter_on_series(cat8_r30e65_b1, prices, rsi_threshold=65.0)
    catalogue.append(("B1 + RSI>30 Exit + RSI<65 Entry", cat8_r30e65_b1))
    cat8_r30e65_b2 = rsi_exit_filter_on_series(b2_base, prices, rsi_threshold=30.0)
    cat8_r30e65_b2 = rsi_entry_filter_on_series(cat8_r30e65_b2, prices, rsi_threshold=65.0)
    catalogue.append(("B2 + RSI>30 Exit + RSI<65 Entry", cat8_r30e65_b2))

    # --- RSI>30 Exit + RSI<60 Entry ---
    cat8_r30e60_b1 = rsi_exit_filter_on_series(b1_base, prices, rsi_threshold=30.0)
    cat8_r30e60_b1 = rsi_entry_filter_on_series(cat8_r30e60_b1, prices, rsi_threshold=60.0)
    catalogue.append(("B1 + RSI>30 Exit + RSI<60 Entry", cat8_r30e60_b1))
    cat8_r30e60_b2 = rsi_exit_filter_on_series(b2_base, prices, rsi_threshold=30.0)
    cat8_r30e60_b2 = rsi_entry_filter_on_series(cat8_r30e60_b2, prices, rsi_threshold=60.0)
    catalogue.append(("B2 + RSI>30 Exit + RSI<60 Entry", cat8_r30e60_b2))

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
# Pareto analysis
# ---------------------------------------------------------------------------


def pareto_analysis(results: list[SweepResult]) -> str:
    """Identify Pareto improvements over each baseline (B1-B4).

    A Pareto improvement: lower avg leverage AND ≥1 metric improved AND
    no metric worsened vs the corresponding baseline.
    """
    # Find baselines
    baseline_names = {
        "B1": "B1: SMA200 ±3% Band + RSI>30 Exit 3x",
        "B2": "B2: SMA200 ±3% Band + RSI>30 Exit 2x",
        "B3": "B3: SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x",
        "B4": "B4: SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x",
    }

    baselines = {}
    for key, name in baseline_names.items():
        bl = next((r for r in results if r.strategy == name), None)
        if bl is not None:
            baselines[key] = bl

    # Metrics where higher is better
    higher_better = ["cagr", "sharpe", "sortino"]
    # Metrics where lower (less negative / smaller) is better
    lower_better = ["max_drawdown", "ann_volatility"]

    EPS = 1e-9

    report_lines = []

    for bl_key, bl in baselines.items():
        report_lines.append(f"\n{'=' * 100}")
        report_lines.append(f"PARETO ANALYSIS vs {bl_key}: {bl.strategy}")
        report_lines.append(f"{'=' * 100}")
        report_lines.append(
            f"  Baseline metrics: CAGR={bl.cagr*100:.2f}%  MaxDD={bl.max_drawdown*100:.1f}%  "
            f"AnnVol={bl.ann_volatility*100:.1f}%  Sharpe={bl.sharpe:.3f}  "
            f"Sortino={bl.sortino:.3f}  AvgLev={bl.avg_leverage:.2f}"
        )

        # Candidate strategies: exclude baselines and buy & hold
        candidates = [
            r for r in results
            if r.strategy not in baseline_names.values()
            and "Buy & Hold" not in r.strategy
            and "plain" not in r.strategy.lower()
        ]

        pareto_improvements = []
        closest_misses = []

        for c in candidates:
            if pd.isna(c.cagr) or pd.isna(c.max_drawdown) or pd.isna(c.ann_volatility) or pd.isna(c.sharpe) or pd.isna(c.sortino):
                continue

            # Check lower average leverage
            lower_lev = c.avg_leverage < bl.avg_leverage - EPS

            # Check improvements
            improved_any = False
            worsened_any = False
            improvements = []
            worsenings = []

            for metric in higher_better:
                c_val = getattr(c, metric)
                bl_val = getattr(bl, metric)
                if c_val > bl_val + EPS:
                    improved_any = True
                    improvements.append(metric)
                elif c_val < bl_val - EPS:
                    worsened_any = True
                    worsenings.append(metric)

            for metric in lower_better:
                c_val = getattr(c, metric)
                bl_val = getattr(bl, metric)
                if c_val > bl_val + EPS:  # less negative = better for drawdown
                    improved_any = True
                    improvements.append(metric)
                elif c_val < bl_val - EPS:  # more negative = worse
                    worsened_any = True
                    worsenings.append(metric)

            if lower_lev and improved_any and not worsened_any:
                pareto_improvements.append((c, improvements))
            elif improved_any:
                # Track closest misses (improved some but worsened others or lev not lower)
                closest_misses.append((c, improvements, worsenings, lower_lev))

        if pareto_improvements:
            report_lines.append(f"\n  ** PARETO IMPROVEMENTS FOUND ({len(pareto_improvements)}):")
            report_lines.append(f"  {'Strategy':<55} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'AvgLev':>7} {'Improved':>30}")
            report_lines.append(f"  {'-' * 130}")
            for c, imps in sorted(pareto_improvements, key=lambda x: x[0].cagr, reverse=True):
                imp_str = ", ".join(imps)
                report_lines.append(
                    f"  {c.strategy:<55} {c.cagr*100:>7.2f}% {c.max_drawdown*100:>7.1f}% "
                    f"{c.ann_volatility*100:>7.1f}% {c.sharpe:>7.3f} {c.sortino:>7.3f} "
                    f"{c.avg_leverage:>7.2f} {imp_str:>30}"
                )
        else:
            report_lines.append(f"\n  No strict Pareto improvements found (lower lev + at least 1 better + none worse).")

        # Show closest misses
        if closest_misses:
            # Sort by number of improvements descending, then by CAGR
            closest_misses.sort(key=lambda x: (len(x[1]), x[0].cagr), reverse=True)
            report_lines.append(f"\n  Closest strategies (improved some metrics but had trade-offs):")
            report_lines.append(f"  {'Strategy':<55} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'AvgLev':>7} {'+':>20} {'-':>20} {'Lev<':>6}")
            report_lines.append(f"  {'-' * 140}")
            for c, imps, wors, lower_lev in closest_misses[:10]:
                imp_str = ", ".join(imps)
                wor_str = ", ".join(wors)
                lev_flag = "YES" if lower_lev else "no"
                report_lines.append(
                    f"  {c.strategy:<55} {c.cagr*100:>7.2f}% {c.max_drawdown*100:>7.1f}% "
                    f"{c.ann_volatility*100:>7.1f}% {c.sharpe:>7.3f} {c.sortino:>7.3f} "
                    f"{c.avg_leverage:>7.2f} {imp_str:>20} {wor_str:>20} {lev_flag:>6}"
                )

    return "\n".join(report_lines)


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 72)
    print("S&P 500 Pareto-Optimization Sweep")
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
    print("\n[3/4] Building Pareto strategy catalogue...")
    catalogue = build_catalogue(prices)
    print(f"  -> {len(catalogue)} strategies to test\n")

    # 4. Run all strategies
    print("[4/4] Running Pareto sweep...\n")
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
            print(f"CAGR={cagr_s}  MaxDD={dd_s}  Sharpe={sh_s}  Trades={r.trades}  AvgLev={r.avg_leverage:.2f}")
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
    print("PARETO SWEEP RESULTS — All Strategies Ranked by CAGR")
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
        al_s = f"{r.avg_leverage:.2f}"
        print(f"{rank:<5} {r.strategy:<58} {cagr_s:>8} {dd_s:>8} {vol_s:>8} {sh_s:>7} {so_s:>7} {cash_s:>7} {al_s:>7} {ev_s:>10} {r.trades:>7}")

    # --- Pareto Analysis ---
    pareto_report = pareto_analysis(results)
    print(pareto_report)

    # --- Category Winners ---
    print(f"\n{'=' * 130}")
    print("WINNERS BY PARETO CATEGORY (best CAGR in each)")
    print(f"{'=' * 130}")

    def best_in_cat(subset, key_fn=lambda r: r.cagr, reverse=True):
        valid = [r for r in subset if not pd.isna(key_fn(r))]
        return max(valid, key=key_fn) if valid else None

    def fmt_res(r):
        if r is None:
            return "N/A"
        return (f"{r.strategy} | CAGR={r.cagr*100:.2f}% MaxDD={r.max_drawdown*100:.1f}% "
                f"Vol={r.ann_volatility*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f} "
                f"AvgLev={r.avg_leverage:.2f}")

    # Category 1: Trend Quality Filters
    cat1 = [r for r in results if any(tag in r.strategy for tag in
            ["Slope>0", "Slope>5%", "Slope>10%", "SMA50>SMA200", "ADX>20", "ADX>25"])
            and "Persist" not in r.strategy and "Scale" not in r.strategy
            and "Combined" not in r.strategy]
    print(f"  Best Trend Quality Filter:       {fmt_res(best_in_cat(cat1))}")

    # Category 2: Persistence
    cat2 = [r for r in results if "Persist" in r.strategy and "Slope" not in r.strategy
            and "ADX" not in r.strategy]
    print(f"  Best Persistence Filter:         {fmt_res(best_in_cat(cat2))}")

    # Category 3: Adaptive Bands
    cat3 = [r for r in results if ("ATR" in r.strategy or "VIX-Scaled" in r.strategy)]
    print(f"  Best Adaptive Band:              {fmt_res(best_in_cat(cat3))}")

    # Category 4: Dual Band
    cat4 = [r for r in results if "Entry±" in r.strategy]
    print(f"  Best Dual Band:                  {fmt_res(best_in_cat(cat4))}")

    # Category 5: Leverage Scaling
    cat5 = [r for r in results if "Leverage Scale" in r.strategy and "Slope>" not in r.strategy
            and "ADX>" not in r.strategy]
    print(f"  Best Leverage Scale:             {fmt_res(best_in_cat(cat5))}")

    # Category 6: Combined
    cat6 = [r for r in results if ("Slope>0 +" in r.strategy or "ADX>20 +" in r.strategy)
            and "Scale" in r.strategy or
            ("Slope>0 + 2-Day" in r.strategy or "Slope>0 + ADX>20" in r.strategy
             or "Slope>0 + SMA50" in r.strategy)]
    print(f"  Best Combined Filter:            {fmt_res(best_in_cat(cat6))}")

    # Category 7: B3/B4 Refinements
    cat7 = [r for r in results if "B3 +" in r.strategy or "B4 +" in r.strategy]
    print(f"  Best B3/B4 Refinement:           {fmt_res(best_in_cat(cat7))}")

    # Category 8: RSI Tuning
    cat8 = [r for r in results if "RSI>" in r.strategy and "Exit" in r.strategy
            and "B1" not in r.strategy and "B2" not in r.strategy
            and "B3" not in r.strategy and "B4" not in r.strategy
            and "Scale" not in r.strategy]
    print(f"  Best RSI Tuning:                 {fmt_res(best_in_cat(cat8))}")

    # --- Benchmark reference ---
    print(f"\n{'=' * 130}")
    print("BENCHMARK REFERENCE")
    print(f"{'=' * 130}")
    for bench_name in ["Buy & Hold SPY 1x", "SMA200 ±3% Band 2x (plain)", "SMA200 ±3% Band 3x (plain)"]:
        b = next((r for r in results if r.strategy == bench_name), None)
        if b:
            print(f"  {b.strategy}: CAGR={b.cagr*100:.2f}% DD={b.max_drawdown*100:.1f}% "
                  f"Sharpe={b.sharpe:.3f} Sortino={b.sortino:.3f} EndVal=${b.end_value:,.0f}")

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
    print("Pareto sweep complete.")
    print(f"{'=' * 130}")


if __name__ == "__main__":
    main()
