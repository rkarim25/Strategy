"""Signal generators for the SPX SMA-band variant sweep. All return a 0/1 numpy
position-intent array (raw, pre-leverage, pre-signal-lag). The fast engine applies
the 1-day lag, costs, funding and ETP returns.

Conventions (daily close model, no intraday):
  upper band = sma*(1+upper_pct)   lower band = sma*(1-lower_pct)
"""
from __future__ import annotations
import numpy as np


# ---------------------------------------------------------------- base bands
def conv_band(close, sma, upper_pct, lower_pct):
    """Conventional confirmed-trend band (incumbent logic).
    long when close > upper band; cash when close < lower band; hold within band."""
    n = len(close)
    ub = sma * (1.0 + upper_pct)
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if np.isnan(sma[i]):
            out[i] = cur
            continue
        c = close[i]
        if c > ub[i]:
            cur = 1.0
        elif c < lb[i]:
            cur = 0.0
        out[i] = cur
    return out


def early_band(close, sma, upper_pct, lower_pct):
    """Early-in / early-out (user's literal rule).
    Enter (flat->long) when close crosses UP through the lower band (sma*(1-lower)).
    Exit  (long->flat) when close crosses DOWN through the upper band (sma*(1+upper))
                       after having been above it, OR breaks below the lower band."""
    n = len(close)
    ub = sma * (1.0 + upper_pct)
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    cur = 0.0
    for i in range(n):
        if np.isnan(sma[i]) or i == 0 or np.isnan(sma[i - 1]):
            out[i] = cur
            continue
        c, cp = close[i], close[i - 1]
        if cur == 0.0:
            # cross up through lower band
            if cp <= lb[i - 1] and c > lb[i]:
                cur = 1.0
        else:
            cross_down_upper = (cp >= ub[i - 1] and c < ub[i])
            breakdown = c < lb[i]
            if cross_down_upper or breakdown:
                cur = 0.0
        out[i] = cur
    return out


# ---------------------------------------------------------------- stop overlays
def apply_fixed_stop(sig, close, stop_pct):
    """Fixed % stop from entry close. On stop, go flat and block re-entry until the
    base signal cycles back to 0 (a fresh 0->1 is required to re-enter)."""
    if stop_pct <= 0.0:
        return sig
    n = len(sig)
    out = np.zeros(n)
    in_pos = False
    entry = 0.0
    blocked = False
    for i in range(n):
        s = sig[i]
        if not in_pos:
            if blocked:
                if s == 0.0:
                    blocked = False
                out[i] = 0.0
            elif s == 1.0:
                in_pos = True
                entry = close[i]
                out[i] = 1.0
            else:
                out[i] = 0.0
        else:
            if close[i] <= entry * (1.0 - stop_pct):
                in_pos = False
                blocked = (s == 1.0)
                out[i] = 0.0
            elif s == 0.0:
                in_pos = False
                out[i] = 0.0
            else:
                out[i] = 1.0
    return out


def apply_trailing_stop(sig, close, trail_pct):
    """Trailing % stop from the peak close since entry."""
    if trail_pct <= 0.0:
        return sig
    n = len(sig)
    out = np.zeros(n)
    in_pos = False
    peak = 0.0
    blocked = False
    for i in range(n):
        s = sig[i]
        if not in_pos:
            if blocked:
                if s == 0.0:
                    blocked = False
                out[i] = 0.0
            elif s == 1.0:
                in_pos = True
                peak = close[i]
                out[i] = 1.0
            else:
                out[i] = 0.0
        else:
            if close[i] > peak:
                peak = close[i]
            if close[i] <= peak * (1.0 - trail_pct):
                in_pos = False
                blocked = (s == 1.0)
                out[i] = 0.0
            elif s == 0.0:
                in_pos = False
                out[i] = 0.0
            else:
                out[i] = 1.0
    return out


# ---------------------------------------------------------------- variant B
def entry_only_band(close, sma, entry_pct, direction):
    """Position-intent driven by ENTRY only; exit handled by the B/C logic.
    direction 'conv': enter when close>sma*(1+entry). 'early': enter when close
    crosses up through sma*(1-entry). Returns boolean 'entry_trigger' per bar."""
    n = len(close)
    trig = np.zeros(n, dtype=bool)
    if direction == "conv":
        ub = sma * (1.0 + entry_pct)
        for i in range(n):
            if not np.isnan(sma[i]) and close[i] > ub[i]:
                trig[i] = True
    else:  # early: cross up through lower band
        lb = sma * (1.0 - entry_pct)
        for i in range(1, n):
            if np.isnan(sma[i]) or np.isnan(sma[i - 1]):
                continue
            if close[i - 1] <= lb[i - 1] and close[i] > lb[i]:
                trig[i] = True
    return trig


