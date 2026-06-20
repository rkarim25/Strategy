"""Monte Carlo validation of the exploration winners (block-bootstrap, like the site's
existing MC). 150 synthetic 10-year paths of ^GSPC / ^NDX returns; for each path recompute
the strategy leverage and run the daily-reset engine (0.10% cost, $10/yr inflow). Reports
median CAGR / median maxDD / P(DD<-40%) so we see distributional robustness, not one path."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS, block_bootstrap_paths
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats

N_SIMS, HORIZON, BLOCK, SEED = 150, 2520, 21, 20260616
_C={}
def close(tk):
    if tk not in _C:
        s=yf.download(tk,period="max",auto_adjust=True,progress=False)["Close"].dropna().astype(float).squeeze(); s.index=s.index.tz_localize(None); _C[tk]=s
    return _C[tk]
def hist(idx):
    return pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna()
def panel(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),
        "ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=10.0)
def C(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p): return C(p).pct_change().rolling(20).std()*np.sqrt(252)
def relhigh(p,k=1.2): rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
def golden(p,f,s,L): c=C(p); o=pd.Series(0.0,index=p.index); o[sma(c,f)>sma(c,s)]=L; return o
def sma_cash(p,w,L): c=C(p); o=pd.Series(0.0,index=p.index); o[c>sma(c,w)]=L; return o
def hyst(p,w,L,b): c=C(p); s=sma(c,w); o=pd.Series(np.nan,index=p.index); o[c>s*(1+b)]=L; o[c<s*(1-b)]=0.0; return o.ffill().fillna(0.0)
def absmom(p,lb,L): c=C(p); o=pd.Series(0.0,index=p.index); o[c>c.shift(lb)]=L; return o
def monthlyize(raw): per=raw.index.to_period("M"); last=raw.groupby(per).last().shift(1); return pd.Series(per.map(last),index=raw.index).astype(float).fillna(0)
def volguard(p,f,s,L,cap): b=golden(p,f,s,L); b[relhigh(p)&(b>cap)]=cap; return b

STRATS={
 "Buy & hold 1x":lambda p:pd.Series(1.0,index=p.index),
 "SMA200 2x daily":lambda p:sma_cash(p,200,2),
 "Mom 12m 2x":lambda p:absmom(p,252,2),
 "SMA200 2x monthly":lambda p:monthlyize(sma_cash(p,200,2)),
 "SMA200 2x 3% band":lambda p:hyst(p,200,2,0.03),
 "Golden 50/200 2x":lambda p:golden(p,50,200,2),
 "Golden 2x volguard":lambda p:volguard(p,50,200,2,1),
 "Golden 3x volguard":lambda p:volguard(p,50,200,3,2)}

for idx,label in [("^GSPC","S&P 500"),("^NDX","Nasdaq 100")]:
    paths=block_bootstrap_paths(hist(idx),n_sims=N_SIMS,horizon_days=HORIZON,block_days=BLOCK,seed=SEED)
    print(f"\n{'='*92}\n{label}  Monte Carlo: {N_SIMS} block-bootstrap 10y paths\n"
          f"{'strategy':22}{'medCAGR':>9}{'medMaxDD':>10}{'P(DD<-40%)':>12}{'P(CAGR>med BH)':>16}")
    res={}
    for name,fn in STRATS.items():
        cs,dds=[],[]
        for pth in paths:
            lev=fn(pth); r=E().run(pth,lev,etp_returns=panel(pth)); s=comprehensive_stats(r.equity,r.daily_returns)
            cs.append(s["cagr"]); dds.append(s["max_drawdown"])
        res[name]=(np.array(cs),np.array(dds))
    bh_med=np.median(res["Buy & hold 1x"][0])
    for name in STRATS:
        cs,dds=res[name]
        print(f"{name:22}{np.median(cs)*100:8.1f}%{np.median(dds)*100:9.1f}%{(dds<=-0.40).mean()*100:11.0f}%{(cs>bh_med).mean()*100:15.0f}%")
