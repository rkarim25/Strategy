"""Phase-A exploration program (drawdown overlays, 3x variants, rebalance/MA/band sweeps)
for SPX & Nasdaq. Same harness as build_summary_data.py (synthetic daily-reset, 0.10%
cost, $10/yr inflow, engine lags signal 1 day). Reports full 30y + both halves; flags
candidates that beat the current production winners on CAGR / drawdown / Calmar / turnover
*and* hold up in BOTH sub-periods."""
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
        s=yf.download(tk,period="max",auto_adjust=True,progress=False)["Close"].dropna().astype(float).squeeze()
        s.index=s.index.tz_localize(None); _C[tk]=s
    return _C[tk]
def prices(idx,start,end=None):
    p=pd.DataFrame({"spx_close":close(idx),"tbill_rate":close("^IRX")/100.0}).sort_index().ffill().dropna()
    p=p.loc[p.index>=start]
    return p.loc[p.index<end] if end else p
def panel(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
        "ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0)},index=p.index)
def eng(floor=False): return PortfolioEngine(max_drawdown_limit=(0.25 if floor else None),
    hard_drawdown_floor=floor, trading_cost_pct=0.001, annual_inflow_pct=0.0, annual_inflow_abs=10.0)

def C(p): return p["spx_close"].astype(float)
def sma(c,w): return c.rolling(w,min_periods=w).mean()
def rvol(p,w=20): return C(p).pct_change().rolling(w).std()*np.sqrt(252)
def golden(p,f,s,L): c=C(p); out=pd.Series(0.0,index=p.index); out[sma(c,f)>sma(c,s)]=L; return out
def sma_cash(p,w,L): c=C(p); out=pd.Series(0.0,index=p.index); out[c>sma(c,w)]=L; return out
def hyst(p,w,L,band): c=C(p); s=sma(c,w); out=pd.Series(np.nan,index=p.index); out[c>s*(1+band)]=L; out[c<s*(1-band)]=0.0; return out.ffill().fillna(0.0)
def absmom(p,lb,L): c=C(p); out=pd.Series(0.0,index=p.index); out[c>c.shift(lb)]=L; return out
def monthlyize(raw): per=raw.index.to_period("M"); last=raw.groupby(per).last().shift(1); return pd.Series(per.map(last),index=raw.index).astype(float).fillna(0.0)
def every_n(raw,n,off=0): keep=np.zeros(len(raw),bool); keep[off::n]=True; return raw.where(pd.Series(keep,index=raw.index)).ffill().fillna(0.0)
# overlays
def volcap(base,p,vt,capL=1.0): out=base.copy(); hi=(rvol(p)>vt).fillna(False); out[hi&(out>capL)]=capL; return out
def relvolcap(base,p,k=1.2,capL=1.0):
    rv=rvol(p); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); out=base.copy(); hi=(rv>th).fillna(False); out[hi&(out>capL)]=capL; return out
def crashexit(base,p,lb=10,drop=-0.12): c=C(p); out=base.copy(); out[c.pct_change(lb)<drop]=0.0; return out

def stat(p,pan,lev,floor=False):
    res=eng(floor).run(p,lev,etp_returns=pan); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return dict(cagr=s["cagr"]*100, dd=s["max_drawdown"]*100, cal=(s.get("calmar") or 0), tr=round(res.rebalance_count/yrs,1))

