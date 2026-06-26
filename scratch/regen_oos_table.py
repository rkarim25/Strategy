"""Recompute the index.html OOS forward-test rows with corrected same-calendar ETPs + 0.10% cost."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.engine import PortfolioEngine
from core.etp_leverage import SPX_ETP, build_etp_return_panel
from core.metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import sma_cash_leverage

A10B20 = dict(trigger_a=0.10, trigger_b=0.20, lead_pct_below_sma20=0.0, x_return=0.25, y_return=1/3)

def cl(t):
    s = yf.download(t, start="2005-06-01", end="2026-06-16", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None); return s

IDX, IR = cl("^GSPC"), cl("^IRX")

def slice_prices(start, end):
    p = pd.DataFrame({"spx_close": IDX, "tbill_rate": IR/100}).ffill().dropna()
    return p.loc[(p.index >= start) & (p.index <= end)]

def row(period, name, lev_fn, start, end):
    p = slice_prices(start, end)
    lev = lev_fn(p)
    panel = build_etp_return_panel(p, SPX_ETP)
    e = PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                        trading_cost_pct=0.001, annual_inflow_pct=0.0, annual_inflow_abs=10.0)
    r = e.run(p, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    print(f"{period:11} | {name:24} | CAGR {s['cagr']*100:6.2f}% | vol {s['volatility']*100:5.2f}% | "
          f"Sharpe {s['sharpe']:.3f} | maxDD {s['max_drawdown']*100:6.2f}% | end ${r.equity.iloc[-1]:,.0f} | trades {r.rebalance_count}")

g = lambda p: guarded_strategy_leverage(p, **A10B20)[0]
row("2006-2026", "Guarded A10/B20 SMA20", g, "2006-01-01", "2026-06-16")
row("2006-2026", "SMA20 3x/cash", lambda p: sma_cash_leverage(p, 20, 3.0), "2006-01-01", "2026-06-16")
row("2006-2026", "SMA20 2x/cash", lambda p: sma_cash_leverage(p, 20, 2.0), "2006-01-01", "2026-06-16")
row("2006-2015", "Guarded A10/B20 SMA20", g, "2006-01-01", "2015-12-31")
row("2016-2026", "Guarded A10/B20 SMA20", g, "2016-01-01", "2026-06-16")
