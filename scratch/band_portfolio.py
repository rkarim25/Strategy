"""Asset-matched family blend: S&P sleeves on the 3% band (low-turnover, wins where the tail
is thin), Nasdaq on the vol-guard (needs the vol cap for its fat dot-com tail). Gold picks its
own best signal from the data (higher Calmar, but veto any signal with maxDD worse than -65%).
Reports per-sleeve stats, blended family CAGR/DD/Calmar/Sharpe, and TOTAL trades/yr vs the
25/month (300/yr) cap. Compares asset-matched vs all-vol-guard vs all-golden blends.
Synthetic daily-reset model, 0.10% cost, signal lagged 1d, no inflows (clean per-GBP blend)."""
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
def prices(idx,start="1990-01-01"):
    p=pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); return p[p.index>=pd.Timestamp(start)]
def pan(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),"ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=0.0)
def C(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p): return C(p).pct_change().rolling(20).std()*np.sqrt(252)
def relhigh(p,k=1.2): rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
def golden(p,L): c=C(p); o=pd.Series(0.0,index=p.index); o[sma(c,50)>sma(c,200)]=L; return o
def volguard(p,L,cap): b=golden(p,L); b[relhigh(p)&(b>cap)]=cap; return b
def band(p,L=2,w=200,bw=0.03): c=C(p); s=sma(c,w); o=pd.Series(np.nan,index=p.index); o[c>s*(1+bw)]=L; o[c<s*(1-bw)]=0.0; return o.ffill().fillna(0.0)

def run(idx,fn,start="1990-01-01"):
    p=prices(idx,start); res=E().run(p,fn(p),etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    eq=res.equity/res.equity.iloc[0]
    return eq, dict(cagr=s["cagr"],dd=s["max_drawdown"],cal=s.get("calmar") or 0,vol=s["volatility"],tr=res.rebalance_count/yrs)

# ---- per-asset: band vs vol-guard, then pick best (max Calmar, veto maxDD < -65%) ----
print("="*100,"\nSIGNAL CHOICE PER ASSET (full history, 2x; veto any signal with maxDD worse than -65%):")
print(f"{'asset':10}{'signal':16}{'CAGR':>7}{'maxDD':>8}{'Calmar':>8}{'tr/yr':>7}   pick")
BEST={}
for idx,label,start in [("^GSPC","S&P 500","1990-01-01"),("^NDX","Nasdaq 100","1990-01-01"),("GC=F","Gold","2000-01-01")]:
    opts={"3% band":lambda p:band(p,2),"vol-guard":lambda p:volguard(p,2,1)}
    stats={n:run(idx,fn,start)[1] for n,fn in opts.items()}
    elig={n:s for n,s in stats.items() if s["dd"]>-0.65} or stats   # veto wipeout-risk; if none, fall back
    pick=max(elig,key=lambda n:elig[n]["cal"])
    BEST[idx]=opts[pick]
    for n,s in stats.items():
        mark=" <= PICK" if n==pick else ""
        print(f"{label:10}{n:16}{s['cagr']*100:6.1f}%{s['dd']*100:7.1f}%{s['cal']:8.2f}{s['tr']:7.1f}{mark}")

# ---- account template: (label, asset, signal_fn, current £) ----
def matched(idx): return BEST[idx]
TEMPLATES={
 "ASSET-MATCHED":[
   ("Saba Trading  S&P 2x band",        "^GSPC", matched("^GSPC"), 356307),
   ("Reza SIPP     Nasdaq 2x vol-guard","^NDX",  matched("^NDX"),  373255),
   ("Reza ISA      Nasdaq 3x vol-guard SAT","^NDX", lambda p: volguard(p,3,2), 114827),
   ("Saba ISA      Gold 2x (best)",     "GC=F",  matched("GC=F"),  129133),
   ("Liyana JISA   S&P 2x band",        "^GSPC", matched("^GSPC"),  72467),
   ("Nameer JISA   S&P 2x band",        "^GSPC", matched("^GSPC"),  49580)],
 "ALL VOL-GUARD":[
   ("Saba Trading  S&P 2x vol-guard",   "^GSPC", lambda p: volguard(p,2,1), 356307),
   ("Reza SIPP     Nasdaq 2x vol-guard","^NDX",  lambda p: volguard(p,2,1), 373255),
   ("Reza ISA      Nasdaq 3x vol-guard SAT","^NDX", lambda p: volguard(p,3,2), 114827),
   ("Saba ISA      Gold 2x vol-guard",  "GC=F",  lambda p: volguard(p,2,1), 129133),
   ("Liyana JISA   S&P 2x vol-guard",   "^GSPC", lambda p: volguard(p,2,1),  72467),
   ("Nameer JISA   S&P 2x vol-guard",   "^GSPC", lambda p: volguard(p,2,1),  49580)],
}

def blend(sleeves):
    eqs={}; W={}; tot_tr=0; rows=[]
    for lbl,idx,fn,w in sleeves:
        start="2000-01-01" if idx=="GC=F" else "1990-01-01"
        eq,m=run(idx,fn,start); eqs[lbl]=eq; W[lbl]=w; tot_tr+=m['tr']
        rows.append((lbl,m,w))
    ic=None
    for eq in eqs.values(): ic=eq.index if ic is None else ic.intersection(eq.index)
    Wtot=sum(W.values()); fam=sum((W[l]/Wtot)*eqs[l].reindex(ic).ffill() for l in eqs)
    fr=fam.pct_change().fillna(0); dd=(fam/fam.cummax()-1); yrs=(ic[-1]-ic[0]).days/365.25
    cagr=(fam.iloc[-1]/fam.iloc[0])**(1/yrs)-1; sharpe=np.sqrt(252)*fr.mean()/fr.std()
    return rows,dict(cagr=cagr,dd=dd.min(),cal=cagr/abs(dd.min()),sharpe=sharpe,tr=tot_tr,win=(ic[0].date(),ic[-1].date()))

for tname,sleeves in TEMPLATES.items():
    rows,b=blend(sleeves)
    print("\n"+"="*100,f"\n{tname} BLEND  (per-GBP, synthetic, 0.10% cost)")
    print(f"{'sleeve':40}{'CAGR':>7}{'maxDD':>8}{'Calmar':>7}{'tr/yr':>7}{'£':>11}")
    for lbl,m,w in rows:
        print(f"{lbl:40}{m['cagr']*100:6.1f}%{m['dd']*100:7.1f}%{m['cal']:7.2f}{m['tr']:7.1f}{w:11,}")
    print(f"  -> FAMILY {b['win'][0]}..{b['win'][1]}:  CAGR {b['cagr']*100:.1f}%   maxDD {b['dd']*100:.1f}%   "
          f"Calmar {b['cal']:.2f}   Sharpe {b['sharpe']:.2f}")
    print(f"  -> TOTAL trades/yr {b['tr']:.1f}  =  {b['tr']/12:.1f}/month   (cap = 25/month = 300/yr)")
