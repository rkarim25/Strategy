"""Build the technical-indicator signal dashboard data for S&P 500 and Nasdaq 100.

This does NOT run any new backtests. The factory already holds a comprehensive,
cost-aware, anti-look-ahead sweep of ~180 indicator strategies per asset in
``output/comprehensive_sweep/spx_ndx_comprehensive.csv`` (SPX 1950-2026, NDX
1985-2026) plus a long single-asset SPX sweep in
``output/spx_1x_sweep/spx_1x_sweep_results.csv``. This script CURATES a graded
subset of those results into ``signals_<asset>.json`` at repo root, which the
Charts workstation (``price.js``) reads to render the live signal dashboard.

Each curated signal carries:
  * the 1x/cash backtest evidence (risk-adjusted stats vs buy-and-hold),
  * an honest A/B/C/D reliability grade derived from the Beat_BH_* flags,
  * a ``rule``+``params`` pair naming the in-browser evaluator that computes the
    CURRENT signal state and 0-100 strength live from price data,
  * a plain-English "why this matters", and a ``plot`` spec for "show on chart".

Run:  python research/build_signal_dashboard.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from signal_state import composite, current_vix, evaluate, load_close

REPO = Path(__file__).resolve().parents[1]
COMPREHENSIVE = REPO / "output" / "comprehensive_sweep" / "spx_ndx_comprehensive.csv"
SPX_1X = REPO / "output" / "spx_1x_sweep" / "spx_1x_sweep_results.csv"

# Grade -> base reliability weight (0..1). Weak-but-famous indicators are shown
# (curation = "comprehensive + graded") but their low weight stops them from
# dominating the composite market read.
GRADE_BASE = {"A": 0.85, "B": 0.60, "C": 0.35, "D": 0.15}


def grade_from_flags(beat_sharpe: int, beat_calmar: int, beat_dd: int,
                     sharpe: float, calmar: float, bh_sharpe: float) -> str:
    """Honest A/B/C/D grade.

    Beating buy-and-hold is necessary but NOT sufficient: a 1x index buy-and-hold
    carries a ~-55% (SPX) / -82% (NDX) drawdown, so almost any cash-raising filter
    clears it on drawdown/Sharpe. Real grade is gated on ABSOLUTE risk-adjusted
    quality (Sharpe + Calmar), with beat-BH as a tie-break floor:
      A  genuinely strong, distinctive edge      (high Sharpe AND high Calmar, beats BH outright)
      B  solid, useful, slightly behind the best  (good Sharpe, decent Calmar, beats BH on Sharpe+DD)
      C  marginal / situational                   (clears BH on >=1 dim but unremarkable)
      D  famous-but-weak                          (fails to beat BH risk-adjusted)
    """
    n_risk = int(beat_sharpe) + int(beat_calmar) + int(beat_dd)
    if sharpe >= 0.50 and calmar >= 0.38 and n_risk == 3:
        return "A"
    if sharpe >= 0.43 and calmar >= 0.25 and beat_sharpe and beat_dd:
        return "B"
    if n_risk >= 1 and not (sharpe < 0.30 and calmar < 0.18):
        return "C"
    return "D"


def reliability(grade: str, sharpe: float, bh_sharpe: float) -> float:
    base = GRADE_BASE[grade]
    rel = base + 0.10 * (sharpe - bh_sharpe)
    return round(max(0.10, min(1.0, rel)), 3)


# ---------------------------------------------------------------------------
# The curated universe. Each entry maps a displayed indicator to its canonical
# backtest row + the in-browser evaluator that reproduces the same signal logic.
# ``source`` selects which CSV the evidence row comes from. ``category`` is one
# of trend / momentum / meanrev / risk / seasonal. ``vote`` signals carry a
# directional long/cash vote into the composite; ``overlay`` signals only
# modulate the suggested leverage (they don't vote a direction).
# ---------------------------------------------------------------------------
CURATED: list[dict[str, Any]] = [
    dict(id="sma200_trend", name="Price vs 200-day SMA", category="trend", kind="vote",
         row="SMA200 1x/cash", rule="ma_trend",
         params=dict(window=200, type="sma"),
         plot=dict(indicator="MA", params=[200]),
         why="The canonical trend filter. Long while price holds above its 200-day "
             "average, cash below. Historically slashes the worst-case drawdown by "
             "more than half while giving up little long-run return."),
    dict(id="sma200_band", name="200-day SMA ±3% Band", category="trend", kind="vote",
         row="SMA200 +-3% Band 1x/cash", rule="ma_band",
         params=dict(window=200, band=0.03, type="sma"),
         plot=dict(indicator="MA", params=[200]),
         why="A 3% dead-band around the 200-day SMA filters out whipsaw crossings. "
             "Best risk-adjusted trend rule in the book — highest Calmar and the "
             "shallowest drawdown of the simple filters."),
    dict(id="golden_cross", name="Golden Cross (50/200)", category="trend", kind="vote",
         row="SMA50/200 Golden Cross 1x/cash", rule="cross",
         params=dict(fast=50, slow=200, type="sma"),
         plot=dict(indicator="MA", params=[50, 200]),
         why="Long when the 50-day SMA sits above the 200-day. Slow and low-turnover "
             "(~1 trade/yr), so it sidesteps chop and rides the big trends."),
    dict(id="sma50_trend", name="Price vs 50-day SMA", category="trend", kind="vote",
         row="SMA50 1x/cash", rule="ma_trend",
         params=dict(window=50, type="sma"),
         plot=dict(indicator="MA", params=[50]),
         why="A faster trend gauge — quicker to react than the 200-day but pays "
             "for it in whipsaw. Useful as a confirming, shorter-horizon read."),
    dict(id="ema200_trend", name="Price vs 200-day EMA", category="trend", kind="vote",
         row="EMA200 1x/cash", rule="ma_trend",
         params=dict(window=200, type="ema"),
         plot=dict(indicator="EMA", params=[200]),
         why="The exponential cousin of the 200-day filter — weights recent price "
             "more, so it turns a little sooner around major tops and bottoms."),
    dict(id="momentum_12m", name="12-Month Momentum", category="momentum", kind="vote",
         row="Momentum 12m 1x/cash", rule="momentum",
         params=dict(lookback=252),
         plot=dict(indicator="MA", params=[252]),
         why="Long while price is above where it sat 12 months ago — the classic "
             "time-series momentum effect. A genuinely independent edge from the "
             "moving-average filters."),
    dict(id="macd", name="MACD (12/26/9)", category="momentum", kind="vote",
         row="MACD 1x/cash", rule="macd",
         params=dict(fast=12, slow=26, signal=9),
         plot=dict(indicator="MACD", params=[12, 26, 9]),
         why="A textbook momentum oscillator. On a trending index it beats buy-and-hold "
             "on a risk-adjusted basis but trades far too often to add real return — "
             "treat it as a tactical tell, not a core driver."),
    dict(id="bollinger", name="Bollinger Mean-Reversion", category="meanrev", kind="vote",
         row="BB Mean Reversion 1x/cash", rule="bollinger",
         params=dict(window=20, std=2.0),
         plot=dict(indicator="BOLL", params=[20, 2]),
         why="Buys pierces below the lower band, exits back at the mid-line. Works in "
             "range-bound tape and cushions drawdowns, but sits in cash ~80% of the "
             "time so it lags in strong trends."),
    dict(id="band_rsi_exit", name="SMA200 Band + RSI Exit", category="trend", kind="vote",
         row="SMA200 +-3% Band + RSI>30 Exit 1x/cash", rule="ma_band",
         params=dict(window=200, band=0.03, type="sma"),
         plot=dict(indicator="MA", params=[200]),
         why="The 200-day band with an RSI-based exit refinement — stays invested "
             "through shallow oversold dips that the plain band would whipsaw out of."),
    dict(id="sell_in_may", name="Seasonality (Sell in May)", category="seasonal", kind="vote",
         row="Sell in May (May-Oct -> cash, Nov-Apr -> 1x)", rule="sell_in_may",
         params=dict(),
         plot=None,
         why="Invested Nov–Apr, cash May–Oct. The seasonal effect is real in the "
             "long record — most of the index's return has historically arrived in "
             "the winter half — but it's a calendar tilt, not a market read."),
    dict(id="rsi_oscillator", name="RSI 30/70 Oscillator", category="meanrev", kind="vote",
         row="RSI 30/70 2x", rule="rsi_osc",
         params=dict(period=14, low=30, high=70),
         plot=dict(indicator="RSI", params=[14]),
         why="The most-watched oscillator — and a cautionary tale. Selling strength "
             "at RSI 70 and buying weakness at 30 fails to beat buy-and-hold on a "
             "trending index. Shown for completeness, weighted accordingly."),
    # --- Risk overlays: these size leverage, they do not cast a long/cash vote ---
    dict(id="vix_regime", name="Volatility Regime (VIX)", category="risk", kind="overlay",
         row="VIX Scale 1-3x", rule="vix_regime",
         params=dict(calm=15, stress=25), data="vix",
         plot=None,
         why="Scales exposure up when volatility is calm and down when it spikes. "
             "Low-vol regimes have historically delivered the best risk-adjusted "
             "returns — one of the strongest single leverage-sizing inputs."),
    dict(id="dd_from_high", name="Drawdown From High", category="risk", kind="overlay",
         row="DD Scale 1-3x", rule="dd_from_high",
         params=dict(),
         plot=None,
         why="Sizes exposure by how far price sits below its all-time high. Leaning in "
             "after controlled pullbacks (not crashes) has been a high-Calmar way to "
             "add leverage."),
    # --- SPX-only: clean 1x oversold-bounce backtest only exists in the long SPX sweep ---
    dict(id="rsi_oversold_bounce", name="RSI Oversold Bounce", category="meanrev", kind="vote",
         row="RSI Oversold Bounce 1x", source="spx_1x", rule="rsi_oversold",
         params=dict(period=14, low=30, smaWin=200), assets=["spx"],
         plot=dict(indicator="RSI", params=[14]),
         why="Buys oversold dips (RSI<30) only while the long-term trend is up, exits "
             "on the bounce. The single best-behaved tactical rule on the S&P — a "
             "94% daily win-rate over its (brief, episodic) holding periods."),
]


def _f(v: Any) -> Optional[float]:
    """CSV value -> float or None, JSON-safe (no NaN/Inf)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def load_sources() -> dict[str, pd.DataFrame]:
    comp = pd.read_csv(COMPREHENSIVE)
    spx1x = pd.read_csv(SPX_1X)
    return {"comp": comp, "spx_1x": spx1x}


