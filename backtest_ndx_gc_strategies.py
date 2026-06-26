"""Backtest + Monte Carlo for the two Nasdaq 100 Golden-Cross strategies featured on the site.

Two strategies on ^NDX (signals on the index, P&L via the listed-ETP panel — QLD/TQQQ with
synthetic daily-reset fallback so 2x days are modelled honestly):

  * Nasdaq Water*  : SMA50/200 Golden Cross 1x/cash
  * Nasdaq Octane* : GC 50/200 1x; +2x when VIX<20 & index drawdown > -12%

Writes ndx_water_site_data.json and ndx_octane_site_data.json (+ etp_returns) for the website,
matching the spx_distance_scale_site_data.json shape so the full-parity strategy pages can read them.
"Water*"/"Octane*" because Nasdaq has no strict Water/Octane (these are the Stillwater picks).

Run from repo root:  python backtest_ndx_gc_strategies.py
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_lqq3_synthetic_guarded import download_ndx_vix_tbill
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from core.etp_leverage import (
    MC_ETP_METHOD, NDX_ETP, bootstrap_etp_paths, build_etp_return_panel,
    etp_coverage_summary, export_etp_returns_json,
)
from core.indicators import sma
from core.metrics import comprehensive_stats

ROOT = Path(__file__).resolve().parent
NDX_TICKER = "^NDX"
ANNUAL_INFLOW_USD = 10.0
N_SIMS, HORIZON_DAYS, BLOCK_DAYS, SEED = 200, 2520, 21, 20260626

SPECS = {
    "ndx_water": {
        "strategy": "SMA50/200 Golden Cross 1x/cash",
        "octane": False,
        "label": "Nasdaq 100 Water*",
        "site_json": "ndx_water_site_data.json",
        "etp_json": "ndx_water_etp_returns.json",
        "out_dir": "ndx_water",
    },
    "ndx_octane": {
        "strategy": "GC 50/200 1x; +2x when VIX<20 & idxDD>-12%",
        "octane": True,
        "label": "Nasdaq 100 Octane*",
        "site_json": "ndx_octane_site_data.json",
        "etp_json": "ndx_octane_etp_returns.json",
        "out_dir": "ndx_octane",
    },
}


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                           trading_cost_pct=TRADING_COST_FROM_MID_PCT,
                           annual_inflow_pct=0.0, annual_inflow_abs=ANNUAL_INFLOW_USD)


def gc_leverage(panel: pd.DataFrame, octane: bool) -> pd.Series:
    """Golden-cross leverage: 1x when SMA50>SMA200 (else cash); Octane bumps to 2x when
    VIX<20 AND index drawdown-from-peak > -12%."""
    close = panel["spx_close"]
    s50, s200 = sma(close, 50), sma(close, 200)
    lev = (s50 > s200).astype(float)
    lev[s200.isna()] = 0.0
    if octane:
        vix = panel["vix"] if "vix" in panel else pd.Series(20.0, index=panel.index)
        dd = close / close.cummax() - 1.0
        bump = (lev > 0) & (vix < 20.0) & (dd > -0.12)
        lev = lev.where(~bump, 2.0)
    return lev


def pct(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else f"{float(x)*100:.2f}%"


def money(x):
    return None if x is None else f"${float(x):,.0f}"


def f3(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else f"{float(x):.3f}"


def f2(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else f"{float(x):.2f}"


def run_lev(panel, lev, name, etp=None):
    kw = {"name": name}
    if (lev > 1.0).any():
        kw["etp_returns"] = etp if etp is not None else None
        if etp is None:
            kw["etp_bundle"] = NDX_ETP
    res = make_engine().run(panel, lev, **{k: v for k, v in kw.items() if v is not None})
    st = comprehensive_stats(res.equity, res.daily_returns, risk_free=float(panel["tbill_rate"].mean()))
    pos = lev[lev > 0]
    return {
        "strategy": name, "cagr": st["cagr"], "ann_volatility": st["volatility"], "sharpe": st["sharpe"],
        "sortino": st.get("sortino"), "max_drawdown": st["max_drawdown"], "calmar": st.get("calmar"),
        "end_$": float(res.equity.iloc[-1]), "rebalances": res.rebalance_count,
        "win_rate": st.get("win_rate"), "profit_factor": st.get("profit_factor"),
        "beta": st.get("beta"), "alpha": st.get("alpha"),
        "pct_days_cash": float((lev <= 0).mean() * 100), "pct_days_1x": float(((lev > 0) & (lev < 1.5)).mean() * 100),
        "pct_days_2x": float((lev >= 1.5).mean() * 100), "pct_days_3x": 0.0,
        "avg_leverage": float(pos.mean()) if len(pos) else 0.0,
        "total_trades": int((lev.diff().fillna(0) != 0).sum()),
    }


def fmt_row(r):
    return {**r, "cagr_pct": pct(r["cagr"]), "ann_volatility_pct": pct(r.get("ann_volatility")),
            "max_drawdown_pct": pct(r["max_drawdown"]), "sharpe_fmt": f3(r.get("sharpe")),
            "sortino_fmt": f3(r.get("sortino")), "end_value_fmt": money(r.get("end_$")),
            "calmar_fmt": f2(r.get("calmar")), "win_rate_pct": pct(r.get("win_rate")),
            "profit_factor_fmt": f2(r.get("profit_factor")), "beta_fmt": f2(r.get("beta")),
            "alpha_pct": pct(r.get("alpha")), "cash_pct": pct(r.get("pct_days_cash", 0)/100.0),
            "avg_leverage_fmt": f2(r.get("avg_leverage"))}


def signal_history(panel, lev):
    close, s50, s200 = panel["spx_close"], sma(panel["spx_close"], 50), sma(panel["spx_close"], 200)
    out, prev = [], 0.0
    for i in range(len(panel)):
        dt = panel.index[i]
        lv = float(lev.iloc[i]) if not pd.isna(lev.iloc[i]) else 0.0
        act = "start" if i == 0 else ("enter_long" if prev <= 0 < lv else ("exit_to_cash" if prev > 0 >= lv else "hold"))
        out.append({"date": dt.date().isoformat(), "signal": "cash" if lv <= 0 else "long",
                    "leverage": round(lv, 1), "spx_close": round(float(close.iloc[i]), 2),
                    "sma50": None if pd.isna(s50.iloc[i]) else round(float(s50.iloc[i]), 2),
                    "sma200": None if pd.isna(s200.iloc[i]) else round(float(s200.iloc[i]), 2),
                    "rsi14": None, "action": act})
        prev = lv
    return out


def price_sma_data(panel):
    close, s50, s200 = panel["spx_close"], sma(panel["spx_close"], 50), sma(panel["spx_close"], 200)
    return {"dates": [d.date().isoformat() for d in panel.index],
            "spx_close": [round(float(c), 2) for c in close],
            "sma50": [None if pd.isna(v) else round(float(v), 2) for v in s50],
            "sma200": [None if pd.isna(v) else round(float(v), 2) for v in s200]}


def equity_curve(panel, lev):
    strat = make_engine().run(panel, lev, name="strategy", etp_bundle=NDX_ETP if (lev > 1.0).any() else None).equity
    bh = make_engine().run(panel, pd.Series(1.0, index=panel.index), name="bh1").equity
    return {"dates": [d.date().isoformat() for d in panel.index],
            "strategy_equity": [round(float(strat.iloc[i]), 2) for i in range(len(strat))],
            "buy_hold_1x_equity": [round(float(bh.iloc[i]), 2) for i in range(len(bh))]}


def monte_carlo(panel, etp, octane):
    cagr, dd, end = [], [], []
    for path, path_etp in bootstrap_etp_paths(panel, etp, n_sims=N_SIMS, horizon_days=HORIZON_DAYS,
                                              block_days=BLOCK_DAYS, seed=SEED):
        r = run_lev(path, gc_leverage(path, octane), "mc", etp=path_etp)
        cagr.append(r["cagr"]); dd.append(r["max_drawdown"]); end.append(r["end_$"])
    c, d, e = pd.Series(cagr).dropna(), pd.Series(dd).dropna(), pd.Series(end).dropna()
    return {"n_sims": N_SIMS, "horizon_years": HORIZON_DAYS/252.0, "block_days": BLOCK_DAYS, "seed": SEED,
            "method": MC_ETP_METHOD, "median_cagr": float(c.median()), "p10_cagr": float(c.quantile(.1)),
            "p90_cagr": float(c.quantile(.9)), "median_max_drawdown": float(d.median()),
            "p10_max_drawdown": float(d.quantile(.1)), "p90_max_drawdown": float(d.quantile(.9)),
            "median_end_$": float(e.median()), "prob_max_dd_worse_35pct": float((d <= -.35).mean()),
            "prob_max_dd_worse_40pct": float((d <= -.40).mean()), "prob_max_dd_worse_50pct": float((d <= -.50).mean()),
            "prob_end_below_start": float((e < INITIAL_CAPITAL).mean())}


def json_safe(o):
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (f != f or f in (float("inf"), float("-inf"))) else f
    if isinstance(o, np.integer):
        return int(o)
    return o


def build_payload(spec, panel, default_row, comparison, mc, etp):
    bh1, bh2, bh3 = comparison[0], comparison[1], comparison[2]
    return {
        "ticker": NDX_TICKER, "asset_label": "Nasdaq 100", "strategy_params": spec,
        "sample": {"start_date": panel.index[0].date().isoformat(), "end_date": panel.index[-1].date().isoformat(),
                   "trading_days": len(panel)},
        "default_backtest": {**default_row, "cagr_pct": pct(default_row["cagr"]),
                             "max_drawdown_pct": pct(default_row["max_drawdown"]),
                             "ann_volatility_pct": pct(default_row["ann_volatility"]),
                             "sharpe_fmt": f3(default_row["sharpe"]), "sortino_fmt": f3(default_row.get("sortino")),
                             "end_value_fmt": money(default_row["end_$"]), "calmar_fmt": f2(default_row.get("calmar")),
                             "win_rate_pct": pct(default_row.get("win_rate")),
                             "profit_factor_fmt": f2(default_row.get("profit_factor")),
                             "beta_fmt": f2(default_row.get("beta")), "alpha_pct": pct(default_row.get("alpha"))},
        "buy_and_hold_1x": {**bh1, "cagr_pct": pct(bh1["cagr"]), "max_drawdown_pct": pct(bh1["max_drawdown"]),
                            "ann_volatility_pct": pct(bh1["ann_volatility"]), "sharpe_fmt": f3(bh1["sharpe"]),
                            "end_value_fmt": money(bh1["end_$"])},
        "buy_and_hold_2x": {**bh2, "cagr_pct": pct(bh2["cagr"]), "max_drawdown_pct": pct(bh2["max_drawdown"]),
                            "ann_volatility_pct": pct(bh2["ann_volatility"]), "sharpe_fmt": f3(bh2["sharpe"]),
                            "end_value_fmt": money(bh2["end_$"])},
        "buy_and_hold_3x": {**bh3, "cagr_pct": pct(bh3["cagr"]), "max_drawdown_pct": pct(bh3["max_drawdown"]),
                            "ann_volatility_pct": pct(bh3["ann_volatility"]), "sharpe_fmt": f3(bh3["sharpe"]),
                            "end_value_fmt": money(bh3["end_$"])},
        "comparison_table": [fmt_row(r) for r in comparison],
        "monte_carlo": {**mc, "median_cagr_pct": pct(mc.get("median_cagr")), "p10_cagr_pct": pct(mc.get("p10_cagr")),
                        "p90_cagr_pct": pct(mc.get("p90_cagr")), "median_max_drawdown_pct": pct(mc.get("median_max_drawdown")),
                        "p10_max_drawdown_pct": pct(mc.get("p10_max_drawdown")), "p90_max_drawdown_pct": pct(mc.get("p90_max_drawdown")),
                        "median_end_value_fmt": money(mc.get("median_end_$")),
                        "prob_max_dd_worse_35pct_fmt": pct(mc.get("prob_max_dd_worse_35pct")),
                        "prob_max_dd_worse_40pct_fmt": pct(mc.get("prob_max_dd_worse_40pct")),
                        "prob_max_dd_worse_50pct_fmt": pct(mc.get("prob_max_dd_worse_50pct")),
                        "prob_end_below_start_fmt": pct(mc.get("prob_end_below_start"))},
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "levered_pnl_model": f"Nasdaq 100 golden-cross signals; 2x days via QLD with synthetic fallback. Monte Carlo: {MC_ETP_METHOD}",
        "etp_coverage": etp_coverage_summary(etp), "monte_carlo_variants": [],
        "price_sma_data": price_sma_data(panel), "signal_history": signal_history(panel, gc_leverage(panel, spec["octane"])),
        "equity_curve": equity_curve(panel, gc_leverage(panel, spec["octane"])),
    }


def bh_row(panel, lev_val, label, etp):
    return run_lev(panel, pd.Series(float(lev_val), index=panel.index), label, etp=etp if lev_val > 1 else None)


def main() -> int:
    print("Downloading ^NDX + VIX + T-bill...", flush=True)
    panel = download_ndx_vix_tbill("1985-01-01")
    print(f"NDX: {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} days)", flush=True)
    etp = build_etp_return_panel(panel, NDX_ETP)

    for key, spec in SPECS.items():
        out_dir = ROOT / "output" / spec["out_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        export_etp_returns_json(etp, NDX_ETP, ROOT / spec["etp_json"])
        comparison = [bh_row(panel, 1.0, "Buy & Hold QQQ 1x", etp),
                      bh_row(panel, 2.0, "Buy & Hold QLD 2x", etp),
                      bh_row(panel, 3.0, "Buy & Hold TQQQ 3x", etp)]
        lev = gc_leverage(panel, spec["octane"])
        default_row = run_lev(panel, lev, spec["strategy"], etp=etp)
        comparison.append(default_row)
        print(f"  {spec['strategy']}: CAGR={pct(default_row['cagr'])} MaxDD={pct(default_row['max_drawdown'])} "
              f"Calmar={f2(default_row.get('calmar'))} Sharpe={f3(default_row['sharpe'])}", flush=True)
        print(f"  running Monte Carlo for {key}...", flush=True)
        mc = monte_carlo(panel, etp, spec["octane"])
        payload = json_safe(build_payload(spec, panel, default_row, comparison, mc, etp))
        txt = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        (ROOT / spec["site_json"]).write_text(txt, encoding="utf-8")
        (out_dir / spec["site_json"]).write_text(txt, encoding="utf-8")
        pd.DataFrame(comparison).to_csv(out_dir / "comparison.csv", index=False)
        print(f"  wrote {spec['site_json']}", flush=True)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
