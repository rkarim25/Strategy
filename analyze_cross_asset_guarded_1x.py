"""
Cross-asset backtest: default Guarded rules capped at 1x (no 2x/3x leverage).

Compares buy-and-hold 1x, SMA20 1x/cash, and Guarded A5/B25/X40/Y15 with 0.75% lead
guard on SPX, gold, Nasdaq, and world equities using the same engine assumptions
as the website ($100 start, $10/year inflow, 1% rebalance cost).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD, BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "cross_asset_guarded_1x"

ASSETS = {
    "SPX": "^GSPC",
    "Gold (GLD)": "GLD",
    "Nasdaq 100": "^NDX",
    "World equities (VT)": "VT",
}

# VT tracks FTSE Global All Cap; the ETF exists only from 2008. For ~30y history we
# splice liquid ETF proxies (see build_world_equity_proxy_close).
WORLD_PROXY_COMPONENTS = ["SPY", "EFA", "VTI", "VEU", "VT"]
US_CAP_WEIGHT = 0.52
EX_US_CAP_WEIGHT = 0.48

TBILL_TICKER = "^IRX"
YEARS = 30

DEFAULT_GUARDED = {
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def build_world_equity_proxy_close(closes: pd.DataFrame) -> pd.Series:
    """
  Approximate FTSE Global All Cap / VT with a spliced ETF chain on Yahoo data:
    - 2008-06-26+: VT (fund)
    - 2007-03-08 to VT launch: 52% VTI + 48% VEU (US total + FTSE all-world ex-US)
    - 2001-08-27 to 2007-03-07: 52% SPY + 48% EFA (US + MSCI EAFE; EM underweight)
    - before EFA: SPY only (US-only placeholder; not true global)
    """
    spy = closes["SPY"].astype(float)
    efa = closes["EFA"].astype(float)
    vti = closes["VTI"].astype(float)
    veu = closes["VEU"].astype(float)
    vt = closes["VT"].astype(float)

    vt_start = vt.dropna().index[0]
    vti_start = vti.dropna().index[0]
    veu_start = veu.dropna().index[0]
    efa_start = efa.dropna().index[0]
    calendar = spy.dropna().index.sort_values()

    daily_ret = pd.Series(index=calendar, dtype=float)
    for dt in calendar:
        if dt >= vt_start and pd.notna(vt.loc[dt]):
            daily_ret.loc[dt] = float(vt.pct_change().loc[dt])
        elif dt >= vti_start and dt >= veu_start:
            daily_ret.loc[dt] = US_CAP_WEIGHT * float(vti.pct_change().loc[dt]) + EX_US_CAP_WEIGHT * float(
                veu.pct_change().loc[dt]
            )
        elif dt >= efa_start:
            daily_ret.loc[dt] = US_CAP_WEIGHT * float(spy.pct_change().loc[dt]) + EX_US_CAP_WEIGHT * float(
                efa.pct_change().loc[dt]
            )
        else:
            daily_ret.loc[dt] = float(spy.pct_change().loc[dt])

    daily_ret = daily_ret.dropna()
    return 100.0 * (1.0 + daily_ret).cumprod()


def download_asset_panel(years: int = YEARS) -> dict[str, pd.DataFrame]:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    tickers = list(ASSETS.values()) + WORLD_PROXY_COMPONENTS + [TBILL_TICKER]
    tickers = list(dict.fromkeys(tickers))
    raw = yf.download(tickers, start=start_s, end=end_s, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError("No market data returned from yfinance.")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw.rename(columns={"Close": tickers[0]})

    closes = closes.sort_index().ffill()
    tbill = closes[TBILL_TICKER] / 100.0

    panels: dict[str, pd.DataFrame] = {}
    for label, ticker in ASSETS.items():
        if ticker not in closes.columns:
            raise ValueError(f"Missing column for {label} ({ticker})")
        asset_close = closes[ticker].dropna()
        panel = pd.DataFrame({"spx_close": asset_close, "tbill_rate": tbill}).dropna(how="any")
        if len(panel) < 260:
            raise ValueError(f"Not enough rows for {label}: {len(panel)}")
        panels[label] = panel

    proxy_close = build_world_equity_proxy_close(closes)
    proxy_panel = pd.DataFrame({"spx_close": proxy_close, "tbill_rate": tbill}).dropna(how="any")
    if len(proxy_panel) < 260:
        raise ValueError(f"Not enough rows for world proxy: {len(proxy_panel)}")
    panels["World equities (30y proxy -> VT)"] = proxy_panel

    return panels


def guarded_lead_leverage(
    prices: pd.DataFrame,
    *,
    max_leverage: float = 3.0,
    trigger_a: float = DEFAULT_GUARDED["trigger_a"],
    trigger_b: float = DEFAULT_GUARDED["trigger_b"],
    lead_pct_below_sma20: float = DEFAULT_GUARDED["lead_pct_below_sma20"],
    x_return: float = DEFAULT_GUARDED["x_return"],
    y_return: float = DEFAULT_GUARDED["y_return"],
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    base_guard = (close > sma20).fillna(False)
    recovery_guard = (close >= sma20 * (1.0 - lead_pct_below_sma20)).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0

    def cap(value: float) -> float:
        return float(min(max(value, 0.0), max_leverage))

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev = 1.0 if base_ok else 0.0
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(3.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = cap(3.0)
                continue
            if px / entry_close - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(2.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = cap(3.0)
        elif dd <= -trigger_a and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = cap(2.0)
        else:
            if dd <= -trigger_a and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = cap(base_lev)

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
        "max_leverage": max_leverage,
    }
    return lev, counts


def run_row(
    asset: str,
    prices: pd.DataFrame,
    strategy: str,
    lev: pd.Series,
    extra: dict | None = None,
) -> dict:
    engine = make_engine()
    res = engine.run(prices, lev, name=strategy)
    stats = comprehensive_stats(res.equity, res.daily_returns)
    cash = invested_vs_tbills_sessions(res.leverage)
    row = {
        "asset": asset,
        "strategy": strategy,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats.get("cagr"),
        "ann_volatility": stats.get("volatility"),
        "sharpe": stats.get("sharpe"),
        "max_drawdown": stats.get("max_drawdown"),
        "calmar": stats.get("calmar"),
        "end_$": float(res.equity.iloc[-1]),
        "rebalances": res.rebalance_count,
        "trading_costs": res.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        "pct_invested": cash["pct_sessions_invested"],
    }
    if extra:
        row.update(extra)
    return row


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading cross-asset daily data...")
    panels = download_asset_panel(YEARS)

    rows: list[dict] = []
    for asset, prices in panels.items():
        print(f"\n{asset}: {prices.index[0].date()} to {prices.index[-1].date()} ({len(prices)} days)")

        lev_bh = pd.Series(1.0, index=prices.index)
        rows.append(run_row(asset, prices, "Buy & hold 1x", lev_bh))

        lev_sma = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
        rows.append(run_row(asset, prices, "SMA20 1x/cash", lev_sma))

        lev_guard_1x, counts_1x = guarded_lead_leverage(prices, max_leverage=1.0)
        rows.append(
            run_row(
                asset,
                prices,
                "Guarded A5/B25 lead 0.75% (max 1x)",
                lev_guard_1x,
                counts_1x,
            )
        )

        if asset == "SPX":
            lev_full, counts_full = guarded_lead_leverage(prices, max_leverage=3.0)
            rows.append(
                run_row(
                    asset,
                    prices,
                    "Guarded A5/B25 lead 0.75% (full 2x/3x)",
                    lev_full,
                    counts_full,
                )
            )

    df = pd.DataFrame(rows)
    df = df.sort_values(["asset", "strategy"]).reset_index(drop=True)

    out_csv = OUTPUT_DIR / "cross_asset_guarded_1x_results.csv"
    df.to_csv(out_csv, index=False)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "guarded_params": DEFAULT_GUARDED,
            "max_leverage_note": "Cross-asset test caps recovery leverage at 1x (no 2x/3x).",
        },
        "assets": {label: ticker for label, ticker in ASSETS.items()},
        "world_30y_proxy": {
            "note": "VT/FTSE Global All Cap has no usable 30y daily index on Yahoo; proxy splices SPY/EFA then VTI/VEU then VT.",
            "components": WORLD_PROXY_COMPONENTS,
            "weights": {"us": US_CAP_WEIGHT, "ex_us": EX_US_CAP_WEIGHT},
            "phases": [
                "pre-EFA: SPY only (US placeholder)",
                "EFA to VEU: 52% SPY + 48% EFA",
                "VEU to VT: 52% VTI + 48% VEU",
                "VT launch onward: VT",
            ],
        },
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    cols = [
        "asset",
        "strategy",
        "start_date",
        "end_date",
        "cagr",
        "ann_volatility",
        "sharpe",
        "max_drawdown",
        "end_$",
        "pct_cash",
        "rebalances",
    ]
    print("\n" + "=" * 100)
    print("CROSS-ASSET GUARDED (MAX 1x) VS REFERENCES")
    print("=" * 100)
    for asset in df["asset"].unique():
        sub = df[df["asset"] == asset]
        print(f"\n--- {asset} ({sub.iloc[0]['start_date']} to {sub.iloc[0]['end_date']}) ---")
        for _, r in sub.iterrows():
            print(
                f"  {r['strategy']:<40} "
                f"CAGR {r['cagr'] * 100:6.2f}%  "
                f"Sharpe {r['sharpe']:5.2f}  "
                f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
                f"End ${r['end_$']:,.0f}  "
                f"Cash {r['pct_cash']:5.1f}%"
            )

    # Common window: VT inception onward (all four assets available)
    common_start = max(panels[a].index[0] for a in panels)
    print(f"\n{'=' * 100}")
    print(f"COMMON WINDOW FROM {common_start.date()} (all assets)")
    print("=" * 100)
    common_rows: list[dict] = []
    for asset, prices in panels.items():
        segment = prices.loc[common_start:].copy()
        for strategy, builder in [
            ("Buy & hold 1x", lambda p: pd.Series(1.0, index=p.index)),
            ("SMA20 1x/cash", lambda p: sma_cash_leverage(p, BASE_SMA_WINDOW, 1.0)),
            (
                "Guarded A5/B25 lead 0.75% (max 1x)",
                lambda p: guarded_lead_leverage(p, max_leverage=1.0)[0],
            ),
        ]:
            common_rows.append(run_row(asset, segment, strategy, builder(segment)))

    common_df = pd.DataFrame(common_rows).sort_values(["asset", "strategy"])
    common_csv = OUTPUT_DIR / "cross_asset_guarded_1x_common_window.csv"
    common_df.to_csv(common_csv, index=False)
    for asset in common_df["asset"].unique():
        sub = common_df[common_df["asset"] == asset]
        print(f"\n--- {asset} ---")
        for _, r in sub.iterrows():
            print(
                f"  {r['strategy']:<40} "
                f"CAGR {r['cagr'] * 100:6.2f}%  "
                f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
                f"End ${r['end_$']:,.0f}"
            )

    print(f"\nWrote {out_csv}")
    print(f"Wrote {common_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
