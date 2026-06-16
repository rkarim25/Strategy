"""Full summary: SMA20 guarded vs non-guarded on real 2x AND 3x ETPs, S&P + Nasdaq.

Each leverage uses its own MAX real-ETP window (3x ETPs only list 2012-12-13+).
$100 start, $10/yr inflow, signal lagged 1 day. Reports gross/0.10%/1% cost.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd
import yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine  # noqa: E402
from etp_leverage import NDX_ETP, SPX_ETP, build_etp_return_panel, etp_coverage_summary  # noqa: E402
from metrics import comprehensive_stats  # noqa: E402
from test_guarded_balanced_candidate import guarded_strategy_leverage  # noqa: E402
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage  # noqa: E402

TBILL = "^IRX"
SPEC = dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15)


def eng(cost):
    return PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)


def close(t):
    s = yf.download(t, period="max", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
    s.index = s.index.tz_localize(None)
    return s


def prices_from(index_ticker, start):
    idx, tb = close(index_ticker), close(TBILL)
    p = pd.DataFrame({"spx_close": idx, "tbill_rate": tb / 100.0}).sort_index().ffill().dropna()
    return p.loc[p.index >= start]


def metrics(prices, lev, panel, cost):
    r = eng(cost).run(prices, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    return dict(cagr=round(s["cagr"], 5), dd=round(s["max_drawdown"], 5), vol=round(s["volatility"], 5),
                sharpe=round(s["sharpe"], 3), end=round(float(r.equity.iloc[-1]), 1), reb=r.rebalance_count)


records = []
for asset, idx_t, bundle in [("S&P 500", "^GSPC", SPX_ETP), ("Nasdaq 100", "^NDX", NDX_ETP)]:
    inc = {2: close(bundle.etf_2x).index[0], 3: close(bundle.etf_3x).index[0]}
    tick = {2: bundle.etf_2x, 3: bundle.etf_3x}
    for L in (2, 3):
        prices = prices_from(idx_t, inc[L])
        panel = build_etp_return_panel(prices, bundle)
        cov = etp_coverage_summary(panel)
        cov_real = cov["pct_real_2x"] if L == 2 else cov["pct_real_3x"]
        levs = {
            "non-guarded": sma_cash_leverage(prices, BASE_SMA_WINDOW, float(L)),
            "guarded": guarded_strategy_leverage(prices, **SPEC)[0].clip(upper=float(L)),
            "buyhold": pd.Series(float(L), index=prices.index),
        }
        for sname, lev in levs.items():
            rec = {
                "asset": asset, "lev": L, "ticker": tick[L], "strategy": sname,
                "start": prices.index[0].date().isoformat(), "end": prices.index[-1].date().isoformat(),
                "years": round((prices.index[-1] - prices.index[0]).days / 365.25, 1),
                "real_pct": cov_real,
                "g": metrics(prices, lev, panel, 0.0),      # gross
                "r": metrics(prices, lev, panel, 0.001),    # 0.10% realistic
                "x": metrics(prices, lev, panel, 0.01),     # 1% repo/site default
            }
            records.append(rec)

out = ROOT / "scratch" / "summary_all_leverage.json"
out.write_text(json.dumps(records, indent=1))

# console table (headline 0.10%)
print(f"{'asset':<11}{'lev':>4} {'strategy':<12}{'window':>24}{'yrs':>5}{'real%':>6}"
      f"{'CAGR':>8}{'maxDD':>8}{'vol':>7}{'Sharpe':>7}{'end$':>12}")
for r in records:
    m = r["r"]
    print(f"{r['asset']:<11}{r['lev']:>3}x {r['strategy']:<12}{r['start']+'→'+r['end']:>24}"
          f"{r['years']:>5.1f}{r['real_pct']:>6.0f}{m['cagr']*100:>7.1f}%{m['dd']*100:>7.1f}%"
          f"{m['vol']*100:>6.1f}%{m['sharpe']:>7.2f}{m['end']:>12,.0f}")
print(f"\nJSON -> {out}")
