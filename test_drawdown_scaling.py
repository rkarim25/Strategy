"""Backtest: SPX drawdown scaling (2x @ -20%, 3x @ -50%) vs buy-and-hold."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, PortfolioEngine
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL, format_stats_for_display, plot_strategy_vs_benchmark
from strategies import DrawdownScalingStrategy

OUTPUT_DIR = Path("output") / "dd_scaling"
CHART_PATH = OUTPUT_DIR / "dd_scaling_vs_buyhold.pdf"
STATS_CSV = OUTPUT_DIR / "dd_scaling_stats.csv"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading market data...")
    prices = load_backtest_data()
    print(
        f"{len(prices)} days ({prices.index[0].date()} to {prices.index[-1].date()}) | "
        f"Start ${INITIAL_CAPITAL:.0f} | 10% annual inflow\n"
    )

    strategy = DrawdownScalingStrategy()
    lev = strategy.generate_leverage(prices)

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=0.0,
    )

    dd_result = engine.run(prices, lev, name=strategy.spec.name)
    bh_result = engine.run(prices, 1.0, name=BENCHMARK_LABEL)

    rows = []
    for name, res in [(strategy.spec.name, dd_result), (BENCHMARK_LABEL, bh_result)]:
        stats = comprehensive_stats(
            res.equity,
            res.daily_returns,
            benchmark_equity=bh_result.equity if name != BENCHMARK_LABEL else None,
            trading_costs_total=res.trading_costs_total,
        )
        pct_2x = (res.leverage == 2.0).mean() * 100
        pct_3x = (res.leverage == 3.0).mean() * 100
        rows.append(
            {
                "Strategy": name,
                **stats,
                "pct_days_2x": pct_2x,
                "pct_days_3x": pct_3x,
                "pct_days_1x": (res.leverage == 1.0).mean() * 100,
            }
        )

    stats_df = pd.DataFrame(rows).set_index("Strategy")
    stats_df.to_csv(STATS_CSV)

    key = [
        "cagr", "total_return", "max_drawdown", "sharpe", "sortino", "calmar",
        "volatility", "final_value", "pct_days_2x", "pct_days_3x", "pct_days_1x",
    ]
    display = format_stats_for_display(stats_df[[c for c in key if c in stats_df.columns]])

    print("=" * 90)
    print("DRAWDOWN SCALING vs BUY & HOLD")
    print("=" * 90)
    print(display.to_string())
    print("=" * 90)

    print("\nStrategy rules:")
    s = strategy.spec
    print(f"  {s.buy_condition}")
    print(f"  {s.sell_condition}")
    print(f"  Levels: {s.buy_levels} | Exit: {s.sell_levels}")

    plot_strategy_vs_benchmark(
        dd_result.equity,
        bh_result.equity,
        strategy.spec.name,
        CHART_PATH,
    )
    print(f"\nChart: {CHART_PATH}")
    print(f"Stats: {STATS_CSV}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
