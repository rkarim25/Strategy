"""Test Guarded lead candidate A5/B25/X40/Y15 against original variants."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "guarded_balanced_candidate"
BACKTEST_CSV = OUTPUT_DIR / "guarded_balanced_candidate_backtest.csv"
MC_PATHS_CSV = OUTPUT_DIR / "guarded_balanced_candidate_monte_carlo_paths.csv"
MC_SUMMARY_CSV = OUTPUT_DIR / "guarded_balanced_candidate_monte_carlo_summary.csv"
MC_METADATA_JSON = OUTPUT_DIR / "guarded_balanced_candidate_monte_carlo_metadata.json"

SMA_WINDOW = 20
N_SIMS = 200
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260517


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def guarded_strategy_leverage(
    prices: pd.DataFrame,
    *,
    trigger_a: float,
    trigger_b: float,
    lead_pct_below_sma20: float,
    x_return: float,
    y_return: float,
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    base_guard = (close > sma20).fillna(False)
    recovery_guard = (close >= sma20 * (1.0 - lead_pct_below_sma20)).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev = 1.0 if base_ok else 0.0
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 3.0
                continue
            else:
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 2.0
                continue
            else:
                lev.loc[dt] = base_lev
                continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -trigger_a and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            lev.loc[dt] = base_lev

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def run_strategy(prices: pd.DataFrame, spec: dict[str, float | str]) -> dict[str, float | int | str]:
    lev, counts = guarded_strategy_leverage(
        prices,
        trigger_a=float(spec["trigger_a"]),
        trigger_b=float(spec["trigger_b"]),
        lead_pct_below_sma20=float(spec["lead_pct_below_sma20"]),
        x_return=float(spec["x_return"]),
        y_return=float(spec["y_return"]),
    )
    result = make_engine().run(prices, lev, name=str(spec["strategy"]))
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        **spec,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        **counts,
    }


def strategy_specs() -> list[dict[str, float | str]]:
    return [
        {
            "strategy": "Original strict SMA20 A10/B20 X25/Y33",
            "trigger_a": 0.10,
            "trigger_b": 0.20,
            "lead_pct_below_sma20": 0.0,
            "x_return": 0.25,
            "y_return": 1.0 / 3.0,
        },
        {
            "strategy": "Lead 0.75 A10/B20 X40/Y15",
            "trigger_a": 0.10,
            "trigger_b": 0.20,
            "lead_pct_below_sma20": 0.0075,
            "x_return": 0.40,
            "y_return": 0.15,
        },
        {
            "strategy": "Lead 0.75 A5/B25 X40/Y15",
            "trigger_a": 0.05,
            "trigger_b": 0.25,
            "lead_pct_below_sma20": 0.0075,
            "x_return": 0.40,
            "y_return": 0.15,
        },
    ]


def synthetic_market_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        sampled_idx: list[np.ndarray] = []
        while sum(len(x) for x in sampled_idx) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_idx.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(sampled_idx)[:HORIZON_DAYS]
        returns = spx_ret[idx]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {
                    "spx_close": 1000.0 * np.cumprod(1.0 + returns),
                    "tbill_rate": tbill[idx],
                },
                index=index,
            )
        )
    return paths


def monte_carlo(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, float | int | str]] = []
    specs = strategy_specs()
    for sim, path in enumerate(synthetic_market_paths(prices)):
        if sim % 25 == 0:
            print(f"Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        for spec in specs:
            row = run_strategy(path, spec)
            row["simulation"] = sim
            rows.append(row)
    paths_df = pd.DataFrame(rows)
    summary_rows = []
    for strategy, group in paths_df.groupby("strategy"):
        summary_rows.append(
            {
                "strategy": strategy,
                "median_cagr": float(group["cagr"].median()),
                "p10_cagr": float(group["cagr"].quantile(0.10)),
                "p90_cagr": float(group["cagr"].quantile(0.90)),
                "median_max_drawdown": float(group["max_drawdown"].median()),
                "p10_max_drawdown": float(group["max_drawdown"].quantile(0.10)),
                "p90_max_drawdown": float(group["max_drawdown"].quantile(0.90)),
                "median_sharpe": float(group["sharpe"].median()),
                "median_end_$": float(group["end_$"].median()),
                "prob_max_dd_worse_35pct": float((group["max_drawdown"] <= -0.35).mean()),
                "prob_max_dd_worse_40pct": float((group["max_drawdown"] <= -0.40).mean()),
                "prob_max_dd_worse_50pct": float((group["max_drawdown"] <= -0.50).mean()),
                "median_pct_days_2x": float(group["pct_days_2x"].median()),
                "median_pct_days_3x": float(group["pct_days_3x"].median()),
            }
        )
    return paths_df, pd.DataFrame(summary_rows)


def print_formatted(df: pd.DataFrame, cols: list[str]) -> None:
    disp = df.copy()
    for col in ["trigger_a", "trigger_b", "lead_pct_below_sma20", "x_return", "y_return", "cagr", "ann_volatility", "max_drawdown"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x) * 100:.2f}%")
    for col in ["median_cagr", "p10_cagr", "p90_cagr", "median_max_drawdown", "p10_max_drawdown", "p90_max_drawdown"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x) * 100:.2f}%")
    for col in ["prob_max_dd_worse_35pct", "prob_max_dd_worse_40pct", "prob_max_dd_worse_50pct"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x) * 100:.1f}%")
    for col in ["sharpe", "median_sharpe"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x):.3f}")
    for col in ["end_$", "median_end_$"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"${float(x):,.0f}")
    print(disp[cols].to_string(index=False))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    print(f"Loaded {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}", flush=True)
    backtest_df = pd.DataFrame([run_strategy(prices, spec) for spec in strategy_specs()])
    backtest_df.to_csv(BACKTEST_CSV, index=False)
    print("\nFull-sample backtest:")
    print_formatted(
        backtest_df,
        [
            "strategy",
            "trigger_a",
            "trigger_b",
            "lead_pct_below_sma20",
            "x_return",
            "y_return",
            "cagr",
            "sharpe",
            "max_drawdown",
            "end_$",
            "rebalances",
            "pct_days_2x",
            "pct_days_3x",
        ],
    )

    print("\nRunning Monte Carlo...", flush=True)
    paths_df, summary_df = monte_carlo(prices)
    paths_df.to_csv(MC_PATHS_CSV, index=False)
    summary_df.to_csv(MC_SUMMARY_CSV, index=False)
    with MC_METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "market_history_start": prices.index[0].date().isoformat(),
                "market_history_end": prices.index[-1].date().isoformat(),
                "n_sims": N_SIMS,
                "horizon_trading_days": HORIZON_DAYS,
                "horizon_years": HORIZON_DAYS / 252.0,
                "block_days": BLOCK_DAYS,
                "seed": SEED,
            },
            f,
            indent=2,
        )
    print("\nMonte Carlo summary:")
    print_formatted(
        summary_df.sort_values("median_cagr", ascending=False),
        [
            "strategy",
            "median_cagr",
            "p10_cagr",
            "p90_cagr",
            "median_max_drawdown",
            "p10_max_drawdown",
            "p90_max_drawdown",
            "median_sharpe",
            "median_end_$",
            "prob_max_dd_worse_35pct",
            "prob_max_dd_worse_40pct",
            "prob_max_dd_worse_50pct",
        ],
    )
    print(f"\nBacktest CSV: {BACKTEST_CSV}")
    print(f"Monte Carlo summary CSV: {MC_SUMMARY_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
