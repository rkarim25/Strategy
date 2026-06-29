"""Comprehensive SPX SMA-band variant sweep (A/B/C + trailing + extras).
Screens every combo through the validated fast engine, classifies vs a fresh
B&H 1x baseline, and reports only Water/Octane winners that beat the incumbents.
"""
from __future__ import annotations
import sys, time, itertools, json
from pathlib import Path
import numpy as np
import pandas as pd

import backtest_spx_distance_scale as ds
from core.etp_leverage import SPX_ETP, build_etp_return_panel
from core.indicators import sma as sma_ind, rsi as rsi_ind, macd as macd_ind
import signals as S
from fast_engine import fast_metrics

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- data + arrays
print("Loading SPX panel...", flush=True)
P = ds.download_spx_panel()
N = len(P)
close = P["spx_close"].to_numpy(dtype=float)
idx_ret = P["spx_close"].pct_change().to_numpy(dtype=float)
cash_ret = P["tbill_rate"].to_numpy(dtype=float) / 252.0
avg_tbill = float(P["tbill_rate"].mean())
panel = build_etp_return_panel(P, SPX_ETP)
ret2 = panel["ret_2"].to_numpy(dtype=float)
ret3 = panel["ret_3"].to_numpy(dtype=float)
RET_IN = {1: idx_ret, 2: ret2, 3: ret3}

SMA_WINDOWS = [20, 50, 100, 200]
SMAS = {w: sma_ind(P["spx_close"], w).to_numpy(dtype=float) for w in SMA_WINDOWS}
RSI14 = rsi_ind(P["spx_close"], 14).to_numpy(dtype=float)
_ml, _ms, _mh = macd_ind(P["spx_close"])
MACD_LINE = _ml.to_numpy(dtype=float)
MACD_SIG = _ms.to_numpy(dtype=float)
YEARS = (P.index[-1] - P.index[0]).days / 365.25
print(f"  {N} sessions {P.index[0].date()}..{P.index[-1].date()} ({YEARS:.1f}y)", flush=True)

results = []

def evaluate(name, variant, params, raw_sig, lev):
    """raw_sig: 0/1 array. lev in {1,2,3}. Append a result row."""
    applied = raw_sig * lev
    stats, extra = fast_metrics(P, applied, RET_IN[lev], cash_ret, avg_tbill)
    row = {
        "Strategy": name, "Variant": variant, "Leverage": lev,
        "CAGR_pct": stats["cagr"] * 100, "Vol_pct": stats["volatility"] * 100,
        "Sharpe": stats["sharpe"], "Sortino": stats["sortino"],
        "Calmar": stats["calmar"], "MaxDD_pct": stats["max_drawdown"] * 100,
        "End_Value": extra["end_$"], "Trades_Per_Year": extra["trades_per_year"],
        "Total_Trades": extra["total_trades"], "Pct_Cash_Time": extra["pct_days_cash"],
        "Avg_Leverage": extra["avg_leverage"],
    }
    row.update(params)
    results.append(row)

STOPS = [0.0, 0.005, 0.01, 0.015, 0.02]        # none, .5, 1, 1.5, 2 %
TRAILS = [0.0, 0.03, 0.05, 0.08]               # trailing-stop extra
LEVS = [1, 2, 3]
SYM = [(0.01, 0.01), (0.02, 0.02), (0.03, 0.03), (0.05, 0.05)]
ASYM = [(0.03, 0.01), (0.01, 0.03), (0.05, 0.02), (0.02, 0.05),
        (0.03, 0.02), (0.02, 0.03), (0.05, 0.03), (0.03, 0.05)]
BANDS = SYM + ASYM
DIRS = ["conv", "early"]

t0 = time.time()

