"""Can anything beat SMA200 3% band 3x (16.6% CAGR / -54% DD) on the S&P, CAGR-first?
Search families: (1) SMA window x band width, (2) EMA band, (3) asymmetric enter/exit band,
(4) faster crash re-entry, (5) 12m-momentum gate, (6) vol-tiering 3<->2x. All at 3x cap,
signal on 1x S&P, synthetic daily-reset, 0.10% cost, no inflow. OVERFIT GUARD: every leader
is re-checked in BOTH halves — only count a win if it beats the band in full AND both halves."""
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
def prices(a="1990-01-01",b=None):
    p=pd.DataFrame({"spx_close":close("^GSPC"),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); p=p[p.index>=pd.Timestamp(a)]
    return p[p.index<pd.Timestamp(b)] if b else p
def pan(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),"ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=0.0)
def C(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def ema(c,w): return c.ewm(span=w,min_periods=w).mean()
def rvol(c): return c.pct_change().rolling(20).std()*np.sqrt(252)
def stat(p,lev):
    res=E().run(p,lev,etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=s.get("calmar") or 0,tr=res.rebalance_count/yrs)

# ---- signal builders (all return a 0/L leverage series from signal price c) ----
def band(c,L,w=200,be=0.03,bx=None):  # asymmetric: enter > sma*(1+be), exit < sma*(1-bx)
    bx=be if bx is None else bx; s=sma(c,w); o=pd.Series(np.nan,index=c.index)
    o[c>s*(1+be)]=L; o[c<s*(1-bx)]=0.0; return o.ffill().fillna(0.0)
def eband(c,L,w=200,b=0.03): s=ema(c,w); o=pd.Series(np.nan,index=c.index); o[c>s*(1+b)]=L; o[c<s*(1-b)]=0.0; return o.ffill().fillna(0.0)
def band_momgate(c,L,w=200,b=0.03):
    base=band(c,L,w,b); base[~(c>c.shift(252)).fillna(False)]=0.0; return base
def band_voltier(c,w=200,b=0.03):
    base=band(c,3,w,b); rv=rvol(c); hi=(rv>rv.rolling(252,min_periods=60).median()).fillna(False)
    base[(base>0)&hi]=2.0; return base
def band_fastreentry(c,L,w=200,bx=0.03,refast=50):
    s=sma(c,w).values; sf=sma(c,refast).values; cv=c.values; out=np.zeros(len(cv)); st=0.0
    for i in range(len(cv)):
        if np.isnan(s[i]): out[i]=0.0; continue
        if st==0.0:
            if cv[i]>s[i] and (not np.isnan(sf[i]) and cv[i]>sf[i]): st=L  # re-enter on SMA reclaim + 50d support (no +b wait)
        else:
            if cv[i]<s[i]*(1-bx): st=0.0
        out[i]=st
    return pd.Series(out,index=c.index)

BENCH = ("SMA200 3% band 3x", lambda c: band(c,3,200,0.03))
p=prices(); c1=C(p)
b_full=stat(p,BENCH[1](c1))
print(f"BENCHMARK  {BENCH[0]}: CAGR {b_full['cagr']:.1f}%  DD {b_full['dd']:.1f}%  Calmar {b_full['cal']:.2f}\n")

cands=[]
# (1) SMA window x symmetric band, 3x
for w in [120,150,180,200,220,250,300]:
    for b in [0.0,0.02,0.03,0.04,0.05,0.06]:
        cands.append((f"SMA{w} {int(b*100)}% band 3x", lambda c,w=w,b=b: band(c,3,w,b)))
# (2) EMA band
for w in [100,150,200]:
    for b in [0.02,0.03,0.04]:
        cands.append((f"EMA{w} {int(b*100)}% band 3x", lambda c,w=w,b=b: eband(c,3,w,b)))
# (3) asymmetric band 3x
for be in [0.01,0.02,0.03]:
    for bx in [0.03,0.05,0.07,0.09]:
        cands.append((f"asym enter+{int(be*100)}/exit-{int(bx*100)} 3x", lambda c,be=be,bx=bx: band(c,3,200,be,bx)))
# (4-6) structural ideas
cands += [("band+12m mom gate 3x", lambda c: band_momgate(c,3,200,0.03)),
          ("band vol-tier 3/2x", lambda c: band_voltier(c,200,0.03)),
          ("band fast-reentry 3x", lambda c: band_fastreentry(c,3,200,0.03,50)),
          ("band fast-reentry wide-exit 3x", lambda c: band_fastreentry(c,3,200,0.05,50))]

res=[(n, stat(p,fn(c1))) for n,fn in cands]
res.sort(key=lambda x:-x[1]["cagr"])
print(f"{'='*92}\nTOP 12 by full-period CAGR (vs benchmark 16.6%):")
print(f"{'strategy':34}{'CAGR':>7}{'maxDD':>8}{'Calmar':>8}{'tr/yr':>7}")
for n,d in res[:12]:
    beat = "  <-- beats" if d["cagr"]>b_full["cagr"] else ""
    print(f"{n:34}{d['cagr']:6.1f}%{d['dd']:7.1f}%{d['cal']:8.2f}{d['tr']:7.1f}{beat}")

# ---- overfit guard: re-check the leaders + benchmark in BOTH halves ----
p1=prices(b="2008-01-01"); p2=prices("2008-01-01"); c1a=C(p1); c1b=C(p2)
fnmap={n:fn for n,fn in cands}; fnmap[BENCH[0]]=BENCH[1]
leaders=[BENCH[0]]+[n for n,_ in res[:6]]
seen=set(); leaders=[x for x in leaders if not (x in seen or seen.add(x))]
print(f"\n{'='*92}\nOVERFIT GUARD — CAGR / maxDD in each half (must beat benchmark in BOTH to count):")
print(f"{'strategy':34}{'H1 90-08':>16}{'H2 08-26':>16}{'full CAGR':>11}")
for n in leaders:
    fn=fnmap[n]; h1=stat(p1,fn(c1a)); h2=stat(p2,fn(c1b)); fu=stat(p,fn(c1))
    print(f"{n:34}{h1['cagr']:7.1f}%/{h1['dd']:5.0f}% {h2['cagr']:7.1f}%/{h2['dd']:5.0f}% {fu['cagr']:9.1f}%")
