"""
Three requested variants (addon list numbering):
  1 — SMA(20) @ 3x / cash + portfolio DD stop at 15%
  4 — Same as (1) + RSI(14) > 55 when taking 3x
  5 — SMA(20) @ 3x + MACD line > signal, only when SPX drawdown from peak is < 15%
      (i.e. spx_dd > -15%).
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

OUTPUT_DIR = Path("output") / "sma20_dd_user"
DD_STOP = 0.15
INDEX_DD_THRESH = -0.15
SMA_FAST = 20
LEV = 3.0


def lev_sma20_3x(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"]
    s20 = sma(close, SMA_FAST)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s20] = LEV
    return lev


def lev_sma20_rsi55_3x(df: pd.DataFrame) -> pd.Series:
    close = df["spx_close"]
    s20 = sma(close, SMA_FAST)
    lev = pd.Series(0.0, index=df.index)
    m = (close > s20) & (df["rsi_14"] > 55)
    lev.loc[m] = LEV
    return lev


def lev_sma20_macd_dd15(df: pd.DataFrame) -> pd.Series:
    """3x only when above SMA20, MACD bull, and index DD shallower than 15%."""
    close = df["spx_close"]
    s20 = sma(close, SMA_FAST)
    lev = pd.Series(0.0, index=df.index)
    m = (close > s20) & (df["macd"] > df["macd_signal"]) & (df["spx_dd"] > INDEX_DD_THRESH)
    lev.loc[m] = LEV
    return lev


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    enriched = enrich_prices(prices)

    engine_plain = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    engine_dd15 = PortfolioEngine(
        max_drawdown_limit=DD_STOP,
        hard_drawdown_floor=True,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    bh = engine_plain.run(prices, 1.0, name=BENCHMARK_LABEL)

    strategies = [
        (
            "(Ref) SMA20 @ 3x no DD stop",
            engine_plain,
            lev_sma20_3x(prices),
        ),
        (
            "(1) SMA20 @ 3x + portfolio DD stop 15%",
            engine_dd15,
            lev_sma20_3x(prices),
        ),
        (
            "(4) SMA20 @ 3x + RSI>55 + portfolio DD stop 15%",
            engine_dd15,
            lev_sma20_rsi55_3x(enriched),
        ),
        (
            "(5) SMA20 @ 3x + MACD bull + index DD < 15%",
            engine_plain,
            lev_sma20_macd_dd15(enriched),
        ),
    ]

    rows = []
    for name, eng, lev_s in strategies:
        res = eng.run(prices, lev_s, name=name)
        st = comprehensive_stats(res.equity, res.daily_returns, benchmark_equity=bh.equity)
        peak = res.equity.cummax()
        max_dd = float(((res.equity - peak) / peak).min())
        rows.append(
            {
                "strategy": name,
                **st,
                "max_dd_check": max_dd,
                "risk_off_days": res.risk_off_days,
                "rebalances": res.rebalance_count,
                "pct_days_3x": (res.leverage >= 2.5).mean() * 100,
                "pct_days_cash": (res.leverage <= 0).mean() * 100,
                "final_value": res.equity.iloc[-1],
                "borrowing": res.funding_costs_total,
                "trading": res.trading_costs_total,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_DIR / "three_dd_strategies.csv", index=False)

    print(f"${INITIAL_CAPITAL} start | 10% annual inflow | {TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance")
    print(f"Portfolio DD stop (strategies 1 & 4): {DD_STOP*100:.0f}% (engine overlay)\n")

    disp = out[
        ["strategy", "cagr", "volatility", "sharpe", "max_drawdown", "final_value",
         "risk_off_days", "rebalances", "pct_days_3x", "pct_days_cash"]
    ].copy()
    disp["cagr"] = disp["cagr"].map(lambda x: f"{x*100:.2f}%")
    disp["volatility"] = disp["volatility"].map(lambda x: f"{x*100:.2f}%")
    disp["max_drawdown"] = disp["max_drawdown"].map(lambda x: f"{x*100:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.2f}")
    disp["final_value"] = disp["final_value"].map(lambda x: f"${x:,.0f}")
    print(disp.to_string(index=False))
    print(f"\nSaved: {OUTPUT_DIR / 'three_dd_strategies.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
