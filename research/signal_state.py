"""Current-state evaluators for the signal dashboard.

Computes, for each curated signal, its CURRENT direction (long / cash) and a
0-100 strength from the latest price data, plus a trust-weighted composite that
yields a market-state label and an INDEPENDENT suggested leverage (0-3x).

This is the canonical specification for the in-browser evaluators in price.js:
the JS must reproduce these formulas so the live dashboard matches. Python here
also writes a ``current`` snapshot into signals_<asset>.json for the
market-analysis skill and the dashboard's first paint (before JS recomputes
against intraday data).

All maths is vectorised (no per-bar Python loops), close-based, and uses only
data up to the latest bar (a current-state read, not a backtest, so no lag).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]


def _squash(x: float, scale: float) -> float:
    """Map a signed distance to 0-100 via tanh; 50 = right at the threshold."""
    return round(50.0 + 50.0 * math.tanh(x / scale), 1)


def _sma(c: pd.Series, n: int) -> float:
    return float(c.tail(n).mean())


def _ema(c: pd.Series, n: int) -> float:
    return float(c.ewm(span=n, adjust=False).mean().iloc[-1])


def _rsi(c: pd.Series, n: int = 14) -> float:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _macd(c: pd.Series, f: int, s: int, sig: int) -> tuple[float, float]:
    macd = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    signal = macd.ewm(span=sig, adjust=False).mean()
    return float(macd.iloc[-1]), float(signal.iloc[-1])


def evaluate(rule: str, params: dict[str, Any], close: pd.Series,
             month: int) -> Optional[dict[str, Any]]:
    """Return {dir: +1 long / -1 cash, strength: 0-100, read: str} or None.

    ``dir`` is the directional vote; ``strength`` is the intensity (0-100) of the
    signal firing right now (later multiplied by reliability in the composite).
    """
    c = close
    last = float(c.iloc[-1])

    if rule == "ma_trend":
        n = params["window"]
        ma = _ema(c, n) if params.get("type") == "ema" else _sma(c, n)
        x = last / ma - 1.0
        d = 1 if last >= ma else -1
        return dict(dir=d, strength=_squash(x, 0.05),
                    read=f"{last:,.0f} vs {n}-day {'EMA' if params.get('type')=='ema' else 'SMA'} "
                         f"{ma:,.0f} ({x*100:+.1f}%)")

    if rule == "ma_band":
        n, band = params["window"], params["band"]
        ma = _ema(c, n) if params.get("type") == "ema" else _sma(c, n)
        upper, lower = ma * (1 + band), ma * (1 - band)
        if last >= upper:
            d, x = 1, last / upper - 1.0
        elif last <= lower:
            d, x = -1, last / lower - 1.0
        else:  # inside the band -> lean by side of the mid-line, damped
            d = 1 if last >= ma else -1
            x = (last / ma - 1.0) * 0.5
        return dict(dir=d, strength=_squash(x, 0.05),
                    read=f"{last:,.0f} vs {n}-day band [{lower:,.0f} – {upper:,.0f}]")

    if rule == "cross":
        f, s = params["fast"], params["slow"]
        use_ema = params.get("type") == "ema"
        mf = _ema(c, f) if use_ema else _sma(c, f)
        ms = _ema(c, s) if use_ema else _sma(c, s)
        x = mf / ms - 1.0
        d = 1 if mf >= ms else -1
        return dict(dir=d, strength=_squash(x, 0.05),
                    read=f"{f}-day {mf:,.0f} {'>' if mf>=ms else '<'} {s}-day {ms:,.0f}")

    if rule == "momentum":
        lb = params["lookback"]
        if len(c) <= lb:
            return None
        ref = float(c.iloc[-1 - lb])
        x = last / ref - 1.0
        d = 1 if x >= 0 else -1
        return dict(dir=d, strength=_squash(x, 0.15),
                    read=f"{last:,.0f} vs {lb//21}-mo-ago {ref:,.0f} ({x*100:+.1f}%)")

    if rule == "macd":
        macd, signal = _macd(c, params["fast"], params["slow"], params["signal"])
        x = (macd - signal) / (0.01 * last)
        d = 1 if macd >= signal else -1
        return dict(dir=d, strength=_squash(x, 1.0),
                    read=f"MACD {macd:,.1f} {'>' if macd>=signal else '<'} signal {signal:,.1f}")

    if rule == "bollinger":
        n, sd = params["window"], params["std"]
        mid = _sma(c, n)
        std = float(c.tail(n).std(ddof=0))
        lower, upper = mid - sd * std, mid + sd * std
        pctb = (last - lower) / (upper - lower) if upper > lower else 0.5
        if last <= lower:
            d, x = 1, (lower - last) / std  # oversold buy
        elif last >= mid:
            d, x = -1, (last - mid) / std    # reverted -> exit
        else:
            d, x = 1, (mid - last) / std * 0.4
        return dict(dir=d, strength=_squash(x, 1.5),
                    read=f"%B {pctb*100:.0f}% (band {lower:,.0f}–{upper:,.0f})")

    if rule == "rsi_osc":
        r = _rsi(c, params.get("period", 14))
        lo, hi = params.get("low", 30), params.get("high", 70)
        if r <= lo:
            d = 1            # oversold -> classic buy
        elif r >= hi:
            d = -1           # overbought -> classic sell
        else:
            d = 1 if r < 50 else -1
        return dict(dir=d, strength=_squash((50 - r) / 50, 0.6),
                    read=f"RSI(14) {r:.0f}")

    if rule == "rsi_oversold":
        r = _rsi(c, params.get("period", 14))
        ma = _sma(c, params.get("smaWin", 200))
        lo = params.get("low", 30)
        trend_ok = last >= ma
        if r <= lo and trend_ok:
            d, x = 1, (lo - r) / 30
        else:
            d, x = -1, (r - lo) / 40
        return dict(dir=d, strength=_squash(x, 0.6),
                    read=f"RSI(14) {r:.0f}, {'above' if trend_ok else 'below'} 200-day")

    if rule == "sell_in_may":
        in_season = month in (11, 12, 1, 2, 3, 4)
        return dict(dir=1 if in_season else -1, strength=68.0,
                    read=("Winter half (Nov–Apr): invested" if in_season
                          else "Summer half (May–Oct): seasonally weak"))

    if rule == "vix_regime":
        vix = params.get("_vix")
        if vix is None:
            return None
        calm, stress = params["calm"], params["stress"]
        if vix <= calm:
            d, x = 1, (calm - vix) / 10
        elif vix >= stress:
            d, x = -1, (vix - stress) / 15
        else:
            d, x = 1 if vix < (calm + stress) / 2 else -1, 0.0
        return dict(dir=d, strength=_squash(x, 0.8), read=f"VIX {vix:.1f}")

    if rule == "dd_from_high":
        hi = float(c.cummax().iloc[-1])
        dd = last / hi - 1.0
        # Risk budget peaks near the high, fades into deep drawdowns.
        if dd >= -0.05:
            d, x = 1, (0.05 + dd) / 0.05
        elif dd >= -0.20:
            d, x = 1, (0.20 + dd) / 0.30
        else:
            d, x = -1, (-0.20 - dd) / 0.30
        return dict(dir=d, strength=_squash(x, 0.6), read=f"{dd*100:+.1f}% from high")

    return None


def composite(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Trust-weighted vote -> net score, market state, independent leverage."""
    votes = [s for s in states if s["kind"] == "vote" and s.get("state")]
    overlays = [s for s in states if s["kind"] == "overlay" and s.get("state")]
    num = den = 0.0
    for s in votes:
        w = (s["state"]["strength"] / 100.0) * s["reliability"]
        num += s["state"]["dir"] * w
        den += w
    net = num / den if den else 0.0  # -1 (risk-off) .. +1 (risk-on)

    # Overlay risk budget (0..1): average of overlay "risk-on-ness", trust-weighted.
    onum = oden = 0.0
    for s in overlays:
        w = s["reliability"]
        budget = s["state"]["strength"] / 100.0 if s["state"]["dir"] > 0 else 1 - s["state"]["strength"] / 100.0
        onum += budget * w
        oden += w
    risk_budget = onum / oden if oden else 0.6

    # Conviction-gated leverage: merely "risk-on" earns 2x; the 3x top of the
    # scale needs strong conviction AND a calm risk budget. Deep-risk overlays
    # (low budget) trim a notch.
    if net <= -0.2:
        base = 0.0
    elif net < 0.25:
        base = 1.0
    elif net < 0.6:
        base = 2.0
    else:
        base = 3.0
    if base == 3.0 and (net < 0.70 or risk_budget < 0.80):
        base = 2.5
    if base >= 2.0 and risk_budget < 0.50:
        base -= 0.5
    suggested = round(max(0.0, min(3.0, base)) * 2) / 2  # nearest 0.5

    if net >= 0.6:
        label = "Strong Risk-On"
    elif net >= 0.25:
        label = "Risk-On"
    elif net > -0.25:
        label = "Neutral"
    elif net > -0.6:
        label = "Risk-Off"
    else:
        label = "Strong Risk-Off"

    longs = sum(1 for s in votes if s["state"]["dir"] > 0)
    return dict(net=round(net, 3), label=label, suggested_leverage=suggested,
                risk_budget=round(risk_budget, 3),
                longs=longs, total_votes=len(votes))


def load_close(asset: str) -> pd.Series:
    df = pd.read_csv(REPO / f"{asset}_daily.csv")
    return df["Close"].astype(float).reset_index(drop=True)


def current_vix() -> Optional[float]:
    p = REPO / "vix_daily.csv"
    if not p.exists():
        return None
    try:
        return float(pd.read_csv(p)["Close"].astype(float).iloc[-1])
    except Exception:
        return None
