"""Series builders for the shared strategy_page.js renderer (Guarded SMA20-lead, max 1x pages).

The shared front-end renderer (`strategy_page.js`) draws the price/SMA chart, on-chart signal
markers and the rebased %-equity chart from three precomputed series in the page payload:
`price_sma_data`, `signal_history`, `equity_curve`. The Guarded backtests already compute the
daily leverage (`guarded_lead_leverage`) and the engine equity curve in memory; these helpers
just shape them into the JSON the renderer expects. All values are NaN/Inf-sanitised to ``None``
(JSON ``null``) so a stray non-finite never produces invalid JSON that silently blanks the page.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _num(x, nd: int = 4):
    """Round to ``nd`` dp; return None for None/NaN/Inf (so JSON stays valid)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, nd)


def _dates(index: pd.DatetimeIndex) -> list[str]:
    return [d.date().isoformat() for d in index]


def build_price_sma_data(prices: pd.DataFrame, sma_window: int = 20) -> dict:
    """Close + SMA(sma_window) aligned to the price index. Renderer keys off ``sma20`` for the
    Guarded family, so the SMA series name is fixed regardless of the window length."""
    close = prices["spx_close"].astype(float)
    sma = close.rolling(sma_window, min_periods=sma_window).mean()
    return {
        "dates": _dates(prices.index),
        "spx_close": [_num(v) for v in close],
        "sma20": [_num(v) for v in sma],
    }


def build_signal_history(prices: pd.DataFrame, lev: pd.Series, sma_window: int = 20) -> list[dict]:
    """Per-session signal rows. Markers are derived front-end from leverage transitions; the
    ``action`` label here feeds the recent-history table only."""
    close = prices["spx_close"].astype(float)
    sma = close.rolling(sma_window, min_periods=sma_window).mean()
    levv = lev.reindex(prices.index).fillna(0.0)
    out: list[dict] = []
    prev: float | None = None
    for i, d in enumerate(prices.index):
        lv = float(levv.iloc[i])
        if prev is None or lv == prev:
            action = "hold"
        elif lv > prev:
            action = "enter/add"
        else:
            action = "reduce/exit"
        out.append({
            "date": d.date().isoformat(),
            "signal": "long" if lv > 0 else "cash",
            "leverage": round(lv, 2),
            "spx_close": _num(close.iloc[i]),
            "sma20": _num(sma.iloc[i]),
            "action": action,
        })
        prev = lv
    return out


def build_equity_curve(index: pd.DatetimeIndex, strategy_equity: pd.Series, bh_equity: pd.Series) -> dict:
    """Strategy vs buy-and-hold 1x equity, aligned to the price index (the renderer rebases to %)."""
    se = strategy_equity.reindex(index)
    be = bh_equity.reindex(index)
    return {
        "dates": _dates(index),
        "strategy_equity": [_num(v) for v in se],
        "buy_hold_1x_equity": [_num(v) for v in be],
    }


# --- Generic per-asset Water default strategies (sma-cash / band / golden-cross) -------------------
# A `spec` is a small dict picked per asset (see core.site_default_strategy.SITE_DEFAULT_STRATEGY):
#   {"name": "...", "kind": "sma"|"band"|"gc", "window"/"band_pct"/"fast"/"slow"/"leverage": ...}
# These three families are exactly what the shared strategy_page.js renderer already understands
# (sma-cash via `sma_main`, band via `sma200_upper_band`, golden cross via `sma50`/`sma200`).


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def leverage_for(prices: pd.DataFrame, spec: dict) -> pd.Series:
    """Daily leverage series for a Water default strategy spec (matches the front-end rules)."""
    close = prices["spx_close"].astype(float)
    lev_amt = float(spec.get("leverage", 1.0))
    lev = pd.Series(0.0, index=prices.index)
    kind = spec["kind"]
    if kind == "sma":                                  # close > SMA(window) -> in, else cash
        lev.loc[close > _sma(close, spec["window"])] = lev_amt
    elif kind == "gc":                                 # SMA(fast) > SMA(slow) -> in, else cash
        s_fast, s_slow = _sma(close, spec["fast"]), _sma(close, spec["slow"])
        lev.loc[s_fast > s_slow] = lev_amt
        lev.loc[s_slow.isna()] = 0.0
    elif kind == "band":                               # ±band hysteresis around SMA(window)
        sma = _sma(close, spec["window"])
        up, lo = 1.0 + spec["band_pct"], 1.0 - spec["band_pct"]
        cur = 0.0
        vals: list[float] = []
        for i in range(len(close)):
            c, sv = close.iloc[i], sma.iloc[i]
            if not pd.isna(sv):
                if c > sv * up:
                    cur = lev_amt
                elif c < sv * lo:
                    cur = 0.0
            vals.append(cur)
        lev = pd.Series(vals, index=prices.index)
    else:
        raise ValueError(f"Unknown strategy kind: {kind}")
    return lev


def strategy_params_for(spec: dict) -> dict:
    """strategy_params block the renderer keys off (family + window/band for the manual-price recompute)."""
    name = spec["name"]
    lev_amt = float(spec.get("leverage", 1.0))
    if spec["kind"] == "sma":
        return {"strategy": name, "family": "sma_cash", "sma_window": spec["window"], "leverage": lev_amt}
    if spec["kind"] == "band":
        return {"strategy": name, "family": "band", "sma_window": spec["window"],
                "band_pct": spec["band_pct"], "leverage": lev_amt}
    if spec["kind"] == "gc":
        return {"strategy": name, "family": "gc", "fast": spec["fast"], "slow": spec["slow"],
                "octane": False, "leverage": lev_amt}
    raise ValueError(f"Unknown strategy kind: {spec['kind']}")


def build_price_sma_data_for(prices: pd.DataFrame, spec: dict) -> dict:
    """price_sma_data in the exact shape the renderer expects for this strategy's family."""
    close = prices["spx_close"].astype(float)
    out = {"dates": _dates(prices.index), "spx_close": [_num(v) for v in close]}
    if spec["kind"] == "sma":
        out["sma_main"] = [_num(v) for v in _sma(close, spec["window"])]
    elif spec["kind"] == "gc":
        out["sma50"] = [_num(v) for v in _sma(close, spec["fast"])]
        out["sma200"] = [_num(v) for v in _sma(close, spec["slow"])]
    elif spec["kind"] == "band":
        sma = _sma(close, spec["window"])
        band = spec["band_pct"]
        out["sma200"] = [_num(v) for v in sma]
        out["sma200_upper_band"] = [_num(v * (1.0 + band)) for v in sma]
        out["sma200_lower_band"] = [_num(v * (1.0 - band)) for v in sma]
    else:
        raise ValueError(f"Unknown strategy kind: {spec['kind']}")
    return out