# ---------------------------------------------------------------- Variant A: band + fixed stop
for direction, w, (up, lo), stop, lev in itertools.product(DIRS, SMA_WINDOWS, BANDS, STOPS, LEVS):
    base = S.conv_band(close, SMAS[w], up, lo) if direction == "conv" else S.early_band(close, SMAS[w], up, lo)
    sig = S.apply_fixed_stop(base, close, stop) if stop > 0 else base
    sl = f" SL{stop*100:.1f}%" if stop > 0 else ""
    nm = f"A {direction} SMA{w} +{up*100:.0f}/-{lo*100:.0f}%{sl} {lev}x"
    evaluate(nm, "A", {"Direction": direction, "SMA": w, "UpBand": up, "LoBand": lo,
                       "Stop": stop, "Trail": 0.0, "Bmode": "", "N": 0, "Param": ""}, sig, lev)
print(f"A done: {len(results)} rows {time.time()-t0:.1f}s", flush=True)

# ---------------------------------------------------------------- Variant A': band + trailing stop
nA = len(results)
for direction, w, (up, lo), trail, lev in itertools.product(DIRS, SMA_WINDOWS, BANDS, TRAILS[1:], LEVS):
    base = S.conv_band(close, SMAS[w], up, lo) if direction == "conv" else S.early_band(close, SMAS[w], up, lo)
    sig = S.apply_trailing_stop(base, close, trail)
    nm = f"A' {direction} SMA{w} +{up*100:.0f}/-{lo*100:.0f}% TS{trail*100:.0f}% {lev}x"
    evaluate(nm, "A-trail", {"Direction": direction, "SMA": w, "UpBand": up, "LoBand": lo,
                             "Stop": 0.0, "Trail": trail, "Bmode": "", "N": 0, "Param": ""}, sig, lev)
print(f"A-trail done: {len(results)-nA} rows {time.time()-t0:.1f}s", flush=True)

# ---------------------------------------------------------------- Variant B: decay / accel
nB = len(results)
B_ENTRY = [0.01, 0.02, 0.03]
B_LOWER = 0.03   # breakdown floor
for direction, w, entry, N_, drop, stop, lev in itertools.product(
        DIRS, SMA_WINDOWS, B_ENTRY, [5, 10, 20], [0.01, 0.02], [0.0, 0.01, 0.02], LEVS):
    base = S.variant_b_decay(close, SMAS[w], entry, direction, N_, drop, B_LOWER)
    sig = S.apply_fixed_stop(base, close, stop) if stop > 0 else base
    sl = f" SL{stop*100:.1f}%" if stop > 0 else ""
    nm = f"B-decay {direction} SMA{w} e{entry*100:.0f}% N{N_} d{drop*100:.0f}%{sl} {lev}x"
    evaluate(nm, "B-decay", {"Direction": direction, "SMA": w, "UpBand": entry, "LoBand": B_LOWER,
                             "Stop": stop, "Trail": 0.0, "Bmode": "decay", "N": N_, "Param": drop}, sig, lev)
for direction, w, entry, N_, step, stop, lev in itertools.product(
        DIRS, SMA_WINDOWS, B_ENTRY, [5, 10, 20], [0.02], [0.0, 0.01, 0.02], LEVS):
    base = S.variant_b_accel(close, SMAS[w], entry, direction, N_, step, B_LOWER)
    sig = S.apply_fixed_stop(base, close, stop) if stop > 0 else base
    sl = f" SL{stop*100:.1f}%" if stop > 0 else ""
    nm = f"B-accel {direction} SMA{w} e{entry*100:.0f}% N{N_} s{step*100:.0f}%{sl} {lev}x"
    evaluate(nm, "B-accel", {"Direction": direction, "SMA": w, "UpBand": entry, "LoBand": B_LOWER,
                             "Stop": stop, "Trail": 0.0, "Bmode": "accel", "N": N_, "Param": step}, sig, lev)
print(f"B done: {len(results)-nB} rows {time.time()-t0:.1f}s", flush=True)

