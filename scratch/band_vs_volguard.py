"""Head-to-head: SMA200 2x 3% band (hysteresis) vs Golden 50/200 2x vol-guard.
Single-path historical (full + both halves) CAGR/maxDD/Calmar/turnover/avgLev, plus
worst real drawdowns by date, for SPX and NDX. Daily-reset synth model, 0.10% cost, signal
lagged 1d in the engine. Answers: is the band actually a 'better signal' than the vol-guard?"""
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
def C(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p): return C(p).pct_change().rolling(20).std()*np.sqrt(252)
def relhigh(p,k=1.2): rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
def golden(p,L): c=C(p); o=pd.Series(0.0,index=p.index); o[sma(c,50)>sma(c,200)]=L; return o
def volguard(p,L,cap): b=golden(p,L); b[relhigh(p)&(b>cap)]=cap; return b
def hyst(p,w,L,b): c=C(p); s=sma(c,w); o=pd.Series(np.nan,index=p.index); o[c>s*(1+b)]=L; o[c<s*(1-b)]=0.0; return o.ffill().fillna(0.0)

CANDS={"SMA200 2x 3% band":lambda p: hyst(p,200,2,0.03),
       "Golden 2x vol-guard":lambda p: volguard(p,2,1)}

def stat(p,lev):
    res=E().run(p,lev,etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=(s.get("calmar") or 0),sharpe=s["sharpe"],
                tr=res.rebalance_count/yrs,avglev=float(lev.reindex(p.index).fillna(0).mean()),eq=res.equity)

for idx,label in [("^GSPC","S&P 500"),("^NDX","Nasdaq 100")]:
    print(f"\n{'='*96}\n{label}")
    for plbl,(a,b) in [("FULL 1990-2026",("1990-01-01",None)),("H1 1990-2008",("1990-01-01","2008-01-01")),("H2 2008-2026",("2008-01-01",None))]:
        p=prices(idx,a,b)
        print(f"  [{plbl}]   {'CAGR':>7}{'maxDD':>8}{'Calmar':>8}{'Sharpe':>8}{'tr/yr':>7}{'avgLev':>8}")
        for name,fn in CANDS.items():
            d=stat(p,fn(p)); print(f"    {name:22}{d['cagr']:6.1f}%{d['dd']:7.1f}%{d['cal']:8.2f}{d['sharpe']:8.2f}{d['tr']:7.1f}{d['avglev']:8.2f}")
    # worst 12-month rolling drawdown windows (full)
    p=prices(idx)
    for name,fn in CANDS.items():
        d=stat(p,fn(p)); eq=d["eq"]; ddser=eq/eq.cummax()-1
        trough=ddser.idxmin()
        print(f"    -> {name:22} worst DD {ddser.min()*100:5.1f}% troughing {trough.date()}")
