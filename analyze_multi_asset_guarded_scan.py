"""
Backtest Guarded A5/B25 (max 1x) across all Yahoo-testable asset classes.
Writes CSV + JSON for canvas embedding.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import (
    DEFAULT_GUARDED,
    build_world_equity_proxy_close,
    guarded_lead_leverage,
    run_row,
)
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "multi_asset_guarded_scan"
TBILL = "^IRX"
MIN_ROWS = 252
YEARS = 30

# (label, ticker, category, series_type)
UNIVERSE: list[tuple[str, str, str, str]] = [
    ("S&P 500", "^GSPC", "US equity", "index"),
    ("S&P 500 ETF", "SPY", "US equity", "etf"),
    ("Nasdaq 100", "^NDX", "US equity", "index"),
    ("Nasdaq Composite", "^IXIC", "US equity", "index"),
    ("Dow Jones", "^DJI", "US equity", "index"),
    ("Russell 2000", "^RUT", "US equity", "index"),
    ("Bloomberg Commodity", "^BCOM", "Commodities", "index"),
    ("Commodities DBC", "DBC", "Commodities", "etf"),
    ("Commodities GSG", "GSG", "Commodities", "etf"),
    ("Gold GLD", "GLD", "Gold", "etf"),
    ("Gold futures", "GC=F", "Gold", "future"),
    ("Treasury 20Y+ TLT", "TLT", "Bonds", "etf"),
    ("Treasury 7-10Y IEF", "IEF", "Bonds", "etf"),
    ("Treasury 1-3Y SHY", "SHY", "Bonds", "etf"),
    ("TIPS TIP", "TIP", "Bonds", "etf"),
    ("Developed ex-US EFA", "EFA", "Intl equity", "etf"),
    ("Emerging EEM", "EEM", "Intl equity", "etf"),
    ("All world ex-US VEU", "VEU", "Intl equity", "etf"),
    ("Total world VT", "VT", "Intl equity", "etf"),
    ("MSCI ACWI ACWI", "ACWI", "Intl equity", "etf"),
    ("EM VWO", "VWO", "Intl equity", "etf"),
    ("REITs VNQ", "VNQ", "REITs", "etf"),
    ("REITs IYR", "IYR", "REITs", "etf"),
    ("Bitcoin", "BTC-USD", "Crypto", "crypto"),
    ("VIX (exploratory)", "^VIX", "Volatility", "exploratory"),
]

PROXY_COMPONENTS = ["SPY", "EFA", "VTI", "VEU", "VT"]


def download_closes(years: int = YEARS) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    start_s = start.strftime("%Y-%m-%d")
    tickers = list({t for _, t, _, _ in UNIVERSE} | set(PROXY_COMPONENTS) | {TBILL})
    raw = yf.download(tickers, start=start_s, progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError("No data from yfinance")
    if isinstance(raw.columns, pd.MultiIndex):
        return raw["Close"].copy().sort_index().ffill()
    return raw.rename(columns={"Close": tickers[0]}).sort_index().ffill()


def panel_for_close(close: pd.Series, tbill: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"spx_close": close.astype(float), "tbill_rate": tbill}).dropna(how="any")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    closes = download_closes(YEARS)
    tbill = closes[TBILL] / 100.0

    rows: list[dict] = []
    skipped: list[dict] = []

    # Synthetic world proxy
    try:
        proxy_close = build_world_equity_proxy_close(closes)
        panel = panel_for_close(proxy_close, tbill)
        if len(panel) >= MIN_ROWS:
            for strategy, lev_fn in _strategies(panel):
                extra = {"ticker": "synthetic", "category": "Intl equity", "series_type": "proxy"}
                rows.append(
                    run_row("World 30y proxy -> VT", panel, strategy, lev_fn(panel), extra)
                )
    except Exception as exc:  # noqa: BLE001
        skipped.append({"asset": "World 30y proxy -> VT", "reason": str(exc)})

    for label, ticker, category, series_type in UNIVERSE:
        if ticker not in closes.columns:
            skipped.append({"asset": label, "ticker": ticker, "reason": "missing column"})
            continue
        series = closes[ticker].dropna()
        if len(series) < MIN_ROWS:
            skipped.append(
                {
                    "asset": label,
                    "ticker": ticker,
                    "reason": f"only {len(series)} rows",
                    "earliest": str(series.index[0].date()) if len(series) else None,
                }
            )
            continue
        panel = panel_for_close(series, tbill)
        meta = {"ticker": ticker, "category": category, "series_type": series_type}
        try:
            for strategy, lev_fn in _strategies(panel):
                rows.append(run_row(label, panel, strategy, lev_fn(panel), meta))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"asset": label, "ticker": ticker, "reason": str(exc)})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "multi_asset_guarded_scan.csv", index=False)

    # Pivot for canvas: guarded vs benchmarks per asset
    summary: list[dict] = []
    for asset in df["asset"].unique():
        sub = df[df["asset"] == asset]
        if sub.empty:
            continue
        meta_row = sub.iloc[0]
        bh = sub[sub["strategy"] == "Buy & hold 1x"]
        sma = sub[sub["strategy"] == "SMA20 1x/cash"]
        grd = sub[sub["strategy"].str.contains("max 1x", regex=False)]
        if bh.empty or grd.empty:
            continue
        bh_cagr = float(bh.iloc[0]["cagr"])
        grd_cagr = float(grd.iloc[0]["cagr"])
        sma_cagr = float(sma.iloc[0]["cagr"]) if not sma.empty else None
        summary.append(
            {
                "asset": asset,
                "ticker": meta_row.get("ticker", ""),
                "category": meta_row.get("category", ""),
                "series_type": meta_row.get("series_type", ""),
                "start_date": meta_row["start_date"],
                "end_date": meta_row["end_date"],
                "trading_days": int(meta_row["trading_days"]),
                "bh_cagr_pct": round(bh_cagr * 100, 2),
                "sma_cagr_pct": round(sma_cagr * 100, 2) if sma_cagr is not None else None,
                "guarded_cagr_pct": round(grd_cagr * 100, 2),
                "bh_max_dd_pct": round(float(bh.iloc[0]["max_drawdown"]) * 100, 2),
                "guarded_max_dd_pct": round(float(grd.iloc[0]["max_drawdown"]) * 100, 2),
                "guarded_sharpe": round(float(grd.iloc[0]["sharpe"]), 2),
                "guarded_end": round(float(grd.iloc[0]["end_$"]), 0),
                "cagr_vs_bh_pct": round((grd_cagr - bh_cagr) * 100, 2),
                "cagr_vs_sma_pct": round((grd_cagr - sma_cagr) * 100, 2) if sma_cagr is not None else None,
                "pct_cash": round(float(grd.iloc[0]["pct_cash"]), 1),
            }
        )

    summary.sort(key=lambda r: r["guarded_cagr_pct"], reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assumptions": {
            "initial_capital": 100,
            "annual_inflow_usd": 10,
            "trading_cost_pct": 1.0,
            "strategy": "Guarded A5/B25/X40/Y15, 0.75% lead, max 1x leverage",
            "benchmarks": ["Buy & hold 1x", "SMA20 1x/cash"],
        },
        "summary": summary,
        "full_results": df.replace({pd.NA: None}).to_dict(orient="records"),
        "skipped": skipped,
    }
    (OUTPUT_DIR / "canvas_data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Tested {len(summary)} assets; skipped {len(skipped)}. Wrote {OUTPUT_DIR}")
    return 0


def _strategies(panel: pd.DataFrame):
    lev_sma = sma_cash_leverage(panel, BASE_SMA_WINDOW, 1.0)

    def bh(_p):
        return pd.Series(1.0, index=_p.index)

    def sma(_p):
        return lev_sma

    def guarded(_p):
        return guarded_lead_leverage(_p, max_leverage=1.0)[0]

    return [
        ("Buy & hold 1x", bh),
        ("SMA20 1x/cash", sma),
        ("Guarded A5/B25 lead 0.75% (max 1x)", guarded),
    ]


if __name__ == "__main__":
    sys.exit(main())
