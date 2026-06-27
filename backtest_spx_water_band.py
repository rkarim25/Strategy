"""Backtest + Monte Carlo for the S&P 500 "SMA200 ±3% Band 1x/cash" (Water).

The 1x/cash Water counterpart to the Octane band+RSI 2x strategy: 1x long when
close > SMA200 x 1.03, cash when close < SMA200 x 0.97, hold prior state within the
band; NO leverage and NO RSI exit filter. Writes spx_water_band_site_data.json
(+ etp_returns) for the S&P page's "S&P Water" tab. Reuses all signal/engine/MC
logic from backtest_spx_distance_scale.py.

Run from repo root:  python backtest_spx_water_band.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from core.etp_leverage import (
    SPX_ETP, build_etp_return_panel, export_etp_returns_json,
)

import backtest_spx_distance_scale as octane
from backtest_spx_distance_scale import (
    build_equity_curve, build_price_sma_data, build_signal_history, build_site_payload,
    buy_hold_row, compute_strategy_leverage, download_spx_panel, fmt3, money,
    monte_carlo, pct, run_strategy,
)

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "spx_water_band"
SITE_DATA_JSON = ROOT / "spx_water_band_site_data.json"
ETP_JSON = ROOT / "spx_water_band_etp_returns.json"

WATER_SPEC = {
    "strategy": "SMA175 ±3% Band 1x/cash",
    "sma_window": 175,  # shortened from 200: ~equal CAGR, lower DD, higher Sharpe/Calmar (scratch/spx_water_octane_improve.py)
    "band_pct": 0.03,
    "leverage": 1.0,
    "rsi_threshold": None,  # plain band, no RSI exit (Water = no metric sacrificed)
    "rsi_period": 14,
}


def _json_safe(o):
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (f != f or f in (float("inf"), float("-inf"))) else f
    if isinstance(o, np.integer):
        return int(o)
    return o


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading S&P 500 / T-bill / VIX (1950+)...", flush=True)
    prices = download_spx_panel()
    print(f"Loaded {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}", flush=True)

    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    export_etp_returns_json(etp_panel, SPX_ETP, ETP_JSON)

    # Comparison: B&H 1x/2x/3x benchmarks + the Water default (1x/cash band).
    comparison = [
        buy_hold_row(prices, 1.0, "Buy & Hold SPY 1x", etp_panel),
        buy_hold_row(prices, 2.0, "Buy & Hold SSO 2x", etp_panel),
        buy_hold_row(prices, 3.0, "Buy & Hold UPRO 3x", etp_panel),
    ]
    default_row = run_strategy(prices, WATER_SPEC)
    comparison.append(default_row)
    print(
        f"  {WATER_SPEC['strategy']}: CAGR={pct(default_row['cagr'])}, "
        f"MaxDD={pct(default_row['max_drawdown'])}, Sharpe={fmt3(default_row['sharpe'])}, "
        f"End={money(default_row['end_$'])}",
        flush=True,
    )

    csv_path = OUTPUT_DIR / "spx_water_band_comparison.csv"
    cols = ["strategy", "cagr", "ann_volatility", "sharpe", "sortino", "max_drawdown",
            "calmar", "end_$", "rebalances", "win_rate", "profit_factor", "beta", "alpha",
            "pct_days_cash", "pct_days_1x", "avg_leverage", "total_trades"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in comparison:
            w.writerow({k: r.get(k) for k in cols})

    print("Building signal history / price-SMA / equity curve...", flush=True)
    signal_history = build_signal_history(prices, WATER_SPEC)
    price_sma_data = build_price_sma_data(prices, WATER_SPEC)
    default_lev, _ = compute_strategy_leverage(prices, WATER_SPEC)
    equity_curve = build_equity_curve(prices, default_lev)

    print("Running Monte Carlo (200 paths x 10yr)...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices, etp_panel, WATER_SPEC)
    mc_paths.to_csv(OUTPUT_DIR / "spx_water_band_monte_carlo_paths.csv", index=False)

    payload = build_site_payload(
        prices, comparison, default_row, mc_summary, etp_panel,
        signal_history, price_sma_data, equity_curve, spec=WATER_SPEC,
    )
    payload["levered_pnl_model"] = (
        "1x unlevered S&P 500 exposure (SPY or VUSA.L/VUAG.L UCITS) toggled to cash by the "
        "SMA200 ±3% band; no leverage, no ETP decay."
    )
    payload = _json_safe(payload)

    site_json = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    SITE_DATA_JSON.write_text(site_json, encoding="utf-8")
    (OUTPUT_DIR / "spx_water_band_site_data.json").write_text(site_json, encoding="utf-8")

    print(f"\nWrote {SITE_DATA_JSON.name} + {ETP_JSON.name}", flush=True)
    print(f"Default Water: CAGR={pct(default_row['cagr'])} / MaxDD={pct(default_row['max_drawdown'])} / "
          f"Calmar={fmt3(default_row.get('calmar'))} / Sharpe={fmt3(default_row['sharpe'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
