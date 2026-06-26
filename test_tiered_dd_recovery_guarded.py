"""Tiered S&P leverage with trend guard for recovery leverage."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

from core.data_manager import load_backtest_data
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions

OUTPUT_DIR = Path("output") / "tiered_dd_recovery_guarded"

A_LEVELS = [0.10, 0.15]
B_LEVELS = [0.20, 0.25]
GUARD_WINDOWS = [20, 50]
ANNUAL_INFLOW_USD = 10.0
BASE_SMA_WINDOW = 20


def sma_cash_leverage(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > sma] = leverage
    return lev


def guarded_tiered_leverage(
    prices: pd.DataFrame,
    trigger_a: float,
    trigger_b: float,
    guard_window: int,
) -> tuple[pd.Series, dict[str, int | float]]:
    """
    Base rule: 1x when close > SMA20, otherwise cash.

    Drawdown arms recovery tiers, but 2x/3x exposure is only allowed when
    close is above the guard SMA. If the guard fails during a tier, exposure
    drops to the base rule, but the tier remains armed until its recovery
    target is hit or a deeper tier is armed.
    """
    close = prices["spx_close"].astype(float)
    base_sma = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    guard_sma = close.rolling(guard_window, min_periods=guard_window).mean()
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    tier_blocked_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_lev = 1.0 if px > float(base_sma.loc[dt]) else 0.0
        guard_ok = px > float(guard_sma.loc[dt])

        if regime == "tier3":
            if px / entry_close - 1.0 >= 1.0 / 3.0:
                regime = "base"
            elif guard_ok:
                lev.loc[dt] = 3.0
                continue
            else:
                tier_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -trigger_b and guard_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= 0.50 / 2.0:
                regime = "base"
            elif guard_ok:
                lev.loc[dt] = 2.0
                continue
            else:
                tier_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if dd <= -trigger_b and guard_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -trigger_a and guard_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            if dd <= -trigger_a and not guard_ok:
                tier_blocked_days += 1
            lev.loc[dt] = base_lev

    counts = {
        "guard_sma": guard_window,
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "tier_blocked_days": tier_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }
    return lev, counts


def add_result_row(
    rows: list[dict],
    prices: pd.DataFrame,
    engine: PortfolioEngine,
    name: str,
    lev: pd.Series,
    extra: dict | None = None,
) -> None:
    res = engine.run(prices, lev, name=name)
    stats = comprehensive_stats(res.equity, res.daily_returns)
    alloc = invested_vs_tbills_sessions(res.leverage)
    row = {
        "strategy": name,
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
    }
    if extra:
        row.update(extra)
    rows.append(row)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )

    rows: list[dict] = []
    for ref_lev in [1.0, 2.0, 3.0]:
        lev = pd.Series(ref_lev, index=prices.index)
        add_result_row(
            rows,
            prices,
            engine,
            f"Buy & hold {ref_lev:.0f}x reference",
            lev,
            {
                "strategy_type": "reference",
                "reference_order": int(ref_lev),
                "A_trigger_pct": None,
                "B_trigger_pct": None,
                "guard_sma": None,
                "tier2_entries": 0,
                "tier3_entries": 0,
                "tier_blocked_days": 0,
                "pct_days_cash": 0.0,
                "pct_days_1x": 100.0 if ref_lev == 1.0 else 0.0,
                "pct_days_2x": 100.0 if ref_lev == 2.0 else 0.0,
                "pct_days_3x": 100.0 if ref_lev == 3.0 else 0.0,
            },
        )

    for ref_lev in [1.0, 2.0, 3.0]:
        lev = sma_cash_leverage(prices, BASE_SMA_WINDOW, ref_lev)
        add_result_row(
            rows,
            prices,
            engine,
            f"SMA20 {ref_lev:.0f}x/cash reference",
            lev,
            {
                "strategy_type": "reference",
                "reference_order": int(ref_lev) + 3,
                "A_trigger_pct": None,
                "B_trigger_pct": None,
                "guard_sma": None,
                "tier2_entries": 0,
                "tier3_entries": 0,
                "tier_blocked_days": 0,
                "pct_days_cash": float((lev <= 0).mean() * 100.0),
                "pct_days_1x": float((lev == 1.0).mean() * 100.0),
                "pct_days_2x": float((lev == 2.0).mean() * 100.0),
                "pct_days_3x": float((lev == 3.0).mean() * 100.0),
            },
        )

    for guard_window, a, b in itertools.product(GUARD_WINDOWS, A_LEVELS, B_LEVELS):
        if a >= b:
            continue
        lev, counts = guarded_tiered_leverage(prices, a, b, guard_window)
        add_result_row(
            rows,
            prices,
            engine,
            f"Guard SMA{guard_window}: A={a * 100:.0f}% to 2x / B={b * 100:.0f}% to 3x",
            lev,
            {
                "strategy_type": "guarded_tiered",
                "reference_order": 99,
                "A_trigger_pct": a * 100.0,
                "B_trigger_pct": b * 100.0,
                **counts,
            },
        )

    df = pd.DataFrame(rows)
    df["_type_order"] = df["strategy_type"].map({"reference": 0, "guarded_tiered": 1})
    df["_ref_order"] = df["reference_order"].fillna(99)
    df["_guard_order"] = df["guard_sma"].fillna(0)
    df["_a_order"] = df["A_trigger_pct"].fillna(0)
    df["_b_order"] = df["B_trigger_pct"].fillna(0)
    df = df.sort_values(["_type_order", "_ref_order", "_guard_order", "_a_order", "_b_order"]).drop(
        columns=["_type_order", "_ref_order", "_guard_order", "_a_order", "_b_order"]
    )

    csv_path = OUTPUT_DIR / "tiered_dd_recovery_guarded_results.csv"
    df.to_csv(csv_path, index=False)

    disp = df.copy()
    for c in (
        "cagr",
        "ann_volatility",
        "max_drawdown",
        "pct_days_cash",
        "pct_days_1x",
        "pct_days_2x",
        "pct_days_3x",
    ):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%" if abs(float(x)) <= 1 else f"{x:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")

    print(
        f"Guarded tiered DD recovery | ${INITIAL_CAPITAL:.0f} start | "
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
                "tier_blocked_days",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
