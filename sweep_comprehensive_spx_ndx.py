"""Comprehensive strategy sweep for S&P 500 and Nasdaq 100.

Runs 150+ strategies for SPX and NDX, including all existing strategies from sweep_all_assets_strategies.py
plus new candidate strategies. Outputs to output/comprehensive_sweep/spx_ndx_comprehensive.csv.
"""

from __future__ import annotations

import csv
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from core.engine import (
    INITIAL_CAPITAL,
    TRADING_DAYS,
    VIX_STRESS_THRESHOLD,
    PortfolioEngine,
    BacktestResult,
)
from core.metrics import comprehensive_stats
from core.etp_leverage import (
    synthetic_daily_reset_return,
    daily_return_for_leverage,
    TER_ANNUAL,
    MAX_ETP_DAILY_ABS,
    EtpBundle,
    SPX_ETP,
    NDX_ETP,
)
from core.indicators import sma, ema, rsi, macd, bollinger_bands

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "comprehensive_sweep"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0      # $10/year on $100 base
SIGNAL_DELAY_DAYS = 1
DEFAULT_VIX = 20.0            # before VIX inception (1990)
DEFAULT_TBILL = 0.03          # before IRX inception
VIX_INCEPTION = "1990-01-02"

# Asset definitions for SPX and NDX only
ASSETS: dict[str, dict[str, Any]] = {
    "spx": {
        "label": "S&P 500", "index": "^GSPC", "etf_1x": "SPY", "etf_2x": "SSO", "etf_3x": "UPRO",
        "etf_1x_start": "1993-01-29", "etf_2x_start": "2006-06-21", "etf_3x_start": "2009-06-25",
        "index_start": "1950-01-03", "max_leverage": 3, "trading_cost": 0.001,
    },
    "ndx": {
        "label": "Nasdaq 100", "index": "^NDX", "etf_1x": "QQQ", "etf_2x": "QLD", "etf_3x": "TQQQ",
        "etf_1x_start": "1999-03-10", "etf_2x_start": "2006-06-21", "etf_3x_start": "2010-02-11",
        "index_start": "1985-10-01", "max_leverage": 3, "trading_cost": 0.001,
    },
}

# ===================================================================
# PART 1: INDICATOR FUNCTIONS (self-contained)
# ===================================================================

