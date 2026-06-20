"""Explore SPX/Nasdaq strategy variants to improve CAGR, drawdown, or turnover.

Same harness as build_summary_data.py: synthetic daily-reset panel (L*r - borrow - ter),
$100 start + $10/yr inflow, 0.10% realistic trading cost, signal lagged 1 day by the
engine (lookahead-free). 30-year synthetic history (^GSPC / ^NDX) — the longest, most
regime-rich test bed (dot-com, GFC, 2020, 2022).

Reports CAGR / maxDD / Calmar / Sharpe / trades-per-year for each candidate and flags
which beat the current production set on each axis.
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

LONG_CAP = pd.Timestamp("1990-01-01")
_C: dict[str, pd.Series] = {}
def close(tk):
    if tk not in _C:
        s = yf.download(tk, period="max", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
        s.index = s.index.tz_localize(None); _C[tk] = s
    return _C[tk]

def prices_from(idx_t, start):
    p = pd.DataFrame({"spx_close": close(idx_t), "tbill_rate": close("^IRX")/100.0}).sort_index().ffill().dropna()
    return p.loc[p.index >= start]

def synth_panel(prices):
    r = prices["spx_close"].astype(float).pct_change(); tb = prices["tbill_rate"].astype(float)
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0": tb/TRADING_DAYS,
        "ret_1": (r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
        "ret_2": (2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
        "ret_3": (3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0)}, index=prices.index)

def eng(cost, floor=False):
    return PortfolioEngine(max_drawdown_limit=(0.25 if floor else None), hard_drawdown_floor=floor,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)

# ---- leverage builders (target leverage series; 0 = cash) ----
def C(p): return p["spx_close"].astype(float)
def sma_cash(p, w, L):
    c=C(p); s=c.rolling(w, min_periods=w).mean(); lev=pd.Series(0.0,index=p.index); lev[c>s]=L; return lev
def golden(p, fast, slow, L):
    c=C(p); f=c.rolling(fast,min_periods=fast).mean(); s=c.rolling(slow,min_periods=slow).mean()
    lev=pd.Series(0.0,index=p.index); lev[f>s]=L; return lev
def absmom(p, lb, L):
    c=C(p); lev=pd.Series(0.0,index=p.index); lev[c>c.shift(lb)]=L; return lev
def dualmom(p, L):
    c=C(p); lev=pd.Series(0.0,index=p.index); lev[(c>c.shift(252))&(c>c.shift(126))]=L; return lev
def hysteresis(p, w, L, band):
    c=C(p); s=c.rolling(w,min_periods=w).mean(); lev=pd.Series(np.nan,index=p.index)
    lev[c>s*(1+band)]=L; lev[c<s*(1-band)]=0.0; return lev.ffill().fillna(0.0)
def realized_vol(p, w=20):
    return C(p).pct_change().rolling(w).std()*np.sqrt(TRADING_DAYS)
def voltarget(p, target, maxL, w=20):
    return (target/realized_vol(p, w)).clip(0, maxL).fillna(0.0)
def voltarget_banded(p, target, maxL, step=0.5, w=20):
    return ((voltarget(p, target, maxL, w)/step).round()*step)
def voltarget_trend(p, target, maxL, band_step=0.5):
    lev=voltarget_banded(p, target, maxL, band_step); c=C(p); s=c.rolling(200,min_periods=200).mean()
    lev[~(c>s).fillna(False)]=0.0; return lev
def monthlyize(raw):
    per=raw.index.to_period("M"); last=raw.groupby(per).last().shift(1)
    return pd.Series(per.map(last), index=raw.index).astype(float).fillna(0.0)
def guarded_plus(p, k=1.2):
    c=C(p); s=c.rolling(200,min_periods=200).mean(); above=(c>s).fillna(False)
    rv=realized_vol(p); thresh=(k*rv.rolling(252,min_periods=60).median()).fillna(0.20)
    lev=pd.Series(0.0,index=p.index); lev[above]=1.0; lev[above&(rv<thresh)]=2.0; return lev

def run(prices, panel, lev, years, floor=False):
    out={}
    for cost,tag in [(0.0,"g"),(0.001,"r")]:
        res=eng(cost,floor).run(prices, lev, etp_returns=panel)
        s=comprehensive_stats(res.equity, res.daily_returns)
        out[f"cagr_{tag}"]=s["cagr"]; out[f"dd_{tag}"]=s["max_drawdown"]
        if tag=="r":
            out.update(calmar=s.get("calmar") or 0, sharpe=s["sharpe"], vol=s["volatility"],
                       trades=round(res.rebalance_count/years,1), end=float(res.equity.iloc[-1]))
    return out

# name -> (builder, floor)
CANDS = {
    # --- current production set (baselines) ---
    "Buy & hold 1x":            (lambda p: pd.Series(1.0,index=p.index), False),
    "Buy & hold 2x":            (lambda p: pd.Series(2.0,index=p.index), False),
    "SMA200 2x/cash":           (lambda p: sma_cash(p,200,2), False),
    "Guarded+ (200/2x/floor)":  (lambda p: guarded_plus(p), True),
    "Mom 12m 2x/cash":          (lambda p: absmom(p,252,2), False),
    # --- CAGR-seeking candidates ---
    "SMA100 2x/cash":           (lambda p: sma_cash(p,100,2), False),
    "SMA50 2x/cash":            (lambda p: sma_cash(p,50,2), False),
    "Golden 50/200 2x":         (lambda p: golden(p,50,200,2), False),
    "Mom 6m 2x/cash":           (lambda p: absmom(p,126,2), False),
    "Mom 12m 3x/cash":          (lambda p: absmom(p,252,3), False),
    "Dual-mom 6+12m 2x":        (lambda p: dualmom(p,2), False),
    "Dual-mom 6+12m 3x":        (lambda p: dualmom(p,3), False),
    # --- drawdown-seeking candidates ---
    "VolTgt 15% max2":          (lambda p: voltarget(p,0.15,2.0), False),
    "VolTgt 20% max3":          (lambda p: voltarget(p,0.20,3.0), False),
    "VolTgt 15%+SMA200 max2":   (lambda p: voltarget_trend(p,0.15,2.0,0.5), False),
    "VolTgt 18%+SMA200 max3":   (lambda p: voltarget_trend(p,0.18,3.0,0.5), False),
    "VolTgt 15%+SMA200+floor":  (lambda p: voltarget_trend(p,0.15,2.0,0.5), True),
    "SMA200 2x +floor":         (lambda p: sma_cash(p,200,2), True),
    "Mom 12m 2x +floor":        (lambda p: absmom(p,252,2), True),
    # --- turnover-reducing candidates ---
    "SMA200 2x monthly":        (lambda p: monthlyize(sma_cash(p,200,2)), False),
    "SMA200 2x hyst +-2%":      (lambda p: hysteresis(p,200,2,0.02), False),
    "SMA200 2x hyst +-3%":      (lambda p: hysteresis(p,200,2,0.03), False),
    "Mom 12m 2x monthly":       (lambda p: monthlyize(absmom(p,252,2)), False),
    "Golden 50/200 2x monthly": (lambda p: monthlyize(golden(p,50,200,2)), False),
}

for label, idx in [("S&P 500","^GSPC"), ("Nasdaq 100","^NDX")]:
    p = prices_from(idx, max(close(idx).index[0], LONG_CAP))
    panel = synth_panel(p); yrs=(p.index[-1]-p.index[0]).days/365.25
    R = {name: run(p, panel, b(p), yrs, fl) for name,(b,fl) in CANDS.items()}
    bh = R["Buy & hold 1x"]; mom = R["Mom 12m 2x/cash"]; sma2 = R["SMA200 2x/cash"]
    print(f"\n{'='*108}\n{label}  synthetic {p.index[0].date()}..{p.index[-1].date()}  ({yrs:.1f}y)   "
          f"BH1x {bh['cagr_r']*100:.1f}%/{bh['dd_r']*100:.0f}%   Mom12m2x {mom['cagr_r']*100:.1f}%/{mom['dd_r']*100:.0f}%")
    print(f"{'strategy':26}{'CAGR':>7}{'maxDD':>8}{'Calmar':>7}{'Sharpe':>7}{'tr/yr':>7}{'end$':>8}   beats")
    for name,(b,fl) in CANDS.items():
        d=R[name]; beat=[]
        if d['cagr_r']>mom['cagr_r']+1e-4: beat.append("CAGR>Mom")
        if d['dd_r']>sma2['dd_r']+1e-4: beat.append("DD>SMA200")
        if d['calmar']>max(mom['calmar'],sma2['calmar'])+1e-2: beat.append("Calmar")
        if d['trades']<sma2['trades']-0.05 and d['cagr_r']>bh['cagr_r']: beat.append("fewer-trades")
        print(f"{name:26}{d['cagr_r']*100:6.1f}%{d['dd_r']*100:7.1f}%{d['calmar']:7.2f}{d['sharpe']:7.2f}"
              f"{d['trades']:7.1f}{d['end']:8.0f}   {','.join(beat)}")