def evidence_from_comprehensive(df: pd.DataFrame, asset: str, row: str) -> Optional[dict[str, Any]]:
    sub = df[(df.Asset == asset) & (df.Strategy == row)]
    if sub.empty:
        return None
    r = sub.iloc[0]
    bh = df[(df.Asset == asset) & (df.Strategy == "Buy & Hold 1x")].iloc[0]
    sharpe = _f(r.Sharpe)
    grade = grade_from_flags(int(r.Beat_BH_Sharpe), int(r.Beat_BH_Calmar),
                             int(r.Beat_BH_DD), sharpe or 0.0, _f(r.Calmar) or 0.0,
                             _f(bh.Sharpe) or 0.0)
    return dict(
        strategy_label=row,
        sample=f"{r.Start_Date} to {r.End_Date} ({_f(r.Years):.0f}y)",
        cagr=_f(r.CAGR_pct), vol=_f(r.Vol_pct), sharpe=sharpe, sortino=_f(r.Sortino),
        calmar=_f(r.Calmar), maxdd=_f(r.MaxDD_pct), pct_cash=_f(r.Pct_Cash_Time),
        trades_per_year=_f(r.Trades_Per_Year),
        beats_bh=dict(sharpe=bool(r.Beat_BH_Sharpe), calmar=bool(r.Beat_BH_Calmar),
                      dd=bool(r.Beat_BH_DD), cagr=bool(r.Beat_BH_CAGR)),
        grade=grade,
        reliability=reliability(grade, sharpe or 0.0, _f(bh.Sharpe) or 0.0),
    )


