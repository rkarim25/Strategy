"""Compare synthetic L*index vs listed ETP returns for Guarded A5/B25."""

from __future__ import annotations

import sys

from data_manager import load_backtest_data
from engine import PortfolioEngine
from etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

DEFAULT = {
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}


def run(prices, *, etp: bool) -> dict:
    lev, _ = guarded_strategy_leverage(prices, **DEFAULT)
    eng = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )
    if etp:
        panel = build_etp_return_panel(prices, SPX_ETP)
        res = eng.run(prices, lev, etp_returns=panel)
        cov = etp_coverage_summary(panel)
    else:
        res = eng.run(prices, lev)
        cov = {}
    st = comprehensive_stats(res.equity, res.daily_returns)
    return {
        "cagr_pct": round(st["cagr"] * 100, 2),
        "sharpe": round(float(st["sharpe"]), 3),
        "max_dd_pct": round(st["max_drawdown"] * 100, 2),
        "end_$": round(float(res.equity.iloc[-1]), 2),
        **cov,
    }


def main() -> int:
    prices = load_backtest_data()
    syn = run(prices, etp=False)
    etp = run(prices, etp=True)
    print("Guarded A5/B25 X40/Y15 — S&P 500 (~30y)")
    print("Synthetic L*index - funding:")
    print(f"  CAGR {syn['cagr_pct']}%  Sharpe {syn['sharpe']}  MaxDD {syn['max_dd_pct']}%  End ${syn['end_$']:,.0f}")
    print("Listed ETP returns (XS2D/3USL/SPY splice):")
    print(
        f"  CAGR {etp['cagr_pct']}%  Sharpe {etp['sharpe']}  MaxDD {etp['max_dd_pct']}%  End ${etp['end_$']:,.0f}"
    )
    print(f"  Real ETP days: 2x {etp.get('pct_real_2x', 0)}%  3x {etp.get('pct_real_3x', 0)}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
