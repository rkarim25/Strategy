"""SMA20 @ 3x: baseline vs 20% DD pause + 30 sessions; fixed $10/year inflow (no % inflow)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from sweep_sma_periods import leverage_daily_sma

OUTPUT_DIR = Path("output") / "sma20_dd_pause_fixed_inflow"
ANNUAL_INFLOW_USD = 10.0


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    lev = leverage_daily_sma(prices, window=20, levered=3.0)

    engines = [
        (
            "Baseline (no DD pause)",
            PortfolioEngine(
                max_drawdown_limit=None,
                hard_drawdown_floor=False,
                trading_cost_pct=TRADING_COST_FROM_MID_PCT,
                annual_inflow_pct=0.0,
                annual_inflow_abs=ANNUAL_INFLOW_USD,
            ),
        ),
        (
            "-20% vs session peak -> 30 sessions cash -> reset peak",
            PortfolioEngine(
                max_drawdown_limit=None,
                hard_drawdown_floor=False,
                trading_cost_pct=TRADING_COST_FROM_MID_PCT,
                annual_inflow_pct=0.0,
                annual_inflow_abs=ANNUAL_INFLOW_USD,
                dd_pause_trigger=0.20,
                dd_pause_trading_days=30,
                dd_pause_reset_peak_on_reentry=True,
            ),
        ),
    ]

    rows = []
    for label, eng in engines:
        res = eng.run(prices, lev, name=label)
        st = comprehensive_stats(res.equity, res.daily_returns)
        alloc = invested_vs_tbills_sessions(res.leverage)
        row = {
            "scenario": label,
            "cagr": st["cagr"],
            "ann_volatility": st["volatility"],
            "sharpe": st["sharpe"],
            "start_$": float(INITIAL_CAPITAL),
            "end_$": float(res.equity.iloc[-1]),
            "max_drawdown": st["max_drawdown"],
            "risk_off_days": res.risk_off_days,
            "rebalances": res.rebalance_count,
            "pct_sessions_invested": alloc["pct_sessions_invested"],
            "pct_sessions_tbills": alloc["pct_sessions_tbills"],
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    csv_path = OUTPUT_DIR / "sma20_dd20_pause30_fixed10yr_inflow.csv"
    df.to_csv(csv_path, index=False)

    disp = df.copy()
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["start_$"] = disp["start_$"].map(lambda x: f"${x:,.2f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")
    disp["pct_sessions_invested"] = disp["pct_sessions_invested"].map(lambda x: f"{x:.2f}%")
    disp["pct_sessions_tbills"] = disp["pct_sessions_tbills"].map(lambda x: f"{x:.2f}%")

    baseline_note = (
        "\n(Session mix from realized leverage: lev>0 = invested in SPX sleeve, "
        "lev<=0 = T-bill cash.)"
    )

    print(
        f"SMA20 @ 3x | ${INITIAL_CAPITAL} start | "
        f"${ANNUAL_INFLOW_USD:.0f} added first session each calendar year "
        f"(not % of AUM) | {TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(
        f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days)\n"
    )
    print(
        disp[
            [
                "scenario",
                "cagr",
                "ann_volatility",
                "sharpe",
                "start_$",
                "end_$",
                "max_drawdown",
                "pct_sessions_invested",
                "pct_sessions_tbills",
                "risk_off_days",
            ]
        ].to_string(index=False)
    )
    print(baseline_note)
    print(f"\nCSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
