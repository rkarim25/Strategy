"""Technical indicators for systematic S&P 500 strategies."""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return lower, mid, upper


def spx_drawdown_from_peak(close: pd.Series) -> pd.Series:
    """Index drawdown from running peak (negative values)."""
    peak = close.cummax()
    return (close - peak) / peak


def enrich_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Attach commonly used indicator columns to price data."""
    close = prices["spx_close"]
    df = prices.copy()

    df["sma_50"] = sma(close, 50)
    df["sma_200"] = sma(close, 200)
    df["rsi_14"] = rsi(close, 14)
    macd_line, macd_sig, macd_hist = macd(close)
    df["macd"] = macd_line
    df["macd_signal"] = macd_sig
    df["macd_hist"] = macd_hist
    bb_low, bb_mid, bb_up = bollinger_bands(close)
    df["bb_lower"] = bb_low
    df["bb_mid"] = bb_mid
    df["bb_upper"] = bb_up
    df["spx_dd"] = spx_drawdown_from_peak(close)

    return df
