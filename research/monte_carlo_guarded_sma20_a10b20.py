"""Monte Carlo simulation for Guarded A10/B20 SMA20 strategy."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, guarded_tiered_leverage

OUTPUT_DIR = Path("output") / "monte_carlo_guarded_sma20_a10b20"

N_SIMS = 500
HORIZON_DAYS = 2520  # ~10 trading years
BLOCK_DAYS = 21  # ~1 trading month, preserves short-term volatility clustering
SEED = 20260516


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
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)

    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        sampled_ret: list[np.ndarray] = []
        sampled_tbill: list[np.ndarray] = []
        while sum(len(x) for x in sampled_ret) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_ret.append(spx_ret[start : start + BLOCK_DAYS])
            sampled_tbill.append(tbill[start : start + BLOCK_DAYS])

        returns = np.concatenate(sampled_ret)[:HORIZON_DAYS]
        yields = np.concatenate(sampled_tbill)[:HORIZON_DAYS]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {
                    "spx_close": 1000.0 * np.cumprod(1.0 + returns),
                    "tbill_rate": yields,
                },
                index=index,
            )
        )
    return paths


def percentiles(series: pd.Series) -> dict[str, float]:
    qs = {
        "p05": 0.05,
        "p10": 0.10,
        "p25": 0.25,
        "median": 0.50,
        "p75": 0.75,
        "p90": 0.90,
        "p95": 0.95,
    }
    return {name: float(series.quantile(q)) for name, q in qs.items()}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    rows: list[dict] = []
    annual_rows: list[dict] = []

    for sim, path in enumerate(synthetic_market_paths(prices)):
        lev, counts = guarded_tiered_leverage(path, 0.10, 0.20, 20)
        res = make_engine().run(path, lev, name="Guarded A10/B20 SMA20")
        stats = comprehensive_stats(res.equity, res.daily_returns)
        dd = res.equity / res.equity.cummax() - 1.0
        row = {
            "simulation": sim,
            "cagr": stats["cagr"],
            "ann_volatility": stats["volatility"],
            "sharpe": stats["sharpe"],
            "max_drawdown": stats["max_drawdown"],
            "end_$": float(res.equity.iloc[-1]),
            "rebalances": res.rebalance_count,
            "pct_days_cash": counts["pct_days_cash"],
            "pct_days_1x": counts["pct_days_1x"],
            "pct_days_2x": counts["pct_days_2x"],
            "pct_days_3x": counts["pct_days_3x"],
            "tier2_entries": counts["tier2_entries"],
            "tier3_entries": counts["tier3_entries"],
            "worst_daily_return": float(res.daily_returns.min()),
        }
        rows.append(row)

        annual_equity = res.equity.resample("YE").last().reset_index(drop=True)
        annual_dd = dd.resample("YE").min().abs().reset_index(drop=True)
        for year_idx, (equity_value, dd_value) in enumerate(zip(annual_equity, annual_dd), start=1):
            annual_rows.append(
                {
                    "simulation": sim,
                    "year": year_idx,
                    "equity_$": float(equity_value),
                    "drawdown_magnitude": float(dd_value),
                }
            )

    paths_df = pd.DataFrame(rows)
    annual_df = pd.DataFrame(annual_rows)
    annual_summary = (
        annual_df.groupby("year")
        .agg(
            equity_p10=("equity_$", lambda x: float(x.quantile(0.10))),
            equity_median=("equity_$", "median"),
            equity_p90=("equity_$", lambda x: float(x.quantile(0.90))),
            dd_p10=("drawdown_magnitude", lambda x: float(x.quantile(0.10))),
            dd_median=("drawdown_magnitude", "median"),
            dd_p90=("drawdown_magnitude", lambda x: float(x.quantile(0.90))),
        )
        .reset_index()
    )

    summary = {
        "strategy": "Guarded A10/B20 SMA20",
        "source": "Yahoo Finance ^GSPC and ^IRX via project data loader",
        "market_history_start": prices.index[0].date().isoformat(),
        "market_history_end": prices.index[-1].date().isoformat(),
        "n_sims": N_SIMS,
        "horizon_trading_days": HORIZON_DAYS,
        "horizon_years": HORIZON_DAYS / 252.0,
        "block_days": BLOCK_DAYS,
        "seed": SEED,
        "cagr": percentiles(paths_df["cagr"]),
        "max_drawdown": percentiles(paths_df["max_drawdown"]),
        "end_$": percentiles(paths_df["end_$"]),
        "sharpe": percentiles(paths_df["sharpe"]),
        "probabilities": {
            "cagr_gt_0": float((paths_df["cagr"] > 0).mean()),
            "cagr_gt_20pct": float((paths_df["cagr"] > 0.20).mean()),
            "cagr_gt_30pct": float((paths_df["cagr"] > 0.30).mean()),
            "max_dd_worse_20pct": float((paths_df["max_drawdown"] <= -0.20).mean()),
            "max_dd_worse_30pct": float((paths_df["max_drawdown"] <= -0.30).mean()),
            "max_dd_worse_40pct": float((paths_df["max_drawdown"] <= -0.40).mean()),
            "max_dd_worse_50pct": float((paths_df["max_drawdown"] <= -0.50).mean()),
            "end_below_start": float((paths_df["end_$"] < INITIAL_CAPITAL).mean()),
        },
        "exposure": {
            "median_pct_days_cash": float(paths_df["pct_days_cash"].median()),
            "median_pct_days_1x": float(paths_df["pct_days_1x"].median()),
            "median_pct_days_2x": float(paths_df["pct_days_2x"].median()),
            "median_pct_days_3x": float(paths_df["pct_days_3x"].median()),
            "median_rebalances": float(paths_df["rebalances"].median()),
        },
    }

    paths_df.to_csv(OUTPUT_DIR / "monte_carlo_paths.csv", index=False)
    annual_summary.to_csv(OUTPUT_DIR / "annual_path_percentiles.csv", index=False)
    with (OUTPUT_DIR / "monte_carlo_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"Monte Carlo complete: {N_SIMS} paths, {HORIZON_DAYS} trading days, "
        f"{BLOCK_DAYS}-day blocks"
    )
    print(
        "Median CAGR "
        f"{summary['cagr']['median'] * 100:.2f}% | "
        f"Median max DD {summary['max_drawdown']['median'] * 100:.2f}% | "
        f"Median end ${summary['end_$']['median']:,.2f}"
    )
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
