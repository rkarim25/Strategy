"""Forward and Monte Carlo validation for the guarded tiered strategy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import (
    ANNUAL_INFLOW_USD,
    BASE_SMA_WINDOW,
    guarded_tiered_leverage,
    sma_cash_leverage,
)

OUTPUT_DIR = Path("output") / "guarded_tiered_forward_test"

STRATEGIES = [
    ("Buy & hold 1x", "buy_hold", 1.0),
    ("Buy & hold 2x", "buy_hold", 2.0),
    ("Buy & hold 3x", "buy_hold", 3.0),
    ("SMA20 1x/cash", "sma_cash", 1.0),
    ("SMA20 2x/cash", "sma_cash", 2.0),
    ("SMA20 3x/cash", "sma_cash", 3.0),
    ("Guarded A10/B20 SMA20", "guarded", 0.0),
]


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def build_leverage(prices: pd.DataFrame, kind: str, leverage: float) -> pd.Series:
    if kind == "buy_hold":
        return pd.Series(leverage, index=prices.index)
    if kind == "sma_cash":
        return sma_cash_leverage(prices, BASE_SMA_WINDOW, leverage)
    if kind == "guarded":
        lev, _ = guarded_tiered_leverage(prices, 0.10, 0.20, 20)
        return lev
    raise ValueError(f"Unknown strategy kind: {kind}")


def run_period(
    prices: pd.DataFrame,
    label: str,
    start: str | None,
    end: str | None,
) -> tuple[list[dict], dict[str, pd.Series]]:
    segment = prices.loc[start:end].copy()
    engine = make_engine()
    rows: list[dict] = []
    returns: dict[str, pd.Series] = {}

    for name, kind, lev_value in STRATEGIES:
        lev = build_leverage(segment, kind, lev_value)
        res = engine.run(segment, lev, name=name)
        stats = comprehensive_stats(res.equity, res.daily_returns)
        rows.append(
            {
                "period": label,
                "start_date": segment.index[0].date().isoformat(),
                "end_date": segment.index[-1].date().isoformat(),
                "trading_days": len(segment),
                "strategy": name,
                "cagr": stats["cagr"],
                "ann_volatility": stats["volatility"],
                "sharpe": stats["sharpe"],
                "max_drawdown": stats["max_drawdown"],
                "end_$": float(res.equity.iloc[-1]),
                "rebalances": res.rebalance_count,
                "risk_off_days": res.risk_off_days,
            }
        )
        returns[name] = res.daily_returns.copy()

    return rows, returns


def rolling_five_year_windows(prices: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    first_year = int(prices.index[0].year)
    last_year = int(prices.index[-1].year)
    for start_year in range(first_year, last_year - 4):
        start = f"{start_year}-01-01"
        end = f"{start_year + 4}-12-31"
        segment = prices.loc[start:end]
        if len(segment) < 252 * 4:
            continue
        period_rows, _ = run_period(prices, f"{start_year}-{start_year + 4}", start, end)
        rows.extend(period_rows)
    return pd.DataFrame(rows)


def monte_carlo_from_market_blocks(
    prices: pd.DataFrame,
    n_sims: int = 100,
    horizon_days: int = 2520,
    block_days: int = 21,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - block_days + 1)

    for sim in range(n_sims):
        sampled_ret: list[np.ndarray] = []
        sampled_tbill: list[np.ndarray] = []
        while sum(len(x) for x in sampled_ret) < horizon_days:
            start = int(rng.choice(block_starts))
            sampled_ret.append(spx_ret[start : start + block_days])
            sampled_tbill.append(tbill[start : start + block_days])

        r = np.concatenate(sampled_ret)[:horizon_days]
        y = np.concatenate(sampled_tbill)[:horizon_days]
        idx = pd.bdate_range("2000-01-03", periods=horizon_days)
        synthetic = pd.DataFrame(
            {
                "spx_close": 1000.0 * np.cumprod(1.0 + r),
                "tbill_rate": y,
            },
            index=idx,
        )

        for strategy, kind, lev_value in STRATEGIES:
            engine = make_engine()
            lev = build_leverage(synthetic, kind, lev_value)
            res = engine.run(synthetic, lev, name=strategy)
            stats = comprehensive_stats(res.equity, res.daily_returns)
            rows.append(
                {
                    "strategy": strategy,
                    "simulation": sim,
                    "horizon_years": horizon_days / 252.0,
                    "end_$": float(res.equity.iloc[-1]),
                    "cagr": stats["cagr"],
                    "max_drawdown": stats["max_drawdown"],
                }
            )

    return pd.DataFrame(rows)


def summarize_rolling(rolling: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, g in rolling.groupby("strategy"):
        rows.append(
            {
                "strategy": strategy,
                "windows": int(len(g)),
                "median_cagr": float(g["cagr"].median()),
                "worst_cagr": float(g["cagr"].min()),
                "median_max_drawdown": float(g["max_drawdown"].median()),
                "worst_max_drawdown": float(g["max_drawdown"].min()),
                "median_sharpe": float(g["sharpe"].median()),
                "pct_windows_cagr_gt_0": float((g["cagr"] > 0).mean() * 100.0),
                "pct_windows_dd_worse_50": float((g["max_drawdown"] <= -0.50).mean() * 100.0),
            }
        )
    return pd.DataFrame(rows)


def summarize_monte_carlo(mc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, g in mc.groupby("strategy"):
        rows.append(
            {
                "strategy": strategy,
                "median_cagr": float(g["cagr"].median()),
                "p10_cagr": float(g["cagr"].quantile(0.10)),
                "p90_cagr": float(g["cagr"].quantile(0.90)),
                "median_max_drawdown": float(g["max_drawdown"].median()),
                "p10_max_drawdown": float(g["max_drawdown"].quantile(0.10)),
                "p90_max_drawdown": float(g["max_drawdown"].quantile(0.90)),
                "median_end_$": float(g["end_$"].median()),
                "pct_sims_cagr_gt_0": float((g["cagr"] > 0).mean() * 100.0),
                "pct_sims_dd_worse_50": float((g["max_drawdown"] <= -0.50).mean() * 100.0),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()

    periods = [
        ("Full sample", None, None),
        ("Forward OOS 2006-2026", "2006-01-01", None),
        ("OOS decade 2006-2015", "2006-01-01", "2015-12-31"),
        ("OOS decade 2016-2026", "2016-01-01", None),
    ]

    rows: list[dict] = []
    for label, start, end in periods:
        period_rows, _ = run_period(prices, label, start, end)
        rows.extend(period_rows)

    period_df = pd.DataFrame(rows)
    rolling_df = rolling_five_year_windows(prices)
    rolling_summary = summarize_rolling(rolling_df)
    mc_df = monte_carlo_from_market_blocks(prices)
    mc_summary = summarize_monte_carlo(mc_df)

    period_df.to_csv(OUTPUT_DIR / "period_results.csv", index=False)
    rolling_df.to_csv(OUTPUT_DIR / "rolling_5y_results.csv", index=False)
    rolling_summary.to_csv(OUTPUT_DIR / "rolling_5y_summary.csv", index=False)
    mc_summary.to_csv(OUTPUT_DIR / "monte_carlo_10y_summary.csv", index=False)

    # The full simulation grid is large enough to be annoying in git diffs; keep it compressed.
    mc_df.to_pickle(OUTPUT_DIR / "monte_carlo_10y_paths.pkl")

    summary = {
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": int(len(prices)),
        "fixed_strategy": "Guarded A10/B20 SMA20",
        "annual_inflow_usd": ANNUAL_INFLOW_USD,
        "period_results": period_df.to_dict("records"),
        "rolling_5y_summary": rolling_summary.to_dict("records"),
        "monte_carlo_10y_summary": mc_summary.to_dict("records"),
    }
    with (OUTPUT_DIR / "forward_test_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"Forward validation complete: {summary['start_date']} -> {summary['end_date']} "
        f"({summary['trading_days']} trading days)"
    )
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
