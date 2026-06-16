"""Compare SMA20/cash with wait-and-see confirmation periods."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats

OUTPUT_DIR = Path("output") / "sma20_wait_and_see"
OUTPUT_CSV = OUTPUT_DIR / "sma20_wait_and_see_results.csv"

SMA_WINDOW = 20
ANNUAL_INFLOW_USD = 10.0
LEVERAGE_LEVELS = [1.0, 2.0, 3.0]
CONFIRMATION_DAYS = [1, 2, 3, 4, 5]


def sma20_wait_leverage(
    prices: pd.DataFrame,
    confirmation_days: int,
    leverage: float,
) -> pd.Series:
    """
    Hold leverage only after close has stayed above SMA20 for N consecutive closes.

    confirmation_days=1 is the original no-wait rule: close > SMA20.
    """
    if confirmation_days < 1:
        raise ValueError("confirmation_days must be >= 1")

    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    above_sma20 = close > sma20
    confirmed = above_sma20.rolling(
        confirmation_days,
        min_periods=confirmation_days,
    ).sum() == confirmation_days

    lev = pd.Series(0.0, index=prices.index)
    lev.loc[confirmed.fillna(False)] = leverage
    return lev


def _row(
    label: str,
    leverage: float,
    confirmation_days: int,
    res,
    stats: dict[str, float],
) -> dict[str, float | int | str]:
    return {
        "strategy": label,
        "leverage": leverage,
        "confirmation_days": confirmation_days,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(res.equity.iloc[-1]),
        "rebalances": res.rebalance_count,
        "trading_costs_total": res.trading_costs_total,
        "funding_costs_total": res.funding_costs_total,
        "pct_days_in_market": float((res.leverage > 0).mean() * 100.0),
        "pct_days_cash": float((res.leverage <= 0).mean() * 100.0),
    }


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

    rows: list[dict[str, float | int | str]] = []
    for leverage in LEVERAGE_LEVELS:
        for days in CONFIRMATION_DAYS:
            lev = sma20_wait_leverage(prices, days, leverage=leverage)
            label = (
                f"SMA20 {leverage:.0f}x/cash (no wait)"
                if days == 1
                else f"SMA20 {leverage:.0f}x/cash ({days} closes above)"
            )
            res = engine.run(prices, lev, name=label)
            stats = comprehensive_stats(res.equity, res.daily_returns)
            rows.append(_row(label, leverage, days, res, stats))

    df = pd.DataFrame(rows)
    baseline = df[df["confirmation_days"] == 1].set_index("leverage")
    df["cagr_delta_pp_vs_no_wait"] = df.apply(
        lambda row: (row["cagr"] - baseline.loc[row["leverage"], "cagr"]) * 100.0,
        axis=1,
    )
    df["max_dd_delta_pp_vs_no_wait"] = df.apply(
        lambda row: (
            row["max_drawdown"] - baseline.loc[row["leverage"], "max_drawdown"]
        )
        * 100.0,
        axis=1,
    )
    df["sharpe_delta_vs_no_wait"] = df.apply(
        lambda row: row["sharpe"] - baseline.loc[row["leverage"], "sharpe"],
        axis=1,
    )
    df.to_csv(OUTPUT_CSV, index=False)

    disp = df.copy()
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        disp[c] = disp[c].map(lambda x: f"{x * 100:.2f}%")
    for c in ("cagr_delta_pp_vs_no_wait", "max_dd_delta_pp_vs_no_wait"):
        disp[c] = disp[c].map(lambda x: f"{x:+.2f} pp")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["sharpe_delta_vs_no_wait"] = disp["sharpe_delta_vs_no_wait"].map(lambda x: f"{x:+.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.0f}")
    disp["pct_days_in_market"] = disp["pct_days_in_market"].map(lambda x: f"{x:.2f}%")

    print(
        "SMA20 wait-and-see study | 1x/2x/3x cash variants | "
        f"${INITIAL_CAPITAL:.0f} start | ${ANNUAL_INFLOW_USD:.0f}/year fixed inflow | "
        f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)\n")
    print(
        disp[
            [
                "strategy",
                "cagr",
                "cagr_delta_pp_vs_no_wait",
                "sharpe",
                "sharpe_delta_vs_no_wait",
                "max_drawdown",
                "max_dd_delta_pp_vs_no_wait",
                "pct_days_in_market",
                "rebalances",
                "end_$",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
