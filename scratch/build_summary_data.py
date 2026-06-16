"""Cross-asset Summary Results data: 6 asset classes x 8 strategies x 3 regimes.

Regimes per strategy: Real (ETP era), Synthetic (same era), Synthetic (long history).
Metrics: CAGR/DD at 0/0.1/1% cost, vol, Sharpe, Sortino, Calmar, %cash, trades/yr, end$.
$100 start, $10/yr inflow, signal lagged 1 day. Writes summary_data.json for summary.html.

Uses SAME-CALENDAR US-listed leveraged ETPs (SSO/UPRO, QLD/TQQQ, UWM/TNA, UGL, UBT/TMF):
the signal index and the P&L ETP trade on the same calendar. UCITS XS2D.L / LQQ.PA were
dropped because their Yahoo daily returns are calendar-offset vs the US index
(corr ~0.57, ratio ~1.2x), which inflates daily-timed backtests even though long-run
totals match. `None` = no same-calendar real product for that tier -> synthetic.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import PortfolioEngine, FUNDING_SPREAD, TRADING_DAYS  # noqa: E402
from etp_leverage import TER_ANNUAL  # noqa: E402
from metrics import comprehensive_stats  # noqa: E402
from test_guarded_balanced_candidate import guarded_strategy_leverage  # noqa: E402
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage  # noqa: E402

TBILL = "^IRX"
LONG_CAP = pd.Timestamp("1990-01-01")
CAP = {1: 0.15, 2: 0.28, 3: 0.42}
SPECS = {
    "Guarded A5/B25": dict(trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15),
    "Guarded A10/B20": dict(trigger_a=0.10, trigger_b=0.20, lead_pct_below_sma20=0.0, x_return=0.25, y_return=1/3),
}
STRATS = ["Buy & hold 1x", "Buy & hold 2x", "Buy & hold 3x",
          "SMA20 1x/cash", "SMA20 2x/cash", "SMA20 3x/cash",
          "SMA200 1x/cash", "SMA200 2x/cash", "SMA200 3x/cash",
          "Guarded A5/B25", "Guarded A10/B20",
          "Guarded+ (200/2x/floor)", "Mom 12m 2x/cash",
          "SMA200 2x monthly", "SMA200 2x 3% band", "Golden 50/200 2x"]
# "Guarded+" strategies run through a -25% drawdown-floor engine (see eng(floor=True)).
FLOOR = {"Guarded+ (200/2x/floor)"}
ASSETS = [
    dict(key="spx", label="S&P 500", idx="^GSPC", t={1: "SPY", 2: "SSO", 3: "UPRO"}, real={1, 2, 3}),
    dict(key="spxew", label="S&P 500 Equal Weight", idx="RSP", t={1: "RSP", 2: None, 3: None}, real={1}),
    dict(key="ndx", label="Nasdaq 100", idx="^NDX", t={1: "QQQ", 2: "QLD", 3: "TQQQ"}, real={1, 2, 3}),
    dict(key="rut", label="Russell 2000", idx="^RUT", t={1: "IWM", 2: "UWM", 3: "TNA"}, real={1, 2, 3}),
    dict(key="gold", label="Gold", idx="GLD", t={1: "GLD", 2: "UGL", 3: None}, real={1, 2}),
    dict(key="tlt", label="20Y+ Treasuries", idx="TLT", t={1: "TLT", 2: "UBT", 3: "TMF"}, real={1, 2, 3}),
]

_C: dict[str, pd.Series] = {}
def close(tk):
    if tk not in _C:
        s = yf.download(tk, period="max", auto_adjust=True, progress=False)["Close"].dropna().astype(float).squeeze()
        s.index = s.index.tz_localize(None)
        _C[tk] = s
    return _C[tk]

def eng(cost, floor=False):
    return PortfolioEngine(max_drawdown_limit=(0.25 if floor else None),
                           hard_drawdown_floor=floor,
                           trading_cost_pct=cost, annual_inflow_pct=0.0, annual_inflow_abs=10.0)

def prices_from(idx_t, start):
    idx, tb = close(idx_t), close(TBILL)
    p = pd.DataFrame({"spx_close": idx, "tbill_rate": tb/100.0}).sort_index().ffill().dropna()
    return p.loc[p.index >= start]

def synth_panel(prices):
    # Clean daily-reset model: daily return = L*r - borrow - fee. Daily compounding
    # already produces volatility drag/boost, so NO separate vol-drag term (the repo's
    # synthetic_daily_reset_return double-counts it -> too pessimistic vs real ETPs;
    # a clean 2x-daily compound matches SSO/XS2D ~19x over 2012-26).
    r = prices["spx_close"].astype(float).pct_change()
    tb = prices["tbill_rate"].astype(float)
    def bor(L): return (L-1.0)*(tb+FUNDING_SPREAD)/TRADING_DAYS
    return pd.DataFrame({
        "ret_0": tb/TRADING_DAYS,
        "ret_1": (r - TER_ANNUAL[1]/TRADING_DAYS).fillna(0.0),
        "ret_2": (2*r - bor(2) - TER_ANNUAL[2]/TRADING_DAYS).fillna(0.0),
        "ret_3": (3*r - bor(3) - TER_ANNUAL[3]/TRADING_DAYS).fillna(0.0),
    }, index=prices.index)

def real_panel(prices, t, real_tiers):
    """Real ETP returns for tiers in real_tiers (bad ticks fall back to synthetic), else synthetic."""
    syn = synth_panel(prices)
    out = syn.copy()
    cov = {2: 0.0, 3: 0.0}
    for tier in (1, 2, 3):
        if tier in real_tiers and t.get(tier):
            r = close(t[tier]).reindex(prices.index).ffill().pct_change()
            ok = (r.abs() <= CAP[tier]) & r.notna()
            out[f"ret_{tier}"] = r.where(ok, syn[f"ret_{tier}"]).fillna(syn[f"ret_{tier}"])
            if tier in cov:
                cov[tier] = round(100.0 * float(ok.mean()), 1)
    return out, {"pct_real_2x": cov[2], "pct_real_3x": cov[3]}

def guarded_plus_lev(prices, k=1.2):
    # Improved guarded: 200-day trend filter + ASSET-RELATIVE volatility de-levering.
    # 2x when above SMA200 and 20-day vol < 1.2x the asset's OWN trailing-252d median vol
    # (calm for this asset, not a fixed 20% that is too tight for high-vol indices like the
    # Nasdaq); 1x when above SMA200 but vol elevated; cash below SMA200. Engine adds -25% floor.
    close = prices["spx_close"].astype(float)
    sma200 = close.rolling(200, min_periods=200).mean()
    above = (close > sma200).fillna(False)
    rvol = close.pct_change().rolling(20).std() * np.sqrt(TRADING_DAYS)
    thresh = (k * rvol.rolling(252, min_periods=60).median()).fillna(0.20)
    lev = pd.Series(0.0, index=prices.index)
    lev[above] = 1.0
    lev[above & (rvol < thresh)] = 2.0
    return lev

def absmom_lev(prices, lookback=252, lev=2.0):
    # Time-series (absolute) momentum: hold 2x while price > price 12 months ago, else cash.
    c = prices["spx_close"].astype(float)
    out = pd.Series(0.0, index=prices.index)
    out[c > c.shift(lookback)] = lev
    return out

def golden_lev(prices, fast=50, slow=200, lev=2.0):
    # Golden cross: 2x while the fast SMA is above the slow SMA, else cash. Crosses are
    # rare (~1 trade/yr), sidestepping the daily SMA200 whipsaw; best Nasdaq all-rounder.
    c = prices["spx_close"].astype(float)
    f = c.rolling(fast, min_periods=fast).mean()
    s = c.rolling(slow, min_periods=slow).mean()
    out = pd.Series(0.0, index=prices.index)
    out[f > s] = lev
    return out

def monthlyize(raw):
    # Hold the leverage decided at the PRIOR month-end through the month (cuts whipsaw
    # turnover ~5x vs daily). Lookahead-free: uses only completed-month signals.
    per = raw.index.to_period("M")
    last = raw.groupby(per).last().shift(1)
    return pd.Series(per.map(last), index=raw.index).astype(float).fillna(0.0)

def hysteresis_lev(prices, window=200, lev=2.0, band=0.03):
    # SMA200 with a +/-3% dead-band: 2x only above SMA*1.03, cash only below SMA*0.97, hold
    # in between. Ignores minor dips around the line -> far fewer false exits/re-entries.
    c = prices["spx_close"].astype(float)
    s = c.rolling(window, min_periods=window).mean()
    out = pd.Series(np.nan, index=prices.index)
    out[c > s * (1 + band)] = lev
    out[c < s * (1 - band)] = 0.0
    return out.ffill().fillna(0.0)

def lev_for(name, prices):
    if name == "SMA200 2x monthly":
        return monthlyize(sma_cash_leverage(prices, 200, 2.0))
    if name == "SMA200 2x 3% band":
        return hysteresis_lev(prices, 200, 2.0, 0.03)
    if name == "Golden 50/200 2x":
        return golden_lev(prices, 50, 200, 2.0)
    if name.startswith("Buy & hold"):
        return pd.Series(float(name.split()[3][0]), index=prices.index)
    if name.startswith("SMA200"):
        return sma_cash_leverage(prices, 200, float(name.split()[1][0]))
    if name.startswith("SMA20"):
        return sma_cash_leverage(prices, BASE_SMA_WINDOW, float(name.split()[1][0]))
    if name.startswith("Mom"):
        return absmom_lev(prices)
    if name.startswith("Guarded+"):
        return guarded_plus_lev(prices)
    return guarded_strategy_leverage(prices, **SPECS[name])[0]

def metrics(prices, lev, panel, years, floor=False):
    out = {}
    for cost, tag in [(0.0, "g"), (0.001, "r"), (0.01, "x")]:
        res = eng(cost, floor).run(prices, lev, etp_returns=panel)
        s = comprehensive_stats(res.equity, res.daily_returns)
        if tag == "r":
            out.update(vol=round(s["volatility"], 4), sharpe=round(s["sharpe"], 2),
                       sortino=round(s.get("sortino") or 0, 2), calmar=round(s.get("calmar") or 0, 2),
                       cash=round(float((res.leverage <= 0).mean()*100), 1),
                       trades_yr=round(res.rebalance_count/years, 1), end=round(float(res.equity.iloc[-1]), 0))
        out[f"cagr_{tag}"] = round(s["cagr"], 4)
        out[f"dd_{tag}"] = round(s["max_drawdown"], 4)
    return out

def regime(prices, real, t=None, real_tiers=None):
    panel, cov = (real_panel(prices, t, real_tiers) if real
                  else (synth_panel(prices), {"pct_real_2x": 0.0, "pct_real_3x": 0.0}))
    yrs = (prices.index[-1]-prices.index[0]).days/365.25
    rows = {s: metrics(prices, lev_for(s, prices), panel, yrs, floor=(s in FLOOR)) for s in STRATS}
    return {"start": prices.index[0].date().isoformat(), "end": prices.index[-1].date().isoformat(),
            "years": round(yrs, 1), "sessions": len(prices), "cov": cov, "rows": rows}

result = {"generated": None, "assets": []}
for A in ASSETS:
    real_tiers, t = A["real"], A["t"]
    real_lev = len(real_tiers) > 1
    start_real = max(close(t[k]).index[0] for k in real_tiers if t.get(k))
    p_real = prices_from(A["idx"], start_real)
    p_long = prices_from(A["idx"], max(close(A["idx"]).index[0], LONG_CAP))
    entry = {"key": A["key"], "label": A["label"], "idx": A["idx"], "real_lev": real_lev,
             "tickers": {"1x": t.get(1) or "—", "2x": t.get(2) or "synthetic", "3x": t.get(3) or "synthetic"},
             "real": regime(p_real, True, t, real_tiers),
             "synth_era": regime(p_real, False),
             "synth_long": regime(p_long, False)}
    result["assets"].append(entry)
    rr = entry["real"]["rows"]["SMA20 2x/cash"]
    print(f"== {A['label']:<22} real {entry['real']['start']}->{entry['real']['end']} "
          f"SMA2 {rr['cagr_r']*100:5.1f}% (synthEra {entry['synth_era']['rows']['SMA20 2x/cash']['cagr_r']*100:5.1f}%) "
          f"trades/yr {rr['trades_yr']}", flush=True)

out = ROOT / "summary_data.json"
out.write_text(json.dumps(result, separators=(",", ":")))
print(f"\nWrote {out} ({out.stat().st_size//1024} KB)")
