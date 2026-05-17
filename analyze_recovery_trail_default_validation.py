"""Validate whether the strategy-equity recovery trail should become default.

This is a focused follow-up to analyze_strategy_mechanics_overlays.py. It keeps
the current guarded baseline assumptions and tests recovery-trail variants for
parameter sensitivity, date-window robustness, Monte Carlo behavior, and trading
cost sensitivity.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


OUTPUT_DIR = Path("output") / "strategy_mechanics_tests"
PREFIX = OUTPUT_DIR / "trail_validation"
SENSITIVITY_CSV = OUTPUT_DIR / "trail_validation_sensitivity.csv"
SUBPERIODS_CSV = OUTPUT_DIR / "trail_validation_subperiods.csv"
CRISIS_WINDOWS_CSV = OUTPUT_DIR / "trail_validation_crisis_windows.csv"
MC_SUMMARY_CSV = OUTPUT_DIR / "trail_validation_monte_carlo_summary.csv"
MC_PATHS_CSV = OUTPUT_DIR / "trail_validation_monte_carlo_paths.csv"
COST_SENSITIVITY_CSV = OUTPUT_DIR / "trail_validation_cost_sensitivity.csv"
EQUITY_CSV = OUTPUT_DIR / "trail_validation_annual_equity_selected.csv"
METADATA_JSON = OUTPUT_DIR / "trail_validation_recommendation_metadata.json"

BASELINE_NAME = "Baseline Guarded A5/B25/X40/Y15 Lead 0.75"
TARGET_NAME = "strategy_equity recovery trail 5%: cap recovery to 1x"
BASELINE_SPEC = {
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}

TRAIL_LEVELS = [0.03, 0.05, 0.075, 0.10, 0.125]
CAPS = [1.0, 2.0, 0.0]
RESET_RULES = ["recovery_reset", "new_strategy_equity_high", "spx_above_sma20", "spx_above_sma50"]
PRIMARY_RESET_RULE = "recovery_reset"
PRIMARY_CAP = 1.0
MC_LEVELS = [0.05, 0.075, 0.10]
TRADING_COSTS = [0.005, 0.01, 0.015, 0.02]

N_SIMS = 500
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260517


@dataclass(frozen=True)
class TrailSpec:
    trail_level: float
    cap: float
    reset_rule: str

    @property
    def cap_label(self) -> str:
        if self.cap == 0.0:
            return "exit/cash"
        return f"cap recovery to {self.cap:.0f}x"

    @property
    def reset_label(self) -> str:
        labels = {
            "recovery_reset": "cap until recovery tier resets",
            "new_strategy_equity_high": "cap until new strategy-equity high",
            "spx_above_sma20": "cap until SPX above SMA20",
            "spx_above_sma50": "cap until SPX above SMA50",
        }
        return labels[self.reset_rule]

    @property
    def strategy(self) -> str:
        pct = f"{self.trail_level * 100:g}%"
        base = f"strategy_equity recovery trail {pct}: {self.cap_label}"
        if self.reset_rule == PRIMARY_RESET_RULE:
            return base
        return f"{base}; {self.reset_label}"


def make_engine(trading_cost_pct: float = TRADING_COST_FROM_MID_PCT) -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=trading_cost_pct,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def baseline_leverage(prices: pd.DataFrame) -> tuple[pd.Series, dict[str, float | int]]:
    return guarded_strategy_leverage(prices, **BASELINE_SPEC)


def prior_session(series: pd.Series) -> pd.Series:
    return series.shift(1)


def trend_signals(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["spx_close"].astype(float)
    signals = pd.DataFrame(index=prices.index)
    for window in [20, 50]:
        sma = close.rolling(window, min_periods=window).mean()
        signals[f"SPX_ABOVE_SMA{window}"] = prior_session(close > sma).fillna(False).astype(bool)
    return signals


def recovery_trail_condition(
    prices: pd.DataFrame,
    base_leverage: pd.Series,
    strategy_equity: pd.Series,
    *,
    trail_level: float,
    reset_rule: str,
) -> pd.Series:
    """Return sessions where the recovery trail has breached and cap should apply."""
    signals = trend_signals(prices)
    condition = pd.Series(False, index=prices.index)
    in_recovery = False
    breached = False
    peak = np.nan

    for dt in prices.index:
        lev = float(base_leverage.loc[dt])
        value = float(strategy_equity.loc[dt]) if not pd.isna(strategy_equity.loc[dt]) else np.nan

        if lev <= 1.0:
            in_recovery = False
            breached = False
            peak = np.nan
            continue

        if not in_recovery:
            in_recovery = True
            breached = False
            peak = value
        elif not pd.isna(value):
            peak = max(peak, value)

        if breached:
            if reset_rule == "new_strategy_equity_high" and not pd.isna(value) and value >= peak:
                breached = False
            elif reset_rule == "spx_above_sma20" and bool(signals["SPX_ABOVE_SMA20"].loc[dt]):
                breached = False
            elif reset_rule == "spx_above_sma50" and bool(signals["SPX_ABOVE_SMA50"].loc[dt]):
                breached = False

        if not breached and peak > 0 and not pd.isna(value):
            if value / peak - 1.0 <= -trail_level:
                breached = True

        condition.loc[dt] = breached

    return condition


def apply_trail_spec(
    prices: pd.DataFrame,
    base_leverage: pd.Series,
    baseline_equity: pd.Series,
    spec: TrailSpec,
) -> tuple[pd.Series, dict[str, float | int | str]]:
    condition = recovery_trail_condition(
        prices,
        base_leverage,
        baseline_equity,
        trail_level=spec.trail_level,
        reset_rule=spec.reset_rule,
    )
    leverage = base_leverage.copy().astype(float)
    if spec.cap == 0.0:
        leverage.loc[condition] = 0.0
    else:
        leverage.loc[condition] = leverage.loc[condition].clip(upper=spec.cap)

    changed = (leverage != base_leverage).reindex(prices.index).fillna(False)
    return leverage, {
        "trail_level": spec.trail_level,
        "cap": spec.cap,
        "reset_rule": spec.reset_rule,
        "cap_behavior": spec.cap_label,
        "reset_behavior": spec.reset_label,
        "overlay_active_days": int(condition.sum()),
        "pct_leverage_changed": float(changed.mean() * 100.0),
    }


def run_result(
    prices: pd.DataFrame,
    leverage: pd.Series,
    strategy: str,
    category: str,
    detail: str,
    notes: str,
    *,
    trading_cost_pct: float = TRADING_COST_FROM_MID_PCT,
    extra: dict[str, float | int | str] | None = None,
) -> tuple[dict[str, float | int | str], pd.Series, pd.Series, pd.Series]:
    result = make_engine(trading_cost_pct).run(prices, leverage, name=strategy)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    row: dict[str, float | int | str] = {
        "category": category,
        "strategy": strategy,
        "detail": detail,
        "notes": notes,
        "trading_cost_pct": trading_cost_pct,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats["sortino"],
        "calmar": stats["calmar"],
        "max_drawdown": stats["max_drawdown"],
        "ulcer_index": stats["ulcer_index"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "turnover_notional": result.turnover_notional,
        "avg_leverage": float(result.leverage.mean()),
        "pct_days_cash": float((result.leverage <= 0).mean() * 100.0),
        "pct_days_1x": float((result.leverage == 1.0).mean() * 100.0),
        "pct_days_2x": float((result.leverage == 2.0).mean() * 100.0),
        "pct_days_3x": float((result.leverage == 3.0).mean() * 100.0),
    }
    if extra:
        row.update(extra)
    return row, result.equity, result.daily_returns, result.leverage


def compare_to_baseline(df: pd.DataFrame, baseline_row: dict[str, float | int | str]) -> pd.DataFrame:
    out = df.copy()
    out["cagr_delta_pp"] = (out["cagr"] - float(baseline_row["cagr"])) * 100.0
    out["cagr_retention_pct"] = out["cagr"] / float(baseline_row["cagr"]) * 100.0
    out["max_dd_delta_pp"] = (out["max_drawdown"] - float(baseline_row["max_drawdown"])) * 100.0
    out["max_dd_improvement_pp"] = out["max_dd_delta_pp"]
    out["sharpe_delta"] = out["sharpe"] - float(baseline_row["sharpe"])
    return out


def all_trail_specs() -> list[TrailSpec]:
    return [TrailSpec(level, cap, reset) for level in TRAIL_LEVELS for cap in CAPS for reset in RESET_RULES]


def primary_spec(level: float = 0.05, cap: float = PRIMARY_CAP) -> TrailSpec:
    return TrailSpec(level, cap, PRIMARY_RESET_RULE)


def compute_window_stats(
    label: str,
    start: str,
    end: str,
    results: dict[str, tuple[pd.Series, pd.Series, pd.Series]],
    baseline_name: str,
    metadata: dict[str, dict[str, float | int | str]],
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    baseline_equity, baseline_returns, _ = results[baseline_name]
    baseline_slice = baseline_equity.loc[start:end]
    if len(baseline_slice) < 30:
        return rows
    baseline_stats = comprehensive_stats(
        baseline_slice,
        baseline_returns.reindex(baseline_slice.index).fillna(0.0),
    )
    for strategy, (equity, returns, leverage) in results.items():
        eq = equity.loc[start:end]
        if len(eq) < 30:
            continue
        stats = comprehensive_stats(eq, returns.reindex(eq.index).fillna(0.0))
        rows.append(
            {
                "window": label,
                "start": eq.index[0].date().isoformat(),
                "end": eq.index[-1].date().isoformat(),
                "sessions": int(len(eq)),
                "strategy": strategy,
                "category": metadata[strategy]["category"],
                "trail_level": metadata[strategy].get("trail_level", np.nan),
                "cap": metadata[strategy].get("cap", np.nan),
                "reset_rule": metadata[strategy].get("reset_rule", ""),
                "cagr": stats["cagr"],
                "max_drawdown": stats["max_drawdown"],
                "sharpe": stats["sharpe"],
                "end_$": float(eq.iloc[-1]),
                "avg_leverage": float(leverage.reindex(eq.index).mean()),
                "cagr_delta_pp": (stats["cagr"] - baseline_stats["cagr"]) * 100.0,
                "max_dd_improvement_pp": (stats["max_drawdown"] - baseline_stats["max_drawdown"]) * 100.0,
                "sharpe_delta": stats["sharpe"] - baseline_stats["sharpe"],
            }
        )
    return rows


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


def monte_carlo(prices: pd.DataFrame, specs: list[TrailSpec]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, float | int | str]] = []
    for sim, path in enumerate(synthetic_market_paths(prices), start=1):
        if sim == 1 or sim % 25 == 0:
            print(f"Monte Carlo path {sim}/{N_SIMS}", flush=True)
        base_lev, base_counts = baseline_leverage(path)
        baseline_row, baseline_equity, _, _ = run_result(
            path,
            base_lev,
            BASELINE_NAME,
            "Baseline",
            "Current default strategy",
            "Monte Carlo baseline.",
            extra=base_counts,
        )
        baseline_row["simulation"] = sim - 1
        rows.append(baseline_row)
        for spec in specs:
            lev, extra = apply_trail_spec(path, base_lev, baseline_equity, spec)
            row, _, _, _ = run_result(
                path,
                lev,
                spec.strategy,
                "Recovery-tier trailing stop",
                f"Strategy-equity trail {spec.trail_level:.1%}; {spec.cap_label}; {spec.reset_label}.",
                "Block-bootstrap Monte Carlo using SPX/tbill history.",
                extra=extra,
            )
            row["simulation"] = sim - 1
            rows.append(row)

    paths = pd.DataFrame(rows)
    summary_rows: list[dict[str, float | int | str]] = []
    baseline_by_sim = paths[paths["strategy"] == BASELINE_NAME].set_index("simulation")
    for strategy, group in paths.groupby("strategy"):
        summary: dict[str, float | int | str] = {
            "strategy": strategy,
            "category": str(group["category"].iloc[0]),
            "trail_level": group["trail_level"].dropna().iloc[0] if "trail_level" in group and group["trail_level"].notna().any() else np.nan,
            "cap": group["cap"].dropna().iloc[0] if "cap" in group and group["cap"].notna().any() else np.nan,
            "reset_rule": group["reset_rule"].dropna().iloc[0] if "reset_rule" in group and group["reset_rule"].notna().any() else "",
            "median_cagr": float(group["cagr"].median()),
            "p10_cagr": float(group["cagr"].quantile(0.10)),
            "p90_cagr": float(group["cagr"].quantile(0.90)),
            "median_max_drawdown": float(group["max_drawdown"].median()),
            "p10_max_drawdown": float(group["max_drawdown"].quantile(0.10)),
            "p90_max_drawdown": float(group["max_drawdown"].quantile(0.90)),
            "median_sharpe": float(group["sharpe"].median()),
            "median_end_$": float(group["end_$"].median()),
            "prob_max_dd_worse_30pct": float((group["max_drawdown"] <= -0.30).mean()),
            "prob_max_dd_worse_35pct": float((group["max_drawdown"] <= -0.35).mean()),
            "prob_max_dd_worse_40pct": float((group["max_drawdown"] <= -0.40).mean()),
            "prob_beats_baseline_cagr_by_sim": np.nan,
            "prob_improves_baseline_dd_by_sim": np.nan,
        }
        if strategy != BASELINE_NAME:
            joined = group.set_index("simulation")[["cagr", "max_drawdown"]].join(
                baseline_by_sim[["cagr", "max_drawdown"]],
                lsuffix="_variant",
                rsuffix="_baseline",
                how="inner",
            )
            summary["prob_beats_baseline_cagr_by_sim"] = float((joined["cagr_variant"] > joined["cagr_baseline"]).mean())
            summary["prob_improves_baseline_dd_by_sim"] = float(
                (joined["max_drawdown_variant"] > joined["max_drawdown_baseline"]).mean()
            )
        summary_rows.append(summary)
    return paths, pd.DataFrame(summary_rows)


def cost_sensitivity(prices: pd.DataFrame, specs: list[TrailSpec]) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for cost in TRADING_COSTS:
        base_lev, base_counts = baseline_leverage(prices)
        baseline_row, baseline_equity, _, _ = run_result(
            prices,
            base_lev,
            BASELINE_NAME,
            "Baseline",
            "Current default strategy",
            "Trading-cost sensitivity baseline.",
            trading_cost_pct=cost,
            extra=base_counts,
        )
        rows.append(baseline_row)
        for spec in specs:
            lev, extra = apply_trail_spec(prices, base_lev, baseline_equity, spec)
            row, _, _, _ = run_result(
                prices,
                lev,
                spec.strategy,
                "Recovery-tier trailing stop",
                f"Strategy-equity trail {spec.trail_level:.1%}; {spec.cap_label}; {spec.reset_label}.",
                "Trading-cost sensitivity candidate.",
                trading_cost_pct=cost,
                extra=extra,
            )
            rows.append(row)
    out = pd.DataFrame(rows)
    baselines = out[out["strategy"] == BASELINE_NAME].set_index("trading_cost_pct")
    deltas = []
    for _, row in out.iterrows():
        base = baselines.loc[row["trading_cost_pct"]]
        enriched = row.to_dict()
        enriched["cagr_delta_pp"] = (float(row["cagr"]) - float(base["cagr"])) * 100.0
        enriched["max_dd_improvement_pp"] = (float(row["max_drawdown"]) - float(base["max_drawdown"])) * 100.0
        enriched["trading_cost_delta_$"] = float(row["trading_costs_total"]) - float(base["trading_costs_total"])
        enriched["turnover_delta_$"] = float(row["turnover_notional"]) - float(base["turnover_notional"])
        enriched["rebalance_delta"] = int(row["rebalances"]) - int(base["rebalances"])
        deltas.append(enriched)
    return pd.DataFrame(deltas)


def annual_equity(results: dict[str, tuple[pd.Series, pd.Series, pd.Series]], selected: list[str]) -> pd.DataFrame:
    rows = []
    for strategy in selected:
        equity = results[strategy][0].resample("YE").last()
        for dt, value in equity.items():
            rows.append({"year": int(dt.year), "strategy": strategy, "equity_$": float(value)})
    return pd.DataFrame(rows)


def recommendation_metadata(
    sensitivity: pd.DataFrame,
    subperiods: pd.DataFrame,
    crises: pd.DataFrame,
    mc_summary: pd.DataFrame,
    costs: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, object]:
    target = sensitivity[sensitivity["strategy"] == TARGET_NAME].iloc[0]
    primary = sensitivity[
        (sensitivity["cap"] == PRIMARY_CAP) & (sensitivity["reset_rule"] == PRIMARY_RESET_RULE)
    ].sort_values("trail_level")
    target_mc = mc_summary[mc_summary["strategy"] == TARGET_NAME].iloc[0]
    baseline_mc = mc_summary[mc_summary["strategy"] == BASELINE_NAME].iloc[0]

    neighbors = primary[primary["trail_level"].isin([0.03, 0.075, 0.10])]
    stable_neighbor_count = int(((neighbors["max_dd_improvement_pp"] > 0) & (neighbors["cagr_retention_pct"] >= 95.0)).sum())
    target_sub = subperiods[subperiods["strategy"] == TARGET_NAME]
    target_crisis = crises[crises["strategy"] == TARGET_NAME]
    subperiod_dd_win_rate = float((target_sub["max_dd_improvement_pp"] > 0).mean()) if len(target_sub) else np.nan
    crisis_dd_win_rate = float((target_crisis["max_dd_improvement_pp"] > 0).mean()) if len(target_crisis) else np.nan
    target_costs = costs[costs["strategy"] == TARGET_NAME]
    cost_positive_cagr_count = int((target_costs["cagr_delta_pp"] > 0).sum())

    evidence = {
        "target_full_sample": {
            "cagr": float(target["cagr"]),
            "max_drawdown": float(target["max_drawdown"]),
            "sharpe": float(target["sharpe"]),
            "cagr_delta_pp": float(target["cagr_delta_pp"]),
            "max_dd_improvement_pp": float(target["max_dd_improvement_pp"]),
            "overlay_active_days": int(target["overlay_active_days"]),
        },
        "monte_carlo_target": {
            "n_sims": N_SIMS,
            "median_cagr": float(target_mc["median_cagr"]),
            "median_max_drawdown": float(target_mc["median_max_drawdown"]),
            "p10_cagr": float(target_mc["p10_cagr"]),
            "p10_max_drawdown": float(target_mc["p10_max_drawdown"]),
            "prob_beats_baseline_cagr_by_sim": float(target_mc["prob_beats_baseline_cagr_by_sim"]),
            "prob_improves_baseline_dd_by_sim": float(target_mc["prob_improves_baseline_dd_by_sim"]),
            "prob_max_dd_worse_30pct": float(target_mc["prob_max_dd_worse_30pct"]),
            "prob_max_dd_worse_35pct": float(target_mc["prob_max_dd_worse_35pct"]),
            "prob_max_dd_worse_40pct": float(target_mc["prob_max_dd_worse_40pct"]),
            "baseline_prob_max_dd_worse_30pct": float(baseline_mc["prob_max_dd_worse_30pct"]),
            "baseline_prob_max_dd_worse_35pct": float(baseline_mc["prob_max_dd_worse_35pct"]),
            "baseline_prob_max_dd_worse_40pct": float(baseline_mc["prob_max_dd_worse_40pct"]),
        },
        "stability": {
            "stable_neighbor_count_3pct_7_5pct_10pct": stable_neighbor_count,
            "subperiod_dd_win_rate": subperiod_dd_win_rate,
            "crisis_dd_win_rate": crisis_dd_win_rate,
            "positive_cagr_cost_cases_for_target": cost_positive_cagr_count,
            "tested_cost_cases": int(len(target_costs)),
        },
    }

    if (
        float(target_mc["prob_improves_baseline_dd_by_sim"]) >= 0.85
        and float(target_mc["prob_beats_baseline_cagr_by_sim"]) >= 0.50
        and stable_neighbor_count >= 2
        and subperiod_dd_win_rate >= 0.50
        and crisis_dd_win_rate >= 0.50
    ):
        recommendation = "keep as candidate but not default"
        rationale = (
            "The rule improves drawdown consistently and does not appear to be a single-point spike, "
            "but the edge is path-dependent and the CAGR advantage is modest. Promote only after a "
            "separate forward/live-paper validation or an explicit governance choice to prioritize lower drawdown."
        )
    else:
        recommendation = "reject as default"
        rationale = (
            "The validation did not clear the stability and Monte Carlo thresholds needed for a path-dependent "
            "overlay to become default."
        )

    return {
        "recommendation": recommendation,
        "rationale": rationale,
        "target_strategy": TARGET_NAME,
        "baseline_strategy": BASELINE_NAME,
        "source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "assumptions": {
            "baseline": BASELINE_SPEC,
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "default_trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "subperiod_method": "Full-history state is preserved; metrics are computed on sliced realized equity/return windows.",
            "trail_basis": "Current mechanics use baseline strategy equity as the trail basis, matching the prior mechanics pass.",
            "monte_carlo": {
                "n_sims": N_SIMS,
                "horizon_trading_days": HORIZON_DAYS,
                "block_days": BLOCK_DAYS,
                "seed": SEED,
            },
        },
        "evidence": evidence,
        "outputs": {
            "sensitivity_csv": str(SENSITIVITY_CSV),
            "subperiods_csv": str(SUBPERIODS_CSV),
            "crisis_windows_csv": str(CRISIS_WINDOWS_CSV),
            "monte_carlo_summary_csv": str(MC_SUMMARY_CSV),
            "monte_carlo_paths_csv": str(MC_PATHS_CSV),
            "cost_sensitivity_csv": str(COST_SENSITIVITY_CSV),
            "annual_equity_csv": str(EQUITY_CSV),
        },
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")

    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, baseline_equity, baseline_returns, baseline_applied = run_result(
        prices,
        base_lev,
        BASELINE_NAME,
        "Baseline",
        "Current default strategy",
        "Guarded A5/B25/X40/Y15 with a 0.75% SMA20 lead guard.",
        extra={**base_counts, "overlay_active_days": 0},
    )

    rows = [baseline_row]
    results: dict[str, tuple[pd.Series, pd.Series, pd.Series]] = {
        BASELINE_NAME: (baseline_equity, baseline_returns, baseline_applied)
    }
    metadata: dict[str, dict[str, float | int | str]] = {
        BASELINE_NAME: {"category": "Baseline", "trail_level": np.nan, "cap": np.nan, "reset_rule": ""}
    }

    specs = all_trail_specs()
    print(f"Testing {len(specs)} trail variants...", flush=True)
    for spec in specs:
        lev, extra = apply_trail_spec(prices, base_lev, baseline_equity, spec)
        row, equity, returns, applied = run_result(
            prices,
            lev,
            spec.strategy,
            "Recovery-tier trailing stop",
            f"Strategy-equity trail {spec.trail_level:.1%}; {spec.cap_label}; {spec.reset_label}.",
            "Focused default validation of recovery-trail mechanics.",
            extra=extra,
        )
        rows.append(row)
        results[spec.strategy] = (equity, returns, applied)
        metadata[spec.strategy] = {
            "category": "Recovery-tier trailing stop",
            "trail_level": spec.trail_level,
            "cap": spec.cap,
            "reset_rule": spec.reset_rule,
        }

    sensitivity = compare_to_baseline(pd.DataFrame(rows), baseline_row)
    sensitivity.to_csv(SENSITIVITY_CSV, index=False)

    selected_specs = [primary_spec(0.05), primary_spec(0.075), primary_spec(0.10), TrailSpec(0.05, 2.0, PRIMARY_RESET_RULE)]
    selected_names = [BASELINE_NAME] + [spec.strategy for spec in selected_specs]
    annual_equity(results, selected_names).to_csv(EQUITY_CSV, index=False)

    subperiod_defs = [
        ("Full sample", prices.index[0].date().isoformat(), prices.index[-1].date().isoformat()),
        ("1996-2005", "1996-01-01", "2005-12-31"),
        ("2006-2015", "2006-01-01", "2015-12-31"),
        ("2016-2026", "2016-01-01", "2026-12-31"),
    ]
    crisis_defs = [
        ("2000-2003", "2000-01-01", "2003-12-31"),
        ("2007-2009", "2007-01-01", "2009-12-31"),
        ("2020", "2020-01-01", "2020-12-31"),
        ("2022-2023", "2022-01-01", "2023-12-31"),
    ]
    window_results = {name: results[name] for name in selected_names}
    subperiod_rows = []
    for label, start, end in subperiod_defs:
        subperiod_rows.extend(compute_window_stats(label, start, end, window_results, BASELINE_NAME, metadata))
    subperiods = pd.DataFrame(subperiod_rows)
    subperiods.to_csv(SUBPERIODS_CSV, index=False)

    crisis_rows = []
    for label, start, end in crisis_defs:
        crisis_rows.extend(compute_window_stats(label, start, end, window_results, BASELINE_NAME, metadata))
    crises = pd.DataFrame(crisis_rows)
    crises.to_csv(CRISIS_WINDOWS_CSV, index=False)

    print("Running 500-path focused Monte Carlo...", flush=True)
    mc_specs = [primary_spec(level) for level in MC_LEVELS]
    mc_paths, mc_summary = monte_carlo(prices, mc_specs)
    mc_paths.to_csv(MC_PATHS_CSV, index=False)
    mc_summary.to_csv(MC_SUMMARY_CSV, index=False)

    costs = cost_sensitivity(prices, selected_specs[:3])
    costs.to_csv(COST_SENSITIVITY_CSV, index=False)

    meta = recommendation_metadata(sensitivity, subperiods, crises, mc_summary, costs, prices)
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    target = sensitivity[sensitivity["strategy"] == TARGET_NAME].iloc[0]
    print("\nTarget full-sample result:")
    print(
        pd.DataFrame(
            [
                {
                    "strategy": TARGET_NAME,
                    "cagr": f"{float(target['cagr']) * 100:.2f}%",
                    "max_drawdown": f"{float(target['max_drawdown']) * 100:.2f}%",
                    "sharpe": f"{float(target['sharpe']):.3f}",
                    "cagr_delta_pp": f"{float(target['cagr_delta_pp']):+.2f}",
                    "dd_improvement_pp": f"{float(target['max_dd_improvement_pp']):+.2f}",
                }
            ]
        ).to_string(index=False)
    )
    print("\nRecommendation:")
    print(meta["recommendation"])
    print(meta["rationale"])
    print(f"\nWrote outputs with prefix {PREFIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