# ---------------------------------------------------------------- Variant C: RSI / MACD entry, band exit
nC = len(results)
C_UPPER = [0.01, 0.03, 0.05]
C_LOWER = 0.03
for w, thr, up, stop, lev in itertools.product(SMA_WINDOWS, [30, 50], C_UPPER, STOPS, LEVS):
    base = S.rsi_entry_band_exit(close, SMAS[w], RSI14, thr, up, C_LOWER)
    sig = S.apply_fixed_stop(base, close, stop) if stop > 0 else base
    sl = f" SL{stop*100:.1f}%" if stop > 0 else ""
    nm = f"C-RSI{thr} SMA{w} exit+{up*100:.0f}%{sl} {lev}x"
    evaluate(nm, "C-rsi", {"Direction": "rsi", "SMA": w, "UpBand": up, "LoBand": C_LOWER,
                           "Stop": stop, "Trail": 0.0, "Bmode": f"rsi{thr}", "N": 14, "Param": thr}, sig, lev)
for w, up, stop, lev in itertools.product(SMA_WINDOWS, C_UPPER, STOPS, LEVS):
    base = S.macd_entry_band_exit(close, SMAS[w], MACD_LINE, MACD_SIG, up, C_LOWER)
    sig = S.apply_fixed_stop(base, close, stop) if stop > 0 else base
    sl = f" SL{stop*100:.1f}%" if stop > 0 else ""
    nm = f"C-MACD SMA{w} exit+{up*100:.0f}%{sl} {lev}x"
    evaluate(nm, "C-macd", {"Direction": "macd", "SMA": w, "UpBand": up, "LoBand": C_LOWER,
                            "Stop": stop, "Trail": 0.0, "Bmode": "macd", "N": 9, "Param": 0}, sig, lev)
print(f"C done: {len(results)-nC} rows {time.time()-t0:.1f}s", flush=True)

# ---------------------------------------------------------------- benchmarks + incumbents (fresh)
def bench(name, applied, lev, variant="benchmark"):
    stats, extra = fast_metrics(P, applied, RET_IN[lev], cash_ret, avg_tbill)
    row = {"Strategy": name, "Variant": variant, "Leverage": lev,
           "CAGR_pct": stats["cagr"]*100, "Vol_pct": stats["volatility"]*100,
           "Sharpe": stats["sharpe"], "Sortino": stats["sortino"], "Calmar": stats["calmar"],
           "MaxDD_pct": stats["max_drawdown"]*100, "End_Value": extra["end_$"],
           "Trades_Per_Year": extra["trades_per_year"], "Total_Trades": extra["total_trades"],
           "Pct_Cash_Time": extra["pct_days_cash"], "Avg_Leverage": extra["avg_leverage"],
           "Direction": "", "SMA": 0, "UpBand": 0, "LoBand": 0, "Stop": 0, "Trail": 0,
           "Bmode": "", "N": 0, "Param": ""}
    return row

ones = np.ones(N)
BH = {1: bench("Buy & Hold 1x", ones, 1), 2: bench("Buy & Hold 2x", ones, 2), 3: bench("Buy & Hold 3x", ones, 3)}
bh1 = BH[1]
# incumbent Water (conv SMA200 +-3% 1x) and Octane (SMA200 +-3% + RSI>20 exit 2x)
inc_water = bench("INC Water: SMA200 +-3% Band 1x/cash", S.conv_band(close, SMAS[200], 0.03, 0.03), 1, "incumbent")
lev_oct, _ = ds.compute_strategy_leverage(P, ds.DEFAULT_SPEC)
inc_oct = bench("INC Octane: SMA200 +-3% + RSI>20 Exit 2x", lev_oct.to_numpy(dtype=float)/2.0, 2, "incumbent")

