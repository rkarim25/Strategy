"""Guarded A5/B25 on PURE SYNTHETIC 2x/3x (no real ETPs), 30y, S&P + Nasdaq.
Decompose the change: vol-drag double-count fix x cost (1% -> 0.10%)."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS
from etp_leverage import TER_ANNUAL
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage

SPEC = dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15)

def cl(t):
    s = yf.download(t, start="1996-06-17", end="2026-06-16", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None); return s
IR = cl("^IRX")

def synth(prices, vol_drag: bool):
    r = prices["spx_close"].pct_change(); tb = prices["tbill_rate"]
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    def lev(L, tier):
        base = L*r - bor(L) - TER_ANNUAL[tier]/TRADING_DAYS
        if vol_drag:
            base = base - 0.5*L*(L-1.0)*r*r
        return base.fillna(0.0)
    return pd.DataFrame({"ret_0": tb/TRADING_DAYS, "ret_1": (r-TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
                         "ret_2": lev(2.0, 2), "ret_3": lev(3.0, 3)}, index=prices.index)

def run(prices, panel, cost):
    levg = guarded_strategy_leverage(prices, **SPEC)[0]
    e = PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False, trading_cost_pct=cost,
                        annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    r = e.run(prices, levg, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    return s["cagr"], s["max_drawdown"]

for label, tk in [("S&P 500", "^GSPC"), ("Nasdaq 100", "^NDX")]:
    p = pd.DataFrame({"spx_close": cl(tk), "tbill_rate": IR/100}).ffill().dropna()
    old_p, new_p = synth(p, vol_drag=True), synth(p, vol_drag=False)
    print(f"\n### {label}  Guarded A5/B25 on PURE SYNTHETIC, {p.index[0].date()}->{p.index[-1].date()}")
    cO, ddO = run(p, old_p, 0.01)     # OLD: vol-drag + 1% cost
    cV, ddV = run(p, new_p, 0.01)     # vol-drag fix only (still 1% cost)
    cN, ddN = run(p, new_p, 0.001)    # NEW: no vol-drag + 0.10% cost
    cVonly, _ = run(p, old_p, 0.001)  # cost fix only (still vol-drag)
    print(f"  OLD (vol-drag + 1% cost)         CAGR {cO*100:6.2f}%   maxDD {ddO*100:6.1f}%")
    print(f"   + vol-drag fix (still 1% cost)  CAGR {cV*100:6.2f}%   maxDD {ddV*100:6.1f}%   [drag effect {(cV-cO)*100:+.1f}pp]")
    print(f"   + cost fix (still vol-drag)     CAGR {cVonly*100:6.2f}%               [cost effect {(cVonly-cO)*100:+.1f}pp]")
    print(f"  NEW (no vol-drag + 0.10% cost)   CAGR {cN*100:6.2f}%   maxDD {ddN*100:6.1f}%   [total {(cN-cO)*100:+.1f}pp]")
