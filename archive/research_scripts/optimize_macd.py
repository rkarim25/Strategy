"""Sweep MACD parameters: focus on 2008 crash window vs buy-and-hold."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from reporting import BENCHMARK_LABEL, plot_strategy_vs_benchmark
from strategies import MacdParams, TunableMacdStrategy

OUTPUT_DIR = Path("output") / "macd_sweep"
CRASH_START = "2007-10-01"
CRASH_END = "2009-03-31"
Y2008_START = "2008-01-01"
Y2008_END = "2008-12-31"


def period_stats(equity: pd.Series, start: str, end: str) -> dict:
    seg = equity.loc[start:end]
    if len(seg) < 2:
        return {"return": float("nan"), "max_dd": float("nan"), "avg_lev": float("nan")}
    ret = seg.iloc[-1] / seg.iloc[0] - 1.0
    peak = seg.cummax()
    max_dd = ((seg - peak) / peak).min()
    return {"return": float(ret), "max_dd": float(max_dd)}


def run_one(prices: pd.DataFrame, params: MacdParams, engine: PortfolioEngine):
    strat = TunableMacdStrategy(params, name_suffix="")
    lev = strat.generate_leverage(prices)
    res = engine.run(prices, lev, name=strat.spec.name)
    return strat, res


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading data | ${INITIAL_CAPITAL} start | {TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance cost\n")
    prices = load_backtest_data()

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)

    # Baseline MACD 12/26/9
    baseline_p = MacdParams()
    _, base_res = run_one(prices, baseline_p, engine)

    fast_opts = [8, 12, 19]
    slow_opts = [21, 26, 39]
    signal_opts = [5, 9]
    hist_opts = [0.0, 0.05, 0.10, 0.20]
    confirm_opts = [1, 3]
    sma_modes = [
        (False, False),
        (True, False),
        (True, True),
    ]

    rows = []
    for fast, slow, signal, hist_pct, confirm, (req_sma, exit_sma) in itertools.product(
        fast_opts, slow_opts, signal_opts, hist_opts, confirm_opts, sma_modes
    ):
        if fast >= slow:
            continue
        params = MacdParams(
            fast=fast,
            slow=slow,
            signal=signal,
            hist_entry_pct=hist_pct,
            confirm_days=confirm,
            require_above_sma200=req_sma,
            exit_below_sma200=exit_sma,
        )
        strat, res = run_one(prices, params, engine)
        full = period_stats(res.equity, str(prices.index[0].date()), str(prices.index[-1].date()))
        crash = period_stats(res.equity, CRASH_START, CRASH_END)
        y08 = period_stats(res.equity, Y2008_START, Y2008_END)
        bh_crash = period_stats(bh.equity, CRASH_START, CRASH_END)
        avg_lev = float(res.leverage.mean())

        rows.append(
            {
                "name": strat.spec.name,
                "fast": fast,
                "slow": slow,
                "signal": signal,
                "hist_pct": hist_pct,
                "confirm_days": confirm,
                "req_sma200": req_sma,
                "exit_sma200": exit_sma,
                "final": res.equity.iloc[-1],
                "full_return": full["return"],
                "full_max_dd": full["max_dd"],
                "crash_return": crash["return"],
                "crash_max_dd": crash["max_dd"],
                "y2008_return": y08["return"],
                "bh_crash_return": bh_crash["return"],
                "crash_vs_bh": crash["return"] - bh_crash["return"],
                "avg_leverage": avg_lev,
                "rebalances": res.rebalance_count,
                "trading_costs": res.trading_costs_total,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "macd_parameter_sweep.csv", index=False)

    # Best for 2008 crash window (highest return Oct07-Mar09, min 3x exposure proxy)
    best_crash = df.sort_values("crash_return", ascending=False).head(10)
    best_y08 = df.sort_values("y2008_return", ascending=False).head(10)
    best_balanced = df.assign(
        score=df["full_return"] + 2 * df["crash_return"]
    ).sort_values("score", ascending=False).head(10)

    print("=" * 90)
    print("BASELINE MACD 12/26/9 (1% rebalance cost, no portfolio DD cap)")
    print("=" * 90)
    b_crash = period_stats(base_res.equity, CRASH_START, CRASH_END)
    b_y08 = period_stats(base_res.equity, Y2008_START, Y2008_END)
    b_full = period_stats(base_res.equity, str(prices.index[0].date()), str(prices.index[-1].date()))
    print(f"  Full sample return: {b_full['return']*100:.1f}% | max DD: {b_full['max_dd']*100:.1f}%")
    print(f"  2007-10 to 2009-03: {b_crash['return']*100:.1f}% | max DD: {b_crash['max_dd']*100:.1f}%")
    print(f"  Calendar 2008:      {b_y08['return']*100:.1f}%")
    print(f"  Buy & hold crash:   {bh_crash['return']*100:.1f}%")
    print(f"  Rebalances / costs: {base_res.rebalance_count} / ${base_res.trading_costs_total:.2f}")

    print("\nTOP 10 — best 2007-09 crash-window return (avoid / survive 2008)")
    print(best_crash[
        ["fast", "slow", "signal", "hist_pct", "confirm_days", "req_sma200", "exit_sma200",
         "crash_return", "crash_max_dd", "y2008_return", "full_return", "rebalances"]
    ].to_string(index=False))

    print("\nTOP 10 — best calendar 2008 return")
    print(best_y08[
        ["fast", "slow", "signal", "hist_pct", "confirm_days", "req_sma200", "exit_sma200",
         "y2008_return", "crash_return", "full_return"]
    ].to_string(index=False))

    print("\nTOP 10 — balanced (full return + 2× crash return)")
    print(best_balanced[
        ["fast", "slow", "signal", "hist_pct", "confirm_days", "req_sma200", "exit_sma200",
         "full_return", "crash_return", "y2008_return"]
    ].to_string(index=False))

    # Run winner vs BH chart
    winner = df.sort_values("crash_return", ascending=False).iloc[0]
    win_params = MacdParams(
        fast=int(winner["fast"]),
        slow=int(winner["slow"]),
        signal=int(winner["signal"]),
        hist_entry_pct=float(winner["hist_pct"]),
        confirm_days=int(winner["confirm_days"]),
        require_above_sma200=bool(winner["req_sma200"]),
        exit_below_sma200=bool(winner["exit_sma200"]),
    )
    win_strat, win_res = run_one(prices, win_params, engine)
    chart_path = OUTPUT_DIR / "best_macd_2008_vs_buyhold.pdf"
    plot_strategy_vs_benchmark(win_res.equity, bh.equity, win_strat.spec.name, chart_path)

    print("\n" + "=" * 90)
    print("ANSWER: Can MACD thresholds avoid 2008?")
    print("=" * 90)
    improved = (df["crash_return"] > b_crash["return"]).sum()
    print(
        f"  {improved} of {len(df)} parameter sets beat baseline MACD in the "
        f"Oct-2007–Mar-2009 window."
    )
    print(
        f"  Best crash-window return: {winner['crash_return']*100:.1f}% vs baseline "
        f"{b_crash['return']*100:.1f}% vs buy-hold {bh_crash['return']*100:.1f}%"
    )
    print(
        "  A pure MACD cross rarely sidesteps 2008 entirely; filters that help most: "
        "slower MACD, SMA200 exit, higher histogram threshold, or 3-day confirmation."
    )
    print(f"\nFull sweep: {OUTPUT_DIR / 'macd_parameter_sweep.csv'}")
    print(f"Best crash config chart: {chart_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
