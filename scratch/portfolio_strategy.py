"""Constraint-aware family portfolio: per-account asset+signal sleeves, blended by current
weights. Reports family CAGR/DD/Calmar, total trades/yr vs the 25/month (300/yr) cap, and a
ruin stress-test on the 3x sleeve (worst DD, time underwater, Monte-Carlo wipeout prob).
Synthetic daily-reset model (no inflows -> clean per-GBP blend), 0.10% cost, signal lagged 1d."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS, block_bootstrap_paths
from core.etp_leverage import TER_ANNUAL
from core.metrics import comprehensive_stats

_C={}
def close(tk):
    if tk not in _C:
        s=yf.download(tk,period="max",auto_adjust=True,progress=False)["Close"].dropna().astype(float).squeeze(); s.index=s.index.tz_localize(None); _C[tk]=s
    return _C[tk]
def prices(idx,start="1990-01-01"):
    p=pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); return p[p.index>=pd.Timestamp(start)]
def pan(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),"ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=0.0)
def Cl(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p): return Cl(p).pct_change().rolling(20).std()*np.sqrt(252)
def relhigh(p,k=1.2): rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
def golden(p,L): c=Cl(p); o=pd.Series(0.0,index=p.index); o[sma(c,50)>sma(c,200)]=L; return o
def volguard(p,L,cap): b=golden(p,L); b[relhigh(p)&(b>cap)]=cap; return b
def buyhold(p,L): return pd.Series(float(L),index=p.index)

def sleeve(idx,lev_fn):
    p=prices(idx); res=E().run(p,lev_fn(p),etp_returns=pan(p))
    yrs=(p.index[-1]-p.index[0]).days/365.25
    eq=res.equity/res.equity.iloc[0]  # per-GBP growth
    s=comprehensive_stats(res.equity,res.daily_returns)
    return eq, dict(cagr=s["cagr"],dd=s["max_drawdown"],cal=s.get("calmar") or 0,vol=s["volatility"],tr=res.rebalance_count/yrs)

# --- TEMPLATE: account -> (asset, signal, current £) ; mirrored JISAs counted x trades ---
SLEEVES = [
 ("Saba Trading  S&P 2x golden",  "^GSPC", lambda p: golden(p,2),       356307, 1),
 ("Reza SIPP     Nasdaq 2x vguard","^NDX",  lambda p: volguard(p,2,1),   373255, 1),
 ("Reza ISA      Nasdaq 3x vguard SATELLITE","^NDX", lambda p: volguard(p,3,2), 114827, 1),
 ("Saba ISA      Gold 2x golden",  "GC=F",  lambda p: golden(p,2),       129133, 1),
 ("Liyana JISA   S&P 2x golden",   "^GSPC", lambda p: golden(p,2),        72467, 1),
 ("Nameer JISA   S&P 2x golden",   "^GSPC", lambda p: golden(p,2),        49580, 1),
]
print("="*100,"\nPER-SLEEVE (synthetic 1990-2026, daily-reset, 0.10% cost):")
print(f"{'sleeve':32}{'CAGR':>7}{'maxDD':>8}{'Calmar':>7}{'vol':>6}{'tr/yr':>7}{'£':>11}")
eqs={}; W={}; tot_tr=0; first=None
for lbl,idx,fn,w,mult in SLEEVES:
    eq,m=sleeve(idx,fn); eqs[lbl]=eq; W[lbl]=w
    tot_tr+=mult*m['tr']
    print(f"{lbl:32}{m['cagr']*100:6.1f}%{m['dd']*100:7.1f}%{m['cal']:7.2f}{m['vol']*100:5.0f}%{m['tr']:7.1f}{w:11,}")
# blend on common dates
idx_common=None
for eq in eqs.values(): idx_common = eq.index if idx_common is None else idx_common.intersection(eq.index)
Wtot=sum(W.values())
fam=sum((W[l]/Wtot)*eqs[l].reindex(idx_common).ffill() for l in eqs)
fr=fam.pct_change().fillna(0); peak=fam.cummax(); dd=(fam/peak-1)
yrs=(idx_common[-1]-idx_common[0]).days/365.25
cagr=(fam.iloc[-1]/fam.iloc[0])**(1/yrs)-1
sharpe=np.sqrt(252)*fr.mean()/fr.std()
print("\n"+"="*100)
print(f"BLENDED EQUITY-SYSTEMATIC PORTFOLIO  ({idx_common[0].date()}..{idx_common[-1].date()}, weight £{Wtot:,})")
print(f"  CAGR {cagr*100:.1f}%   maxDD {dd.min()*100:.1f}%   Calmar {cagr/abs(dd.min()):.2f}   Sharpe {sharpe:.2f}")
print(f"  TOTAL trades/yr {tot_tr:.1f}  ->  {tot_tr/12:.1f}/month   (cap = 25/month = 300/yr)")

# --- 3x sleeve ruin stress test ---
print("\n"+"="*100,"\n3x SLEEVE RUIN STRESS-TEST (Nasdaq 3x vol-guard):")
p=prices("^NDX"); eq,m=sleeve("^NDX",lambda p: volguard(p,3,2))
under=(eq<eq.cummax()).astype(int);
# longest underwater stretch (trading days)
mx=cur=0
for u in under:
    cur=cur+1 if u else 0; mx=max(mx,cur)
print(f"  Historical (1990-2026): CAGR {m['cagr']*100:.1f}%  worst DD {m['dd']*100:.1f}%  longest underwater {mx/252:.1f}y  min equity {eq.min()/eq.cummax().loc[eq.idxmin()]*100:.0f}% of peak")
paths=block_bootstrap_paths(prices("^NDX"),n_sims=300,horizon_days=2520,block_days=21,seed=20260616)
dds=[]; ends=[]
for pth in paths:
    r=E().run(pth,volguard(pth,3,2),etp_returns=pan(pth)); s=comprehensive_stats(r.equity,r.daily_returns)
    dds.append(s["max_drawdown"]); ends.append(r.equity.iloc[-1]/r.equity.iloc[0])
dds=np.array(dds); ends=np.array(ends)
print(f"  Monte Carlo (300 x 10y): median DD {np.median(dds)*100:.0f}%  worst DD {dds.min()*100:.0f}%  "
      f"P(DD<-80%) {(dds<-0.80).mean()*100:.0f}%  P(near-wipe DD<-95%) {(dds<-0.95).mean()*100:.0f}%  P(end<0.5x) {(ends<0.5).mean()*100:.0f}%")
