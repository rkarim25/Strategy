"""Is it worth adding FTSE 250 / DAX / MSCI EM / MSCI World to the family (S&P+Nasdaq+Gold)?
(A) Standalone golden-2x-volguard CAGR/DD/Calmar per asset (own history + common window).
(B) WEEKLY-return correlation to S&P (weekly avoids US-vs-Europe calendar/timezone noise).
(C) Diversification test: does swapping 15% of the US+gold core into an international basket
    improve family Calmar/drawdown, or just dilute return? Synthetic daily-reset, 0.10% cost.
Note: ^GDAXI is a TOTAL-RETURN index (flatters DAX vs price-return ^FTMC) -> flagged, not mixed
into the blend on equal footing."""
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
def prices(tk,start="1990-01-01"):
    p=pd.DataFrame({"spx_close":close(tk),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); return p[p.index>=pd.Timestamp(start)]
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

ASSETS=[("S&P 500","^GSPC"),("Nasdaq 100","^NDX"),("Gold","GC=F"),
        ("FTSE 250","^FTMC"),("DAX (TR!)","^GDAXI"),("MSCI EM","EEM"),("MSCI World","URTH")]

def sleeve(tk):
    p=prices(tk); res=E().run(p,volguard(p,2,1),etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    eq=res.equity/res.equity.iloc[0]
    return eq, dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=s.get("calmar") or 0,
                    tr=res.rebalance_count/yrs,start=p.index[0].date())

print("="*92,"\n(A) STANDALONE  Golden 2x vol-guard, synthetic daily-reset, 0.10% cost (own full history):")
print(f"{'asset':14}{'from':>12}{'CAGR':>8}{'maxDD':>8}{'Calmar':>8}{'tr/yr':>7}")
EQ={}
for lbl,tk in ASSETS:
    eq,m=sleeve(tk); EQ[lbl]=eq
    print(f"{lbl:14}{str(m['start']):>12}{m['cagr']:7.1f}%{m['dd']:7.1f}%{m['cal']:8.2f}{m['tr']:7.1f}")

# (B) weekly-return correlation to S&P (raw index, buy&hold, weekly to dodge calendar offset)
print("\n"+"="*92,"\n(B) WEEKLY buy&hold return correlation (2004+, common window):")
wk={lbl:close(tk).resample("W-FRI").last().pct_change() for lbl,tk in ASSETS}
W=pd.DataFrame(wk).loc["2004-01-01":].dropna()
corr=W.corr()["S&P 500"].sort_values(ascending=False)
for lbl in corr.index: print(f"   {lbl:14} corr vs S&P 500 = {corr[lbl]:+.2f}")

# (C) diversification blend test -- ALL blends forced onto the SAME window (else the window
#     difference, not the asset mix, drives the result). FAIR control: same 15% into more gold.
print("\n"+"="*92,"\n(C) DIVERSIFICATION TEST  (per-GBP golden-2x-vguard sleeves, IDENTICAL window):")
FORCE="2003-04-14"  # EEM inception -> the binding common start for any blend with MSCI EM
def blend(weights,start=FORCE):
    ic=None
    for l in weights: e=EQ[l][EQ[l].index>=pd.Timestamp(start)]; ic=e.index if ic is None else ic.intersection(e.index)
    fam=sum(w*EQ[l].reindex(ic).ffill() for l,w in weights.items()); fam=fam/fam.iloc[0]
    dd=(fam/fam.cummax()-1); yrs=(ic[-1]-ic[0]).days/365.25
    cagr=(fam.iloc[-1]/fam.iloc[0])**(1/yrs)-1
    return dict(cagr=cagr*100,dd=dd.min()*100,cal=cagr/abs(dd.min()),win=(ic[0].date(),ic[-1].date()))
CORE={"S&P 500":0.50,"Nasdaq 100":0.30,"Gold":0.20}
INTL={"S&P 500":0.40,"Nasdaq 100":0.25,"Gold":0.20,"FTSE 250":0.05,"DAX (TR!)":0.05,"MSCI EM":0.05}
MOREGOLD={"S&P 500":0.40,"Nasdaq 100":0.25,"Gold":0.35}
for name,wts in [("CORE   (50 S&P / 30 NDX / 20 Gold)",CORE),
                 ("+INTL  (15% -> FTSE250/DAX/EM)",INTL),
                 ("+GOLD  (same 15% -> more gold)",MOREGOLD)]:
    b=blend(wts); print(f"   {name:38} CAGR {b['cagr']:5.1f}%  maxDD {b['dd']:6.1f}%  Calmar {b['cal']:.2f}   [{b['win'][0]}..{b['win'][1]}]")
