"""Backtest Guarded A5/B25 (max 1x) on WisdomTree 3x Nasdaq ETP LQQ3.L (GBX).

3QQQ (Xetra) is not on Yahoo; LQQ3.L is the same product (IE00BLRPRL42).
Runs comprehensive backtest + Monte Carlo on real LQQ3 since listing (2012-12-13).
Also runs the same rules on ^NDX for longer-history context.

Writes:
  - lqq3_daily.csv + lqq3_guarded_site_data.json (repo root, for website)
  - output/lqq3_guarded/ comparison, MC paths, summary
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from price_cleaning import clean_close_series
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW, sma_cash_leverage

ROOT = Path(__file__).resolve().parent
LQQ3_TICKER = "LQQ3.L"
NDX_TICKER = "^NDX"
TBILL_TICKER = "^IRX"
LQQ3_START = "2012-12-13"
OUTPUT_DIR = ROOT / "output" / "lqq3_guarded"
LQQ3_DAILY_CSV = ROOT / "lqq3_daily.csv"
LQQ3_DAILY_CSV_OUTPUT = OUTPUT_DIR / "lqq3_daily.csv"
SITE_DATA_JSON = ROOT / "lqq3_guarded_site_data.json"

N_SIMS = 200
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260604

DEFAULT_SPEC = {
    "strategy": "Guarded A5/B25 SMA20 Lead (max 1x)",
    "trigger_a": DEFAULT_GUARDED["trigger_a"],
    "trigger_b": DEFAULT_GUARDED["trigger_b"],
    "lead_pct_below_sma20": DEFAULT_GUARDED["lead_pct_below_sma20"],
    "x_return": DEFAULT_GUARDED["x_return"],
    "y_return": DEFAULT_GUARDED["y_return"],
    "max_leverage": 1.0,
}


def make_engine(trading_cost_pct: float = TRADING_COST_FROM_MID_PCT) -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=trading_cost_pct,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def download_panel(asset_ticker: str, start: str | None = None) -> pd.DataFrame:
    end = datetime.today()
    start_s = start or "1990-01-01"
    raw = yf.download(
        [asset_ticker, TBILL_TICKER],
        start=start_s,
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"No data returned for {asset_ticker}.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": asset_ticker})

    panel = pd.DataFrame(
        {
            "spx_close": closes[asset_ticker].astype(float),
            "tbill_rate": closes[TBILL_TICKER].astype(float) / 100.0,
        }
    )
    panel = panel.sort_index().ffill().dropna(how="any")
    panel["spx_close"] = clean_close_series(panel["spx_close"])
    if len(panel) < 260:
        raise ValueError(f"Not enough rows for {asset_ticker}: {len(panel)}")
    return panel


def write_lqq3_daily_csv(prices: pd.DataFrame) -> None:
    for path in (LQQ3_DAILY_CSV, LQQ3_DAILY_CSV_OUTPUT):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Close"])
            for dt, row in prices.iterrows():
                writer.writerow([dt.strftime("%Y-%m-%d"), f"{float(row['spx_close']):.9g}"])


def run_guarded_1x(prices: pd.DataFrame, *, trading_cost_pct: float = TRADING_COST_FROM_MID_PCT) -> dict:
    lev, counts = guarded_lead_leverage(prices, max_leverage=1.0)
    result = make_engine(trading_cost_pct).run(prices, lev, name=DEFAULT_SPEC["strategy"])
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


def buy_hold_row(prices: pd.DataFrame, label: str = "Buy & hold (always in 3x ETP)") -> dict:
    lev = pd.Series(1.0, index=prices.index)
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


def run_strategy_row(
    asset: str,
    ticker: str,
    prices: pd.DataFrame,
    strategy: str,
    lev: pd.Series,
    extra: dict | None = None,
) -> dict:
    result = make_engine().run(prices, lev, name=strategy)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    row = {
        "asset": asset,
        "ticker": ticker,
        "strategy": strategy,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        "pct_invested": cash["pct_sessions_invested"],
    }
    if extra:
        row.update(extra)
    return row


def strategies_for_panel(asset: str, ticker: str, prices: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []

    lev_bh = pd.Series(1.0, index=prices.index)
    rows.append(
        run_strategy_row(asset, ticker, prices, "Buy & hold (always in ETP/index)", lev_bh)
    )

    lev_sma = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    rows.append(run_strategy_row(asset, ticker, prices, "SMA20 1x/cash", lev_sma))

    lev_guard, counts = guarded_lead_leverage(prices, max_leverage=1.0)
    rows.append(
        run_strategy_row(
            asset,
            ticker,
            prices,
            DEFAULT_SPEC["strategy"],
            lev_guard,
            {
                "pct_days_cash": counts["pct_days_cash"],
                "pct_days_1x": counts["pct_days_1x"],
                "tier2_entries": counts["tier2_entries"],
                "tier3_entries": counts["tier3_entries"],
                "lead_only_days": counts["lead_only_days"],
                "guard_blocked_days": counts["guard_blocked_days"],
            },
        )
    )
    return rows


def lqq3_site_comparison(prices: pd.DataFrame) -> list[dict]:
    return [
        buy_hold_row(prices),
        sma_row(prices),
        run_guarded_1x(prices),
    ]


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
        returns = ret[idx]
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
    prices: pd.DataFrame, comparison: list[dict], default_row: dict, mc: dict
) -> dict:
    bh = comparison[0]
    return {
        "ticker": LQQ3_TICKER,
        "asset_label": "LQQ3.L (WisdomTree 3x Daily Leveraged Nasdaq 100, GBX)",
        "proxy_note": (
            "3QQQ (Xetra) unavailable on Yahoo; LQQ3.L used — ISIN IE00BLRPRL42 "
            "(same product as 3QQQ). Prices in GBX."
        ),
        "guarded_params": DEFAULT_SPEC,
        "leverage_note": (
            "Max 1x on this tab means the portfolio toggles between cash (T-bills) and "
            "fully invested in LQQ3 (3x daily Nasdaq ETP). Recovery tiers still arm at "
            "-5% / -25% but exposure stays at 0 or 100% of the 3x product — not economic 1x Nasdaq beta."
        ),
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
                "cash_pct": pct(row["pct_days_cash"] / 100.0)
                if row.get("pct_days_cash") is not None
                else None,
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


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {LQQ3_TICKER} (from {LQQ3_START}) and T-bill...", flush=True)
    lqq3 = download_panel(LQQ3_TICKER, start=LQQ3_START)
    print(
        f"LQQ3: {len(lqq3)} sessions {lqq3.index[0].date()} -> {lqq3.index[-1].date()}",
        flush=True,
    )

    print(f"Downloading {NDX_TICKER} for comparison...", flush=True)
    ndx = download_panel(NDX_TICKER)
    print(f"NDX: {len(ndx)} sessions {ndx.index[0].date()} -> {ndx.index[-1].date()}", flush=True)

    write_lqq3_daily_csv(lqq3)
    print(f"Wrote {LQQ3_DAILY_CSV.name}", flush=True)

    site_comparison = lqq3_site_comparison(lqq3)
    default_row = site_comparison[2]

    comparison = strategies_for_panel("LQQ3.L (3x Nasdaq ETP)", LQQ3_TICKER, lqq3)
    comparison.extend(strategies_for_panel("Nasdaq 100 index", NDX_TICKER, ndx))

    pd.DataFrame(comparison).to_csv(OUTPUT_DIR / "lqq3_guarded_comparison.csv", index=False)
    pd.DataFrame(site_comparison).to_csv(OUTPUT_DIR / "lqq3_site_comparison.csv", index=False)

    print("\nRunning Monte Carlo on LQQ3 (max 1x)...", flush=True)
    mc_paths, mc_summary = monte_carlo(lqq3)
    mc_paths.to_csv(OUTPUT_DIR / "lqq3_monte_carlo_paths.csv", index=False)

    payload = build_site_payload(lqq3, site_comparison, default_row, mc_summary)
    SITE_DATA_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "lqq3_guarded_site_data.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )

    lqq3_rows = [r for r in comparison if r["asset"].startswith("LQQ3")]
    ndx_rows = [r for r in comparison if r["asset"].startswith("Nasdaq")]

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "proxy_note": payload["proxy_note"],
        "leverage_note": payload["leverage_note"],
        "guarded_params": DEFAULT_SPEC,
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
        },
        "lqq3": {
            "ticker": LQQ3_TICKER,
            "start_date": lqq3.index[0].date().isoformat(),
            "end_date": lqq3.index[-1].date().isoformat(),
            "trading_days": len(lqq3),
            "strategies": lqq3_rows,
            "site_strategies": site_comparison,
        },
        "ndx_reference": {
            "ticker": NDX_TICKER,
            "start_date": ndx.index[0].date().isoformat(),
            "end_date": ndx.index[-1].date().isoformat(),
            "trading_days": len(ndx),
            "strategies": ndx_rows,
        },
        "monte_carlo": mc_summary,
        "comparison_formatted": [
            {
                **row,
                "cagr_pct": pct(row["cagr"]),
                "max_drawdown_pct": pct(row["max_drawdown"]),
                "ann_volatility_pct": pct(row.get("ann_volatility")),
            }
            for row in comparison
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print("\n=== LQQ3.L Guarded (max 1x) — website default ===")
    print(
        f"CAGR {pct(default_row['cagr'])}  Sharpe {default_row['sharpe']:.3f}  "
        f"MaxDD {pct(default_row['max_drawdown'])}  End {money(default_row['end_$'])}"
    )
    print(
        f"Monte Carlo median CAGR {pct(mc_summary['median_cagr'])}  "
        f"median max DD {pct(mc_summary['median_max_drawdown'])}"
    )

    print("\n=== LQQ3.L all strategies ===")
    for row in lqq3_rows:
        print(
            f"  {row['strategy']:<45} "
            f"CAGR {row['cagr'] * 100:7.2f}%  "
            f"Sharpe {row['sharpe']:5.2f}  "
            f"MaxDD {row['max_drawdown'] * 100:7.2f}%  "
            f"End ${row['end_$']:,.0f}  "
            f"Cash {row['pct_cash']:5.1f}%"
        )

    print(f"\nWrote {SITE_DATA_JSON.name}, {LQQ3_DAILY_CSV.name}, {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
