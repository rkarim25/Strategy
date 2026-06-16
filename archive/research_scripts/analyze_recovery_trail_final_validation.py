"""Final validation for making recovery-trail capped leverage the default.

This script extends analyze_recovery_trail_default_validation.py without
changing site/default strategy behavior. It adds the requested out-of-sample
walk-forward parameter selection, larger Monte Carlo tail stress, and execution
realism checks before issuing a final recommendation.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from analyze_recovery_trail_default_validation import (
    BASELINE_NAME,
    BASELINE_SPEC,
    PRIMARY_RESET_RULE,
    TARGET_NAME,
    TRAIL_LEVELS,
    TrailSpec,
    baseline_leverage,
    make_engine,
    recovery_trail_condition,
    run_result,
)
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


OUTPUT_DIR = Path("output") / "strategy_mechanics_tests"
PREFIX = OUTPUT_DIR / "final_trail_validation"
WALK_FORWARD_CSV = OUTPUT_DIR / "final_trail_validation_walk_forward.csv"
PARAMETER_GRID_CSV = OUTPUT_DIR / "final_trail_validation_parameter_grid.csv"
MC_SUMMARY_CSV = OUTPUT_DIR / "final_trail_validation_monte_carlo_summary.csv"
MC_PATHS_CSV = OUTPUT_DIR / "final_trail_validation_monte_carlo_paths.csv"
COST_EXECUTION_CSV = OUTPUT_DIR / "final_trail_validation_cost_execution.csv"
RECOMMENDATION_JSON = OUTPUT_DIR / "final_trail_validation_recommendation.json"

LEVELS = [0.03, 0.05, 0.075, 0.10, 0.125]
CAPS = [1.0, 2.0]
MC_LEVELS = [0.05, 0.075, 0.10]
TRADING_COSTS = [0.01, 0.015, 0.02]
N_SIMS = 1000
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260518
MATERIAL_CAGR_UNDERPERFORMANCE_PP = 3.0


@dataclass(frozen=True)
class ExecutionSpec:
    name: str
    check_frequency: str = "daily"
    delay_days: int = 0


BASE_EXECUTION = ExecutionSpec("daily same-day")
EXECUTION_CASES = [
    BASE_EXECUTION,
    ExecutionSpec("daily next-day", "daily", 1),
    ExecutionSpec("daily delayed 2 sessions", "daily", 2),
    ExecutionSpec("daily delayed 5 sessions", "daily", 5),
    ExecutionSpec("weekly same-day", "weekly", 0),
    ExecutionSpec("weekly next-day", "weekly", 1),
]


def pct(value: float) -> float:
    return float(value) * 100.0


def strategy_label(spec: TrailSpec) -> str:
    return spec.strategy


def make_spec(level: float, cap: float = 1.0) -> TrailSpec:
    return TrailSpec(level, cap, PRIMARY_RESET_RULE)


def candidate_specs() -> list[TrailSpec]:
    return [make_spec(level, cap) for level in LEVELS for cap in CAPS]


def monitored_condition(condition: pd.Series, execution: ExecutionSpec) -> pd.Series:
    """Approximate less-than-daily monitoring by only updating on check sessions."""
    observed = condition.astype(bool)
    if execution.check_frequency == "weekly":
        check_day = pd.Series(observed.index.weekday == 4, index=observed.index)
        if len(check_day):
            check_day.iloc[0] = True
        observed = observed.where(check_day, np.nan).ffill().fillna(False).astype(bool)
    elif execution.check_frequency != "daily":
        raise ValueError(f"Unsupported check frequency: {execution.check_frequency}")

    if execution.delay_days > 0:
        observed = observed.shift(execution.delay_days).fillna(False).astype(bool)
    return observed


def apply_trail_spec_execution(
    prices: pd.DataFrame,
    base_leverage: pd.Series,
    baseline_equity: pd.Series,
    spec: TrailSpec,
    execution: ExecutionSpec = BASE_EXECUTION,
) -> tuple[pd.Series, dict[str, float | int | str]]:
    raw_condition = recovery_trail_condition(
        prices,
        base_leverage,
        baseline_equity,
        trail_level=spec.trail_level,
        reset_rule=spec.reset_rule,
    )
    condition = monitored_condition(raw_condition, execution)
    leverage = base_leverage.copy().astype(float)
    leverage.loc[condition] = leverage.loc[condition].clip(upper=spec.cap)
    changed = (leverage != base_leverage).reindex(prices.index).fillna(False)
    return leverage, {
        "trail_level": spec.trail_level,
        "cap": spec.cap,
        "reset_rule": spec.reset_rule,
        "execution": execution.name,
        "check_frequency": execution.check_frequency,
        "delay_days": execution.delay_days,
        "raw_overlay_active_days": int(raw_condition.sum()),
        "overlay_active_days": int(condition.sum()),
        "pct_leverage_changed": float(changed.mean() * 100.0),
    }


def run_baseline(
    prices: pd.DataFrame,
    category: str,
    notes: str,
    *,
    trading_cost_pct: float = TRADING_COST_FROM_MID_PCT,
) -> tuple[dict[str, float | int | str], pd.Series, pd.Series, pd.Series]:
    lev, counts = baseline_leverage(prices)
    row, equity, returns, applied = run_result(
        prices,
        lev,
        BASELINE_NAME,
        category,
        "Current default strategy",
        notes,
        trading_cost_pct=trading_cost_pct,
        extra={**counts, "overlay_active_days": 0},
    )
    return row, equity, returns, applied


def run_spec(
    prices: pd.DataFrame,
    base_leverage: pd.Series,
    baseline_equity: pd.Series,
    spec: TrailSpec,
    category: str,
    notes: str,
    *,
    trading_cost_pct: float = TRADING_COST_FROM_MID_PCT,
    execution: ExecutionSpec = BASE_EXECUTION,
) -> tuple[dict[str, float | int | str], pd.Series, pd.Series, pd.Series]:
    lev, extra = apply_trail_spec_execution(prices, base_leverage, baseline_equity, spec, execution)
    label = strategy_label(spec)
    if execution != BASE_EXECUTION:
        label = f"{label}; {execution.name}"
    return run_result(
        prices,
        lev,
        label,
        category,
        f"Strategy-equity trail {spec.trail_level:.1%}; cap recovery to {spec.cap:.0f}x; {execution.name}.",
        notes,
        trading_cost_pct=trading_cost_pct,
        extra=extra,
    )


def add_baseline_deltas(df: pd.DataFrame, baseline: pd.Series | dict[str, object]) -> pd.DataFrame:
    out = df.copy()
    base_cagr = float(baseline["cagr"])
    base_dd = float(baseline["max_drawdown"])
    out["cagr_delta_pp"] = (out["cagr"].astype(float) - base_cagr) * 100.0
    out["cagr_retention_pct"] = out["cagr"].astype(float) / base_cagr * 100.0
    out["max_dd_improvement_pp"] = (out["max_drawdown"].astype(float) - base_dd) * 100.0
    out["sharpe_delta"] = out["sharpe"].astype(float) - float(baseline["sharpe"])
    return out


def validation_score(row: pd.Series) -> float:
    """Selection score used only inside the training window.

    The score prioritizes drawdown reduction, then risk-adjusted return, while
    heavily penalizing variants that keep less than 97% of baseline CAGR.
    """
    retention_shortfall = max(0.0, 97.0 - float(row["cagr_retention_pct"]))
    return (
        float(row["max_dd_improvement_pp"])
        + 0.35 * float(row["cagr_delta_pp"])
        + 0.75 * float(row["sharpe_delta"])
        - 2.0 * retention_shortfall
    )


def evaluate_grid(prices: pd.DataFrame, label: str, start: str, end: str) -> pd.DataFrame:
    window = prices.loc[start:end].copy()
    baseline_row, baseline_equity, _, base_lev = run_baseline(
        window,
        "Baseline",
        f"Baseline for {label}.",
    )
    rows = [baseline_row]
    for spec in candidate_specs():
        row, _, _, _ = run_spec(
            window,
            base_lev,
            baseline_equity,
            spec,
            "Recovery-tier trailing stop",
            f"Parameter grid for {label}.",
        )
        rows.append(row)

    out = add_baseline_deltas(pd.DataFrame(rows), baseline_row)
    out["window"] = label
    out["start"] = window.index[0].date().isoformat()
    out["end"] = window.index[-1].date().isoformat()
    out["sessions"] = int(len(window))
    out["selection_score"] = out.apply(
        lambda row: validation_score(row) if row["strategy"] != BASELINE_NAME else np.nan,
        axis=1,
    )
    return out


def walk_forward(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    splits = [
        ("train 1996-2010 -> test 2011-2026", "1996-01-01", "2010-12-31", "2011-01-01", "2026-12-31"),
        ("train 1996-2015 -> test 2016-2026", "1996-01-01", "2015-12-31", "2016-01-01", "2026-12-31"),
        ("train 1996-2005 -> test 2006-2015", "1996-01-01", "2005-12-31", "2006-01-01", "2015-12-31"),
        ("train 2006-2015 -> test 2016-2026", "2006-01-01", "2015-12-31", "2016-01-01", "2026-12-31"),
    ]
    parameter_rows: list[pd.DataFrame] = []
    walk_rows: list[dict[str, float | int | str]] = []

    for split, train_start, train_end, test_start, test_end in splits:
        train_grid = evaluate_grid(prices, f"{split} train", train_start, train_end)
        parameter_rows.append(train_grid)
        eligible = train_grid[
            (train_grid["strategy"] != BASELINE_NAME)
            & (train_grid["cagr_retention_pct"] >= 97.0)
            & (train_grid["max_dd_improvement_pp"] >= 0.0)
        ]
        if eligible.empty:
            eligible = train_grid[train_grid["strategy"] != BASELINE_NAME]
        selected = eligible.sort_values(
            ["selection_score", "max_dd_improvement_pp", "cagr_retention_pct"],
            ascending=False,
        ).iloc[0]

        selected_spec = make_spec(float(selected["trail_level"]), float(selected["cap"]))
        test_grid = evaluate_grid(prices, f"{split} untouched test", test_start, test_end)
        parameter_rows.append(test_grid)
        test_selected = test_grid[test_grid["strategy"] == selected_spec.strategy].iloc[0]
        test_target = test_grid[test_grid["strategy"] == TARGET_NAME].iloc[0]
        test_075 = test_grid[test_grid["strategy"] == make_spec(0.075, 1.0).strategy].iloc[0]
        test_10 = test_grid[test_grid["strategy"] == make_spec(0.10, 1.0).strategy].iloc[0]

        for role, row in [
            ("selected_by_train", test_selected),
            ("fixed_5pct_1x", test_target),
            ("fixed_7_5pct_1x", test_075),
            ("fixed_10pct_1x", test_10),
        ]:
            walk_rows.append(
                {
                    "split": split,
                    "role": role,
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "selected_train_strategy": selected_spec.strategy,
                    "selected_train_trail_level": float(selected["trail_level"]),
                    "selected_train_cap": float(selected["cap"]),
                    "selected_train_score": float(selected["selection_score"]),
                    "test_strategy": str(row["strategy"]),
                    "trail_level": float(row["trail_level"]) if pd.notna(row["trail_level"]) else np.nan,
                    "cap": float(row["cap"]) if pd.notna(row["cap"]) else np.nan,
                    "test_cagr": float(row["cagr"]),
                    "test_max_drawdown": float(row["max_drawdown"]),
                    "test_sharpe": float(row["sharpe"]),
                    "test_cagr_delta_pp": float(row["cagr_delta_pp"]),
                    "test_cagr_retention_pct": float(row["cagr_retention_pct"]),
                    "test_max_dd_improvement_pp": float(row["max_dd_improvement_pp"]),
                    "test_passes_default_rule": bool(
                        float(row["max_dd_improvement_pp"]) >= 3.0
                        and float(row["cagr_retention_pct"]) >= 97.0
                    ),
                }
            )

    return pd.concat(parameter_rows, ignore_index=True), pd.DataFrame(walk_rows)


def synthetic_market_paths(prices: pd.DataFrame, n_sims: int = N_SIMS) -> Iterable[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    for _ in range(n_sims):
        sampled_idx: list[np.ndarray] = []
        while sum(len(x) for x in sampled_idx) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_idx.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(sampled_idx)[:HORIZON_DAYS]
        returns = spx_ret[idx]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        yield pd.DataFrame(
            {
                "spx_close": 1000.0 * np.cumprod(1.0 + returns),
                "tbill_rate": tbill[idx],
            },
            index=index,
        )


def monte_carlo(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, float | int | str]] = []
    specs = [make_spec(level, 1.0) for level in MC_LEVELS]
    for sim, path in enumerate(synthetic_market_paths(prices), start=1):
        if sim == 1 or sim % 25 == 0:
            print(f"Monte Carlo path {sim}/{N_SIMS}", flush=True)
        baseline_row, baseline_equity, _, base_lev = run_baseline(
            path,
            "Baseline",
            "Block-bootstrap Monte Carlo baseline.",
        )
        baseline_row["simulation"] = sim - 1
        rows.append(baseline_row)
        for spec in specs:
            row, _, _, _ = run_spec(
                path,
                base_lev,
                baseline_equity,
                spec,
                "Recovery-tier trailing stop",
                "Block-bootstrap Monte Carlo candidate.",
            )
            row["simulation"] = sim - 1
            rows.append(row)

    paths = pd.DataFrame(rows)
    baseline = paths[paths["strategy"] == BASELINE_NAME].set_index("simulation")
    summaries: list[dict[str, float | int | str]] = []

    for strategy, group in paths.groupby("strategy"):
        summary: dict[str, float | int | str] = {
            "strategy": strategy,
            "category": str(group["category"].iloc[0]),
            "trail_level": float(group["trail_level"].dropna().iloc[0])
            if "trail_level" in group and group["trail_level"].notna().any()
            else np.nan,
            "cap": float(group["cap"].dropna().iloc[0])
            if "cap" in group and group["cap"].notna().any()
            else np.nan,
            "n_sims": int(group["simulation"].nunique()),
            "median_cagr": float(group["cagr"].median()),
            "p10_cagr": float(group["cagr"].quantile(0.10)),
            "p5_cagr": float(group["cagr"].quantile(0.05)),
            "median_max_drawdown": float(group["max_drawdown"].median()),
            "p10_max_drawdown": float(group["max_drawdown"].quantile(0.10)),
            "p5_max_drawdown": float(group["max_drawdown"].quantile(0.05)),
            "prob_max_dd_worse_30pct": float((group["max_drawdown"] <= -0.30).mean()),
            "prob_max_dd_worse_35pct": float((group["max_drawdown"] <= -0.35).mean()),
            "prob_max_dd_worse_40pct": float((group["max_drawdown"] <= -0.40).mean()),
            "prob_beats_baseline_cagr_by_sim": np.nan,
            "prob_improves_baseline_dd_by_sim": np.nan,
            "prob_underperforms_cagr_materially_by_sim": np.nan,
            "median_cagr_delta_pp_by_sim": np.nan,
            "median_dd_improvement_pp_by_sim": np.nan,
            "p10_dd_improvement_pp_by_sim": np.nan,
            "p5_dd_improvement_pp_by_sim": np.nan,
        }
        if strategy != BASELINE_NAME:
            joined = group.set_index("simulation")[["cagr", "max_drawdown"]].join(
                baseline[["cagr", "max_drawdown"]],
                lsuffix="_variant",
                rsuffix="_baseline",
                how="inner",
            )
            cagr_delta_pp = (joined["cagr_variant"] - joined["cagr_baseline"]) * 100.0
            dd_delta_pp = (joined["max_drawdown_variant"] - joined["max_drawdown_baseline"]) * 100.0
            summary.update(
                {
                    "prob_beats_baseline_cagr_by_sim": float((cagr_delta_pp > 0.0).mean()),
                    "prob_improves_baseline_dd_by_sim": float((dd_delta_pp > 0.0).mean()),
                    "prob_underperforms_cagr_materially_by_sim": float(
                        (cagr_delta_pp <= -MATERIAL_CAGR_UNDERPERFORMANCE_PP).mean()
                    ),
                    "median_cagr_delta_pp_by_sim": float(cagr_delta_pp.median()),
                    "median_dd_improvement_pp_by_sim": float(dd_delta_pp.median()),
                    "p10_dd_improvement_pp_by_sim": float(dd_delta_pp.quantile(0.10)),
                    "p5_dd_improvement_pp_by_sim": float(dd_delta_pp.quantile(0.05)),
                }
            )
        summaries.append(summary)

    return paths, pd.DataFrame(summaries)


def full_sample_parameter_grid(prices: pd.DataFrame) -> pd.DataFrame:
    return evaluate_grid(prices, "full sample", "1900-01-01", "2100-01-01")


def cost_execution_sensitivity(prices: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    specs = [make_spec(0.05, 1.0), make_spec(0.075, 1.0), make_spec(0.10, 1.0)]

    for cost in TRADING_COSTS:
        baseline_row, baseline_equity, _, base_lev = run_baseline(
            prices,
            "Baseline",
            "Trading-cost and execution sensitivity baseline.",
            trading_cost_pct=cost,
        )
        baseline_row["execution"] = BASE_EXECUTION.name
        baseline_row["check_frequency"] = BASE_EXECUTION.check_frequency
        baseline_row["delay_days"] = BASE_EXECUTION.delay_days
        rows.append(baseline_row)

        for spec in specs:
            for execution in EXECUTION_CASES:
                row, _, _, _ = run_spec(
                    prices,
                    base_lev,
                    baseline_equity,
                    spec,
                    "Recovery-tier trailing stop",
                    "Trading-cost and execution sensitivity candidate.",
                    trading_cost_pct=cost,
                    execution=execution,
                )
                rows.append(row)

    out = pd.DataFrame(rows)
    enriched = []
    baselines = out[out["strategy"] == BASELINE_NAME].set_index("trading_cost_pct")
    for _, row in out.iterrows():
        base = baselines.loc[float(row["trading_cost_pct"])]
        data = row.to_dict()
        data["cagr_delta_pp"] = (float(row["cagr"]) - float(base["cagr"])) * 100.0
        data["cagr_retention_pct"] = float(row["cagr"]) / float(base["cagr"]) * 100.0
        data["max_dd_improvement_pp"] = (float(row["max_drawdown"]) - float(base["max_drawdown"])) * 100.0
        data["trading_cost_delta_$"] = float(row["trading_costs_total"]) - float(base["trading_costs_total"])
        data["turnover_delta_$"] = float(row["turnover_notional"]) - float(base["turnover_notional"])
        data["rebalance_delta"] = int(row["rebalances"]) - int(base["rebalances"])
        enriched.append(data)
    return pd.DataFrame(enriched)


def criteria_summary(
    full_grid: pd.DataFrame,
    walk: pd.DataFrame,
    mc_summary: pd.DataFrame,
    cost_exec: pd.DataFrame,
) -> tuple[dict[str, object], str, str]:
    target_full = full_grid[full_grid["strategy"] == TARGET_NAME].iloc[0]
    primary_full = full_grid[
        (full_grid["cap"] == 1.0)
        & (full_grid["trail_level"].isin([0.05, 0.075, 0.10]))
        & (full_grid["strategy"] != BASELINE_NAME)
    ].copy()
    target_mc = mc_summary[mc_summary["strategy"] == TARGET_NAME].iloc[0]
    baseline_mc = mc_summary[mc_summary["strategy"] == BASELINE_NAME].iloc[0]

    selected_rows = walk[walk["role"] == "selected_by_train"]
    fixed_5_rows = walk[walk["role"] == "fixed_5pct_1x"]
    selected_5_share = float((selected_rows["selected_train_trail_level"] == 0.05).mean())
    selected_1x_share = float((selected_rows["selected_train_cap"] == 1.0).mean())

    base_cost_cases = cost_exec[
        (cost_exec["strategy"] == TARGET_NAME)
        & (cost_exec["execution"] == BASE_EXECUTION.name)
        & (cost_exec["trading_cost_pct"].isin(TRADING_COSTS))
    ]
    delayed_cost_cases = cost_exec[
        (cost_exec["trail_level"] == 0.05)
        & (cost_exec["cap"] == 1.0)
        & (cost_exec["execution"] != BASE_EXECUTION.name)
    ]

    neighbor_rows = primary_full[primary_full["trail_level"].isin([0.075, 0.10])]
    neighbor_ok_count = int(
        (
            (neighbor_rows["max_dd_improvement_pp"] >= 3.0)
            & (neighbor_rows["cagr_retention_pct"] >= 97.0)
        ).sum()
    )

    criteria = {
        "full_sample_drawdown_improves_at_least_3pp": bool(target_full["max_dd_improvement_pp"] >= 3.0),
        "full_sample_cagr_keeps_97pct_or_beats": bool(target_full["cagr_retention_pct"] >= 97.0),
        "monte_carlo_median_drawdown_improves": bool(
            target_mc["median_max_drawdown"] > baseline_mc["median_max_drawdown"]
        ),
        "monte_carlo_p10_p5_drawdown_improves": bool(
            target_mc["p10_max_drawdown"] > baseline_mc["p10_max_drawdown"]
            and target_mc["p5_max_drawdown"] > baseline_mc["p5_max_drawdown"]
        ),
        "nearby_7_5_or_10pct_still_acceptable": bool(neighbor_ok_count >= 1),
        "cost_1_5_to_2pct_not_unattractive": bool(
            (
                (base_cost_cases["cagr_retention_pct"] >= 97.0)
                & (base_cost_cases["max_dd_improvement_pp"] >= 3.0)
            ).all()
        ),
        "walk_forward_no_severe_overfit": bool(
            selected_5_share < 1.0
            and selected_1x_share >= 0.50
            and (fixed_5_rows["test_cagr_retention_pct"] >= 97.0).mean() >= 0.50
            and (fixed_5_rows["test_max_dd_improvement_pp"] >= 0.0).mean() >= 0.50
        ),
        "execution_delay_not_fragile": bool(
            (
                (delayed_cost_cases["cagr_retention_pct"] >= 97.0)
                & (delayed_cost_cases["max_dd_improvement_pp"] >= 0.0)
            ).mean()
            >= 0.70
        ),
    }

    hard_failures = [
        key
        for key in [
            "full_sample_drawdown_improves_at_least_3pp",
            "full_sample_cagr_keeps_97pct_or_beats",
            "monte_carlo_median_drawdown_improves",
            "monte_carlo_p10_p5_drawdown_improves",
            "nearby_7_5_or_10pct_still_acceptable",
            "cost_1_5_to_2pct_not_unattractive",
            "walk_forward_no_severe_overfit",
        ]
        if not criteria[key]
    ]
    passed = sum(bool(v) for v in criteria.values())
    if not hard_failures and passed >= 7:
        decision = "make default"
        rationale = (
            "The 5% cap-to-1x rule clears the required drawdown, CAGR, Monte Carlo tail, "
            "cost, nearby-parameter, and walk-forward stability checks."
        )
    else:
        decision = "do not make default"
        rationale = (
            "The rule improves full-sample and Monte Carlo drawdowns, but the final validation "
            "does not clear enough default-level robustness checks."
        )

    summary = {
        "criteria": criteria,
        "criteria_passed": int(passed),
        "criteria_total": int(len(criteria)),
        "hard_failures": hard_failures,
        "target_full_sample": {
            "cagr": float(target_full["cagr"]),
            "max_drawdown": float(target_full["max_drawdown"]),
            "sharpe": float(target_full["sharpe"]),
            "cagr_delta_pp": float(target_full["cagr_delta_pp"]),
            "cagr_retention_pct": float(target_full["cagr_retention_pct"]),
            "max_dd_improvement_pp": float(target_full["max_dd_improvement_pp"]),
            "overlay_active_days": int(target_full["overlay_active_days"]),
            "turnover_notional": float(target_full["turnover_notional"]),
            "rebalances": int(target_full["rebalances"]),
        },
        "nearby_full_sample": primary_full[
            [
                "strategy",
                "trail_level",
                "cap",
                "cagr",
                "max_drawdown",
                "cagr_retention_pct",
                "max_dd_improvement_pp",
                "sharpe",
            ]
        ].to_dict(orient="records"),
        "walk_forward": {
            "selected_5pct_share": selected_5_share,
            "selected_1x_share": selected_1x_share,
            "fixed_5pct_test_pass_rate": float(fixed_5_rows["test_passes_default_rule"].mean()),
            "fixed_5pct_mean_test_cagr_delta_pp": float(fixed_5_rows["test_cagr_delta_pp"].mean()),
            "fixed_5pct_mean_test_dd_improvement_pp": float(fixed_5_rows["test_max_dd_improvement_pp"].mean()),
            "selected_train_choices": selected_rows[
                [
                    "split",
                    "selected_train_strategy",
                    "selected_train_trail_level",
                    "selected_train_cap",
                    "test_cagr_delta_pp",
                    "test_max_dd_improvement_pp",
                ]
            ].to_dict(orient="records"),
        },
        "monte_carlo": {
            "n_sims": N_SIMS,
            "target": target_mc.to_dict(),
            "baseline": baseline_mc.to_dict(),
        },
        "cost_execution": {
            "target_daily_same_day": base_cost_cases[
                [
                    "trading_cost_pct",
                    "cagr",
                    "max_drawdown",
                    "cagr_delta_pp",
                    "cagr_retention_pct",
                    "max_dd_improvement_pp",
                    "trading_cost_delta_$",
                    "turnover_delta_$",
                    "rebalance_delta",
                ]
            ].to_dict(orient="records"),
            "target_delayed_execution": delayed_cost_cases[
                [
                    "trading_cost_pct",
                    "execution",
                    "cagr",
                    "max_drawdown",
                    "cagr_delta_pp",
                    "cagr_retention_pct",
                    "max_dd_improvement_pp",
                ]
            ].to_dict(orient="records"),
        },
        "assumptions": {
            "baseline": BASELINE_SPEC,
            "candidate": TARGET_NAME,
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "default_trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "monte_carlo": {
                "n_sims": N_SIMS,
                "horizon_trading_days": HORIZON_DAYS,
                "block_days": BLOCK_DAYS,
                "seed": SEED,
                "method": "Contiguous 21-trading-day block bootstrap of historical SPX returns and T-bill rates.",
            },
            "walk_forward_selection": (
                "Parameters are selected only on the train window from 3%, 5%, 7.5%, 10%, "
                "12.5% trails and 1x/2x caps using drawdown-first score with a 97% CAGR "
                "retention eligibility preference, then evaluated on untouched later windows."
            ),
            "execution_realism": (
                "Signal delays shift the cap state by 1/2/5 sessions. Weekly monitoring only "
                "updates the observed cap state on Friday sessions and holds the last observed state."
            ),
        },
    }
    return summary, decision, rationale


def write_recommendation(
    prices: pd.DataFrame,
    full_grid: pd.DataFrame,
    walk: pd.DataFrame,
    mc_summary: pd.DataFrame,
    cost_exec: pd.DataFrame,
) -> dict[str, object]:
    criteria, decision, rationale = criteria_summary(full_grid, walk, mc_summary, cost_exec)
    payload: dict[str, object] = {
        "decision": decision,
        "rationale": rationale,
        "target_strategy": TARGET_NAME,
        "baseline_strategy": BASELINE_NAME,
        "source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "created_by": Path(__file__).name,
        "outputs": {
            "walk_forward_csv": str(WALK_FORWARD_CSV),
            "parameter_grid_csv": str(PARAMETER_GRID_CSV),
            "monte_carlo_summary_csv": str(MC_SUMMARY_CSV),
            "monte_carlo_paths_csv": str(MC_PATHS_CSV),
            "cost_execution_csv": str(COST_EXECUTION_CSV),
            "recommendation_json": str(RECOMMENDATION_JSON),
        },
        **criteria,
    }
    with RECOMMENDATION_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return payload


def print_key_results(payload: dict[str, object]) -> None:
    evidence = payload["target_full_sample"]
    mc = payload["monte_carlo"]["target"]
    print("\nFinal decision:")
    print(payload["decision"])
    print(payload["rationale"])
    print("\nTarget full-sample:")
    print(
        f"CAGR {pct(evidence['cagr']):.2f}% "
        f"({evidence['cagr_delta_pp']:+.2f} pp), "
        f"max DD {pct(evidence['max_drawdown']):.2f}% "
        f"({evidence['max_dd_improvement_pp']:+.2f} pp), "
        f"Sharpe {evidence['sharpe']:.3f}"
    )
    print("\nTarget Monte Carlo:")
    print(
        f"median CAGR {pct(mc['median_cagr']):.2f}%, "
        f"median DD {pct(mc['median_max_drawdown']):.2f}%, "
        f"P(DD<-35%) {pct(mc['prob_max_dd_worse_35pct']):.1f}%, "
        f"P(beats CAGR) {pct(mc['prob_beats_baseline_cagr_by_sim']):.1f}%, "
        f"P(improves DD) {pct(mc['prob_improves_baseline_dd_by_sim']):.1f}%"
    )
    print(f"\nCriteria passed: {payload['criteria_passed']}/{payload['criteria_total']}")
    print(f"Wrote outputs with prefix {PREFIX}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")

    print("Running full-sample parameter grid...", flush=True)
    full_grid = full_sample_parameter_grid(prices)

    print("Running walk-forward parameter stability...", flush=True)
    parameter_grid, walk = walk_forward(prices)
    parameter_grid = pd.concat([full_grid, parameter_grid], ignore_index=True)
    parameter_grid.to_csv(PARAMETER_GRID_CSV, index=False)
    walk.to_csv(WALK_FORWARD_CSV, index=False)

    print(f"Running {N_SIMS}-path Monte Carlo tail stress...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices)
    mc_paths.to_csv(MC_PATHS_CSV, index=False)
    mc_summary.to_csv(MC_SUMMARY_CSV, index=False)

    print("Running cost and execution sensitivity...", flush=True)
    cost_exec = cost_execution_sensitivity(prices)
    cost_exec.to_csv(COST_EXECUTION_CSV, index=False)

    payload = write_recommendation(prices, full_grid, walk, mc_summary, cost_exec)
    print_key_results(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
