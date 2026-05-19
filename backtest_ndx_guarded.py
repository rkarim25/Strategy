"""Backtest and Monte Carlo for Nasdaq 100 Guarded A5/B25/X40/Y15 (full 2x/3x leverage).

Mirrors test_guarded_balanced_candidate.py and the SPX GitHub Pages dashboard assumptions:
$100 start, $10/year inflow, 1% rebalance cost, same DEFAULT_GUARDED parameters.
Writes ndx_daily.csv and ndx_guarded_site_data.json for ndx_guarded.html.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW, sma_cash_leverage

ROOT = Path(__file__).resolve().parent
NDX_TICKER = "^NDX"
TBILL_TICKER = "^IRX"
YEARS = 30
OUTPUT_DIR = ROOT / "output" / "ndx_guarded"
NDX_DAILY_CSV = ROOT / "ndx_daily.csv"
SITE_DATA_JSON = ROOT / "ndx_guarded_site_data.json"

DEFAULT_SPEC = {
    "strategy": "Guarded A5/B25 SMA20 Lead",
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}

N_SIMS = 200
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260519


def download_ndx_panel(years: int = YEARS) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    raw = yf.download(
        [NDX_TICKER, TBILL_TICKER],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No data returned from yfinance.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": NDX_TICKER})

    panel = pd.DataFrame(
        {
            "spx_close": closes[NDX_TICKER].astype(float),
            "tbill_rate": closes[TBILL_TICKER].astype(float) / 100.0,
        }
    )
    panel = panel.sort_index().ffill().dropna(how="any")
    if len(panel) < 260:
        raise ValueError(f"Not enough NDX rows: {len(panel)}")
    return panel


def write_ndx_daily_csv(prices: pd.DataFrame) -> None:
    with NDX_DAILY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Close"])
        for dt, row in prices.iterrows():
            writer.writerow([dt.strftime("%Y-%m-%d"), f"{float(row['spx_close']):.9g}"])


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def run_strategy(prices: pd.DataFrame, spec: dict) -> dict:
    lev, counts = guarded_strategy_leverage(
        prices,
        trigger_a=float(spec["trigger_a"]),
        trigger_b=float(spec["trigger_b"]),
        lead_pct_below_sma20=float(spec["lead_pct_below_sma20"]),
        x_return=float(spec["x_return"]),
        y_return=float(spec["y_return"]),
    )
    result = make_engine().run(prices, lev, name=str(spec["strategy"]))
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": spec["strategy"],
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "pct_days_cash": counts["pct_days_cash"],
        "pct_days_1x": counts["pct_days_1x"],
        "pct_days_2x": counts["pct_days_2x"],
        "pct_days_3x": counts["pct_days_3x"],
        "tier2_entries": counts["tier2_entries"],
        "tier3_entries": counts["tier3_entries"],
        "lead_only_days": counts["lead_only_days"],
    }


def buy_hold_row(prices: pd.DataFrame, leverage: float, label: str) -> dict:
    lev = pd.Series(leverage, index=prices.index)
    result = make_engine().run(prices, lev, name=label)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "pct_days_cash": 0.0 if leverage > 0 else 100.0,
    }


def synthetic_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    ndx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        chunks: list[np.ndarray] = []
        while sum(len(x) for x in chunks) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            chunks.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(chunks)[:HORIZON_DAYS]
        returns = ndx_ret[idx]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {"spx_close": 1000.0 * np.cumprod(1.0 + returns), "tbill_rate": tbill[idx]},
                index=index,
            )
        )
    return paths


def monte_carlo(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    for sim, path in enumerate(synthetic_paths(prices)):
        if sim % 25 == 0:
            print(f"Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        row = run_strategy(path, DEFAULT_SPEC)
        row["simulation"] = sim
        rows.append(row)
    df = pd.DataFrame(rows)
    return df, {
        "strategy": DEFAULT_SPEC["strategy"],
        "median_cagr": float(df["cagr"].median()),
        "p10_cagr": float(df["cagr"].quantile(0.10)),
        "p90_cagr": float(df["cagr"].quantile(0.90)),
        "median_max_drawdown": float(df["max_drawdown"].median()),
        "p10_max_drawdown": float(df["max_drawdown"].quantile(0.10)),
        "p90_max_drawdown": float(df["max_drawdown"].quantile(0.90)),
        "median_sharpe": float(df["sharpe"].median()),
        "median_end_$": float(df["end_$"].median()),
        "prob_max_dd_worse_35pct": float((df["max_drawdown"] <= -0.35).mean()),
        "prob_max_dd_worse_40pct": float((df["max_drawdown"] <= -0.40).mean()),
        "prob_max_dd_worse_50pct": float((df["max_drawdown"] <= -0.50).mean()),
        "prob_end_below_start": float((df["end_$"] < INITIAL_CAPITAL).mean()),
    }


def pct(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x) * 100:.2f}%"


def money(x: float | None) -> str | None:
    if x is None:
        return None
    return f"${float(x):,.0f}"


def build_site_payload(prices: pd.DataFrame, comparison: list[dict], default_row: dict, mc: dict) -> dict:
    bh = next(r for r in comparison if r["strategy"] == "Buy & hold 1x")
    return {
        "ticker": NDX_TICKER,
        "asset_label": "Nasdaq 100",
        "guarded_params": DEFAULT_SPEC,
        "sample": {
            "start_date": prices.index[0].date().isoformat(),
            "end_date": prices.index[-1].date().isoformat(),
            "trading_days": len(prices),
        },
        "default_backtest": {
            **default_row,
            "cagr_pct": pct(default_row["cagr"]),
            "max_drawdown_pct": pct(default_row["max_drawdown"]),
            "ann_volatility_pct": pct(default_row["ann_volatility"]),
            "sharpe_fmt": f"{default_row['sharpe']:.3f}",
            "end_value_fmt": money(default_row["end_$"]),
            "calmar_fmt": f"{default_row.get('calmar', 0):.2f}" if default_row.get("calmar") else None,
        },
        "buy_and_hold_1x": {
            **bh,
            "cagr_pct": pct(bh["cagr"]),
            "max_drawdown_pct": pct(bh["max_drawdown"]),
        },
        "comparison_table": [
            {
                **row,
                "cagr_pct": pct(row["cagr"]),
                "ann_volatility_pct": pct(row.get("ann_volatility")),
                "max_drawdown_pct": pct(row["max_drawdown"]),
                "sharpe_fmt": f"{row['sharpe']:.3f}" if row.get("sharpe") is not None else None,
                "end_value_fmt": money(row.get("end_$")),
                "cash_pct": pct(row["pct_days_cash"] / 100.0) if row.get("pct_days_cash") is not None else None,
            }
            for row in comparison
        ],
        "monte_carlo": {
            "n_sims": N_SIMS,
            "horizon_years": HORIZON_DAYS / 252.0,
            "block_days": BLOCK_DAYS,
            "seed": SEED,
            **mc,
            "median_cagr_pct": pct(mc["median_cagr"]),
            "p10_cagr_pct": pct(mc["p10_cagr"]),
            "p90_cagr_pct": pct(mc["p90_cagr"]),
            "median_max_drawdown_pct": pct(mc["median_max_drawdown"]),
            "p10_max_drawdown_pct": pct(mc["p10_max_drawdown"]),
            "p90_max_drawdown_pct": pct(mc["p90_max_drawdown"]),
            "median_sharpe_fmt": f"{mc['median_sharpe']:.3f}",
            "median_end_value_fmt": money(mc["median_end_$"]),
            "prob_max_dd_worse_35pct_fmt": pct(mc["prob_max_dd_worse_35pct"]),
            "prob_max_dd_worse_40pct_fmt": pct(mc["prob_max_dd_worse_40pct"]),
            "prob_max_dd_worse_50pct_fmt": pct(mc["prob_max_dd_worse_50pct"]),
            "prob_end_below_start_fmt": pct(mc["prob_end_below_start"]),
        },
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading Nasdaq 100 and T-bill data...", flush=True)
    prices = download_ndx_panel()
    print(f"Loaded {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}", flush=True)

    write_ndx_daily_csv(prices)
    print(f"Wrote {NDX_DAILY_CSV.name}", flush=True)

    comparison = [
        buy_hold_row(prices, 1.0, "Buy & hold 1x"),
        buy_hold_row(prices, 2.0, "Buy & hold 2x"),
        buy_hold_row(prices, 3.0, "Buy & hold 3x"),
    ]
    lev_sma = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    sma_res = make_engine().run(prices, lev_sma, name="SMA20 1x/cash")
    sma_stats = comprehensive_stats(sma_res.equity, sma_res.daily_returns)
    comparison.append(
        {
            "strategy": "SMA20 1x/cash",
            "cagr": sma_stats["cagr"],
            "ann_volatility": sma_stats["volatility"],
            "sharpe": sma_stats["sharpe"],
            "max_drawdown": sma_stats["max_drawdown"],
            "end_$": float(sma_res.equity.iloc[-1]),
            "rebalances": sma_res.rebalance_count,
            "pct_days_cash": float((lev_sma <= 0).mean() * 100.0),
        }
    )
    lev_sma2 = sma_cash_leverage(prices, BASE_SMA_WINDOW, 2.0)
    sma2_res = make_engine().run(prices, lev_sma2, name="SMA20 2x/cash")
    sma2_stats = comprehensive_stats(sma2_res.equity, sma2_res.daily_returns)
    comparison.append(
        {
            "strategy": "SMA20 2x/cash",
            "cagr": sma2_stats["cagr"],
            "ann_volatility": sma2_stats["volatility"],
            "sharpe": sma2_stats["sharpe"],
            "max_drawdown": sma2_stats["max_drawdown"],
            "end_$": float(sma2_res.equity.iloc[-1]),
            "rebalances": sma2_res.rebalance_count,
            "pct_days_cash": float((lev_sma2 <= 0).mean() * 100.0),
        }
    )
    lev_sma3 = sma_cash_leverage(prices, BASE_SMA_WINDOW, 3.0)
    sma3_res = make_engine().run(prices, lev_sma3, name="SMA20 3x/cash")
    sma3_stats = comprehensive_stats(sma3_res.equity, sma3_res.daily_returns)
    comparison.append(
        {
            "strategy": "SMA20 3x/cash",
            "cagr": sma3_stats["cagr"],
            "ann_volatility": sma3_stats["volatility"],
            "sharpe": sma3_stats["sharpe"],
            "max_drawdown": sma3_stats["max_drawdown"],
            "end_$": float(sma3_res.equity.iloc[-1]),
            "rebalances": sma3_res.rebalance_count,
            "pct_days_cash": float((lev_sma3 <= 0).mean() * 100.0),
        }
    )
    default_row = run_strategy(prices, DEFAULT_SPEC)
    comparison.append(default_row)
    comparison.append(
        run_strategy(
            prices,
            {
                "strategy": "Original Guarded A10/B20 SMA20",
                "trigger_a": 0.10,
                "trigger_b": 0.20,
                "lead_pct_below_sma20": 0.0,
                "x_return": 0.25,
                "y_return": 1.0 / 3.0,
            },
        )
    )

    pd.DataFrame(comparison).to_csv(OUTPUT_DIR / "ndx_guarded_comparison.csv", index=False)
    pd.DataFrame([default_row]).to_csv(OUTPUT_DIR / "ndx_guarded_default_backtest.csv", index=False)

    print("\nRunning Monte Carlo...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices)
    mc_paths.to_csv(OUTPUT_DIR / "ndx_guarded_monte_carlo_paths.csv", index=False)

    payload = build_site_payload(prices, comparison, default_row, mc_summary)
    SITE_DATA_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "ndx_guarded_site_data.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    bh_row = comparison[0]
    print("\n=== Nasdaq 100 Guarded (full leverage) ===")
    print(f"CAGR: {pct(default_row['cagr'])}  Max DD: {pct(default_row['max_drawdown'])}  Sharpe: {default_row['sharpe']:.3f}")
    print(f"End value: {money(default_row['end_$'])}  vs buy-hold CAGR {pct(bh_row['cagr'])} / DD {pct(bh_row['max_drawdown'])}")
    print(f"\nMonte Carlo median CAGR: {pct(mc_summary['median_cagr'])}  median max DD: {pct(mc_summary['median_max_drawdown'])}")
    print(f"\nWrote {SITE_DATA_JSON.name} and {NDX_DAILY_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
