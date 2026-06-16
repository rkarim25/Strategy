"""Search for strategies that beat buy & hold 1x on CAGR or drawdown (30y synthetic, S&P + Nasdaq)."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats

def cl(t):
    s = yf.download(t, start="1990-01-01", end="2026-06-16", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None); return s
IR = cl("^IRX")

def synth(prices):
    r = prices["spx_close"].pct_change(); tb = prices["tbill_rate"]
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({"ret_0": tb/TRADING_DAYS, "ret_1": (r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
                         "ret_2": (2*r-bor(2)-TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
                         "ret_3": (3*r-bor(3)-TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0)}, index=prices.index)

def sma_cash(p, w, L):
    c = p["spx_close"]; sma = c.rolling(w, min_periods=w).mean()
    lev = pd.Series(0.0, index=p.index); lev[c > sma] = L; return lev

def vol_regime(p, w, maxL, vt):
    c = p["spx_close"]; sma = c.rolling(w, min_periods=w).mean(); above = (c > sma).fillna(False)
    rvol = c.pct_change().rolling(20).std()*np.sqrt(TRADING_DAYS)
    lev = pd.Series(0.0, index=p.index); lev[above] = 1.0; lev[above & (rvol < vt)] = maxL; return lev

def donchian(p, L, entry=60, exit=20):
    c = p["spx_close"]; hi = c.rolling(entry).max(); lo = c.rolling(exit).min()
    sig = pd.Series(np.nan, index=p.index); sig[c >= hi] = L; sig[c <= lo] = 0.0
    return sig.ffill().fillna(0.0)

def absmom(p, L, lb=252):
    c = p["spx_close"]; lev = pd.Series(0.0, index=p.index); lev[c > c.shift(lb)] = L; return lev

def run(p, panel, lev, floor):
    e = PortfolioEngine(max_drawdown_limit=(0.25 if floor else None), hard_drawdown_floor=floor,
                        trading_cost_pct=0.001, annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    r = e.run(p, lev, etp_returns=panel); s = comprehensive_stats(r.equity, r.daily_returns)
    return s["cagr"], s["max_drawdown"], s.get("calmar") or 0

CANDS = [
    ("Buy & hold 1x", lambda p: pd.Series(1.0, index=p.index), False),
    ("SMA200 1x/cash", lambda p: sma_cash(p,200,1), False),
    ("SMA200 2x/cash", lambda p: sma_cash(p,200,2), False),
    ("SMA200 3x/cash", lambda p: sma_cash(p,200,3), False),
    ("SMA100 2x/cash", lambda p: sma_cash(p,100,2), False),
    ("SMA200 2x +floor", lambda p: sma_cash(p,200,2), True),
    ("SMA200 3x +floor", lambda p: sma_cash(p,200,3), True),
    ("SMA200 2x volreg", lambda p: vol_regime(p,200,2,0.20), False),
    ("Guarded+ (200/2x/floor)", lambda p: vol_regime(p,200,2,0.20), True),
    ("SMA200 3x volreg +floor", lambda p: vol_regime(p,200,3,0.20), True),
    ("Donchian 2x", lambda p: donchian(p,2), False),
    ("Donchian 2x +floor", lambda p: donchian(p,2), True),
    ("12m abs-mom 2x", lambda p: absmom(p,2), False),
    ("12m abs-mom 2x +floor", lambda p: absmom(p,2), True),
]
for label, tk in [("S&P 500","^GSPC"), ("Nasdaq 100","^NDX")]:
    p = pd.DataFrame({"spx_close": cl(tk), "tbill_rate": IR/100}).ffill().dropna()
    panel = synth(p)
    bh = run(p, panel, pd.Series(1.0, index=p.index), False)
    print(f"\n### {label} 30y synthetic ({p.index[0].date()}..{p.index[-1].date()})  BH1x = {bh[0]*100:.1f}% / {bh[1]*100:.1f}%")
    print(f"{'strategy':26}{'CAGR':>8}{'maxDD':>9}{'Calmar':>8}  beats BH1x?")
    for name, fn, fl in CANDS:
        c, dd, cal = run(p, panel, fn(p), fl)
        beat = []
        if c > bh[0]: beat.append("CAGR")
        if dd > bh[1]: beat.append("DD")
        tag = "+".join(beat) if beat else "no"
        print(f"{name:26}{c*100:7.1f}%{dd*100:8.1f}%{cal:8.2f}  {tag}")