def variant_b_decay(close, sma, entry_pct, direction, N, drop, lower_pct):
    """Enter via band; while long, exit when the premium (close/sma-1) falls by
    >= `drop` from its trailing N-day max (momentum decay -> 'no steam'), or breaks
    below the lower band."""
    n = len(close)
    trig = entry_only_band(close, sma, entry_pct, direction)
    prem = close / sma - 1.0
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    in_pos = False
    hist = []  # premiums since entry (last N)
    for i in range(n):
        if np.isnan(sma[i]):
            out[i] = 1.0 if in_pos else 0.0
            continue
        if not in_pos:
            if trig[i]:
                in_pos = True
                hist = [prem[i]]
                out[i] = 1.0
            else:
                out[i] = 0.0
        else:
            hist.append(prem[i])
            if len(hist) > N:
                hist = hist[-N:]
            tmax = max(hist)
            if (prem[i] <= tmax - drop) or (close[i] < lb[i]):
                in_pos = False
                out[i] = 0.0
            else:
                out[i] = 1.0
    return out


def variant_b_accel(close, sma, entry_pct, direction, N, step, lower_pct):
    """Enter via band; the trade must keep making higher premium-highs: if by N days
    after entry the max premium since entry has not risen by >= `step` above the entry
    premium, cut it. Also exit on breakdown below the lower band."""
    n = len(close)
    trig = entry_only_band(close, sma, entry_pct, direction)
    prem = close / sma - 1.0
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    in_pos = False
    entry_prem = 0.0
    maxp = 0.0
    age = 0
    for i in range(n):
        if np.isnan(sma[i]):
            out[i] = 1.0 if in_pos else 0.0
            continue
        if not in_pos:
            if trig[i]:
                in_pos = True
                entry_prem = prem[i]
                maxp = prem[i]
                age = 0
                out[i] = 1.0
            else:
                out[i] = 0.0
        else:
            age += 1
            if prem[i] > maxp:
                maxp = prem[i]
            no_accel = (age >= N) and (maxp < entry_prem + step)
            if no_accel or (close[i] < lb[i]):
                in_pos = False
                out[i] = 0.0
            else:
                out[i] = 1.0
    return out


# ---------------------------------------------------------------- variant C
def rsi_entry_band_exit(close, sma, rsi_arr, rsi_thr, upper_pct, lower_pct):
    """Enter when RSI crosses up through rsi_thr; exit when close crosses down
    through the upper band (sma*(1+upper)) or breaks below the lower band."""
    n = len(close)
    ub = sma * (1.0 + upper_pct)
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    in_pos = False
    for i in range(1, n):
        if np.isnan(sma[i]) or np.isnan(rsi_arr[i]) or np.isnan(rsi_arr[i - 1]):
            out[i] = 1.0 if in_pos else 0.0
            continue
        if not in_pos:
            if rsi_arr[i - 1] < rsi_thr <= rsi_arr[i]:
                in_pos = True
                out[i] = 1.0
        else:
            cross_down = (close[i - 1] >= ub[i - 1] and close[i] < ub[i])
            if cross_down or close[i] < lb[i]:
                in_pos = False
            else:
                out[i] = 1.0
        if in_pos:
            out[i] = 1.0
    return out


def macd_entry_band_exit(close, sma, macd_line, macd_sig, upper_pct, lower_pct):
    """Enter on bullish MACD crossover (line crosses above signal); exit when close
    crosses down through the upper band or breaks below the lower band."""
    n = len(close)
    ub = sma * (1.0 + upper_pct)
    lb = sma * (1.0 - lower_pct)
    out = np.zeros(n)
    in_pos = False
    for i in range(1, n):
        if np.isnan(sma[i]) or np.isnan(macd_line[i]) or np.isnan(macd_sig[i - 1]):
            out[i] = 1.0 if in_pos else 0.0
            continue
        if not in_pos:
            if macd_line[i - 1] <= macd_sig[i - 1] and macd_line[i] > macd_sig[i]:
                in_pos = True
        else:
            cross_down = (close[i - 1] >= ub[i - 1] and close[i] < ub[i])
            if cross_down or close[i] < lb[i]:
                in_pos = False
        if in_pos:
            out[i] = 1.0
    return out