def _sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram."""
    line = _ema(close, fast) - _ema(close, slow)
    sig = _ema(line, signal)
    hist = line - sig
    return line, sig, hist


def _bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0):
    """Bollinger Bands: lower, mid, upper."""
    mid = _sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return lower, mid, upper


def _drawdown_from_peak(close: pd.Series) -> pd.Series:
    """Price drawdown from running peak (negative values = below peak)."""
    peak = close.cummax()
    return (close - peak) / peak


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    tr0 = abs(high - low)
    tr1 = abs(high - close.shift())
    tr2 = abs(low - close.shift())
    tr = pd.DataFrame({"tr0": tr0, "tr1": tr1, "tr2": tr2}).max(axis=1)
    return tr.rolling(window=window, min_periods=window).mean()


def _keltner_bands(close: pd.Series, high: pd.Series, low: pd.Series, window: int = 20, mult: float = 2.0):
    """Keltner Channels: lower, mid, upper."""
    mid = _ema(close, window)
    atr = _atr(high, low, close, window)
    upper = mid + atr * mult
    lower = mid - atr * mult
    return lower, mid, upper


def _donchian_channels(high: pd.Series, low: pd.Series, window: int = 20):
    """Donchian Channels: lower, mid, upper."""
    upper = high.rolling(window=window, min_periods=window).max()
    lower = low.rolling(window=window, min_periods=window).min()
    mid = (upper + lower) / 2
    return lower, mid, upper


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0), index=high.index)
    
    tr = pd.DataFrame({
        'tr0': abs(high - low),
        'tr1': abs(high - close.shift()),
        'tr2': abs(low - close.shift())
    }).max(axis=1)
    
    plus_di = 100 * (_ema(plus_dm, window) / _ema(tr, window))
    minus_di = 100 * (_ema(minus_dm, window) / _ema(tr, window))
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = _ema(dx, window)
    
    return adx


# ===================================================================
# PART 2: DATA LOADING
# ===================================================================

def _download_tbill_vix() -> tuple[pd.Series, pd.Series]:
    """Download ^IRX (13-week T-bill) and ^VIX once for all assets."""
    print("  Downloading ^IRX (T-bill) and ^VIX ...", flush=True)
    raw = yf.download(["^IRX", "^VIX"], start="1950-01-01", progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError("No T-bill/VIX data returned from yfinance.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw[["Close"]].copy()
        # If only one ticker returned, handle gracefully
        if "^IRX" not in closes.columns and "^VIX" not in closes.columns:
            # Try renaming
            pass

    tbill = closes.get("^IRX", pd.Series(index=closes.index))
    vix = closes.get("^VIX", pd.Series(index=closes.index))

    # ^IRX is in percent; convert to decimal
    tbill = tbill.astype(float) / 100.0
    vix = vix.astype(float)

    tbill = tbill.sort_index().ffill()
    vix = vix.sort_index().ffill()

    return tbill, vix


def load_asset_data(asset_key: str, tbill_global: pd.Series, vix_global: pd.Series):
    """Download index + ETP data for an asset. Returns dict with prices DataFrame and ETP closes."""
    cfg = ASSETS[asset_key]
    print(f"  Downloading index: {cfg['index']} from {cfg['index_start']} ...", flush=True)

    # Download index data
    index_raw = yf.download(cfg["index"], start=cfg["index_start"], progress=False, auto_adjust=True)
    if index_raw.empty:
        raise ValueError(f"No index data for {cfg['index']}")

    if isinstance(index_raw.columns, pd.MultiIndex):
        index_close = index_raw["Close"].copy().iloc[:, 0] if index_raw["Close"].shape[1] > 1 else index_raw["Close"].iloc[:, 0]
    else:
        index_close = index_raw["Close"].astype(float)

    index_close = index_close.sort_index()
    # Remove zero or negative prices
    index_close = index_close[index_close > 0]

    # Download ETP data where available
    etp_closes: dict[str, pd.Series] = {}
    for lev, ticker_key in [("1x", "etf_1x"), ("2x", "etf_2x"), ("3x", "etf_3x")]:
        ticker = cfg.get(ticker_key)
        start = cfg.get(f"etf_{lev}_start")
        if ticker and start:
            print(f"    Downloading {ticker} ({lev}) from {start} ...", flush=True)
            try:
                raw = yf.download(ticker, start=start, progress=False, auto_adjust=True)
                if not raw.empty:
                    if isinstance(raw.columns, pd.MultiIndex):
                        close = raw["Close"].copy().iloc[:, 0] if raw["Close"].shape[1] > 1 else raw["Close"].iloc[:, 0]
                    else:
                        close = raw["Close"].astype(float)
                    close = close.sort_index()
                    close = close[close > 0]
                    if len(close) > 0:
                        etp_closes[lev] = close
                        print(f"      -> {len(close)} rows", flush=True)
            except Exception as e:
                print(f"      WARNING: Could not download {ticker}: {e}", flush=True)

    # Build unified prices DataFrame
    # Align index_close, tbill, vix on the same date range
    idx = index_close.index
    tbill_aligned = tbill_global.reindex(idx).ffill()
    vix_aligned = vix_global.reindex(idx).ffill()

    # Fill pre-inception gaps
    tbill_aligned = tbill_aligned.fillna(DEFAULT_TBILL)
    vix_aligned = vix_aligned.fillna(DEFAULT_VIX)

    # For dates before VIX inception, use default
    if VIX_INCEPTION:
        pre_vix = vix_aligned.index < pd.Timestamp(VIX_INCEPTION)
        vix_aligned.loc[pre_vix] = DEFAULT_VIX

    prices = pd.DataFrame({
        "spx_close": index_close.astype(float),
        "tbill_rate": tbill_aligned.astype(float),
        "vix": vix_aligned.astype(float),
    }, index=idx)
    
    # Add high and low for indicators that need them
    if "High" in index_raw.columns and "Low" in index_raw.columns:
        if isinstance(index_raw.columns, pd.MultiIndex):
            prices["high"] = index_raw["High"].iloc[:, 0].astype(float)
            prices["low"] = index_raw["Low"].iloc[:, 0].astype(float)
        else:
            prices["high"] = index_raw["High"].astype(float)
            prices["low"] = index_raw["Low"].astype(float)
    else:
        # If high/low not available, use close for all (less accurate but functional)
        prices["high"] = prices["spx_close"]
        prices["low"] = prices["spx_close"]
    
    prices = prices.dropna(subset=["spx_close"])
    prices = prices.ffill()

    return {"prices": prices, "etp_closes": etp_closes, "cfg": cfg}


# ===================================================================
# PART 3: ETP RETURN PANEL CONSTRUCTION
# ===================================================================

def build_asset_etp_panel(prices: pd.DataFrame, etp_closes: dict[str, pd.Series], cfg: dict) -> pd.DataFrame:
    """Build daily ETP return panel with columns: ret_0, ret_1, ret_2, ret_3, vix.

    Uses real ETP returns where available, synthetic fills otherwise.
    """
    index = prices.index
    idx_ret = prices["spx_close"].pct_change()
    tbill = prices["tbill_rate"]
    vix = prices["vix"]

    # ret_0 = daily T-bill return
    ret_0 = tbill / TRADING_DAYS

    # Build ret_1, ret_2, ret_3
    ret_1 = pd.Series(np.nan, index=index)
    ret_2 = pd.Series(np.nan, index=index)
    ret_3 = pd.Series(np.nan, index=index)
    synthetic_2 = pd.Series(True, index=index)
    synthetic_3 = pd.Series(True, index=index)

    # 1x: use real ETP if available, else synthetic
    if "1x" in etp_closes:
        close_1x = etp_closes["1x"].reindex(index).ffill()
        ret_1_raw = close_1x.pct_change()
        for dt in index:
            val = ret_1_raw.loc[dt]
            if pd.notna(val) and abs(float(val)) <= MAX_ETP_DAILY_ABS[1]:
                ret_1.loc[dt] = float(val)
    # Fill remaining NaN in ret_1 with synthetic
    for dt in index:
        if pd.isna(ret_1.loc[dt]) and pd.notna(idx_ret.loc[dt]):
            r_idx = float(idx_ret.loc[dt])
            tb = float(tbill.loc[dt]) if pd.notna(tbill.loc[dt]) else 0.0
            vix_val = float(vix.loc[dt]) if pd.notna(vix.loc[dt]) else None
            ret_1.loc[dt] = synthetic_daily_reset_return(r_idx, 1.0, tb, vix=vix_val)

    # 2x: use real ETP if available, else synthetic
    if "2x" in etp_closes:
        close_2x = etp_closes["2x"].reindex(index).ffill()
        ret_2_raw = close_2x.pct_change()
        for dt in index:
            val = ret_2_raw.loc[dt]
            if pd.notna(val) and abs(float(val)) <= MAX_ETP_DAILY_ABS[2]:
                ret_2.loc[dt] = float(val)
                synthetic_2.loc[dt] = False
    for dt in index:
        if pd.isna(ret_2.loc[dt]) and pd.notna(idx_ret.loc[dt]):
            r_idx = float(idx_ret.loc[dt])
            tb = float(tbill.loc[dt]) if pd.notna(tbill.loc[dt]) else 0.0
            vix_val = float(vix.loc[dt]) if pd.notna(vix.loc[dt]) else None
            ret_2.loc[dt] = synthetic_daily_reset_return(r_idx, 2.0, tb, vix=vix_val)

    # 3x: use real ETP if available, else synthetic
    if "3x" in etp_closes:
        close_3x = etp_closes["3x"].reindex(index).ffill()
        ret_3_raw = close_3x.pct_change()
        for dt in index:
            val = ret_3_raw.loc[dt]
            if pd.notna(val) and abs(float(val)) <= MAX_ETP_DAILY_ABS[3]:
                ret_3.loc[dt] = float(val)
                synthetic_3.loc[dt] = False
    for dt in index:
        if pd.isna(ret_3.loc[dt]) and pd.notna(idx_ret.loc[dt]):
            r_idx = float(idx_ret.loc[dt])
            tb = float(tbill.loc[dt]) if pd.notna(tbill.loc[dt]) else 0.0
            vix_val = float(vix.loc[dt]) if pd.notna(vix.loc[dt]) else None
            ret_3.loc[dt] = synthetic_daily_reset_return(r_idx, 3.0, tb, vix=vix_val)

    panel = pd.DataFrame({
        "ret_0": ret_0.fillna(0.0),
        "ret_1": ret_1.fillna(0.0),
        "ret_2": ret_2.fillna(0.0),
        "ret_3": ret_3.fillna(0.0),
        "vix": vix.ffill().fillna(DEFAULT_VIX),
        "synthetic_2": synthetic_2,
        "synthetic_3": synthetic_3,
    }, index=index)

    return panel


# ===================================================================
# PART 4: SIGNAL FUNCTIONS (self-contained, generic)
# ===================================================================

# --- Basic SMA signal ---
def sma_signal(prices: pd.DataFrame, window: int, leverage: float = 1.0) -> pd.Series:
    """Returns leverage when close > SMA, 0 otherwise."""
    close = prices["spx_close"]
    s = _sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s] = leverage
    return lev


# --- EMA signal ---
def ema_signal(prices: pd.DataFrame, window: int, leverage: float = 1.0) -> pd.Series:
    """Returns leverage when close > EMA, 0 otherwise."""
    close = prices["spx_close"]
    e = _ema(close, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > e] = leverage
    return lev


# --- SMA Band / Hysteresis ---
def sma_band_signal(prices: pd.DataFrame, window: int, band_pct: float, leverage: float) -> pd.Series:
    """SMA crossover with hysteresis band. Returns leverage or 0."""
    close = prices["spx_close"]
    s = _sma(close, window)
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


# --- RSI Exit Filter ---
def rsi_exit_filter_on_series(lev_series: pd.Series, prices: pd.DataFrame,
                               rsi_threshold: float = 30.0, rsi_period: int = 14) -> pd.Series:
    """Block exit when RSI < threshold (oversold). Avoid selling into panic."""
    close = prices["spx_close"]
    r = _rsi(close, rsi_period)
    result = lev_series.copy()
    in_position = False
    current_lev = 0.0

    for i in range(len(result)):
        bl = lev_series.iloc[i]
        rsi_val = r.iloc[i]
        if pd.isna(bl):
            continue
        if not in_position:
            if bl > 0.0:
                in_position = True
                current_lev = bl
                result.iloc[i] = bl
        else:
            if bl == 0.0:
                if pd.notna(rsi_val) and rsi_val < rsi_threshold:
                    result.iloc[i] = current_lev
                else:
                    in_position = False
                    current_lev = 0.0
                    result.iloc[i] = 0.0
            else:
                current_lev = bl
                result.iloc[i] = bl
    return result


# --- RSI Leverage Signal (counter-cyclical) ---
def rsi_leverage_signal(prices: pd.DataFrame, zones: list[tuple[float, float]],
                        rsi_period: int = 14) -> pd.Series:
    """Return leverage based on RSI zone. zones: [(threshold, leverage), ...] sorted ascending."""
    close = prices["spx_close"]
    r = _rsi(close, rsi_period)
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


# --- VIX Leverage Signal ---
def vix_leverage_signal(prices: pd.DataFrame, zones: list[tuple[float, float]]) -> pd.Series:
    """Return leverage based on VIX level. zones: [(vix_threshold, leverage), ...] sorted DESCENDING."""
    vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
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


# --- Distance-from-SMA Leverage Scale ---
def distance_leverage_scale(base_lev: pd.Series, prices: pd.DataFrame,
                            sma_window: int = 200) -> pd.Series:
    """Scale leverage 1-3 based on price/SMA ratio when base signal says long."""
    close = prices["spx_close"]
    s = _sma(close, sma_window)
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


# --- Golden Cross Signal ---
def golden_cross_signal(prices: pd.DataFrame, fast: int = 50, slow: int = 200,
                        leverage: float = 1.0) -> pd.Series:
    """SMA fast > SMA slow -> leverage, else 0. State machine with hysteresis."""
    close = prices["spx_close"]
    fast_sma = _sma(close, fast)
    slow_sma = _sma(close, slow)
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    warmup = max(fast, slow)
    for i in range(len(prices)):
        if i < warmup:
            continue
        f_val = fast_sma.iloc[i]
        s_val = slow_sma.iloc[i]
        if pd.isna(f_val) or pd.isna(s_val):
            lev.iloc[i] = leverage if in_position else 0.0
            continue
        if f_val > s_val:
            in_position = True
        elif f_val < s_val:
            in_position = False
        lev.iloc[i] = leverage if in_position else 0.0
    return lev


# --- Bollinger Band Mean Reversion Signal ---
def bb_signal(prices: pd.DataFrame, window: int = 20, num_std: float = 2.0,
              leverage: float = 1.0) -> pd.Series:
    """Enter when price touches/crosses below lower band, exit when crosses above mid."""
    close = prices["spx_close"]
    lower, mid, upper = _bollinger_bands(close, window, num_std)
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    for i in range(len(prices)):
        if i < window:
            continue
        c = close.iloc[i]
        l = lower.iloc[i]
        m = mid.iloc[i]
        if pd.isna(c) or pd.isna(l) or pd.isna(m):
            lev.iloc[i] = leverage if in_position else 0.0
            continue
        if not in_position and c <= l:
            in_position = True
        elif in_position and c >= m:
            in_position = False
        lev.iloc[i] = leverage if in_position else 0.0
    return lev


# --- Momentum Signal (N-month) ---
def momentum_signal(prices: pd.DataFrame, months: int = 12, leverage: float = 1.0) -> pd.Series:
    """Long if current close > close N months ago, else cash."""
    close = prices["spx_close"]
    lookback_days = int(months * 21)  # ~21 trading days per month
    lev = pd.Series(0.0, index=prices.index)
    for i in range(len(prices)):
        if i < lookback_days:
            continue
        c = close.iloc[i]
        c_past = close.iloc[i - lookback_days]
        if pd.isna(c) or pd.isna(c_past):
            continue
        lev.iloc[i] = leverage if c > c_past else 0.0
    return lev


# --- MACD Signal ---
def macd_signal(prices: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9,
                leverage: float = 1.0) -> pd.Series:
    """Long when MACD line > signal line, else cash."""
    close = prices["spx_close"]
    line, sig, _ = _macd(close, fast, slow, signal)
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    warmup = slow + signal
    for i in range(len(prices)):
        if i < warmup:
            continue
        macd_val = line.iloc[i]
        sig_val = sig.iloc[i]
        if pd.isna(macd_val) or pd.isna(sig_val):
            lev.iloc[i] = leverage if in_position else 0.0
            continue
        if macd_val > sig_val:
            in_position = True
        elif macd_val < sig_val:
            in_position = False
        lev.iloc[i] = leverage if in_position else 0.0
    return lev


# --- Band + Trend Hybrid (for counter-cyclical scaling) ---
def band_trend_hybrid(prices: pd.DataFrame, sma_window: int, band_pct: float,
                      cc_lev: pd.Series) -> pd.Series:
    """SMA band hysteresis for trend detection + counter-cyclical leverage scaling."""
    close = prices["spx_close"]
    s = _sma(close, sma_window)
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
        if in_market:
            cc_val = cc_lev.iloc[i]
            lev.iloc[i] = cc_val if not pd.isna(cc_val) and cc_val > 0.0 else 1.0
        else:
            lev.iloc[i] = 0.0
    return lev


# --- DD-Based Leverage Signal ---
def dd_based_leverage(prices: pd.DataFrame, dd_threshold_2x: float = 0.20,
                      dd_threshold_3x: float = 0.50) -> pd.Series:
    """Enter 2x at -20% DD, 3x at -50% DD (from running peak)."""
    close = prices["spx_close"]
    dd = _drawdown_from_peak(close)
    lev = pd.Series(0.0, index=prices.index)
    for i in range(len(prices)):
        d = dd.iloc[i]
        if pd.isna(d):
            continue
        if d <= -dd_threshold_3x:
            lev.iloc[i] = 3.0
        elif d <= -dd_threshold_2x:
            lev.iloc[i] = 2.0
        else:
            lev.iloc[i] = 1.0
    return lev


# --- BB Counter-Cyclical Signal ---
def bb_counter_cyclical(prices: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """Enter below lower band -> 3x, between bands -> 1x, above upper -> 0."""
    close = prices["spx_close"]
    lower, mid, upper = _bollinger_bands(close, window, num_std)
    lev = pd.Series(0.0, index=prices.index)
    for i in range(len(prices)):
        c = close.iloc[i]
        l = lower.iloc[i]
        u = upper.iloc[i]
        if pd.isna(c) or pd.isna(l) or pd.isna(u):
            continue
        if c < l:
            lev.iloc[i] = 3.0
        elif c > u:
            lev.iloc[i] = 0.0
        else:
            lev.iloc[i] = 1.0
    return lev


# --- Guarded Tiered DD Recovery ---
def guarded_leverage(prices: pd.DataFrame, sma_window: int = 20,
                     trigger_a: float = 0.10, trigger_b: float = 0.20,
                     max_leverage: float = 2.0) -> pd.Series:
    """Tiered DD recovery with SMA guard.

    Base: 1x when close > SMA(sma_window), else cash.
    DD triggers: -trigger_a -> 2x tier, -trigger_b -> 3x tier (capped at max_leverage).
    Guard SMA prevents levered exposure when price is below it.
    Recovery: tier2 at 25% gain, tier3 at 33% gain.
    """
    close = prices["spx_close"]
    base_sma = _sma(close, sma_window)
    guard_sma = _sma(close, sma_window)  # same as base for standard guarded
    spx_dd = _drawdown_from_peak(close)

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_lev = min(2.0, max_leverage)
    tier3_lev = min(3.0, max_leverage)

    for i in range(len(prices)):
        if i < sma_window:
            continue
        px = float(close.iloc[i])
        dd = float(spx_dd.iloc[i]) if pd.notna(spx_dd.iloc[i]) else 0.0
        base_sma_val = float(base_sma.iloc[i]) if pd.notna(base_sma.iloc[i]) else 0.0
        guard_sma_val = float(guard_sma.iloc[i]) if pd.notna(guard_sma.iloc[i]) else 0.0
        base_lev = 1.0 if px > base_sma_val else 0.0
        guard_ok = px > guard_sma_val

        if regime == "tier3":
            if entry_close > 0 and px / entry_close - 1.0 >= 1.0 / 3.0:
                regime = "base"
            elif guard_ok:
                lev.iloc[i] = tier3_lev
                continue
            else:
                lev.iloc[i] = base_lev
                continue

        if regime == "tier2":
            if dd <= -trigger_b and guard_ok:
                regime = "tier3"
                entry_close = px
                lev.iloc[i] = tier3_lev
                continue
            if entry_close > 0 and px / entry_close - 1.0 >= 0.50 / 2.0:
                regime = "base"
            elif guard_ok:
                lev.iloc[i] = tier2_lev
                continue
            else:
                lev.iloc[i] = base_lev
                continue

        if dd <= -trigger_b and guard_ok:
            regime = "tier3"
            entry_close = px
            lev.iloc[i] = tier3_lev
        elif dd <= -trigger_a and guard_ok:
            regime = "tier2"
            entry_close = px
            lev.iloc[i] = tier2_lev
        else:
            lev.iloc[i] = base_lev

    return lev


# --- Guarded+ (SMA200 base, DD triggers, max 2x) ---
def guarded_plus_leverage(prices: pd.DataFrame, sma_window: int = 200,
                          trigger_a: float = 0.10, trigger_b: float = 0.20,
                          max_leverage: float = 2.0) -> pd.Series:
    """Guarded+ variant: SMA200 base trend, DD recovery tiers, max 2x."""
    close = prices["spx_close"]
    base_sma = _sma(close, sma_window)
    guard_sma = _sma(close, sma_window)
    spx_dd = _drawdown_from_peak(close)

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_lev = min(2.0, max_leverage)
    tier3_lev = min(3.0, max_leverage)

    for i in range(len(prices)):
        if i < sma_window:
            continue
        px = float(close.iloc[i])
        dd = float(spx_dd.iloc[i]) if pd.notna(spx_dd.iloc[i]) else 0.0
        base_sma_val = float(base_sma.iloc[i]) if pd.notna(base_sma.iloc[i]) else 0.0
        guard_sma_val = float(guard_sma.iloc[i]) if pd.notna(guard_sma.iloc[i]) else 0.0
        base_lev = 1.0 if px > base_sma_val else 0.0
        guard_ok = px > guard_sma_val

        if regime == "tier3":
            if entry_close > 0 and px / entry_close - 1.0 >= 1.0 / 3.0:
                regime = "base"
            elif guard_ok:
                lev.iloc[i] = tier3_lev
                continue
            else:
                lev.iloc[i] = base_lev
                continue

        if regime == "tier2":
            if dd <= -trigger_b and guard_ok:
                regime = "tier3"
                entry_close = px
                lev.iloc[i] = tier3_lev
                continue
            if entry_close > 0 and px / entry_close - 1.0 >= 0.50 / 2.0:
                regime = "base"
            elif guard_ok:
                lev.iloc[i] = tier2_lev
                continue
            else:
                lev.iloc[i] = base_lev
                continue

        if dd <= -trigger_b and guard_ok:
            regime = "tier3"
            entry_close = px
            lev.iloc[i] = tier3_lev
        elif dd <= -trigger_a and guard_ok:
            regime = "tier2"
            entry_close = px
            lev.iloc[i] = tier2_lev
        else:
            lev.iloc[i] = base_lev

    return lev


# --- Golden Cross + VIX Volguard ---
def golden_volguard_signal(prices: pd.DataFrame, max_leverage: float = 2.0) -> pd.Series:
    """Golden cross (SMA50 > SMA200) determines trend. VIX scales leverage when long."""
    close = prices["spx_close"]
    fast_sma = _sma(close, 50)
    slow_sma = _sma(close, 200)
    vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    warmup = 200

    for i in range(len(prices)):
        if i < warmup:
            continue
        f_val = fast_sma.iloc[i]
        s_val = slow_sma.iloc[i]
        v = vix_series.iloc[i]
        if pd.isna(f_val) or pd.isna(s_val):
            lev.iloc[i] = 0.0
            continue
        if f_val > s_val:
            in_position = True
        elif f_val < s_val:
            in_position = False

        if not in_position:
            lev.iloc[i] = 0.0
        else:
            if pd.isna(v):
                lev.iloc[i] = 1.0
            elif v > 30:
                lev.iloc[i] = 1.0
            elif v > 20 and max_leverage >= 3:
                lev.iloc[i] = 2.0
            else:
                lev.iloc[i] = max_leverage
    return lev


# --- Monthly SMA Signal ---
def monthly_sma_signal(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    """SMA signal evaluated at month-end only, held for the entire next month."""
    close = prices["spx_close"]
    s = _sma(close, window)
    daily_signal = pd.Series(0.0, index=prices.index)
    mask = close > s
    daily_signal[mask] = leverage

    # Get month-end values and forward-fill
    monthly = daily_signal.resample("ME").last()
    # Reindex to daily, forward fill, fill initial NaNs with 0
    result = monthly.reindex(prices.index).ffill().fillna(0.0)
    return result


# --- Volatility Targeting ---
def volatility_targeting_signal(prices: pd.DataFrame, target_vol: float, sma_filter: int = None) -> pd.Series:
    """Target volatility by scaling leverage. Optionally with SMA filter."""
    close = prices["spx_close"]
    returns = close.pct_change()
    vol_20d = returns.rolling(20).std() * np.sqrt(252)  # Annualized 20-day vol
    
    # Calculate leverage as target_vol / realized_vol, clamped to [0, 3]
    lev = pd.Series(1.0, index=prices.index)
    lev = (target_vol / vol_20d).clip(0, 3)
    
    # Apply SMA filter if specified
    if sma_filter is not None:
        sma_val = _sma(close, sma_filter)
        above_sma = close > sma_val
        lev = lev.where(above_sma, 0.0)  # Set to 0 when below SMA
    
    return lev


# --- Multi-timeframe Confluence ---
def multi_sma_confluence_signal(prices: pd.DataFrame, windows: list[int], leverage: float) -> pd.Series:
    """Enter when price is above all specified SMAs, else cash."""
    close = prices["spx_close"]
    lev = pd.Series(0.0, index=prices.index)
    
    # Start with all True, then AND with each SMA condition
    condition = pd.Series(True, index=prices.index)
    for window in windows:
        sma_val = _sma(close, window)
        condition = condition & (close > sma_val)
    
    lev.loc[condition] = leverage
    return lev


# --- Trailing Stop ---
def trailing_stop_signal(prices: pd.DataFrame, base_signal: pd.Series, stop_pct: float) -> pd.Series:
    """Apply trailing stop to base signal."""
    close = prices["spx_close"]
    lev = base_signal.copy()
    
    in_position = False
    peak_price = 0.0
    
    for i in range(len(prices)):
        base_lev = base_signal.iloc[i]
        price = close.iloc[i]
        
        # If base signal says to exit, we exit regardless of trailing stop
        if in_position and base_lev == 0.0:
            in_position = False
            peak_price = 0.0
            lev.iloc[i] = 0.0
            continue
            
        # If base signal says to enter and we're not in position
        if not in_position and base_lev > 0.0:
            in_position = True
            peak_price = price
            lev.iloc[i] = base_lev
            continue
            
        # If we're in position, update peak and check stop
        if in_position:
            # Update peak
            if price > peak_price:
                peak_price = price
            
            # Check trailing stop
            drawdown = (peak_price - price) / peak_price
            if drawdown >= stop_pct:
                # Trailing stop triggered
                in_position = False
                peak_price = 0.0
                lev.iloc[i] = 0.0
            else:
                lev.iloc[i] = base_lev
    
    return lev


# --- Seasonality ---
def seasonality_signal(prices: pd.DataFrame, leverage: float, months_in_market: list[int]) -> pd.Series:
    """Seasonal signal: in market during specified months, else cash."""
    lev = pd.Series(0.0, index=prices.index)
    months = prices.index.month
    in_market = months.isin(months_in_market)
    lev.loc[in_market] = leverage
    return lev


# --- Keltner Channel ---
def keltner_signal(prices: pd.DataFrame, window: int, mult: float, leverage: float) -> pd.Series:
    """Keltner Channel breakout signal."""
    close = prices["spx_close"]
    high = prices["high"]
    low = prices["low"]
    lower, mid, upper = _keltner_bands(close, high, low, window, mult)
    
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    
    for i in range(len(prices)):
        if i < window:
            continue
        c = close.iloc[i]
        l = lower.iloc[i]
        u = upper.iloc[i]
        if pd.isna(c) or pd.isna(l) or pd.isna(u):
            lev.iloc[i] = leverage if in_position else 0.0
            continue
        if not in_position and c > u:
            in_position = True
        elif in_position and c < l:
            in_position = False
        lev.iloc[i] = leverage if in_position else 0.0
    return lev


# --- Donchian Channel ---
def donchian_signal(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    """Donchian Channel breakout signal."""
    close = prices["spx_close"]
    high = prices["high"]
    low = prices["low"]
    lower, mid, upper = _donchian_channels(high, low, window)
    
    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    
    for i in range(len(prices)):
        if i < window:
            continue
        c = close.iloc[i]
        l = lower.iloc[i]
        u = upper.iloc[i]
        if pd.isna(c) or pd.isna(l) or pd.isna(u):
            lev.iloc[i] = leverage if in_position else 0.0
            continue
        if not in_position and c > u:
            in_position = True
        elif in_position and c < l:
            in_position = False
        lev.iloc[i] = leverage if in_position else 0.0
    return lev


# ===================================================================
# PART 5: STRATEGY UNIVERSE BUILDER
# ===================================================================

def build_strategies(prices: pd.DataFrame, asset_key: str) -> list[tuple[str, pd.Series, float]]:
    """Build list of (name, leverage_series, max_leverage) for all strategies applicable to this asset.

    Returns empty list for strategies that can't be built (e.g., insufficient data).
    """
    cfg = ASSETS[asset_key]
    max_lev = cfg["max_leverage"]
    strategies: list[tuple[str, pd.Series, float]] = []

    def add(name: str, lev: pd.Series, lev_max: float):
        strategies.append((name, lev, lev_max))

    # ===================================================================
    # A. Benchmarks
    # ===================================================================
    add("Buy & Hold 1x", pd.Series(1.0, index=prices.index), 1.0)
    if max_lev >= 2:
        add("Buy & Hold 2x", pd.Series(2.0, index=prices.index), 2.0)
    if max_lev >= 3:
        add("Buy & Hold 3x", pd.Series(3.0, index=prices.index), 3.0)

    # ===================================================================
    # B. Existing strategies (from sweep_all_assets_strategies.py)
    # ===================================================================
    
    # SMA strategies
    add("SMA20 1x/cash", sma_signal(prices, 20, 1.0), 1.0)
    if max_lev >= 2:
        add("SMA20 2x/cash", sma_signal(prices, 20, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA20 3x/cash", sma_signal(prices, 20, 3.0), 3.0)
        
    add("SMA200 1x/cash", sma_signal(prices, 200, 1.0), 1.0)
    if max_lev >= 2:
        add("SMA200 2x/cash", sma_signal(prices, 200, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA200 3x/cash", sma_signal(prices, 200, 3.0), 3.0)
        
    add("SMA50/200 Golden Cross 1x/cash", golden_cross_signal(prices, 50, 200, 1.0), 1.0)
    if max_lev >= 2:
        add("SMA50/200 Golden Cross 2x/cash", golden_cross_signal(prices, 50, 200, 2.0), 2.0)
        
    # SMA bands
    band_1x = sma_band_signal(prices, 200, 0.03, 1.0)
    add("SMA200 +-3% Band 1x/cash", band_1x, 1.0)
    
    if max_lev >= 2:
        band_2x = sma_band_signal(prices, 200, 0.03, 2.0)
        add("SMA200 +-3% Band 2x/cash", band_2x, 2.0)
        
    if max_lev >= 3:
        band_3x = sma_band_signal(prices, 200, 0.03, 3.0)
        add("SMA200 +-3% Band 3x/cash", band_3x, 3.0)
        
    # SMA bands with RSI exit
    band_rsi_1x = rsi_exit_filter_on_series(band_1x, prices, 30.0, 14)
    add("SMA200 +-3% Band + RSI>30 Exit 1x/cash", band_rsi_1x, 1.0)
    
    if max_lev >= 2:
        band_rsi_2x = rsi_exit_filter_on_series(band_2x, prices, 30.0, 14)
        add("SMA200 +-3% Band + RSI>30 Exit 2x/cash", band_rsi_2x, 2.0)
        
    if max_lev >= 3:
        band_rsi_3x = rsi_exit_filter_on_series(band_3x, prices, 30.0, 14)
        add("SMA200 +-3% Band + RSI>30 Exit 3x/cash", band_rsi_3x, 3.0)
        
    # MACD
    add("MACD 1x/cash", macd_signal(prices, 12, 26, 9, 1.0), 1.0)
    if max_lev >= 2:
        add("MACD 2x/cash", macd_signal(prices, 12, 26, 9, 2.0), 2.0)
    if max_lev >= 3:
        add("MACD 3x/cash", macd_signal(prices, 12, 26, 9, 3.0), 3.0)
        
    # BB Mean Reversion
    add("BB Mean Reversion 1x/cash", bb_signal(prices, 20, 2.0, 1.0), 1.0)
    if max_lev >= 2:
        add("BB Mean Reversion 2x/cash", bb_signal(prices, 20, 2.0, 2.0), 2.0)
        
    # Momentum
    add("Momentum 12m 1x/cash", momentum_signal(prices, 12, 1.0), 1.0)
    if max_lev >= 2:
        add("Momentum 12m 2x/cash", momentum_signal(prices, 12, 2.0), 2.0)
    if max_lev >= 3:
        add("Momentum 12m 3x/cash", momentum_signal(prices, 12, 3.0), 3.0)
        
    # Guarded strategies
    if max_lev >= 2:
        add("Guarded A5/B25 2x", guarded_leverage(prices, 20, 0.05, 0.25, 2.0), 2.0)
        add("Guarded A10/B20 2x", guarded_leverage(prices, 20, 0.10, 0.20, 2.0), 2.0)
        add("Guarded+ (200/2x/floor) 2x", guarded_plus_leverage(prices, 200, 0.10, 0.20, 2.0), 2.0)
        
    # Golden volguard
    if max_lev >= 2:
        add("Golden 2x volguard", golden_volguard_signal(prices, 2.0), 2.0)
    if max_lev >= 3:
        add("Golden 3x volguard", golden_volguard_signal(prices, 3.0), 3.0)
        
    # Monthly SMA
    if max_lev >= 2:
        add("SMA200 2x monthly", monthly_sma_signal(prices, 200, 2.0), 2.0)
        
    # SMA bands variants
    if max_lev >= 2:
        add("SMA200 2x 3% band", sma_band_signal(prices, 200, 0.03, 2.0), 2.0)
        
    # Momentum variants
    if max_lev >= 2:
        add("Mom 12m 2x/cash", momentum_signal(prices, 12, 2.0), 2.0)
        
    # Counter-cyclical strategies
    cc_max = min(3, max_lev)
    if cc_max >= 2:
        # RSI zones for counter-cyclical
        if cc_max >= 3:
            rsi_zones = [(30, 3.0), (50, 2.0), (70, 1.0), (100, 0.0)]
            vix_zones = [(30, 3.0), (20, 2.0), (0, 1.0)]
        else:
            rsi_zones = [(30, 2.0), (50, 1.0), (100, 0.0)]
            vix_zones = [(25, 2.0), (0, 1.0)]

        rsi_cc = rsi_leverage_signal(prices, rsi_zones)
        vix_cc = vix_leverage_signal(prices, vix_zones)

        # RSI Scale
        hybrid_rsi = band_trend_hybrid(prices, 200, 0.03, rsi_cc)
        hybrid_rsi_exit = rsi_exit_filter_on_series(hybrid_rsi, prices, 30.0, 14)
        hybrid_rsi_exit = hybrid_rsi_exit.clip(upper=float(cc_max))
        add(f"RSI Scale 1-{cc_max}x", hybrid_rsi_exit, float(cc_max))

        # VIX Scale
        hybrid_vix = band_trend_hybrid(prices, 200, 0.03, vix_cc)
        hybrid_vix_exit = rsi_exit_filter_on_series(hybrid_vix, prices, 30.0, 14)
        hybrid_vix_exit = hybrid_vix_exit.clip(upper=float(cc_max))
        add(f"VIX Scale 1-{cc_max}x", hybrid_vix_exit, float(cc_max))

        # Distance Scale
        dist_scale = distance_leverage_scale(band_2x if max_lev >= 2 else band_1x, prices, 200)
        dist_scale = dist_scale.clip(upper=float(cc_max))
        add(f"Distance Scale 1-{cc_max}x", dist_scale, float(cc_max))

        # DD Scale
        dd_scale = dd_based_leverage(prices, 0.20, 0.50)
        hybrid_dd = band_trend_hybrid(prices, 200, 0.03, dd_scale)
        hybrid_dd = hybrid_dd.clip(upper=float(cc_max))
        add(f"DD Scale 1-{cc_max}x", hybrid_dd, float(cc_max))

        # BB Scale
        bb_scale = bb_counter_cyclical(prices, 20, 2.0)
        hybrid_bb = band_trend_hybrid(prices, 200, 0.03, bb_scale)
        hybrid_bb = hybrid_bb.clip(upper=float(cc_max))
        add(f"BB Scale 1-{cc_max}x", hybrid_bb, float(cc_max))

        # SMA200 +-3% Band + RSI Scale/VIX Scale
        add(f"SMA200 +-3% Band + RSI Scale 1-{cc_max}x", hybrid_rsi_exit, float(cc_max))
        add(f"SMA200 +-3% Band + VIX Scale 1-{cc_max}x", hybrid_vix_exit, float(cc_max))

        # SMA200 +-3% Band + RSI>30 Exit + RSI Scale/VIX Scale
        add(f"SMA200 +-3% Band + RSI>30 Exit + RSI Scale 1-{cc_max}x", hybrid_rsi_exit, float(cc_max))
        add(f"SMA200 +-3% Band + RSI>30 Exit + VIX Scale 1-{cc_max}x", hybrid_vix_exit, float(cc_max))

    # ===================================================================
    # C. NEW strategies to test
    # ===================================================================
    
    # C1. Extended SMA periods
    for window in [50, 100]:
        add(f"SMA{window} 1x/cash", sma_signal(prices, window, 1.0), 1.0)
        if max_lev >= 2:
            add(f"SMA{window} 2x/cash", sma_signal(prices, window, 2.0), 2.0)
        if max_lev >= 3:
            add(f"SMA{window} 3x/cash", sma_signal(prices, window, 3.0), 3.0)
            
    for window in [20, 50, 100, 200]:
        add(f"EMA{window} 1x/cash", ema_signal(prices, window, 1.0), 1.0)
        if max_lev >= 2:
            add(f"EMA{window} 2x/cash", ema_signal(prices, window, 2.0), 2.0)
        if max_lev >= 3:
            add(f"EMA{window} 3x/cash", ema_signal(prices, window, 3.0), 3.0)

    # C2. Extended SMA bands
    for band_pct in [0.01, 0.02, 0.05, 0.10]:
        if max_lev >= 2:
            add(f"SMA200 +-{int(band_pct*100)}% Band 2x", sma_band_signal(prices, 200, band_pct, 2.0), 2.0)
        if max_lev >= 3:
            add(f"SMA200 +-{int(band_pct*100)}% Band 3x", sma_band_signal(prices, 200, band_pct, 3.0), 3.0)
            
    for window in [50, 100]:
        if max_lev >= 2:
            add(f"SMA{window} +-3% Band 2x", sma_band_signal(prices, window, 0.03, 2.0), 2.0)
        if max_lev >= 3:
            add(f"SMA{window} +-3% Band 3x", sma_band_signal(prices, window, 0.03, 3.0), 3.0)

    # C3. SMA Cross variants
    add("SMA20/50 Cross 2x", golden_cross_signal(prices, 20, 50, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA20/50 Cross 3x", golden_cross_signal(prices, 20, 50, 3.0), 3.0)
        
    add("SMA20/100 Cross 2x", golden_cross_signal(prices, 20, 100, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA20/100 Cross 3x", golden_cross_signal(prices, 20, 100, 3.0), 3.0)
        
    add("SMA10/50 Cross 2x", golden_cross_signal(prices, 10, 50, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA10/50 Cross 3x", golden_cross_signal(prices, 10, 50, 3.0), 3.0)
        
    if max_lev >= 3:
        add("SMA50/200 Cross 3x", golden_cross_signal(prices, 50, 200, 3.0), 3.0)
        
    # SMA50/200 Cross with band
    if max_lev >= 2:
        sma50_200_cross_2x = golden_cross_signal(prices, 50, 200, 2.0)
        add("SMA50/200 Cross +-3% Band 2x", sma_band_signal(prices, 200, 0.03, 2.0), 2.0)
    if max_lev >= 3:
        add("SMA50/200 Cross +-3% Band 3x", sma_band_signal(prices, 200, 0.03, 3.0), 3.0)

    # C4. RSI exit threshold sweep
    band_2x_base = sma_band_signal(prices, 200, 0.03, 2.0)
    if max_lev >= 2:
        for rsi_threshold in [20, 25, 35, 40]:
            band_rsi_exit = rsi_exit_filter_on_series(band_2x_base, prices, float(rsi_threshold), 14)
            add(f"SMA200 +-3% Band + RSI>{rsi_threshold} Exit 2x", band_rsi_exit, 2.0)
            
    band_3x_base = sma_band_signal(prices, 200, 0.03, 3.0)
    if max_lev >= 3:
        for rsi_threshold in [20, 25, 35, 40]:
            band_rsi_exit = rsi_exit_filter_on_series(band_3x_base, prices, float(rsi_threshold), 14)
            add(f"SMA200 +-3% Band + RSI>{rsi_threshold} Exit 3x", band_rsi_exit, 3.0)

    # C5. Multi-timeframe confluence
    if max_lev >= 3:
        add("Above SMA20 AND SMA50 AND SMA200 -> 3x", multi_sma_confluence_signal(prices, [20, 50, 200], 3.0), 3.0)
    if max_lev >= 2:
        add("Above SMA20 AND SMA200 -> 2x", multi_sma_confluence_signal(prices, [20, 200], 2.0), 2.0)
        add("Above SMA50 AND SMA200 -> 2x", multi_sma_confluence_signal(prices, [50, 200], 2.0), 2.0)
        add("Above SMA20 AND SMA50 AND SMA200 -> 2x", multi_sma_confluence_signal(prices, [20, 50, 200], 2.0), 2.0)

    # C6. Volatility-targeted leverage
    for target_vol in [0.12, 0.15, 0.20]:
        add(f"Target {int(target_vol*100)}% annualized vol 1-3x", volatility_targeting_signal(prices, target_vol), 3.0)
    add("Target 15% vol with SMA200 filter", volatility_targeting_signal(prices, 0.15, 200), 3.0)

    # C7. Guarded variants with different SMA windows
    if max_lev >= 2:
        add("Guarded A5/B25 with SMA50 lead", guarded_leverage(prices, 50, 0.05, 0.25, 2.0), 2.0)
        add("Guarded A5/B25 with SMA100 lead", guarded_leverage(prices, 100, 0.05, 0.25, 2.0), 2.0)
        add("Guarded A5/B25 with SMA200 lead", guarded_leverage(prices, 200, 0.05, 0.25, 2.0), 2.0)
        add("Guarded A10/B20 with SMA50 lead", guarded_leverage(prices, 50, 0.10, 0.20, 2.0), 2.0)
        add("Guarded A3/B15 with SMA20 lead", guarded_leverage(prices, 20, 0.03, 0.15, 2.0), 2.0)
        add("Guarded A5/B15 with SMA20 lead", guarded_leverage(prices, 20, 0.05, 0.15, 2.0), 2.0)

    # C8. Take-profit exits on Guarded
    # These would require modifications to the guarded_leverage function to add take-profit logic
    # For now, we'll skip these as they require more complex implementation

    # C9. Trailing stop strategies
    if max_lev >= 2:
        sma200_2x = sma_signal(prices, 200, 2.0)
        add("SMA200 2x + 10% trailing stop", trailing_stop_signal(prices, sma200_2x, 0.10), 2.0)
        add("SMA200 2x + 15% trailing stop", trailing_stop_signal(prices, sma200_2x, 0.15), 2.0)
        
        band_2x_ts = sma_band_signal(prices, 200, 0.03, 2.0)
        add("SMA200 +-3% Band 2x + 10% trailing stop", trailing_stop_signal(prices, band_2x_ts, 0.10), 2.0)
        add("SMA200 +-3% Band 2x + 15% trailing stop", trailing_stop_signal(prices, band_2x_ts, 0.15), 2.0)
        
    if max_lev >= 3:
        sma200_3x = sma_signal(prices, 200, 3.0)
        add("SMA200 3x + 15% trailing stop", trailing_stop_signal(prices, sma200_3x, 0.15), 3.0)

    # C10. VIX filter strategies
    sma200_2x_base = sma_signal(prices, 200, 2.0)
    if max_lev >= 2:
        for vix_threshold in [20, 25, 30]:
            # Create a signal that goes to 1x when VIX > threshold
            vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
            vix_filter = pd.Series(2.0, index=prices.index)
            vix_filter.loc[vix_series > vix_threshold] = 1.0
            # Combine with base signal (take minimum of the two)
            combined = pd.concat([sma200_2x_base, vix_filter], axis=1).min(axis=1)
            add(f"SMA200 2x + VIX>{vix_threshold} de-lever to 1x", combined, 2.0)
            
    sma200_3x_base = sma_signal(prices, 200, 3.0)
    if max_lev >= 3:
        for vix_threshold in [25, 30]:
            # Create a signal that goes to 1x when VIX > threshold
            vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
            vix_filter = pd.Series(3.0, index=prices.index)
            vix_filter.loc[vix_series > vix_threshold] = 1.0
            # Combine with base signal (take minimum of the two)
            combined = pd.concat([sma200_3x_base, vix_filter], axis=1).min(axis=1)
            add(f"SMA200 3x + VIX>{vix_threshold} de-lever to 1x", combined, 3.0)
            
    band_2x_vix = sma_band_signal(prices, 200, 0.03, 2.0)
    if max_lev >= 2:
        vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
        vix_filter = pd.Series(2.0, index=prices.index)
        vix_filter.loc[vix_series > 25] = 1.0
        combined = pd.concat([band_2x_vix, vix_filter], axis=1).min(axis=1)
        add("SMA200 +-3% Band 2x + VIX>25 de-lever to 1x", combined, 2.0)

    # C11. Momentum variants
    for months in [3, 6, 9]:
        if max_lev >= 2:
            add(f"Momentum {months}m 2x/cash", momentum_signal(prices, months, 2.0), 2.0)
    if max_lev >= 3:
        add("Momentum 12m 3x/cash", momentum_signal(prices, 12, 3.0), 3.0)
        
    # Dual momentum would require NDX data for SPX and vice versa, so skipping for now

    # C12. Keltner Channel breakout
    if max_lev >= 2:
        add("Keltner(20, 2ATR) breakout 2x", keltner_signal(prices, 20, 2.0, 2.0), 2.0)
        add("Keltner(20, 1.5ATR) breakout 2x", keltner_signal(prices, 20, 1.5, 2.0), 2.0)

    # C13. Donchian Channel breakout
    if max_lev >= 2:
        add("Donchian(20) breakout 2x", donchian_signal(prices, 20, 2.0), 2.0)
        add("Donchian(55) breakout 2x", donchian_signal(prices, 55, 2.0), 2.0)
    if max_lev >= 3:
        add("Donchian(20) breakout 3x", donchian_signal(prices, 20, 3.0), 3.0)

    # C14. MACD variants
    if max_lev >= 2:
        add("MACD 2x/cash", macd_signal(prices, 12, 26, 9, 2.0), 2.0)
        # Custom MACD parameters
        add("MACD 5/35/5 2x", macd_signal(prices, 5, 35, 5, 2.0), 2.0)
        add("MACD 8/17/9 2x", macd_signal(prices, 8, 17, 9, 2.0), 2.0)
    if max_lev >= 3:
        add("MACD 3x/cash", macd_signal(prices, 12, 26, 9, 3.0), 3.0)
        add("MACD + SMA200 2x", macd_signal(prices, 12, 26, 9, 2.0), 2.0)  # This needs refinement

    # C15. RSI strategies
    close = prices["spx_close"]
    rsi_val = _rsi(close, 14)
    if max_lev >= 2:
        # RSI 30/70
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(rsi_val < 30)] = 2.0
        lev.loc[(rsi_val > 70)] = 0.0
        add("RSI 30/70 2x", lev, 2.0)
        
        # RSI 40/60
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(rsi_val < 40)] = 2.0
        lev.loc[(rsi_val > 60)] = 0.0
        add("RSI 40/60 2x", lev, 2.0)
        
        # RSI 25/75
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(rsi_val < 25)] = 2.0
        lev.loc[(rsi_val > 75)] = 0.0
        add("RSI 25/75 2x", lev, 2.0)
        
        # RSI momentum
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(rsi_val > 50)] = 2.0
        lev.loc[(rsi_val < 45)] = 0.0
        add("RSI momentum 2x", lev, 2.0)

    # C16. Combined filters
    sma200 = _sma(close, 200)
    if max_lev >= 2:
        # SMA200 + RSI>50
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(close > sma200) & (rsi_val > 50)] = 2.0
        add("SMA200 + RSI>50 2x", lev, 2.0)
        
        # SMA200 + MACD bull cross
        macd_line, macd_sig, _ = _macd(close, 12, 26, 9)
        bull_cross = (macd_line > macd_sig) & (macd_line.shift(1) <= macd_sig.shift(1))
        lev = pd.Series(0.0, index=prices.index)
        lev.loc[(close > sma200) & bull_cross] = 2.0
        add("SMA200 + MACD bull cross 2x", lev, 2.0)
        
        # SMA200 +-3% Band + ADX>25
        if "high" in prices.columns and "low" in prices.columns:
            adx_val = _adx(prices["high"], prices["low"], close, 14)
            band_2x_adx = sma_band_signal(prices, 200, 0.03, 2.0)
            filtered = band_2x_adx.copy()
            filtered.loc[adx_val <= 25] = 0.0  # Set to cash when ADX <= 25
            add("SMA200 +-3% Band + ADX>25 2x", filtered, 2.0)
        
        # SMA200 +-3% Band + low VIX (<20)
        vix_series = prices["vix"].ffill().fillna(DEFAULT_VIX)
        band_2x_vix_filter = band_2x_base.copy()
        band_2x_vix_filter.loc[vix_series >= 20] = 0.0  # Set to cash when VIX >= 20
        add("SMA200 +-3% Band + low VIX (<20) 2x", band_2x_vix_filter, 2.0)

    # C17. Guarded + Counter-cyclical hybrid
    # These would require modifications to combine guarded entry with counter-cyclical leverage
    # For now, we'll skip these as they require more complex implementation

    # C18. Seasonality (simple)
    add("Sell in May (May-Oct -> cash, Nov-Apr -> 1x)", seasonality_signal(prices, 1.0, [11, 12, 1, 2, 3, 4]), 1.0)
    if max_lev >= 2:
        add("Sell in May 2x (May-Oct -> cash, Nov-Apr -> 2x)", seasonality_signal(prices, 2.0, [11, 12, 1, 2, 3, 4]), 2.0)

    # C19. Profit-locked Guarded with trailing stop
    # Would require modifications to guarded strategy, skipping for now

    # C20. Dual-band asymmetric
    # Custom implementation needed, skipping for now

    # ===================================================================
    # C21. Water/Octane-targeted lever-up families.
    #      1x floor; step to 2x ONLY in calm / shallow-drawdown / near-high /
    #      strong-momentum regimes. Distinct from the VIX strategies above:
    #      those DE-lever (2x->1x) when VIX is high; these LEVER UP from a 1x
    #      floor only when conditions are benign. Plus defensive 1x/cash Water
    #      candidates (tighter/wider SMA200 bands, slow golden cross, dual-SMA).
    # ===================================================================
    _vix_s = prices["vix"].ffill().fillna(DEFAULT_VIX)
    _sma50 = _sma(close, 50)
    _sma100 = _sma(close, 100)
    _peak = close.cummax()
    _idxdd = close / _peak - 1.0
    _gc_in = golden_cross_signal(prices, 50, 200, 1.0) > 0
    _above200 = close > sma200
    _above100 = close > _sma100
    _stacked = (_sma50 > _sma100) & (_sma100 > sma200)
    _mom6 = close / close.shift(126) - 1.0
    _mom12 = close / close.shift(252) - 1.0

    def _floor1_gate2(in_trend, gate):
        _a = np.asarray(in_trend, dtype=bool)
        _g = np.asarray(gate, dtype=bool)
        return pd.Series(np.where(_a & _g, 2.0, np.where(_a, 1.0, 0.0)),
                         index=prices.index).astype(float)

    # Defensive 1x/cash Water candidates
    for _bp in (0.01, 0.02, 0.05):
        add(f"SMA200 +-{int(_bp*100)}% Band 1x/cash", sma_band_signal(prices, 200, _bp, 1.0), 1.0)
    add("SMA100/200 Golden Cross 1x/cash", golden_cross_signal(prices, 100, 200, 1.0), 1.0)
    add("Above SMA50 AND SMA200 -> 1x", multi_sma_confluence_signal(prices, [50, 200], 1.0), 1.0)
    add("Above SMA100 AND SMA200 -> 1x", multi_sma_confluence_signal(prices, [100, 200], 1.0), 1.0)

    if max_lev >= 2:
        _bases = [("GC 50/200", _gc_in.values), ("SMA200", _above200.values), ("SMA100", _above100.values)]
        # N1 VIX-gated lever-up
        for _bn, _bm in _bases:
            for _vth in (15, 18, 20, 22):
                add(f"{_bn} 1x; +2x when VIX<{_vth}", _floor1_gate2(_bm, _vix_s.values < _vth), 2.0)
        # N2 index-drawdown-gated lever-up
        for _bn, _bm in [("GC 50/200", _gc_in.values), ("SMA200", _above200.values)]:
            for _dth in (8, 10, 12, 15):
                add(f"{_bn} 1x; +2x when idxDD>-{_dth}%", _floor1_gate2(_bm, _idxdd.values > -_dth / 100.0), 2.0)
        # N3 near-high-gated lever-up
        for _bn, _bm in [("SMA200", _above200.values), ("GC 50/200", _gc_in.values)]:
            for _nh in (3, 5, 7, 10):
                add(f"{_bn} 1x; +2x when within {_nh}% of high",
                    _floor1_gate2(_bm, close.values >= (1 - _nh / 100.0) * _peak.values), 2.0)
        # N4 stacked-SMA trend lever-up with calm gate
        add("SMA200 1x; +2x when 50>100>200 & idxDD>-10%",
            _floor1_gate2(_above200.values, _stacked.values & (_idxdd.values > -0.10)), 2.0)
        add("SMA200 1x; +2x when 50>100>200 & VIX<20",
            _floor1_gate2(_above200.values, _stacked.values & (_vix_s.values < 20)), 2.0)
        add("SMA200 1x; +2x when 50>100>200 & within 5% of high",
            _floor1_gate2(_above200.values, _stacked.values & (close.values >= 0.95 * _peak.values)), 2.0)
        # N5 momentum-gated lever-up
        add("SMA200 1x; +2x when 6m&12m mom>0",
            _floor1_gate2(_above200.values, (_mom6.values > 0) & (_mom12.values > 0)), 2.0)
        add("SMA200 1x; +2x when 6m&12m mom>0 & VIX<22",
            _floor1_gate2(_above200.values, (_mom6.values > 0) & (_mom12.values > 0) & (_vix_s.values < 22)), 2.0)
        # N6 combined VIX & DD gate
        add("GC 50/200 1x; +2x when VIX<20 & idxDD>-12%",
            _floor1_gate2(_gc_in.values, (_vix_s.values < 20) & (_idxdd.values > -0.12)), 2.0)
        add("SMA200 1x; +2x when VIX<18 & idxDD>-10%",
            _floor1_gate2(_above200.values, (_vix_s.values < 18) & (_idxdd.values > -0.10)), 2.0)

    return strategies


# ===================================================================
# PART 6: BACKTEST EXECUTION
# ===================================================================

def make_engine(trading_cost: float) -> PortfolioEngine:
    """Standard engine: no DD protection, ETP mode, honest execution, per-asset trading cost."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=trading_cost,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=SIGNAL_DELAY_DAYS,
    )


