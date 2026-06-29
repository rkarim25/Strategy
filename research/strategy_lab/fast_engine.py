"""Fast numpy replica of core.engine.PortfolioEngine for the config used by the
SPX sweeps: max_drawdown_limit=None, hard_drawdown_floor=False, no dd-pause,
annual_inflow_abs=10.0, trading_cost_pct=0.001, signal_delay_days=1.

Validated to reproduce backtest_spx_distance_scale.run_strategy / buy_hold_row
to ~1e-6. Lets us screen thousands of strategies in seconds with no model risk.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from core.metrics import comprehensive_stats

INITIAL_CAPITAL = 100.0
ANNUAL_INFLOW_ABS = 10.0
TRADING_COST = 0.001


def fast_metrics(prices, applied_lev, ret_in, ret_cash, avg_tbill):
    """applied_lev: numpy array of the TARGET leverage per day (0 or L), NOT yet shifted.
    ret_in: daily return when invested (idx_ret for 1x non-etp, ret_2/ret_3 for etp).
    ret_cash: daily return when in cash (tbill/252).
    Returns (stats_dict, extra) replicating the engine exactly.
    """
    n = len(applied_lev)
    spx_ret = prices["spx_close"].pct_change().to_numpy(dtype=float)
    years = np.array([dt.year for dt in prices.index])

    # signal_delay_days=1: shift target leverage forward 1 day, fill 0.
    app = np.empty(n)
    app[0] = 0.0
    app[1:] = applied_lev[:-1]

    equity = np.empty(n)
    port = np.zeros(n)
    aum = INITIAL_CAPITAL
    peak = aum
    prev_lev = 1.0
    prev_year = None
    tc = 0.0
    rebal = 0
    for i in range(n):
        yr = years[i]
        if prev_year is not None and yr != prev_year:
            aum += ANNUAL_INFLOW_ABS
            if aum > peak:
                peak = aum
        lev = app[i]
        if abs(lev - prev_lev) > 1e-9:
            traded = abs(lev - prev_lev) * aum
            cost = traded * TRADING_COST
            aum -= cost
            tc += cost
            rebal += 1
            prev_lev = lev
        if i > 0 and not np.isnan(spx_ret[i]):
            r = ret_cash[i] if lev <= 0.0 else ret_in[i]
            aum *= 1.0 + r
            port[i] = r
        if aum > peak:
            peak = aum
        equity[i] = aum
        prev_year = yr

    eq = pd.Series(equity, index=prices.index)
    pr = pd.Series(port, index=prices.index)
    stats = comprehensive_stats(eq, pr, risk_free=avg_tbill)
    pct_cash = float((app <= 0.0).mean() * 100.0)
    avg_lev = float(app[app > 0.0].mean()) if (app > 0.0).any() else 0.0
    years_total = (prices.index[-1] - prices.index[0]).days / 365.25
    extra = {
        "end_$": float(equity[-1]),
        "rebalances": rebal,
        "total_trades": rebal,
        "trades_per_year": rebal / years_total if years_total > 0 else 0.0,
        "pct_days_cash": pct_cash,
        "avg_leverage": avg_lev,
        "trading_costs_total": tc,
        "years": years_total,
    }
    return stats, extra


if __name__ == "__main__":
    import time
    import backtest_spx_distance_scale as ds
    from core.etp_leverage import SPX_ETP, build_etp_return_panel

    p = ds.download_spx_panel()
    avg_tbill = float(p["tbill_rate"].mean())
    idx_ret = p["spx_close"].pct_change().to_numpy(dtype=float)
    cash_ret = (p["tbill_rate"].to_numpy(dtype=float)) / 252.0
    panel = build_etp_return_panel(p, SPX_ETP)
    ret2 = panel["ret_2"].to_numpy(dtype=float)
    ret3 = panel["ret_3"].to_numpy(dtype=float)

    n = len(p)
    ones = np.ones(n)

    def cmp(label, fast_stats, fast_extra, real):
        print(f"\n{label}")
        print(f"  FAST cagr={fast_stats['cagr']*100:.4f} dd={fast_stats['max_drawdown']*100:.4f} "
              f"sharpe={fast_stats['sharpe']:.4f} calmar={fast_stats['calmar']:.4f} "
              f"sortino={fast_stats['sortino']:.4f} vol={fast_stats['volatility']*100:.4f} end={fast_extra['end_$']:.2f} trades={fast_extra['total_trades']}")
        print(f"  REAL cagr={real['cagr']*100:.4f} dd={real['max_drawdown']*100:.4f} "
              f"sharpe={real['sharpe']:.4f} calmar={real['calmar']:.4f} "
              f"sortino={real['sortino']:.4f} vol={real['ann_volatility']*100:.4f} end={real['end_$']:.2f} trades={real['total_trades']}")

    # B&H 1x non-etp
    t0 = time.time()
    s, e = fast_metrics(p, ones * 1.0, idx_ret, cash_ret, avg_tbill)
    ft = time.time() - t0
    real = ds.buy_hold_row(p, 1.0, "Buy & Hold SPY 1x")
    cmp(f"B&H 1x (fast {ft*1000:.0f}ms)", s, e, real)

    # B&H 2x etp
    s, e = fast_metrics(p, ones * 2.0, ret2, cash_ret, avg_tbill)
    real = ds.buy_hold_row(p, 2.0, "Buy & Hold SSO 2x", panel)
    cmp("B&H 2x", s, e, real)

    # B&H 3x etp
    s, e = fast_metrics(p, ones * 3.0, ret3, cash_ret, avg_tbill)
    real = ds.buy_hold_row(p, 3.0, "Buy & Hold UPRO 3x", panel)
    cmp("B&H 3x", s, e, real)

    # SMA200 +-3% band 1x non-etp
    sig = ds.sma_band_signal(p, 200, 0.03).to_numpy(dtype=float)
    s, e = fast_metrics(p, sig * 1.0, idx_ret, cash_ret, avg_tbill)
    spec1 = {"strategy": "t", "sma_window": 200, "band_pct": 0.03, "leverage": 1.0, "rsi_threshold": None, "rsi_period": 14}
    real = ds.run_strategy(p, spec1)
    cmp("SMA200 +-3% Band 1x", s, e, real)

    # Octane: SMA200 +-3% band + RSI>20 exit, 2x etp
    lev_oct, _ = ds.compute_strategy_leverage(p, ds.DEFAULT_SPEC)  # already *2 with rsi filter
    s, e = fast_metrics(p, lev_oct.to_numpy(dtype=float), ret2, cash_ret, avg_tbill)
    real = ds.run_strategy(p, ds.DEFAULT_SPEC, etp_returns=panel)
    cmp("Octane SMA200 +-3% +RSI>20 2x", s, e, real)
