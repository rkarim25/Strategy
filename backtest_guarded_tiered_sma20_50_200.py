"""Backtest guarded tiered strategy across SMA20, SMA50, and SMA200."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "guarded_tiered_sma20_50_200"

SMA_WINDOWS = [20, 50, 200]
LEVERAGES = [1.0, 2.0, 3.0]
TRIGGER_A = 0.10
TRIGGER_B = 0.20


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def sma_cash_leverage(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > sma] = leverage
    return lev


def guarded_tiered_leverage(prices: pd.DataFrame, window: int) -> tuple[pd.Series, dict]:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()
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
        above_sma = px > float(sma.loc[dt])
        base_lev = 1.0 if above_sma else 0.0

        if regime == "tier3":
            if px / entry_close - 1.0 >= 1.0 / 3.0:
                regime = "base"
            elif above_sma:
                lev.loc[dt] = 3.0
                continue
            else:
                tier_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -TRIGGER_B and above_sma:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= 0.50 / 2.0:
                regime = "base"
            elif above_sma:
                lev.loc[dt] = 2.0
                continue
            else:
                tier_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if dd <= -TRIGGER_B and above_sma:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -TRIGGER_A and above_sma:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            if dd <= -TRIGGER_A and not above_sma:
                tier_blocked_days += 1
            lev.loc[dt] = base_lev

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "tier_blocked_days": tier_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def add_row(
    rows: list[dict],
    prices: pd.DataFrame,
    engine: PortfolioEngine,
    strategy: str,
    sma_window: int | str,
    lev: pd.Series,
    extra: dict | None = None,
) -> None:
    res = engine.run(prices, lev, name=strategy)
    stats = comprehensive_stats(res.equity, res.daily_returns)
    row = {
        "strategy": strategy,
        "sma_window": sma_window,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(res.equity.iloc[-1]),
        "rebalances": res.rebalance_count,
        "funding_costs_total": res.funding_costs_total,
        "trading_costs_total": res.trading_costs_total,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }
    if extra:
        row.update(extra)
    rows.append(row)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    engine = make_engine()
    rows: list[dict] = []

    for lev_value in LEVERAGES:
        lev = pd.Series(lev_value, index=prices.index)
        add_row(rows, prices, engine, f"Buy & hold {lev_value:.0f}x", "n/a", lev)

    for window in SMA_WINDOWS:
        for lev_value in LEVERAGES:
            lev = sma_cash_leverage(prices, window, lev_value)
            add_row(rows, prices, engine, f"SMA{window} {lev_value:.0f}x/cash", window, lev)

        lev, counts = guarded_tiered_leverage(prices, window)
        add_row(
            rows,
            prices,
            engine,
            f"Guarded A10/B20 SMA{window}",
            window,
            lev,
            counts,
        )

    df = pd.DataFrame(rows)
    csv_path = OUTPUT_DIR / "guarded_tiered_sma20_50_200_results.csv"
    df.to_csv(csv_path, index=False)

    disp = df.copy()
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")

    print(
        f"Guarded tiered SMA20/50/200 | ${INITIAL_CAPITAL:.0f} start | "
        f"${ANNUAL_INFLOW_USD:.0f}/year inflow | "
        f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)\n")
    print(
        disp[
            [
                "strategy",
                "sma_window",
                "cagr",
                "ann_volatility",
                "sharpe",
                "max_drawdown",
                "end_$",
                "pct_days_cash",
                "pct_days_1x",
                "pct_days_2x",
                "pct_days_3x",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
