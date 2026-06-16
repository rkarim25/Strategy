"""
Realistic 2x/3x modelling via listed daily-reset ETP returns (UK/II tickers).

Signals still use the index close in ``spx_close``; P&L at 1x/2x/3x uses UCITS/ETP
daily total returns when Yahoo history exists, otherwise a daily-reset synthetic
that adds volatility drag and TER on top of borrow (closer to levered ETPs than
``L * index_return - funding`` alone).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from engine import TRADING_DAYS, VIX_STRESS_THRESHOLD, funding_cost_daily

TBILL_TICKER = "^IRX"
VIX_TICKER = "^VIX"

MC_ETP_METHOD = (
    "Block-bootstrap of joint historical segments (index return, ret_0–ret_3, T-bill); "
    "listed ETP where available with VIX-linked synthetic daily-reset pre-inception."
)

# Approximate OCF drag on NAV (decimal, annual) when synthesising pre-ETP history
TER_ANNUAL = {1: 0.0030, 2: 0.0060, 3: 0.0090}
# Clip corrupt Yahoo ticks; above these use synthetic daily-reset for that day
MAX_ETP_DAILY_ABS = {1: 0.15, 2: 0.28, 3: 0.42}


@dataclass(frozen=True)
class EtpBundle:
    """Yahoo symbols for implementable 1x / 2x / 3x products."""

    name: str
    etf_1x: str
    etf_2x: str
    etf_3x: str
    etf_1x_fallback: str | None = None  # longer history before primary 1x lists


# Same-calendar US-listed leveraged ETPs: the signal index (^GSPC / ^NDX) and the P&L ETP
# share a trading calendar. The UCITS XS2D.L / 3USL.L (LSE) and LQQ.PA / LQQ3.L (Paris)
# were dropped from the daily-timed backtest because their Yahoo daily returns are
# calendar-offset vs the US index (corr ~0.57, ratio ~1.2x): long-run totals match but a
# daily-timed strategy gets badly inflated. UK / II investors implement the same
# daily-leveraged exposure via XS2D.L (2x) / 3USL.L (3x) and LQQ.PA (2x) / LQQ3.L (3x).
SPX_ETP = EtpBundle(
    name="S&P 500",
    etf_1x="SPY",
    etf_1x_fallback=None,
    etf_2x="SSO",
    etf_3x="UPRO",
)

NDX_ETP = EtpBundle(
    name="Nasdaq 100",
    etf_1x="QQQ",
    etf_1x_fallback=None,
    etf_2x="QLD",
    etf_3x="TQQQ",
)


def _download_closes(
    tickers: list[str],
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    uniq = list(dict.fromkeys(tickers))
    raw = yf.download(
        uniq,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"No data for {uniq}")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": uniq[0]})

    return closes.sort_index().ffill()


def _spliced_1x_close(closes: pd.DataFrame, bundle: EtpBundle) -> pd.Series:
    primary = closes[bundle.etf_1x].astype(float)
    if bundle.etf_1x_fallback and bundle.etf_1x_fallback in closes.columns:
        fallback = closes[bundle.etf_1x_fallback].astype(float)
        first_primary = primary.first_valid_index()
        if first_primary is not None:
            out = fallback.copy()
            out.loc[first_primary:] = primary.loc[first_primary:]
            return out.ffill()
    return primary


def synthetic_daily_reset_return(
    index_return: float,
    leverage: float,
    tbill_rate: float,
    *,
    vix: float | None = None,
) -> float:
    """
    Approximate daily-reset levered ETP before listed history exists.

    Daily return = leverage * index_return - VIX-linked borrow - TER. Compounding these
    daily returns already produces the volatility drag/boost, so NO separate vol-drag term
    is subtracted: doing so double-counts it and makes the model far too pessimistic. A
    clean daily-reset 2x compound matches listed SSO/XS2D (~19x over 2012-26); the corrected
    model tracks real same-calendar ETPs within ~2%/yr.
    """
    if leverage <= 0.0:
        return tbill_rate / TRADING_DAYS
    if leverage <= 1.0:
        ter = TER_ANNUAL[1] / TRADING_DAYS
        return index_return - ter

    borrow = funding_cost_daily(leverage, tbill_rate, vix=vix)
    tier = 3 if leverage >= 2.5 else 2
    ter = TER_ANNUAL[tier] / TRADING_DAYS
    return leverage * index_return - borrow - ter


def _tier_column(leverage: float) -> str:
    if leverage <= 0.0:
        return "ret_0"
    if leverage < 1.5:
        return "ret_1"
    if leverage < 2.5:
        return "ret_2"
    return "ret_3"


def daily_return_for_leverage(
    leverage: float,
    index_return: float,
    tbill_rate: float,
    etp_row: pd.Series | None,
) -> float:
    """Portfolio daily return for target leverage using ETP panel when provided."""
    if leverage <= 0.0:
        return tbill_rate / TRADING_DAYS

    if etp_row is not None:
        col = _tier_column(leverage)
        etp_r = etp_row.get(col)
        if etp_r is not None and not pd.isna(etp_r):
            return float(etp_r)

    vix = None
    if etp_row is not None:
        raw_vix = etp_row.get("vix")
        if raw_vix is not None and not pd.isna(raw_vix):
            vix = float(raw_vix)

    return synthetic_daily_reset_return(index_return, leverage, tbill_rate, vix=vix)


@lru_cache(maxsize=16)
def _download_closes_cached(
    tickers_key: str,
    start_s: str,
    end_s: str,
) -> pd.DataFrame:
    tickers = tickers_key.split("|")
    start = datetime.fromisoformat(start_s)
    end = datetime.fromisoformat(end_s)
    return _download_closes(tickers, start, end)


def build_etp_return_panel(
    prices: pd.DataFrame,
    bundle: EtpBundle,
) -> pd.DataFrame:
    """
    Build daily return columns aligned to ``prices.index``.

    Columns: ret_0 (T-bill), ret_1, ret_2, ret_3, and flags synthetic_2, synthetic_3.
    """
    index = prices.index
    if len(index) == 0:
        raise ValueError("empty prices index")

    start = index[0].to_pydatetime() if hasattr(index[0], "to_pydatetime") else index[0]
    end = index[-1].to_pydatetime() if hasattr(index[-1], "to_pydatetime") else index[-1]
    tickers = [bundle.etf_1x, bundle.etf_2x, bundle.etf_3x, TBILL_TICKER, VIX_TICKER]
    if bundle.etf_1x_fallback:
        tickers.append(bundle.etf_1x_fallback)

    tickers_key = "|".join(tickers)
    closes = _download_closes_cached(tickers_key, start.isoformat(), end.isoformat())
    tbill = closes[TBILL_TICKER].astype(float) / 100.0
    idx_ret = prices["spx_close"].astype(float).pct_change()

    close_1x = _spliced_1x_close(closes, bundle).reindex(index).ffill()
    close_2x = closes[bundle.etf_2x].astype(float).reindex(index).ffill()
    close_3x = closes[bundle.etf_3x].astype(float).reindex(index).ffill()
    tbill_a = tbill.reindex(index).ffill()
    if VIX_TICKER in closes.columns:
        vix_a = closes[VIX_TICKER].astype(float).reindex(index).ffill()
    else:
        vix_a = pd.Series(VIX_STRESS_THRESHOLD, index=index)

    ret_1 = close_1x.pct_change()
    ret_2 = close_2x.pct_change()
    ret_3 = close_3x.pct_change()
    ret_0 = tbill_a / TRADING_DAYS

    synthetic_2 = ret_2.isna()
    synthetic_3 = ret_3.isna()

    for dt in index:
        if pd.isna(idx_ret.loc[dt]):
            continue
        r_idx = float(idx_ret.loc[dt])
        tb = float(tbill_a.loc[dt]) if not pd.isna(tbill_a.loc[dt]) else 0.0
        vix_val = float(vix_a.loc[dt]) if not pd.isna(vix_a.loc[dt]) else None
        if synthetic_2.loc[dt]:
            ret_2.loc[dt] = synthetic_daily_reset_return(r_idx, 2.0, tb, vix=vix_val)
        elif abs(float(ret_2.loc[dt])) > MAX_ETP_DAILY_ABS[2]:
            ret_2.loc[dt] = synthetic_daily_reset_return(r_idx, 2.0, tb, vix=vix_val)
            synthetic_2.loc[dt] = True
        if synthetic_3.loc[dt]:
            ret_3.loc[dt] = synthetic_daily_reset_return(r_idx, 3.0, tb, vix=vix_val)
        elif abs(float(ret_3.loc[dt])) > MAX_ETP_DAILY_ABS[3]:
            ret_3.loc[dt] = synthetic_daily_reset_return(r_idx, 3.0, tb, vix=vix_val)
            synthetic_3.loc[dt] = True
        if pd.isna(ret_1.loc[dt]):
            ret_1.loc[dt] = synthetic_daily_reset_return(r_idx, 1.0, tb, vix=vix_val)
        elif abs(float(ret_1.loc[dt])) > MAX_ETP_DAILY_ABS[1]:
            ret_1.loc[dt] = synthetic_daily_reset_return(r_idx, 1.0, tb, vix=vix_val)

    panel = pd.DataFrame(
        {
            "ret_0": ret_0,
            "ret_1": ret_1.fillna(0.0),
            "ret_2": ret_2.fillna(0.0),
            "ret_3": ret_3.fillna(0.0),
            "vix": vix_a.ffill().fillna(VIX_STRESS_THRESHOLD),
            "synthetic_2": synthetic_2.fillna(True),
            "synthetic_3": synthetic_3.fillna(True),
        },
        index=index,
    )
    return panel


def etp_coverage_summary(panel: pd.DataFrame) -> dict[str, float]:
    """Fraction of days using real ETP returns vs synthetic fill."""
    if "synthetic_2" not in panel.columns or "synthetic_3" not in panel.columns:
        return {"pct_real_2x": 0.0, "pct_real_3x": 0.0}
    return {
        "pct_real_2x": round(100.0 * float((~panel["synthetic_2"]).mean()), 1),
        "pct_real_3x": round(100.0 * float((~panel["synthetic_3"]).mean()), 1),
    }


def export_etp_returns_json(
    panel: pd.DataFrame,
    bundle: EtpBundle,
    path: Path,
) -> None:
    """Compact daily return series for browser backtests (aligned by date)."""
    payload = {
        "bundle": bundle.name,
        "tickers": {
            "1x": bundle.etf_1x,
            "1x_fallback": bundle.etf_1x_fallback,
            "2x": bundle.etf_2x,
            "3x": bundle.etf_3x,
        },
        "model": "listed_etp_with_synthetic_pre_inception",
        "borrow_spread_model": "vix_linked: 0.6% base + 30bp/10pts above VIX 15 (cap 2.6%), +20bp at 3x",
        "dates": [dt.strftime("%Y-%m-%d") for dt in panel.index],
        "ret_0": [round(float(x), 8) for x in panel["ret_0"].tolist()],
        "ret_1": [round(float(x), 8) for x in panel["ret_1"].tolist()],
        "ret_2": [round(float(x), 8) for x in panel["ret_2"].tolist()],
        "ret_3": [round(float(x), 8) for x in panel["ret_3"].tolist()],
        "vix": [round(float(x), 4) for x in panel["vix"].tolist()],
        "coverage": etp_coverage_summary(panel),
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def bootstrap_etp_paths(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    *,
    n_sims: int,
    horizon_days: int,
    block_days: int,
    seed: int,
    start_date: str = "2000-01-03",
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Block-bootstrap joint (index return, ETP tier returns, T-bill) for Monte Carlo.

    Reconstructs synthetic index closes for Guarded signals; bootstrapped ETP tier
    returns supply P&L on the same calendar day.
    """
    panel = etp_panel.reindex(prices.index)
    if len(panel) != len(prices):
        raise ValueError("etp_panel length must match prices")

    rng = np.random.default_rng(seed)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    r0 = panel["ret_0"].to_numpy(dtype=float)
    r1 = panel["ret_1"].to_numpy(dtype=float)
    r2 = panel["ret_2"].to_numpy(dtype=float)
    r3 = panel["ret_3"].to_numpy(dtype=float)
    vix_arr = panel["vix"].to_numpy(dtype=float) if "vix" in panel.columns else None

    block_starts = np.arange(1, len(prices) - block_days + 1)
    if len(block_starts) == 0:
        raise ValueError("prices too short for block bootstrap")

    paths: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for _ in range(n_sims):
        chunks: list[np.ndarray] = []
        while sum(len(x) for x in chunks) < horizon_days:
            start = int(rng.choice(block_starts))
            chunks.append(np.arange(start, start + block_days))
        idx = np.concatenate(chunks)[:horizon_days]
        bindex = pd.bdate_range(start_date, periods=horizon_days)
        path_prices = pd.DataFrame(
            {
                "spx_close": 1000.0 * np.cumprod(1.0 + spx_ret[idx]),
                "tbill_rate": tbill[idx],
            },
            index=bindex,
        )
        etp_cols: dict[str, object] = {
            "ret_0": r0[idx],
            "ret_1": r1[idx],
            "ret_2": r2[idx],
            "ret_3": r3[idx],
        }
        if vix_arr is not None:
            etp_cols["vix"] = vix_arr[idx]
        if "synthetic_2" in panel.columns:
            etp_cols["synthetic_2"] = panel["synthetic_2"].to_numpy(dtype=bool)[idx]
        if "synthetic_3" in panel.columns:
            etp_cols["synthetic_3"] = panel["synthetic_3"].to_numpy(dtype=bool)[idx]
        path_etp = pd.DataFrame(etp_cols, index=bindex)
        paths.append((path_prices, path_etp))
    return paths
