"""Authoritative run: SMA20 guarded vs non-guarded on REAL leveraged ETPs.

Honest execution = repo engine (signal lagged 1 day), $100 start, $10/yr inflow.
Headline trading cost 0.10% (realistic liquid-ETP half-spread on traded notional);
also shown at 0% (gross) and 1% (repo/website default) for continuity.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine  # noqa: E402
from etp_leverage import NDX_ETP, SPX_ETP, EtpBundle, build_etp_return_panel, etp_coverage_summary  # noqa: E402
from metrics import comprehensive_stats  # noqa: E402
from test_guarded_balanced_candidate import guarded_strategy_leverage  # noqa: E402
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage  # noqa: E402

TBILL = "^IRX"
SPEC = dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15)


def eng(cost: float) -> PortfolioEngine:
    return PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)


def close(t: str) -> pd.Series:
    s = yf.download(t, period="max", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None)
    return s


def prices_from(index_ticker: str, start: pd.Timestamp) -> pd.DataFrame:
    idx, tb = close(index_ticker), close(TBILL)
    p = pd.DataFrame({"spx_close": idx, "tbill_rate": tb / 100.0}).sort_index().ffill().dropna()
    return p.loc[p.index >= start]


def metrics(prices, lev, panel, cost):
    r = eng(cost).run(prices, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    return dict(cagr=s["cagr"], dd=s["max_drawdown"], vol=s["volatility"], sharpe=s["sharpe"],
                end=float(r.equity.iloc[-1]), reb=r.rebalance_count)


def run_asset(label, index_ticker, bundle: EtpBundle, cap2x: bool):
    start = close(bundle.etf_2x).index[0] if cap2x else max(close(bundle.etf_2x).index[0], close(bundle.etf_3x).index[0])
    prices = prices_from(index_ticker, start)
    panel = build_etp_return_panel(prices, bundle)
    cov = etp_coverage_summary(panel)
    win = f"{prices.index[0].date()}->{prices.index[-1].date()} ({round((prices.index[-1]-prices.index[0]).days/365.25,1)}y, {len(prices)} sess)"
    lev_ng = sma_cash_leverage(prices, BASE_SMA_WINDOW, 2.0)
    lev_g_raw = guarded_strategy_leverage(prices, **SPEC)[0]
    lev_g = lev_g_raw.clip(upper=2.0) if cap2x else lev_g_raw
    str
    rows = {}
    for name, lev in [("non-guarded", lev_ng), ("guarded", lev_g)]:
        rows[name] = {c: metrics(prices, lev, panel, c) for c in (0.0, 0.001, 0.01)}
    # buy & hold refs (cost ~ irrelevant, 2 rebalances)
    bh = {"BH2x": metrics(prices, pd.Series(2.0, index=prices.index), panel, 0.001),
          "BH1x": metrics(prices, pd.Series(1.0, index=prices.index), panel, 0.001)}
    return label, win, cov, rows, bh


def show(label, win, cov, rows, bh, cap_note):
    print(f"\n{'='*96}\n{label}  |  {win}  |  real-2x {cov['pct_real_2x']}%  real-3x {cov['pct_real_3x']}%  {cap_note}")
    print(f"{'strategy':<16}{'cost':>6}{'CAGR':>9}{'maxDD':>9}{'vol':>7}{'Sharpe':>8}{'start$':>8}{'end$':>13}{'reb':>6}")
    for name in ("non-guarded", "guarded"):
        for c in (0.0, 0.001, 0.01):
            m = rows[name][c]
            tag = {0.0: "0%(gross)", 0.001: "0.10%", 0.01: "1%(repo)"}[c]
            print(f"{name:<16}{tag:>6}{m['cagr']*100:>8.2f}%{m['dd']*100:>8.1f}%{m['vol']*100:>6.1f}%{m['sharpe']:>8.2f}{100:>8.0f}{m['end']:>13,.0f}{m['reb']:>6}")
    for k in ("BH2x", "BH1x"):
        m = bh[k]
        print(f"{k+' B&H':<16}{'~':>6}{m['cagr']*100:>8.2f}%{m['dd']*100:>8.1f}%{m['vol']*100:>6.1f}%{m['sharpe']:>8.2f}{100:>8.0f}{m['end']:>13,.0f}{m['reb']:>6}")


print("$100 start, $10/yr inflow, signal lagged 1 day (no look-ahead). Vol is cost-independent.")
print("\n########## PART 1: capped at 2x, MAX real-2x history ##########")
for label, idx, bundle in [("SPX 2x  (XS2D.L)", "^GSPC", SPX_ETP), ("NDX 2x  (LQQ.PA)", "^NDX", NDX_ETP)]:
    show(*run_asset(label, idx, bundle, cap2x=True), "[guarded capped 2x]")
print("\n########## PART 2: guarded NATIVE (up to 3x), real 2x+3x window (2012-12-13+) ##########")
for label, idx, bundle in [("SPX  (XS2D.L+3USL.L)", "^GSPC", SPX_ETP), ("NDX  (LQQ.PA+LQQ3.L)", "^NDX", NDX_ETP)]:
    show(*run_asset(label, idx, bundle, cap2x=False), "[guarded NATIVE up to 3x]")
