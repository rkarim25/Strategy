"""Generate compact chart data for guarded tiered SMA20/50/200 canvas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from backtest_guarded_tiered_sma20_50_200 import (
    OUTPUT_DIR,
    guarded_tiered_leverage,
    make_engine,
    sma_cash_leverage,
)
from data_manager import load_backtest_data
from etp_leverage import SPX_ETP, build_etp_return_panel

CHART_JSON = OUTPUT_DIR / "guarded_tiered_sma20_50_200_chart_data.json"

KEY_STRATEGIES = [
    ("SMA20 3x/cash", 20, "sma3"),
    ("Guarded A10/B20 SMA20", 20, "guarded"),
    ("SMA50 3x/cash", 50, "sma3"),
    ("Guarded A10/B20 SMA50", 50, "guarded"),
    ("SMA200 3x/cash", 200, "sma3"),
    ("Guarded A10/B20 SMA200", 200, "guarded"),
]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    engine = make_engine()
    etp_panel = build_etp_return_panel(prices, SPX_ETP)

    equity_series = {}
    drawdown_series = {}
    for name, window, kind in KEY_STRATEGIES:
        if kind == "sma3":
            lev = sma_cash_leverage(prices, window, 3.0)
        else:
            lev, _ = guarded_tiered_leverage(prices, window)
        etp_kw = {"etp_returns": etp_panel} if kind == "sma3" or "Guarded" in name else {}
        res = engine.run(prices, lev, name=name, **etp_kw)
        annual_equity = res.equity.resample("YE").last()
        annual_dd = (res.equity / res.equity.cummax() - 1.0).resample("YE").min()
        equity_series[name] = [round(float(v), 2) for v in annual_equity]
        drawdown_series[name] = [round(abs(float(v)) * 100.0, 2) for v in annual_dd]

    categories = [str(dt.year) for dt in annual_equity.index]
    payload = {
        "source": "Yahoo Finance ^GSPC via project data loader",
        "time_range": f"{prices.index[0].date()} to {prices.index[-1].date()}",
        "categories": categories,
        "equity_$": equity_series,
        "drawdown_magnitude_pct": drawdown_series,
    }
    with CHART_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {CHART_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
