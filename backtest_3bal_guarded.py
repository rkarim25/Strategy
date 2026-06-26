"""Backtest SMA20 1x/cash (default) and Guarded max 1x on WisdomTree 3BAL (3x EURO STOXX Banks).

3BAL.L — IE00BLS09N40, EURO STOXX Banks 3x Daily Leveraged (GBX on LSE).
Runs from inception (2014-12-08). Default site strategy is SMA20 1x/cash.

Writes:
  - 3bal_daily.csv + 3bal_guarded_site_data.json (repo root, for website)
  - output/3bal_guarded/ comparison, MC paths, summary
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from backtest_lqq3_guarded import (
    DEFAULT_SPEC,
    N_SIMS,
    BLOCK_DAYS,
    HORIZON_DAYS,
    SEED,
    download_panel,
    make_engine,
    money,
    pct,
    run_guarded_1x,
    run_strategy_row,
    sma_cash_leverage,
    sma_row,
    buy_hold_row,
)
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from core.guarded_site_series import build_equity_curve, build_price_sma_data, build_signal_history
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "3bal_guarded"
TICKER = "3BAL.L"
INCEPTION = "2014-12-08"
DAILY_CSV = ROOT / "3bal_daily.csv"
DAILY_CSV_OUTPUT = OUTPUT_DIR / "3bal_daily.csv"
SITE_DATA_JSON = ROOT / "3bal_guarded_site_data.json"

ASSET_LABEL = "3BAL.L (WisdomTree EURO STOXX Banks 3x Daily Leveraged, GBX)"
DEFAULT_STRATEGY_NAME = "SMA20 1x/cash"


def write_daily_csv(prices: pd.DataFrame) -> None:
    for path in (DAILY_CSV, DAILY_CSV_OUTPUT):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Close"])
            for dt, row in prices.iterrows():
                writer.writerow([dt.strftime("%Y-%m-%d"), f"{float(row['spx_close']):.9g}"])


def run_sma20_1x(prices: pd.DataFrame) -> dict:
    return sma_row(prices)


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


def monte_carlo_sma20(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    for sim, path in enumerate(synthetic_paths(prices)):
        if sim % 25 == 0:
            print(f"Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        row = run_sma20_1x(path)
        row["simulation"] = sim
        rows.append(row)
    df = pd.DataFrame(rows)
    return df, {
        "strategy": DEFAULT_STRATEGY_NAME,
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


def site_comparison(prices: pd.DataFrame) -> list[dict]:
    return [
        buy_hold_row(prices, label="Buy & hold (always in 3BAL)"),
        run_sma20_1x(prices),
        run_guarded_1x(prices),
    ]


def build_site_payload(
    prices: pd.DataFrame,
    comparison: list[dict],
    default_row: dict,
    mc: dict,
    price_sma_data: dict,
    signal_history: list[dict],
    equity_curve: dict,
) -> dict:
    bh = comparison[0]
    return {
        "ticker": TICKER,
        "asset_label": ASSET_LABEL,
        "isin": "IE00BLS09N40",
        "inception": INCEPTION,
        "default_strategy": DEFAULT_STRATEGY_NAME,
        "guarded_params": DEFAULT_SPEC,
        # Default site strategy is the strict SMA20 1x/cash cross (no lead-guard hysteresis), so
        # lead_pct_below_sma20=0 makes the shared renderer's manual-price recompute a strict cross.
        "strategy_params": {
            "strategy": DEFAULT_STRATEGY_NAME,
            "family": "guarded",
            "sma_window": BASE_SMA_WINDOW,
            "lead_pct_below_sma20": 0.0,
            "max_leverage": 1.0,
        },
        "leverage_note": (
            "Max 1x on this tab means the portfolio toggles between cash (T-bills) and "
            "fully invested in 3BAL (3x daily EURO STOXX Banks ETP). The default SMA20 rule "
            "is above SMA20 = 1x in 3BAL, below SMA20 = cash. Guarded A5/B25 recovery tiers "
            "still arm at -5% / -25% but exposure stays at 0 or 100% of the 3x product."
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
            "sortino_fmt": f"{default_row['sortino']:.3f}" if default_row.get("sortino") is not None else None,
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
        # Series consumed by the shared strategy_page.js renderer (price chart + markers + % equity).
        "price_sma_data": price_sma_data,
        "signal_history": signal_history,
        "equity_curve": equity_curve,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {TICKER} from {INCEPTION}...", flush=True)
    prices = download_panel(TICKER, start=INCEPTION)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days) | close {prices['spx_close'].iloc[0]:.2f} -> "
        f"{prices['spx_close'].iloc[-1]:.2f} (GBX)",
        flush=True,
    )

    write_daily_csv(prices)
    print(f"Wrote {DAILY_CSV.name}", flush=True)

    site_rows = site_comparison(prices)
    default_row = site_rows[1]

    lev_bh = pd.Series(1.0, index=prices.index)
    row_bh = run_strategy_row(
        "3BAL.L (3x EURO STOXX Banks ETP)",
        TICKER,
        prices,
        "Buy & hold (always in 3BAL)",
        lev_bh,
    )
    lev_sma = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    row_sma = run_strategy_row(
        "3BAL.L (3x EURO STOXX Banks ETP)",
        TICKER,
        prices,
        DEFAULT_STRATEGY_NAME,
        lev_sma,
        {"pct_days_cash": float((lev_sma <= 0).mean() * 100.0)},
    )
    lev_guard, counts = guarded_lead_leverage(prices, max_leverage=1.0)
    row_guard = run_strategy_row(
        "3BAL.L (3x EURO STOXX Banks ETP)",
        TICKER,
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
    comparison_rows = [row_bh, row_sma, row_guard]
    pd.DataFrame(comparison_rows).to_csv(OUTPUT_DIR / "comparison.csv", index=False)
    pd.DataFrame(site_rows).to_csv(OUTPUT_DIR / "site_comparison.csv", index=False)

    # Series for the shared renderer, built from the DEFAULT site strategy (SMA20 1x/cash → lev_sma).
    strat_result = make_engine().run(prices, lev_sma, name=DEFAULT_STRATEGY_NAME)
    bh_result = make_engine().run(prices, lev_bh, name="Buy & hold (always in 3BAL)")
    price_sma_data = build_price_sma_data(prices, BASE_SMA_WINDOW)
    signal_history = build_signal_history(prices, lev_sma, BASE_SMA_WINDOW)
    equity_curve = build_equity_curve(prices.index, strat_result.equity, bh_result.equity)

    print("\nRunning Monte Carlo on SMA20 1x/cash...", flush=True)
    mc_paths, mc_summary = monte_carlo_sma20(prices)
    mc_paths.to_csv(OUTPUT_DIR / "monte_carlo_paths.csv", index=False)

    payload = build_site_payload(
        prices, site_rows, default_row, mc_summary,
        price_sma_data, signal_history, equity_curve,
    )
    # allow_nan=False: fail loud rather than emit NaN/Infinity (invalid JSON silently blanks the page).
    text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    SITE_DATA_JSON.write_text(text, encoding="utf-8")
    (OUTPUT_DIR / "3bal_guarded_site_data.json").write_text(text, encoding="utf-8")

    summary = {
        "generated_at_utc": payload["generated_at_utc"],
        "asset": {
            "ticker": TICKER,
            "name": "WisdomTree EURO STOXX Banks 3x Daily Leveraged",
            "isin": "IE00BLS09N40",
            "currency": "GBX (LSE)",
            "inception": INCEPTION,
        },
        "default_strategy": DEFAULT_STRATEGY_NAME,
        "guarded_params": DEFAULT_SPEC,
        "leverage_note": payload["leverage_note"],
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "signal_and_pnl": "Rules on 3BAL price; max 1x = cash vs fully in 3x ETP",
        },
        "sample": payload["sample"],
        "strategies": comparison_rows,
        "site_strategies": site_rows,
        "monte_carlo": mc_summary,
        "default_vs_buy_hold": {
            "cagr_delta_pp": (default_row["cagr"] - row_bh["cagr"]) * 100,
            "sharpe_delta": default_row["sharpe"] - row_bh["sharpe"],
            "max_dd_delta_pp": (default_row["max_drawdown"] - row_bh["max_drawdown"]) * 100,
            "end_value_ratio": default_row["end_$"] / row_bh["end_$"],
        },
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"\n=== 3BAL.L — {DEFAULT_STRATEGY_NAME} (website default) ===")
    print(
        f"CAGR {pct(default_row['cagr'])}  Sharpe {default_row['sharpe']:.3f}  "
        f"MaxDD {pct(default_row['max_drawdown'])}  End {money(default_row['end_$'])}"
    )
    print(
        f"Monte Carlo median CAGR {pct(mc_summary['median_cagr'])}  "
        f"median max DD {pct(mc_summary['median_max_drawdown'])}"
    )

    print("\n=== 3BAL.L all strategies ===")
    for row in comparison_rows:
        print(
            f"  {row['strategy']:<42} "
            f"CAGR {row['cagr'] * 100:7.2f}%  "
            f"Sharpe {row['sharpe']:5.2f}  "
            f"MaxDD {row['max_drawdown'] * 100:7.2f}%  "
            f"End ${row['end_$']:,.0f}  "
            f"Cash {row.get('pct_cash', 0):5.1f}%"
        )

    print(f"\nWrote {SITE_DATA_JSON.name}, {DAILY_CSV.name}, {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
