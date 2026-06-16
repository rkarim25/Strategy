"""Isolate why the 30y Guarded numbers changed: calendar (XS2D->SSO) vs cost vs base-rule."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine
from etp_leverage import EtpBundle, build_etp_return_panel
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import sma_cash_leverage

SPEC = dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15)
XS2D = EtpBundle("SPX-UCITS", "SPY", "XS2D.L", "3USL.L")   # UK/Paris listed (old, calendar-offset)
SSO = EtpBundle("SPX-US", "SPY", "SSO", "UPRO")             # US listed (same calendar as ^GSPC)

def cl(t, start):
    s = yf.download(t, start=start, end="2026-06-16", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None); return s

def prices(start):
    idx, ir = cl("^GSPC", start), cl("^IRX", start)
    return pd.DataFrame({"spx_close": idx, "tbill_rate": ir/100}).ffill().dropna()

def run(p, lev, bundle, cost):
    panel = build_etp_return_panel(p, bundle)
    e = PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                        trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    r = e.run(p, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    eq = r.equity; dd = (eq - eq.cummax()) / eq.cummax()
    return s["cagr"], s["max_drawdown"], dd.idxmin().date()

print("### FULL 30y (1996-2026): Guarded A5/B25 — pre-inception synthetic + real after")
p30 = prices("1996-06-17"); levg = guarded_strategy_leverage(p30, **SPEC)[0]
for label, b in [("XS2D/3USL (UK, OLD)", XS2D), ("SSO/UPRO (US, FIXED)", SSO)]:
    for cost in (0.01, 0.001):
        c, dd, dt = run(p30, levg, b, cost)
        print(f"  {label:22} cost {cost*100:>4.1f}%:  CAGR {c*100:6.1f}%   maxDD {dd*100:6.1f}%   (trough {dt})")

print("\n### OVERLAP 2012-2026 (BOTH ETPs real) — isolates the calendar effect alone")
p12 = prices("2012-12-13"); levg12 = guarded_strategy_leverage(p12, **SPEC)[0]
for label, b in [("XS2D/3USL (UK, OLD)", XS2D), ("SSO/UPRO (US, FIXED)", SSO)]:
    c, dd, dt = run(p12, levg12, b, 0.001)
    print(f"  {label:22} cost 0.1%:  CAGR {c*100:6.1f}%   maxDD {dd*100:6.1f}%")

print("\n### Drawdown source — base SMA20 rule vs the leverage tiers (SSO, 0.10%, 30y)")
for name, lev in [("SMA20 1x/cash (base exit rule)", sma_cash_leverage(p30, 20, 1.0)),
                  ("SMA20 2x/cash", sma_cash_leverage(p30, 20, 2.0)),
                  ("SMA20 3x/cash", sma_cash_leverage(p30, 20, 3.0)),
                  ("Guarded A5/B25 (dynamic 1x/2x/3x)", levg)]:
    c, dd, dt = run(p30, lev, SSO, 0.001)
    print(f"  {name:34} CAGR {c*100:6.1f}%   maxDD {dd*100:6.1f}%   (trough {dt})")
