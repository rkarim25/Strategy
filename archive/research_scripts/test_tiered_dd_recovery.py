"""Tiered S&P leverage: SMA20 base plus drawdown-triggered recovery tiers."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats, invested_vs_tbills_sessions

OUTPUT_DIR = Path("output") / "tiered_dd_recovery"

A_LEVELS = [0.10, 0.15]
B_LEVELS = [0.20, 0.25]
ANNUAL_INFLOW_USD = 10.0
SMA_WINDOW = 20


def tiered_dd_recovery_leverage(
    prices: pd.DataFrame,
    trigger_a: float,
    trigger_b: float,
) -> tuple[pd.Series, dict[str, int]]:
    """
    Base rule: 1x when close > 20d SMA, otherwise cash.

    Recovery tiers use S&P drawdown from its prior closing high:
      - <= -A: enter/hold 2x until 2x trade return reaches +50%.
      - <= -B: enter/hold 3x until 3x trade return reaches +100%.

    Exit thresholds are translated to underlying index moves:
      - 2x +50% target -> SPX +25% from 2x entry close.
      - 3x +100% target -> SPX +33.33% from 3x entry close.
    """
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_lev = 1.0 if px > float(sma20.loc[dt]) else 0.0

        if regime == "tier3":
            if px / entry_close - 1.0 >= 1.0 / 3.0:
                regime = "base"
            else:
                lev.loc[dt] = 3.0
                continue

        if regime == "tier2":
            if dd <= -trigger_b:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= 0.50 / 2.0:
                regime = "base"
            else:
                lev.loc[dt] = 2.0
                continue

        if dd <= -trigger_b:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -trigger_a:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            lev.loc[dt] = base_lev

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }
    return lev, counts


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )

    rows = []
    for ref_lev in [1.0, 2.0, 3.0]:
        base_lev = pd.Series(0.0, index=prices.index)
        base_lev.loc[close > sma20] = ref_lev
        base_res = engine.run(prices, base_lev, name=f"SMA20 {ref_lev:.0f}x/cash reference")
        base_stats = comprehensive_stats(base_res.equity, base_res.daily_returns)
        base_alloc = invested_vs_tbills_sessions(base_res.leverage)
        rows.append(
            {
                "strategy": f"SMA20 {ref_lev:.0f}x/cash reference",
                "A_trigger_pct": None,
                "B_trigger_pct": None,
                "cagr": base_stats["cagr"],
                "ann_volatility": base_stats["volatility"],
                "sharpe": base_stats["sharpe"],
                "max_drawdown": base_stats["max_drawdown"],
                "start_$": float(INITIAL_CAPITAL),
                "end_$": float(base_res.equity.iloc[-1]),
                "pct_sessions_invested": base_alloc["pct_sessions_invested"],
                "pct_sessions_tbills": base_alloc["pct_sessions_tbills"],
                "rebalances": base_res.rebalance_count,
                "trading_costs_total": base_res.trading_costs_total,
                "funding_costs_total": base_res.funding_costs_total,
                "pct_days_cash": float((base_lev <= 0).mean() * 100.0),
                "pct_days_1x": float((base_lev == 1.0).mean() * 100.0),
                "pct_days_2x": float((base_lev == 2.0).mean() * 100.0),
                "pct_days_3x": float((base_lev == 3.0).mean() * 100.0),
                "tier2_entries": 0,
                "tier3_entries": 0,
            }
        )
    signals: dict[str, list[dict]] = {}
    for a, b in itertools.product(A_LEVELS, B_LEVELS):
        if a >= b:
            continue
        lev, counts = tiered_dd_recovery_leverage(prices, a, b)
        name = f"A={a * 100:.0f}% to 2x / B={b * 100:.0f}% to 3x"
        res = engine.run(prices, lev, name=name)
        stats = comprehensive_stats(res.equity, res.daily_returns)
        alloc = invested_vs_tbills_sessions(res.leverage)
        row = {
            "strategy": name,
            "A_trigger_pct": a * 100.0,
            "B_trigger_pct": b * 100.0,
            "cagr": stats["cagr"],
            "ann_volatility": stats["volatility"],
            "sharpe": stats["sharpe"],
            "max_drawdown": stats["max_drawdown"],
            "start_$": float(INITIAL_CAPITAL),
            "end_$": float(res.equity.iloc[-1]),
            "pct_sessions_invested": alloc["pct_sessions_invested"],
            "pct_sessions_tbills": alloc["pct_sessions_tbills"],
            "rebalances": res.rebalance_count,
            "trading_costs_total": res.trading_costs_total,
            "funding_costs_total": res.funding_costs_total,
            **counts,
        }
        rows.append(row)
        signals[f"A{a * 100:.0f}_B{b * 100:.0f}"] = [
            {
                "date": str(idx.date()),
                "leverage": float(value),
            }
            for idx, value in lev.items()
        ]

    df = pd.DataFrame(rows)
    df["_sort_a"] = df["A_trigger_pct"].fillna(-1.0)
    df["_sort_b"] = df["B_trigger_pct"].fillna(-1.0)
    df = df.sort_values(["_sort_a", "_sort_b"]).drop(columns=["_sort_a", "_sort_b"])
    csv_path = OUTPUT_DIR / "tiered_dd_recovery_results.csv"
    df.to_csv(csv_path, index=False)
    with (OUTPUT_DIR / "tiered_dd_recovery_signals.json").open("w", encoding="utf-8") as f:
        json.dump(signals, f)

    disp = df.copy()
    for c in (
        "cagr",
        "ann_volatility",
        "sharpe",
        "max_drawdown",
        "end_$",
        "pct_days_cash",
        "pct_days_1x",
        "pct_days_2x",
        "pct_days_3x",
    ):
        if c == "sharpe":
            disp[c] = disp[c].map(lambda x: f"{x:.3f}")
        elif c == "end_$":
            disp[c] = disp[c].map(lambda x: f"${x:,.2f}")
        else:
            disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%" if abs(x) <= 1 else f"{x:.2f}%")

    print(
        f"Tiered DD recovery | ${INITIAL_CAPITAL:.0f} start | "
        f"${ANNUAL_INFLOW_USD:.0f}/year inflow | {TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)\n")
    print(
        disp[
            [
                "strategy",
                "cagr",
                "ann_volatility",
                "sharpe",
                "max_drawdown",
                "end_$",
                "pct_days_cash",
                "pct_days_1x",
                "pct_days_2x",
                "pct_days_3x",
                "tier2_entries",
                "tier3_entries",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
