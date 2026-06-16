"""Exhaust promising free/public-data risk overlays for the guarded default.

Baseline is the current site default:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard.

The grid intentionally prioritizes overlays that throttle only 3x recovery
exposure or cap max exposure at 2x, because the research goal is drawdown
improvement without materially reducing CAGR. External signals are lagged before
use: daily market/FRED data by one session, weekly FRED data by five sessions,
and monthly FRED/Shiller data by 21 sessions.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_fundamental_overlay_filters import (
    BASELINE_SPEC,
    OUTPUT_DIR,
    add_comparison_columns,
    align_signal,
    baseline_leverage,
    fetch_fred_series,
    fetch_shiller_cape,
    run_backtest,
    selected_annual_equity,
)
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


RESULTS_CSV = OUTPUT_DIR / "free_data_overlay_results.csv"
TOP_CSV = OUTPUT_DIR / "free_data_overlay_top.csv"
CATEGORY_BEST_CSV = OUTPUT_DIR / "free_data_overlay_category_best.csv"
METADATA_JSON = OUTPUT_DIR / "free_data_overlay_metadata.json"
SIGNAL_COVERAGE_CSV = OUTPUT_DIR / "free_data_signal_coverage.csv"
ANNUAL_EQUITY_CSV = OUTPUT_DIR / "free_data_overlay_annual_equity_selected.csv"

UNEMPLOYMENT_BENCHMARK = {
    "strategy": "Unemployment rising 3m cap max 2x (3x only)",
    "cagr": 0.37225809997277004,
    "max_drawdown": -0.2330864206300392,
    "sharpe": 3.2711461407981886,
    "cagr_retention_pct": 95.23092948938483,
    "max_dd_improvement_pp": 4.19853128059694,
}


@dataclass(frozen=True)
class FreeOverlaySpec:
    category: str
    name: str
    signal: str
    threshold: str
    action: str
    condition: Callable[[pd.DataFrame], pd.Series]
    data_series: tuple[str, ...]
    practicality: int
    notes: str


def prior_session(series: pd.Series) -> pd.Series:
    return series.shift(1)


def safe_bool(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    return series.reindex(index).fillna(False).astype(bool)


def fetch_yahoo_close(ticker: str, prices: pd.DataFrame) -> pd.Series:
    raw = yf.download(
        ticker,
        start=prices.index[0].strftime("%Y-%m-%d"),
        end=(prices.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"No Yahoo data returned for {ticker}")
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if out.empty:
        raise ValueError(f"No numeric close data returned for {ticker}")
    return out


def add_fred_signal(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    availability: dict[str, dict[str, str]],
    label: str,
    series_id: str,
    *,
    lag_sessions: int,
    scale: float,
    source: str,
) -> None:
    try:
        raw = fetch_fred_series(series_id)
        aligned = align_signal(prices.index, raw, lag_sessions=lag_sessions, scale=scale)
        if aligned.notna().sum() == 0:
            raise ValueError("Aligned series has no overlap with market history")
        signals[label] = aligned
        availability[label] = {
            "status": "available",
            "series_id": series_id,
            "source": source,
            "raw_start": raw.index[0].date().isoformat(),
            "raw_end": raw.index[-1].date().isoformat(),
            "lag": f"{lag_sessions} market sessions",
            "available_market_days": str(int(aligned.notna().sum())),
        }
    except Exception as exc:  # noqa: BLE001 - public data coverage is part of the result.
        availability[label] = {
            "status": "unavailable",
            "series_id": series_id,
            "source": source,
            "error": str(exc),
        }


def load_free_public_signals(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    signals = pd.DataFrame(index=prices.index)
    availability: dict[str, dict[str, str]] = {}

    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    signals["SPX_BELOW_SMA20"] = prior_session(close < sma20)
    signals["SPX_BELOW_SMA50"] = prior_session(close < sma50)
    signals["SPX_ABOVE_SMA20"] = prior_session(close > sma20)
    signals["SPX_ABOVE_SMA50"] = prior_session(close > sma50)
    signals["SPX_21D_RET"] = prior_session(close.pct_change(21))
    availability["SPX_TREND"] = {
        "status": "available",
        "source": "Yahoo Finance ^GSPC via project data_manager.load_backtest_data",
        "raw_start": prices.index[0].date().isoformat(),
        "raw_end": prices.index[-1].date().isoformat(),
        "lag": "1 market session",
    }

    fred_specs = [
        ("NFCI", "NFCI", 5, 1.0, "Chicago Fed National Financial Conditions Index, FRED"),
        ("ANFCI", "ANFCI", 5, 1.0, "Chicago Fed Adjusted NFCI, FRED"),
        ("HY_OAS", "BAMLH0A0HYM2", 1, 0.01, "ICE BofA US High Yield OAS, FRED"),
        ("IG_OAS", "BAMLC0A0CM", 1, 0.01, "ICE BofA US Corporate OAS, FRED"),
        ("BAA10Y", "BAA10Y", 1, 0.01, "Moody's Baa yield minus 10Y Treasury, FRED"),
        ("AAA10Y", "AAA10Y", 1, 0.01, "Moody's Aaa yield minus 10Y Treasury, FRED"),
        ("DGS10", "DGS10", 1, 0.01, "10-year Treasury constant maturity, FRED"),
        ("DFII10", "DFII10", 1, 0.01, "10-year TIPS real yield, FRED"),
        ("CPIAUCSL", "CPIAUCSL", 21, 1.0, "Consumer Price Index, monthly, FRED"),
        ("UNRATE", "UNRATE", 21, 0.01, "Civilian unemployment rate, FRED"),
        ("WALCL", "WALCL", 5, 1.0, "Federal Reserve total assets, weekly, FRED"),
        ("WRESBAL", "WRESBAL", 5, 1.0, "Reserve balances with Federal Reserve Banks, weekly, FRED"),
        ("RRPONTSYD", "RRPONTSYD", 1, 1.0, "Overnight reverse repo accepted bids, daily, FRED"),
        ("M2SL", "M2SL", 21, 1.0, "M2 money stock, monthly, FRED"),
    ]
    for label, series_id, lag, scale, source in fred_specs:
        add_fred_signal(
            prices,
            signals,
            availability,
            label,
            series_id,
            lag_sessions=lag,
            scale=scale,
            source=source,
        )

    try:
        cape_raw = fetch_shiller_cape()
        signals["CAPE"] = align_signal(prices.index, cape_raw, lag_sessions=21)
        signals["EARNINGS_YIELD"] = 1.0 / signals["CAPE"]
        availability["CAPE"] = {
            "status": "available",
            "source": "Robert Shiller online data",
            "raw_start": cape_raw.index[0].date().isoformat(),
            "raw_end": cape_raw.index[-1].date().isoformat(),
            "lag": "21 market sessions",
            "available_market_days": str(int(signals["CAPE"].notna().sum())),
        }
    except Exception as exc:  # noqa: BLE001
        availability["CAPE"] = {"status": "unavailable", "source": "Robert Shiller online data", "error": str(exc)}

    breadth_symbols = {
        "BREADTH_SP500_ABOVE_200DMA": ("^S5TH", "Yahoo public S&P 500 % above 200DMA proxy"),
        "BREADTH_SP500_ABOVE_50DMA": ("^S5FI", "Yahoo public S&P 500 % above 50DMA proxy"),
        "BREADTH_NYSE_ADV_DEC": ("^NYAD", "Yahoo public NYSE advance/decline proxy"),
        "BREADTH_NASDAQ_ADV_DEC": ("^NAAD", "Yahoo public Nasdaq advance/decline proxy"),
    }
    for label, (ticker, source) in breadth_symbols.items():
        try:
            close_raw = fetch_yahoo_close(ticker, prices)
            aligned = prior_session(close_raw.reindex(prices.index).ffill())
            if aligned.notna().sum() < 252:
                raise ValueError("Less than one year of overlapping history")
            signals[label] = aligned
            availability[label] = {
                "status": "available",
                "ticker": ticker,
                "source": source,
                "raw_start": close_raw.index[0].date().isoformat(),
                "raw_end": close_raw.index[-1].date().isoformat(),
                "lag": "1 market session",
                "available_market_days": str(int(aligned.notna().sum())),
            }
        except Exception as exc:  # noqa: BLE001
            availability[label] = {"status": "unavailable", "ticker": ticker, "source": source, "error": str(exc)}

    return signals, availability


def add_derived_signals(signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()

    if "UNRATE" in out:
        out["UNRATE_RISING_3M"] = out["UNRATE"].diff(63) >= 0.001
        out["UNRATE_RISING_6M"] = out["UNRATE"].diff(126) >= 0.002
        out["UNRATE_NOT_RISING_3M"] = out["UNRATE"].diff(63) <= 0.0

    for col in ["NFCI", "ANFCI"]:
        if col in out:
            out[f"{col}_ABOVE_0"] = out[col] > 0.0
            out[f"{col}_ABOVE_25BP"] = out[col] > 0.25
            out[f"{col}_UP_13W_25BP"] = out[col].diff(63) >= 0.25
            out[f"{col}_UP_26W_35BP"] = out[col].diff(126) >= 0.35
            out[f"{col}_NOT_WORSENING_13W"] = out[col].diff(63) <= 0.0

    for col in ["HY_OAS", "IG_OAS", "BAA10Y", "AAA10Y"]:
        if col in out:
            out[f"{col}_WIDEN_21D"] = out[col].diff(21)
            out[f"{col}_WIDEN_63D"] = out[col].diff(63)
            out[f"{col}_NOT_WIDENING_21D"] = out[col].diff(21) <= 0.0

    if "HY_OAS" in out:
        out["HY_OAS_ABOVE_5"] = out["HY_OAS"] >= 0.05
        out["HY_OAS_ABOVE_65"] = out["HY_OAS"] >= 0.065
        out["HY_OAS_WIDEN_21D_50BP"] = out["HY_OAS"].diff(21) >= 0.005
        out["HY_OAS_WIDEN_63D_100BP"] = out["HY_OAS"].diff(63) >= 0.010
    if "IG_OAS" in out:
        out["IG_OAS_ABOVE_15"] = out["IG_OAS"] >= 0.015
        out["IG_OAS_ABOVE_20"] = out["IG_OAS"] >= 0.020
        out["IG_OAS_WIDEN_21D_15BP"] = out["IG_OAS"].diff(21) >= 0.0015
        out["IG_OAS_WIDEN_63D_30BP"] = out["IG_OAS"].diff(63) >= 0.0030
    if "BAA10Y" in out:
        out["BAA10Y_ABOVE_25"] = out["BAA10Y"] >= 0.025
        out["BAA10Y_ABOVE_35"] = out["BAA10Y"] >= 0.035
        out["BAA10Y_WIDEN_63D_50BP"] = out["BAA10Y"].diff(63) >= 0.005
    if "AAA10Y" in out:
        out["AAA10Y_ABOVE_10"] = out["AAA10Y"] >= 0.010
        out["AAA10Y_WIDEN_63D_25BP"] = out["AAA10Y"].diff(63) >= 0.0025

    if "CPIAUCSL" in out:
        out["CPI_YOY"] = out["CPIAUCSL"].pct_change(252)
    if "DGS10" in out and "CPI_YOY" in out:
        out["REAL10Y_CPI_PROXY"] = out["DGS10"] - out["CPI_YOY"]
    if "EARNINGS_YIELD" in out and "DFII10" in out:
        out["ERP_REAL_TIPS"] = out["EARNINGS_YIELD"] - out["DFII10"]
        out["ERP_REAL_TIPS_PRESSURE"] = out["ERP_REAL_TIPS"] <= 0.02
        out["ERP_REAL_TIPS_DETERIORATE_63D"] = out["ERP_REAL_TIPS"].diff(63) <= -0.005
    if "EARNINGS_YIELD" in out and "REAL10Y_CPI_PROXY" in out:
        out["ERP_REAL_CPI_PROXY"] = out["EARNINGS_YIELD"] - out["REAL10Y_CPI_PROXY"]
        out["ERP_REAL_CPI_PRESSURE"] = out["ERP_REAL_CPI_PROXY"] <= 0.01
        out["ERP_REAL_CPI_DETERIORATE_63D"] = out["ERP_REAL_CPI_PROXY"].diff(63) <= -0.005
    if "DFII10" in out:
        out["REAL_YIELD_RISE_63D_50BP"] = out["DFII10"].diff(63) >= 0.005

    for col in ["WALCL", "WRESBAL", "RRPONTSYD", "M2SL"]:
        if col in out:
            out[f"{col}_CHG_63D"] = out[col].pct_change(63)
            out[f"{col}_CHG_126D"] = out[col].pct_change(126)
            out[f"{col}_CHG_252D"] = out[col].pct_change(252)
            out[f"{col}_NOT_CONTRACTING_63D"] = out[col].pct_change(63) >= 0.0
    if "WALCL" in out:
        out["WALCL_CONTRACT_6M_5"] = out["WALCL_CHG_126D"] <= -0.05
        out["WALCL_CONTRACT_12M_10"] = out["WALCL_CHG_252D"] <= -0.10
    if "WRESBAL" in out:
        out["WRESBAL_CONTRACT_3M_10"] = out["WRESBAL_CHG_63D"] <= -0.10
        out["WRESBAL_CONTRACT_6M_15"] = out["WRESBAL_CHG_126D"] <= -0.15
    if "M2SL" in out:
        out["M2SL_CONTRACT_6M_2"] = out["M2SL_CHG_126D"] <= -0.02
        out["M2SL_CONTRACT_12M_4"] = out["M2SL_CHG_252D"] <= -0.04
    if "RRPONTSYD" in out and "WRESBAL" in out:
        out["RRP_DRAIN_RESERVES_FALL_3M"] = (out["RRPONTSYD_CHG_63D"] <= -0.25) & (
            out["WRESBAL_CHG_63D"] <= -0.05
        )

    if "BREADTH_SP500_ABOVE_200DMA" in out:
        value = out["BREADTH_SP500_ABOVE_200DMA"]
        threshold_value = 45.0 if value.quantile(0.95) > 2.0 else 0.45
        out["BREADTH_200DMA_WEAK"] = value <= threshold_value
        out["BREADTH_200DMA_DETERIORATE"] = value.diff(21) <= (-10.0 if threshold_value > 2.0 else -0.10)
    if "BREADTH_SP500_ABOVE_50DMA" in out:
        value = out["BREADTH_SP500_ABOVE_50DMA"]
        threshold_value = 35.0 if value.quantile(0.95) > 2.0 else 0.35
        out["BREADTH_50DMA_WEAK"] = value <= threshold_value
        out["BREADTH_50DMA_DETERIORATE"] = value.diff(21) <= (-15.0 if threshold_value > 2.0 else -0.15)

    deterioration_inputs = [
        "UNRATE_RISING_3M",
        "NFCI_UP_13W_25BP",
        "ANFCI_UP_13W_25BP",
        "HY_OAS_WIDEN_21D_50BP",
        "IG_OAS_WIDEN_21D_15BP",
        "BAA10Y_WIDEN_63D_50BP",
        "ERP_REAL_TIPS_DETERIORATE_63D",
        "ERP_REAL_CPI_DETERIORATE_63D",
        "WALCL_CONTRACT_6M_5",
        "WRESBAL_CONTRACT_3M_10",
        "M2SL_CONTRACT_6M_2",
        "BREADTH_200DMA_DETERIORATE",
        "BREADTH_50DMA_DETERIORATE",
    ]
    available = [col for col in deterioration_inputs if col in out]
    if available:
        out["FREE_STRESS_COUNT"] = out[available].fillna(False).astype(bool).sum(axis=1)
        out["FREE_STRESS_2PLUS"] = out["FREE_STRESS_COUNT"] >= 2
        out["FREE_STRESS_3PLUS"] = out["FREE_STRESS_COUNT"] >= 3
        weights = pd.Series(0.0, index=out.index)
        for col in available:
            weight = 1.5 if col in {"UNRATE_RISING_3M", "HY_OAS_WIDEN_21D_50BP", "NFCI_UP_13W_25BP"} else 1.0
            weights = weights + out[col].fillna(False).astype(bool).astype(float) * weight
        out["FREE_STRESS_SCORE"] = weights
        out["FREE_STRESS_SCORE_2"] = weights >= 2.0
        out["FREE_STRESS_SCORE_3"] = weights >= 3.0

    return out


def apply_overlay(base_leverage: pd.Series, condition: pd.Series, action: str) -> pd.Series:
    cond = condition.reindex(base_leverage.index).fillna(False).astype(bool)
    lev = base_leverage.copy().astype(float)
    if action == "cap_3x_to_2x":
        mask = cond & (lev == 3.0)
        lev.loc[mask] = 2.0
    elif action == "cap_max_2x":
        mask = cond & (lev > 2.0)
        lev.loc[mask] = 2.0
    elif action == "cap_recovery_max_1x":
        mask = cond & (lev > 1.0)
        lev.loc[mask] = 1.0
    elif action == "reduce_one_tier":
        mask = cond & (lev > 0.0)
        lev.loc[mask] = lev.loc[mask].map({3.0: 2.0, 2.0: 1.0, 1.0: 1.0}).fillna(
            lev.loc[mask].clip(lower=0.0) - 1.0
        ).clip(lower=0.0)
    else:
        raise ValueError(f"Unknown action: {action}")
    return lev


def defensive_regime(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    entry = entry.fillna(False).astype(bool)
    exit_ = exit_.fillna(False).astype(bool)
    active: list[bool] = []
    is_active = False
    for dt in entry.index:
        if is_active and bool(exit_.loc[dt]):
            is_active = False
        if bool(entry.loc[dt]):
            is_active = True
        active.append(is_active)
    return pd.Series(active, index=entry.index)


def all_present(signals: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    return all(col in signals.columns for col in columns)


def add_action_specs(
    specs: list[FreeOverlaySpec],
    *,
    category: str,
    base_name: str,
    signal: str,
    threshold: str,
    condition: Callable[[pd.DataFrame], pd.Series],
    data_series: tuple[str, ...],
    practicality: int,
    notes: str,
    include_1x: bool = True,
) -> None:
    action_labels = [
        ("cap_3x_to_2x", "3x-only cap to 2x", practicality),
        ("cap_max_2x", "max 2x cap", practicality),
        ("reduce_one_tier", "one-tier reduction", max(1, practicality - 1)),
    ]
    if include_1x:
        action_labels.append(("cap_recovery_max_1x", "conditional 1x recovery cap", max(1, practicality - 2)))
    for action, label, action_practicality in action_labels:
        specs.append(
            FreeOverlaySpec(
                category=category,
                name=f"{base_name} / {label}",
                signal=signal,
                threshold=threshold,
                action=action,
                condition=condition,
                data_series=data_series,
                practicality=action_practicality,
                notes=notes,
            )
        )


def build_specs(signals: pd.DataFrame) -> list[FreeOverlaySpec]:
    specs: list[FreeOverlaySpec] = []

    for col, label in [("NFCI", "NFCI"), ("ANFCI", "ANFCI")]:
        if col in signals:
            candidates = [
                (f"{col}_ABOVE_0", f"{label} above zero", ">0"),
                (f"{col}_ABOVE_25BP", f"{label} above +0.25", ">+0.25"),
                (f"{col}_UP_13W_25BP", f"{label} up 13w >= 0.25", "13w change >= +0.25"),
                (f"{col}_UP_26W_35BP", f"{label} up 26w >= 0.35", "26w change >= +0.35"),
            ]
            for signal_col, name, threshold in candidates:
                if signal_col in signals:
                    add_action_specs(
                        specs,
                        category="Financial conditions",
                        base_name=name,
                        signal=label,
                        threshold=threshold,
                        condition=lambda s, c=signal_col: s[c],
                        data_series=(col, signal_col),
                        practicality=5,
                        notes="Chicago Fed financial conditions are free weekly FRED data lagged five sessions.",
                        include_1x=False,
                    )
                    for trend_col, trend_label in [
                        ("SPX_BELOW_SMA20", "SPX below SMA20"),
                        ("SPX_BELOW_SMA50", "SPX below SMA50"),
                    ]:
                        add_action_specs(
                            specs,
                            category="Financial conditions + trend",
                            base_name=f"{name} and {trend_label}",
                            signal=f"{label} stress plus {trend_label}",
                            threshold=f"{threshold} and {trend_label}",
                            condition=lambda s, c=signal_col, t=trend_col: s[c] & s[t],
                            data_series=(col, signal_col, trend_col),
                            practicality=5,
                            notes="Requires public financial stress deterioration and already-weak SPX trend.",
                            include_1x=True,
                        )

    credit_candidates = [
        ("HY_OAS_ABOVE_5", "HY OAS >= 5%", "HY_OAS", ">=5.0%"),
        ("HY_OAS_ABOVE_65", "HY OAS >= 6.5%", "HY_OAS", ">=6.5%"),
        ("HY_OAS_WIDEN_21D_50BP", "HY OAS widening 21d >= 50bp", "HY_OAS", "21d widening >= 50bp"),
        ("HY_OAS_WIDEN_63D_100BP", "HY OAS widening 63d >= 100bp", "HY_OAS", "63d widening >= 100bp"),
        ("IG_OAS_ABOVE_15", "IG OAS >= 1.5%", "IG_OAS", ">=1.5%"),
        ("IG_OAS_ABOVE_20", "IG OAS >= 2.0%", "IG_OAS", ">=2.0%"),
        ("IG_OAS_WIDEN_21D_15BP", "IG OAS widening 21d >= 15bp", "IG_OAS", "21d widening >= 15bp"),
        ("IG_OAS_WIDEN_63D_30BP", "IG OAS widening 63d >= 30bp", "IG_OAS", "63d widening >= 30bp"),
        ("BAA10Y_ABOVE_25", "BAA-10Y spread >= 2.5%", "BAA10Y", ">=2.5%"),
        ("BAA10Y_ABOVE_35", "BAA-10Y spread >= 3.5%", "BAA10Y", ">=3.5%"),
        ("BAA10Y_WIDEN_63D_50BP", "BAA-10Y spread widening 63d >= 50bp", "BAA10Y", "63d widening >= 50bp"),
        ("AAA10Y_ABOVE_10", "AAA-10Y spread >= 1.0%", "AAA10Y", ">=1.0%"),
        ("AAA10Y_WIDEN_63D_25BP", "AAA-10Y spread widening 63d >= 25bp", "AAA10Y", "63d widening >= 25bp"),
    ]
    for signal_col, name, base_col, threshold in credit_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Credit stress",
                base_name=name,
                signal=base_col,
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=(base_col, signal_col),
                practicality=4,
                notes="Free FRED credit stress series; OAS and corporate/Treasury spreads are used as throttles.",
                include_1x=False,
            )
            for trend_col, trend_label in [
                ("SPX_BELOW_SMA20", "SPX below SMA20"),
                ("SPX_BELOW_SMA50", "SPX below SMA50"),
            ]:
                add_action_specs(
                    specs,
                    category="Credit stress + trend",
                    base_name=f"{name} and {trend_label}",
                    signal=f"{base_col} stress plus {trend_label}",
                    threshold=f"{threshold} and {trend_label}",
                    condition=lambda s, c=signal_col, t=trend_col: s[c] & s[t],
                    data_series=(base_col, signal_col, trend_col),
                    practicality=5,
                    notes="Credit stress is only used when SPX trend is already weak.",
                    include_1x=True,
                )

    labor_candidates = [
        ("UNRATE_RISING_3M", "Unemployment rising 3m", "3m change >= +0.10pp"),
        ("UNRATE_RISING_6M", "Unemployment rising 6m", "6m change >= +0.20pp"),
    ]
    for signal_col, name, threshold in labor_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Labor stress",
                base_name=name,
                signal="UNRATE",
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=("UNRATE", signal_col),
                practicality=5,
                notes="Public FRED unemployment deterioration, lagged 21 sessions before use.",
                include_1x=True,
            )
            for trend_col, trend_label in [
                ("SPX_BELOW_SMA20", "SPX below SMA20"),
                ("SPX_BELOW_SMA50", "SPX below SMA50"),
            ]:
                add_action_specs(
                    specs,
                    category="Labor stress + trend",
                    base_name=f"{name} and {trend_label}",
                    signal=f"UNRATE deterioration plus {trend_label}",
                    threshold=f"{threshold} and {trend_label}",
                    condition=lambda s, c=signal_col, t=trend_col: s[c] & s[t],
                    data_series=("UNRATE", signal_col, trend_col),
                    practicality=5,
                    notes="Labor deterioration must coincide with weak SPX trend.",
                    include_1x=True,
                )

    erp_candidates = [
        ("ERP_REAL_TIPS_PRESSURE", "Shiller EY - TIPS real 10Y <= 2%", "ERP_REAL_TIPS", "<=2.0%"),
        ("ERP_REAL_TIPS_DETERIORATE_63D", "Shiller EY - TIPS real 10Y deteriorating", "ERP_REAL_TIPS", "63d change <= -50bp"),
        ("ERP_REAL_CPI_PRESSURE", "Shiller EY - CPI-proxy real 10Y <= 1%", "ERP_REAL_CPI_PROXY", "<=1.0%"),
        ("ERP_REAL_CPI_DETERIORATE_63D", "Shiller EY - CPI-proxy real 10Y deteriorating", "ERP_REAL_CPI_PROXY", "63d change <= -50bp"),
        ("REAL_YIELD_RISE_63D_50BP", "TIPS real yield rising 63d >= 50bp", "DFII10", "63d rise >= 50bp"),
    ]
    for signal_col, name, base_col, threshold in erp_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Real yield / ERP",
                base_name=name,
                signal=base_col,
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=(base_col, signal_col),
                practicality=3,
                notes="Valuation/real-yield pressure is tested as a throttle rather than an all-risk exit.",
                include_1x=False,
            )
            add_action_specs(
                specs,
                category="Real yield / ERP + trend",
                base_name=f"{name} and SPX below SMA50",
                signal=f"{base_col} pressure plus SPX below SMA50",
                threshold=f"{threshold} and SPX below SMA50",
                condition=lambda s, c=signal_col: s[c] & s["SPX_BELOW_SMA50"],
                data_series=(base_col, signal_col, "SPX_BELOW_SMA50"),
                practicality=4,
                notes="Real-yield/ERP pressure is required to coincide with weak price trend.",
                include_1x=True,
            )

    liquidity_candidates = [
        ("WALCL_CONTRACT_6M_5", "Fed assets contracting 6m >= 5%", "WALCL", "6m change <= -5%"),
        ("WALCL_CONTRACT_12M_10", "Fed assets contracting 12m >= 10%", "WALCL", "12m change <= -10%"),
        ("WRESBAL_CONTRACT_3M_10", "Reserve balances contracting 3m >= 10%", "WRESBAL", "3m change <= -10%"),
        ("WRESBAL_CONTRACT_6M_15", "Reserve balances contracting 6m >= 15%", "WRESBAL", "6m change <= -15%"),
        ("M2SL_CONTRACT_6M_2", "M2 contracting 6m >= 2%", "M2SL", "6m change <= -2%"),
        ("M2SL_CONTRACT_12M_4", "M2 contracting 12m >= 4%", "M2SL", "12m change <= -4%"),
        ("RRP_DRAIN_RESERVES_FALL_3M", "RRP drain and reserves falling 3m", "RRPONTSYD", "RRP <= -25% and reserves <= -5%"),
    ]
    for signal_col, name, base_col, threshold in liquidity_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Liquidity regime",
                base_name=name,
                signal=base_col,
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=(base_col, signal_col),
                practicality=3,
                notes="Fed/liquidity contraction is free FRED data but has shorter or regime-dependent history.",
                include_1x=False,
            )
            add_action_specs(
                specs,
                category="Liquidity + trend",
                base_name=f"{name} and SPX below SMA50",
                signal=f"{base_col} contraction plus SPX below SMA50",
                threshold=f"{threshold} and SPX below SMA50",
                condition=lambda s, c=signal_col: s[c] & s["SPX_BELOW_SMA50"],
                data_series=(base_col, signal_col, "SPX_BELOW_SMA50"),
                practicality=4,
                notes="Liquidity contraction must be confirmed by weak market trend.",
                include_1x=True,
            )

    breadth_candidates = [
        ("BREADTH_200DMA_WEAK", "S&P breadth above 200DMA weak", "BREADTH_SP500_ABOVE_200DMA", "below weak threshold"),
        (
            "BREADTH_200DMA_DETERIORATE",
            "S&P breadth above 200DMA deteriorating",
            "BREADTH_SP500_ABOVE_200DMA",
            "21d deterioration threshold",
        ),
        ("BREADTH_50DMA_WEAK", "S&P breadth above 50DMA weak", "BREADTH_SP500_ABOVE_50DMA", "below weak threshold"),
        (
            "BREADTH_50DMA_DETERIORATE",
            "S&P breadth above 50DMA deteriorating",
            "BREADTH_SP500_ABOVE_50DMA",
            "21d deterioration threshold",
        ),
    ]
    for signal_col, name, base_col, threshold in breadth_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Public breadth proxy",
                base_name=name,
                signal=base_col,
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=(base_col, signal_col),
                practicality=4,
                notes="Uses only public index-level Yahoo breadth proxy if returned; no current-constituent reconstruction.",
                include_1x=False,
            )

    composite_candidates = [
        ("FREE_STRESS_2PLUS", "2+ free-data deterioration signals", "count >= 2", 5),
        ("FREE_STRESS_3PLUS", "3+ free-data deterioration signals", "count >= 3", 5),
        ("FREE_STRESS_SCORE_2", "free-data weighted stress score >= 2", "score >= 2", 5),
        ("FREE_STRESS_SCORE_3", "free-data weighted stress score >= 3", "score >= 3", 5),
    ]
    for signal_col, name, threshold, practicality in composite_candidates:
        if signal_col in signals:
            add_action_specs(
                specs,
                category="Composite free-data stress",
                base_name=name,
                signal="labor, NFCI/ANFCI, credit, ERP, liquidity, breadth, SPX trend",
                threshold=threshold,
                condition=lambda s, c=signal_col: s[c],
                data_series=(signal_col,),
                practicality=practicality,
                notes="Composite trigger uses public inputs and prioritizes 3x/max-2x throttles.",
                include_1x=True,
            )
            for trend_col, trend_label in [
                ("SPX_BELOW_SMA50", "SPX below SMA50"),
                ("SPX_BELOW_SMA20", "SPX below SMA20"),
            ]:
                add_action_specs(
                    specs,
                    category="Composite + trend",
                    base_name=f"{name} and {trend_label}",
                    signal=f"Composite stress plus {trend_label}",
                    threshold=f"{threshold} and {trend_label}",
                    condition=lambda s, c=signal_col, t=trend_col: s[c] & s[t],
                    data_series=(signal_col, trend_col),
                    practicality=5,
                    notes="Requires multiple free stress signals and weak SPX trend.",
                    include_1x=True,
                )

    re_risk_entries = [
        ("UNRATE_RISING_3M", "unemployment 3m rising", "UNRATE_NOT_RISING_3M"),
        ("NFCI_UP_13W_25BP", "NFCI 13w worsening", "NFCI_NOT_WORSENING_13W"),
        ("ANFCI_UP_13W_25BP", "ANFCI 13w worsening", "ANFCI_NOT_WORSENING_13W"),
        ("HY_OAS_WIDEN_21D_50BP", "HY OAS 21d widening", "HY_OAS_NOT_WIDENING_21D"),
        ("IG_OAS_WIDEN_21D_15BP", "IG OAS 21d widening", "IG_OAS_NOT_WIDENING_21D"),
        ("FREE_STRESS_2PLUS", "2+ free stress signals", None),
        ("FREE_STRESS_SCORE_2", "free stress score >= 2", None),
    ]
    for entry_col, entry_label, repair_col in re_risk_entries:
        if entry_col not in signals:
            continue
        exit_variants: list[tuple[str, Callable[[pd.DataFrame], pd.Series], tuple[str, ...]]] = [
            ("exit SPX > SMA20", lambda s: s["SPX_ABOVE_SMA20"], ("SPX_ABOVE_SMA20",)),
            ("exit SPX > SMA50", lambda s: s["SPX_ABOVE_SMA50"], ("SPX_ABOVE_SMA50",)),
        ]
        if repair_col and repair_col in signals:
            exit_variants.append(
                (
                    f"exit {repair_col.replace('_', ' ').lower()}",
                    lambda s, c=repair_col: s[c],
                    (repair_col,),
                )
            )
        if entry_col.startswith("FREE_STRESS"):
            exit_variants.append(("exit stress count <= 1", lambda s: s["FREE_STRESS_COUNT"] <= 1, ("FREE_STRESS_COUNT",)))
        for exit_label, exit_func, exit_cols in exit_variants:
            for action in ["cap_3x_to_2x", "cap_max_2x"]:
                specs.append(
                    FreeOverlaySpec(
                        category="Re-risk stateful",
                        name=f"Stateful {entry_label}, {exit_label} / {action}",
                        signal=f"Enter on {entry_label}; {exit_label}",
                        threshold="stateful defensive cap with explicit repair trigger",
                        action=action,
                        condition=lambda s, e=entry_col, x=exit_func: defensive_regime(s[e], x(s)),
                        data_series=(entry_col,) + exit_cols,
                        practicality=5,
                        notes="Tests whether a throttle should persist until trend or stress momentum repairs.",
                    )
                )

    return specs


def signal_coverage(signals: pd.DataFrame, availability: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows = []
    for name, info in availability.items():
        if info.get("status") == "available":
            if name == "SPX_TREND":
                matching_cols = [
                    col
                    for col in ["SPX_BELOW_SMA20", "SPX_BELOW_SMA50", "SPX_ABOVE_SMA20", "SPX_ABOVE_SMA50"]
                    if col in signals.columns
                ]
            else:
                matching_cols = [name] if name in signals.columns else [c for c in signals.columns if c.startswith(name)]
            valid_days = max((int(signals[c].notna().sum()) for c in matching_cols), default=0)
            first_valid = None
            last_valid = None
            if matching_cols:
                valid_mask = signals[matching_cols].notna().any(axis=1)
                if valid_mask.any():
                    first_valid = signals.index[valid_mask][0].date().isoformat()
                    last_valid = signals.index[valid_mask][-1].date().isoformat()
            rows.append(
                {
                    "signal": name,
                    "status": "available",
                    "source": info.get("source", ""),
                    "series_or_ticker": info.get("series_id", info.get("ticker", "")),
                    "raw_start": info.get("raw_start", ""),
                    "raw_end": info.get("raw_end", ""),
                    "lag": info.get("lag", ""),
                    "valid_market_days": valid_days,
                    "first_valid_market_day": first_valid or "",
                    "last_valid_market_day": last_valid or "",
                    "error": "",
                }
            )
        else:
            rows.append(
                {
                    "signal": name,
                    "status": "unavailable",
                    "source": info.get("source", ""),
                    "series_or_ticker": info.get("series_id", info.get("ticker", "")),
                    "raw_start": "",
                    "raw_end": "",
                    "lag": "",
                    "valid_market_days": 0,
                    "first_valid_market_day": "",
                    "last_valid_market_day": "",
                    "error": info.get("error", ""),
                }
            )
    return pd.DataFrame(rows).sort_values(["status", "signal"], ascending=[True, True])


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, baseline_equity = run_backtest(
        prices,
        base_lev,
        str(BASELINE_SPEC["strategy"]),
        base_counts,
    )

    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print("Loading free/public macro, credit, liquidity, ERP, and breadth signals...", flush=True)
    signals, availability = load_free_public_signals(prices)
    signals = add_derived_signals(signals)
    signals = signals[[c for c in signals.columns if signals[c].notna().any()]]

    specs = build_specs(signals)
    rows: list[dict[str, float | int | str]] = []
    equity_by_name = {str(BASELINE_SPEC["strategy"]): baseline_equity}

    for spec in specs:
        if not all_present(signals, spec.data_series):
            continue
        condition = spec.condition(signals).reindex(prices.index).fillna(False).astype(bool)
        active_days = int(condition.sum())
        if active_days == 0:
            continue
        lev = apply_overlay(base_lev, condition, spec.action)
        changed = lev != base_lev
        if not bool(changed.any()):
            continue
        row, equity = run_backtest(
            prices,
            lev,
            spec.name,
            {
                "category": spec.category,
                "signal": spec.signal,
                "threshold": spec.threshold,
                "action": spec.action,
                "overlay_active_days": active_days,
                "overlay_active_pct": float(active_days / len(prices) * 100.0),
                "avg_leverage": float(lev.mean()),
                "pct_leverage_changed": float(changed.mean() * 100.0),
                "pct_2x_days_changed": float(
                    ((base_lev == 2.0) & changed).sum() / max((base_lev == 2.0).sum(), 1) * 100.0
                ),
                "pct_3x_days_changed": float(
                    ((base_lev == 3.0) & changed).sum() / max((base_lev == 3.0).sum(), 1) * 100.0
                ),
                "practicality": spec.practicality,
                "notes": spec.notes,
            },
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    if not rows:
        raise RuntimeError("No free/public overlay candidates changed baseline leverage.")

    results = add_comparison_columns(pd.DataFrame(rows), baseline_row)
    results["beats_unemployment_dd"] = results["max_drawdown"] > UNEMPLOYMENT_BENCHMARK["max_drawdown"]
    results["beats_unemployment_cagr"] = results["cagr"] >= UNEMPLOYMENT_BENCHMARK["cagr"]
    results["beats_unemployment_practical"] = (
        results["max_drawdown"] > UNEMPLOYMENT_BENCHMARK["max_drawdown"]
    ) & (results["cagr_retention_pct"] >= UNEMPLOYMENT_BENCHMARK["cagr_retention_pct"])
    results["practical_rank_score"] = (
        results["max_dd_improvement_pp"] * 3.0
        + (results["cagr_retention_pct"] - 100.0) * 0.40
        + results["sharpe_delta"] * 5.0
        + results["practicality"].astype(float)
        - results["pct_leverage_changed"] * 0.03
    )
    results = results.sort_values(
        ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "practicality"],
        ascending=[False, False, False, False],
    )

    baseline_df = add_comparison_columns(pd.DataFrame([baseline_row]), baseline_row)
    baseline_df["category"] = "Baseline"
    baseline_df["signal"] = "Current default strategy"
    baseline_df["threshold"] = "n/a"
    baseline_df["action"] = "n/a"
    baseline_df["overlay_active_days"] = 0
    baseline_df["overlay_active_pct"] = 0.0
    baseline_df["avg_leverage"] = float(base_lev.mean())
    baseline_df["pct_leverage_changed"] = 0.0
    baseline_df["pct_2x_days_changed"] = 0.0
    baseline_df["pct_3x_days_changed"] = 0.0
    baseline_df["practicality"] = 5
    baseline_df["notes"] = "Current default benchmark."
    baseline_df["beats_unemployment_dd"] = False
    baseline_df["beats_unemployment_cagr"] = False
    baseline_df["beats_unemployment_practical"] = False
    baseline_df["practical_rank_score"] = 0.0

    category_best = (
        results.sort_values(
            ["category", "max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "practicality"],
            ascending=[True, False, False, False, False],
        )
        .groupby("category", as_index=False)
        .head(3)
    )
    top = results.sort_values(
        ["practical_rank_score", "max_dd_improvement_pp", "cagr_retention_pct", "sharpe"],
        ascending=[False, False, False, False],
    ).head(20)

    pd.concat([baseline_df, results], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    top.to_csv(TOP_CSV, index=False)
    category_best.to_csv(CATEGORY_BEST_CSV, index=False)
    signal_coverage(signals, availability).to_csv(SIGNAL_COVERAGE_CSV, index=False)

    selected_names = [str(BASELINE_SPEC["strategy"])] + list(top["strategy"].head(8))
    selected_annual_equity(equity_by_name, selected_names).to_csv(ANNUAL_EQUITY_CSV, index=False)

    available_inputs = {
        name: info
        for name, info in availability.items()
        if info.get("status") == "available"
    }
    unavailable_inputs = {
        name: info
        for name, info in availability.items()
        if info.get("status") != "available"
    }
    materially_preserved = results[results["cagr_retention_pct"] >= 95.0]
    best_preserved = (
        materially_preserved.sort_values(
            ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe"],
            ascending=[False, False, False],
        )
        .head(1)
        .to_dict(orient="records")
    )
    metadata = {
        "market_source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "baseline": BASELINE_SPEC,
        "initial_capital": INITIAL_CAPITAL,
        "annual_inflow_usd": ANNUAL_INFLOW_USD,
        "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
        "lag_policy": {
            "daily_fred_and_yahoo": "forward-filled to market sessions and shifted one market session before use",
            "weekly_fred": "forward-filled to market sessions and shifted five market sessions before use",
            "monthly_fred_and_shiller": "forward-filled to market sessions and shifted 21 market sessions before use",
            "spx_trend": "SMA20/SMA50 computed from end-of-day close and shifted one market session before use",
        },
        "availability": availability,
        "available_input_count": int(len(available_inputs)),
        "unavailable_input_count": int(len(unavailable_inputs)),
        "tested_overlay_count": int(len(results)),
        "candidate_count_before_filters": int(len(specs)),
        "unemployment_benchmark": UNEMPLOYMENT_BENCHMARK,
        "best_materially_preserved_cagr": best_preserved[0] if best_preserved else None,
        "ranking_policy": (
            "Primary ordering ranks max drawdown improvement first, then CAGR retention, Sharpe, and practicality. "
            "Top CSV practical score also penalizes leverage churn and rewards public-data practicality."
        ),
        "breadth_limitations": {
            "policy": (
                "No point-in-time S&P 500 constituent breadth was reconstructed from current constituents. "
                "Only public index-level Yahoo breadth symbols were tested if they returned usable history."
            ),
            "tested_public_symbols": {
                name: {
                    "status": info.get("status"),
                    "ticker": info.get("ticker"),
                    "error": info.get("error", ""),
                }
                for name, info in availability.items()
                if name.startswith("BREADTH_")
            },
        },
        "real_yield_limitations": (
            "DFII10 TIPS real-yield history begins later than the full market sample. "
            "A CPI-trend proxy for real 10Y yield was also tested for broader history, but it is a rough public-data proxy."
        ),
    }
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    disp_cols = [
        "category",
        "strategy",
        "cagr",
        "cagr_retention_pct",
        "sharpe",
        "max_drawdown",
        "max_dd_improvement_pp",
        "overlay_active_pct",
        "pct_leverage_changed",
        "beats_unemployment_practical",
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    print("\nTop free/public overlays by max drawdown improvement:")
    print(results[disp_cols].head(15).to_string(index=False))
    print("\nTop free/public overlays by practical score:")
    print(top[disp_cols].head(12).to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {TOP_CSV}")
    print(f"Wrote {CATEGORY_BEST_CSV}")
    print(f"Wrote {SIGNAL_COVERAGE_CSV}")
    print(f"Wrote {ANNUAL_EQUITY_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network/data access failed: {exc}", file=sys.stderr)
        raise
