"""Test unemployment no-leverage overlays for the guarded default.

The baseline is the current site default:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard.

Monthly FRED UNRATE is shifted 21 market sessions before use, matching the
prior unemployment recovery-cap tests and avoiding lookahead.
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
    baseline_leverage,
    run_backtest,
)
from analyze_unemployment_recovery_caps import load_unemployment_signals, stateful_condition
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


RESULTS_CSV = OUTPUT_DIR / "unemployment_no_leverage_results.csv"
TOP_CSV = OUTPUT_DIR / "unemployment_no_leverage_top.csv"
SIGNAL_SUMMARY_CSV = OUTPUT_DIR / "unemployment_no_leverage_signal_summary.csv"
METADATA_JSON = OUTPUT_DIR / "unemployment_no_leverage_metadata.json"
PRIOR_CAP_CSV = OUTPUT_DIR / "unemployment_recovery_cap_top.csv"

Scope = Literal["three_x_only", "leveraged_tiers", "all_risky_to_cash"]


@dataclass(frozen=True)
class NoLeverageSpec:
    name: str
    category: str
    mode: str
    scope: Scope
    signal: str
    threshold: str
    action: str
    condition: Callable[[pd.DataFrame], pd.Series]
    data_series: tuple[str, ...]
    notes: str


def add_no_leverage_signals(signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()
    out["UNRATE_RISING_3M_OR_6M"] = out["UNRATE_RISING_3M"] | out["UNRATE_RISING_6M"]
    out["UNRATE_6M_NOT_RISING"] = out["UNRATE"].diff(126) <= 0.0
    out["UNRATE_3M_AND_6M_NOT_RISING"] = out["UNRATE_3M_NOT_RISING"] & out["UNRATE_6M_NOT_RISING"]
    return out


def apply_scope(base_leverage: pd.Series, condition: pd.Series, scope: Scope) -> pd.Series:
    cond = condition.reindex(base_leverage.index).fillna(False).astype(bool)
    lev = base_leverage.copy().astype(float)
    if scope == "three_x_only":
        mask = cond & (lev == 3.0)
        lev.loc[mask] = 1.0
    elif scope == "leveraged_tiers":
        mask = cond & (lev > 1.0)
        lev.loc[mask] = 1.0
    elif scope == "all_risky_to_cash":
        mask = cond & (lev > 0.0)
        lev.loc[mask] = 0.0
    else:
        raise ValueError(f"Unknown scope: {scope}")
    return lev


def build_specs() -> list[NoLeverageSpec]:
    specs: list[NoLeverageSpec] = []
    signal_defs = [
        (
            "UNRATE_RISING_3M",
            "UNRATE rising over 3 months",
            "3m change >= 0.10pp",
            lambda s: s["UNRATE_RISING_3M"],
            ("UNRATE_RISING_3M",),
        ),
        (
            "UNRATE_RISING_6M",
            "UNRATE rising over 6 months",
            "6m change >= 0.20pp",
            lambda s: s["UNRATE_RISING_6M"],
            ("UNRATE_RISING_6M",),
        ),
        (
            "UNRATE_RISING_3M_OR_6M",
            "UNRATE rising over 3m or 6m",
            "3m change >= 0.10pp or 6m change >= 0.20pp",
            lambda s: s["UNRATE_RISING_3M_OR_6M"],
            ("UNRATE_RISING_3M", "UNRATE_RISING_6M"),
        ),
    ]
    scope_labels = {
        "three_x_only": "3x only",
        "leveraged_tiers": "2x/3x to 1x",
    }

    for _, signal, threshold, condition, data_series in signal_defs:
        for scope, scope_label in scope_labels.items():
            specs.append(
                NoLeverageSpec(
                    name=f"{signal} no leverage cap max 1x ({scope_label})",
                    category="No-leverage unemployment throttle",
                    mode="stateless",
                    scope=scope,
                    signal=signal,
                    threshold=threshold,
                    action="cap_1x",
                    condition=condition,
                    data_series=data_series,
                    notes="When active, baseline leveraged exposure is reduced to 1x; cash and existing 1x are preserved.",
                )
            )

    exit_variants = [
        (
            "exit when UNRATE 3m momentum stops rising",
            "UNRATE_3M_NOT_RISING",
            lambda s: s["UNRATE_3M_NOT_RISING"],
        ),
        ("exit when SPX > SMA20", "SPX_ABOVE_SMA20", lambda s: s["SPX_ABOVE_SMA20"]),
        ("exit when SPX > SMA50", "SPX_ABOVE_SMA50", lambda s: s["SPX_ABOVE_SMA50"]),
    ]
    for exit_label, exit_col, exit_func in exit_variants:
        for scope, scope_label in scope_labels.items():
            specs.append(
                NoLeverageSpec(
                    name=f"Stateful 3m UNRATE no leverage cap max 1x, {exit_label} ({scope_label})",
                    category="Re-risk no-leverage unemployment throttle",
                    mode="stateful",
                    scope=scope,
                    signal="Enter on UNRATE rising over 3 months; lift cap on repair trigger",
                    threshold=f"enter 3m change >= 0.10pp; {exit_label}",
                    action="cap_1x",
                    condition=lambda s, x=exit_func: stateful_condition(s["UNRATE_RISING_3M"], x(s)),
                    data_series=("UNRATE_RISING_3M", exit_col),
                    notes="Persists the 1x leverage cap until the selected re-risk trigger fires.",
                )
            )

    for _, signal, threshold, condition, data_series in signal_defs:
        specs.append(
            NoLeverageSpec(
                name=f"{signal} force cash (severe comparison)",
                category="Severe cash comparison",
                mode="stateless",
                scope="all_risky_to_cash",
                signal=signal,
                threshold=threshold,
                action="force_cash",
                condition=condition,
                data_series=data_series,
                notes="Severe comparison only: rising unemployment forces cash rather than merely removing leverage.",
            )
        )

    return specs


def load_prior_cap_2x() -> dict[str, float | str] | None:
    if not PRIOR_CAP_CSV.exists():
        return None
    prior = pd.read_csv(PRIOR_CAP_CSV)
    target = prior[prior["strategy"].eq("Unemployment rising 3m cap max 2x (3x only)")]
    if target.empty:
        target = prior.sort_values("practical_rank_score", ascending=False).head(1)
    row = target.iloc[0]
    return {
        "strategy": str(row["strategy"]),
        "cagr": float(row["cagr"]),
        "max_drawdown": float(row["max_drawdown"]),
        "cagr_retention_pct": float(row["cagr_retention_pct"]),
        "max_dd_improvement_pp": float(row["max_dd_improvement_pp"]),
    }


def signal_summary(signals: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in [
        ("UNRATE_RISING_3M", "UNRATE 3m change >= 0.10pp"),
        ("UNRATE_RISING_6M", "UNRATE 6m change >= 0.20pp"),
        ("UNRATE_RISING_3M_OR_6M", "UNRATE 3m or 6m rising"),
        ("UNRATE_3M_NOT_RISING", "UNRATE 3m change <= 0.00pp"),
        ("UNRATE_6M_NOT_RISING", "UNRATE 6m change <= 0.00pp"),
        ("SPX_ABOVE_SMA20", "SPX above SMA20"),
        ("SPX_ABOVE_SMA50", "SPX above SMA50"),
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


def add_prior_columns(df: pd.DataFrame, prior: dict[str, float | str] | None) -> pd.DataFrame:
    out = df.copy()
    if prior is None:
        out["prior_cap2x_cagr_delta_pp"] = pd.NA
        out["prior_cap2x_cagr_retention_pct"] = pd.NA
        out["prior_cap2x_dd_delta_pp"] = pd.NA
        return out
    prior_cagr = float(prior["cagr"])
    prior_dd = float(prior["max_drawdown"])
    out["prior_cap2x_cagr_delta_pp"] = (out["cagr"] - prior_cagr) * 100.0
    out["prior_cap2x_cagr_retention_pct"] = out["cagr"] / prior_cagr * 100.0
    out["prior_cap2x_dd_delta_pp"] = (out["max_drawdown"] - prior_dd) * 100.0
    return out


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, _ = run_backtest(
        prices,
        base_lev,
        str(BASELINE_SPEC["strategy"]),
        base_counts,
    )

    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print("Loading lagged FRED unemployment and shifted SPX trend signals...", flush=True)
    signals, availability = load_unemployment_signals(prices)
    signals = add_no_leverage_signals(signals)
    prior_cap_2x = load_prior_cap_2x()

    rows: list[dict[str, float | int | str]] = []
    for spec in build_specs():
        condition = spec.condition(signals).reindex(prices.index).fillna(False).astype(bool)
        lev = apply_scope(base_lev, condition, spec.scope)
        changed = lev != base_lev
        if not bool(changed.any()):
            continue
        row, _ = run_backtest(
            prices,
            lev,
            spec.name,
            {
                "category": spec.category,
                "mode": spec.mode,
                "scope": spec.scope,
                "signal": spec.signal,
                "threshold": spec.threshold,
                "action": spec.action,
                "overlay_active_days": int(condition.sum()),
                "overlay_active_pct": float(condition.mean() * 100.0),
                "cap_1x_active_days": int((condition & (spec.scope != "all_risky_to_cash")).sum()),
                "force_cash_active_days": int((condition & (spec.scope == "all_risky_to_cash")).sum()),
                "avg_leverage": float(lev.mean()),
                "pct_leverage_changed": float(changed.mean() * 100.0),
                "pct_2x_days_changed": float(((base_lev == 2.0) & changed).sum() / max((base_lev == 2.0).sum(), 1) * 100.0),
                "pct_3x_days_changed": float(((base_lev == 3.0) & changed).sum() / max((base_lev == 3.0).sum(), 1) * 100.0),
                "notes": spec.notes,
            },
        )
        rows.append(row)

    if not rows:
        raise RuntimeError("No unemployment no-leverage candidates changed baseline leverage.")

    results = add_comparison_columns(pd.DataFrame(rows), baseline_row)
    results = add_prior_columns(results, prior_cap_2x)
    results["maintains_cagr_90"] = results["cagr_retention_pct"] >= 90.0
    results["maintains_cagr_95"] = results["cagr_retention_pct"] >= 95.0
    results["improves_drawdown"] = results["max_dd_improvement_pp"] > 0.0
    results["practical_rank_score"] = (
        results["max_dd_improvement_pp"] * 3.0
        + (results["cagr_retention_pct"] - 100.0) * 0.35
        + results["sharpe_delta"] * 5.0
        - results["pct_leverage_changed"] * 0.03
    )

    baseline_df = add_comparison_columns(pd.DataFrame([baseline_row]), baseline_row)
    baseline_df = add_prior_columns(baseline_df, prior_cap_2x)
    baseline_df["category"] = "Baseline"
    baseline_df["mode"] = "baseline"
    baseline_df["scope"] = "n/a"
    baseline_df["signal"] = "Current default strategy"
    baseline_df["threshold"] = "n/a"
    baseline_df["action"] = "n/a"
    baseline_df["overlay_active_days"] = 0
    baseline_df["overlay_active_pct"] = 0.0
    baseline_df["cap_1x_active_days"] = 0
    baseline_df["force_cash_active_days"] = 0
    baseline_df["avg_leverage"] = float(base_lev.mean())
    baseline_df["pct_leverage_changed"] = 0.0
    baseline_df["pct_2x_days_changed"] = 0.0
    baseline_df["pct_3x_days_changed"] = 0.0
    baseline_df["notes"] = "Current default benchmark."
    baseline_df["maintains_cagr_90"] = True
    baseline_df["maintains_cagr_95"] = True
    baseline_df["improves_drawdown"] = False
    baseline_df["practical_rank_score"] = 0.0

    ordered = results.sort_values(
        ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "pct_leverage_changed"],
        ascending=[False, False, False, True],
    )
    top = results.sort_values(
        ["practical_rank_score", "max_dd_improvement_pp", "cagr_retention_pct"],
        ascending=[False, False, False],
    ).head(12)

    pd.concat([baseline_df, ordered], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    top.to_csv(TOP_CSV, index=False)
    signal_summary(signals).to_csv(SIGNAL_SUMMARY_CSV, index=False)

    metadata = {
        "market_source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "baseline": BASELINE_SPEC,
        "prior_cap_2x_comparison": prior_cap_2x,
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
            "UNRATE_RISING_3M_OR_6M": "Either 3m or 6m lagged UNRATE rising trigger is active",
        },
        "scope_definitions": {
            "three_x_only": "Only baseline 3x exposure is reduced to 1x.",
            "leveraged_tiers": "Baseline 2x and 3x exposure is reduced to 1x; cash and existing 1x are preserved.",
            "all_risky_to_cash": "Severe comparison only: any baseline risky exposure is forced to cash.",
        },
        "availability": availability,
        "tested_overlay_count": int(len(results)),
        "ranking_policy": "practical score weights max drawdown improvement, CAGR retention, Sharpe delta, and modestly penalizes leverage churn",
    }
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    disp_cols = [
        "category",
        "mode",
        "scope",
        "strategy",
        "cagr",
        "cagr_retention_pct",
        "max_drawdown",
        "max_dd_improvement_pp",
        "prior_cap2x_cagr_delta_pp",
        "prior_cap2x_dd_delta_pp",
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    if prior_cap_2x is not None:
        print("\nPrior cap-to-2x comparison:")
        print(pd.DataFrame([prior_cap_2x]).to_string(index=False))
    print("\nTop unemployment no-leverage overlays by practical score:")
    print(top[disp_cols].to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {TOP_CSV}")
    print(f"Wrote {SIGNAL_SUMMARY_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network/data access failed: {exc}", file=sys.stderr)
        raise
