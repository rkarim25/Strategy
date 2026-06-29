"""Confirm the headline band-sweep winners through the REAL PortfolioEngine
(not the fast replica), exactly as the main Excel sweep would run them."""
from __future__ import annotations
import numpy as np, pandas as pd
import backtest_spx_distance_scale as ds
from core.etp_leverage import SPX_ETP, build_etp_return_panel
from core.engine import PortfolioEngine, TRADING_COST_FROM_MID_PCT
from core.indicators import sma as sma_ind
from core.metrics import comprehensive_stats
import signals as S

P = ds.download_spx_panel()
close = P["spx_close"].to_numpy(dtype=float)
sma200 = sma_ind(P["spx_close"], 200).to_numpy(dtype=float)
panel = build_etp_return_panel(P, SPX_ETP)
avg_tbill = float(P["tbill_rate"].mean())
YEARS = (P.index[-1] - P.index[0]).days / 365.25


def real_run(raw_sig, lev):
    series = pd.Series(raw_sig * lev, index=P.index)
    eng = PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                          trading_cost_pct=TRADING_COST_FROM_MID_PCT,
                          annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    kw = {"name": "x"}
    if lev > 1:
        kw["etp_returns"] = panel
    res = eng.run(P, series, **kw)
    st = comprehensive_stats(res.equity, res.daily_returns, risk_free=avg_tbill)
    tpy = res.rebalance_count / YEARS
    return dict(cagr=st["cagr"]*100, vol=st["volatility"]*100, sharpe=st["sharpe"],
                sortino=st["sortino"], calmar=st["calmar"], dd=st["max_drawdown"]*100,
                end=float(res.equity.iloc[-1]), trades=res.rebalance_count, tpy=tpy)


# headline winner signals
baccel_n10 = S.variant_b_accel(close, sma200, 0.03, "conv", 10, 0.02, 0.03)
baccel_n20 = S.variant_b_accel(close, sma200, 0.03, "conv", 20, 0.02, 0.03)
inc_band = S.conv_band(close, sma200, 0.03, 0.03)

for name, sig, lev in [
    ("INCUMBENT band SMA200 +-3% 1x", inc_band, 1),
    ("B-accel SMA200 e3% N10 s2% 1x", baccel_n10, 1),
    ("B-accel SMA200 e3% N20 s2% 1x", baccel_n20, 1),
    ("INCUMBENT band SMA200 +-3% 2x", inc_band, 2),
    ("B-accel SMA200 e3% N10 s2% 2x", baccel_n10, 2),
    ("B-accel SMA200 e3% N20 s2% 2x", baccel_n20, 2),
]:
    r = real_run(sig, lev)
    print(f"{name:34s} CAGR {r['cagr']:6.2f}  Vol {r['vol']:5.2f}  Sharpe {r['sharpe']:.3f}  "
          f"Sortino {r['sortino']:.3f}  Calmar {r['calmar']:.3f}  DD {r['dd']:7.2f}  "
          f"trades {r['trades']:4d} ({r['tpy']:.1f}/yr)  end ${r['end']:,.0f}")