def run_one_backtest(prices: pd.DataFrame, etp_panel: pd.DataFrame,
                     name: str, leverage: pd.Series, trading_cost: float) -> dict[str, Any]:
    """Run a single strategy through PortfolioEngine and return metrics dict."""
    engine = make_engine(trading_cost)
    result = engine.run(prices, leverage, name=name, etp_returns=etp_panel)

    # Average risk-free rate over the period
    avg_tbill = float(prices["tbill_rate"].mean()) if "tbill_rate" in prices.columns else 0.0

    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        risk_free=avg_tbill,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )

    # Compute additional metrics
    lev_applied = result.leverage.astype(float).fillna(0.0)
    n = len(lev_applied)
    pct_cash = 100.0 * float((lev_applied <= 0.0).sum()) / n if n > 0 else 0.0
    invested = lev_applied[lev_applied > 0.0]
    avg_lev = float(invested.mean()) if len(invested) > 0 else 0.0

    years = (prices.index[-1] - prices.index[0]).days / 365.25
    trades_per_year = result.rebalance_count / years if years > 0 else 0.0

    return {
        "strategy": name,
        "cagr": stats.get("cagr", float("nan")),
        "volatility": stats.get("volatility", float("nan")),
        "sharpe": stats.get("sharpe", float("nan")),
        "sortino": stats.get("sortino", float("nan")),
        "calmar": stats.get("calmar", float("nan")),
        "max_drawdown": stats.get("max_drawdown", float("nan")),
        "end_value": float(result.equity.iloc[-1]) if len(result.equity) > 0 else float("nan"),
        "start_date": prices.index[0],
        "end_date": prices.index[-1],
        "years": years,
        "pct_cash_time": pct_cash,
        "trades_per_year": trades_per_year,
        "total_trades": result.rebalance_count,
        "avg_leverage": avg_lev,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
    }


