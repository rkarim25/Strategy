"""Decision-grade S&P 500 bake-off. CAGR-first (drawdown-tolerant), 1990-2026, synthetic
daily-reset, 0.10% cost, NO inflow (pure compounding). Three parts:
  1. Every strategy at 1x/2x/3x, signal on the 1x S&P, ranked by CAGR (+ ruin flag).
  2. Signal-basis test: signal on 1x S&P vs on the 2x/3x series itself (LQQ3-style).
  3. Robustness: CAGR of the top strategies in each half of history.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
SPEC = dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15)
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
def synthLx(p,L): return (1+pan(p)[f"ret_{L}"].fillna(0)).cumprod()
def rvol_of(c): return c.pct_change().rolling(20).std()*np.sqrt(252)
def relhigh(c,k=1.2): rv=rvol_of(c); th=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20); return (rv>th).fillna(False)
# leverage builders take the SIGNAL price series c and target leverage L
def bh(c,L): return pd.Series(float(L),index=c.index)
def sma_cash(c,w,L): o=pd.Series(0.0,index=c.index); o[c>sma(c,w)]=L; return o
def golden(c,L): o=pd.Series(0.0,index=c.index); o[sma(c,50)>sma(c,200)]=L; return o
def band(c,L,w=200,b=0.03): s=sma(c,w); o=pd.Series(np.nan,index=c.index); o[c>s*(1+b)]=L; o[c<s*(1-b)]=0.0; return o.ffill().fillna(0.0)
def monthlyize(raw): per=raw.index.to_period("M"); last=raw.groupby(per).last().shift(1); return pd.Series(per.map(last),index=raw.index).astype(float).fillna(0)
def mom(c,L,lb=252): o=pd.Series(0.0,index=c.index); o[c>c.shift(lb)]=L; return o
def volguard(c,L,cap): b=golden(c,L); b[relhigh(c)&(b>cap)]=cap; return b

def stat(p,lev):
    res=E().run(p,lev,etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=s.get("calmar") or 0,sharpe=s["sharpe"],
                tr=res.rebalance_count/yrs,grow=res.equity.iloc[-1]/res.equity.iloc[0])

p=prices(); c1=C(p)  # 1x signal series
yrs=(p.index[-1]-p.index[0]).days/365.25
# ---- Part 1: bake-off, signal on 1x S&P ----
ROWS=[("Buy & hold",bh,[1,2,3]),("SMA200/cash",lambda c,L:sma_cash(c,200,L),[1,2,3]),
      ("SMA20/cash",lambda c,L:sma_cash(c,20,L),[1,2,3]),("Golden 50/200",golden,[1,2,3]),
      ("SMA200 monthly",lambda c,L:monthlyize(sma_cash(c,200,L)),[2,3]),
      ("SMA200 3% band",band,[1,2,3]),("Mom 12m",mom,[2,3])]
rows=[]
for name,fn,levs in ROWS:
    for L in levs:
        d=stat(p,fn(c1,L)); rows.append((f"{name} {L}x",L,d))
for name,(L,cap) in [("Golden vol-guard 2x",(2,1)),("Golden vol-guard 3x",(3,2))]:
    d=stat(p,volguard(c1,L,cap)); rows.append((name,L,d))
gl=guarded_strategy_leverage(p,**SPEC)[0]; rows.append(("Guarded A5/B25 (tiered <=3x)",3,stat(p,gl)))

rows.sort(key=lambda r:-r[2]["cagr"])
print(f"\n{'='*100}\nPART 1 — S&P 500 bake-off, signal on 1x S&P  ({p.index[0].date()}..{p.index[-1].date()}, {yrs:.0f}y, no inflow, 0.10% cost)")
print(f"ranked by CAGR\n{'strategy':30}{'CAGR':>7}{'maxDD':>8}{'Calmar':>8}{'Sharpe':>7}{'tr/yr':>7}{'growth x':>10}  flag")
for name,L,d in rows:
    flag = "RUIN<-85%" if d["dd"]<-85 else ("deep<-70%" if d["dd"]<-70 else "")
    print(f"{name:30}{d['cagr']:6.1f}%{d['dd']:7.1f}%{d['cal']:8.2f}{d['sharpe']:7.2f}{d['tr']:7.1f}{d['grow']:9.1f}x  {flag}")

# ---- Part 2: signal basis (1x vs leveraged series) for the trend strategies ----
print(f"\n{'='*100}\nPART 2 — does signalling on the leveraged series help?  (signal on 1x S&P  vs  on the Lx series itself)")
print(f"{'strategy':22}{'lev':>4}{'signal on':>13}{'CAGR':>8}{'maxDD':>8}{'Calmar':>8}")
for label,fn in [("SMA200/cash",lambda c,L:sma_cash(c,200,L)),("Golden 50/200",golden),("SMA200 3% band",band)]:
    for L in [2,3]:
        a=stat(p,fn(c1,L)); b=stat(p,fn(synthLx(p,L),L))
        print(f"{label:22}{L:>3}x{'1x S&P':>13}{a['cagr']:7.1f}%{a['dd']:7.1f}%{a['cal']:8.2f}")
        print(f"{'':22}{'':>4}{f'{L}x series':>13}{b['cagr']:7.1f}%{b['dd']:7.1f}%{b['cal']:8.2f}")

# ---- Part 3: robustness of the CAGR leaders, by half ----
print(f"\n{'='*100}\nPART 3 — robustness: CAGR in each half (signal on 1x S&P)")
top=[name for name,_,_ in rows[:6]]
def mk(name):
    base=name.replace(" (tiered <=3x)","")
    if base.startswith("Guarded"): return guarded_strategy_leverage  # special
    L=int(base.strip()[-2]) if base.strip()[-1]=="x" else 1
    if base.startswith("Buy & hold"): return lambda c:bh(c,L)
    if base.startswith("SMA200 monthly"): return lambda c:monthlyize(sma_cash(c,200,L))
    if base.startswith("SMA200 3% band"): return lambda c:band(c,L)
    if base.startswith("SMA200"): return lambda c:sma_cash(c,200,L)
    if base.startswith("SMA20"): return lambda c:sma_cash(c,20,L)
    if base.startswith("Golden vol-guard"): return lambda c:volguard(c,L,L-1)
    if base.startswith("Golden"): return lambda c:golden(c,L)
    if base.startswith("Mom"): return lambda c:mom(c,L)
print(f"{'strategy':30}{'H1 90-08 CAGR':>16}{'H2 08-26 CAGR':>16}{'full CAGR':>12}")
for name,L,d in rows[:6]:
    f=mk(name)
    if f is guarded_strategy_leverage:
        h1=stat(prices(b="2008-01-01"),guarded_strategy_leverage(prices(b="2008-01-01"),**SPEC)[0])
        h2=stat(prices("2008-01-01"),guarded_strategy_leverage(prices("2008-01-01"),**SPEC)[0])
    else:
        p1=prices(b="2008-01-01"); p2=prices("2008-01-01")
        h1=stat(p1,f(C(p1))); h2=stat(p2,f(C(p2)))
    print(f"{name:30}{h1['cagr']:14.1f}% {h2['cagr']:14.1f}% {d['cagr']:10.1f}%")
