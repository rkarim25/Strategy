"""Gold market-structure backtest sweep: swing detection × topping/bottom rules × integration modes.

Uses GC=F (~30y), $100 start, $10/yr inflow, 1% rebalance cost — same engine as backtest_gold_guarded.py.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED
from backtest_gold_guarded import buy_hold_row, download_gold_panel, make_engine, run_guarded_1x, sma_row
from core.metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW

OUTPUT_DIR = Path("output") / "gold_market_structure"

SWING_FAMILIES = {
    "fractal": [3, 5, 7],
    "pct": [0.02, 0.03, 0.05],
    "atr": [1.0, 1.5, 2.0],
    "zigzag": [0.02, 0.03, 0.05],
}

MID_SWING = {
    "fractal": 5,
    "pct": 0.03,
    "atr": 1.5,
    "zigzag": 0.03,
}


@dataclass(frozen=True)
class SwingPoint:
    bar: int
    price: float
    kind: str  # "H" or "L"
    label: str | None = None  # HH, HL, LH, LL


@dataclass(frozen=True)
class StructureConfig:
    swing_family: str
    swing_param: float
    top_family: str
    top_params: dict
    bottom_family: str
    bottom_params: dict
    integration: str  # structure_only | guarded | sell_only

    def run_id(self) -> str:
        tp = "_".join(f"{k}{v}" for k, v in sorted(self.top_params.items()))
        bp = "_".join(f"{k}{v}" for k, v in sorted(self.bottom_params.items()))
        sp = str(self.swing_param).replace(".", "p")
        return f"{self.swing_family}_{sp}__top_{self.top_family}_{tp}__bot_{self.bottom_family}_{bp}__{self.integration}"


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _label_swings(swings: list[SwingPoint]) -> list[SwingPoint]:
    out: list[SwingPoint] = []
    prev_h: float | None = None
    prev_l: float | None = None
    for sp in swings:
        label: str | None = None
        if sp.kind == "H" and prev_h is not None:
            label = "HH" if sp.price > prev_h else "LH"
            prev_h = sp.price
        elif sp.kind == "H":
            prev_h = sp.price
        elif sp.kind == "L" and prev_l is not None:
            label = "HL" if sp.price > prev_l else "LL"
            prev_l = sp.price
        elif sp.kind == "L":
            prev_l = sp.price
        out.append(SwingPoint(sp.bar, sp.price, sp.kind, label))
    return out


def swings_fractal(high: np.ndarray, low: np.ndarray, n: int) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    length = len(high)
    for i in range(n, length - n):
        window_h = high[i - n : i + n + 1]
        window_l = low[i - n : i + n + 1]
        if high[i] >= window_h.max() and np.sum(window_h == high[i]) == 1:
            swings.append(SwingPoint(i, float(high[i]), "H"))
        if low[i] <= window_l.min() and np.sum(window_l == low[i]) == 1:
            swings.append(SwingPoint(i, float(low[i]), "L"))
    swings.sort(key=lambda s: s.bar)
    merged: list[SwingPoint] = []
    for sp in swings:
        if merged and merged[-1].bar == sp.bar:
            continue
        if merged and merged[-1].kind == sp.kind:
            if sp.kind == "H" and sp.price > merged[-1].price:
                merged[-1] = sp
            elif sp.kind == "L" and sp.price < merged[-1].price:
                merged[-1] = sp
        else:
            merged.append(sp)
    return _label_swings(merged)


def swings_pct_reversal(close: np.ndarray, pct: float) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    if len(close) < 2:
        return swings
    direction = 0  # 1 up leg, -1 down leg
    extreme_idx = 0
    extreme_px = float(close[0])
    for i in range(1, len(close)):
        px = float(close[i])
        if direction == 0:
            if px > extreme_px:
                extreme_idx, extreme_px, direction = i, px, 1
            elif px < extreme_px:
                extreme_idx, extreme_px, direction = i, px, -1
            continue
        if direction == 1:
            if px >= extreme_px:
                extreme_idx, extreme_px = i, px
            elif px <= extreme_px * (1.0 - pct):
                swings.append(SwingPoint(extreme_idx, extreme_px, "H"))
                extreme_idx, extreme_px, direction = i, px, -1
        else:
            if px <= extreme_px:
                extreme_idx, extreme_px = i, px
            elif px >= extreme_px * (1.0 + pct):
                swings.append(SwingPoint(extreme_idx, extreme_px, "L"))
                extreme_idx, extreme_px, direction = i, px, 1
    return _label_swings(swings)


def swings_atr_reversal(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, k: float
) -> list[SwingPoint]:
    atr = _atr(high, low, close, 14)
    swings: list[SwingPoint] = []
    if len(close) < 2:
        return swings
    direction = 0
    extreme_idx = 0
    extreme_px = float(close[0])
    for i in range(1, len(close)):
        px = float(close[i])
        if direction == 0:
            if px > extreme_px:
                extreme_idx, extreme_px, direction = i, px, 1
            elif px < extreme_px:
                extreme_idx, extreme_px, direction = i, px, -1
            continue
        thr = k * float(atr[extreme_idx]) if np.isfinite(atr[extreme_idx]) else k * px * 0.02
        if thr <= 0:
            thr = px * 0.02
        if direction == 1:
            if px >= extreme_px:
                extreme_idx, extreme_px = i, px
            elif px <= extreme_px - thr:
                swings.append(SwingPoint(extreme_idx, extreme_px, "H"))
                extreme_idx, extreme_px, direction = i, px, -1
        else:
            if px <= extreme_px:
                extreme_idx, extreme_px = i, px
            elif px >= extreme_px + thr:
                swings.append(SwingPoint(extreme_idx, extreme_px, "L"))
                extreme_idx, extreme_px, direction = i, px, 1
    return _label_swings(swings)


def swings_zigzag(high: np.ndarray, low: np.ndarray, pct: float) -> list[SwingPoint]:
    """ZigZag on high/low extremes (pct move to confirm pivot)."""
    if len(high) == 0:
        return []
    swings: list[SwingPoint] = []
    direction = 0
    extreme_idx = 0
    extreme_px = float(high[0])
    for i in range(1, len(high)):
        hi, lo = float(high[i]), float(low[i])
        if direction == 0:
            if hi > extreme_px:
                extreme_idx, extreme_px, direction = i, hi, 1
            if lo < extreme_px:
                extreme_idx, extreme_px, direction = i, lo, -1
            continue
        if direction == 1:
            if hi >= extreme_px:
                extreme_idx, extreme_px = i, hi
            elif lo <= extreme_px * (1.0 - pct):
                swings.append(SwingPoint(extreme_idx, extreme_px, "H"))
                extreme_idx, extreme_px, direction = i, lo, -1
        else:
            if lo <= extreme_px:
                extreme_idx, extreme_px = i, lo
            elif hi >= extreme_px * (1.0 + pct):
                swings.append(SwingPoint(extreme_idx, extreme_px, "L"))
                extreme_idx, extreme_px, direction = i, hi, 1
    return _label_swings(swings)


def detect_swings(
    prices: pd.DataFrame, family: str, param: float
) -> list[SwingPoint]:
    close = prices["spx_close"].astype(float).to_numpy()
    high = close.copy()
    low = close.copy()
    if family == "fractal":
        return swings_fractal(high, low, int(param))
    if family == "pct":
        return swings_pct_reversal(close, float(param))
    if family == "atr":
        return swings_atr_reversal(high, low, close, float(param))
    if family == "zigzag":
        return swings_zigzag(high, low, float(param))
    raise ValueError(f"Unknown swing family: {family}")


def _swing_events_by_bar(swings: list[SwingPoint], index: pd.Index) -> dict[int, list[SwingPoint]]:
    by_bar: dict[int, list[SwingPoint]] = {}
    for sp in swings:
        by_bar.setdefault(sp.bar, []).append(sp)
    return by_bar


def generate_structure_signals(
    prices: pd.DataFrame,
    swings: list[SwingPoint],
    *,
    top_family: str,
    top_params: dict,
    bottom_family: str,
    bottom_params: dict,
) -> tuple[pd.Series, pd.Series]:
    """Return (entry_signal, exit_signal) boolean Series aligned to prices.index."""
    index = prices.index
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    n = len(index)
    entry = np.zeros(n, dtype=bool)
    exit_ = np.zeros(n, dtype=bool)
    by_bar = _swing_events_by_bar(swings, index)

    hh_hl_streak = 0
    ll_lh_streak = 0
    hl_count_uptrend = 0
    hl_stack = 0
    topped_armed = False
    last_swing_high: float | None = None
    failed_hh_idx: int | None = None
    failed_hh_level: float | None = None
    spring_ll_level: float | None = None
    spring_deadline: int | None = None
    saw_hl_for_reversal = False

    k_top = int(top_params.get("k", 3))
    exit_mode = top_params.get("exit", "LH_LL")
    m_top = int(top_params.get("m", 5))
    n_hl_req = int(top_params.get("n_hl", 2))
    ext_pct = float(top_params.get("ext_pct", 0.0))
    k_bot = int(bottom_params.get("k", 3))
    m_bot = int(bottom_params.get("m", 5))
    hl_stack_req = int(bottom_params.get("hl_stack", 2))

    def _classic_exit(lbl: str | None) -> bool:
        if not lbl or not topped_armed or top_family != "classic":
            return False
        if exit_mode == "LH":
            return lbl == "LH"
        if exit_mode == "LL":
            return lbl == "LL"
        return lbl in ("LH", "LL")

    def _bearish_exit(lbl: str | None) -> bool:
        return bool(lbl in ("LH", "LL") and topped_armed and top_family in ("hl_decay", "extension"))

    for i in range(n):
        px = float(close.iloc[i])
        sma = float(sma20.iloc[i]) if pd.notna(sma20.iloc[i]) else float("nan")
        extension_ok = not np.isfinite(sma) or sma <= 0 or px >= sma * (1.0 + ext_pct)

        if spring_deadline is not None and i > spring_deadline:
            spring_ll_level = None
            spring_deadline = None

        if spring_ll_level is not None and px > spring_ll_level:
            if bottom_family == "spring":
                entry[i] = True
            spring_ll_level = None
            spring_deadline = None

        if failed_hh_idx is not None:
            if i - failed_hh_idx <= m_top and failed_hh_level is not None and px < failed_hh_level:
                if top_family == "failed_hh" and hh_hl_streak >= 1:
                    exit_[i] = True
                    topped_armed = False
                failed_hh_idx = None
                failed_hh_level = None
            elif i - failed_hh_idx > m_top:
                failed_hh_idx = None
                failed_hh_level = None

        for sp in by_bar.get(i, []):
            lbl = sp.label
            if not lbl:
                continue

            # --- exits (evaluate before streak resets) ---
            if _classic_exit(lbl) or _bearish_exit(lbl):
                exit_[i] = True
                topped_armed = False
                hh_hl_streak = 0
                hl_count_uptrend = 0

            if top_family == "hl_decay" and hl_count_uptrend >= n_hl_req and lbl in ("LH", "LL"):
                exit_[i] = True
                topped_armed = False
                hh_hl_streak = 0
                hl_count_uptrend = 0

            # --- entries ---
            if bottom_family == "capitulation" and lbl == "HL" and ll_lh_streak >= k_bot:
                entry[i] = True

            if bottom_family == "full_reversal" and lbl == "HH" and saw_hl_for_reversal:
                entry[i] = True
                saw_hl_for_reversal = False

            if bottom_family == "hl_stack" and lbl == "HL" and hl_stack >= hl_stack_req - 1:
                entry[i] = True

            # --- update structure state ---
            if lbl in ("HH", "HL"):
                if lbl == "HL":
                    if bottom_family == "capitulation" and ll_lh_streak >= k_bot:
                        pass  # entry already handled
                    ll_lh_streak = 0
                    hl_stack += 1
                    hl_count_uptrend += 1
                    saw_hl_for_reversal = True
                elif lbl == "HH":
                    hl_stack = 0
                hh_hl_streak += 1
                if lbl == "HH":
                    if top_family == "failed_hh" and hh_hl_streak >= 1 and last_swing_high is not None:
                        failed_hh_idx = i
                        failed_hh_level = last_swing_high
                    last_swing_high = sp.price

                arm = hh_hl_streak >= k_top
                if top_family == "extension":
                    arm = arm and extension_ok
                if arm and top_family in ("classic", "hl_decay", "extension"):
                    topped_armed = True

            elif lbl in ("LL", "LH"):
                if lbl == "LH":
                    ll_lh_streak += 1
                elif lbl == "LL":
                    ll_lh_streak += 1
                    if bottom_family == "spring":
                        spring_ll_level = sp.price
                        spring_deadline = i + m_bot

                hh_hl_streak = 0
                hl_count_uptrend = 0
                hl_stack = 0
                topped_armed = False
                saw_hl_for_reversal = False
                failed_hh_idx = None

    return pd.Series(entry, index=index), pd.Series(exit_, index=index)


def structure_only_leverage(
    prices: pd.DataFrame, entry: pd.Series, exit_: pd.Series
) -> tuple[pd.Series, dict[str, float | int]]:
    lev = pd.Series(0.0, index=prices.index)
    in_pos = False
    entries = 0
    exits = 0
    for dt in prices.index:
        if bool(exit_.loc[dt]) and in_pos:
            in_pos = False
            exits += 1
        if bool(entry.loc[dt]) and not in_pos:
            in_pos = True
            entries += 1
        lev.loc[dt] = 1.0 if in_pos else 0.0
    return lev, {"structure_entries": entries, "structure_exits": exits, "pct_days_cash": float((lev <= 0).mean() * 100.0)}


def sell_only_structure_leverage(
    prices: pd.DataFrame, exit_: pd.Series
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    lev = pd.Series(0.0, index=prices.index)
    in_pos = False
    exits = 0
    for dt in prices.index:
        px = float(close.loc[dt])
        ma = float(sma.loc[dt]) if pd.notna(sma.loc[dt]) else float("nan")
        if in_pos and bool(exit_.loc[dt]):
            in_pos = False
            exits += 1
        elif not in_pos and np.isfinite(ma) and px > ma:
            in_pos = True
        lev.loc[dt] = 1.0 if in_pos else 0.0
    return lev, {"structure_exits": exits, "pct_days_cash": float((lev <= 0).mean() * 100.0)}


def guarded_structure_leverage(
    prices: pd.DataFrame,
    entry: pd.Series,
    exit_: pd.Series,
    *,
    max_leverage: float = 1.0,
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    recovery_guard = (close >= sma20 * (1.0 - DEFAULT_GUARDED["lead_pct_below_sma20"])).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    structure_blocked = False
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0
    structure_entries = 0
    structure_exits = 0

    def cap(value: float) -> float:
        return float(min(max(value, 0.0), max_leverage))

    for dt in prices.index:
        px = float(close.loc[dt])
        sma = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_ok = px > sma if np.isfinite(sma) else False

        if bool(exit_.loc[dt]):
            structure_blocked = True
            structure_exits += 1
        if bool(entry.loc[dt]):
            structure_blocked = False
            structure_entries += 1

        if structure_blocked:
            base_lev = 0.0
        elif base_ok or bool(entry.loc[dt]):
            base_lev = 1.0
        else:
            base_lev = 0.0

        if recovery_ok and not base_ok and not structure_blocked:
            lead_only_days += 1

        ta = DEFAULT_GUARDED["trigger_a"]
        tb = DEFAULT_GUARDED["trigger_b"]
        xr = DEFAULT_GUARDED["x_return"]
        yr = DEFAULT_GUARDED["y_return"]

        if regime == "tier3":
            if px / entry_close - 1.0 >= yr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(3.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if regime == "tier2":
            if dd <= -tb and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = cap(3.0)
                continue
            if px / entry_close - 1.0 >= xr:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(2.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if dd <= -tb and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = cap(3.0)
        elif dd <= -ta and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = cap(2.0)
        else:
            if dd <= -ta and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = cap(base_lev)

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "structure_entries": structure_entries,
        "structure_exits": structure_exits,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
    }
    return lev, counts


def build_leverage(
    prices: pd.DataFrame,
    cfg: StructureConfig,
    swings: list[SwingPoint],
) -> tuple[pd.Series, dict[str, float | int]]:
    entry, exit_ = generate_structure_signals(
        prices,
        swings,
        top_family=cfg.top_family,
        top_params=cfg.top_params,
        bottom_family=cfg.bottom_family,
        bottom_params=cfg.bottom_params,
    )
    if cfg.integration == "structure_only":
        return structure_only_leverage(prices, entry, exit_)
    if cfg.integration == "sell_only":
        return sell_only_structure_leverage(prices, exit_)
    if cfg.integration == "guarded":
        return guarded_structure_leverage(prices, entry, exit_, max_leverage=1.0)
    raise ValueError(cfg.integration)


def run_structure_row(prices: pd.DataFrame, cfg: StructureConfig, swings: list[SwingPoint]) -> dict[str, object]:
    lev, counts = build_leverage(prices, cfg, swings)
    name = cfg.run_id()
    result = make_engine().run(prices, lev, name=name)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    row: dict[str, object] = {
        "run_id": name,
        "swing_family": cfg.swing_family,
        "swing_param": cfg.swing_param,
        "top_family": cfg.top_family,
        "top_params": json.dumps(cfg.top_params, sort_keys=True),
        "bottom_family": cfg.bottom_family,
        "bottom_params": json.dumps(cfg.bottom_params, sort_keys=True),
        "integration": cfg.integration,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "rebalances": result.rebalance_count,
        "swing_count": len(swings),
    }
    row.update(counts)
    return row


def baseline_rows(prices: pd.DataFrame) -> list[dict[str, object]]:
    bh = buy_hold_row(prices)
    sma = sma_row(prices)
    guarded = run_guarded_1x(prices)
    rows = []
    for src, integration in (
        (bh, "baseline"),
        (sma, "baseline"),
        (guarded, "baseline"),
    ):
        rows.append(
            {
                "run_id": src["strategy"],
                "swing_family": "baseline",
                "swing_param": np.nan,
                "top_family": "none",
                "top_params": "{}",
                "bottom_family": "none",
                "bottom_params": "{}",
                "integration": integration,
                "cagr": src["cagr"],
                "ann_volatility": src.get("ann_volatility"),
                "sharpe": src["sharpe"],
                "max_drawdown": src["max_drawdown"],
                "calmar": src.get("calmar"),
                "end_$": src["end_$"],
                "pct_days_cash": src.get("pct_days_cash", 0.0),
                "rebalances": src.get("rebalances"),
                "swing_count": np.nan,
            }
        )
    return rows


def canonical_top() -> tuple[str, dict]:
    return "classic", {"k": 3, "exit": "LH_LL"}


def canonical_bottom() -> tuple[str, dict]:
    return "capitulation", {"k": 3}


def iter_topping_variants() -> Iterator[tuple[str, dict]]:
    for k in (2, 3, 4):
        for exit_mode in ("LH", "LL", "LH_LL"):
            yield "classic", {"k": k, "exit": exit_mode}
    for m in (3, 5):
        yield "failed_hh", {"m": m}
    for n_hl in (2, 3):
        yield "hl_decay", {"n_hl": n_hl, "k": 3}
    for ext_pct in (0.0, 0.05, 0.10):
        for k in (2, 3):
            yield "extension", {"ext_pct": ext_pct, "k": k}


def iter_bottom_variants() -> Iterator[tuple[str, dict]]:
    for k in (2, 3):
        yield "capitulation", {"k": k}
    yield "full_reversal", {}
    for m in (3, 5):
        yield "spring", {"m": m}
    for hl_stack in (2, 3):
        yield "hl_stack", {"hl_stack": hl_stack}


def build_sweep_configs() -> list[StructureConfig]:
    configs: list[StructureConfig] = []
    top_c, top_p = canonical_top()
    bot_c, bot_p = canonical_bottom()
    integrations_core = ("structure_only", "guarded", "sell_only")
    integrations_extra = ("structure_only", "guarded")

    # Core: every swing param × canonical top/bottom × all integration modes
    for family, params in SWING_FAMILIES.items():
        for param in params:
            for integration in integrations_core:
                configs.append(
                    StructureConfig(family, float(param), top_c, dict(top_p), bot_c, dict(bot_p), integration)
                )

    # Topping sweep at mid swing for each family
    for family in SWING_FAMILIES:
        sp = MID_SWING[family]
        for top_f, top_parms in iter_topping_variants():
            for integration in integrations_extra:
                configs.append(
                    StructureConfig(
                        family, float(sp), top_f, dict(top_parms), bot_c, dict(bot_p), integration
                    )
                )

    # Bottom sweep at mid swing for each family
    for family in SWING_FAMILIES:
        sp = MID_SWING[family]
        sweep_top_c, sweep_top_p = canonical_top()
        for bot_f, bot_parms in iter_bottom_variants():
            for integration in integrations_extra:
                configs.append(
                    StructureConfig(
                        family, float(sp), sweep_top_c, dict(sweep_top_p), bot_f, dict(bot_parms), integration
                    )
                )

    # Deduplicate
    seen: set[str] = set()
    unique: list[StructureConfig] = []
    for cfg in configs:
        rid = cfg.run_id()
        if rid not in seen:
            seen.add(rid)
            unique.append(cfg)
    return unique


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading gold panel (GC=F)...", flush=True)
    prices = download_gold_panel()
    print(
        f"  {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    rows: list[dict[str, object]] = baseline_rows(prices)
    configs = build_sweep_configs()
    print(f"Running {len(configs)} structure configurations...", flush=True)

    swing_cache: dict[tuple[str, float], list[SwingPoint]] = {}
    for i, cfg in enumerate(configs):
        if i % 50 == 0:
            print(f"  config {i + 1}/{len(configs)}: {cfg.run_id()}", flush=True)
        key = (cfg.swing_family, cfg.swing_param)
        if key not in swing_cache:
            swing_cache[key] = detect_swings(prices, cfg.swing_family, cfg.swing_param)
        rows.append(run_structure_row(prices, cfg, swing_cache[key]))

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "structure_sweep_results.csv", index=False)

    structure_df = df[df["swing_family"] != "baseline"].copy()
    # Exclude near-all-cash degenerate runs (inflated Sharpe from ~0 vol)
    realistic = structure_df[
        (structure_df["pct_days_cash"] < 95.0) & (structure_df["max_drawdown"] < -0.02)
    ]
    ranked = realistic.sort_values(["sharpe", "calmar"], ascending=[False, False], na_position="last")
    ranked.to_csv(OUTPUT_DIR / "structure_sweep_ranked.csv", index=False)

    guarded_baseline = df[df["run_id"].str.contains("Guarded A5", na=False)].iloc[0]
    best = ranked.iloc[0] if len(ranked) else None

    best_per_swing: dict[str, dict] = {}
    for family in SWING_FAMILIES:
        sub = ranked[ranked["swing_family"] == family]
        if len(sub):
            r = sub.iloc[0]
            best_per_swing[family] = {
                "run_id": r["run_id"],
                "swing_param": r["swing_param"],
                "sharpe": float(r["sharpe"]),
                "cagr": float(r["cagr"]),
                "max_drawdown": float(r["max_drawdown"]),
                "integration": r["integration"],
            }

    best_per_top: dict[str, dict] = {}
    for top_f in ("classic", "failed_hh", "hl_decay", "extension"):
        sub = ranked[ranked["top_family"] == top_f]
        if len(sub):
            r = sub.iloc[0]
            best_per_top[top_f] = {
                "run_id": r["run_id"],
                "sharpe": float(r["sharpe"]),
                "cagr": float(r["cagr"]),
                "max_drawdown": float(r["max_drawdown"]),
            }

    best_per_bottom: dict[str, dict] = {}
    for bot_f in ("capitulation", "full_reversal", "spring", "hl_stack"):
        sub = ranked[ranked["bottom_family"] == bot_f]
        if len(sub):
            r = sub.iloc[0]
            best_per_bottom[bot_f] = {
                "run_id": r["run_id"],
                "sharpe": float(r["sharpe"]),
                "cagr": float(r["cagr"]),
                "max_drawdown": float(r["max_drawdown"]),
            }

    beats_guarded = realistic[
        (realistic["cagr"] > guarded_baseline["cagr"])
        & (realistic["sharpe"] > guarded_baseline["sharpe"])
        & (realistic["max_drawdown"] >= guarded_baseline["max_drawdown"])
    ]

    summary = {
        "sample": {
            "ticker": "GC=F",
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "baselines": {
            "buy_hold_1x": {
                k: float(df[df["run_id"] == "Buy & hold 1x"].iloc[0][k])
                for k in ("cagr", "sharpe", "max_drawdown", "calmar", "end_$")
            },
            "sma20_1x_cash": {
                k: float(df[df["run_id"] == "SMA20 1x/cash"].iloc[0][k])
                for k in ("cagr", "sharpe", "max_drawdown", "calmar", "end_$")
            },
            "guarded_max_1x": {
                k: float(guarded_baseline[k]) for k in ("cagr", "sharpe", "max_drawdown", "calmar", "end_$")
            },
        },
        "best_overall": {
            "run_id": best["run_id"],
            "sharpe": float(best["sharpe"]),
            "cagr": float(best["cagr"]),
            "max_drawdown": float(best["max_drawdown"]),
            "calmar": float(best["calmar"]) if pd.notna(best["calmar"]) else None,
            "integration": best["integration"],
            "swing_family": best["swing_family"],
            "swing_param": best["swing_param"],
        }
        if best is not None
        else None,
        "best_per_swing_family": best_per_swing,
        "best_per_top_family": best_per_top,
        "best_per_bottom_family": best_per_bottom,
        "beats_guarded_cagr_sharpe_maxdd_count": int(len(beats_guarded)),
        "beats_guarded_rows": [
            {
                "run_id": r["run_id"],
                "cagr_pct": f"{r['cagr'] * 100:.2f}%",
                "sharpe": f"{r['sharpe']:.3f}",
                "max_dd_pct": f"{r['max_drawdown'] * 100:.2f}%",
            }
            for _, r in beats_guarded.sort_values("sharpe", ascending=False).head(15).iterrows()
        ],
        "total_runs": len(df),
        "structure_runs": len(structure_df),
        "realistic_structure_runs": len(realistic),
        "ranking_note": "Ranked subset excludes pct_days_cash>=95% or max_drawdown>-2% (degenerate low-vol Sharpe).",
    }
    def _json_default(obj: object) -> object:
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        raise TypeError(f"Not serializable: {type(obj)}")

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )

    print("\n=== Baselines ===")
    for label, key in (
        ("Buy & hold 1x", "buy_hold_1x"),
        ("SMA20 1x/cash", "sma20_1x_cash"),
        ("Guarded max 1x", "guarded_max_1x"),
    ):
        b = summary["baselines"][key]
        print(
            f"  {label}: CAGR {b['cagr'] * 100:.2f}%  Sharpe {b['sharpe']:.3f}  "
            f"MaxDD {b['max_drawdown'] * 100:.2f}%  End ${b['end_$']:,.0f}"
        )

    if best is not None:
        print("\n=== Best overall (Sharpe) ===")
        print(
            f"  {best['run_id']}\n"
            f"  CAGR {best['cagr'] * 100:.2f}%  Sharpe {best['sharpe']:.3f}  "
            f"MaxDD {best['max_drawdown'] * 100:.2f}%  Calmar {best['calmar']:.2f}"
        )

    print(f"\n=== Beats Guarded on CAGR+Sharpe+MaxDD: {len(beats_guarded)} configs ===")

    print("\n=== Top 15 by Sharpe ===")
    for _, r in ranked.head(15).iterrows():
        print(
            f"  {r['sharpe']:.3f}  CAGR {r['cagr'] * 100:5.2f}%  "
            f"MaxDD {r['max_drawdown'] * 100:5.2f}%  {r['integration']:<15}  "
            f"{r['swing_family']}({r['swing_param']})  top={r['top_family']}  bot={r['bottom_family']}"
        )

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
