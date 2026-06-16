"""Test lead-indicator proxies for Guarded A10/B20 SMA20 recovery entries."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "guarded_sma20_lead_indicators"
OUTPUT_CSV = OUTPUT_DIR / "guarded_sma20_lead_indicator_results.csv"

SMA_WINDOW = 20
TRIGGER_A = 0.10
TRIGGER_B = 0.20
TIER2_EXIT_RETURN = 0.25
TIER3_EXIT_RETURN = 1.0 / 3.0


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def guarded_leverage_with_recovery_guard(
    prices: pd.DataFrame,
    recovery_guard: pd.Series,
) -> tuple[pd.Series, dict[str, float | int]]:
    """Guarded A10/B20 SMA20 where only recovery tiers use the supplied lead guard."""
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    base_guard = (close > sma20).fillna(False)
    recovery_guard = recovery_guard.reindex(prices.index).fillna(False).astype(bool)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev = 1.0 if base_ok else 0.0
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= TIER3_EXIT_RETURN:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 3.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -TRIGGER_B and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= TIER2_EXIT_RETURN:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 2.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if dd <= -TRIGGER_B and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -TRIGGER_A and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            if dd <= -TRIGGER_A and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = base_lev

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def indicator_variants(prices: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    sma3 = close.rolling(3, min_periods=3).mean()
    sma5 = close.rolling(5, min_periods=5).mean()
    sma10 = close.rolling(10, min_periods=10).mean()
    sma20_slope_5d = sma20 / sma20.shift(5) - 1.0
    near_1pct = close >= sma20 * 0.99
    near_half_pct = close >= sma20 * 0.995

    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0.0)).rolling(14, min_periods=14).mean()
    rsi = 100.0 - (100.0 / (1.0 + gain / loss.replace(0.0, np.nan)))

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd - signal
    hist_rising_3d = (hist > hist.shift(1)) & (hist.shift(1) > hist.shift(2))

    high5 = close.rolling(5, min_periods=5).max().shift(1)
    high10 = close.rolling(10, min_periods=10).max().shift(1)

    return [
        ("Baseline strict SMA20", "Original: recovery allowed only when close > SMA20.", close > sma20),
        ("Within 0.10% of SMA20", "Recovery allowed when close is at least 99.90% of SMA20.", close >= sma20 * 0.999),
        ("Within 0.20% of SMA20", "Recovery allowed when close is at least 99.80% of SMA20.", close >= sma20 * 0.998),
        ("Within 0.25% of SMA20", "Recovery allowed when close is at least 99.75% of SMA20.", close >= sma20 * 0.9975),
        ("Within 0.30% of SMA20", "Recovery allowed when close is at least 99.70% of SMA20.", close >= sma20 * 0.997),
        ("Within 0.40% of SMA20", "Recovery allowed when close is at least 99.60% of SMA20.", close >= sma20 * 0.996),
        ("Within 0.50% of SMA20", "Recovery allowed when close is at least 99.50% of SMA20.", near_half_pct),
        ("Within 0.60% of SMA20", "Recovery allowed when close is at least 99.40% of SMA20.", close >= sma20 * 0.994),
        ("Within 0.75% of SMA20", "Recovery allowed when close is at least 99.25% of SMA20.", close >= sma20 * 0.9925),
        ("Within 1.00% of SMA20", "Recovery allowed when close is at least 99.00% of SMA20.", near_1pct),
        ("Near SMA20 + slope up", "Within 0.50% of SMA20 and SMA20 has positive 5-day slope.", near_half_pct & (sma20_slope_5d > 0.0)),
        ("SMA3 above SMA20", "Recovery allowed when 3-day SMA is above SMA20.", sma3 > sma20),
        ("SMA5 above SMA20", "Recovery allowed when 5-day SMA is above SMA20.", sma5 > sma20),
        ("Close above SMA5 near SMA20", "Close above SMA5 while within 1% of SMA20.", (close > sma5) & near_1pct),
        ("Close above SMA10 near SMA20", "Close above SMA10 while within 1% of SMA20.", (close > sma10) & near_1pct),
        ("RSI14 > 45 near SMA20", "RSI14 above 45 while within 1% of SMA20.", (rsi > 45.0) & near_1pct),
        ("RSI14 > 50 near SMA20", "RSI14 above 50 while within 1% of SMA20.", (rsi > 50.0) & near_1pct),
        ("MACD hist rising near SMA20", "MACD histogram rising for 3 days while within 1% of SMA20.", hist_rising_3d & near_1pct),
        ("Close above prior 5d high near SMA20", "Close breaks prior 5-day high while within 1% of SMA20.", (close > high5) & near_1pct),
        ("Close above prior 10d high near SMA20", "Close breaks prior 10-day high while within 1% of SMA20.", (close > high10) & near_1pct),
    ]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    engine = make_engine()
    rows: list[dict[str, float | int | str]] = []

    for name, description, recovery_guard in indicator_variants(prices):
        lev, counts = guarded_leverage_with_recovery_guard(prices, recovery_guard)
        result = engine.run(prices, lev, name=name)
        stats = comprehensive_stats(result.equity, result.daily_returns)
        rows.append(
            {
                "variant": name,
                "description": description,
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
    baseline = df.loc[df["variant"] == "Baseline strict SMA20"].iloc[0]
    df["cagr_delta_pp"] = (df["cagr"] - baseline["cagr"]) * 100.0
    df["max_dd_delta_pp"] = (df["max_drawdown"] - baseline["max_drawdown"]) * 100.0
    df["sharpe_delta"] = df["sharpe"] - baseline["sharpe"]
    df["improves_cagr"] = df["cagr"] > baseline["cagr"]
    df["improves_drawdown"] = df["max_drawdown"] > baseline["max_drawdown"]
    df["improves_sharpe"] = df["sharpe"] > baseline["sharpe"]
    df = df.sort_values("cagr", ascending=False)
    df.to_csv(OUTPUT_CSV, index=False)

    disp = df.copy()
    for col in ["cagr", "ann_volatility", "max_drawdown"]:
        disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%")
    for col in ["cagr_delta_pp", "max_dd_delta_pp"]:
        disp[col] = disp[col].map(lambda x: f"{x:+.2f} pp")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["sharpe_delta"] = disp["sharpe_delta"].map(lambda x: f"{x:+.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.0f}")

    print(
        "Guarded SMA20 lead-indicator study | recovery-tier guard only | "
        f"${INITIAL_CAPITAL:.0f} start | ${ANNUAL_INFLOW_USD:.0f}/year fixed inflow | "
        f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)\n")
    print(
        disp[
            [
                "variant",
                "cagr",
                "cagr_delta_pp",
                "sharpe",
                "sharpe_delta",
                "max_drawdown",
                "max_dd_delta_pp",
                "end_$",
                "rebalances",
                "lead_only_days",
                "pct_days_2x",
                "pct_days_3x",
            ]
        ].to_string(index=False)
    )
    print(f"\nCSV: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
