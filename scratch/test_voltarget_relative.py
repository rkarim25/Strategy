"""Asset-relative vol threshold for Guarded+: de-lever when 20d vol > k * trailing-median vol."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats

def cl(t):
    s = yf.download(t, start="1990-01-01", end="2026-06-16", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None); return s
IR = cl("^IRX")

def synth(p):
    r = p["spx_close"].pct_change(); tb = p["tbill_rate"]
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0": tb/TRADING_DAYS, "ret_1": (r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
                         "ret_2": (2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
                         "ret_3": (3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0)}, index=p.index)

def gplus(p, mode, k=1.3, vt=0.20):
    c = p["spx_close"]; sma = c.rolling(200, min_periods=200).mean(); above = (c > sma).fillna(False)
    rvol = c.pct_change().rolling(20).std()*np.sqrt(TRADING_DAYS)
    if mode == "abs":
        calm = above & (rvol < vt)
    else:
        med = rvol.rolling(252, min_periods=60).median()
        thresh = (k*med).fillna(vt)
        calm = above & (rvol < thresh)
    lev = pd.Series(0.0, index=p.index); lev[above] = 1.0; lev[calm] = 2.0
    return lev

def run(p, panel, lev):
    e = PortfolioEngine(max_drawdown_limit=0.25, hard_drawdown_floor=True,
                        trading_cost_pct=0.001, annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    r = e.run(p, lev, etp_returns=panel); s = comprehensive_stats(r.equity, r.daily_returns)
    pct2x = float((r.leverage >= 1.5).mean()*100)
    return s["cagr"], s["max_drawdown"], s.get("calmar") or 0, pct2x

for label, tk in [("S&P 500","^GSPC"), ("Nasdaq 100","^NDX")]:
    p = pd.DataFrame({"spx_close": cl(tk), "tbill_rate": IR/100}).ffill().dropna()
    panel = synth(p)
    print(f"\n### {label} 30y synthetic")
    print(f"{'variant':28}{'CAGR':>8}{'maxDD':>8}{'Calmar':>8}{'%2x':>7}")
    c,dd,cal,p2 = run(p, panel, gplus(p, "abs", vt=0.20))
    print(f"{'abs 20% (current)':28}{c*100:7.1f}%{dd*100:7.1f}%{cal:8.2f}{p2:6.0f}%")
    for k in (1.2, 1.3, 1.5):
        c,dd,cal,p2 = run(p, panel, gplus(p, "rel", k=k))
        print(f"{'rel k=%.1f x median' % k:28}{c*100:7.1f}%{dd*100:7.1f}%{cal:8.2f}{p2:6.0f}%")