# ===================================================================
# PART 7: MAIN SWEEP
# ===================================================================

def main() -> int:
    print("=" * 80)
    print("COMPREHENSIVE STRATEGY SWEEP - S&P 500 AND NASDAQ 100")
    print("=" * 80)

    # -------------------------------------------------------------------
    # 1. Download global T-bill and VIX data
    # -------------------------------------------------------------------
    print("\n[1/3] Downloading global T-bill (^IRX) and VIX (^VIX) data ...")
    try:
        tbill_global, vix_global = _download_tbill_vix()
        print(f"  T-bill: {len(tbill_global)} rows, VIX: {len(vix_global)} rows")
    except Exception as e:
        print(f"FATAL: Could not download T-bill/VIX: {e}")
        return 1

    # -------------------------------------------------------------------
    # 2. Process each asset
    # -------------------------------------------------------------------
    all_results: list[dict[str, Any]] = []
    asset_keys = ["spx", "ndx"]  # Only SPX and NDX for this sweep

    for asset_idx, asset_key in enumerate(asset_keys):
        cfg = ASSETS[asset_key]
        print(f"\n{'=' * 80}")
        print(f"[Asset {asset_idx + 1}/{len(asset_keys)}] {cfg['label']} ({asset_key})")
        print(f"  Index: {cfg['index']}, Max Leverage: {cfg['max_leverage']}x")
        print(f"{'=' * 80}")

        # --- Load data ---
        print("  Loading asset data ...")
        try:
            asset_data = load_asset_data(asset_key, tbill_global, vix_global)
        except Exception as e:
            print(f"  ERROR loading data for {asset_key}: {e}")
            traceback.print_exc()
            continue

        prices = asset_data["prices"]
        etp_closes = asset_data["etp_closes"]
        print(f"  Prices: {len(prices)} trading days, {prices.index[0].date()} to {prices.index[-1].date()}")
        etp_available = [k for k in etp_closes if etp_closes[k] is not None and len(etp_closes[k]) > 0]
        print(f"  Real ETPs available: {etp_available if etp_available else '(none - all synthetic)'}")

        if len(prices) < 200:
            print(f"  SKIPPING {asset_key}: insufficient data ({len(prices)} rows < 200)")
            continue

        # --- Build ETP return panel ---
        print("  Building ETP return panel ...")
        try:
            etp_panel = build_asset_etp_panel(prices, etp_closes, cfg)
        except Exception as e:
            print(f"  ERROR building ETP panel for {asset_key}: {e}")
            traceback.print_exc()
            continue

        # --- Build strategies ---
        print("  Building strategy universe ...")
        try:
            strategies = build_strategies(prices, asset_key)
        except Exception as e:
            print(f"  ERROR building strategies for {asset_key}: {e}")
            traceback.print_exc()
            continue
        print(f"  -> {len(strategies)} strategies to test")

        # --- Run all strategies ---
        asset_results: list[dict[str, Any]] = []
        for i, (name, leverage, lev_max) in enumerate(strategies):
            pct_done = (i + 1) / len(strategies) * 100
            print(f"    [{i+1:3d}/{len(strategies)} {pct_done:5.1f}%] {name} ...", end=" ", flush=True)
            try:
                row = run_one_backtest(prices, etp_panel, name, leverage, cfg["trading_cost"])
                row["asset"] = asset_key
                row["asset_label"] = cfg["label"]
                row["leverage_max"] = lev_max
                row["trading_cost"] = cfg["trading_cost"]
                asset_results.append(row)

                cagr_s = f"{row['cagr']*100:.2f}%" if not np.isnan(row['cagr']) else "N/A"
                dd_s = f"{row['max_drawdown']*100:.1f}%" if not np.isnan(row['max_drawdown']) else "N/A"
                sh_s = f"{row['sharpe']:.3f}" if not np.isnan(row['sharpe']) else "N/A"
                print(f"CAGR={cagr_s}  MaxDD={dd_s}  Sharpe={sh_s}  Trades={row['total_trades']}")
            except Exception as e:
                print(f"FAILED: {e}")
                traceback.print_exc()

        # --- Compute Beat_BH metrics ---
        bh1_row = next((r for r in asset_results if r["strategy"] == "Buy & Hold 1x"), None)
        if bh1_row:
            for row in asset_results:
                row["beat_bh_sharpe"] = 1 if (not np.isnan(row.get("sharpe", float("nan")))
                    and not np.isnan(bh1_row.get("sharpe", float("nan")))
                    and row["sharpe"] > bh1_row["sharpe"]) else 0
                row["beat_bh_calmar"] = 1 if (not np.isnan(row.get("calmar", float("nan")))
                    and not np.isnan(bh1_row.get("calmar", float("nan")))
                    and row["calmar"] > bh1_row["calmar"]) else 0
                row["beat_bh_dd"] = 1 if (not np.isnan(row.get("max_drawdown", float("nan")))
                    and not np.isnan(bh1_row.get("max_drawdown", float("nan")))
                    and row["max_drawdown"] > bh1_row["max_drawdown"]) else 0
                row["beat_bh_cagr"] = 1 if (not np.isnan(row.get("cagr", float("nan")))
                    and not np.isnan(bh1_row.get("cagr", float("nan")))
                    and row["cagr"] > bh1_row["cagr"]) else 0
        else:
            for row in asset_results:
                row["beat_bh_sharpe"] = 0
                row["beat_bh_calmar"] = 0
                row["beat_bh_dd"] = 0
                row["beat_bh_cagr"] = 0

        all_results.extend(asset_results)

    # -------------------------------------------------------------------
    # 3. Write combined CSV
    # -------------------------------------------------------------------
    if all_results:
        csv_path = OUTPUT_DIR / "spx_ndx_comprehensive.csv"
        _write_results_csv(all_results, csv_path, include_asset=True)
        print(f"\n{'=' * 80}")
        print(f"Combined CSV written: {csv_path}")
        print(f"Total strategies tested: {len(all_results)}")
        print(f"{'=' * 80}")
        
        # Print Water and Octane strategies
        print("\nWATER AND OCTANE STRATEGIES:")
        print("-" * 50)
        
        # Group by asset
        for asset_key in ["spx", "ndx"]:
            asset_results = [r for r in all_results if r["asset"] == asset_key]
            if not asset_results:
                continue
                
            print(f"\n{ASSETS[asset_key]['label']} ({asset_key.upper()}):")
            
            # Find B&H 1x for comparison
            bh1_row = next((r for r in asset_results if r["strategy"] == "Buy & Hold 1x"), None)
            if not bh1_row:
                print("  No B&H 1x baseline found for comparison")
                continue
                
            # Water strategies (improve on B&H 1x on at least one of CAGR or MaxDD, without sacrificing any metric)
            water_strategies = []
            for row in asset_results:
                if row["strategy"] == "Buy & Hold 1x":
                    continue
                    
                # Check if it's Water
                improves_cagr = not np.isnan(row.get("cagr", float("nan"))) and not np.isnan(bh1_row.get("cagr", float("nan"))) and row["cagr"] >= bh1_row["cagr"]
                improves_dd = not np.isnan(row.get("max_drawdown", float("nan"))) and not np.isnan(bh1_row.get("max_drawdown", float("nan"))) and row["max_drawdown"] >= bh1_row["max_drawdown"]  # Note: MaxDD is negative, so >= means less negative (better)
                not_worse_sharpe = not np.isnan(row.get("sharpe", float("nan"))) and not np.isnan(bh1_row.get("sharpe", float("nan"))) and row["sharpe"] >= bh1_row["sharpe"]
                not_worse_calmar = not np.isnan(row.get("calmar", float("nan"))) and not np.isnan(bh1_row.get("calmar", float("nan"))) and row["calmar"] >= bh1_row["calmar"]
                not_worse_sortino = not np.isnan(row.get("sortino", float("nan"))) and not np.isnan(bh1_row.get("sortino", float("nan"))) and row["sortino"] >= bh1_row["sortino"]
                not_worse_vol = not np.isnan(row.get("volatility", float("nan"))) and not np.isnan(bh1_row.get("volatility", float("nan"))) and row["volatility"] <= bh1_row["volatility"]
                
                # At least one of {CAGR > B&H 1x, MaxDD > B&H 1x} strictly better
                strictly_better_cagr = not np.isnan(row.get("cagr", float("nan"))) and not np.isnan(bh1_row.get("cagr", float("nan"))) and row["cagr"] > bh1_row["cagr"]
                strictly_better_dd = not np.isnan(row.get("max_drawdown", float("nan"))) and not np.isnan(bh1_row.get("max_drawdown", float("nan"))) and row["max_drawdown"] > bh1_row["max_drawdown"]  # Note: MaxDD is negative, so > means less negative (better)
                
                if (improves_cagr or improves_dd) and not_worse_sharpe and not_worse_calmar and not_worse_sortino and not_worse_vol and (strictly_better_cagr or strictly_better_dd):
                    water_strategies.append(row)
            
            # Octane strategies (CAGR > B&H 1x CAGR AND Calmar > B&H 1x Calmar AND MaxDD >= -45% AND Trades_Per_Year <= 30)
            octane_strategies = []
            for row in asset_results:
                if row["strategy"] == "Buy & Hold 1x":
                    continue
                    
                # Check if it's Octane
                better_cagr = not np.isnan(row.get("cagr", float("nan"))) and not np.isnan(bh1_row.get("cagr", float("nan"))) and row["cagr"] > bh1_row["cagr"]
                better_calmar = not np.isnan(row.get("calmar", float("nan"))) and not np.isnan(bh1_row.get("calmar", float("nan"))) and row["calmar"] > bh1_row["calmar"]
                maxdd_limit = not np.isnan(row.get("max_drawdown", float("nan"))) and row["max_drawdown"] >= -0.45  # MaxDD is negative
                trades_limit = row.get("trades_per_year", 0) <= 30.0
                
                if better_cagr and better_calmar and maxdd_limit and trades_limit:
                    octane_strategies.append(row)
            
            # Print Water strategies
            if water_strategies:
                print("  WATER:")
                # Sort by Sharpe ratio
                water_strategies.sort(key=lambda x: x.get("sharpe", 0) if not np.isnan(x.get("sharpe", float("nan"))) else 0, reverse=True)
                for row in water_strategies[:10]:  # Top 10
                    cagr = f"{row['cagr']*100:.2f}%" if not np.isnan(row.get('cagr', float('nan'))) else "N/A"
                    sharpe = f"{row['sharpe']:.3f}" if not np.isnan(row.get('sharpe', float('nan'))) else "N/A"
                    maxdd = f"{row['max_drawdown']*100:.1f}%" if not np.isnan(row.get('max_drawdown', float('nan'))) else "N/A"
                    print(f"    {row['strategy']:<50} Sharpe={sharpe:<6} CAGR={cagr:<8} MaxDD={maxdd}")
            
            # Print Octane strategies
            if octane_strategies:
                print("  OCTANE:")
                # Sort by Calmar ratio
                octane_strategies.sort(key=lambda x: x.get("calmar", 0) if not np.isnan(x.get("calmar", float('nan'))) else 0, reverse=True)
                for row in octane_strategies[:10]:  # Top 10
                    cagr = f"{row['cagr']*100:.2f}%" if not np.isnan(row.get('cagr', float('nan'))) else "N/A"
                    calmar = f"{row['calmar']:.3f}" if not np.isnan(row.get('calmar', float('nan'))) else "N/A"
                    maxdd = f"{row['max_drawdown']*100:.1f}%" if not np.isnan(row.get('max_drawdown', float('nan'))) else "N/A"
                    trades = f"{row['trades_per_year']:.1f}" if not np.isnan(row.get('trades_per_year', float('nan'))) else "N/A"
                    print(f"    {row['strategy']:<50} Calmar={calmar:<6} CAGR={cagr:<8} MaxDD={maxdd:<8} Trades/yr={trades}")
            
            if not water_strategies and not octane_strategies:
                print("  No Water or Octane strategies found")
    else:
        print("\nNo results generated. Check errors above.")
        return 1

    return 0