CANDS = {
  # current production winners (bars to beat)
  "Golden 50/200 2x":        (lambda p: golden(p,50,200,2), False),
  "SMA200 2x monthly":       (lambda p: monthlyize(sma_cash(p,200,2)), False),
  "SMA200 2x 3% band":       (lambda p: hyst(p,200,2,0.03), False),
  "Mom 12m 2x/cash":         (lambda p: absmom(p,252,2), False),
  # 1) drawdown overlays on the slow trend
  "Golden 2x +relvolcap":    (lambda p: relvolcap(golden(p,50,200,2),p), False),
  "Golden 2x +volcap25":     (lambda p: volcap(golden(p,50,200,2),p,0.25), False),
  "Golden 2x +floor":        (lambda p: golden(p,50,200,2), True),
  "Monthly 2x +floor":       (lambda p: monthlyize(sma_cash(p,200,2)), True),
  "Golden 2x +crashexit":    (lambda p: crashexit(golden(p,50,200,2),p), False),
  "Golden 2x +relvolcap+fl": (lambda p: relvolcap(golden(p,50,200,2),p), True),
  "3%band 2x +relvolcap":    (lambda p: relvolcap(hyst(p,200,2,0.03),p), False),
  # 3) 3x variants of the slow trend
  "Golden 50/200 3x":        (lambda p: golden(p,50,200,3), False),
  "SMA200 3x monthly":       (lambda p: monthlyize(sma_cash(p,200,3)), False),
  "Golden 3x +floor":        (lambda p: golden(p,50,200,3), True),
  "Golden 3x +relvolcap":    (lambda p: relvolcap(golden(p,50,200,3),p,capL=2.0), False),
  "Golden 3x +relvolcap+fl": (lambda p: relvolcap(golden(p,50,200,3),p,capL=2.0), True),
  # 4) sweeps — rebalance frequency
  "SMA200 2x weekly":        (lambda p: every_n(sma_cash(p,200,2),5), False),
  "SMA200 2x biweekly":      (lambda p: every_n(sma_cash(p,200,2),10), False),
  "SMA200 2x quarterly":     (lambda p: every_n(sma_cash(p,200,2),63), False),
  # 4) sweeps — MA pairs
  "Golden 20/100 2x":        (lambda p: golden(p,20,100,2), False),
  "Golden 50/150 2x":        (lambda p: golden(p,50,150,2), False),
  "Golden 100/200 2x":       (lambda p: golden(p,100,200,2), False),
  "Golden 20/200 2x":        (lambda p: golden(p,20,200,2), False),
  # 4) sweeps — band width
  "SMA200 2x 2% band":       (lambda p: hyst(p,200,2,0.02), False),
  "SMA200 2x 4% band":       (lambda p: hyst(p,200,2,0.04), False),
  "SMA200 2x 5% band":       (lambda p: hyst(p,200,2,0.05), False),
}

for idx,label in [("^GSPC","S&P 500"),("^NDX","Nasdaq 100")]:
    per={lab:(prices(idx,a,b),) for lab,(a,b) in
         [("FULL",("1990-01-01",None)),("H1",("1990-01-01","2008-01-01")),("H2",("2008-01-01",None))]}
    pans={lab:panel(p[0]) for lab,p in per.items()}
    R={name:{lab:stat(per[lab][0],pans[lab],b(per[lab][0]),fl) for lab in per} for name,(b,fl) in CANDS.items()}
    # bars to beat = best of the current production winners on full period
    cur=["Golden 50/200 2x","SMA200 2x monthly","SMA200 2x 3% band","Mom 12m 2x/cash"]
    barC=max(R[s]["FULL"]["cagr"] for s in cur); barDD=max(R[s]["FULL"]["dd"] for s in cur)
    barCal=max(R[s]["FULL"]["cal"] for s in cur); barTr=min(R[s]["FULL"]["tr"] for s in cur)
    print(f"\n{'='*120}\n{label}  (bars to beat: CAGR>{barC:.1f}%  DD>{barDD:.1f}%  Calmar>{barCal:.2f}  trades<{barTr})")
    print(f"{'strategy':26}{'CAGR':>6}{'maxDD':>8}{'Calmar':>7}{'tr/yr':>6}   {'H1 cagr/dd':>14}{'H2 cagr/dd':>16}   winner")
    for name,(b,fl) in CANDS.items():
        f=R[name]["FULL"]; h1=R[name]["H1"]; h2=R[name]["H2"]; w=[]
        if f["cagr"]>barC+0.3 and min(h1["cagr"],h2["cagr"])>0: w.append("CAGR")
        if f["dd"]>barDD+1 and min(h1["dd"],h2["dd"])>barDD-3: w.append("DD")
        if f["cal"]>barCal+0.02 and min(h1["cal"],h2["cal"])>barCal*0.7: w.append("Calmar")
        if f["tr"]<barTr-0.05 and f["cagr"]>barC-2: w.append("fewer-trades")
        print(f"{name:26}{f['cagr']:5.1f}%{f['dd']:7.1f}%{f['cal']:7.2f}{f['tr']:6.1f}   "
              f"{h1['cagr']:5.1f}%/{h1['dd']:5.0f}%{h2['cagr']:7.1f}%/{h2['dd']:5.0f}%   {'+'.join(w)}")
