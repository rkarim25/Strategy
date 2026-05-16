"""S&P + cash trend rules vs buy-and-hold (2008 crisis focus)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, PortfolioEngine
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL, format_stats_for_display, plot_all_strategies

OUTPUT_DIR = Path("output") / "trend_cash"
CRASH_START, CRASH_END = "2007-10-01", "2009-03-31"
Y2008_START, Y2008_END = "2008-01-01", "2008-12-31"


def exposure_sma200(prices: pd.DataFrame) -> pd.Series:
    """1 = fully in SPX, 0 = cash (T-Bill)."""
    close = prices["spx_close"]
    sma = close.rolling(200, min_periods=200).mean()
    return (close > sma).astype(float)


def exposure_sma10m(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"]
    sma = close.resample("ME").last().rolling(10, min_periods=10).mean()
    sma_daily = sma.reindex(close.index, method="ffill")
    return (close > sma_daily).astype(float)


def exposure_momentum_12_1(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"]
    mom = close.shift(21) / close.shift(252) - 1.0
    return (mom > 0).astype(float)


def period_return(equity: pd.Series, start: str, end: str) -> float:
    seg = equity.loc[start:end]
    if len(seg) < 2:
        return float("nan")
    return float(seg.iloc[-1] / seg.iloc[0] - 1.0)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=0.0,
    )

    rules = [
        ("200-day SMA", exposure_sma200),
        ("10-month SMA", exposure_sma10m),
        ("12-1 month momentum", exposure_momentum_12_1),
    ]

    results = {}
    rows = []

    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)
    results[BENCHMARK_LABEL] = bh

    for name, fn in rules:
        exp = fn(prices)
        res = engine.run(prices, exp, name=name)
        results[name] = res

        stats = comprehensive_stats(
            res.equity, res.daily_returns, benchmark_equity=bh.equity
        )
        pct_in = float(exp.mean() * 100)
        rows.append(
            {
                "Strategy": name,
                **stats,
                "pct_days_in_sp500": pct_in,
                "pct_days_cash": 100 - pct_in,
                "crash_07_09": period_return(res.equity, CRASH_START, CRASH_END),
                "calendar_2008": period_return(res.equity, Y2008_START, Y2008_END),
            }
        )

    bh_stats = comprehensive_stats(bh.equity, bh.daily_returns)
    rows.insert(
        0,
        {
            "Strategy": BENCHMARK_LABEL,
            **bh_stats,
            "pct_days_in_sp500": 100.0,
            "pct_days_cash": 0.0,
            "crash_07_09": period_return(bh.equity, CRASH_START, CRASH_END),
            "calendar_2008": period_return(bh.equity, Y2008_START, Y2008_END),
        },
    )

    df = pd.DataFrame(rows).set_index("Strategy")
    df.to_csv(OUTPUT_DIR / "trend_cash_stats.csv")

    display = df[
        [
            "cagr",
            "volatility",
            "sharpe",
            "sortino",
            "max_drawdown",
            "calmar",
            "final_value",
            "pct_days_in_sp500",
            "crash_07_09",
            "calendar_2008",
        ]
    ].copy()
    for c in ("crash_07_09", "calendar_2008"):
        display[c] = display[c].map(lambda x: f"{x * 100:.1f}%")
    print(f"\nS&P + cash | ${INITIAL_CAPITAL} start | 10% annual inflow | cash earns T-Bill\n")
    print(format_stats_for_display(
        df[["cagr", "volatility", "sharpe", "sortino", "max_drawdown", "final_value", "pct_days_in_sp500"]]
    ).to_string())
    print("\n2008 crisis windows:")
    print(display[["crash_07_09", "calendar_2008", "pct_days_in_sp500"]].to_string())

    equities = {k: v.equity for k, v in results.items()}
    plot_all_strategies(
        equities,
        OUTPUT_DIR / "trend_cash_vs_buyhold.pdf",
        title="Trend + Cash vs Buy & Hold (Log Scale)",
    )
    print(f"\nSaved: {OUTPUT_DIR / 'trend_cash_stats.csv'}")
    print(f"Chart:  {OUTPUT_DIR / 'trend_cash_vs_buyhold.pdf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
