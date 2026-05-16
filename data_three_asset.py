"""Three-asset panel: S&P 500, gold (futures proxy), 13-week T-Bill yield."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

SPX_TICKER = "^GSPC"
TBILL_TICKER = "^IRX"
# Continuous gold futures — longer history than GLD ETF (~2004)
GOLD_TICKER = "GC=F"
YEARS_OF_HISTORY = 30


def download_three_asset_panel(
    years: int = YEARS_OF_HISTORY,
    end: datetime | None = None,
) -> pd.DataFrame:
    """
    Daily aligned panel: spx_close, gold_close, tbill_rate (annual decimal).

    Cash sleeve earns overnight TBill approximation: tbill_rate / 252 per day.
    """
    end = end or datetime.today()
    start = end - timedelta(days=int(years * 365.25))

    raw = yf.download(
        [SPX_TICKER, GOLD_TICKER, TBILL_TICKER],
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

    rename_map = {
        SPX_TICKER: "spx_close",
        GOLD_TICKER: "gold_close",
        TBILL_TICKER: "tbill_rate",
    }
    prices = prices.rename(columns={k: v for k, v in rename_map.items() if k in prices.columns})

    if "tbill_rate" in prices.columns:
        prices["tbill_rate"] = prices["tbill_rate"] / 100.0

    prices = prices.sort_index().ffill().dropna(how="any")
    return prices


def load_three_asset_data(years: int = YEARS_OF_HISTORY) -> pd.DataFrame:
    return download_three_asset_panel(years=years)
