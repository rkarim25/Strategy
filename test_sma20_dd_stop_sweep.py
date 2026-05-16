"""SMA(20) @ 3x / cash with portfolio DD stops at 10%, 20%, 30%, 40%."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from sweep_sma_periods import leverage_daily_sma

OUTPUT_DIR = Path("output") / "sma20_dd_stop_sweep"
DD_STOPS_PCT = [10, 20, 30, 40]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    lev_signal = leverage_daily_sma(prices, window=20, levered=3.0)

    rows = []

    # Reference: no portfolio DD overlay
    eng_none = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    r0 = eng_none.run(prices, lev_signal, name="SMA20 @ 3x no DD stop")
    st0 = comprehensive_stats(r0.equity, r0.daily_returns)
    rows.append(
        _row("No DD stop (ref)", None, r0, st0),
    )

    for pct in DD_STOPS_PCT:
        lim = pct / 100.0
        eng = PortfolioEngine(
            max_drawdown_limit=lim,
            hard_drawdown_floor=True,
            trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        )
        res = eng.run(prices, lev_signal, name=f"SMA20 @ 3x DD stop {pct}%")
        st = comprehensive_stats(res.equity, res.daily_returns)
        rows.append(_row(f"{pct}% DD stop", lim, res, st))

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "sma20_3x_dd_stop_results.csv", index=False)

    disp = df.copy()
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["start_$"] = disp["start_$"].map(lambda x: f"${x:,.2f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")

    print(f"SMA20 @ 3x / cash | ${INITIAL_CAPITAL} start | 10% annual inflow | "
          f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost")
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)\n")
    print(
        disp[
            [
                "scenario",
                "dd_stop_pct",
                "cagr",
                "ann_volatility",
                "sharpe",
                "start_$",
                "end_$",
                "max_drawdown",
                "risk_off_days",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {OUTPUT_DIR / 'sma20_3x_dd_stop_results.csv'}")
    return 0


def _row(label: str, lim: float | None, res, st: dict) -> dict:
    return {
        "scenario": label,
        "dd_stop_pct": lim if lim is not None else "none",
        "cagr": st["cagr"],
        "ann_volatility": st["volatility"],
        "sharpe": st["sharpe"],
        "start_$": float(INITIAL_CAPITAL),
        "end_$": float(res.equity.iloc[-1]),
        "max_drawdown": st["max_drawdown"],
        "risk_off_days": res.risk_off_days,
        "rebalances": res.rebalance_count,
    }


if __name__ == "__main__":
    sys.exit(main())
