"""SMA(20) @ 3x / cash: DD pause lengths with peak reset on re-entry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from sweep_sma_periods import leverage_daily_sma

OUTPUT_DIR = Path("output") / "sma20_dd_pause_reset_peak"

# Trading sessions ~N calendar months (~21 sessions/month), ~2 weeks, ~1 week
PAUSE_VARIANTS: list[tuple[int, str]] = [
    (63, "3 months (~63 sessions)"),
    (42, "2 months (~42 sessions)"),
    (21, "1 month (~21 sessions)"),
    (10, "2 weeks (~10 sessions)"),
    (5, "1 week (5 sessions)"),
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SMA20@3x DD cash-pause sweep (session peak resets on re-entry).",
    )
    p.add_argument(
        "--dd-pct",
        type=float,
        default=7.0,
        help="Drawdown vs session peak that starts a cash pause (percent). Default: 7.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    dd_pause_trigger = args.dd_pct / 100.0
    if not (0 < dd_pause_trigger < 1):
        print("error: --dd-pct must be between 0 and 100", file=sys.stderr)
        return 2
    dd_label = args.dd_pct
    # Integer label in filenames when whole number
    dd_tag = str(int(dd_label)) if float(dd_label).is_integer() else str(dd_label).replace(".", "p")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    lev_signal = leverage_daily_sma(prices, window=20, levered=3.0)

    base_engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    rows = []

    r_base = base_engine.run(prices, lev_signal, name="SMA20 @ 3x baseline")
    st_base = comprehensive_stats(r_base.equity, r_base.daily_returns)
    rows.append(_row("Baseline (no DD pause)", None, None, r_base, st_base))

    for n_sessions, label in PAUSE_VARIANTS:
        pause_engine = PortfolioEngine(
            max_drawdown_limit=None,
            hard_drawdown_floor=False,
            trading_cost_pct=TRADING_COST_FROM_MID_PCT,
            dd_pause_trigger=dd_pause_trigger,
            dd_pause_trading_days=n_sessions,
            dd_pause_reset_peak_on_reentry=True,
        )
        res = pause_engine.run(
            prices,
            lev_signal,
            name=f"SMA20 @ 3x pause {label}",
        )
        st = comprehensive_stats(res.equity, res.daily_returns)
        rows.append(
            _row(
                f"-{dd_label:g}% DD vs session peak -> cash {n_sessions}d -> reset peak | {label}",
                n_sessions,
                dd_label,
                res,
                st,
            )
        )

    df = pd.DataFrame(rows)
    csv_path = OUTPUT_DIR / f"sma20_3x_dd{dd_tag}pct_pause_reset_peak.csv"
    df.to_csv(csv_path, index=False)
    disp = df.copy()
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["start_$"] = disp["start_$"].map(lambda x: f"${x:,.2f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")

    print(
        f"SMA20 @ 3x / cash | DD pause trigger: {dd_label:g}% of session peak | "
        f"peak resets on pause exit | ${INITIAL_CAPITAL} start | "
        f"10% annual inflow | {TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(
        f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days)\n"
    )
    print(
        disp[            [
                "scenario",
                "dd_stop_pct",
                "pause_sessions",
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
    print(f"\nCSV: {csv_path}")
    return 0


def _row(
    label: str,
    pause_sessions: int | None,
    dd_stop_pct: float | None,
    res,
    st: dict,
) -> dict:
    return {
        "scenario": label,
        "dd_stop_pct": dd_stop_pct if dd_stop_pct is not None else "n/a",
        "pause_sessions": pause_sessions if pause_sessions is not None else "none",
        "cagr": st["cagr"],        "ann_volatility": st["volatility"],
        "sharpe": st["sharpe"],
        "start_$": float(INITIAL_CAPITAL),
        "end_$": float(res.equity.iloc[-1]),
        "max_drawdown": st["max_drawdown"],
        "risk_off_days": res.risk_off_days,
        "rebalances": res.rebalance_count,
    }


if __name__ == "__main__":
    sys.exit(main())
