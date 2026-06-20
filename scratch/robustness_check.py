"""Robustness check for the standout candidates from explore_spx_ndx_strategies.py.
(1) Sub-period split (does the edge hold in BOTH halves?)  (2) low-frequency rebalance
timing sensitivity (is the 'monthly' edge just lucky month-end dates?)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats

_C={}
def close(tk):
    if tk not in _C:
        s=yf.download(tk,period="max",auto_adjust=True,progress=False)["Close"].dropna().astype(float).squeeze()
        s.index=s.index.tz_localize(None); _C[tk]=s
    return _C[tk]
def prices(idx,start,end=None):
    p=pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100.0}).sort_index().ffill().dropna()
    p=p.loc[p.index>=start]
    if end is not None: p=p.loc[p.index<end]
    return p
def panel(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
        "ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0)},index=p.index)
def eng(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0.0,annual_inflow_abs=10.0)
def C(p): return p["spx_close"].astype(float)
def sma_cash(p,w,L): c=C(p); s=c.rolling(w,min_periods=w).mean(); l=pd.Series(0.0,index=p.index); l[c>s]=L; return l
def golden(p,f,sl,L): c=C(p); a=c.rolling(f,min_periods=f).mean(); b=c.rolling(sl,min_periods=sl).mean(); l=pd.Series(0.0,index=p.index); l[a>b]=L; return l
def absmom(p,lb,L): c=C(p); l=pd.Series(0.0,index=p.index); l[c>c.shift(lb)]=L; return l
def hyst(p,w,L,band): c=C(p); s=c.rolling(w,min_periods=w).mean(); l=pd.Series(np.nan,index=p.index); l[c>s*(1+band)]=L; l[c<s*(1-band)]=0.0; return l.ffill().fillna(0.0)
def monthlyize(raw): per=raw.index.to_period("M"); last=raw.groupby(per).last().shift(1); return pd.Series(per.map(last),index=raw.index).astype(float).fillna(0.0)
def every_n(raw,n,off):  # hold signal, only allowed to change every n trading days from offset
    keep=np.zeros(len(raw),bool); keep[off::n]=True
    s=raw.where(pd.Series(keep,index=raw.index)).ffill().fillna(0.0); return s
def stat(p,pan,lev):
    res=eng().run(p,lev,etp_returns=pan); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return s["cagr"]*100, s["max_drawdown"]*100, (s.get("calmar") or 0), round(res.rebalance_count/yrs,1)

CANDS={"BH 1x":lambda p:pd.Series(1.0,index=p.index),
 "SMA200 2x daily":lambda p:sma_cash(p,200,2),
 "Mom 12m 2x":lambda p:absmom(p,252,2),
 "SMA200 2x monthly":lambda p:monthlyize(sma_cash(p,200,2)),
 "SMA200 2x hyst3%":lambda p:hyst(p,200,2,0.03),
 "Golden 50/200 2x":lambda p:golden(p,50,200,2)}

for idx,name in [("^GSPC","S&P 500"),("^NDX","Nasdaq 100")]:
    print(f"\n################  {name}  ################")
    for lbl,(a,b) in [("FULL 1990-2026",("1990-01-01",None)),("H1 1990-2008",("1990-01-01","2008-01-01")),("H2 2008-2026",("2008-01-01",None))]:
        p=prices(idx,a,b); pan=panel(p)
        print(f"\n-- {lbl}  ({p.index[0].date()}..{p.index[-1].date()}) --   {'CAGR':>6}{'maxDD':>8}{'Calmar':>7}{'tr/yr':>6}")
        for s,fn in CANDS.items():
            c,d,cal,tr=stat(p,pan,fn(p)); print(f"   {s:20}{c:6.1f}%{d:7.1f}%{cal:7.2f}{tr:6.1f}")
    # rebalance-timing robustness for the low-frequency winners (full period)
    p=prices(idx,"1990-01-01"); pan=panel(p)
    print(f"\n-- {name} rebalance-timing robustness (SMA200 2x, change only every 21 trading days) --")
    res=[stat(p,pan,every_n(sma_cash(p,200,2),21,off)) for off in (0,5,10,15,20)]
    cagrs=[r[0] for r in res]; dds=[r[1] for r in res]
    print(f"   21d-rebalance across 5 phase offsets: CAGR {min(cagrs):.1f}-{max(cagrs):.1f}%  maxDD {min(dds):.1f}..{max(dds):.1f}%  (tight spread = robust)")
