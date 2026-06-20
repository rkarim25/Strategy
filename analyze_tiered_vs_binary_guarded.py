"""Compare tiered Guarded (0/1/2/3x) vs binary 3x-or-cash alternatives.

Runs a full test battery on SPX and NDX using the ETP+VIX cost model:
  1. Full-period strategy grid
  2. Tier decomposition (value of 1x vs 2x vs 3x)
  3. Walk-forward (4 folds)
  4. Block-bootstrap CI on CAGR difference (tiered vs best binary)
  5. Rolling 5-year windows
  6. Crisis-episode drawdowns
  7. Trading-cost sensitivity
  8. Forward Monte Carlo (200 x 10y paths)

Outputs: output/tiered_vs_binary_guarded/
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, TRADING_DAYS
from etp_leverage import bootstrap_etp_paths
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "tiered_vs_binary_guarded"
OUT.mkdir(parents=True, exist_ok=True)

GUARDED_SPEC = dict(
    trigger_a=0.05,
    trigger_b=0.25,
    lead_pct_below_sma20=0.0075,
    x_return=0.40,
    y_return=0.15,
)
SMA_WINDOW = 20
SMA_LONG = 200
SMA_SHORT = 50
VOL_LOOKBACK = 21
ANNUAL_INFLOW = 10.0
TRADING_COST = TRADING_COST_FROM_MID_PCT

CRISIS = [
    ("dotcom", "2000-03-01", "2002-10-31"),
    ("gfc", "2008-09-01", "2009-06-30"),
    ("covid", "2020-02-15", "2020-12-31"),
    ("rate_2022", "2022-01-01", "2022-12-31"),
]

WALK_FOLDS = [
    ("train_96_10", "1996-01-01", "2010-01-01", "2010-01-01", "2026-12-31"),
    ("train_10_26", "2010-01-01", "2026-12-31", "1996-01-01", "2010-01-01"),
    ("holdout_gfc", "1996-01-01", "2007-01-01", "2007-01-01", "2015-01-01"),
    ("holdout_covid", "1996-01-01", "2018-01-01", "2018-01-01", "2026-12-31"),
]


def _load_etp_json(path: Path) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    with path.open() as f:
        ej = json.load(f)
    dates = pd.to_datetime(ej["dates"])
    keys = ("ret_0", "ret_1", "ret_2", "ret_3", "vix")
    return dates, {k: np.asarray(ej[k], dtype=float) for k in keys if k in ej}


def load_asset(name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if name == "NDX":
        csv, etp_json = ROOT / "ndx_daily.csv", ROOT / "ndx_etp_returns.json"
    else:
        csv, etp_json = ROOT / "spx_daily.csv", ROOT / "spx_etp_returns.json"
    df = pd.read_csv(csv, parse_dates=["Date"]).set_index("Date")
    dates, ej = _load_etp_json(etp_json)
    tbill = pd.Series(ej["ret_0"], index=dates) * TRADING_DAYS
    prices = pd.DataFrame(
        {
            "spx_close": df["Close"].astype(float).reindex(dates),
            "tbill_rate": tbill,
            "vix": pd.Series(ej["vix"], index=dates),
        }
    ).dropna()
    etp = pd.DataFrame({k: ej[k] for k in ("ret_0", "ret_1", "ret_2", "ret_3", "vix")}, index=dates)
    etp = etp.reindex(prices.index).ffill()
    etp["synthetic_2"] = False
    etp["synthetic_3"] = False
    return prices, etp


def _rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan)
    if n < w:
        return out
    csum = np.cumsum(x, dtype=float)
    out[w - 1] = csum[w - 1] / w
    out[w:] = (csum[w:] - csum[:-w]) / w
    return out


def fast_guarded_lev(
    close: np.ndarray,
    spx_dd: np.ndarray,
    base_guard: np.ndarray,
    rec_guard: np.ndarray,
    *,
    trigger_a: float,
    trigger_b: float,
    x_return: float,
    y_return: float,
) -> np.ndarray:
    n = len(close)
    lev = np.zeros(n)
    regime = 0
    entry_close = 0.0
    for i in range(n):
        px, dd = close[i], spx_dd[i]
        base_ok, rec_ok = base_guard[i], rec_guard[i]
        base_lev = 1.0 if base_ok else 0.0
        if regime == 2:
            if entry_close > 0 and px / entry_close - 1.0 >= y_return:
                regime = 0
            elif rec_ok:
                lev[i] = 3.0
                continue
            else:
                lev[i] = base_lev
                continue
        if regime == 1:
            if dd <= -trigger_b and rec_ok:
                regime = 2
                entry_close = px
                lev[i] = 3.0
                continue
            if entry_close > 0 and px / entry_close - 1.0 >= x_return:
                regime = 0
            elif rec_ok:
                lev[i] = 2.0
                continue
            else:
                lev[i] = base_lev
                continue
        if dd <= -trigger_b and rec_ok:
            regime = 2
            entry_close = px
            lev[i] = 3.0
        elif dd <= -trigger_a and rec_ok:
            regime = 1
            entry_close = px
            lev[i] = 2.0
        else:
            lev[i] = base_lev
    return lev


def fast_engine(
    close: np.ndarray,
    tbill: np.ndarray,
    ret_0: np.ndarray,
    ret_1: np.ndarray,
    ret_2: np.ndarray,
    ret_3: np.ndarray,
    has_2: np.ndarray,
    has_3: np.ndarray,
    leverage: np.ndarray,
    years: np.ndarray,
    *,
    trading_cost_pct: float = TRADING_COST,
    annual_inflow: float = ANNUAL_INFLOW,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(close)
    spx_ret = np.zeros(n)
    spx_ret[1:] = close[1:] / close[:-1] - 1.0
    equity = np.empty(n)
    port_ret = np.zeros(n)
    aum, prev_lev, prev_year = float(INITIAL_CAPITAL), 1.0, years[0]
    for i in range(n):
        if i > 0 and years[i] != prev_year:
            aum += annual_inflow
            prev_year = years[i]
        lev = float(leverage[i])
        if abs(lev - prev_lev) > 1e-9:
            aum -= abs(lev - prev_lev) * aum * trading_cost_pct
            prev_lev = lev
        if i == 0:
            equity[i] = aum
            continue
        if lev <= 0:
            r = float(ret_0[i])
        elif lev < 1.5:
            r = float(ret_1[i])
        elif lev < 2.5 and has_2[i]:
            r = float(ret_2[i])
        elif lev >= 2.5 and has_3[i]:
            r = float(ret_3[i])
        else:
            r = lev * float(spx_ret[i])
        aum *= 1.0 + r
        equity[i] = aum
        port_ret[i] = r
    return equity, port_ret


def build_signals(prices: pd.DataFrame, tiered: np.ndarray) -> dict[str, np.ndarray]:
    close = prices["spx_close"].to_numpy(dtype=float)
    n = len(close)
    sma20 = _rolling_mean(close, SMA_WINDOW)
    sma50 = _rolling_mean(close, SMA_SHORT)
    sma200 = _rolling_mean(close, SMA_LONG)
    spx_dd = close / np.maximum.accumulate(close) - 1.0
    base_guard = close > sma20
    rec_guard = close >= sma20 * (1.0 - GUARDED_SPEC["lead_pct_below_sma20"])
    base_guard = np.where(np.isnan(sma20), False, base_guard)
    rec_guard = np.where(np.isnan(sma20), False, rec_guard)

    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1.0
    vol = pd.Series(ret).rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std().to_numpy() * np.sqrt(TRADING_DAYS)
    vix = prices["vix"].to_numpy(dtype=float) if "vix" in prices.columns else np.full(n, 15.0)

    signals: dict[str, np.ndarray] = {}
    signals["tiered_default"] = tiered.copy()

    # Binary 3x/cash variants
    signals["binary_always_3x"] = np.full(n, 3.0)
    signals["binary_sma20_3x"] = np.where(base_guard & rec_guard, 3.0, 0.0)
    signals["binary_guarded_lever_only"] = np.where(tiered >= 2.0, 3.0, 0.0)
    signals["binary_guarded_any_invested"] = np.where(tiered > 0, 3.0, 0.0)
    signals["binary_dd5_only"] = np.where((spx_dd <= -0.05) & rec_guard, 3.0, 0.0)
    signals["binary_dd25_only"] = np.where((spx_dd <= -0.25) & rec_guard, 3.0, 0.0)
    trend = (close > sma200) & (sma50 > sma200)
    trend = np.where(np.isnan(sma200) | np.isnan(sma50), False, trend)
    signals["binary_trend_golden"] = np.where(trend, 3.0, 0.0)
    signals["binary_vol_low"] = np.where((vix < 20) & (vol < 0.18), 3.0, 0.0)
    signals["binary_vol_low"] = np.where(np.isnan(vol), 0.0, signals["binary_vol_low"])

    # Tiered ablations
    signals["tiered_cap_2x"] = np.minimum(tiered, 2.0)
    signals["tiered_cap_1x"] = np.minimum(tiered, 1.0)
    signals["tiered_skip_2x"] = np.where(tiered == 2.0, 3.0, tiered)

    return signals


def run_one(
    prices: pd.DataFrame,
    etp: pd.DataFrame,
    leverage: np.ndarray,
    *,
    trading_cost_pct: float = TRADING_COST,
) -> dict:
    close = prices["spx_close"].to_numpy(dtype=float)
    tbill = prices["tbill_rate"].to_numpy(dtype=float)
    years = prices.index.year.to_numpy()
    has_2 = ~etp["synthetic_2"].fillna(True).to_numpy() if "synthetic_2" in etp else np.ones(len(prices), bool)
    has_3 = ~etp["synthetic_3"].fillna(True).to_numpy() if "synthetic_3" in etp else np.ones(len(prices), bool)
    eq, rets = fast_engine(
        close,
        tbill,
        etp["ret_0"].to_numpy(),
        etp["ret_1"].to_numpy(),
        etp["ret_2"].to_numpy(),
        etp["ret_3"].to_numpy(),
        has_2,
        has_3,
        leverage,
        years,
        trading_cost_pct=trading_cost_pct,
    )
    stats = comprehensive_stats(pd.Series(eq, index=prices.index), pd.Series(rets, index=prices.index))
    lev = leverage
    switches = int(np.sum(np.abs(np.diff(lev)) > 0.5))
    return {
        "cagr": stats["cagr"],
        "max_drawdown": stats["max_drawdown"],
        "sharpe": stats["sharpe"],
        "calmar": stats.get("calmar"),
        "end_value": float(eq[-1]),
        "pct_cash": float((lev <= 0).mean() * 100),
        "pct_1x": float((lev == 1.0).mean() * 100),
        "pct_2x": float((lev == 2.0).mean() * 100),
        "pct_3x": float((lev >= 2.5).mean() * 100),
        "switches": switches,
        "equity": eq,
        "returns": rets,
    }


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def money(x: float) -> str:
    if x >= 1e9:
        return f"${x / 1e9:.2f}B"
    if x >= 1e6:
        return f"${x / 1e6:.2f}M"
    if x >= 1e3:
        return f"${x / 1e3:.1f}K"
    return f"${x:,.0f}"


def main() -> None:
    t0 = time.time()
    print("Loading SPX + NDX panels...", flush=True)
    assets: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {
        "SPX": load_asset("SPX"),
        "NDX": load_asset("NDX"),
    }

    strategy_labels = {
        "tiered_default": "Tiered Guarded A5/B25 (default)",
        "binary_always_3x": "Always 3x (no cash filter)",
        "binary_sma20_3x": "Binary: SMA20 on → 3x, else cash",
        "binary_guarded_lever_only": "Binary: Guarded 2x/3x slots → 3x, else cash",
        "binary_guarded_any_invested": "Binary: any Guarded invested day → 3x",
        "binary_dd5_only": "Binary: DD≥5% + recovery → 3x",
        "binary_dd25_only": "Binary: DD≥25% + recovery → 3x",
        "binary_trend_golden": "Binary: SMA50>SMA200 trend → 3x",
        "binary_vol_low": "Binary: low vol/VIX → 3x",
        "tiered_cap_2x": "Tiered ablation: cap at 2x (no 3x tier)",
        "tiered_cap_1x": "Tiered ablation: cap at 1x (no leverage)",
        "tiered_skip_2x": "Tiered ablation: skip 2x (1x→3x jump)",
    }

    # --- Test 1: Full period grid ---
    rows: list[dict] = []
    equity_cache: dict[tuple[str, str], np.ndarray] = {}
    for asset, (prices, etp) in assets.items():
        close = prices["spx_close"].to_numpy(dtype=float)
        sma20 = _rolling_mean(close, SMA_WINDOW)
        spx_dd = close / np.maximum.accumulate(close) - 1.0
        base = close > sma20
        rec = close >= sma20 * (1.0 - GUARDED_SPEC["lead_pct_below_sma20"])
        base = np.where(np.isnan(sma20), False, base)
        rec = np.where(np.isnan(sma20), False, rec)
        tiered = fast_guarded_lev(
            close, spx_dd, base, rec,
            trigger_a=GUARDED_SPEC["trigger_a"],
            trigger_b=GUARDED_SPEC["trigger_b"],
            x_return=GUARDED_SPEC["x_return"],
            y_return=GUARDED_SPEC["y_return"],
        )
        signals = build_signals(prices, tiered)
        for key, lev in signals.items():
            r = run_one(prices, etp, lev)
            equity_cache[(asset, key)] = r["equity"]
            rows.append({
                "asset": asset,
                "strategy_key": key,
                "strategy": strategy_labels[key],
                **{k: r[k] for k in ("cagr", "max_drawdown", "sharpe", "calmar", "end_value",
                                       "pct_cash", "pct_1x", "pct_2x", "pct_3x", "switches")},
            })
    df_full = pd.DataFrame(rows)
    df_full.to_csv(OUT / "test1_full_period.csv", index=False)

    # --- Test 2: Tier decomposition ---
    decomp_rows = []
    for asset in assets:
        base = df_full[(df_full.asset == asset) & (df_full.strategy_key == "tiered_default")].iloc[0]
        for key in ("tiered_cap_1x", "tiered_cap_2x", "tiered_skip_2x", "binary_guarded_any_invested"):
            row = df_full[(df_full.asset == asset) & (df_full.strategy_key == key)].iloc[0]
            decomp_rows.append({
                "asset": asset,
                "variant": key,
                "cagr_delta_vs_tiered": row["cagr"] - base["cagr"],
                "dd_delta_vs_tiered": row["max_drawdown"] - base["max_drawdown"],
                "end_ratio": row["end_value"] / base["end_value"],
            })
    pd.DataFrame(decomp_rows).to_csv(OUT / "test2_tier_decomposition.csv", index=False)

    # --- Test 3: Walk-forward ---
    wf_rows = []
    for asset, (prices, etp) in assets.items():
        for fold_name, tr_s, tr_e, te_s, te_e in WALK_FOLDS:
            train = prices.loc[tr_s:tr_e]
            test = prices.loc[te_s:te_e]
            if len(train) < 500 or len(test) < 200:
                continue
            for key in ("tiered_default", "binary_guarded_lever_only", "binary_sma20_3x", "binary_trend_golden"):
                # rebuild signals on test slice only (no look-ahead from train)
                close_t = test["spx_close"].to_numpy(float)
                sma20_t = _rolling_mean(close_t, SMA_WINDOW)
                dd_t = close_t / np.maximum.accumulate(close_t) - 1.0
                base_t = np.where(np.isnan(sma20_t), False, close_t > sma20_t)
                rec_t = np.where(np.isnan(sma20_t), False, close_t >= sma20_t * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
                tier_t = fast_guarded_lev(close_t, dd_t, base_t, rec_t, **{
                    "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
                    "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
                })
                sigs = build_signals(test, tier_t)
                r = run_one(test, etp.reindex(test.index).ffill(), sigs[key])
                wf_rows.append({
                    "asset": asset, "fold": fold_name, "strategy_key": key,
                    "cagr": r["cagr"], "max_drawdown": r["max_drawdown"],
                    "end_value": r["end_value"], "sharpe": r["sharpe"],
                })
    pd.DataFrame(wf_rows).to_csv(OUT / "test3_walkforward.csv", index=False)

    # --- Test 4: Bootstrap CI (NDX tiered vs best binary by full-sample CAGR) ---
    prices, etp = assets["NDX"]
    ndx_bin = df_full[(df_full.asset == "NDX") & (df_full.strategy_key.str.startswith("binary_"))]
    ndx_bin = ndx_bin[ndx_bin.strategy_key != "binary_always_3x"]
    best_bin_key = ndx_bin.sort_values("cagr", ascending=False).iloc[0]["strategy_key"]
    print(f"NDX best binary (excl always-3x): {best_bin_key}", flush=True)

    ret = prices["spx_close"].pct_change().fillna(0).to_numpy()
    tbill_d = etp["ret_0"].to_numpy()
    block = 21
    rng = np.random.default_rng(20260527)
    starts = np.arange(1, len(ret) - block)
    boot_deltas = []
    for _ in range(500):
        chunks = []
        while sum(len(c) for c in chunks) < len(ret):
            s = int(rng.choice(starts))
            chunks.append(np.arange(s, s + block))
        idx = np.concatenate(chunks)[: len(ret)]
        sub_prices = pd.DataFrame({
            "spx_close": 1000 * np.cumprod(1 + ret[idx]),
            "tbill_rate": prices["tbill_rate"].to_numpy()[idx],
            "vix": prices["vix"].to_numpy()[idx],
        }, index=prices.index)
        sub_etp = etp.iloc[idx].copy()
        sub_etp.index = prices.index
        close_s = sub_prices["spx_close"].to_numpy(float)
        sma20_s = _rolling_mean(close_s, SMA_WINDOW)
        dd_s = close_s / np.maximum.accumulate(close_s) - 1.0
        base_s = np.where(np.isnan(sma20_s), False, close_s > sma20_s)
        rec_s = np.where(np.isnan(sma20_s), False, close_s >= sma20_s * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
        tier_s = fast_guarded_lev(close_s, dd_s, base_s, rec_s, **{
            "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
            "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
        })
        sigs_s = build_signals(sub_prices, tier_s)
        rt = run_one(sub_prices, sub_etp, sigs_s["tiered_default"])
        rb = run_one(sub_prices, sub_etp, sigs_s[best_bin_key])
        boot_deltas.append(rt["cagr"] - rb["cagr"])
    boot_arr = np.array(boot_deltas)
    boot_summary = {
        "best_binary_key": best_bin_key,
        "tiered_wins_pct": float((boot_arr > 0).mean()),
        "mean_cagr_delta_tiered_minus_binary": float(boot_arr.mean()),
        "ci95_low": float(np.quantile(boot_arr, 0.025)),
        "ci95_high": float(np.quantile(boot_arr, 0.975)),
    }
    with (OUT / "test4_bootstrap.json").open("w") as f:
        json.dump(boot_summary, f, indent=2)

    # --- Test 5: Rolling 5yr ---
    roll_rows = []
    for asset, (prices, etp) in assets.items():
        idx = prices.index
        for start_i in range(0, len(idx) - 1260, 252):
            window = prices.iloc[start_i : start_i + 1260]
            if len(window) < 1000:
                continue
            close_w = window["spx_close"].to_numpy(float)
            sma20_w = _rolling_mean(close_w, SMA_WINDOW)
            dd_w = close_w / np.maximum.accumulate(close_w) - 1.0
            base_w = np.where(np.isnan(sma20_w), False, close_w > sma20_w)
            rec_w = np.where(np.isnan(sma20_w), False, close_w >= sma20_w * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
            tier_w = fast_guarded_lev(close_w, dd_w, base_w, rec_w, **{
                "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
                "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
            })
            sigs_w = build_signals(window, tier_w)
            rt = run_one(window, etp.reindex(window.index).ffill(), sigs_w["tiered_default"])
            rb = run_one(window, etp.reindex(window.index).ffill(), sigs_w[best_bin_key])
            roll_rows.append({
                "asset": asset,
                "start": str(window.index[0].date()),
                "tiered_cagr": rt["cagr"],
                "binary_cagr": rb["cagr"],
                "tiered_wins": rt["cagr"] >= rb["cagr"],
            })
    roll_df = pd.DataFrame(roll_rows)
    roll_df.to_csv(OUT / "test5_rolling_5yr.csv", index=False)

    # --- Test 6: Crisis episodes ---
    crisis_rows = []
    for asset, (prices, etp) in assets.items():
        close = prices["spx_close"].to_numpy(float)
        sma20 = _rolling_mean(close, SMA_WINDOW)
        dd = close / np.maximum.accumulate(close) - 1.0
        base = np.where(np.isnan(sma20), False, close > sma20)
        rec = np.where(np.isnan(sma20), False, close >= sma20 * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
        tiered = fast_guarded_lev(close, dd, base, rec, **{
            "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
            "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
        })
        sigs = build_signals(prices, tiered)
        for ep_name, s, e in CRISIS:
            sub = prices.loc[s:e]
            if len(sub) < 20:
                continue
            sub_etp = etp.reindex(sub.index).ffill()
            for key in ("tiered_default", best_bin_key, "binary_guarded_lever_only"):
                # rebuild on sub
                cw = sub["spx_close"].to_numpy(float)
                sm = _rolling_mean(cw, SMA_WINDOW)
                ddw = cw / np.maximum.accumulate(cw) - 1.0
                bw = np.where(np.isnan(sm), False, cw > sm)
                rw = np.where(np.isnan(sm), False, cw >= sm * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
                tw = fast_guarded_lev(cw, ddw, bw, rw, **{
                    "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
                    "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
                })
                sw = build_signals(sub, tw)
                r = run_one(sub, sub_etp, sw[key])
                crisis_rows.append({
                    "asset": asset, "episode": ep_name, "strategy_key": key,
                    "max_dd": r["max_drawdown"], "cagr": r["cagr"],
                })
    pd.DataFrame(crisis_rows).to_csv(OUT / "test6_crisis.csv", index=False)

    # --- Test 7: Cost sensitivity ---
    cost_rows = []
    prices, etp = assets["NDX"]
    close = prices["spx_close"].to_numpy(float)
    sma20 = _rolling_mean(close, SMA_WINDOW)
    dd = close / np.maximum.accumulate(close) - 1.0
    base = np.where(np.isnan(sma20), False, close > sma20)
    rec = np.where(np.isnan(sma20), False, close >= sma20 * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
    tiered = fast_guarded_lev(close, dd, base, rec, **{
        "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
        "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
    })
    sigs = build_signals(prices, tiered)
    for tc in (0.005, 0.01, 0.015, 0.02):
        rt = run_one(prices, etp, sigs["tiered_default"], trading_cost_pct=tc)
        rb = run_one(prices, etp, sigs[best_bin_key], trading_cost_pct=tc)
        cost_rows.append({
            "trading_cost_pct": tc,
            "tiered_cagr": rt["cagr"],
            "binary_cagr": rb["cagr"],
            "tiered_wins": rt["cagr"] > rb["cagr"],
            "cagr_delta": rt["cagr"] - rb["cagr"],
        })
    pd.DataFrame(cost_rows).to_csv(OUT / "test7_cost_sensitivity.csv", index=False)

    # --- Test 8: Forward MC ---
    paths = bootstrap_etp_paths(
        prices, etp, n_sims=100, horizon_days=2520, block_days=21, seed=20260527,
    )
    mc_rows = []
    for sim, (path, path_etp) in enumerate(paths):
        if "vix" not in path.columns and "vix" in prices.columns:
            path = path.copy()
            path["vix"] = prices["vix"].reindex(path.index).ffill().fillna(15.0).values
        cw = path["spx_close"].to_numpy(float)
        sm = _rolling_mean(cw, SMA_WINDOW)
        ddw = cw / np.maximum.accumulate(cw) - 1.0
        bw = np.where(np.isnan(sm), False, cw > sm)
        rw = np.where(np.isnan(sm), False, cw >= sm * (1 - GUARDED_SPEC["lead_pct_below_sma20"]))
        tw = fast_guarded_lev(cw, ddw, bw, rw, **{
            "trigger_a": GUARDED_SPEC["trigger_a"], "trigger_b": GUARDED_SPEC["trigger_b"],
            "x_return": GUARDED_SPEC["x_return"], "y_return": GUARDED_SPEC["y_return"],
        })
        sw = build_signals(path, tw)
        rt = run_one(path, path_etp, sw["tiered_default"])
        rb = run_one(path, path_etp, sw[best_bin_key])
        mc_rows.append({"sim": sim, "tiered_cagr": rt["cagr"], "binary_cagr": rb["cagr"],
                        "tiered_end": rt["end_value"], "binary_end": rb["end_value"]})
    mc_df = pd.DataFrame(mc_rows)
    mc_df.to_csv(OUT / "test8_monte_carlo.csv", index=False)
    mc_summary = {
        "tiered_median_cagr": float(mc_df["tiered_cagr"].median()),
        "binary_median_cagr": float(mc_df["binary_cagr"].median()),
        "tiered_wins_pct": float((mc_df["tiered_cagr"] > mc_df["binary_cagr"]).mean()),
        "tiered_median_end": float(mc_df["tiered_end"].median()),
        "binary_median_end": float(mc_df["binary_end"].median()),
    }
    with (OUT / "test8_mc_summary.json").open("w") as f:
        json.dump(mc_summary, f, indent=2)

    # --- Verdict scoring ---
    tiered_ndx = df_full[(df_full.asset == "NDX") & (df_full.strategy_key == "tiered_default")].iloc[0]
    tiered_spx = df_full[(df_full.asset == "SPX") & (df_full.strategy_key == "tiered_default")].iloc[0]
    best_bin_ndx = df_full[(df_full.asset == "NDX") & (df_full.strategy_key == best_bin_key)].iloc[0]

    tests = []
    tests.append(("Full-period NDX CAGR", tiered_ndx["cagr"] > best_bin_ndx["cagr"],
                  f"tiered {pct(tiered_ndx['cagr'])} vs binary {pct(best_bin_ndx['cagr'])}"))
    tests.append(("Full-period NDX end value", tiered_ndx["end_value"] > best_bin_ndx["end_value"],
                  f"{money(tiered_ndx['end_value'])} vs {money(best_bin_ndx['end_value'])}"))
    tests.append(("Full-period NDX max DD", tiered_ndx["max_drawdown"] >= best_bin_ndx["max_drawdown"],
                  f"{pct(tiered_ndx['max_drawdown'])} vs {pct(best_bin_ndx['max_drawdown'])}"))
    tests.append(("Bootstrap tiered wins", boot_summary["tiered_wins_pct"] > 0.5,
                  f"{boot_summary['tiered_wins_pct']*100:.1f}% of 500 resamples"))
    tests.append(("Rolling 5yr NDX tiered wins", roll_df[roll_df.asset == "NDX"]["tiered_wins"].mean() > 0.5,
                  f"{roll_df[roll_df.asset=='NDX']['tiered_wins'].mean()*100:.1f}% of windows"))
    wf_ndx = pd.DataFrame(wf_rows)
    if len(wf_ndx):
        wf_t = wf_ndx[wf_ndx.strategy_key == "tiered_default"].groupby("fold")["cagr"].first()
        wf_b = wf_ndx[wf_ndx.strategy_key == best_bin_key].groupby("fold")["cagr"].first()
        wf_wins = int((wf_t.values > wf_b.reindex(wf_t.index, fill_value=0).values).sum())
        tests.append(("Walk-forward NDX", wf_wins >= 2, f"tiered wins {wf_wins}/4 folds on test"))
    tests.append(("Cost sensitivity (all costs)", all(pd.read_csv(OUT / "test7_cost_sensitivity.csv")["tiered_wins"]),
                  "tiered ahead at every cost level"))
    tests.append(("MC forward median CAGR", mc_summary["tiered_median_cagr"] > mc_summary["binary_median_cagr"],
                  f"{pct(mc_summary['tiered_median_cagr'])} vs {pct(mc_summary['binary_median_cagr'])}"))

    tiered_pass = sum(1 for _, p, _ in tests if p)
    verdict = "KEEP TIERED DEFAULT" if tiered_pass >= 6 else "BINARY COMPETITIVE — REVIEW"

    # --- Markdown report ---
    lines = [
        "# Tiered Guarded vs Binary 3x/Cash — Full Test Battery\n",
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n",
        f"Runtime: {time.time()-t0:.1f}s\n",
        "## Test 1: Full-period comparison\n",
        "| Asset | Strategy | CAGR | Max DD | End Value | Sharpe | %3x | Switches |",
        "|-------|----------|------|--------|-----------|--------|-----|----------|",
    ]
    for _, row in df_full.sort_values(["asset", "cagr"], ascending=[True, False]).iterrows():
        lines.append(
            f"| {row['asset']} | {row['strategy']} | {pct(row['cagr'])} | {pct(row['max_drawdown'])} "
            f"| {money(row['end_value'])} | {row['sharpe']:.2f} | {row['pct_3x']:.1f}% | {row['switches']} |"
        )
    lines += [
        "\n## Test 2: Tier decomposition (delta vs tiered default)\n",
        pd.read_csv(OUT / "test2_tier_decomposition.csv").to_csv(index=False),
        "\n## Test 4: Bootstrap (NDX tiered vs best binary)\n",
        json.dumps(boot_summary, indent=2),
        "\n## Test 5: Rolling 5yr win rate\n",
        f"NDX tiered wins {roll_df[roll_df.asset=='NDX']['tiered_wins'].mean()*100:.1f}% of windows\n",
        f"SPX tiered wins {roll_df[roll_df.asset=='SPX']['tiered_wins'].mean()*100:.1f}% of windows\n",
        "\n## Test 7: Cost sensitivity (NDX)\n",
        pd.read_csv(OUT / "test7_cost_sensitivity.csv").to_csv(index=False),
        "\n## Test 8: Forward MC summary\n",
        json.dumps(mc_summary, indent=2),
        "\n## Verdict scorecard\n",
        "| Test | Pass? | Detail |",
        "|------|-------|--------|",
    ]
    for name, passed, detail in tests:
        lines.append(f"| {name} | {'YES' if passed else 'NO'} | {detail} |")
    lines.append(f"\n**Overall: {tiered_pass}/{len(tests)} tests favour tiered → {verdict}**\n")

    report = "\n".join(lines)
    (OUT / "final_report.md").write_text(report, encoding="utf-8")

    summary = {
        "verdict": verdict,
        "tiered_pass_count": tiered_pass,
        "total_tests": len(tests),
        "best_binary_ndx": best_bin_key,
        "tiered_ndx": tiered_ndx.to_dict(),
        "best_binary_ndx_row": best_bin_ndx.to_dict(),
        "bootstrap": boot_summary,
        "mc": mc_summary,
    }
    with (OUT / "summary.json").open("w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(report)
    print(f"\nWrote outputs to {OUT}")


if __name__ == "__main__":
    main()
