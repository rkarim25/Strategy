"""Second-pass fundamental and macro overlay tests for the guarded default.

This script focuses on combined and momentum-style overlays proposed after the
first-pass fundamental screen. External macro/fundamental data is lagged by the
loader in ``analyze_fundamental_overlay_filters``; technical and VIX conditions
are shifted one market session so an end-of-day signal affects the next session.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_fundamental_overlay_filters import (
    BASELINE_SPEC,
    OUTPUT_DIR,
    add_comparison_columns,
    apply_action,
    baseline_leverage,
    load_signal_data,
    run_backtest,
    selected_annual_equity,
)
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


RESULTS_CSV = OUTPUT_DIR / "smart_overlay_results.csv"
CATEGORY_BEST_CSV = OUTPUT_DIR / "smart_category_best.csv"
TOP_RANKED_CSV = OUTPUT_DIR / "smart_top_ranked.csv"
ANNUAL_EQUITY_CSV = OUTPUT_DIR / "smart_annual_equity_selected.csv"
SIGNAL_SUMMARY_CSV = OUTPUT_DIR / "smart_signal_summary.csv"
METADATA_JSON = OUTPUT_DIR / "smart_metadata.json"


@dataclass(frozen=True)
class SmartOverlaySpec:
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


def add_market_context(prices: pd.DataFrame, signals: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    out = signals.copy()
    availability: dict[str, dict[str, str]] = {}
    close = prices["spx_close"]

    out["SPX_BELOW_SMA20"] = prior_session(close < close.rolling(20, min_periods=20).mean())
    out["SPX_BELOW_SMA50"] = prior_session(close < close.rolling(50, min_periods=50).mean())
    out["SPX_ABOVE_SMA20"] = prior_session(close > close.rolling(20, min_periods=20).mean())
    out["SPX_ABOVE_SMA50"] = prior_session(close > close.rolling(50, min_periods=50).mean())
    out["SPX_ABOVE_SMA20_SMA50"] = out["SPX_ABOVE_SMA20"] & out["SPX_ABOVE_SMA50"]
    out["SPX_RET_21D"] = prior_session(close.pct_change(21))
    availability["SPX_TREND"] = {
        "status": "available",
        "source": "Yahoo Finance ^GSPC via project data_manager.load_backtest_data",
        "raw_start": prices.index[0].date().isoformat(),
        "raw_end": prices.index[-1].date().isoformat(),
        "lag": "1 market session",
    }

    try:
        raw = yf.download(
            "^VIX",
            start=prices.index[0].strftime("%Y-%m-%d"),
            end=(prices.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            raise ValueError("No data returned for ^VIX")
        close_raw = raw["Close"]
        if isinstance(close_raw, pd.DataFrame):
            close_raw = close_raw.iloc[:, 0]
        vix = pd.to_numeric(close_raw, errors="coerce").dropna().sort_index()
        out["VIX"] = prior_session(vix.reindex(prices.index).ffill())
        out["VIX_ELEVATED"] = out["VIX"] >= 25.0
        out["VIX_HIGH"] = out["VIX"] >= 30.0
        availability["VIX"] = {
            "status": "available",
            "source": "Yahoo Finance ^VIX",
            "raw_start": vix.index[0].date().isoformat(),
            "raw_end": vix.index[-1].date().isoformat(),
            "lag": "1 market session",
        }
    except Exception as exc:  # noqa: BLE001 - VIX is useful but not required.
        availability["VIX"] = {"status": "unavailable", "error": str(exc)}

    return out, availability


def add_derived_signals(signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()
    if "HY_OAS" in out:
        out["HY_WIDEN_21D_50BP"] = out["HY_OAS"].diff(21) > 0.005
        out["HY_WIDEN_63D_100BP"] = out["HY_OAS"].diff(63) > 0.010
        out["HY_STOP_WIDENING_21D"] = out["HY_OAS"].diff(21) <= 0.0
    if "IG_OAS" in out:
        out["IG_WIDEN_21D_15BP"] = out["IG_OAS"].diff(21) > 0.0015
        out["IG_WIDEN_63D_30BP"] = out["IG_OAS"].diff(63) > 0.003
        out["IG_STOP_WIDENING_21D"] = out["IG_OAS"].diff(21) <= 0.0
    if "UNRATE" in out:
        out["UNRATE_RISING_3M"] = out["UNRATE"].diff(63) >= 0.001
        out["UNRATE_RISING_6M"] = out["UNRATE"].diff(126) >= 0.002
    if "DGS10" in out:
        out["DGS10_FAST_RISE_21D"] = out["DGS10"].diff(21) >= 0.005
        out["DGS10_FAST_RISE_63D"] = out["DGS10"].diff(63) >= 0.0075
    if "T10Y3M" in out:
        was_inverted = out["T10Y3M"].rolling(126, min_periods=21).min() < 0.0
        out["CURVE_INVERTED"] = out["T10Y3M"] < 0.0
        out["CURVE_STEEPEN_AFTER_INVERSION"] = was_inverted & (out["T10Y3M"].diff(63) > 0.005)
    return out


def all_present(signals: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    return all(col in signals.columns for col in columns)


def defensive_regime(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    entry = entry.fillna(False).astype(bool)
    exit_ = exit_.fillna(False).astype(bool)
    active = []
    is_active = False
    for dt in entry.index:
        if is_active and bool(exit_.loc[dt]):
            is_active = False
        if bool(entry.loc[dt]):
            is_active = True
        active.append(is_active)
    return pd.Series(active, index=entry.index)


def signal_count(signals: pd.DataFrame, names: list[str]) -> pd.Series:
    available = [name for name in names if name in signals.columns]
    if not available:
        return pd.Series(0, index=signals.index, dtype=int)
    return signals[available].fillna(False).astype(bool).sum(axis=1)


def build_smart_specs(signals: pd.DataFrame) -> list[SmartOverlaySpec]:
    specs: list[SmartOverlaySpec] = []

    for credit_signal, label, data_series in [
        ("HY_WIDEN_21D_50BP", "HY OAS widening 21d > 50bp", ("HY_OAS", "SPX_BELOW_SMA20")),
        ("HY_WIDEN_63D_100BP", "HY OAS widening 63d > 100bp", ("HY_OAS", "SPX_BELOW_SMA50")),
        ("IG_WIDEN_21D_15BP", "IG OAS widening 21d > 15bp", ("IG_OAS", "SPX_BELOW_SMA20")),
        ("IG_WIDEN_63D_30BP", "IG OAS widening 63d > 30bp", ("IG_OAS", "SPX_BELOW_SMA50")),
    ]:
        if credit_signal in signals:
            trend_col = data_series[1]
            for action in ["cap_2x", "reduce_one_tier", "cap_1x"]:
                specs.append(
                    SmartOverlaySpec(
                        "Credit + trend",
                        f"{label} and SPX trend weak / {action}",
                        f"{label} plus {trend_col}",
                        "credit widening and SPX below SMA20/SMA50",
                        action,
                        lambda s, c=credit_signal, t=trend_col: s[c] & s[t],
                        data_series,
                        4 if action != "cap_1x" else 3,
                        "Caps only when spreads are widening and price trend is already weak.",
                    )
                )

    if "CAPE" in signals:
        for threshold in [30.0, 35.0, 40.0]:
            for action in ["cap_2x", "reduce_one_tier"]:
                specs.append(
                    SmartOverlaySpec(
                        "Valuation throttle",
                        f"CAPE > {threshold:g} throttle / {action}",
                        "CAPE valuation throttle",
                        f">{threshold:g}",
                        action,
                        lambda s, t=threshold: s["CAPE"] > t,
                        ("CAPE",),
                        5 if threshold >= 35.0 else 4,
                        "Valuation is used as a 3x-to-2x throttle, not a full risk-off exit.",
                    )
                )

    for column, label, action, practicality in [
        ("UNRATE_RISING_3M", "Unemployment rising 3m", "cap_2x", 4),
        ("UNRATE_RISING_6M", "Unemployment rising 6m", "cap_2x", 4),
        ("DGS10_FAST_RISE_21D", "10Y yield rising 21d > 50bp", "reduce_one_tier", 3),
        ("DGS10_FAST_RISE_63D", "10Y yield rising 63d > 75bp", "reduce_one_tier", 3),
        ("HY_WIDEN_21D_50BP", "HY OAS widening 21d > 50bp", "cap_2x", 3),
        ("HY_WIDEN_63D_100BP", "HY OAS widening 63d > 100bp", "cap_2x", 3),
        ("IG_WIDEN_21D_15BP", "IG OAS widening 21d > 15bp", "cap_2x", 3),
        ("IG_WIDEN_63D_30BP", "IG OAS widening 63d > 30bp", "cap_2x", 3),
    ]:
        if column in signals:
            specs.append(
                SmartOverlaySpec(
                    "Macro momentum",
                    f"{label} / {action}",
                    label,
                    "deterioration momentum",
                    action,
                    lambda s, c=column: s[c],
                    tuple([column.split("_")[0]]) if column.startswith(("HY", "IG")) else (column,),
                    practicality,
                    "Momentum-style macro deterioration rather than high/static levels.",
                )
            )

    regime_inputs = [
        "HY_WIDEN_21D_50BP",
        "IG_WIDEN_21D_15BP",
        "CURVE_INVERTED",
        "CURVE_STEEPEN_AFTER_INVERSION",
        "UNRATE_RISING_3M",
        "SPX_BELOW_SMA20",
        "SPX_BELOW_SMA50",
        "VIX_ELEVATED",
    ]
    available_regime_inputs = tuple(name for name in regime_inputs if name in signals.columns)
    if len(available_regime_inputs) >= 2:
        for min_count in [2, 3]:
            for action in ["cap_2x", "reduce_one_tier", "cap_1x"]:
                specs.append(
                    SmartOverlaySpec(
                        "Two-signal regime",
                        f"{min_count}+ deterioration signals / {action}",
                        "Credit, curve, labor, SPX trend, and VIX signal count",
                        f">={min_count} true",
                        action,
                        lambda s, m=min_count: signal_count(s, regime_inputs) >= m,
                        available_regime_inputs,
                        5 if min_count == 2 and action != "cap_1x" else 4,
                        "De-risks only after multiple independent stress signals agree.",
                    )
                )

        entry_2 = lambda s: signal_count(s, regime_inputs) >= 2
        exit_variants: list[tuple[str, Callable[[pd.DataFrame], pd.Series], tuple[str, ...]]] = [
            ("exit SPX > SMA20", lambda s: s["SPX_ABOVE_SMA20"], ("SPX_ABOVE_SMA20",)),
            ("exit SPX > SMA20+SMA50", lambda s: s["SPX_ABOVE_SMA20_SMA50"], ("SPX_ABOVE_SMA20_SMA50",)),
        ]
        if "HY_STOP_WIDENING_21D" in signals:
            exit_variants.append(
                (
                    "exit SPX > SMA20 and HY stops widening",
                    lambda s: s["SPX_ABOVE_SMA20"] & s["HY_STOP_WIDENING_21D"],
                    ("SPX_ABOVE_SMA20", "HY_STOP_WIDENING_21D"),
                )
            )
        if "IG_STOP_WIDENING_21D" in signals:
            exit_variants.append(
                (
                    "exit SPX > SMA20 and IG stops widening",
                    lambda s: s["SPX_ABOVE_SMA20"] & s["IG_STOP_WIDENING_21D"],
                    ("SPX_ABOVE_SMA20", "IG_STOP_WIDENING_21D"),
                )
            )
        for exit_name, exit_func, exit_cols in exit_variants:
            for action in ["cap_2x", "reduce_one_tier", "cap_1x"]:
                specs.append(
                    SmartOverlaySpec(
                        "Re-risk trigger",
                        f"2+ signal defensive mode, {exit_name} / {action}",
                        "Stateful defensive regime with explicit re-risk trigger",
                        "enter on >=2 signals; exit on trend/spread repair",
                        action,
                        lambda s, e=entry_2, x=exit_func: defensive_regime(e(s), x(s)),
                        available_regime_inputs + exit_cols,
                        5 if action != "cap_1x" else 4,
                        "Tests whether defensive mode should persist until price trend or spreads repair.",
                    )
                )

    return specs


def signal_summary(signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in [
        "SPX_BELOW_SMA20",
        "SPX_BELOW_SMA50",
        "VIX_ELEVATED",
        "HY_WIDEN_21D_50BP",
        "IG_WIDEN_21D_15BP",
        "CURVE_INVERTED",
        "CURVE_STEEPEN_AFTER_INVERSION",
        "UNRATE_RISING_3M",
        "DGS10_FAST_RISE_21D",
    ]:
        if column in signals:
            valid = signals[column].dropna()
            if valid.empty:
                continue
            if valid.dtype == bool or valid.dropna().isin([True, False]).all():
                active_pct = float(valid.astype(bool).mean() * 100.0)
                rows.append({"signal": column, "available_days": int(valid.count()), "active_pct": active_pct})
    return pd.DataFrame(rows)


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
    print("Loading lagged macro/fundamental signals...", flush=True)
    macro_signals, availability = load_signal_data(prices)
    signals, market_availability = add_market_context(prices, macro_signals)
    signals = add_derived_signals(signals)
    signals = signals[[c for c in signals.columns if signals[c].notna().any()]]
    availability.update(market_availability)

    specs = build_smart_specs(signals)
    rows: list[dict[str, float | int | str]] = []
    equity_by_name = {str(BASELINE_SPEC["strategy"]): baseline_equity}

    for spec in specs:
        if not all_present(signals, spec.data_series):
            continue
        condition = spec.condition(signals).reindex(prices.index).fillna(False).astype(bool)
        active_days = int(condition.sum())
        if active_days == 0:
            continue
        lev = apply_action(base_lev, condition, spec.action)
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
                "practicality": spec.practicality,
                "notes": spec.notes,
            },
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    if not rows:
        raise RuntimeError("No smart overlay candidates could be tested with the available signals.")

    results = add_comparison_columns(pd.DataFrame(rows), baseline_row)
    results["practical_rank_score"] = (
        results["max_dd_improvement_pp"] * 3.0
        + (results["cagr_retention_pct"] - 100.0) * 0.35
        + results["sharpe_delta"] * 5.0
        + results["practicality"].astype(float)
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
    baseline_df["practicality"] = 5
    baseline_df["notes"] = "Current default benchmark."
    baseline_df["practical_rank_score"] = 0.0

    category_best = (
        results.sort_values(
            ["category", "max_dd_improvement_pp", "cagr_retention_pct", "sharpe"],
            ascending=[True, False, False, False],
        )
        .groupby("category", as_index=False)
        .head(3)
    )
    top_ranked = results.sort_values(
        ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "practicality"],
        ascending=[False, False, False, False],
    ).head(15)

    pd.concat([baseline_df, results], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    category_best.to_csv(CATEGORY_BEST_CSV, index=False)
    top_ranked.to_csv(TOP_RANKED_CSV, index=False)

    selected_names = [str(BASELINE_SPEC["strategy"])] + list(top_ranked["strategy"].head(6))
    selected_annual_equity(equity_by_name, selected_names).to_csv(ANNUAL_EQUITY_CSV, index=False)
    sig_summary = signal_summary(signals)
    sig_summary.to_csv(SIGNAL_SUMMARY_CSV, index=False)

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
            "external_macro_fundamental": "reused first-pass loader: daily FRED shifted 1 market session; monthly FRED/Shiller shifted 21 market sessions",
            "market_trend_and_vix": "computed from end-of-day data and shifted 1 market session before use",
        },
        "availability": availability,
        "breadth_and_sector_availability": {
            "status": "not_tested",
            "reason": (
                "Reliable point-in-time S&P 500 constituent breadth, earnings revision breadth, "
                "forward EPS momentum, profit margin trend, and downgrade breadth were not available "
                "from the repo's free/public data sources. Testing current constituents from free data "
                "would introduce survivorship bias, so breadth was documented but not fabricated."
            ),
        },
        "tested_overlay_count": int(len(results)),
        "ranking_policy": "max drawdown improvement first, then CAGR retention, Sharpe, and practicality",
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
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    print("\nTop smart overlays by max drawdown improvement:")
    print(results[disp_cols].head(15).to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {CATEGORY_BEST_CSV}")
    print(f"Wrote {TOP_RANKED_CSV}")
    print(f"Wrote {ANNUAL_EQUITY_CSV}")
    print(f"Wrote {SIGNAL_SUMMARY_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network/data access failed: {exc}", file=sys.stderr)
        raise
