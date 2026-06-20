"""Comprehensive gold strategy variant sweep on GC=F (~30y).

Tests trailing ATR, longer SMA, dual timeframe, vol scaling, sell buffers,
Donchian breakout, profit skim, combinations, chandelier, asymmetric MA — vs
Guarded max 1x default. Same engine as backtest_gold_guarded.py.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from analyze_gold_sma_sell_buffer import (
    base_leverage_with_sell_buffer,
    crossed_down,
    guarded_lead_leverage_sell_buffer,
)
from backtest_gold_guarded import (
    buy_hold_row,
    download_gold_panel,
    make_engine,
    run_guarded_1x,
    sma_row,
)
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "gold_strategy_variants"

ATR_K_GRID = [1.5, 2.0, 2.5, 3.0]
SMA_WINDOWS = [30, 50, 100, 200]
VOL_SCALE_GRID = [0.5, 0.75]
PROFIT_THRESHOLDS = [0.10, 0.20, 0.30]
DONCHIAN_WINDOW = 55


def atr_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-style ATR from close-only proxy (high=low=close for gold panel)."""
    px = close.astype(float)
    tr = px.diff().abs()
    tr.iloc[0] = 0.0
    return tr.rolling(period, min_periods=period).mean()


def build_sell_buffer_grid() -> list[float]:
    return [round(v, 4) for v in np.arange(-0.02, 0.0001, 0.001)]


def _cap(value: float, max_leverage: float) -> float:
    return float(min(max(value, 0.0), max_leverage))


@dataclass
class BaseState:
    in_position: bool = False
    entry_high: float = 0.0
    entry_close: float = 0.0
    need_cross_reentry: bool = False
    skim_until_cross: bool = False
    donchian_armed: bool = False


def guarded_lead_loop(
    prices: pd.DataFrame,
    *,
    base_sma_window: int = BASE_SMA_WINDOW,
    max_leverage: float = 1.0,
    regime_gate: pd.Series | None = None,
    vol_scale_series: pd.Series | None = None,
    base_rule: Callable[
        [float, float, float, float, float, BaseState, dict[str, Any]], tuple[float, BaseState]
    ],
    rule_params: dict[str, Any] | None = None,
    trigger_a: float = DEFAULT_GUARDED["trigger_a"],
    trigger_b: float = DEFAULT_GUARDED["trigger_b"],
    lead_pct_below_sma20: float = DEFAULT_GUARDED["lead_pct_below_sma20"],
    x_return: float = DEFAULT_GUARDED["x_return"],
    y_return: float = DEFAULT_GUARDED["y_return"],
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(base_sma_window, min_periods=base_sma_window).mean()
    atr = atr_series(close, 14)
    recovery_guard = (close >= sma * (1.0 - lead_pct_below_sma20)).fillna(False)
    spx_dd = close / close.cummax() - 1.0
    if regime_gate is None:
        regime_gate = pd.Series(True, index=prices.index)
    params = rule_params or {}

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    tier_entry = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0
    state = BaseState()
    prev_px = float("nan")
    prev_sma = float("nan")

    for dt in prices.index:
        px = float(close.loc[dt])
        sma_v = float(sma.loc[dt]) if pd.notna(sma.loc[dt]) else float("nan")
        atr_v = float(atr.loc[dt]) if pd.notna(atr.loc[dt]) else float("nan")
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        gate_ok = bool(regime_gate.loc[dt])

        if gate_ok:
            base_lev, state = base_rule(px, prev_px, sma_v, prev_sma, atr_v, state, params)
        else:
            base_lev, state = 0.0, BaseState()

        if vol_scale_series is not None and base_lev > 0:
            scale = float(vol_scale_series.loc[dt])
            if np.isfinite(scale) and 0 < scale < 1:
                base_lev = base_lev * scale

        base_ok = px > sma_v if np.isfinite(sma_v) else False
        if recovery_ok and not base_ok:
            lead_only_days += 1

        prev_px = px
        prev_sma = sma_v

        if regime == "tier3":
            if px / tier_entry - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = _cap(3.0, max_leverage)
                continue
            guard_blocked_days += 1
            lev.loc[dt] = _cap(base_lev, max_leverage)
            continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                tier_entry = px
                tier3_entries += 1
                lev.loc[dt] = _cap(3.0, max_leverage)
                continue
            if px / tier_entry - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = _cap(2.0, max_leverage)
                continue
            guard_blocked_days += 1
            lev.loc[dt] = _cap(base_lev, max_leverage)
            continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            tier_entry = px
            tier3_entries += 1
            lev.loc[dt] = _cap(3.0, max_leverage)
        elif dd <= -trigger_a and recovery_ok:
            regime = "tier2"
            tier_entry = px
            tier2_entries += 1
            lev.loc[dt] = _cap(2.0, max_leverage)
        else:
            if dd <= -trigger_a and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = _cap(base_lev, max_leverage)

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
    }
    return lev, counts