def evidence_from_spx1x(df: pd.DataFrame, row: str) -> Optional[dict[str, Any]]:
    sub = df[df.strategy == row]
    if sub.empty:
        return None
    r = sub.iloc[0]
    bh = df[df.strategy == "Buy & Hold SPY 1x"].iloc[0]
    sharpe = _f(r.sharpe)
    bh_sharpe = _f(bh.sharpe) or 0.0
    beat_sharpe = int(sharpe > bh_sharpe) if sharpe is not None else 0
    beat_calmar = int((_f(r.calmar) or 0) > (_f(bh.calmar) or 0))
    beat_dd = int((_f(r.max_drawdown) or -1) > (_f(bh.max_drawdown) or -1))
    grade = grade_from_flags(beat_sharpe, beat_calmar, beat_dd, sharpe or 0.0,
                             _f(r.calmar) or 0.0, bh_sharpe)
    return dict(
        strategy_label=row,
        sample="1994 to 2026 (~30y)",
        cagr=round((_f(r.cagr) or 0) * 100, 2), vol=round((_f(r.ann_volatility) or 0) * 100, 2),
        sharpe=sharpe, sortino=_f(r.sortino), calmar=_f(r.calmar),
        maxdd=round((_f(r.max_drawdown) or 0) * 100, 2),
        pct_cash=round(_f(r.pct_days_cash) or 0, 1), trades_per_year=None,
        win_rate=round((_f(r.win_rate) or 0) * 100, 1),
        beats_bh=dict(sharpe=bool(beat_sharpe), calmar=bool(beat_calmar),
                      dd=bool(beat_dd), cagr=bool((_f(r.cagr) or 0) > (_f(bh.cagr) or 0))),
        grade=grade,
        reliability=reliability(grade, sharpe or 0.0, bh_sharpe),
    )


