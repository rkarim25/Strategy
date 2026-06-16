"""Compare Guarded A10/B20 SMA20 with wait-and-see SMA confirmation periods."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "guarded_sma20_wait_and_see"
OUTPUT_CSV = OUTPUT_DIR / "guarded_sma20_wait_and_see_results.csv"

SMA_WINDOW = 20
TRIGGER_A = 0.10
TRIGGER_B = 0.20
TIER2_EXIT_RETURN = 0.25
TIER3_EXIT_RETURN = 1.0 / 3.0
CONFIRMATION_DAYS = [1, 2, 3, 4, 5]


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def guarded_wait_leverage(
    prices: pd.DataFrame,
    confirmation_days: int,
) -> tuple[pd.Series, dict[str, float | int]]:
    """Guarded A10/B20 SMA20, where the SMA guard requires N consecutive closes above SMA20."""
    if confirmation_days < 1:
        raise ValueError("confirmation_days must be >= 1")

    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    above_sma20 = close > sma20
    guard_ok = (
        above_sma20.rolling(confirmation_days, min_periods=confirmation_days).sum()
        == confirmation_days
    ).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    guard_blocked_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        guard = bool(guard_ok.loc[dt])
        base_lev = 1.0 if guard else 0.0

        if regime == "tier3":
            if px / entry_close - 1.0 >= TIER3_EXIT_RETURN:
                regime = "base"
            elif guard:
                lev.loc[dt] = 3.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -TRIGGER_B and guard:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= TIER2_EXIT_RETURN:
                regime = "base"
            elif guard:
                lev.loc[dt] = 2.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if dd <= -TRIGGER_B and guard:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -TRIGGER_A and guard:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            if dd <= -TRIGGER_A and not guard:
                guard_blocked_days += 1
            lev.loc[dt] = base_lev

    return lev, {
        "confirmation_days": confirmation_days,
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    engine = make_engine()
    rows: list[dict[str, float | int | str]] = []

    for confirmation_days in CONFIRMATION_DAYS:
        lev, counts = guarded_wait_leverage(prices, confirmation_days)
        label = (
            "Guarded A10/B20 SMA20 (no wait)"
            if confirmation_days == 1
            else f"Guarded A10/B20 SMA20 ({confirmation_days} closes above)"
        )
        result = engine.run(prices, lev, name=label)
        stats = comprehensive_stats(result.equity, result.daily_returns)
        rows.append(
            {
                "strategy": label,
                "confirmation_days": confirmation_days,
                "cagr": stats["cagr"],
                "ann_volatility": stats["volatility"],
                "sharpe": stats["sharpe"],
                "max_drawdown": stats["max_drawdown"],
                "end_$": float(result.equity.iloc[-1]),
                "rebalances": result.rebalance_count,
                "trading_costs_total": result.trading_costs_total,
                "funding_costs_total": result.funding_costs_total,
                **counts,
            }
        )

    df = pd.DataFrame(rows)
    baseline = df.loc[df["confirmation_days"] == 1].iloc[0]
    df["cagr_delta_pp_vs_no_wait"] = (df["cagr"] - baseline["cagr"]) * 100.0
    df["max_dd_delta_pp_vs_no_wait"] = (
        df["max_drawdown"] - baseline["max_drawdown"]
    ) * 100.0
    df["sharpe_delta_vs_no_wait"] = df["sharpe"] - baseline["sharpe"]
    df.to_csv(OUTPUT_CSV, index=False)

    disp = df.copy()
    for col in [
        "cagr",
        "ann_volatility",
        "max_drawdown",
        "pct_days_cash",
        "pct_days_1x",
        "pct_days_2x",
        "pct_days_3x",
    ]:
        disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%" if abs(x) < 1 else f"{x:.2f}%")
    for col in ["cagr_delta_pp_vs_no_wait", "max_dd_delta_pp_vs_no_wait"]:
        disp[col] = disp[col].map(lambda x: f"{x:+.2f} pp")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["sharpe_delta_vs_no_wait"] = disp["sharpe_delta_vs_no_wait"].map(lambda x: f"{x:+.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.0f}")

    print(
        "Guarded SMA20 wait-and-see study | "
        f"${INITIAL_CAPITAL:.0f} start | ${ANNUAL_INFLOW_USD:.0f}/year fixed inflow | "
        f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)\n")
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
                "end_$",
                "rebalances",
                "pct_days_cash",
                "pct_days_1x",
                "pct_days_2x",
                "pct_days_3x",
                "tier2_entries",
                "tier3_entries",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