# --- Base rule implementations ---


def rule_sma_simple(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    in_pos = px > sma if np.isfinite(sma) else False
    return (1.0 if in_pos else 0.0), BaseState(in_position=in_pos)


def rule_atr_trail_entry_sma20(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    k = p["atr_k"]
    if not np.isfinite(sma) or sma <= 0:
        return 0.0, BaseState()
    if st.in_position:
        st.entry_high = max(st.entry_high, px)
        stop = st.entry_high - k * atr if np.isfinite(atr) else float("nan")
        if np.isfinite(stop) and px < stop:
            return 0.0, BaseState()
        return 1.0, st
    if px > sma:
        return 1.0, BaseState(in_position=True, entry_high=px, entry_close=px)
    return 0.0, BaseState()


def rule_sma_window(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    in_pos = px > sma if np.isfinite(sma) else False
    return (1.0 if in_pos else 0.0), BaseState(in_position=in_pos)


def rule_sell_buffer(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    lev, in_pos = base_leverage_with_sell_buffer(
        px, sma, prev_px, prev_sma, in_position=st.in_position, sell_buffer_x=p["sell_buffer_x"]
    )
    return lev, BaseState(in_position=in_pos)


def rule_chandelier_hwm(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    k = p["atr_k"]
    if not np.isfinite(sma) or sma <= 0:
        return 0.0, BaseState()
    if st.in_position:
        st.entry_high = max(st.entry_high, px)
        stop = st.entry_high - k * atr if np.isfinite(atr) else float("nan")
        if np.isfinite(stop) and crossed_down(px, prev_px, stop, stop):
            return 0.0, BaseState()
        return 1.0, st
    if px > sma:
        return 1.0, BaseState(in_position=True, entry_high=px)
    return 0.0, BaseState()


def rule_chandelier_rolling_max(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    """Uses precomputed rolling max in params['rolling_max'] indexed by bar."""
    k = p["atr_k"]
    roll_max = p.get("_roll_max", px)
    if not np.isfinite(sma) or sma <= 0:
        return 0.0, BaseState()
    stop = roll_max - k * atr if np.isfinite(atr) else float("nan")
    prev_stop = p.get("_prev_stop", float("nan"))
    if st.in_position:
        if np.isfinite(stop) and crossed_down(px, prev_px, stop, prev_stop):
            return 0.0, BaseState()
        return 1.0, BaseState(in_position=True)
    if px > sma:
        return 1.0, BaseState(in_position=True)
    return 0.0, BaseState()


def rule_asymmetric_sma20_50(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    sma50 = p.get("_sma50", float("nan"))
    if not np.isfinite(sma):
        return 0.0, BaseState()
    if st.in_position:
        if np.isfinite(sma50) and px <= sma50:
            return 0.0, BaseState()
        return 1.0, st
    if px > sma:
        return 1.0, BaseState(in_position=True)
    return 0.0, BaseState()


def rule_donchian_sma(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    high55 = p.get("_high55", float("nan"))
    prev_high55 = p.get("_prev_high55", float("nan"))
    if not np.isfinite(sma):
        return 0.0, BaseState()
    if st.in_position:
        if px < sma:
            return 0.0, BaseState()
        k = p.get("trail_k")
        if k is not None and np.isfinite(atr):
            st.entry_high = max(st.entry_high, px)
            if px < st.entry_high - k * atr:
                return 0.0, BaseState()
        return 1.0, st
    breakout = (
        np.isfinite(high55)
        and np.isfinite(prev_high55)
        and prev_px < prev_high55
        and px >= high55
        and px > sma
    )
    if breakout:
        return 1.0, BaseState(in_position=True, entry_high=px)
    if px > sma and st.donchian_armed:
        return 1.0, BaseState(in_position=True, entry_high=px)
    return 0.0, BaseState(donchian_armed=st.donchian_armed or (np.isfinite(high55) and px >= high55))


def rule_profit_skim(
    px: float, prev_px: float, sma: float, prev_sma: float, atr: float, st: BaseState, p: dict
) -> tuple[float, BaseState]:
    thresh = p["profit_thresh"]
    after = p["after_lev"]  # 0.0 cash or 0.5
    if not np.isfinite(sma):
        return 0.0, BaseState()
    if st.skim_until_cross:
        if prev_px <= prev_sma and px > sma:
            return 1.0, BaseState(in_position=True, entry_close=px)
        return after, BaseState(skim_until_cross=True)
    if st.in_position:
        if st.entry_close > 0 and px / st.entry_close - 1.0 >= thresh:
            return after, BaseState(skim_until_cross=True)
        if p.get("sell_buffer_x") is not None:
            lev, in_pos = base_leverage_with_sell_buffer(
                px, sma, prev_px, prev_sma, in_position=True, sell_buffer_x=p["sell_buffer_x"]
            )
            if lev <= 0:
                return 0.0, BaseState(entry_close=st.entry_close)
            return lev, BaseState(in_position=True, entry_close=st.entry_close)
        if px <= sma:
            return 0.0, BaseState()
        return 1.0, st
    if p.get("sell_buffer_x") is not None:
        lev, in_pos = base_leverage_with_sell_buffer(
            px, sma, prev_px, prev_sma, in_position=False, sell_buffer_x=p["sell_buffer_x"]
        )
        if in_pos:
            return lev, BaseState(in_position=True, entry_close=px)
        return 0.0, BaseState()
    if px > sma:
        return 1.0, BaseState(in_position=True, entry_close=px)
    return 0.0, BaseState()


def weekly_regime_gate(prices: pd.DataFrame, sma_window: int = 20) -> pd.Series:
    close = prices["spx_close"].astype(float)
    weekly = close.resample("W-FRI").last().dropna()
    w_sma = weekly.rolling(sma_window, min_periods=sma_window).mean()
    regime = (weekly > w_sma).astype(float)
    daily = regime.reindex(close.index, method="ffill").fillna(0.0)
    return daily > 0


def vol_top_quartile_scale(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    ret = close.pct_change()
    vol20 = ret.rolling(20, min_periods=20).std() * np.sqrt(252)
    q75 = vol20.rolling(252, min_periods=126).quantile(0.75)
    high_vol = (vol20 >= q75).fillna(False)
    scale = pd.Series(1.0, index=prices.index)
    scale.loc[high_vol] = np.nan  # filled per variant
    return high_vol


def run_variant_row(
    prices: pd.DataFrame,
    *,
    family: str,
    variant_id: str,
    strategy: str,
    lev: pd.Series,
    params: dict[str, Any] | None = None,
) -> dict[str, object]:
    result = make_engine().run(prices, lev, name=strategy)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    row: dict[str, object] = {
        "family": family,
        "variant_id": variant_id,
        "strategy": strategy,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_cash_sessions": cash["pct_sessions_tbills"],
    }
    if params:
        row["params"] = json.dumps(params, sort_keys=True)
    return row


def guarded_atr_trail(prices: pd.DataFrame, atr_k: float, sma_window: int = 20) -> pd.Series:
    lev, _ = guarded_lead_loop(
        prices,
        base_sma_window=sma_window,
        max_leverage=1.0,
        base_rule=rule_atr_trail_entry_sma20,
        rule_params={"atr_k": atr_k},
    )
    return lev


def guarded_with_buffer(prices: pd.DataFrame, sell_x: float, sma_window: int = 20) -> pd.Series:
    lev, _ = guarded_lead_leverage_sell_buffer(
        prices, sell_buffer_x=sell_x, max_leverage=1.0
    )
    # sell_buffer uses BASE_SMA_WINDOW internally — for longer SMA combos use custom loop
    if sma_window == BASE_SMA_WINDOW:
        return lev
    lev2, _ = guarded_lead_loop(
        prices,
        base_sma_window=sma_window,
        max_leverage=1.0,
        base_rule=rule_sell_buffer,
        rule_params={"sell_buffer_x": sell_x},
    )
    return lev2


def _guarded_chandelier_rolling_impl(prices: pd.DataFrame, atr_k: float) -> pd.Series:
    close = prices["spx_close"].astype(float)
    roll_max = close.rolling(20, min_periods=20).max()
    atr = atr_series(close, 14)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    recovery_guard = (close >= sma20 * (1.0 - DEFAULT_GUARDED["lead_pct_below_sma20"])).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    tier_entry = 0.0
    st = BaseState()
    prev_px = float("nan")
    prev_stop = float("nan")

    for dt in prices.index:
        px = float(close.loc[dt])
        sma = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        atr_v = float(atr.loc[dt]) if pd.notna(atr.loc[dt]) else float("nan")
        rm = float(roll_max.loc[dt]) if pd.notna(roll_max.loc[dt]) else px
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        stop = rm - atr_k * atr_v if np.isfinite(atr_v) else float("nan")
        p = {"atr_k": atr_k, "_roll_max": rm, "_prev_stop": prev_stop}
        base_lev, st = rule_chandelier_rolling_max(px, prev_px, sma, float("nan"), atr_v, st, p)
        prev_stop = stop
        prev_px = px

        ta, tb = DEFAULT_GUARDED["trigger_a"], DEFAULT_GUARDED["trigger_b"]
        xr, yr = DEFAULT_GUARDED["x_return"], DEFAULT_GUARDED["y_return"]
        if regime == "tier3":
            if px / tier_entry - 1.0 >= yr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if regime == "tier2":
            if dd <= -tb and recovery_ok:
                regime = "tier3"
                tier_entry = px
                lev.loc[dt] = 1.0
                continue
            if px / tier_entry - 1.0 >= xr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if dd <= -tb and recovery_ok:
            regime = "tier3"
            tier_entry = px
            lev.loc[dt] = 1.0
        elif dd <= -ta and recovery_ok:
            regime = "tier2"
            tier_entry = px
            lev.loc[dt] = 1.0
        else:
            lev.loc[dt] = base_lev
    return lev


def guarded_donchian(prices: pd.DataFrame, trail_k: float | None = None) -> pd.Series:
    close = prices["spx_close"].astype(float)
    high55 = close.rolling(DONCHIAN_WINDOW, min_periods=DONCHIAN_WINDOW).max()
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    atr = atr_series(close, 14)
    recovery_guard = (close >= sma20 * (1.0 - DEFAULT_GUARDED["lead_pct_below_sma20"])).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    tier_entry = 0.0
    st = BaseState()
    prev_px = float("nan")
    prev_high55 = float("nan")

    for dt in prices.index:
        px = float(close.loc[dt])
        sma = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        atr_v = float(atr.loc[dt]) if pd.notna(atr.loc[dt]) else float("nan")
        h55 = float(high55.loc[dt]) if pd.notna(high55.loc[dt]) else float("nan")
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        p = {"_high55": h55, "_prev_high55": prev_high55, "trail_k": trail_k}
        base_lev, st = rule_donchian_sma(px, prev_px, sma, float("nan"), atr_v, st, p)
        prev_high55 = h55
        prev_px = px

        ta, tb = DEFAULT_GUARDED["trigger_a"], DEFAULT_GUARDED["trigger_b"]
        xr, yr = DEFAULT_GUARDED["x_return"], DEFAULT_GUARDED["y_return"]
        if regime == "tier3":
            if px / tier_entry - 1.0 >= yr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if regime == "tier2":
            if dd <= -tb and recovery_ok:
                regime = "tier3"
                tier_entry = px
                lev.loc[dt] = 1.0
                continue
            if px / tier_entry - 1.0 >= xr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if dd <= -tb and recovery_ok:
            regime = "tier3"
            tier_entry = px
            lev.loc[dt] = 1.0
        elif dd <= -ta and recovery_ok:
            regime = "tier2"
            tier_entry = px
            lev.loc[dt] = 1.0
        else:
            lev.loc[dt] = base_lev
    return lev


def guarded_asymmetric(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()

    def base_rule(px, prev_px, sma, prev_sma, atr, st, p):
        s50 = float(sma50.loc[p["_dt"]]) if pd.notna(sma50.loc[p["_dt"]]) else float("nan")
        p2 = {**p, "_sma50": s50}
        return rule_asymmetric_sma20_50(px, prev_px, sma, prev_sma, atr, st, p2)

    # Use indexed loop
    recovery_guard = (close >= sma20 * (1.0 - DEFAULT_GUARDED["lead_pct_below_sma20"])).fillna(False)
    spx_dd = close / close.cummax() - 1.0
    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    tier_entry = 0.0
    st = BaseState()
    prev_px = float("nan")
    for dt in prices.index:
        px = float(close.loc[dt])
        sma = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        s50 = float(sma50.loc[dt]) if pd.notna(sma50.loc[dt]) else float("nan")
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev, st = rule_asymmetric_sma20_50(px, prev_px, sma, float("nan"), 0.0, st, {"_sma50": s50})
        prev_px = px
        ta, tb = DEFAULT_GUARDED["trigger_a"], DEFAULT_GUARDED["trigger_b"]
        xr, yr = DEFAULT_GUARDED["x_return"], DEFAULT_GUARDED["y_return"]
        if regime == "tier3":
            if px / tier_entry - 1.0 >= yr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if regime == "tier2":
            if dd <= -tb and recovery_ok:
                regime = "tier3"
                tier_entry = px
                lev.loc[dt] = 1.0
                continue
            if px / tier_entry - 1.0 >= xr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 1.0
                continue
            lev.loc[dt] = base_lev
            continue
        if dd <= -tb and recovery_ok:
            regime = "tier3"
            tier_entry = px
            lev.loc[dt] = 1.0
        elif dd <= -ta and recovery_ok:
            regime = "tier2"
            tier_entry = px
            lev.loc[dt] = 1.0
        else:
            lev.loc[dt] = base_lev
    return lev


def collect_all_variants(prices: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def add(family: str, vid: str, name: str, lev: pd.Series, params: dict | None = None):
        rows.append(run_variant_row(prices, family=family, variant_id=vid, strategy=name, lev=lev, params=params))

    # Baselines
    bh = buy_hold_row(prices)
    rows.append({**bh, "family": "baseline", "variant_id": "buy_hold", "params": "{}"})
    sm = sma_row(prices)
    rows.append({**sm, "family": "baseline", "variant_id": "sma20", "params": "{}"})
    g = run_guarded_1x(prices)
    rows.append({**g, "family": "baseline", "variant_id": "guarded_default", "params": "{}"})

    # 1. Trailing ATR exit (Guarded)
    for k in ATR_K_GRID:
        lev = guarded_atr_trail(prices, k)
        add("atr_trail", f"atr_k{k}", f"Guarded ATR trail k={k} (entry>SMA20)", lev, {"atr_k": k})

    # 2. Longer SMA — simple and guarded
    for w in SMA_WINDOWS:
        lev = sma_cash_leverage(prices, w, 1.0)
        add("longer_sma", f"sma{w}_simple", f"SMA{w} 1x/cash", lev, {"sma_window": w})
        lev2, _ = guarded_lead_loop(
            prices, base_sma_window=w, base_rule=rule_sma_window, rule_params={}
        )
        add("longer_sma", f"sma{w}_guarded", f"Guarded SMA{w} base", lev2, {"sma_window": w})

    # 3. Dual timeframe
    gate = weekly_regime_gate(prices)
    lev, _ = guarded_lead_loop(
        prices, regime_gate=gate, base_rule=rule_sma_simple, rule_params={}
    )
    add("dual_timeframe", "weekly_sma20_gate", "Guarded + weekly>SMA20 gate", lev)

    # 4. Vol-scaled exposure
    high_vol = vol_top_quartile_scale(prices)
    for scale in VOL_SCALE_GRID:
        vol_series = pd.Series(1.0, index=prices.index)
        vol_series.loc[high_vol] = scale
        lev, _ = guarded_lead_loop(
            prices, vol_scale_series=vol_series, base_rule=rule_sma_simple, rule_params={}
        )
        add(
            "vol_scaled",
            f"vol_q4_scale{scale}",
            f"Guarded vol-scale {scale}x in top Q4",
            lev,
            {"scale": scale},
        )

    # 5. Sell buffer dense -2% to 0
    for x in build_sell_buffer_grid():
        lev = guarded_with_buffer(prices, x)
        pct = f"{x * 100:.1f}%"
        add(
            "sell_buffer",
            f"buf_{pct.replace('.', 'p').replace('-', 'm')}",
            f"Guarded sell buffer X={x:.3f}",
            lev,
            {"sell_buffer_x": x},
        )

    # 6. Donchian + SMA
    lev = guarded_donchian(prices, trail_k=None)
    add("donchian", "breakout_sma_exit", "Guarded Donchian55+SMA20 exit", lev)
    for k in [2.0, 2.5]:
        lev = guarded_donchian(prices, trail_k=k)
        add("donchian", f"breakout_trail{k}", f"Guarded Donchian+ATR trail k={k}", lev, {"trail_k": k})

    # 7. Profit skim
    for thresh in PROFIT_THRESHOLDS:
        for after, label in [(0.0, "cash"), (0.5, "half")]:
            lev, _ = guarded_lead_loop(
                prices,
                base_rule=rule_profit_skim,
                rule_params={"profit_thresh": thresh, "after_lev": after},
            )
            add(
                "profit_skim",
                f"skim_{int(thresh*100)}_{label}",
                f"Guarded profit skim {int(thresh*100)}% -> {label}",
                lev,
                {"profit_thresh": thresh, "after_lev": after},
            )

    # 8. Combined best candidates
    combos = [
        ("combo_buf09", {"sell_buffer_x": -0.009}, "Guarded + buffer -0.9%"),
        ("combo_buf09_sma50", {"sell_buffer_x": -0.009, "sma_window": 50}, "Guarded buffer -0.9% SMA50"),
        ("combo_atr2_buf09", {"atr_k": 2.0, "sell_buffer_x": -0.009}, "Guarded ATR2 + buffer -0.9%"),
        ("combo_atr25_buf09", {"atr_k": 2.5, "sell_buffer_x": -0.009}, "Guarded ATR2.5 + buffer -0.9%"),
        ("combo_weekly_buf09", {"sell_buffer_x": -0.009, "weekly_gate": True}, "Guarded weekly gate + buffer -0.9%"),
        ("combo_vol75_buf09", {"sell_buffer_x": -0.009, "vol_scale": 0.75}, "Guarded vol0.75 Q4 + buffer -0.9%"),
    ]
    for vid, p, name in combos:
        lev = _run_combo(prices, p)
        add("combined", vid, name, lev, p)

    # 9. Chandelier from rolling max (Guarded)
    for k in ATR_K_GRID:
        lev = _guarded_chandelier_rolling_impl(prices, k)
        add("chandelier_hwm", f"roll_chand_k{k}", f"Guarded chandelier roll20 k={k}", lev, {"atr_k": k})

    # Chandelier entry-SMA style (from high since entry) — family 9 overlap with 1; use distinct id
    for k in ATR_K_GRID:
        lev, _ = guarded_lead_loop(
            prices, base_rule=rule_chandelier_hwm, rule_params={"atr_k": k}
        )
        add("chandelier_entry", f"entry_chand_k{k}", f"Guarded entry-HWM chandelier k={k}", lev, {"atr_k": k})

    # 10. Asymmetric SMA20 buy / SMA50 exit
    lev = guarded_asymmetric(prices)
    add("asymmetric_ma", "sma20_buy_sma50_exit", "Guarded SMA20 in / SMA50 out", lev)

    return rows


def _run_combo(prices: pd.DataFrame, p: dict[str, Any]) -> pd.Series:
    """Combined rules: buffer + optional ATR trail, SMA window, weekly gate, vol scale."""
    sma_w = int(p.get("sma_window", BASE_SMA_WINDOW))
    sell_x = p.get("sell_buffer_x")
    atr_k = p.get("atr_k")
    weekly = p.get("weekly_gate", False)
    vol_scale = p.get("vol_scale")

    gate = weekly_regime_gate(prices) if weekly else None
    vol_series = None
    if vol_scale is not None:
        high_vol = vol_top_quartile_scale(prices)
        vol_series = pd.Series(1.0, index=prices.index)
        vol_series.loc[high_vol] = vol_scale

    def combo_rule(px, prev_px, sma, prev_sma, atr, st, pr):
        if atr_k is not None and st.in_position:
            st.entry_high = max(st.entry_high, px)
            stop = st.entry_high - atr_k * atr if np.isfinite(atr) else float("nan")
            if np.isfinite(stop) and px < stop:
                return 0.0, BaseState()
        if sell_x is not None:
            lev, in_pos = base_leverage_with_sell_buffer(
                px, sma, prev_px, prev_sma, in_position=st.in_position, sell_buffer_x=sell_x
            )
            if st.in_position and lev <= 0:
                return 0.0, BaseState()
            if not st.in_position and in_pos:
                return lev, BaseState(in_position=True, entry_high=px)
            if st.in_position:
                return lev, BaseState(in_position=True, entry_high=max(st.entry_high, px))
            return 0.0, BaseState()
        return rule_sma_simple(px, prev_px, sma, prev_sma, atr, st, pr)

    lev, _ = guarded_lead_loop(
        prices,
        base_sma_window=sma_w,
        regime_gate=gate,
        vol_scale_series=vol_series,
        base_rule=combo_rule,
        rule_params=p,
    )
    return lev


def beats_guarded_all_three(row: pd.Series, baseline: pd.Series) -> bool:
    return (
        float(row["cagr"]) > float(baseline["cagr"])
        and float(row["sharpe"]) > float(baseline["sharpe"])
        and float(row["max_drawdown"]) >= float(baseline["max_drawdown"])
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading gold panel (GC=F)...", flush=True)
    prices = download_gold_panel()
    print(
        f"  {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    print("Running variant sweep...", flush=True)
    rows = collect_all_variants(prices)
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "variants_sweep_results.csv", index=False)

    baseline = df[df["variant_id"] == "guarded_default"].iloc[0]
    variants = df[df["family"] != "baseline"].copy()
    variants["delta_cagr_pp"] = (variants["cagr"] - baseline["cagr"]) * 100.0
    variants["delta_sharpe"] = variants["sharpe"] - baseline["sharpe"]
    variants["delta_max_dd_pp"] = (variants["max_drawdown"] - baseline["max_drawdown"]) * 100.0
    variants["beats_guarded_all_three"] = variants.apply(
        lambda r: beats_guarded_all_three(r, baseline), axis=1
    )

    ranked_sharpe = variants.sort_values(["sharpe", "cagr"], ascending=False)
    ranked_cagr = variants.sort_values("cagr", ascending=False)
    ranked_calmar = variants.sort_values("calmar", ascending=False, na_position="last")
    ranked_sharpe.to_csv(OUTPUT_DIR / "variants_sweep_ranked.csv", index=False)

    winners = variants[variants["beats_guarded_all_three"]]
    best_sharpe = ranked_sharpe.iloc[0]
    best_cagr = ranked_cagr.iloc[0]
    best_calmar = ranked_calmar.iloc[0]

    best_per_family: dict[str, dict] = {}
    for fam in variants["family"].unique():
        sub = variants[variants["family"] == fam].sort_values(["sharpe", "cagr"], ascending=False)
        r = sub.iloc[0]
        best_per_family[fam] = {
            "variant_id": r["variant_id"],
            "strategy": r["strategy"],
            "cagr": float(r["cagr"]),
            "sharpe": float(r["sharpe"]),
            "max_drawdown": float(r["max_drawdown"]),
            "calmar": float(r["calmar"]) if pd.notna(r.get("calmar")) else None,
            "beats_guarded_all_three": bool(r["beats_guarded_all_three"]),
        }

    top20 = ranked_sharpe.head(20)[
        ["family", "variant_id", "strategy", "cagr", "sharpe", "max_drawdown", "calmar", "end_$", "beats_guarded_all_three"]
    ].to_dict(orient="records")
    for t in top20:
        t["cagr_pct"] = f"{t['cagr'] * 100:.2f}%"
        t["max_dd_pct"] = f"{t['max_drawdown'] * 100:.2f}%"

    summary = {
        "baseline_guarded": {
            "cagr": float(baseline["cagr"]),
            "sharpe": float(baseline["sharpe"]),
            "max_drawdown": float(baseline["max_drawdown"]),
            "calmar": float(baseline["calmar"]) if pd.notna(baseline.get("calmar")) else None,
            "end_$": float(baseline["end_$"]),
        },
        "baselines_all": {
            "buy_hold": {k: float(df[df["variant_id"] == "buy_hold"].iloc[0][k]) for k in ("cagr", "sharpe", "max_drawdown")},
            "sma20": {k: float(df[df["variant_id"] == "sma20"].iloc[0][k]) for k in ("cagr", "sharpe", "max_drawdown")},
        },
        "variant_count": int(len(variants)),
        "beats_guarded_all_three_count": int(len(winners)),
        "best_overall_by_sharpe": {
            "strategy": str(best_sharpe["strategy"]),
            "family": str(best_sharpe["family"]),
            "cagr": float(best_sharpe["cagr"]),
            "sharpe": float(best_sharpe["sharpe"]),
            "max_drawdown": float(best_sharpe["max_drawdown"]),
            "beats_guarded_all_three": bool(best_sharpe["beats_guarded_all_three"]),
        },
        "best_overall_by_cagr": {
            "strategy": str(best_cagr["strategy"]),
            "family": str(best_cagr["family"]),
            "cagr": float(best_cagr["cagr"]),
            "sharpe": float(best_cagr["sharpe"]),
            "max_drawdown": float(best_cagr["max_drawdown"]),
            "beats_guarded_all_three": bool(best_cagr["beats_guarded_all_three"]),
        },
        "best_overall_by_calmar": {
            "strategy": str(best_calmar["strategy"]),
            "cagr": float(best_calmar["cagr"]),
            "sharpe": float(best_calmar["sharpe"]),
            "max_drawdown": float(best_calmar["max_drawdown"]),
            "calmar": float(best_calmar["calmar"]) if pd.notna(best_calmar.get("calmar")) else None,
        },
        "best_beating_guarded_all_three": (
            {
                "strategy": str(winners.sort_values("sharpe", ascending=False).iloc[0]["strategy"]),
                "cagr": float(winners.sort_values("sharpe", ascending=False).iloc[0]["cagr"]),
                "sharpe": float(winners.sort_values("sharpe", ascending=False).iloc[0]["sharpe"]),
                "max_drawdown": float(winners.sort_values("sharpe", ascending=False).iloc[0]["max_drawdown"]),
            }
            if len(winners) > 0
            else None
        ),
        "best_per_family": best_per_family,
        "top_20_by_sharpe": top20,
        "winners_all_three": [
            {
                "strategy": str(r["strategy"]),
                "family": str(r["family"]),
                "cagr_pct": f"{r['cagr'] * 100:.2f}%",
                "sharpe": f"{r['sharpe']:.3f}",
                "max_dd_pct": f"{r['max_drawdown'] * 100:.2f}%",
            }
            for _, r in winners.sort_values("sharpe", ascending=False).iterrows()
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n=== Guarded default baseline ===")
    print(
        f"  CAGR {baseline['cagr'] * 100:.2f}%  Sharpe {baseline['sharpe']:.3f}  "
        f"MaxDD {baseline['max_drawdown'] * 100:.2f}%  End ${baseline['end_$']:,.0f}"
    )
    print(f"\n=== Best by Sharpe: {best_sharpe['strategy']} ===")
    print(
        f"  CAGR {best_sharpe['cagr'] * 100:.2f}%  Sharpe {best_sharpe['sharpe']:.3f}  "
        f"MaxDD {best_sharpe['max_drawdown'] * 100:.2f}%  beats all3: {best_sharpe['beats_guarded_all_three']}"
    )
    print(f"\nVariants beating Guarded (CAGR+Sharpe+MaxDD): {len(winners)} / {len(variants)}")
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
