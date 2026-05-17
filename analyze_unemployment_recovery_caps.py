"""Focused unemployment recovery cap tests for the guarded default.

The baseline is the current site default:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard.

This pass tests unemployment-triggered leverage throttles only during recovery
tiers, using lagged FRED UNRATE and shifted SPX trend signals to avoid lookahead.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import pandas as pd

from analyze_fundamental_overlay_filters import (
    BASELINE_SPEC,
    OUTPUT_DIR,
    add_comparison_columns,
    align_signal,
    baseline_leverage,
    fetch_fred_series,
    run_backtest,
    selected_annual_equity,
)
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


RESULTS_CSV = OUTPUT_DIR / "unemployment_recovery_cap_results.csv"
TOP_CSV = OUTPUT_DIR / "unemployment_recovery_cap_top.csv"
ANNUAL_EQUITY_CSV = OUTPUT_DIR / "unemployment_recovery_cap_annual_equity_selected.csv"
SIGNAL_SUMMARY_CSV = OUTPUT_DIR / "unemployment_recovery_cap_signal_summary.csv"
METADATA_JSON = OUTPUT_DIR / "unemployment_recovery_cap_metadata.json"

Scope = Literal["all_recovery", "three_x_only"]


@dataclass(frozen=True)
class RecoveryCapSpec:
    name: str
    category: str
    mode: str
    cap_scope: Scope
    cap_level: float | None
    signal: str
    threshold: str
    condition: Callable[[pd.DataFrame], pd.Series] | None
    cap_series: Callable[[pd.DataFrame], pd.Series] | None
    data_series: tuple[str, ...]
    notes: str


def prior_session(series: pd.Series) -> pd.Series:
    return series.shift(1)


def load_unemployment_signals(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    signals = pd.DataFrame(index=prices.index)
    availability: dict[str, dict[str, str]] = {}

    raw = fetch_fred_series("UNRATE")
    signals["UNRATE"] = align_signal(prices.index, raw, lag_sessions=21, scale=0.01)
    availability["UNRATE"] = {
        "status": "available",
        "source": "Civilian unemployment rate, FRED",
        "raw_start": raw.index[0].date().isoformat(),
        "raw_end": raw.index[-1].date().isoformat(),
        "lag": "21 market sessions after monthly observation date",
    }

    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    signals["SPX_BELOW_SMA50"] = prior_session(close < sma50)
    signals["SPX_ABOVE_SMA20"] = prior_session(close > sma20)
    signals["SPX_ABOVE_SMA50"] = prior_session(close > sma50)
    availability["SPX_TREND"] = {
        "status": "available",
        "source": "Yahoo Finance ^GSPC via project data_manager.load_backtest_data",
        "raw_start": prices.index[0].date().isoformat(),
        "raw_end": prices.index[-1].date().isoformat(),
        "lag": "1 market session",
    }

    signals["UNRATE_RISING_3M"] = signals["UNRATE"].diff(63) >= 0.001
    signals["UNRATE_RISING_6M"] = signals["UNRATE"].diff(126) >= 0.002
    signals["UNRATE_3M_NOT_RISING"] = signals["UNRATE"].diff(63) <= 0.0
    signals["SEVERE_UNEMPLOYMENT_TREND"] = signals["UNRATE_RISING_6M"] & signals["SPX_BELOW_SMA50"]
    return signals, availability


def stateful_condition(entry: pd.Series, exit_: pd.Series) -> pd.Series:
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


def stateful_combined_cap(signals: pd.DataFrame, exit_condition: pd.Series) -> pd.Series:
    rising_3m = signals["UNRATE_RISING_3M"].fillna(False).astype(bool)
    severe = signals["SEVERE_UNEMPLOYMENT_TREND"].fillna(False).astype(bool)
    exit_condition = exit_condition.reindex(signals.index).fillna(False).astype(bool)

    caps: list[float] = []
    active_cap: float | None = None
    for dt in signals.index:
        if active_cap is not None and bool(exit_condition.loc[dt]):
            active_cap = None
        if bool(severe.loc[dt]):
            active_cap = 1.0
        elif bool(rising_3m.loc[dt]) and active_cap is None:
            active_cap = 2.0
        caps.append(active_cap if active_cap is not None else 3.0)
    return pd.Series(caps, index=signals.index)


def apply_cap(base_leverage: pd.Series, cap: pd.Series | float, scope: Scope) -> pd.Series:
    if isinstance(cap, pd.Series):
        cap_series = cap.reindex(base_leverage.index).fillna(3.0).astype(float)
    else:
        cap_series = pd.Series(float(cap), index=base_leverage.index)

    lev = base_leverage.copy().astype(float)
    if scope == "all_recovery":
        mask = lev > 1.0
    elif scope == "three_x_only":
        mask = lev == 3.0
    else:
        raise ValueError(f"Unknown cap scope: {scope}")
    lev.loc[mask] = pd.concat([lev.loc[mask], cap_series.loc[mask]], axis=1).min(axis=1)
    return lev


def build_specs(signals: pd.DataFrame) -> list[RecoveryCapSpec]:
    specs: list[RecoveryCapSpec] = []
    scope_labels: dict[Scope, str] = {
        "all_recovery": "all recovery leverage",
        "three_x_only": "3x only",
    }

    for scope in ["three_x_only", "all_recovery"]:
        specs.append(
            RecoveryCapSpec(
                name=f"Unemployment rising 3m cap max 2x ({scope_labels[scope]})",
                category="3m unemployment throttle",
                mode="stateless",
                cap_scope=scope,
                cap_level=2.0,
                signal="UNRATE rising over 3 months",
                threshold="3m change >= 0.10pp",
                condition=lambda s: s["UNRATE_RISING_3M"],
                cap_series=None,
                data_series=("UNRATE_RISING_3M",),
                notes="Blocks only baseline 3x exposure; 0x/1x/2x are preserved.",
            )
        )
        specs.append(
            RecoveryCapSpec(
                name=f"Unemployment rising 6m and SPX below SMA50 cap max 1x ({scope_labels[scope]})",
                category="Conditional severe cap",
                mode="stateless",
                cap_scope=scope,
                cap_level=1.0,
                signal="UNRATE rising 6m plus SPX below SMA50",
                threshold="6m change >= 0.20pp and SPX < SMA50",
                condition=lambda s: s["SEVERE_UNEMPLOYMENT_TREND"],
                cap_series=None,
                data_series=("UNRATE_RISING_6M", "SPX_BELOW_SMA50"),
                notes="Severe condition tests whether 2x/3x recovery leverage should be cut to 1x.",
            )
        )
        specs.append(
            RecoveryCapSpec(
                name=f"Two-stage unemployment cap: 3m to 2x, severe to 1x ({scope_labels[scope]})",
                category="Combined two-stage cap",
                mode="stateless",
                cap_scope=scope,
                cap_level=None,
                signal="UNRATE rising 3m; severe if 6m rising and SPX below SMA50",
                threshold="3m >= 0.10pp; severe 6m >= 0.20pp and SPX < SMA50",
                condition=None,
                cap_series=lambda s: pd.Series(3.0, index=s.index)
                .mask(s["UNRATE_RISING_3M"], 2.0)
                .mask(s["SEVERE_UNEMPLOYMENT_TREND"], 1.0),
                data_series=("UNRATE_RISING_3M", "UNRATE_RISING_6M", "SPX_BELOW_SMA50"),
                notes="Stateless two-stage rule: 3m labor deterioration blocks 3x; severe labor/trend stress caps at 1x.",
            )
        )

    exit_variants = [
        ("exit when SPX > SMA20", "SPX_ABOVE_SMA20", lambda s: s["SPX_ABOVE_SMA20"]),
        ("exit when SPX > SMA50", "SPX_ABOVE_SMA50", lambda s: s["SPX_ABOVE_SMA50"]),
        (
            "exit when UNRATE 3m momentum stops rising",
            "UNRATE_3M_NOT_RISING",
            lambda s: s["UNRATE_3M_NOT_RISING"],
        ),
    ]
    for exit_label, exit_col, exit_func in exit_variants:
        for scope in ["three_x_only", "all_recovery"]:
            specs.append(
                RecoveryCapSpec(
                    name=f"Stateful 3m unemployment cap max 2x, {exit_label} ({scope_labels[scope]})",
                    category="Re-risk stateful 3m",
                    mode="stateful",
                    cap_scope=scope,
                    cap_level=2.0,
                    signal="Enter on UNRATE rising 3m; re-risk on repair trigger",
                    threshold=f"enter 3m change >= 0.10pp; {exit_label}",
                    condition=lambda s, x=exit_func: stateful_condition(s["UNRATE_RISING_3M"], x(s)),
                    cap_series=None,
                    data_series=("UNRATE_RISING_3M", exit_col),
                    notes="Persists the 2x cap until the selected re-risk trigger fires.",
                )
            )
            specs.append(
                RecoveryCapSpec(
                    name=f"Stateful two-stage unemployment cap, {exit_label} ({scope_labels[scope]})",
                    category="Re-risk stateful two-stage",
                    mode="stateful",
                    cap_scope=scope,
                    cap_level=None,
                    signal="Enter 2x cap on 3m rising; 1x cap on severe condition; re-risk on repair trigger",
                    threshold=f"enter 3m/severe signals; {exit_label}",
                    condition=None,
                    cap_series=lambda s, x=exit_func: stateful_combined_cap(s, x(s)),
                    data_series=("UNRATE_RISING_3M", "UNRATE_RISING_6M", "SPX_BELOW_SMA50", exit_col),
                    notes="Persists the most defensive active cap until the selected re-risk trigger fires.",
                )
            )

    return specs


def signal_summary(signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in [
        ("UNRATE_RISING_3M", "UNRATE 3m change >= 0.10pp"),
        ("UNRATE_RISING_6M", "UNRATE 6m change >= 0.20pp"),
        ("SPX_BELOW_SMA50", "SPX below SMA50"),
        ("SEVERE_UNEMPLOYMENT_TREND", "UNRATE rising 6m and SPX below SMA50"),
        ("SPX_ABOVE_SMA20", "SPX above SMA20"),
        ("SPX_ABOVE_SMA50", "SPX above SMA50"),
        ("UNRATE_3M_NOT_RISING", "UNRATE 3m change <= 0.00pp"),
    ]:
        valid = signals[column].dropna()
        rows.append(
            {
                "signal": column,
                "label": label,
                "available_days": int(valid.count()),
                "active_days": int(valid.astype(bool).sum()),
                "active_pct": float(valid.astype(bool).mean() * 100.0),
            }
        )
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
    print("Loading lagged FRED unemployment and shifted SPX trend signals...", flush=True)
    signals, availability = load_unemployment_signals(prices)

    rows: list[dict[str, float | int | str]] = []
    equity_by_name = {str(BASELINE_SPEC["strategy"]): baseline_equity}
    for spec in build_specs(signals):
        if spec.cap_series is not None:
            cap = spec.cap_series(signals).reindex(prices.index).fillna(3.0).astype(float)
            lev = apply_cap(base_lev, cap, spec.cap_scope)
            active = cap < 3.0
            cap_1x_days = int((cap <= 1.0).sum())
            cap_2x_days = int(((cap > 1.0) & (cap < 3.0)).sum())
        elif spec.condition is not None and spec.cap_level is not None:
            condition = spec.condition(signals).reindex(prices.index).fillna(False).astype(bool)
            cap = pd.Series(3.0, index=prices.index).mask(condition, spec.cap_level)
            lev = apply_cap(base_lev, cap, spec.cap_scope)
            active = condition
            cap_1x_days = int((condition & (spec.cap_level <= 1.0)).sum())
            cap_2x_days = int((condition & (spec.cap_level > 1.0)).sum())
        else:
            raise ValueError(f"Incomplete spec: {spec.name}")

        changed = lev != base_lev
        if not bool(changed.any()):
            continue
        row, equity = run_backtest(
            prices,
            lev,
            spec.name,
            {
                "category": spec.category,
                "mode": spec.mode,
                "cap_scope": spec.cap_scope,
                "signal": spec.signal,
                "threshold": spec.threshold,
                "action": "dynamic_cap" if spec.cap_level is None else f"cap_{spec.cap_level:g}x",
                "overlay_active_days": int(active.sum()),
                "overlay_active_pct": float(active.mean() * 100.0),
                "cap_1x_active_days": cap_1x_days,
                "cap_2x_active_days": cap_2x_days,
                "avg_leverage": float(lev.mean()),
                "pct_leverage_changed": float(changed.mean() * 100.0),
                "pct_2x_days_changed": float(((base_lev == 2.0) & changed).sum() / max((base_lev == 2.0).sum(), 1) * 100.0),
                "pct_3x_days_changed": float(((base_lev == 3.0) & changed).sum() / max((base_lev == 3.0).sum(), 1) * 100.0),
                "notes": spec.notes,
            },
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    if not rows:
        raise RuntimeError("No unemployment recovery cap candidates changed baseline leverage.")

    results = add_comparison_columns(pd.DataFrame(rows), baseline_row)
    results["practical_rank_score"] = (
        results["max_dd_improvement_pp"] * 3.0
        + (results["cagr_retention_pct"] - 100.0) * 0.35
        + results["sharpe_delta"] * 5.0
        - results["pct_leverage_changed"] * 0.03
    )
    results = results.sort_values(
        ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "pct_leverage_changed"],
        ascending=[False, False, False, True],
    )

    baseline_df = add_comparison_columns(pd.DataFrame([baseline_row]), baseline_row)
    baseline_df["category"] = "Baseline"
    baseline_df["mode"] = "baseline"
    baseline_df["cap_scope"] = "n/a"
    baseline_df["signal"] = "Current default strategy"
    baseline_df["threshold"] = "n/a"
    baseline_df["action"] = "n/a"
    baseline_df["overlay_active_days"] = 0
    baseline_df["overlay_active_pct"] = 0.0
    baseline_df["cap_1x_active_days"] = 0
    baseline_df["cap_2x_active_days"] = 0
    baseline_df["avg_leverage"] = float(base_lev.mean())
    baseline_df["pct_leverage_changed"] = 0.0
    baseline_df["pct_2x_days_changed"] = 0.0
    baseline_df["pct_3x_days_changed"] = 0.0
    baseline_df["notes"] = "Current default benchmark."
    baseline_df["practical_rank_score"] = 0.0

    pd.concat([baseline_df, results], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    top = results.sort_values(
        ["practical_rank_score", "max_dd_improvement_pp", "cagr_retention_pct"],
        ascending=[False, False, False],
    ).head(12)
    top.to_csv(TOP_CSV, index=False)

    selected_names = [str(BASELINE_SPEC["strategy"])] + list(top["strategy"].head(6))
    selected_annual_equity(equity_by_name, selected_names).to_csv(ANNUAL_EQUITY_CSV, index=False)
    signal_summary(signals).to_csv(SIGNAL_SUMMARY_CSV, index=False)

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
            "unemployment": "FRED UNRATE monthly observations forward-filled to market sessions, then shifted 21 market sessions before use",
            "spx_trend": "SPX SMA20/SMA50 trend computed from end-of-day close and shifted one market session before use",
        },
        "unemployment_signal_definitions": {
            "UNRATE_RISING_3M": "Lagged UNRATE 63-session change >= 0.10 percentage points",
            "UNRATE_RISING_6M": "Lagged UNRATE 126-session change >= 0.20 percentage points",
            "UNRATE_3M_NOT_RISING": "Lagged UNRATE 63-session change <= 0.00 percentage points",
            "SEVERE_UNEMPLOYMENT_TREND": "UNRATE_RISING_6M and prior-session SPX below SMA50",
        },
        "scope_definitions": {
            "three_x_only": "Only baseline 3x recovery exposure can be reduced.",
            "all_recovery": "Baseline 2x and 3x recovery exposure can be reduced; cash and 1x base exposure are preserved.",
        },
        "availability": availability,
        "tested_overlay_count": int(len(results)),
        "ranking_policy": "practical score weights max drawdown improvement, CAGR retention, Sharpe delta, and modestly penalizes leverage churn",
        "paid_data_recommendation": {
            "need_paid_data": False,
            "reason": (
                "This specific unemployment momentum test is already covered by public, directly accessible FRED UNRATE. "
                "Paid data would matter more for point-in-time earnings revisions, forward EPS breadth, constituent-level "
                "breadth, layoff announcements, or real-time macro vintages than for the basic unemployment throttle."
            ),
            "potential_providers": [
                "ALFRED/FRED vintage data via St. Louis Fed for true real-time unemployment release vintages",
                "FactSet or Refinitiv I/B/E/S for point-in-time earnings revision breadth",
                "S&P Global/Compustat or Bloomberg for point-in-time index constituent and fundamental breadth",
            ],
            "access_note": "Direct access would require user-provided API credentials or a local data export for paid providers.",
        },
    }
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    disp_cols = [
        "category",
        "mode",
        "cap_scope",
        "strategy",
        "cagr",
        "cagr_retention_pct",
        "sharpe",
        "max_drawdown",
        "max_dd_improvement_pp",
        "pct_leverage_changed",
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    print("\nTop unemployment recovery caps by practical score:")
    print(top[disp_cols].to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {TOP_CSV}")
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