def build_asset(asset: str, src: dict[str, pd.DataFrame]) -> dict[str, Any]:
    comp = src["comp"]
    bh = comp[(comp.Asset == asset) & (comp.Strategy == "Buy & Hold 1x")].iloc[0]
    signals: list[dict[str, Any]] = []
    skipped: list[str] = []
    for spec in CURATED:
        if "assets" in spec and asset not in spec["assets"]:
            continue
        source = spec.get("source", "comp")
        if source == "spx_1x":
            ev = evidence_from_spx1x(src["spx_1x"], spec["row"])
        else:
            ev = evidence_from_comprehensive(comp, asset, spec["row"])
        if ev is None:
            skipped.append(f"{spec['id']} ({spec['row']})")
            continue
        signals.append(dict(
            id=spec["id"], name=spec["name"], category=spec["category"], kind=spec["kind"],
            rule=spec["rule"], params=spec["params"], plot=spec.get("plot"),
            data=spec.get("data"), why=spec["why"],
            grade=ev["grade"], reliability=ev["reliability"], evidence=ev,
        ))
    if skipped:
        print(f"  [{asset}] skipped (no backtest row): {', '.join(skipped)}")
    # Order: graded A->D, then by reliability, with risk overlays last within a grade.
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    signals.sort(key=lambda s: (order[s["grade"]], s["kind"] == "overlay", -s["reliability"]))

    # --- Current-state snapshot (live read for the skill + dashboard first paint) ---
    daily = pd.read_csv(REPO / f"{asset}_daily.csv")
    close = daily["Close"].astype(float).reset_index(drop=True)
    asof = str(daily["Date"].iloc[-1])
    month = int(asof[5:7])
    vix = current_vix()
    for s in signals:
        params = dict(s["params"])
        if s.get("data") == "vix":
            params["_vix"] = vix
        st = evaluate(s["rule"], params, close, month)
        s["state"] = st
    comp = composite(signals)
    comp["asof"] = asof
    comp["price"] = round(float(close.iloc[-1]), 2)

    return dict(
        asset=asset,
        asset_label="S&P 500" if asset == "spx" else "Nasdaq 100",
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source="output/comprehensive_sweep/spx_ndx_comprehensive.csv (+ spx_1x_sweep)",
        benchmark=dict(
            label="Buy & Hold 1x", cagr=_f(bh.CAGR_pct), vol=_f(bh.Vol_pct),
            sharpe=_f(bh.Sharpe), calmar=_f(bh.Calmar), maxdd=_f(bh.MaxDD_pct),
            sample=f"{bh.Start_Date} to {bh.End_Date} ({_f(bh.Years):.0f}y)",
        ),
        current=comp,
        signals=signals,
    )


def main() -> None:
    src = load_sources()
    for asset in ("spx", "ndx"):
        data = build_asset(asset, src)
        out = REPO / f"signals_{asset}.json"
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        grades = {}
        for s in data["signals"]:
            grades[s["grade"]] = grades.get(s["grade"], 0) + 1
        gstr = " ".join(f"{g}:{grades.get(g, 0)}" for g in "ABCD")
        print(f"[{asset}] {len(data['signals'])} signals ({gstr}) -> {out.name}")


if __name__ == "__main__":
    main()
