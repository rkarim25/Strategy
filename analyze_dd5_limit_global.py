"""
Global scan: highest CAGR under a 5% max drawdown portfolio limit.

Uses PortfolioEngine hard floor at -5% (same mechanism as site: cash when breach).
Tests buy-and-hold 1x, SMA20 1x/cash, and Guarded max 1x across the multi-asset universe.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import (
    build_world_equity_proxy_close,
    guarded_lead_leverage,
)
from analyze_multi_asset_guarded_scan import UNIVERSE, MIN_ROWS, YEARS, PROXY_COMPONENTS
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine, passes_drawdown_limit
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "dd5_limit_global"
DD_LIMIT = 0.05


def download_closes(years: int = YEARS) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    tickers = list({t for _, t, _, _ in UNIVERSE} | set(PROXY_COMPONENTS) | {"^IRX"})
    raw = yf.download(tickers, start=start.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError("No data")
    if isinstance(raw.columns, pd.MultiIndex):
        return raw["Close"].copy().sort_index().ffill()
    return raw.rename(columns={"Close": tickers[0]}).sort_index().ffill()


def panel_for_close(close: pd.Series, tbill: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"spx_close": close.astype(float), "tbill_rate": tbill}).dropna(how="any")


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=DD_LIMIT,
        hard_drawdown_floor=True,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def run_with_limit(panel: pd.DataFrame, lev: pd.Series, name: str, asset: str, meta: dict) -> dict:
    eng = make_engine()
    res = eng.run(panel, lev, name=name)
    stats = __import__("metrics", fromlist=["comprehensive_stats"]).comprehensive_stats(
        res.equity, res.daily_returns
    )
    row = {
        "asset": asset,
        "strategy": name,
        "start_date": panel.index[0].date().isoformat(),
        "end_date": panel.index[-1].date().isoformat(),
        "trading_days": len(panel),
        "cagr": stats["cagr"],
        "max_drawdown": stats["max_drawdown"],
        "sharpe": stats["sharpe"],
        "end_$": float(res.equity.iloc[-1]),
        "pct_days_cash": float((res.leverage <= 0).mean() * 100.0),
        "risk_off_days": res.risk_off_days,
        "within_5pct_limit": passes_drawdown_limit(res.equity, DD_LIMIT),
        **meta,
    }
    return row


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading data ({YEARS}y)...", flush=True)
    closes = download_closes(YEARS)
    tbill = closes["^IRX"] / 100.0

    rows: list[dict] = []
    skipped: list[dict] = []

    # World proxy
    try:
        proxy_close = build_world_equity_proxy_close(closes)
        panel = panel_for_close(proxy_close, tbill)
        meta = {"ticker": "synthetic", "category": "Intl equity", "series_type": "proxy"}
        asset = "World 30y proxy -> VT"
        for name, lev in _strategies(panel):
            rows.append(run_with_limit(panel, lev(panel), name, asset, meta))
    except Exception as exc:  # noqa: BLE001
        skipped.append({"asset": "World proxy", "reason": str(exc)})

    for label, ticker, category, series_type in UNIVERSE:
        if ticker not in closes.columns:
            skipped.append({"asset": label, "ticker": ticker, "reason": "missing"})
            continue
        series = closes[ticker].dropna()
        if len(series) < MIN_ROWS:
            skipped.append({"asset": label, "reason": f"{len(series)} rows"})
            continue
        panel = panel_for_close(series, tbill)
        meta = {"ticker": ticker, "category": category, "series_type": series_type}
        try:
            for name, lev in _strategies(panel):
                rows.append(run_with_limit(panel, lev(panel), name, asset=label, meta=meta))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"asset": label, "reason": str(exc)})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "dd5_limit_results.csv", index=False)

    # Only rows that actually respected the limit (should be all with hard floor)
    ok = df[df["within_5pct_limit"]].copy()

    def best_by(group_cols: list[str]) -> pd.DataFrame:
        idx = ok.groupby(group_cols, dropna=False)["cagr"].idxmax()
        return ok.loc[idx].sort_values("cagr", ascending=False)

    best_strategy = best_by(["strategy"])
    best_category = (
        ok.groupby("category", dropna=False)["cagr"]
        .max()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"cagr": "best_cagr_any_strategy"})
    )

    # Per category: best asset + strategy
    cat_detail: list[dict] = []
    for cat in ok["category"].dropna().unique():
        sub = ok[ok["category"] == cat]
        top = sub.loc[sub["cagr"].idxmax()]
        cat_detail.append(
            {
                "category": cat,
                "best_asset": top["asset"],
                "best_strategy": top["strategy"],
                "cagr_pct": round(float(top["cagr"]) * 100, 2),
                "max_dd_pct": round(float(top["max_drawdown"]) * 100, 2),
                "pct_days_cash": round(float(top["pct_days_cash"]), 1),
            }
        )
    cat_detail.sort(key=lambda x: x["cagr_pct"], reverse=True)

    overall = ok.loc[ok["cagr"].idxmax()]

    payload = {
        "dd_limit_pct": DD_LIMIT * 100,
        "engine_note": "Hard floor at -5% from peak; leverage forced to cash when breached.",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall_winner": {
            "asset": overall["asset"],
            "category": overall["category"],
            "strategy": overall["strategy"],
            "cagr_pct": round(float(overall["cagr"]) * 100, 2),
            "max_dd_pct": round(float(overall["max_drawdown"]) * 100, 2),
            "pct_days_cash": round(float(overall["pct_days_cash"]), 1),
            "sharpe": round(float(overall["sharpe"]), 2),
        },
        "best_by_strategy": best_strategy[
            ["strategy", "asset", "category", "cagr", "max_drawdown", "pct_days_cash", "sharpe"]
        ].to_dict(orient="records"),
        "best_cagr_by_category": cat_detail,
        "skipped": skipped,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== 5% max DD limit — global winner ===")
    print(
        f"{overall['asset']} | {overall['strategy']} | "
        f"CAGR {float(overall['cagr'])*100:.2f}% | cash {float(overall['pct_days_cash']):.0f}% of days"
    )
    print("\nTop by category (best any strategy):")
    for row in cat_detail[:8]:
        print(
            f"  {row['category']}: {row['best_asset']} ({row['best_strategy']}) "
            f"{row['cagr_pct']}% CAGR, {row['pct_days_cash']}% cash days"
        )
    print(f"\nWrote {OUTPUT_DIR}")
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
        ("Guarded max 1x", guarded),
    ]


if __name__ == "__main__":
    sys.exit(main())
