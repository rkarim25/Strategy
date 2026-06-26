"""Synthetic LQQ3 (3x daily-reset on ^NDX) from 1990 + Guarded max 1x backtest.

Builds a full synthetic LQQ3 price path using etp_leverage.synthetic_daily_reset_return
(VIX-linked borrow, vol drag, TER) on Nasdaq 100 index returns — same model as pre-inception
fills in ndx_etp_returns.json.

Compares Guarded max 1x on:
  - Synthetic LQQ3 (1990 → present)
  - Real LQQ3.L (listing date → present)

Writes output/lqq3_synthetic_guarded/ and supports canvas embedding.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from backtest_lqq3_guarded import (
    DEFAULT_SPEC,
    LQQ3_START,
    make_engine,
    run_strategy_row,
    sma_cash_leverage,
    strategies_for_panel,
)
from core.etp_leverage import TBILL_TICKER, VIX_TICKER, synthetic_daily_reset_return
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "lqq3_synthetic_guarded"
NDX_TICKER = "^NDX"
LQQ3_TICKER = "LQQ3.L"
SYNTH_START = "1990-01-01"
INITIAL_SYNTH_PRICE = 100.0


def download_ndx_vix_tbill(start: str = SYNTH_START) -> pd.DataFrame:
    end = datetime.today()
    raw = yf.download(
        [NDX_TICKER, TBILL_TICKER, VIX_TICKER],
        start=start,
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No Yahoo data for NDX/T-bill/VIX.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": NDX_TICKER})

    panel = pd.DataFrame(
        {
            "spx_close": closes[NDX_TICKER].astype(float),
            "tbill_rate": closes[TBILL_TICKER].astype(float) / 100.0,
            "vix": closes[VIX_TICKER].astype(float),
        }
    )
    panel = panel.sort_index().ffill().dropna(how="any")
    if len(panel) < 260:
        raise ValueError(f"Not enough rows: {len(panel)}")
    return panel


def build_synthetic_lqq3_close(panel: pd.DataFrame, *, initial: float = INITIAL_SYNTH_PRICE) -> pd.Series:
    """Compound synthetic 3x daily-reset returns into a price level series."""
    idx_ret = panel["spx_close"].astype(float).pct_change()
    tbill = panel["tbill_rate"].astype(float)
    vix = panel["vix"].astype(float)

    prices = pd.Series(index=panel.index, dtype=float)
    prices.iloc[0] = initial
    prev = initial

    for i in range(1, len(panel)):
        dt = panel.index[i]
        if pd.isna(idx_ret.iloc[i]):
            prices.iloc[i] = prev
            continue
        r_idx = float(idx_ret.iloc[i])
        tb = float(tbill.iloc[i]) if pd.notna(tbill.iloc[i]) else 0.0
        vv = float(vix.iloc[i]) if pd.notna(vix.iloc[i]) else None
        r_3x = synthetic_daily_reset_return(r_idx, 3.0, tb, vix=vv)
        prev = prev * (1.0 + r_3x)
        prices.iloc[i] = prev

    return prices


def panel_from_close(close: pd.Series, tbill: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"spx_close": close.astype(float), "tbill_rate": tbill.astype(float)})


def overlap_tracking(synth: pd.Series, real: pd.Series) -> dict[str, float]:
    """Compare normalized synthetic vs real LQQ3 over overlap."""
    common = synth.index.intersection(real.index)
    if len(common) < 20:
        return {}
    s = synth.loc[common] / float(synth.loc[common[0]])
    r = real.loc[common] / float(real.loc[common[0]])
    rs = s.pct_change().dropna()
    rr = r.pct_change().dropna()
    aligned = rs.index.intersection(rr.index)
    diff = rs.loc[aligned] - rr.loc[aligned]
    end_ratio = float(s.iloc[-1] / r.iloc[-1])
    return {
        "overlap_start": str(common[0].date()),
        "overlap_end": str(common[-1].date()),
        "overlap_days": int(len(common)),
        "daily_return_corr": float(rs.loc[aligned].corr(rr.loc[aligned])),
        "wealth_ratio_synth_over_real_end": end_ratio,
        "ann_tracking_error_pct": float(diff.std() * np.sqrt(252) * 100),
    }


def write_synthetic_csv(close: pd.Series, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Close"])
        for dt, px in close.items():
            writer.writerow([dt.strftime("%Y-%m-%d"), f"{float(px):.9g}"])


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading ^NDX, ^IRX, ^VIX from 1990...", flush=True)
    ndx_panel = download_ndx_vix_tbill(SYNTH_START)
    synth_close = build_synthetic_lqq3_close(ndx_panel)
    synth_panel = panel_from_close(synth_close, ndx_panel["tbill_rate"])

    write_synthetic_csv(synth_close, OUTPUT_DIR / "lqq3_synthetic_daily.csv")

    print(
        f"Synthetic LQQ3: {synth_panel.index[0].date()} -> {synth_panel.index[-1].date()} "
        f"({len(synth_panel)} days)",
        flush=True,
    )

    rows_synth = strategies_for_panel("Synthetic LQQ3 (3x model on ^NDX)", "SYN-LQQ3", synth_panel)

    # Real LQQ3 from listing
    from backtest_lqq3_guarded import download_panel

    real_panel = download_panel(LQQ3_TICKER, start=LQQ3_START)
    rows_real = strategies_for_panel("Real LQQ3.L", LQQ3_TICKER, real_panel)

    tracking = overlap_tracking(synth_close, real_panel["spx_close"])

    comparison = rows_synth + rows_real
    import pandas as pd

    pd.DataFrame(comparison).to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    synth_guarded = next(r for r in rows_synth if "Guarded" in r["strategy"])
    real_guarded = next(r for r in rows_real if "Guarded" in r["strategy"])

    summary = {
        "synthetic_model": {
            "description": "3x daily-reset on ^NDX: 3*r - borrow(VIX) - vol_drag - 0.90% TER/yr",
            "start": synth_panel.index[0].date().isoformat(),
            "end": synth_panel.index[-1].date().isoformat(),
            "days": len(synth_panel),
            "initial_price": INITIAL_SYNTH_PRICE,
            "final_synthetic_close": float(synth_close.iloc[-1]),
        },
        "real_lqq3": {
            "ticker": LQQ3_TICKER,
            "start": real_panel.index[0].date().isoformat(),
            "end": real_panel.index[-1].date().isoformat(),
            "days": len(real_panel),
        },
        "guarded_max_1x_synthetic": {k: synth_guarded[k] for k in (
            "cagr", "ann_volatility", "sharpe", "max_drawdown", "end_$", "pct_cash",
            "start_date", "end_date", "trading_days",
        )},
        "guarded_max_1x_real_lqq3": {k: real_guarded[k] for k in (
            "cagr", "ann_volatility", "sharpe", "max_drawdown", "end_$", "pct_cash",
            "start_date", "end_date", "trading_days",
        )},
        "all_strategies": comparison,
        "overlap_tracking": tracking,
        "guarded_params": DEFAULT_SPEC,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print("\n=== Guarded max 1x on synthetic LQQ3 (1990+) ===")
    print(
        f"CAGR {synth_guarded['cagr']*100:.2f}%  Sharpe {synth_guarded['sharpe']:.3f}  "
        f"MaxDD {synth_guarded['max_drawdown']*100:.2f}%  End ${synth_guarded['end_$']:,.0f}"
    )
    print("\n=== Guarded max 1x on real LQQ3.L ===")
    print(
        f"CAGR {real_guarded['cagr']*100:.2f}%  Sharpe {real_guarded['sharpe']:.3f}  "
        f"MaxDD {real_guarded['max_drawdown']*100:.2f}%  End ${real_guarded['end_$']:,.0f}"
    )
    if tracking:
        print(
            f"\nOverlap synth vs real: corr {tracking['daily_return_corr']:.3f}, "
            f"wealth ratio {tracking['wealth_ratio_synth_over_real_end']:.3f}"
        )
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