def _write_results_csv(results: list[dict[str, Any]], path: Path, include_asset: bool = False):
    """Write results to CSV with standardized columns."""
    fieldnames = [
        "Strategy", "Leverage_Max", "CAGR_pct", "Vol_pct", "Sharpe", "Sortino", "Calmar",
        "MaxDD_pct", "End_Value", "Start_Date", "End_Date", "Years",
        "Pct_Cash_Time", "Trades_Per_Year", "Total_Trades", "Avg_Leverage",
        "Beat_BH_Sharpe", "Beat_BH_Calmar", "Beat_BH_DD", "Beat_BH_CAGR",
        "Trading_Cost_Pct",
    ]
    if include_asset:
        fieldnames = ["Asset"] + fieldnames

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row_out: dict[str, Any] = {}
            if include_asset:
                row_out["Asset"] = r.get("asset", "")
            row_out["Strategy"] = r.get("strategy", "")
            row_out["Leverage_Max"] = r.get("leverage_max", "")
            row_out["CAGR_pct"] = _pct(r.get("cagr"))
            row_out["Vol_pct"] = _pct(r.get("volatility"))
            row_out["Sharpe"] = _fmt(r.get("sharpe"), 3)
            row_out["Sortino"] = _fmt(r.get("sortino"), 3)
            row_out["Calmar"] = _fmt(r.get("calmar"), 3)
            row_out["MaxDD_pct"] = _pct(r.get("max_drawdown"))
            row_out["End_Value"] = _fmt(r.get("end_value"), 2)
            row_out["Start_Date"] = str(r.get("start_date", ""))[:10] if r.get("start_date") is not None else ""
            row_out["End_Date"] = str(r.get("end_date", ""))[:10] if r.get("end_date") is not None else ""
            row_out["Years"] = _fmt(r.get("years"), 2)
            row_out["Pct_Cash_Time"] = _fmt(r.get("pct_cash_time"), 1)
            row_out["Trades_Per_Year"] = _fmt(r.get("trades_per_year"), 1)
            row_out["Total_Trades"] = r.get("total_trades", "")
            row_out["Avg_Leverage"] = _fmt(r.get("avg_leverage"), 2)
            row_out["Beat_BH_Sharpe"] = r.get("beat_bh_sharpe", 0)
            row_out["Beat_BH_Calmar"] = r.get("beat_bh_calmar", 0)
            row_out["Beat_BH_DD"] = r.get("beat_bh_dd", 0)
            row_out["Beat_BH_CAGR"] = r.get("beat_bh_cagr", 0)
            row_out["Trading_Cost_Pct"] = _pct(r.get("trading_cost", 0.0))
            writer.writerow(row_out)


def _pct(val: Any) -> str:
    """Format as percentage string or empty."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return f"{float(val) * 100:.2f}"


def _fmt(val: Any, decimals: int = 2) -> str:
    """Format float or return empty for NaN."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return f"{float(val):.{decimals}f}"


# ===================================================================
# ENTRY POINT
# ===================================================================

if __name__ == "__main__":
    sys.exit(main())