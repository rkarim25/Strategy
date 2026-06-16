"""Comprehensive summary: ALL 8 website strategies on real ETP, full ratio set.

Common real-ETP window (2012-12-13+, all of 1x/2x/3x real) for apples-to-apples.
Plus a longer 2x-only window (SPX 2010 / NDX 2008) for max history on <=2x strategies.
$100 start, $10/yr inflow, signal lagged 1 day, headline 0.10% trading cost.
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
SPECS = {
    "A5/B25": dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15),
    "A10/B20": dict(trigger_a=0.10, trigger_b=0.20, lead_pct_below_sma20=0.0, x_return=0.25, y_return=1.0 / 3.0),
}
_CACHE: dict[str, pd.Series] = {}


def close(t):
    if t not in _CACHE:
        s = yf.download(t, period="max", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
        s.index = s.index.tz_localize(None)
        _CACHE[t] = s
    return _CACHE[t]


def eng(cost):
    return PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)


def prices_from(index_ticker, start):
    idx, tb = close(index_ticker), close(TBILL)
    p = pd.DataFrame({"spx_close": idx, "tbill_rate": tb / 100.0}).sort_index().ffill().dropna()
    return p.loc[p.index >= start]


def stats_for(prices, lev, panel, cost):
    r = eng(cost).run(prices, lev, etp_returns=panel)
    s = comprehensive_stats(r.equity, r.daily_returns)
    appl = r.leverage
    def f(x, n=4):
        return None if x is None or (isinstance(x, float) and x != x) else round(float(x), n)
    return dict(cagr=f(s["cagr"]), dd=f(s["max_drawdown"]), vol=f(s["volatility"]), sharpe=f(s["sharpe"], 3),
                sortino=f(s.get("sortino"), 3), calmar=f(s.get("calmar"), 3), ulcer=f(s.get("ulcer_index")),
                ddur=int(s.get("max_dd_duration_days") or 0), end=round(float(r.equity.iloc[-1]), 1),
                pct_cash=round(float((appl <= 0).mean() * 100), 1), reb=r.rebalance_count)


def lev_for(kind, prices, cap=None):
    if kind.startswith("BH"):
        return pd.Series(float(kind[2]), index=prices.index)
    if kind.startswith("SMA"):
        return sma_cash_leverage(prices, BASE_SMA_WINDOW, float(kind[3]))
    spec = SPECS[kind.split()[1]]
    lev = guarded_strategy_leverage(prices, **spec)[0]
    return lev.clip(upper=float(cap)) if cap else lev


def block(asset, idx_t, bundle, start, kinds, costs, cap=None):
    prices = prices_from(idx_t, start)
    panel = build_etp_return_panel(prices, bundle)
    cov = etp_coverage_summary(panel)
    out = {"asset": asset, "start": prices.index[0].date().isoformat(),
           "end": prices.index[-1].date().isoformat(),
           "years": round((prices.index[-1] - prices.index[0]).days / 365.25, 1),
           "sessions": len(prices), "cov": cov, "rows": []}
    for kind in kinds:
        lev = lev_for(kind, prices, cap=cap)
        rec = {"kind": kind}
        for c in costs:
            rec[f"c{c}"] = stats_for(prices, lev, panel, c)
        out["rows"].append(rec)
    return out


result = {"common": [], "long2x": []}
for asset, idx_t, bundle in [("S&P 500", "^GSPC", SPX_ETP), ("Nasdaq 100", "^NDX", NDX_ETP)]:
    inc2 = close(bundle.etf_2x).index[0]
    inc3 = close(bundle.etf_3x).index[0]
    common_kinds = ["BH1", "BH2", "BH3", "SMA1", "SMA2", "SMA3", "Guarded A5/B25", "Guarded A10/B20"]
    result["common"].append(block(asset, idx_t, bundle, inc3, common_kinds, [0.0, 0.001, 0.01]))
    long_kinds = ["BH1", "BH2", "SMA1", "SMA2", "Guarded A5/B25", "Guarded A10/B20"]
    result["long2x"].append(block(asset, idx_t, bundle, inc2, long_kinds, [0.001], cap=2.0))

out = ROOT / "scratch" / "comprehensive_summary.json"
out.write_text(json.dumps(result, indent=1))
print("OK ->", out)
for sec in ("common", "long2x"):
    for blk in result[sec]:
        print(f"\n[{sec}] {blk['asset']} {blk['start']}..{blk['end']} {blk['years']}y "
              f"real2x={blk['cov']['pct_real_2x']} real3x={blk['cov']['pct_real_3x']}")
        for row in blk["rows"]:
            m = row["c0.001"]
            print(f"  {row['kind']:<18} CAGR {m['cagr']*100:6.1f}%  DD {m['dd']*100:6.1f}%  "
                  f"vol {m['vol']*100:5.1f}%  Shrp {m['sharpe']:.2f}  Sort {m['sortino']:.2f}  "
                  f"Calm {m['calmar']:.2f}  cash {m['pct_cash']:.0f}%  end ${m['end']:,.0f}")
