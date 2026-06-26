"""Dedicated LQQ3 backtest: signal computed ON LQQ3 vs ON the underlying Nasdaq.

For a set of signal strategies, run each two ways -- the signal computed from the
held instrument's own price (LQQ3 / synthetic-3x) vs the signal computed from the
underlying Nasdaq 100 index (^NDX) and applied to holding the 3x product -- across
two data regimes:
  * Real LQQ3.L (listing 2012-12-13 -> present)
  * Synthetic 3x daily-reset on ^NDX (1990 -> present) for the longer horizon

No Water/Octane classification -- it's one flat results table. Outputs
output/lqq3_dedicated/ (results.csv + summary.json); build_strategy_results_excel.py
reads results.csv to add the "LQQ3" sheet.

Run from repo root:  python research/analyze_lqq3_signal_source.py
"""
from __future__ import annotations

import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (research/ script)

import json
from pathlib import Path

import pandas as pd

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from backtest_lqq3_guarded import download_panel, make_engine
from backtest_lqq3_synthetic_guarded import (
    build_synthetic_lqq3_close, download_ndx_vix_tbill, panel_from_close,
)
from backtest_spx_distance_scale import sma_band_signal
from core.indicators import sma
from core.metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import sma_cash_leverage

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "lqq3_dedicated"
NDX_TICKER = "^NDX"
LQQ3_TICKER = "LQQ3.L"
LQQ3_START = "2012-12-13"
SYNTH_START = "1990-01-01"

# Order of the strategy set tested on LQQ3.
STRATEGIES = [
    "Buy & hold (always in 3x)",
    "SMA20 1x/cash",
    "SMA50 1x/cash",
    "SMA100 1x/cash",
    "SMA200 1x/cash",
    "SMA50/200 Golden Cross 1x/cash",
    "SMA200 +-3% Band 1x/cash",
    "Guarded A5/B25 max 1x",
]


def compute_signals(panel: pd.DataFrame) -> dict[str, pd.Series]:
    """0/1 leverage series for each strategy, computed from panel['spx_close']."""
    close = panel["spx_close"]
    sig: dict[str, pd.Series] = {}
    sig["Buy & hold (always in 3x)"] = pd.Series(1.0, index=panel.index)
    for w in (20, 50, 100, 200):
        sig[f"SMA{w} 1x/cash"] = sma_cash_leverage(panel, w, 1.0)
    s50, s200 = sma(close, 50), sma(close, 200)
    gc = (s50 > s200).astype(float)
    gc[s200.isna()] = 0.0
    sig["SMA50/200 Golden Cross 1x/cash"] = gc
    sig["SMA200 +-3% Band 1x/cash"] = sma_band_signal(panel, 200, 0.03)
    glev, _ = guarded_lead_leverage(panel, max_leverage=1.0)
    sig["Guarded A5/B25 max 1x"] = glev
    return sig


def run_row(strategy: str, signal_source: str, data_label: str,
            instrument: pd.DataFrame, lev: pd.Series) -> dict:
    """Run one strategy: hold `instrument`, leverage from `lev` (aligned to instrument)."""
    lev = lev.reindex(instrument.index).ffill().fillna(0.0)
    result = make_engine().run(instrument, lev, name=strategy)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "Strategy": strategy,
        "Signal_Source": signal_source,
        "Data": data_label,
        "Start": instrument.index[0].date().isoformat(),
        "End": instrument.index[-1].date().isoformat(),
        "Trading_Days": len(instrument),
        "CAGR_pct": round(stats["cagr"] * 100, 2),
        "Vol_pct": round(stats["volatility"] * 100, 2),
        "Sharpe": round(stats["sharpe"], 3),
        "MaxDD_pct": round(stats["max_drawdown"] * 100, 2),
        "Calmar": round(stats["calmar"], 3) if stats.get("calmar") is not None else None,
        "End_Value": round(float(result.equity.iloc[-1]), 0),
        "Pct_Cash": round(float((lev <= 0.0).mean() * 100.0), 1),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading real LQQ3.L + ^NDX (signals) ...", flush=True)
    real_lqq3 = download_panel(LQQ3_TICKER, start=LQQ3_START)
    ndx_full = download_panel(NDX_TICKER, start=SYNTH_START)
    print(f"  real LQQ3: {real_lqq3.index[0].date()} -> {real_lqq3.index[-1].date()} ({len(real_lqq3)})", flush=True)

    print("Building synthetic 3x LQQ3 from ^NDX (1990+) ...", flush=True)
    ndx_vix = download_ndx_vix_tbill(SYNTH_START)
    synth_close = build_synthetic_lqq3_close(ndx_vix)
    synth_panel = panel_from_close(synth_close, ndx_vix["tbill_rate"])
    print(f"  synthetic 3x: {synth_panel.index[0].date()} -> {synth_panel.index[-1].date()} ({len(synth_panel)})", flush=True)

    rows: list[dict] = []

    # --- Real LQQ3 regime ---
    sig_on_lqq3 = compute_signals(real_lqq3)
    sig_on_ndx_real = compute_signals(ndx_full)  # computed on full ^NDX, reindexed to LQQ3 dates
    for name in STRATEGIES:
        rows.append(run_row(name, "LQQ3 (held instrument)", "Real LQQ3 (2012+)", real_lqq3, sig_on_lqq3[name]))
        rows.append(run_row(name, "Nasdaq 100 (underlying)", "Real LQQ3 (2012+)", real_lqq3, sig_on_ndx_real[name]))

    # --- Synthetic 3x regime (longer history) ---
    sig_on_synth = compute_signals(synth_panel)
    sig_on_ndx_synth = compute_signals(ndx_vix)  # ndx_vix['spx_close'] is ^NDX, same calendar as synth
    for name in STRATEGIES:
        rows.append(run_row(name, "Synthetic LQQ3 (held)", "Synthetic 3x (1990+)", synth_panel, sig_on_synth[name]))
        rows.append(run_row(name, "Nasdaq 100 (underlying)", "Synthetic 3x (1990+)", synth_panel, sig_on_ndx_synth[name]))

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "results.csv", index=False)
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps({"strategies": STRATEGIES, "rows": rows}, indent=2, default=str) + "\n",
        encoding="utf-8")

    print("\n=== LQQ3 dedicated backtest (CAGR / MaxDD / Sharpe) ===", flush=True)
    for data_label in ("Real LQQ3 (2012+)", "Synthetic 3x (1990+)"):
        print(f"\n[{data_label}]")
        for src in ("LQQ3 (held instrument)", "Synthetic LQQ3 (held)", "Nasdaq 100 (underlying)"):
            sub = [r for r in rows if r["Data"] == data_label and r["Signal_Source"] == src]
            if not sub:
                continue
            print(f"  signal on {src}:")
            for r in sub:
                print(f"    {r['Strategy']:<34} CAGR {r['CAGR_pct']:>6.2f}%  MaxDD {r['MaxDD_pct']:>7.2f}%  "
                      f"Sharpe {r['Sharpe']:>5.2f}  Cash {r['Pct_Cash']:>4.0f}%")
    print(f"\nWrote {OUTPUT_DIR}/results.csv ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
