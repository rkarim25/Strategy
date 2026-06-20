"""Buy-and-hold only: assets with historical max drawdown <= 5%."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from analyze_multi_asset_guarded_scan import UNIVERSE, MIN_ROWS, YEARS, PROXY_COMPONENTS, panel_for_close
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT = Path("output") / "bh_dd5_filter"
DD_MAX = 0.05

# Extra low-vol / cash-like tickers not in UNIVERSE
EXTRA = [
    ("Sterling proxy (GBP=X inv vol)", "GBP=X", "Cash/FX", "fx"),
    ("US dollar index", "DX-Y.NYB", "Cash/FX", "fx"),
    ("Ultrashort bond BIL", "BIL", "Cash-like", "etf"),
    ("Ultrashort bond SHV", "SHV", "Cash-like", "etf"),
    ("Money market VMFXX proxy", "VMOT", "Cash-like", "etf"),
    ("1-3Y Treasury SHY", "SHY", "Bonds", "etf"),
    ("0-1Y Treasury SHV", "SHV", "Bonds", "etf"),
    ("T-bill ETF TBIL", "TBIL", "Cash-like", "etf"),
    ("SONIA proxy (not listed)", "", "skip", "skip"),
]


def download() -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(YEARS * 365.25))
    tickers = list({t for _, t, _, _ in UNIVERSE + EXTRA if t} | set(PROXY_COMPONENTS) | {"^IRX"})
    raw = yf.download(tickers, start=start.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        return raw["Close"].copy().sort_index().ffill()
    return raw.rename(columns={"Close": tickers[0]}).sort_index().ffill()


def bh_row(label: str, panel: pd.DataFrame, meta: dict) -> dict:
    eng = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )
    lev = pd.Series(1.0, index=panel.index)
    res = eng.run(panel, lev, name="Buy & hold 1x")
    st = comprehensive_stats(res.equity, res.daily_returns)
    return {
        "asset": label,
        "cagr": st["cagr"],
        "max_drawdown": st["max_drawdown"],
        "volatility": st["volatility"],
        "sharpe": st["sharpe"],
        "calmar": st["calmar"],
        "end_$": float(res.equity.iloc[-1]),
        "trading_days": len(panel),
        "start_date": panel.index[0].date().isoformat(),
        "end_date": panel.index[-1].date().isoformat(),
        **meta,
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    closes = download()
    tbill = closes["^IRX"] / 100.0
    rows: list[dict] = []

    all_assets = list(UNIVERSE) + [e for e in EXTRA if e[2] != "skip"]
    seen = set()
    for label, ticker, category, series_type in all_assets:
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        if ticker not in closes.columns:
            continue
        series = closes[ticker].dropna()
        if len(series) < MIN_ROWS:
            continue
        panel = panel_for_close(series, tbill)
        rows.append(
            bh_row(
                label,
                panel,
                {"ticker": ticker, "category": category, "series_type": series_type},
            )
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT / "buy_hold_all.csv", index=False)

    within = df[df["max_drawdown"] >= -DD_MAX].sort_values("cagr", ascending=False)
    within.to_csv(OUTPUT / "buy_hold_within_5pct_dd.csv", index=False)

    shallow = df.sort_values("max_drawdown", ascending=False).head(15)

    payload = {
        "criterion": "Buy & hold 1x, no engine DD floor; max_drawdown >= -5%",
        "within_5pct_count": int(len(within)),
        "total_tested": int(len(df)),
        "winners": within.replace({pd.NA: None}).to_dict(orient="records"),
        "shallowest_15": shallow.replace({pd.NA: None}).to_dict(orient="records"),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Tested {len(df)} series. B&H with max DD <= 5%: {len(within)}")
    if len(within):
        for _, r in within.head(10).iterrows():
            print(
                f"  {r['asset']}: CAGR {r['cagr']*100:.2f}%, maxDD {r['max_drawdown']*100:.2f}%"
            )
    else:
        print("None qualify. Shallowest max DD:")
        for _, r in shallow.head(8).iterrows():
            print(
                f"  {r['asset']}: CAGR {r['cagr']*100:.2f}%, maxDD {r['max_drawdown']*100:.2f}%"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
