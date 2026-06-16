"""
SMA(20) @ 3x / cash baseline + optional technical add-ons.

Goal: measure whether common filters improve max drawdown while keeping CAGR high.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from indicators import enrich_prices, sma
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL

OUTPUT_DIR = Path("output") / "sma20_3x_addons"

SMA_FAST = 20
LEVER_FULL = 3.0


def base_signal_3x(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"]
    s = sma(close, SMA_FAST)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s] = LEVER_FULL
    return lev


def run(engine: PortfolioEngine, prices: pd.DataFrame, lev: pd.Series, name: str):
    return engine.run(prices, lev, name=name)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    df = enrich_prices(prices)

    close = df["spx_close"]
    sma20 = sma(close, SMA_FAST)

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)
    rows = []

    variants: list[tuple[str, pd.Series]] = []

    # --- Baseline ---
    lev0 = base_signal_3x(prices)
    variants.append(("SMA20 @ 3x / cash (baseline)", lev0))

    # --- Single add-ons (AND with base: only 3x when all true) ---
    in20 = close > sma20

    variants.append(
        (
            "+ Close > SMA200",
            pd.Series(0.0, index=prices.index).where(~(in20 & (close > df["sma_200"])), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ RSI(14) > 50",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["rsi_14"] > 50)), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ RSI(14) > 55",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["rsi_14"] > 55)), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ MACD line > signal",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["macd"] > df["macd_signal"])), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ MACD hist > 0",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["macd_hist"] > 0)), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ Close > BB middle (20)",
            pd.Series(0.0, index=prices.index).where(~(in20 & (close > df["bb_mid"])), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ SPX DD > -8% from peak",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["spx_dd"] > -0.08)), LEVER_FULL),
        )
    )
    variants.append(
        (
            "+ SPX DD > -5% from peak",
            pd.Series(0.0, index=prices.index).where(~(in20 & (df["spx_dd"] > -0.05)), LEVER_FULL),
        )
    )

    # --- Tiered leverage (often improves DD vs pure 3x) ---
    lev_tier = pd.Series(0.0, index=prices.index)
    lev_tier.loc[in20 & (close > df["sma_200"])] = 3.0
    lev_tier.loc[in20 & ~(close > df["sma_200"])] = 2.0
    variants.append(("Tier: 3x if >SMA200 else 2x if >SMA20", lev_tier))

    lev_tier2 = pd.Series(0.0, index=prices.index)
    bull_macd = df["macd"] > df["macd_signal"]
    lev_tier2.loc[in20 & bull_macd] = 3.0
    lev_tier2.loc[in20 & ~bull_macd] = 2.0
    variants.append(("Tier: 3x if MACD bull else 2x if >SMA20", lev_tier2))

    # --- Two-factor combos ---
    variants.append(
        (
            "+ SMA200 AND RSI>50",
            pd.Series(0.0, index=prices.index).where(
                ~(in20 & (close > df["sma_200"]) & (df["rsi_14"] > 50)),
                LEVER_FULL,
            ),
        )
    )
    variants.append(
        (
            "+ SMA200 AND MACD bull",
            pd.Series(0.0, index=prices.index).where(
                ~(in20 & (close > df["sma_200"]) & (df["macd"] > df["macd_signal"])),
                LEVER_FULL,
            ),
        )
    )

    baseline_stats = None
    for name, lev_series in variants:
        res = run(engine, prices, lev_series, name=name)
        st = comprehensive_stats(res.equity, res.daily_returns, benchmark_equity=bh.equity)
        if name.startswith("SMA20 @ 3x"):
            baseline_stats = st
        rows.append(
            {
                "strategy": name,
                **st,
                "rebalances": res.rebalance_count,
                "pct_days_3x": (res.leverage >= 2.5).mean() * 100,
                "avg_leverage": float(res.leverage.mean()),
                "borrowing": res.funding_costs_total,
                "trading": res.trading_costs_total,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_DIR / "sma20_addon_results.csv", index=False)

    base_cagr = baseline_stats["cagr"]
    base_dd = baseline_stats["max_drawdown"]

    print(f"\n${INITIAL_CAPITAL} start | 10% inflow | {TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance\n")
    print(f"Baseline SMA20 @ 3x: CAGR {base_cagr*100:.2f}% | Max DD {base_dd*100:.2f}% | Sharpe {baseline_stats['sharpe']:.2f}\n")

    display = out[["strategy", "cagr", "volatility", "sharpe", "max_drawdown", "final_value", "rebalances"]].copy()
    for c in ("cagr", "volatility", "max_drawdown"):
        display[c] = display[c].map(lambda x: f"{x*100:.2f}%")
    display["sharpe"] = display["sharpe"].map(lambda x: f"{x:.2f}")
    display["final_value"] = display["final_value"].map(lambda x: f"${x:,.0f}")
    print(display.to_string(index=False))

    # Pareto-ish: better DD same or higher CAGR (within 0.25% CAGR tolerance)
    tol = 0.0025
    improved_dd = out[
        (out["max_drawdown"] > base_dd + 1e-9)
        & (out["cagr"] >= base_cagr - tol)
    ].sort_values("max_drawdown", ascending=False)

    print("\n--- Filters that shallow drawdown vs baseline WITHOUT losing >0.25% CAGR ---")
    if improved_dd.empty:
        print("None found (trade-off is unavoidable on this grid).")
        print("Closest: sort by Calmar or by DD improvement accepting small CAGR give-up.")
        alt = out[out["strategy"] != out.iloc[0]["strategy"]].copy()
        alt["dd_vs_base"] = alt["max_drawdown"] - base_dd
        alt["cagr_vs_base"] = alt["cagr"] - base_cagr
        alt = alt.sort_values(["dd_vs_base", "cagr_vs_base"], ascending=[False, False])
        print(
            alt[["strategy", "cagr", "max_drawdown", "dd_vs_base", "cagr_vs_base"]]
            .head(8)
            .assign(cagr=lambda x: x["cagr"].map(lambda v: f"{v*100:.2f}%"))
            .assign(max_drawdown=lambda x: x["max_drawdown"].map(lambda v: f"{v*100:.2f}%"))
            .assign(dd_vs_base=lambda x: x["dd_vs_base"].map(lambda v: f"{v*100:.2f}pp"))
            .assign(cagr_vs_base=lambda x: x["cagr_vs_base"].map(lambda v: f"{v*100:.2f}pp"))
            .to_string(index=False)
        )
    else:
        print(improved_dd[["strategy", "cagr", "max_drawdown", "sharpe"]].to_string(index=False))

    print(f"\nCSV: {OUTPUT_DIR / 'sma20_addon_results.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
