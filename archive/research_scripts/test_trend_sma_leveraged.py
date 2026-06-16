"""200d / 10-month SMA with 2x or 3x when in trend, cash when out."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import FUNDING_SPREAD, INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL, format_stats_for_display, plot_all_strategies

OUTPUT_DIR = Path("output") / "trend_sma_leveraged"
CRASH_START, CRASH_END = "2007-10-01", "2009-03-31"
Y2008_START, Y2008_END = "2008-01-01", "2008-12-31"


def _in_trend(prices: pd.DataFrame, kind: str) -> pd.Series:
    close = prices["spx_close"]
    if kind == "200d":
        sma = close.rolling(200, min_periods=200).mean()
        return close > sma
    sma = close.resample("ME").last().rolling(10, min_periods=10).mean()
    sma_daily = sma.reindex(close.index, method="ffill")
    return close > sma_daily


def leverage_sma(prices: pd.DataFrame, kind: str, levered_when_in: float) -> pd.Series:
    """cash (0) when below SMA; levered_when_in (1, 2, or 3) when above."""
    trend = _in_trend(prices, kind)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[trend] = levered_when_in
    return lev


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
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    configs = [
        (BENCHMARK_LABEL, "constant", 1.0),
        ("Buy & Hold 2x", "constant", 2.0),
        ("Buy & Hold 3x", "constant", 3.0),
        ("200d SMA + cash (1x)", "200d", 1.0),
        ("200d SMA @ 2x / cash", "200d", 2.0),
        ("200d SMA @ 3x / cash", "200d", 3.0),
        ("10m SMA + cash (1x)", "10m", 1.0),
        ("10m SMA @ 2x / cash", "10m", 2.0),
        ("10m SMA @ 3x / cash", "10m", 3.0),
    ]

    rows = []
    results = {}

    for name, kind, lev in configs:
        if kind == "constant":
            res = engine.run(prices, lev, name=name)
        else:
            lev_series = leverage_sma(prices, kind, lev)
            res = engine.run(prices, lev_series, name=name)

        results[name] = res
        bh = results[BENCHMARK_LABEL]
        stats = comprehensive_stats(
            res.equity,
            res.daily_returns,
            benchmark_equity=bh.equity if bh and name != BENCHMARK_LABEL else None,
            trading_costs_total=res.trading_costs_total,
        )
        rows.append(
            {
                "Strategy": name,
                **stats,
                "pct_days_levered": (res.leverage > 1.0).mean() * 100,
                "pct_days_cash": (res.leverage <= 0.0).mean() * 100,
                "avg_leverage": float(res.leverage.mean()),
                "borrowing_costs": res.funding_costs_total,
                "trading_costs": res.trading_costs_total,
                "rebalances": res.rebalance_count,
                "crash_07_09": period_return(res.equity, CRASH_START, CRASH_END),
                "calendar_2008": period_return(res.equity, Y2008_START, Y2008_END),
            }
        )

    df = pd.DataFrame(rows).set_index("Strategy")

    order = [
        BENCHMARK_LABEL,
        "Buy & Hold 2x",
        "Buy & Hold 3x",
        "200d SMA + cash (1x)",
        "200d SMA @ 2x / cash",
        "200d SMA @ 3x / cash",
        "10m SMA + cash (1x)",
        "10m SMA @ 2x / cash",
        "10m SMA @ 3x / cash",
    ]
    df = df.reindex(order)

    meta = pd.DataFrame(
        [
            {"Strategy": BENCHMARK_LABEL, "type": "Buy & Hold", "filter": "None", "leverage": "1x"},
            {"Strategy": "Buy & Hold 2x", "type": "Buy & Hold", "filter": "None", "leverage": "2x"},
            {"Strategy": "Buy & Hold 3x", "type": "Buy & Hold", "filter": "None", "leverage": "3x"},
            {"Strategy": "200d SMA + cash (1x)", "type": "200-day SMA", "filter": "200d SMA", "leverage": "1x / cash"},
            {"Strategy": "200d SMA @ 2x / cash", "type": "200-day SMA", "filter": "200d SMA", "leverage": "2x / cash"},
            {"Strategy": "200d SMA @ 3x / cash", "type": "200-day SMA", "filter": "200d SMA", "leverage": "3x / cash"},
            {"Strategy": "10m SMA + cash (1x)", "type": "10-month SMA", "filter": "10m SMA", "leverage": "1x / cash"},
            {"Strategy": "10m SMA @ 2x / cash", "type": "10-month SMA", "filter": "10m SMA", "leverage": "2x / cash"},
            {"Strategy": "10m SMA @ 3x / cash", "type": "10-month SMA", "filter": "10m SMA", "leverage": "3x / cash"},
        ]
    ).set_index("Strategy")
    full_list = meta.join(df, how="left")
    full_list.to_csv(OUTPUT_DIR / "full_strategy_list.csv")
    df.to_csv(OUTPUT_DIR / "sma_leveraged_stats.csv")

    core = [
        "cagr", "volatility", "sharpe", "max_drawdown", "final_value",
        "pct_days_levered", "pct_days_cash", "borrowing_costs", "trading_costs",
        "crash_07_09", "calendar_2008",
    ]
    print(
        f"\n${INITIAL_CAPITAL} start | 10% annual inflow | "
        f"{TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance | "
        f"borrowing ((L-1)*(TBill+{FUNDING_SPREAD*100:.1f}%))/252\n"
    )
    print(
        "Rules: Buy & hold = constant 1x/2x/3x always. "
        "SMA = 1x/2x/3x when above SMA, cash when below.\n"
    )
    display_df = df[core[:8]].copy()
    display_df["pct_days_levered"] = df["pct_days_levered"]
    display_df["pct_days_cash"] = df["pct_days_cash"]
    print(format_stats_for_display(display_df).to_string())

    crisis = df[["crash_07_09", "calendar_2008", "avg_leverage"]].copy()
    for c in ("crash_07_09", "calendar_2008"):
        crisis[c] = crisis[c].map(lambda x: f"{x * 100:.1f}%")
    crisis["avg_leverage"] = df["avg_leverage"].map(lambda x: f"{x:.2f}x")
    print("\nCrisis windows & avg leverage:")
    print(crisis.to_string())

    plot_all_strategies(
        {k: v.equity for k, v in results.items()},
        OUTPUT_DIR / "sma_leveraged_vs_buyhold.pdf",
        title="SMA Trend & Buy & Hold: 1x / 2x / 3x",
    )
    print(f"\nSaved: {OUTPUT_DIR / 'full_strategy_list.csv'}")
    print(f"       {OUTPUT_DIR / 'sma_leveraged_stats.csv'}")
    print(f"Chart:  {OUTPUT_DIR / 'sma_leveraged_vs_buyhold.pdf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
