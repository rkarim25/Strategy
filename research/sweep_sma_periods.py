"""Sweep SMA lookback periods (daily & month-based) for Sharpe and drawdown."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import sys
from pathlib import Path

import pandas as pd

from core.data_manager import load_backtest_data
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from core.metrics import comprehensive_stats
from core.reporting import BENCHMARK_LABEL

OUTPUT_DIR = Path("output") / "sma_sweep"

DAILY_WINDOWS = [20, 50, 80, 100, 120, 150, 200, 250, 300]
MONTH_WINDOWS = [3, 6, 8, 10, 12, 15]
LEVERAGE_LEVELS = [1.0, 2.0, 3.0]


def leverage_daily_sma(prices: pd.DataFrame, window: int, levered: float) -> pd.Series:
    close = prices["spx_close"]
    sma = close.rolling(window, min_periods=window).mean()
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > sma] = levered
    return lev


def leverage_monthly_sma(prices: pd.DataFrame, months: int, levered: float) -> pd.Series:
    close = prices["spx_close"]
    sma = close.resample("ME").last().rolling(months, min_periods=months).mean()
    sma_d = sma.reindex(close.index, method="ffill")
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > sma_d] = levered
    return lev


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )

    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)
    bh_stats = comprehensive_stats(bh.equity, bh.daily_returns)

    rows = [
        {
            "strategy": BENCHMARK_LABEL,
            "sma_type": "none",
            "period": 0,
            "leverage": 1.0,
            **bh_stats,
            "pct_days_in_market": 100.0,
            "borrowing_costs": 0.0,
            "trading_costs": 0.0,
        }
    ]

    for window in DAILY_WINDOWS:
        for lev in LEVERAGE_LEVELS:
            name = f"SMA{window}d @ {lev:.0f}x/cash"
            series = leverage_daily_sma(prices, window, lev)
            res = engine.run(prices, series, name=name)
            stats = comprehensive_stats(
                res.equity, res.daily_returns, benchmark_equity=bh.equity
            )
            rows.append(
                {
                    "strategy": name,
                    "sma_type": "daily",
                    "period": window,
                    "leverage": lev,
                    **stats,
                    "pct_days_in_market": float((series > 0).mean() * 100),
                    "borrowing_costs": res.funding_costs_total,
                    "trading_costs": res.trading_costs_total,
                }
            )

    for months in MONTH_WINDOWS:
        for lev in LEVERAGE_LEVELS:
            name = f"SMA{months}m @ {lev:.0f}x/cash"
            series = leverage_monthly_sma(prices, months, lev)
            res = engine.run(prices, series, name=name)
            stats = comprehensive_stats(
                res.equity, res.daily_returns, benchmark_equity=bh.equity
            )
            rows.append(
                {
                    "strategy": name,
                    "sma_type": "monthly",
                    "period": months,
                    "leverage": lev,
                    **stats,
                    "pct_days_in_market": float((series > 0).mean() * 100),
                    "borrowing_costs": res.funding_costs_total,
                    "trading_costs": res.trading_costs_total,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "sma_period_sweep_all.csv", index=False)

    systematic = df[df["sma_type"] != "none"].copy()

    for lev in LEVERAGE_LEVELS:
        sub = systematic[systematic["leverage"] == lev].copy()
        best_sharpe = sub.nlargest(15, "sharpe")
        best_dd = sub.nlargest(15, "max_drawdown")
        best_calmar = sub.nlargest(15, "calmar")
        lev_tag = f"{lev:.0f}x"
        best_sharpe.to_csv(OUTPUT_DIR / f"top_sharpe_{lev_tag}.csv", index=False)
        best_dd.to_csv(OUTPUT_DIR / f"top_max_dd_{lev_tag}.csv", index=False)
        best_calmar.to_csv(OUTPUT_DIR / f"top_calmar_{lev_tag}.csv", index=False)

    print(
        f"\nSMA period sweep | ${INITIAL_CAPITAL} start | 10% inflow | "
        f"{TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance cost\n"
    )
    print(
        f"Benchmark {BENCHMARK_LABEL}: "
        f"CAGR {bh_stats['cagr']*100:.2f}% | "
        f"Sharpe {bh_stats['sharpe']:.2f} | "
        f"Max DD {bh_stats['max_drawdown']*100:.2f}%\n"
    )

    for lev in LEVERAGE_LEVELS:
        sub = systematic[systematic["leverage"] == lev]
        print("=" * 88)
        print(f"TOP 10 BY SHARPE @ {lev:.0f}x/cash (higher = better risk-adjusted)")
        print("=" * 88)
        top = sub.nlargest(10, "sharpe")[
            ["strategy", "cagr", "volatility", "sharpe", "sortino", "max_drawdown", "calmar", "final_value"]
        ]
        for c in ("cagr", "volatility", "max_drawdown"):
            top[c] = top[c].map(lambda x: f"{x*100:.2f}%")
        for c in ("sharpe", "sortino", "calmar"):
            top[c] = top[c].map(lambda x: f"{x:.2f}")
        top["final_value"] = sub.nlargest(10, "sharpe")["final_value"].map(lambda x: f"${x:,.0f}")
        print(top.to_string(index=False))

        print(f"\nTOP 10 BY MAX DRAWDOWN @ {lev:.0f}x/cash (closest to 0 = shallowest)")
        top_dd = sub.nlargest(10, "max_drawdown")[
            ["strategy", "cagr", "sharpe", "max_drawdown", "calmar", "pct_days_in_market"]
        ]
        for c in ("cagr", "max_drawdown", "pct_days_in_market"):
            top_dd[c] = top_dd[c].map(lambda x: f"{x*100:.2f}%")
        for c in ("sharpe", "calmar"):
            top_dd[c] = top_dd[c].map(lambda x: f"{x:.2f}")
        print(top_dd.to_string(index=False))
        print()

    overall = systematic.copy()
    overall["score_balanced"] = overall["sharpe"] + overall["max_drawdown"] * 2
    print("=" * 88)
    print("BEST BALANCED (Sharpe + 2× max_drawdown, max_dd is negative)")
    print("=" * 88)
    bal = overall.nlargest(12, "score_balanced")[
        ["strategy", "leverage", "cagr", "sharpe", "max_drawdown", "calmar", "final_value"]
    ]
    for c in ("cagr", "max_drawdown"):
        bal[c] = bal[c].map(lambda x: f"{x*100:.2f}%")
    for c in ("sharpe", "calmar"):
        bal[c] = bal[c].map(lambda x: f"{x:.2f}")
    bal["final_value"] = overall.nlargest(12, "score_balanced")["final_value"].map(lambda x: f"${x:,.0f}")
    print(bal.to_string(index=False))

    print(f"\nFull results: {OUTPUT_DIR / 'sma_period_sweep_all.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
