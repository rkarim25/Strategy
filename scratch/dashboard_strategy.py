"""Conviction dashboard: leverage = f(# technical signals green). 6 diverse binary signals;
leverage scales 0->3x with the count. 3x only when nearly all green (strong trend + calm
vol) = rational by construction. Backtest vs incumbents on SPX/NDX (30y synth, both halves),
report CAGR/DD/Calmar/turnover + leverage mix. Daily and monthly-applied versions."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from core.etp_leverage import TER_ANNUAL
from core.metrics import comprehensive_stats
_C={}
def close(tk):
    if tk not in _C:
        s=yf.download(tk,period="max",auto_adjust=True,progress=False)["Close"].dropna().astype(float).squeeze(); s.index=s.index.tz_localize(None); _C[tk]=s
    return _C[tk]
def prices(idx,a="1990-01-01",b=None):
    p=pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); p=p[p.index>=pd.Timestamp(a)]
    return p[p.index<pd.Timestamp(b)] if b else p
def pan(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),"ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),"ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=10.0)
def Cl(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p): return Cl(p).pct_change().rolling(20).std()*np.sqrt(252)

def signals(p):
    c=Cl(p); rv=rvol(p)
    return pd.DataFrame({
        "above_sma200": (c>sma(c,200)),
        "above_sma50":  (c>sma(c,50)),
        "above_sma20":  (c>sma(c,20)),
        "mom_12m":      (c>c.shift(252)),
        "breakout_60d": (c>=0.97*c.rolling(60,min_periods=60).max()),
        "calm_vol":     (rv < 1.2*rv.rolling(252,min_periods=60).median()),
    }).fillna(False)

def dashboard_lev(p, maxlev=3, monthly=False):
    sig=signals(p); n=sig.sum(axis=1)  # 0..6 green
    # map count -> leverage: <=1 cash, 2 ->1x, 3-4 ->2x, 5-6 ->3x  (capped at maxlev)
    lev=pd.Series(0.0,index=p.index)
    lev[n>=2]=1.0; lev[n>=3]=2.0; lev[n>=5]=3.0
    lev=lev.clip(upper=maxlev)
    if monthly:
        per=lev.index.to_period("M"); last=lev.groupby(per).last().shift(1); lev=pd.Series(per.map(last),index=lev.index).astype(float).fillna(0.0)
    return lev
# incumbents
def golden(p,L): c=Cl(p); o=pd.Series(0.0,index=p.index); o[sma(c,50)>sma(c,200)]=L; return o
def relhigh(p,k=1.2): rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
def volguard(p,L,cap): b=golden(p,L); b[relhigh(p)&(b>cap)]=cap; return b

def stat(p,lev):
    res=E().run(p,lev,etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    avglev=float(lev.reindex(p.index).fillna(0).mean())
    return dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=(s.get("calmar") or 0),sharpe=s["sharpe"],tr=res.rebalance_count/yrs,avglev=avglev)

CANDS={
 "Buy & hold 2x":         lambda p: pd.Series(2.0,index=p.index),
 "Golden 50/200 2x":      lambda p: golden(p,2),
 "Golden 2x vol-guard":   lambda p: volguard(p,2,1),
 "Dashboard 0-3x daily":  lambda p: dashboard_lev(p,3,False),
 "Dashboard 0-3x monthly":lambda p: dashboard_lev(p,3,True),
 "Dashboard 0-2x daily":  lambda p: dashboard_lev(p,2,False),
}
for idx,label in [("^GSPC","S&P 500"),("^NDX","Nasdaq 100")]:
    print(f"\n{'='*104}\n{label}")
    for lbl,(a,b) in [("FULL 1990-2026",("1990-01-01",None)),("H1 90-08",("1990-01-01","2008-01-01")),("H2 08-26",("2008-01-01",None))]:
        p=prices(idx,a,b)
        if lbl=="FULL 1990-2026":
            print(f"{'strategy':24}{'CAGR':>7}{'maxDD':>8}{'Calmar':>7}{'Sharpe':>7}{'tr/yr':>7}{'avgLev':>7}")
        tag = "" if lbl=="FULL 1990-2026" else f"   [{lbl}]"
        if lbl!="FULL 1990-2026": continue
        for name,fn in CANDS.items():
            d=stat(p,fn(p)); print(f"{name:24}{d['cagr']:6.1f}%{d['dd']:7.1f}%{d['cal']:7.2f}{d['sharpe']:7.2f}{d['tr']:7.1f}{d['avglev']:7.2f}")
    # sub-period robustness for the dashboard vs golden vguard
    print("  sub-periods (CAGR/maxDD):")
    for name in ["Golden 2x vol-guard","Dashboard 0-3x daily","Dashboard 0-3x monthly"]:
        h1=stat(prices(idx,"1990-01-01","2008-01-01"),CANDS[name](prices(idx,"1990-01-01","2008-01-01")))
        h2=stat(prices(idx,"2008-01-01"),CANDS[name](prices(idx,"2008-01-01")))
        print(f"    {name:24} H1 {h1['cagr']:5.1f}%/{h1['dd']:5.0f}%   H2 {h2['cagr']:5.1f}%/{h2['dd']:5.0f}%")
