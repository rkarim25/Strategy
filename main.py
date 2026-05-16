"""Run systematic S&P 500 strategies with hard DD cap, costs, and reporting."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import DEFAULT_MAX_DRAWDOWN, INITIAL_CAPITAL, PortfolioEngine, passes_drawdown_limit
from reporting import (
    BENCHMARK_LABEL,
    build_stats_dataframe,
    build_strategy_details_csv,
    format_stats_for_display,
    plot_all_strategies,
    plot_strategy_vs_benchmark,
    print_stats_table,
    split_included_excluded,
)
from strategies import LeverageStrategy, all_strategies

OUTPUT_DIR = Path("output")
STATS_CSV = OUTPUT_DIR / "strategy_stats.csv"
STATS_FULL_CSV = OUTPUT_DIR / "strategy_stats_full.csv"
DETAILS_CSV = OUTPUT_DIR / "strategy_rules_and_levels.csv"
EXCLUDED_CSV = OUTPUT_DIR / "excluded_strategies.csv"
COMBINED_CHART = OUTPUT_DIR / "approved_strategies_vs_buyhold.pdf"
COMBINED_ALL_CHART = OUTPUT_DIR / "all_strategies_vs_buyhold.pdf"


def run_backtests(
    prices,
    strategies: list[LeverageStrategy],
    max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
):
    strategy_engine = PortfolioEngine(
        max_drawdown_limit=max_drawdown,
        hard_drawdown_floor=True,
    )
    benchmark_engine = PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False)
    results = {}

    benchmark = benchmark_engine.run(prices, leverage=1.0, name=BENCHMARK_LABEL)
    results[BENCHMARK_LABEL] = benchmark

    print(
        f"\nRunning {len(strategies)} strategies | "
        f"Start: ${INITIAL_CAPITAL:.0f} | "
        f"Hard DD cap: {max_drawdown * 100:.0f}% | "
        f"Trading cost: 1.0% from mid on leverage changes\n"
    )

    for strategy in strategies:
        lev = strategy.generate_leverage(prices)
        result = strategy_engine.run(prices, leverage=lev, name=strategy.spec.name)
        results[strategy.spec.name] = result
        ok = passes_drawdown_limit(result.equity, max_drawdown)
        status = "PASS" if ok else "EXCLUDED"
        peak = result.equity.cummax()
        max_dd = ((result.equity - peak) / peak).min()
        print(
            f"  [{status}] {strategy.spec.name}: "
            f"final=${result.equity.iloc[-1]:,.2f}, "
            f"max DD={max_dd * 100:.2f}%, "
            f"costs=${result.trading_costs_total:.2f}, "
            f"rebalances={result.rebalance_count}"
        )

    return results


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("Downloading market data...")
    prices = load_backtest_data()
    print(
        f"Loaded {len(prices)} trading days "
        f"({prices.index[0].date()} to {prices.index[-1].date()})."
    )

    strategies = all_strategies()
    results = run_backtests(prices, strategies)

    stats_full = build_stats_dataframe(results, max_dd_limit=DEFAULT_MAX_DRAWDOWN)
    included_df, excluded_df = split_included_excluded(stats_full)

    details_df = build_strategy_details_csv(strategies, DEFAULT_MAX_DRAWDOWN)
    details_df.to_csv(DETAILS_CSV, index=False)

    stats_full.to_csv(STATS_FULL_CSV)

    # Rich CSV: metrics + buy/sell rules per row
    details_idx = details_df.set_index("strategy")
    included_with_rules = included_df.join(
        details_idx[
            [
                "overview",
                "buy_condition",
                "sell_condition",
                "buy_levels",
                "sell_levels",
                "target_leverage",
                "risk_overlay",
                "trading_cost",
                "annual_cash_inflow",
                "starting_capital",
            ]
        ],
        how="left",
    )
    included_with_rules.to_csv(STATS_CSV)

    if len(excluded_df):
        excluded_df.to_csv(EXCLUDED_CSV)
    else:
        pd.DataFrame(
            [{"message": "No strategies excluded; all passed the drawdown limit."}]
        ).to_csv(EXCLUDED_CSV, index=False)

    print_stats_table(included_df, title="APPROVED STRATEGIES (within 20% max drawdown)")
    if len(excluded_df):
        print_stats_table(excluded_df, title="EXCLUDED STRATEGIES (breached drawdown limit)")

    equities = {name: r.equity for name, r in results.items()}
    approved_names = list(included_df.index)
    approved_equities = {k: equities[k] for k in approved_names if k in equities}
    plot_all_strategies(approved_equities, COMBINED_CHART, title="Approved Strategies vs Buy & Hold")
    plot_all_strategies(equities, COMBINED_ALL_CHART, title="All Strategies vs Buy & Hold")

    strategy_dir = OUTPUT_DIR / "strategies"
    strategy_dir.mkdir(exist_ok=True)
    bench_eq = equities[BENCHMARK_LABEL]
    for name in approved_names:
        if name == BENCHMARK_LABEL:
            continue
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        plot_strategy_vs_benchmark(equities[name], bench_eq, name, strategy_dir / f"{safe}.pdf")

    print(f"Approved stats:     {STATS_CSV}")
    print(f"Full stats:         {STATS_FULL_CSV}")
    print(f"Rules & levels:     {DETAILS_CSV}")
    print(f"Excluded list:      {EXCLUDED_CSV}")
    print(f"Approved chart:     {COMBINED_CHART}")
    print(f"All-strategies chart: {COMBINED_ALL_CHART}")
    print(f"Per-strategy PDFs:  {strategy_dir}/ (approved only)")
    n_approved = int(included_df.drop(BENCHMARK_LABEL, errors="ignore")["within_dd_limit"].sum())
    print(f"\nSystematic strategies approved: {n_approved} | Excluded: {len(excluded_df)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
