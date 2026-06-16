"""Decompose: how much of the real-ETP-window SMA20 result is trading cost vs regime."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine  # noqa: E402
from etp_leverage import NDX_ETP, SPX_ETP, build_etp_return_panel, etp_coverage_summary  # noqa: E402
from metrics import comprehensive_stats  # noqa: E402
from test_guarded_balanced_candidate import guarded_strategy_leverage  # noqa: E402
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage  # noqa: E402

sys.path.insert(0, str(ROOT / "scratch"))
from backtest_sma20_real_etp_2x import load_prices, DEFAULT_SPEC  # noqa: E402

def eng(cost):
    return PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)

def stat(prices, lev, panel, cost):
    r = eng(cost).run(prices, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    return s["cagr"], s["max_drawdown"], s["volatility"], float(r.equity.iloc[-1]), r.rebalance_count

for label, idx, bundle in [("SPX", "^GSPC", SPX_ETP), ("NDX", "^NDX", NDX_ETP)]:
    prices, start = load_prices(idx, bundle.etf_2x)
    panel = build_etp_return_panel(prices, bundle)
    lev_ng = sma_cash_leverage(prices, BASE_SMA_WINDOW, 2.0)
    lev_g = guarded_strategy_leverage(prices, **DEFAULT_SPEC)[0].clip(upper=2.0)
    print(f"\n=== {label}  {prices.index[0].date()}->{prices.index[-1].date()}  "
          f"real2x {etp_coverage_summary(panel)['pct_real_2x']}% ===")
    print(f"{'strategy':<22}{'cost':>7}{'CAGR':>9}{'maxDD':>9}{'vol':>8}{'end$':>11}{'reb':>6}")
    for name, lev in [("SMA20 non-guarded", lev_ng), ("SMA20 guarded(2x)", lev_g)]:
        for cost in [0.0, 0.0005, 0.001, 0.002, 0.005, 0.01]:
            c, dd, v, e, n = stat(prices, lev, panel, cost)
            print(f"{name:<22}{cost*100:>6.2f}%{c*100:>8.2f}%{dd*100:>8.1f}%{v*100:>7.1f}%{e:>11,.0f}{n:>6}")
