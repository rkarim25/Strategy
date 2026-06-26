"""Monte Carlo stress tests for momentum leverage strategy candidates."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_guarded_tiered_sma20_50_200 import guarded_tiered_leverage, sma_cash_leverage
from backtest_long_hold_momentum_strategies import (
    absolute_momentum_trailing_stop,
    adx_trend_strength,
    keltner_trend_channel,
    load_ohlc_data,
    long_hold_time_series_momentum,
    monthly_momentum_regime,
    sma_stack_hysteresis,
)
from backtest_momentum_leverage_strategies import (
    donchian_breakout_momentum,
    macd_momentum,
    rsi_momentum,
    sma_slope_momentum,
    sma_stack_momentum,
    vol_adjusted_momentum,
)
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "momentum_monte_carlo"

N_SIMS = 75
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260517


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def synthetic_market_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    high_ratio = (prices["spx_high"] / prices["spx_close"]).clip(lower=1.0).fillna(1.0).to_numpy(dtype=float)
    low_ratio = (prices["spx_low"] / prices["spx_close"]).clip(upper=1.0).fillna(1.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)

    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        sampled_idx: list[np.ndarray] = []
        while sum(len(x) for x in sampled_idx) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_idx.append(np.arange(start, start + BLOCK_DAYS))

        idx = np.concatenate(sampled_idx)[:HORIZON_DAYS]
        returns = spx_ret[idx]
        close = 1000.0 * np.cumprod(1.0 + returns)
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {
                    "spx_close": close,
                    "spx_high": close * high_ratio[idx],
                    "spx_low": close * low_ratio[idx],
                    "tbill_rate": tbill[idx],
                },
                index=index,
            )
        )
    return paths


def exposure_mix(lev: pd.Series) -> dict[str, float]:
    return {
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def strategy_specs(path: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    guarded_lev, _ = guarded_tiered_leverage(path, 20)
    return [
        ("SMA stack momentum", "Momentum trigger", sma_stack_momentum(path)),
        ("SMA slope momentum", "Momentum trigger", sma_slope_momentum(path)),
        ("MACD momentum", "Momentum trigger", macd_momentum(path)),
        ("RSI momentum", "Momentum trigger", rsi_momentum(path)),
        ("Donchian breakout momentum", "Momentum trigger", donchian_breakout_momentum(path)),
        ("Vol-adjusted SMA stack", "Momentum trigger", vol_adjusted_momentum(path)),
        ("Long-hold 3/6/12m momentum", "Long-hold momentum", long_hold_time_series_momentum(path)),
        ("SMA stack hysteresis", "Long-hold momentum", sma_stack_hysteresis(path)),
        ("Absolute momentum trailing stop", "Long-hold momentum", absolute_momentum_trailing_stop(path)),
        ("ADX trend strength", "Long-hold momentum", adx_trend_strength(path)),
        ("Keltner trend channel", "Long-hold momentum", keltner_trend_channel(path)),
        ("Monthly momentum regime", "Long-hold momentum", monthly_momentum_regime(path)),
        ("Guarded A10/B20 SMA20", "Reference", guarded_lev),
        ("SMA20 3x/cash", "Reference", sma_cash_leverage(path, 20, 3.0)),
        ("SMA20 2x/cash", "Reference", sma_cash_leverage(path, 20, 2.0)),
        ("Buy & hold 1x", "Reference", pd.Series(1.0, index=path.index)),
    ]


def percentile(series: pd.Series, q: float) -> float:
    return float(series.quantile(q))


def summarize(paths_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (group, strategy), g in paths_df.groupby(["group", "strategy"]):
        rows.append(
            {
                "strategy": strategy,
                "group": group,
                "median_cagr": float(g["cagr"].median()),
                "p10_cagr": percentile(g["cagr"], 0.10),
                "p90_cagr": percentile(g["cagr"], 0.90),
                "median_max_drawdown": float(g["max_drawdown"].median()),
                "p10_max_drawdown": percentile(g["max_drawdown"], 0.10),
                "p90_max_drawdown": percentile(g["max_drawdown"], 0.90),
                "median_sharpe": float(g["sharpe"].median()),
                "median_end_$": float(g["end_$"].median()),
                "prob_cagr_gt_0": float((g["cagr"] > 0.0).mean()),
                "prob_cagr_gt_20pct": float((g["cagr"] > 0.20).mean()),
                "prob_cagr_gt_30pct": float((g["cagr"] > 0.30).mean()),
                "prob_max_dd_worse_30pct": float((g["max_drawdown"] <= -0.30).mean()),
                "prob_max_dd_worse_40pct": float((g["max_drawdown"] <= -0.40).mean()),
                "prob_max_dd_worse_50pct": float((g["max_drawdown"] <= -0.50).mean()),
                "prob_end_below_start": float((g["end_$"] < INITIAL_CAPITAL).mean()),
                "median_rebalances": float(g["rebalances"].median()),
                "median_pct_days_cash": float(g["pct_days_cash"].median()),
                "median_pct_days_1x": float(g["pct_days_1x"].median()),
                "median_pct_days_2x": float(g["pct_days_2x"].median()),
                "median_pct_days_3x": float(g["pct_days_3x"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values(["group", "median_cagr"], ascending=[True, False])


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_ohlc_data(years=30)
    print(
        f"Loaded {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )
    engine = make_engine()
    rows: list[dict] = []

    for sim, path in enumerate(synthetic_market_paths(prices)):
        if sim % 25 == 0:
            print(f"Running simulation {sim + 1}/{N_SIMS}", flush=True)
        for strategy, group, lev in strategy_specs(path):
            result = engine.run(path, lev, name=strategy)
            stats = comprehensive_stats(result.equity, result.daily_returns)
            rows.append(
                {
                    "simulation": sim,
                    "strategy": strategy,
                    "group": group,
                    "cagr": stats["cagr"],
                    "ann_volatility": stats["volatility"],
                    "sharpe": stats["sharpe"],
                    "max_drawdown": stats["max_drawdown"],
                    "end_$": float(result.equity.iloc[-1]),
                    "rebalances": result.rebalance_count,
                    **exposure_mix(result.leverage),
                }
            )

    paths_df = pd.DataFrame(rows)
    summary_df = summarize(paths_df)
    paths_df.to_csv(OUTPUT_DIR / "momentum_monte_carlo_paths.csv", index=False)
    summary_df.to_csv(OUTPUT_DIR / "momentum_monte_carlo_summary.csv", index=False)
    with (OUTPUT_DIR / "momentum_monte_carlo_metadata.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "Yahoo Finance ^GSPC and ^IRX via project data loader",
                "market_history_start": prices.index[0].date().isoformat(),
                "market_history_end": prices.index[-1].date().isoformat(),
                "n_sims": N_SIMS,
                "horizon_trading_days": HORIZON_DAYS,
                "horizon_years": HORIZON_DAYS / 252.0,
                "block_days": BLOCK_DAYS,
                "seed": SEED,
            },
            f,
            indent=2,
        )

    print(f"Momentum Monte Carlo complete: {N_SIMS} paths x {summary_df.shape[0]} strategies")
    print(summary_df[["strategy", "group", "median_cagr", "median_max_drawdown", "prob_max_dd_worse_40pct"]].to_string(index=False))
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
