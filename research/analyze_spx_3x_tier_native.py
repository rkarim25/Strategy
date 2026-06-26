"""3x ETP with tier-native SMA signals on 3x benchmark (1996+)."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyze_spx_parallel_tier_sma import benchmark_prices_from_etp
from backtest_spx_guarded import download_spx_panel, make_engine
from core.etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import sma_cash_leverage

from analyze_cross_asset_guarded_1x import guarded_lead_leverage

OUTPUT_DIR = Path("output") / "spx_3x_tier_native"
SMA_WINDOW = 20
LEAD_PCT = 0.0075


def run_row(prices: pd.DataFrame, lev: pd.Series, name: str, etp: pd.DataFrame) -> dict:
    result = make_engine().run(prices, lev, name=name, etp_returns=etp)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    return {
        "strategy": name,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
        "pct_cash": cash["pct_sessions_tbills"],
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = download_spx_panel()
    etp = build_etp_return_panel(prices, SPX_ETP)
    bench = benchmark_prices_from_etp(etp)
    p3 = bench["p_3x"].astype(float)
    sma3 = p3.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    mom3 = p3 / p3.shift(20) - 1.0

    rows: list[dict] = []

    lev = pd.Series(0.0, index=prices.index)
    lev.loc[p3 > sma3] = 3.0
    rows.append(run_row(prices, lev, "3x when 3x benchmark > SMA20 (tier-native)", etp))

    lev = pd.Series(0.0, index=prices.index)
    lev.loc[p3 >= sma3 * (1.0 - LEAD_PCT)] = 3.0
    rows.append(run_row(prices, lev, "3x when 3x benchmark >= SMA20 - 0.75% (tier-native lead)", etp))

    lev = pd.Series(0.0, index=prices.index)
    lev.loc[(p3 > sma3) & (mom3 > 0)] = 3.0
    rows.append(run_row(prices, lev, "3x tier-native SMA + positive 20d mom", etp))

    lev_spx = sma_cash_leverage(prices, SMA_WINDOW, 3.0)
    rows.append(run_row(prices, lev_spx, "3x when SPX > SMA20 (index signal)", etp))

    lev_g, _ = guarded_lead_leverage(prices, max_leverage=3.0)
    lev_bin = lev_g.map(lambda x: 3.0 if x > 0 else 0.0)
    rows.append(run_row(prices, lev_bin, "Guarded signals -> binary 3x/cash (SPX)", etp))

    lev_bh = pd.Series(3.0, index=prices.index)
    rows.append(run_row(prices, lev_bh, "Buy & hold 3x ETP", etp))

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "etp_coverage": etp_coverage_summary(etp),
        "tier_native_signal": "P_3x = cumulative 3x ETP price; SMA20 on P_3x not SPX",
        "results": rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    print(f"Window: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)")
    print(f"ETP real 3x days: {summary['etp_coverage']['pct_real_3x']}%")
    print()
    for _, r in df.iterrows():
        print(
            f"  {r['strategy'][:48]:48}  "
            f"CAGR {r['cagr']*100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
            f"MaxDD {r['max_drawdown']*100:6.2f}%  End ${r['end_$']:,.0f}  "
            f"3x {r['pct_days_3x']:5.1f}%"
        )
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
