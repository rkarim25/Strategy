"""Backtest + Monte Carlo + site JSON for Guarded 1x asset pages (FTSE 250, EM, DAX, MSCI World)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from guarded_asset_registry import ASSETS, GuardedAssetSpec
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW, sma_cash_leverage

ROOT = Path(__file__).resolve().parent
TBILL_TICKER = "^IRX"
YEARS = 30
N_SIMS = 200
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260523

DEFAULT_SPEC = {
    "strategy": "Guarded A5/B25 SMA20 Lead (max 1x)",
    "trigger_a": DEFAULT_GUARDED["trigger_a"],
    "trigger_b": DEFAULT_GUARDED["trigger_b"],
    "lead_pct_below_sma20": DEFAULT_GUARDED["lead_pct_below_sma20"],
    "x_return": DEFAULT_GUARDED["x_return"],
    "y_return": DEFAULT_GUARDED["y_return"],
    "max_leverage": 1.0,
}


def paths_for(spec: GuardedAssetSpec) -> dict[str, Path]:
    return {
        "daily_csv": ROOT / f"{spec.slug}_daily.csv",
        "site_json": ROOT / f"{spec.slug}_guarded_site_data.json",
        "output_dir": ROOT / "output" / f"{spec.slug}_guarded",
    }


def download_panel(ticker: str, years: int = YEARS) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    raw = yf.download(
        [ticker, TBILL_TICKER],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"No data for {ticker}")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": ticker})

    col = ticker if ticker in closes.columns else ticker.replace(".L", "")
    if col not in closes.columns:
        raise ValueError(f"Missing column {ticker}")

    panel = pd.DataFrame(
        {
            "spx_close": closes[col].astype(float),
            "tbill_rate": closes[TBILL_TICKER].astype(float) / 100.0,
        }
    )
    panel = panel.sort_index().ffill().dropna(how="any")
    if len(panel) < 260:
        raise ValueError(f"Not enough rows for {ticker}: {len(panel)}")
    return panel


def write_daily_csv(prices: pd.DataFrame, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
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


def run_guarded_1x(prices: pd.DataFrame) -> dict:
    lev, counts = guarded_lead_leverage(prices, max_leverage=1.0)
    result = make_engine().run(prices, lev, name=DEFAULT_SPEC["strategy"])
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    return {
        "strategy": DEFAULT_SPEC["strategy"],
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
        "guard_blocked_days": counts["guard_blocked_days"],
        "pct_cash": cash["pct_sessions_tbills"],
    }


def buy_hold_row(prices: pd.DataFrame) -> dict:
    lev = pd.Series(1.0, index=prices.index)
    result = make_engine().run(prices, lev, name="Buy & hold 1x")
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": "Buy & hold 1x",
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "pct_days_cash": 0.0,
    }


def sma_row(prices: pd.DataFrame) -> dict:
    lev = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    result = make_engine().run(prices, lev, name="SMA20 1x/cash")
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": "SMA20 1x/cash",
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
    }


def synthetic_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        chunks: list[np.ndarray] = []
        while sum(len(x) for x in chunks) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            chunks.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(chunks)[:HORIZON_DAYS]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {"spx_close": 1000.0 * np.cumprod(1.0 + ret[idx]), "tbill_rate": tbill[idx]},
                index=index,
            )
        )
    return paths


def monte_carlo(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    for sim, path in enumerate(synthetic_paths(prices)):
        if sim % 25 == 0:
            print(f"  MC path {sim + 1}/{N_SIMS}", flush=True)
        row = run_guarded_1x(path)
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


def build_site_payload(
    spec: GuardedAssetSpec,
    prices: pd.DataFrame,
    comparison: list[dict],
    default_row: dict,
    mc: dict,
) -> dict:
    bh = next(r for r in comparison if r["strategy"] == "Buy & hold 1x")
    return {
        "ticker": spec.yahoo_ticker,
        "asset_label": spec.asset_label,
        "guarded_params": DEFAULT_SPEC,
        "leverage_note": "Site default caps recovery tiers at 1x (tier arms still fire; exposure stays at 1x max).",
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
            "max_leverage": 1.0,
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


def run_asset(spec: GuardedAssetSpec) -> None:
    p = paths_for(spec)
    p["output_dir"].mkdir(parents=True, exist_ok=True)
    print(f"\n=== {spec.title_short} ({spec.yahoo_ticker}) ===", flush=True)
    prices = download_panel(spec.yahoo_ticker)
    print(f"Loaded {len(prices)} sessions", flush=True)
    write_daily_csv(prices, p["daily_csv"])

    comparison = [buy_hold_row(prices), sma_row(prices), run_guarded_1x(prices)]
    default_row = comparison[2]
    pd.DataFrame(comparison).to_csv(p["output_dir"] / f"{spec.slug}_comparison.csv", index=False)

    print("Monte Carlo...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices)
    mc_paths.to_csv(p["output_dir"] / f"{spec.slug}_monte_carlo_paths.csv", index=False)

    payload = build_site_payload(spec, prices, comparison, default_row, mc_summary)
    text = json.dumps(payload, indent=2) + "\n"
    p["site_json"].write_text(text, encoding="utf-8")
    (p["output_dir"] / f"{spec.slug}_site_data.json").write_text(text, encoding="utf-8")

    print(
        f"Guarded 1x: CAGR {pct(default_row['cagr'])}  DD {pct(default_row['max_drawdown'])}  "
        f"vs B&H {pct(comparison[0]['cagr'])} / {pct(comparison[0]['max_drawdown'])}"
    )
    print(f"Wrote {p['daily_csv'].name}, {p['site_json'].name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", action="append", help="Run one slug only (repeatable)")
    args = parser.parse_args()
    specs = ASSETS
    if args.slug:
        specs = [s for s in ASSETS if s.slug in args.slug]
        if not specs:
            raise SystemExit(f"Unknown slug(s): {args.slug}")
    for spec in specs:
        run_asset(spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
