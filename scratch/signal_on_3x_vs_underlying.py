"""Does computing the entry/exit signal on the 3x series itself (LQQ3-style) beat computing it
on the 1x Nasdaq (summary-style)? Isolation test: BOTH earn the identical synthetic-3x daily
return when 'in'; only the SIGNAL series differs. Strategies: SMA20/cash, SMA200/cash, Golden
50/200 -- each either 3x or cash. Synthetic daily-reset, 0.10% cost, signal lagged 1d, 1990-2026."""
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
def prices(tk="^NDX",start="1990-01-01"):
    p=pd.DataFrame({"spx_close":close(tk),"tbill_rate":close("^IRX")/100}).sort_index().ffill().dropna(); return p[p.index>=pd.Timestamp(start)]
def pan(p):
    r=p["spx_close"].pct_change(); tb=p["tbill_rate"]
    def bor(L): return (L-1)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0":tb/TRADING_DAYS,"ret_1":(r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0),
        "ret_2":(2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0),"ret_3":(3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0)},index=p.index)
def E(): return PortfolioEngine(max_drawdown_limit=None,hard_drawdown_floor=False,trading_cost_pct=0.001,annual_inflow_pct=0,annual_inflow_abs=0.0)

def synth3x_price(p):
    # the SAME 3x daily-reset series the strategy is invested in, compounded to a price level
    return (1+pan(p)["ret_3"].fillna(0)).cumprod()

def sma(c,w): return c.rolling(w,min_periods=w).mean()
# signal builders: each returns a 3x-or-cash leverage series from a chosen SIGNAL price series
def sig_sma_cash(c,w): o=pd.Series(0.0,index=c.index); o[c>sma(c,w)]=3.0; return o
def sig_golden(c,f=50,s=200): o=pd.Series(0.0,index=c.index); o[sma(c,f)>sma(c,s)]=3.0; return o

def stat(p,lev):
    res=E().run(p,lev,etp_returns=pan(p)); s=comprehensive_stats(res.equity,res.daily_returns)
    yrs=(p.index[-1]-p.index[0]).days/365.25
    return dict(cagr=s["cagr"]*100,dd=s["max_drawdown"]*100,cal=s.get("calmar") or 0,
                tr=res.rebalance_count/yrs,cash=float((lev.reindex(p.index).fillna(0)<=0).mean()*100))

p=prices("^NDX","1990-01-01")
ndx=p["spx_close"].astype(float)          # 1x Nasdaq  -> approach A signal
s3=synth3x_price(p)                        # synthetic 3x -> approach B signal

STRATS=[("SMA20 / cash  @3x", lambda c: sig_sma_cash(c,20)),
        ("SMA200 / cash @3x", lambda c: sig_sma_cash(c,200)),
        ("Golden 50/200 @3x", lambda c: sig_golden(c))]

print("="*96,"\nNasdaq 3x strategies: SIGNAL ON 1x NDX (A, summary-style) vs SIGNAL ON 3x SERIES (B, LQQ3-style)")
print(f"   (identical 3x return earned when in; 1990-{p.index[-1].year}, 0.10% cost)\n")
print(f"{'strategy':20}{'signal on':14}{'CAGR':>8}{'maxDD':>8}{'Calmar':>8}{'tr/yr':>7}{'%cash':>7}")
for name,fn in STRATS:
    a=stat(p,fn(ndx)); b=stat(p,fn(s3))
    print(f"{name:20}{'1x NDX (A)':14}{a['cagr']:7.1f}%{a['dd']:7.1f}%{a['cal']:8.2f}{a['tr']:7.1f}{a['cash']:6.0f}%")
    print(f"{'':20}{'3x series (B)':14}{b['cagr']:7.1f}%{b['dd']:7.1f}%{b['cal']:8.2f}{b['tr']:7.1f}{b['cash']:6.0f}%")
    d_cagr=b['cagr']-a['cagr']; d_dd=b['dd']-a['dd']
    print(f"{'':20}{'-> B minus A':14}{d_cagr:+7.1f}%{d_dd:+7.1f}%{'(better DD if +)' if d_dd>0 else '(worse DD)':>23}\n")
