"""Market data acquisition and preprocessing for S&P 500 backtests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

SPX_TICKER = "^GSPC"
TBILL_TICKER = "^IRX"
VIX_TICKER = "^VIX"
YEARS_OF_HISTORY = 30


def download_market_data(
    years: int = YEARS_OF_HISTORY,
    end: datetime | None = None,
) -> pd.DataFrame:
    """
    Download daily SPX and 13-week T-Bill data, align on calendar, forward-fill gaps.

    Returns a DataFrame with columns: spx_close, tbill_rate (annualized, decimal).
    """
    end = end or datetime.today()
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
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()
        prices.columns = [SPX_TICKER]

    prices = prices.rename(
        columns={
            SPX_TICKER: "spx_close",
            TBILL_TICKER: "tbill_rate",
            VIX_TICKER: "vix",
        }
    )

    # ^IRX is quoted as annualized yield in percent (e.g. 5.2 = 5.2%)
    if "tbill_rate" in prices.columns:
        prices["tbill_rate"] = prices["tbill_rate"] / 100.0

    prices = prices.sort_index()
    prices = prices.ffill().dropna(how="any")

    return prices


def load_backtest_data(years: int = YEARS_OF_HISTORY) -> pd.DataFrame:
    """Convenience wrapper used by the backtest engine and dashboard."""
    return download_market_data(years=years)
