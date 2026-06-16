"""Test labor-market leading indicators as defensive overlays.

Baseline is the current site default:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard.

The primary overlay action throttles only baseline 3x exposure to 2x when a
labor-stress trigger is active. A stricter max-1x variant is also tested for
comparison. FRED series are forward-filled to market sessions and lagged before
use: weekly data by five sessions and monthly data by 21 sessions.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from analyze_fundamental_overlay_filters import (
    BASELINE_SPEC,
    OUTPUT_DIR,
    add_comparison_columns,
    baseline_leverage,
    fetch_fred_series,
    run_backtest,
)
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


RESULTS_CSV = OUTPUT_DIR / "labor_lead_overlay_results.csv"
TOP_CSV = OUTPUT_DIR / "labor_lead_overlay_top.csv"
CATEGORY_BEST_CSV = OUTPUT_DIR / "labor_lead_category_best.csv"
METADATA_JSON = OUTPUT_DIR / "labor_lead_metadata.json"
SIGNAL_COVERAGE_CSV = OUTPUT_DIR / "labor_lead_signal_coverage.csv"

UNEMPLOYMENT_BENCHMARK = {
    "strategy": "Unemployment rising 3m cap max 2x (3x only)",
    "cagr": 0.37225809997277004,
    "max_drawdown": -0.2330864206300392,
    "sharpe": 3.2711461407981886,
    "cagr_retention_pct": 95.23092948938483,
    "max_dd_improvement_pp": 4.19853128059694,
}


@dataclass(frozen=True)
class LaborOverlaySpec:
    category: str
    name: str
    signal: str
    threshold: str
    action: str
    condition: Callable[[pd.DataFrame], pd.Series]
    data_series: tuple[str, ...]
    notes: str


def pct_change(series: pd.Series, sessions: int) -> pd.Series:
    return series.pct_change(sessions)


def align_observation_signal(
    market_index: pd.DatetimeIndex,
    series: pd.Series,
    *,
    lag_sessions: int,
    scale: float = 1.0,
) -> pd.Series:
    """As-of align macro observations even when release dates are not trading days."""
    source = series.sort_index()
    combined_index = market_index.union(source.index).sort_values()
    aligned = source.reindex(combined_index).ffill().reindex(market_index).shift(lag_sessions)
    if scale != 1.0:
        aligned = aligned * scale
    return aligned


def safe_bool(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    return series.reindex(index).fillna(False).astype(bool)


def add_fred_signal(
    prices: pd.DataFrame,
    signals: pd.DataFrame,
    availability: dict[str, dict[str, str]],
    label: str,
    candidates: tuple[tuple[str, str], ...],
    *,
    lag_sessions: int,
    scale: float = 1.0,
    transform: Callable[[pd.Series], pd.Series] | None = None,
    source_note: str,
) -> None:
    errors: list[str] = []
    for series_id, description in candidates:
        try:
            raw = fetch_fred_series(series_id)
            if transform is not None:
                raw = transform(raw).dropna()
            aligned = align_observation_signal(prices.index, raw, lag_sessions=lag_sessions, scale=scale)
            if aligned.notna().sum() == 0:
                raise ValueError("Aligned series has no overlap with market history")
            signals[label] = aligned
            availability[label] = {
                "status": "available",
                "series_id": series_id,
                "source": f"{description}, FRED",
                "source_note": source_note,
                "raw_start": raw.index[0].date().isoformat(),
                "raw_end": raw.index[-1].date().isoformat(),
                "lag": f"{lag_sessions} market sessions",
                "available_market_days": str(int(aligned.notna().sum())),
            }
            return
        except Exception as exc:  # noqa: BLE001 - candidate availability is part of the result.
            errors.append(f"{series_id}: {exc}")

    availability[label] = {
        "status": "unavailable",
        "series_id": ",".join(series_id for series_id, _ in candidates),
        "source": source_note,
        "error": "; ".join(errors),
    }


def load_labor_signals(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    signals = pd.DataFrame(index=prices.index)
    availability: dict[str, dict[str, str]] = {}

    add_fred_signal(
        prices,
        signals,
        availability,
        "INITIAL_CLAIMS_4W",
        (
            ("IC4WSA", "Initial claims 4-week moving average"),
            ("ICSA", "Initial claims, seasonally adjusted; transformed to 4-week average"),
        ),
        lag_sessions=5,
        transform=lambda s: s.rolling(4, min_periods=4).mean(),
        source_note="Weekly initial jobless claims; weekly data lagged one trading week.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "CONTINUING_CLAIMS_4W",
        (
            ("CC4WSA", "Continued claims 4-week moving average"),
            ("CCSA", "Continued claims, seasonally adjusted; transformed to 4-week average"),
        ),
        lag_sessions=5,
        transform=lambda s: s.rolling(4, min_periods=4).mean(),
        source_note="Weekly continued claims; weekly data lagged one trading week.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "TEMP_HELP",
        (
            ("TEMPHELPS", "Temporary help services employment"),
            ("CES6056132001", "Temporary help services employment"),
        ),
        lag_sessions=21,
        source_note="Monthly temporary help services employment; lagged 21 market sessions.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "WEEKLY_HOURS",
        (
            ("AWHAETP", "Average weekly hours of all employees, total private"),
            ("AWHNONAG", "Average weekly hours of production and nonsupervisory employees"),
        ),
        lag_sessions=21,
        source_note="Monthly average weekly hours; broad private series preferred where available.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "JOLTS_OPENINGS",
        (("JTSJOL", "JOLTS job openings"),),
        lag_sessions=21,
        source_note="Monthly JOLTS job openings; history begins in 2000 and is shorter than the market sample.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "JOLTS_QUITS",
        (("JTSQUR", "JOLTS quits rate"),),
        lag_sessions=21,
        source_note="Monthly JOLTS quits rate; history begins in 2000 and is shorter than the market sample.",
    )
    add_fred_signal(
        prices,
        signals,
        availability,
        "ISM_EMPLOYMENT",
        (("NAPMEI", "ISM Manufacturing Employment Index"),),
        lag_sessions=21,
        source_note="Monthly ISM manufacturing employment diffusion index; tested only if FRED returns usable free data.",
    )

    availability["CONFERENCE_BOARD_LABOR_DIFFERENTIAL"] = {
        "status": "unavailable",
        "source": "Conference Board Consumer Confidence labor differential",
        "error": "No free direct FRED series or project data source identified; generally requires Conference Board or vendor access.",
    }
    availability["CHALLENGER_JOB_CUTS"] = {
        "status": "unavailable",
        "source": "Challenger job-cut announcements",
        "error": "No free direct point-in-time series in existing project data/FRED access; direct history generally requires vendor or manual download access.",
    }

    return signals, availability


def add_derived_signals(signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()

    for col in ["INITIAL_CLAIMS_4W", "CONTINUING_CLAIMS_4W"]:
        if col in out:
            out[f"{col}_CHG_13W"] = pct_change(out[col], 63)
            out[f"{col}_CHG_26W"] = pct_change(out[col], 126)
            prefix = "CLAIMS" if col == "INITIAL_CLAIMS_4W" else "CONT_CLAIMS"
            for horizon, change_col in [("13W", f"{col}_CHG_13W"), ("26W", f"{col}_CHG_26W")]:
                for threshold in [0.05, 0.10, 0.15]:
                    out[f"{prefix}_RISE_{horizon}_{int(threshold * 100)}"] = out[change_col] >= threshold

    for col, prefix in [
        ("TEMP_HELP", "TEMPHELP"),
        ("WEEKLY_HOURS", "HOURS"),
        ("JOLTS_OPENINGS", "JOLTS_OPENINGS"),
        ("JOLTS_QUITS", "JOLTS_QUITS"),
    ]:
        if col in out:
            out[f"{col}_CHG_3M"] = pct_change(out[col], 63)
            out[f"{col}_CHG_6M"] = pct_change(out[col], 126)
            for horizon, change_col, thresholds in [
                ("3M", f"{col}_CHG_3M", [0.0, -0.01, -0.02] if col == "TEMP_HELP" else [0.0, -0.005, -0.01]),
                ("6M", f"{col}_CHG_6M", [-0.01, -0.02, -0.03] if col == "TEMP_HELP" else [0.0, -0.005, -0.01]),
            ]:
                for threshold in thresholds:
                    label = "0" if threshold == 0 else str(int(abs(threshold) * 1000)).rstrip("0")
                    out[f"{prefix}_FALL_{horizon}_{label}"] = out[change_col] <= threshold

    if "ISM_EMPLOYMENT" in out:
        out["ISM_EMP_BELOW_50"] = out["ISM_EMPLOYMENT"] < 50.0
        out["ISM_EMP_BELOW_50_AND_FALLING"] = (out["ISM_EMPLOYMENT"] < 50.0) & (out["ISM_EMPLOYMENT"].diff(63) < 0.0)

    composite_inputs = [
        col
        for col in [
            "CLAIMS_RISE_13W_10",
            "CONT_CLAIMS_RISE_13W_5",
            "TEMPHELP_FALL_3M_0",
            "HOURS_FALL_3M_0",
            "JOLTS_OPENINGS_FALL_3M_0",
            "JOLTS_QUITS_FALL_3M_0",
            "ISM_EMP_BELOW_50",
        ]
        if col in out
    ]
    if composite_inputs:
        out["LABOR_STRESS_COUNT"] = out[composite_inputs].fillna(False).astype(bool).sum(axis=1)
        out["LABOR_STRESS_2PLUS"] = out["LABOR_STRESS_COUNT"] >= 2
        out["LABOR_STRESS_3PLUS"] = out["LABOR_STRESS_COUNT"] >= 3

    if {"CLAIMS_RISE_13W_10", "TEMPHELP_FALL_3M_0"}.issubset(out.columns):
        out["CLAIMS_PLUS_TEMPHELP"] = out["CLAIMS_RISE_13W_10"] & out["TEMPHELP_FALL_3M_0"]
    if {"CLAIMS_RISE_13W_10", "HOURS_FALL_3M_0"}.issubset(out.columns):
        out["CLAIMS_PLUS_HOURS"] = out["CLAIMS_RISE_13W_10"] & out["HOURS_FALL_3M_0"]
    if {"CLAIMS_RISE_13W_10", "CONT_CLAIMS_RISE_13W_5"}.issubset(out.columns):
        out["CLAIMS_PLUS_CONTINUING"] = out["CLAIMS_RISE_13W_10"] & out["CONT_CLAIMS_RISE_13W_5"]

    return out


def apply_overlay(base_leverage: pd.Series, condition: pd.Series, action: str) -> pd.Series:
    cond = condition.reindex(base_leverage.index).fillna(False).astype(bool)
    lev = base_leverage.copy().astype(float)
    if action == "cap_3x_to_2x":
        lev.loc[cond & (lev == 3.0)] = 2.0
    elif action == "cap_max_1x":
        lev.loc[cond & (lev > 1.0)] = 1.0
    else:
        raise ValueError(f"Unknown action: {action}")
    return lev


def add_action_specs(
    specs: list[LaborOverlaySpec],
    *,
    category: str,
    base_name: str,
    signal: str,
    threshold: str,
    signal_col: str,
    notes: str,
    include_1x: bool = True,
) -> None:
    actions = [("cap_3x_to_2x", "3x-only cap to 2x")]
    if include_1x:
        actions.append(("cap_max_1x", "max 1x cap"))
    for action, action_label in actions:
        specs.append(
            LaborOverlaySpec(
                category=category,
                name=f"{base_name} / {action_label}",
                signal=signal,
                threshold=threshold,
                action=action,
                condition=lambda s, c=signal_col: s[c],
                data_series=(signal_col,),
                notes=notes,
            )
        )


def build_specs(signals: pd.DataFrame) -> list[LaborOverlaySpec]:
    specs: list[LaborOverlaySpec] = []

    for prefix, category, signal, base in [
        ("CLAIMS", "Initial claims", "Initial jobless claims 4-week average", "Initial claims 4w avg rising"),
        ("CONT_CLAIMS", "Continuing claims", "Continuing claims 4-week average", "Continuing claims 4w avg rising"),
    ]:
        for horizon in ["13W", "26W"]:
            for threshold in [5, 10, 15]:
                col = f"{prefix}_RISE_{horizon}_{threshold}"
                if col in signals:
                    add_action_specs(
                        specs,
                        category=category,
                        base_name=f"{base} {horizon.lower()} >= {threshold}%",
                        signal=signal,
                        threshold=f"{horizon.lower()} change >= {threshold}%",
                        signal_col=col,
                        notes="Weekly claims data are lagged five market sessions before affecting leverage.",
                    )

    for prefix, category, signal, base, horizons in [
        ("TEMPHELP", "Temporary help", "Temporary help services employment", "Temporary help employment falling", ["3M", "6M"]),
        ("HOURS", "Average weekly hours", "Average weekly hours", "Average weekly hours falling", ["3M", "6M"]),
        ("JOLTS_OPENINGS", "JOLTS", "JOLTS job openings", "JOLTS openings falling", ["3M", "6M"]),
        ("JOLTS_QUITS", "JOLTS", "JOLTS quits rate", "JOLTS quits falling", ["3M", "6M"]),
    ]:
        for horizon in horizons:
            for suffix, label in [("0", "any decline"), ("1", ">= 1% decline"), ("2", ">= 2% decline"), ("5", ">= 0.5% decline")]:
                col = f"{prefix}_FALL_{horizon}_{suffix}"
                if col in signals:
                    add_action_specs(
                        specs,
                        category=category,
                        base_name=f"{base} {horizon.lower()} {label}",
                        signal=signal,
                        threshold=f"{horizon.lower()} {label}",
                        signal_col=col,
                        notes="Monthly labor data are lagged 21 market sessions before affecting leverage.",
                    )

    if "ISM_EMP_BELOW_50" in signals:
        add_action_specs(
            specs,
            category="ISM employment",
            base_name="ISM employment below 50",
            signal="ISM manufacturing employment index",
            threshold="< 50",
            signal_col="ISM_EMP_BELOW_50",
            notes="ISM employment is a monthly diffusion index lagged 21 market sessions.",
        )
    if "ISM_EMP_BELOW_50_AND_FALLING" in signals:
        add_action_specs(
            specs,
            category="ISM employment",
            base_name="ISM employment below 50 and falling",
            signal="ISM manufacturing employment index",
            threshold="< 50 and 3m change < 0",
            signal_col="ISM_EMP_BELOW_50_AND_FALLING",
            notes="ISM employment is used only when both below 50 and deteriorating.",
        )

    combo_specs = [
        ("CLAIMS_PLUS_TEMPHELP", "Combinations", "Initial claims rising plus temp help falling", "claims 13w >= 10% and temp help down 3m"),
        ("CLAIMS_PLUS_HOURS", "Combinations", "Initial claims rising plus weekly hours falling", "claims 13w >= 10% and hours down 3m"),
        ("CLAIMS_PLUS_CONTINUING", "Combinations", "Initial claims plus continuing claims rising", "claims 13w >= 10% and continuing claims 13w >= 5%"),
        ("LABOR_STRESS_2PLUS", "Labor composite", "2-of-N labor stress composite", "at least two leading labor stress signals"),
        ("LABOR_STRESS_3PLUS", "Labor composite", "3-of-N labor stress composite", "at least three leading labor stress signals"),
    ]
    for col, category, name, threshold in combo_specs:
        if col in signals:
            add_action_specs(
                specs,
                category=category,
                base_name=name,
                signal="claims, continuing claims, temp help, hours, JOLTS, ISM",
                threshold=threshold,
                signal_col=col,
                notes="Composite/combination signal uses only components available in the current free data pull.",
            )

    return specs


def all_present(signals: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    return all(col in signals.columns for col in columns)


def signal_coverage(signals: pd.DataFrame, availability: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name, info in availability.items():
        matching_cols = [name] if name in signals.columns else [col for col in signals.columns if col.startswith(name)]
        valid_days = 0
        first_valid = ""
        last_valid = ""
        active_days = ""
        active_pct = ""
        if matching_cols:
            valid_mask = signals[matching_cols].notna().any(axis=1)
            valid_days = int(valid_mask.sum())
            if valid_mask.any():
                first_valid = signals.index[valid_mask][0].date().isoformat()
                last_valid = signals.index[valid_mask][-1].date().isoformat()
            bool_cols = [col for col in matching_cols if signals[col].dropna().isin([True, False]).all()]
            if bool_cols:
                active = signals[bool_cols].fillna(False).astype(bool).any(axis=1)
                active_days = int(active.sum())
                active_pct = float(active.mean() * 100.0)
        rows.append(
            {
                "signal": name,
                "status": info.get("status", ""),
                "source": info.get("source", ""),
                "series_or_ticker": info.get("series_id", ""),
                "raw_start": info.get("raw_start", ""),
                "raw_end": info.get("raw_end", ""),
                "lag": info.get("lag", ""),
                "valid_market_days": valid_days,
                "first_valid_market_day": first_valid,
                "last_valid_market_day": last_valid,
                "active_days_any_derived": active_days,
                "active_pct_any_derived": active_pct,
                "error": info.get("error", ""),
            }
        )

    for col in [
        "CLAIMS_RISE_13W_10",
        "CONT_CLAIMS_RISE_13W_5",
        "TEMPHELP_FALL_3M_0",
        "HOURS_FALL_3M_0",
        "JOLTS_OPENINGS_FALL_3M_0",
        "JOLTS_QUITS_FALL_3M_0",
        "ISM_EMP_BELOW_50",
        "LABOR_STRESS_2PLUS",
        "LABOR_STRESS_3PLUS",
    ]:
        if col in signals:
            valid = signals[col].dropna().astype(bool)
            rows.append(
                {
                    "signal": col,
                    "status": "derived",
                    "source": "Derived from available lagged labor inputs",
                    "series_or_ticker": "",
                    "raw_start": "",
                    "raw_end": "",
                    "lag": "inherits source lag",
                    "valid_market_days": int(valid.count()),
                    "first_valid_market_day": signals.index[signals[col].notna()][0].date().isoformat(),
                    "last_valid_market_day": signals.index[signals[col].notna()][-1].date().isoformat(),
                    "active_days_any_derived": int(valid.sum()),
                    "active_pct_any_derived": float(valid.mean() * 100.0),
                    "error": "",
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, baseline_equity = run_backtest(prices, base_lev, str(BASELINE_SPEC["strategy"]), base_counts)

    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print("Loading lagged FRED labor-market leading signals...", flush=True)
    signals, availability = load_labor_signals(prices)
    signals = add_derived_signals(signals)
    signals = signals[[col for col in signals.columns if signals[col].notna().any()]]

    specs = build_specs(signals)
    rows: list[dict[str, float | int | str | bool]] = []
    equity_by_name = {str(BASELINE_SPEC["strategy"]): baseline_equity}
    for spec in specs:
        if not all_present(signals, spec.data_series):
            continue
        condition = safe_bool(spec.condition(signals), prices.index)
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
                "pct_2x_days_changed": float(((base_lev == 2.0) & changed).sum() / max((base_lev == 2.0).sum(), 1) * 100.0),
                "pct_3x_days_changed": float(((base_lev == 3.0) & changed).sum() / max((base_lev == 3.0).sum(), 1) * 100.0),
                "notes": spec.notes,
            },
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    if not rows:
        raise RuntimeError("No labor-leading overlay candidates changed baseline leverage.")

    results = add_comparison_columns(pd.DataFrame(rows), baseline_row)
    results["beats_unrate_3m_dd"] = results["max_drawdown"] > UNEMPLOYMENT_BENCHMARK["max_drawdown"]
    results["beats_unrate_3m_cagr"] = results["cagr"] >= UNEMPLOYMENT_BENCHMARK["cagr"]
    results["beats_unrate_3m_practical"] = (
        results["beats_unrate_3m_dd"]
        & (results["cagr_retention_pct"] >= UNEMPLOYMENT_BENCHMARK["cagr_retention_pct"])
        & (results["sharpe"] >= UNEMPLOYMENT_BENCHMARK["sharpe"])
    )
    results["meets_95pct_cagr_retention"] = results["cagr_retention_pct"] >= 95.0
    results["meets_90pct_cagr_retention"] = results["cagr_retention_pct"] >= 90.0
    results["practical_rank_score"] = (
        results["max_dd_improvement_pp"] * 3.0
        + (results["cagr_retention_pct"] - 100.0) * 0.45
        + results["sharpe_delta"] * 6.0
        - results["pct_leverage_changed"] * 0.035
        + (results["action"] == "cap_3x_to_2x").astype(float) * 2.0
    )
    results = results.sort_values(
        ["max_dd_improvement_pp", "cagr_retention_pct", "sharpe", "pct_leverage_changed"],
        ascending=[False, False, False, True],
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
    baseline_df["notes"] = "Current default benchmark."
    baseline_df["beats_unrate_3m_dd"] = False
    baseline_df["beats_unrate_3m_cagr"] = False
    baseline_df["beats_unrate_3m_practical"] = False
    baseline_df["meets_95pct_cagr_retention"] = True
    baseline_df["meets_90pct_cagr_retention"] = True
    baseline_df["practical_rank_score"] = 0.0

    top = results.sort_values(
        ["practical_rank_score", "max_dd_improvement_pp", "cagr_retention_pct", "sharpe"],
        ascending=[False, False, False, False],
    ).head(20)
    category_best = (
        results.sort_values(
            ["category", "max_dd_improvement_pp", "cagr_retention_pct", "sharpe"],
            ascending=[True, False, False, False],
        )
        .groupby("category", as_index=False)
        .head(3)
    )

    pd.concat([baseline_df, results], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    top.to_csv(TOP_CSV, index=False)
    category_best.to_csv(CATEGORY_BEST_CSV, index=False)
    signal_coverage(signals, availability).to_csv(SIGNAL_COVERAGE_CSV, index=False)

    preserved_95 = results[results["meets_95pct_cagr_retention"]]
    preserved_90 = results[results["meets_90pct_cagr_retention"]]
    best_95 = preserved_95.sort_values(["max_dd_improvement_pp", "cagr_retention_pct"], ascending=[False, False]).head(1)
    best_90 = preserved_90.sort_values(["max_dd_improvement_pp", "cagr_retention_pct"], ascending=[False, False]).head(1)
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
            "weekly_fred": "forward-filled to market sessions and shifted five market sessions before use",
            "monthly_fred": "forward-filled to market sessions and shifted 21 market sessions before use",
        },
        "availability": availability,
        "tested_overlay_count": int(len(results)),
        "candidate_count_before_filters": int(len(specs)),
        "unemployment_benchmark": UNEMPLOYMENT_BENCHMARK,
        "best_with_95pct_cagr_retention": best_95.to_dict(orient="records")[0] if not best_95.empty else None,
        "best_with_90pct_cagr_retention": best_90.to_dict(orient="records")[0] if not best_90.empty else None,
        "beats_unemployment_count": int(results["beats_unrate_3m_practical"].sum()),
        "ranking_policy": (
            "Practical ranking rewards drawdown improvement, CAGR retention, Sharpe improvement, and 3x-only throttles, "
            "while penalizing leverage churn. Primary screen also reports best overlays with >=95% and >=90% CAGR retention."
        ),
        "limitations": {
            "jolts": "JOLTS openings and quits begin in 2000, so their effective overlap is shorter than the 30-year market sample.",
            "ism": "ISM employment is tested only when FRED NAPMEI is accessible as free data.",
            "conference_board": "Conference Board labor differential was not tested because no free direct source was identified.",
            "challenger": "Challenger job cuts were not tested because no free direct point-in-time source was identified.",
            "vintages": "FRED observation-date data are lagged, but this is not a full real-time vintage/ALFRED release-calendar simulation.",
        },
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
        "beats_unrate_3m_practical",
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    print("\nTop labor-leading overlays by practical score:")
    print(top[disp_cols].head(12).to_string(index=False))
    print("\nBest labor-leading overlays by drawdown improvement:")
    print(results[disp_cols].head(12).to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {TOP_CSV}")
    print(f"Wrote {CATEGORY_BEST_CSV}")
    print(f"Wrote {SIGNAL_COVERAGE_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network/data access failed: {exc}", file=sys.stderr)
        raise