print(f"\nFRESH baselines on {P.index[0].date()}..{P.index[-1].date()}:")
print(f"  B&H 1x: CAGR {bh1['CAGR_pct']:.2f} Vol {bh1['Vol_pct']:.2f} Sharpe {bh1['Sharpe']:.3f} "
      f"Sortino {bh1['Sortino']:.3f} Calmar {bh1['Calmar']:.3f} DD {bh1['MaxDD_pct']:.2f}")
print(f"  INC Water:  CAGR {inc_water['CAGR_pct']:.2f} Sharpe {inc_water['Sharpe']:.3f} "
      f"Calmar {inc_water['Calmar']:.3f} DD {inc_water['MaxDD_pct']:.2f}")
print(f"  INC Octane: CAGR {inc_oct['CAGR_pct']:.2f} Sharpe {inc_oct['Sharpe']:.3f} "
      f"Calmar {inc_oct['Calmar']:.3f} DD {inc_oct['MaxDD_pct']:.2f} Trades/yr {inc_oct['Trades_Per_Year']:.1f}")

# ---------------------------------------------------------------- classify
df = pd.DataFrame(results)

def classify(r):
    cagr, dd, cal, sh, so, vol, tr = (r.CAGR_pct, r.MaxDD_pct, r.Calmar, r.Sharpe,
                                      r.Sortino, r.Vol_pct, r.Trades_Per_Year)
    not_worse = (sh >= bh1["Sharpe"] and cal >= bh1["Calmar"] and dd >= bh1["MaxDD_pct"]
                 and cagr >= bh1["CAGR_pct"] and so >= bh1["Sortino"] and vol <= bh1["Vol_pct"])
    strictly = (cagr > bh1["CAGR_pct"] or dd > bh1["MaxDD_pct"])
    if not_worse and strictly:
        return "Water"
    if cagr > bh1["CAGR_pct"] and cal > bh1["Calmar"] and dd >= -45.0 and tr <= 30.0:
        return "Octane"
    return "Neither"

df["Class"] = df.apply(classify, axis=1)
df.to_csv(OUT / "spx_band_variants_all.csv", index=False)
print(f"\nTotal strategies: {len(df)}  ({time.time()-t0:.1f}s)")
print(df["Class"].value_counts().to_dict())

# winners that BEAT the incumbents
water = df[df.Class == "Water"].copy()
better_water = water[(water.Sharpe > inc_water["Sharpe"]) | (water.Calmar > inc_water["Calmar"])]
octane = df[df.Class == "Octane"].copy()
better_octane = octane[(octane.Calmar > inc_oct["Calmar"]) |
                       ((octane.CAGR_pct > inc_oct["CAGR_pct"]) & (octane.MaxDD_pct >= -45.0))]

better_water = better_water.sort_values("Sharpe", ascending=False)
better_octane = better_octane.sort_values("Calmar", ascending=False)
print(f"\n=== BETTER WATER ({len(better_water)}) vs INC Sharpe {inc_water['Sharpe']:.3f}/Calmar {inc_water['Calmar']:.3f} ===")
cols = ["Strategy", "CAGR_pct", "Vol_pct", "Sharpe", "Sortino", "Calmar", "MaxDD_pct", "Trades_Per_Year", "Total_Trades"]
with pd.option_context("display.width", 200, "display.max_columns", 20, "display.float_format", lambda x: f"{x:.3f}"):
    print(better_water[cols].head(20).to_string(index=False))
    print(f"\n=== BETTER OCTANE ({len(better_octane)}) vs INC Calmar {inc_oct['Calmar']:.3f}/CAGR {inc_oct['CAGR_pct']:.2f} ===")
    print(better_octane[cols].head(25).to_string(index=False))

# persist winners + baselines
better_water.to_csv(OUT / "spx_better_water.csv", index=False)
better_octane.to_csv(OUT / "spx_better_octane.csv", index=False)
base_df = pd.DataFrame([bh1, BH[2], BH[3], inc_water, inc_oct])
base_df.to_csv(OUT / "spx_baselines.csv", index=False)
print("\nWrote CSVs to", OUT)
