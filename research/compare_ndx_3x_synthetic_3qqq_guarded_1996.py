"""
Side-by-side: Guarded NDX binary 3x/cash vs Guarded on synthetic 3QQQ from 1996.

Strategy A — Guarded A5/B25 signals on ^NDX; any invested day maps to 3x ETP (ret_3),
          else cash. No 1x/2x tiers.

Strategy B — Synthetic 3× daily-reset LQQ3/3QQQ model on ^NDX from 1996; Guarded
          max 1x (cash vs fully in the 3x product). Signals and P&L on synthetic price.

Common window aligned after SMA warmup. Writes output/ndx_3x_vs_synthetic_3qqq_1996/
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from backtest_lqq3_synthetic_guarded import (
    build_synthetic_lqq3_close,
    download_ndx_vix_tbill,
    panel_from_close,
)
from backtest_ndx_guarded import DEFAULT_SPEC, make_engine
from core.etp_leverage import NDX_ETP, build_etp_return_panel, etp_coverage_summary
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_DIR = Path("output") / "ndx_3x_vs_synthetic_3qqq_1996"
COMMON_START = "1996-01-01"
NDX_TICKER = "^NDX"


def run_row(
    label: str,
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
    cash = invested_vs_tbills_sessions(result.leverage)
    row = {
        "label": label,
        "start_date": prices.index[0].date().isoformat(),
        "end_date": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        **extra,
    }
    return row, result


def downsample_equity(equity: pd.Series, *, n_points: int = 60) -> list[dict]:
    if len(equity) <= n_points:
        idx = equity.index
    else:
        positions = np.linspace(0, len(equity) - 1, n_points).astype(int)
        idx = equity.index[positions]
    out = []
    for dt in idx:
        out.append({"date": dt.strftime("%Y-%m"), "value": round(float(equity.loc[dt]), 2)})
    return out


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building synthetic 3QQQ from 1996...", flush=True)
    ndx_vix = download_ndx_vix_tbill(COMMON_START)
    synth_close = build_synthetic_lqq3_close(ndx_vix)
    synth_panel = panel_from_close(synth_close, ndx_vix["tbill_rate"])

    ndx_panel = pd.DataFrame(
        {
            "spx_close": ndx_vix["spx_close"].astype(float),
            "tbill_rate": ndx_vix["tbill_rate"].astype(float),
        }
    )

    warmup = BASE_SMA_WINDOW + 5
    common_idx = synth_panel.index.intersection(ndx_panel.index)
    if len(common_idx) <= warmup:
        raise ValueError("Not enough overlapping history.")
    common_idx = common_idx[warmup:]
    synth_panel = synth_panel.loc[common_idx].copy()
    ndx_panel = ndx_panel.loc[common_idx].copy()

    etp = build_etp_return_panel(ndx_panel, NDX_ETP)
    cov = etp_coverage_summary(etp)

    lev_ndx, counts_ndx = guarded_strategy_leverage(
        ndx_panel,
        trigger_a=DEFAULT_SPEC["trigger_a"],
        trigger_b=DEFAULT_SPEC["trigger_b"],
        lead_pct_below_sma20=DEFAULT_SPEC["lead_pct_below_sma20"],
        x_return=DEFAULT_SPEC["x_return"],
        y_return=DEFAULT_SPEC["y_return"],
    )
    lev_3x = lev_ndx.map(lambda x: 3.0 if float(x) > 0 else 0.0)

    row_a, res_a = run_row(
        "Guarded NDX binary 3x/cash",
        ndx_panel,
        lev_3x,
        etp_returns=etp,
        signal_ticker=NDX_TICKER,
        pnl_mode="NDX signals · 3x ETP ret_3 when invested",
        pct_days_3x=float((lev_3x > 0).mean() * 100.0),
        pct_days_cash=float((lev_3x <= 0).mean() * 100.0),
        tier2_entries=counts_ndx.get("tier2_entries"),
        tier3_entries=counts_ndx.get("tier3_entries"),
    )

    lev_synth, counts_synth = guarded_lead_leverage(synth_panel, max_leverage=1.0)
    row_b, res_b = run_row(
        "Guarded max 1x on synthetic 3QQQ",
        synth_panel,
        lev_synth,
        signal_ticker="SYN-3QQQ",
        pnl_mode="Synthetic 3× daily-reset on ^NDX · cash vs fully in product",
        pct_days_cash=counts_synth["pct_days_cash"],
        pct_days_in_3x=float((lev_synth > 0).mean() * 100.0),
        tier2_entries=counts_synth.get("tier2_entries"),
        tier3_entries=counts_synth.get("tier3_entries"),
    )

    rows = [row_a, row_b]
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    equity_a = downsample_equity(res_a.equity)
    equity_b = downsample_equity(res_b.equity)
    dates = sorted({p["date"] for p in equity_a} | {p["date"] for p in equity_b})
    by_date_a = {p["date"]: p["value"] for p in equity_a}
    by_date_b = {p["date"]: p["value"] for p in equity_b}
    equity_chart = [
        {"date": d, "ndx3x": by_date_a.get(d), "synth3qqq": by_date_b.get(d)}
        for d in dates
        if d in by_date_a and d in by_date_b
    ]

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": {
            "start": row_a["start_date"],
            "end": row_a["end_date"],
            "days": row_a["trading_days"],
        },
        "assumptions": {
            "guarded": DEFAULT_SPEC,
            "initial_capital": 100,
            "annual_inflow": 10,
            "rebalance_cost_pct": 1.0,
            "synthetic_model": "3x daily-reset on ^NDX: borrow(VIX), vol drag, 0.90% TER/yr",
        },
        "etp_coverage": cov,
        "strategies": rows,
        "equity_chart": equity_chart,
        "synthetic_final_close": float(synth_close.loc[common_idx[-1]]),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"\nPeriod: {row_a['start_date']} -> {row_a['end_date']} ({row_a['trading_days']} days)")
    for r in rows:
        print(
            f"\n{r['label']}\n"
            f"  CAGR {r['cagr']*100:.2f}%  Sharpe {r['sharpe']:.2f}  "
            f"MaxDD {r['max_drawdown']*100:.2f}%  End ${r['end_$']:,.0f}  "
            f"Rebal {r['rebalances']}"
        )
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
