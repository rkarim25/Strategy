"""Compare Guarded default (NDX 2x/3x ETP) vs Guarded max 1x on LQQ3 over LQQ3 listing window."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from pathlib import Path

import pandas as pd

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from backtest_lqq3_guarded import download_panel, make_engine
from core.etp_leverage import NDX_ETP, build_etp_return_panel
from core.metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage

OUTPUT_DIR = Path("output") / "ndx_vs_lqq3_guarded"
LQQ3_START = "2012-12-13"
NDX_TICKER = "^NDX"
LQQ3_TICKER = "LQQ3.L"


def run_row(
    label: str,
    ticker: str,
    prices: pd.DataFrame,
    lev: pd.Series,
    *,
    etp_returns: pd.DataFrame | None = None,
    **extra,
) -> dict:
    run_kw: dict = {"name": label}
    if etp_returns is not None:
        run_kw["etp_returns"] = etp_returns
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    row = {
        "label": label,
        "ticker": ticker,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        **extra,
    }
    return row


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ndx = download_panel(NDX_TICKER, start=LQQ3_START)
    lqq = download_panel(LQQ3_TICKER, start=LQQ3_START)
    common = ndx.index.intersection(lqq.index)
    ndx = ndx.loc[common].copy()
    lqq = lqq.loc[common].copy()

    lev_ndx, _ = guarded_strategy_leverage(
        ndx,
        trigger_a=0.05,
        trigger_b=0.25,
        lead_pct_below_sma20=0.0075,
        x_return=0.40,
        y_return=0.15,
    )
    etp = build_etp_return_panel(ndx, NDX_ETP)
    row_ndx = run_row(
        "Guarded A5/B25 default (2x/3x tiers)",
        NDX_TICKER,
        ndx,
        lev_ndx,
        etp_returns=etp,
        note="Signals on ^NDX; P&L via listed ETP panel (LQQ3 at 3x tier)",
    )

    lev_3x_cash = lev_ndx.map(lambda x: 3.0 if float(x) > 0 else 0.0)
    row_3x = run_row(
        "Guarded A5/B25 binary 3x/cash",
        NDX_TICKER,
        ndx,
        lev_3x_cash,
        etp_returns=etp,
        note="Same Guarded signals as default; any invested day → 3x ETP, else cash",
        pct_days_3x=float((lev_3x_cash > 0).mean() * 100.0),
    )

    lev_lqq, counts = guarded_lead_leverage(lqq, max_leverage=1.0)
    row_lqq = run_row(
        "Guarded A5/B25 max 1x on LQQ3",
        LQQ3_TICKER,
        lqq,
        lev_lqq,
        pct_days_cash=counts["pct_days_cash"],
        note="Signals and P&L on LQQ3.L; max 1x = cash vs fully in 3x ETP",
    )

    rows = [row_ndx, row_3x, row_lqq]
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "comparison.csv", index=False)
    summary = {
        "period": {
            "start": row_ndx["start_date"],
            "end": row_ndx["end_date"],
            "days": row_ndx["trading_days"],
        },
        "strategies": rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
