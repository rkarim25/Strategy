"""MACD at 3x with borrowing cost (T-Bill + 60bps) and 1% rebalance cost."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import FUNDING_SPREAD, INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL, format_stats_for_display, plot_strategy_vs_benchmark
from strategies import MacdParams, TunableMacdStrategy

OUTPUT_DIR = Path("output") / "macd_3x"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    configs = [
        ("Buy & Hold 1x", None),
        (
            "MACD 12/26/9 @ 3x",
            MacdParams(fast=12, slow=26, signal=9, levered_level=3.0),
        ),
        (
            "MACD 8/21/5 @ 3x (tuned)",
            MacdParams(fast=8, slow=21, signal=5, hist_entry_pct=0.20, levered_level=3.0),
        ),
        (
            "MACD 8/21/5 @ 1x (tuned, no leverage)",
            MacdParams(fast=8, slow=21, signal=5, hist_entry_pct=0.20, levered_level=1.0),
        ),
    ]

    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)
    rows = []

    for label, params in configs:
        if params is None:
            res = bh
        else:
            strat = TunableMacdStrategy(params)
            lev = strat.generate_leverage(prices)
            res = engine.run(prices, lev, name=label)

        stats = comprehensive_stats(
            res.equity,
            res.daily_returns,
            benchmark_equity=bh.equity if label != BENCHMARK_LABEL else None,
            trading_costs_total=res.trading_costs_total,
        )
        pct_3x = (res.leverage >= 2.5).mean() * 100
        rows.append(
            {
                "Strategy": label,
                "cagr": stats["cagr"],
                "volatility": stats["volatility"],
                "sharpe": stats["sharpe"],
                "sortino": stats["sortino"],
                "max_drawdown": stats["max_drawdown"],
                "calmar": stats["calmar"],
                "final_value": stats["final_value"],
                "pct_days_at_3x": pct_3x,
                "rebalances": res.rebalance_count,
                "trading_costs": res.trading_costs_total,
                "borrowing_costs": res.funding_costs_total,
                "total_costs": res.trading_costs_total + res.funding_costs_total,
            }
        )

    df = pd.DataFrame(rows).set_index("Strategy")
    df.to_csv(OUTPUT_DIR / "macd_3x_stats.csv")

    display_cols = [
        "cagr", "volatility", "sharpe", "sortino", "max_drawdown",
        "final_value", "pct_days_at_3x", "borrowing_costs", "trading_costs", "total_costs",
    ]
    print(f"\nBorrowing: ((L-1) * (T-Bill + {FUNDING_SPREAD*100:.1f}%)) / 252 daily on levered days")
    print(f"Rebalance: {TRADING_COST_FROM_MID_PCT*100:.1f}% of |dL| x AUM | Start ${INITIAL_CAPITAL}\n")
    print(format_stats_for_display(df[display_cols]).to_string())

    tuned = TunableMacdStrategy(
        MacdParams(fast=8, slow=21, signal=5, hist_entry_pct=0.20, levered_level=3.0)
    )
    tuned_res = engine.run(prices, tuned.generate_leverage(prices), name="tuned")
    plot_strategy_vs_benchmark(
        tuned_res.equity,
        bh.equity,
        "MACD 8/21/5 @ 3x",
        OUTPUT_DIR / "macd_3x_tuned_vs_buyhold.pdf",
    )
    print(f"\nSaved: {OUTPUT_DIR / 'macd_3x_stats.csv'}")
    print(f"Chart: {OUTPUT_DIR / 'macd_3x_tuned_vs_buyhold.pdf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
