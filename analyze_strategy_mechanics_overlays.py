"""Broad strategy-mechanics overlay research for the guarded default.

Baseline:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard, $100 initial
capital, $10 annual inflow, 1% rebalance cost, and the existing funding/cash
assumptions from PortfolioEngine.

The screen intentionally reuses the existing guarded strategy and engine. It
tests mechanical overlays that alter leverage paths, plus one clearly-labeled
synthetic protection proxy that adjusts returns after the engine run.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yfinance as yf

from data_manager import load_backtest_data
from engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    PortfolioEngine,
    funding_cost_daily,
    levered_return,
)
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


OUTPUT_DIR = Path("output") / "strategy_mechanics_tests"
RESULTS_CSV = OUTPUT_DIR / "mechanics_results.csv"
TOP_DRAWDOWN_CSV = OUTPUT_DIR / "mechanics_top_drawdown.csv"
TOP_CAGR_CSV = OUTPUT_DIR / "mechanics_top_cagr.csv"
CATEGORY_BEST_CSV = OUTPUT_DIR / "mechanics_category_best.csv"
ANNUAL_EQUITY_CSV = OUTPUT_DIR / "mechanics_annual_equity_selected.csv"
MC_SUMMARY_CSV = OUTPUT_DIR / "mechanics_monte_carlo_summary.csv"
MC_PATHS_CSV = OUTPUT_DIR / "mechanics_monte_carlo_paths.csv"
METADATA_JSON = OUTPUT_DIR / "mechanics_metadata.json"

BASELINE_NAME = "Baseline Guarded A5/B25/X40/Y15 Lead 0.75"
BASELINE_SPEC = {
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}

N_SIMS = 120
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260517


@dataclass(frozen=True)
class VariantSpec:
    category: str
    name: str
    detail: str
    builder: Callable[[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series], tuple[pd.Series, dict[str, float | int | str]]]
    notes: str


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def baseline_leverage(prices: pd.DataFrame) -> tuple[pd.Series, dict[str, float | int]]:
    return guarded_strategy_leverage(prices, **BASELINE_SPEC)


def prior_session(series: pd.Series) -> pd.Series:
    return series.shift(1)


def fetch_yahoo_close(ticker: str, prices: pd.DataFrame) -> pd.Series:
    raw = yf.download(
        ticker,
        start=prices.index[0].strftime("%Y-%m-%d"),
        end=(prices.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"No Yahoo data returned for {ticker}")
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    if out.empty:
        raise ValueError(f"No numeric close data returned for {ticker}")
    return out


def load_mechanics_signals(prices: pd.DataFrame, *, include_external: bool = True) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    close = prices["spx_close"].astype(float)
    ret = close.pct_change()
    signals = pd.DataFrame(index=prices.index)
    availability: dict[str, dict[str, str]] = {
        "SPX": {
            "status": "available",
            "source": "Yahoo Finance ^GSPC via project data_manager.load_backtest_data",
            "raw_start": prices.index[0].date().isoformat(),
            "raw_end": prices.index[-1].date().isoformat(),
            "lag": "all trend/return/volatility signals shifted one session before use",
        }
    }

    for window in [10, 20, 60]:
        signals[f"SPX_VOL_{window}D"] = prior_session(ret.rolling(window, min_periods=window).std() * np.sqrt(252.0))
        signals[f"SPX_RET_{window}D"] = prior_session(close.pct_change(window))
    for window in [3, 5]:
        signals[f"SPX_RET_{window}D"] = prior_session(close.pct_change(window))
    for window in [20, 50]:
        sma = close.rolling(window, min_periods=window).mean()
        signals[f"SPX_ABOVE_SMA{window}"] = prior_session(close > sma)
        signals[f"SPX_BELOW_SMA{window}"] = prior_session(close < sma)

    if not include_external:
        return signals, availability

    for label, pair, source in [
        ("RSP_SPY_REL", ("RSP", "SPY"), "Yahoo RSP/SPY equal-weight vs cap-weight relative strength"),
        ("IWM_SPY_REL", ("IWM", "SPY"), "Yahoo IWM/SPY small-cap vs large-cap relative strength"),
    ]:
        try:
            left = fetch_yahoo_close(pair[0], prices).reindex(prices.index).ffill()
            right = fetch_yahoo_close(pair[1], prices).reindex(prices.index).ffill()
            rel = left / right
            if rel.notna().sum() < 252:
                raise ValueError("Less than one year of overlapping data")
            signals[f"{label}_ABOVE_SMA50"] = prior_session(rel > rel.rolling(50, min_periods=50).mean())
            signals[f"{label}_RET_63D"] = prior_session(rel.pct_change(63))
            availability[label] = {
                "status": "available",
                "source": source,
                "tickers": "/".join(pair),
                "raw_start": str(rel.dropna().index[0].date()),
                "raw_end": str(rel.dropna().index[-1].date()),
                "lag": "1 market session",
            }
        except Exception as exc:  # noqa: BLE001 - unavailable public proxies are part of the research result.
            availability[label] = {"status": "unavailable", "source": source, "error": str(exc)}

    return signals, availability


def apply_action(base: pd.Series, condition: pd.Series, action: str) -> pd.Series:
    cond = condition.reindex(base.index).fillna(False).astype(bool)
    lev = base.copy().astype(float)
    if action == "3x_to_2x":
        lev.loc[cond & (lev > 2.0)] = 2.0
    elif action == "cap_2x":
        lev.loc[cond] = lev.loc[cond].clip(upper=2.0)
    elif action == "cap_1x":
        lev.loc[cond] = lev.loc[cond].clip(upper=1.0)
    elif action == "reduce_one_tier":
        mask = cond & (lev > 0.0)
        lev.loc[mask] = lev.loc[mask].map({3.0: 2.0, 2.0: 1.0, 1.0: 1.0}).fillna(
            lev.loc[mask] - 1.0
        ).clip(lower=0.0)
    else:
        raise ValueError(f"Unknown action: {action}")
    return lev


def crash_brake_condition(
    index: pd.DatetimeIndex,
    trigger: pd.Series,
    release: pd.Series | None,
    cooldown_days: int,
) -> pd.Series:
    out = pd.Series(False, index=index)
    remaining = 0
    for dt in index:
        if bool(trigger.loc[dt]):
            remaining = cooldown_days
        elif remaining > 0 and release is not None and bool(release.loc[dt]):
            remaining = 0
        if remaining > 0:
            out.loc[dt] = True
            remaining -= 1
    return out


def trailing_stop_condition(
    base: pd.Series,
    basis: pd.Series,
    threshold: float,
) -> pd.Series:
    condition = pd.Series(False, index=base.index)
    in_recovery = False
    peak = np.nan
    breached = False
    for dt in base.index:
        lev = float(base.loc[dt])
        value = float(basis.loc[dt]) if not pd.isna(basis.loc[dt]) else np.nan
        if lev > 1.0:
            if not in_recovery:
                in_recovery = True
                breached = False
                peak = value
            elif not pd.isna(value):
                peak = max(peak, value)
            if in_recovery and not breached and peak > 0 and value / peak - 1.0 <= -threshold:
                breached = True
            condition.loc[dt] = breached
        else:
            in_recovery = False
            breached = False
            peak = np.nan
    return condition


def time_decay_condition(base: pd.Series, max_days: int) -> pd.Series:
    out = pd.Series(False, index=base.index)
    days = 0
    for dt in base.index:
        if float(base.loc[dt]) > 1.0:
            days += 1
            out.loc[dt] = days > max_days
        else:
            days = 0
    return out


def ramp_into_3x(base: pd.Series, ramp_days: int) -> pd.Series:
    lev = base.copy().astype(float)
    days_in_3x = 0
    for dt in base.index:
        if float(base.loc[dt]) >= 3.0:
            days_in_3x += 1
            if ramp_days == 3:
                schedule = [2.0, 2.5, 3.0]
            elif ramp_days == 5:
                schedule = [2.0, 2.25, 2.5, 2.75, 3.0]
            else:
                schedule = list(np.linspace(2.0, 3.0, ramp_days))
            lev.loc[dt] = schedule[min(days_in_3x, len(schedule)) - 1]
        else:
            days_in_3x = 0
    return lev


def dynamic_b_leverage(
    prices: pd.DataFrame,
    vol: pd.Series,
    *,
    vol_threshold: float,
    high_vol_b: float,
    high_vol_a: float | None = None,
) -> tuple[pd.Series, dict[str, float | int | str]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    base_guard = (close > sma20).fillna(False)
    recovery_guard = (close >= sma20 * (1.0 - BASELINE_SPEC["lead_pct_below_sma20"])).fillna(False)
    spx_dd = close / close.cummax() - 1.0
    high_vol = (vol > vol_threshold).reindex(prices.index).fillna(False)

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    high_vol_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        hv = bool(high_vol.loc[dt])
        trigger_a = high_vol_a if (hv and high_vol_a is not None) else BASELINE_SPEC["trigger_a"]
        trigger_b = high_vol_b if hv else BASELINE_SPEC["trigger_b"]
        base_lev = 1.0 if base_ok else 0.0
        if hv:
            high_vol_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= BASELINE_SPEC["y_return"]:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 3.0
                continue
            else:
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= BASELINE_SPEC["x_return"]:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 2.0
                continue
            else:
                lev.loc[dt] = base_lev
                continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -float(trigger_a) and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            lev.loc[dt] = base_lev

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "high_vol_days": high_vol_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def dd_budget_leverage(
    prices: pd.DataFrame,
    base: pd.Series,
    *,
    trigger_dd: float,
    cap: float,
    release_rule: str,
) -> tuple[pd.Series, dict[str, float | int | str]]:
    index = prices.index
    spx_ret = prices["spx_close"].pct_change()
    tbill = prices["tbill_rate"].ffill().fillna(0.0)
    signals, _ = load_mechanics_signals(prices, include_external=False)
    aum = INITIAL_CAPITAL
    peak = aum
    prev_lev = 1.0
    prev_year: int | None = None
    capped = False
    capped_days = 0
    entries = 0
    lev = pd.Series(index=index, dtype=float)

    for i, dt in enumerate(index):
        if prev_year is not None and dt.year != prev_year:
            aum += ANNUAL_INFLOW_USD
            peak = max(peak, aum)

        dd = (aum - peak) / peak if peak > 0 else 0.0
        if not capped and dd <= -trigger_dd:
            capped = True
            entries += 1
        elif capped:
            if release_rule == "new_high" and aum >= peak:
                capped = False
            elif release_rule == "spx_above_sma20" and bool(signals["SPX_ABOVE_SMA20"].loc[dt]):
                capped = False
            elif release_rule == "spx_above_sma50" and bool(signals["SPX_ABOVE_SMA50"].loc[dt]):
                capped = False

        target = float(base.loc[dt])
        applied = min(target, cap) if capped else target
        if capped:
            capped_days += 1

        if abs(applied - prev_lev) > 1e-9:
            aum -= abs(applied - prev_lev) * aum * TRADING_COST_FROM_MID_PCT
            prev_lev = applied

        if i > 0 and not pd.isna(spx_ret.iloc[i]):
            tb = float(tbill.iloc[i])
            aum *= 1.0 + levered_return(float(spx_ret.iloc[i]), applied, tb)
        peak = max(peak, aum)
        lev.loc[dt] = applied
        prev_year = dt.year

    return lev, {"dd_budget_entries": entries, "dd_budget_capped_days": capped_days}


def synthetic_protection_equity(
    baseline_returns: pd.Series,
    *,
    period: str,
    loss_threshold: float,
    annual_cost: float,
    protection_ratio: float,
) -> tuple[pd.Series, pd.Series]:
    adjusted = baseline_returns.copy().fillna(0.0)
    cost_daily = annual_cost / 252.0
    groups = adjusted.index.to_period("M" if period == "monthly" else "Q")
    out = pd.Series(0.0, index=adjusted.index)
    for _, period_returns in adjusted.groupby(groups):
        period_ret = 0.0
        for dt, raw_return in period_returns.items():
            r = float(raw_return)
            projected = (1.0 + period_ret) * (1.0 + r) - 1.0
            if projected < -loss_threshold and r < 0:
                excess_loss = -loss_threshold - projected
                r += min(abs(r), excess_loss) * protection_ratio
            r -= cost_daily
            out.loc[dt] = r
            period_ret = (1.0 + period_ret) * (1.0 + r) - 1.0

    equity = pd.Series(index=out.index, dtype=float)
    aum = INITIAL_CAPITAL
    for dt in out.index:
        aum *= 1.0 + float(out.loc[dt])
        equity.loc[dt] = aum
    return equity, out


def build_variants(signals: pd.DataFrame) -> list[VariantSpec]:
    specs: list[VariantSpec] = []

    for window in [10, 20, 60]:
        for threshold in [0.20, 0.25, 0.30, 0.35]:
            col = f"SPX_VOL_{window}D"
            for action, label in [("3x_to_2x", "3x-only to 2x"), ("reduce_one_tier", "all recovery reduce one tier")]:
                specs.append(
                    VariantSpec(
                        "Volatility-scaled leverage",
                        f"Vol {window}d > {threshold:.0%}: {label}",
                        f"{window}d realized vol above {threshold:.0%}",
                        lambda p, b, s, e, c=col, a=action: (
                            apply_action(b, s[c] > threshold, a),
                            {"overlay_active_days": int((s[c] > threshold).sum())},
                        ),
                        "Uses prior-session annualized realized volatility.",
                    )
                )

    for window in [3, 5, 10]:
        for threshold in [-0.03, -0.05, -0.07, -0.10]:
            trigger_col = f"SPX_RET_{window}D"
            for cooldown in [5, 10, 20]:
                for cap, action in [(1.0, "cap_1x"), (2.0, "cap_2x")]:
                    for release_label, release_col in [
                        ("cooldown", None),
                        ("SMA20 repair", "SPX_ABOVE_SMA20"),
                        ("SMA50 repair", "SPX_ABOVE_SMA50"),
                    ]:
                        specs.append(
                            VariantSpec(
                                "Crash-speed brake",
                                f"{window}d SPX <= {threshold:.0%}, cap {cap:.0f}x {cooldown}d / {release_label}",
                                f"Fast SPX drawdown brake with {cooldown}-session cooldown",
                                lambda p, b, s, e, tc=trigger_col, th=threshold, rc=release_col, cd=cooldown, a=action: (
                                    apply_action(
                                        b,
                                        crash_brake_condition(
                                            p.index,
                                            (s[tc] <= th).fillna(False),
                                            s[rc].fillna(False) if rc else None,
                                            cd,
                                        ),
                                        a,
                                    ),
                                    {
                                        "overlay_active_days": int(
                                            crash_brake_condition(
                                                p.index,
                                                (s[tc] <= th).fillna(False),
                                                s[rc].fillna(False) if rc else None,
                                                cd,
                                            ).sum()
                                        )
                                    },
                                ),
                                "Fast price move only; no external data.",
                            )
                        )

    for basis_name in ["SPX", "strategy_equity"]:
        for threshold in [0.05, 0.08, 0.10, 0.12, 0.15]:
            for action, label in [("3x_to_2x", "3x to 2x"), ("cap_1x", "cap recovery to 1x"), ("cap_2x", "cap recovery to 2x")]:
                specs.append(
                    VariantSpec(
                        "Recovery-tier trailing stop",
                        f"{basis_name} recovery trail {threshold:.0%}: {label}",
                        f"Trailing stop from recovery-tier peak using {basis_name}",
                        lambda p, b, s, e, basis=basis_name, th=threshold, a=action: (
                            apply_action(
                                b,
                                trailing_stop_condition(b, p["spx_close"] if basis == "SPX" else e, th),
                                a,
                            ),
                            {
                                "overlay_active_days": int(
                                    trailing_stop_condition(b, p["spx_close"] if basis == "SPX" else e, th).sum()
                                )
                            },
                        ),
                        "State resets when the base strategy leaves recovery leverage.",
                    )
                )

    for window in [10, 20, 60]:
        col = f"SPX_VOL_{window}D"
        for threshold in [0.20, 0.25, 0.30, 0.35]:
            for trend_label, trend_col in [("vol only", None), ("and SPX > SMA20", "SPX_ABOVE_SMA20"), ("and SPX > SMA50", "SPX_ABOVE_SMA50")]:
                specs.append(
                    VariantSpec(
                        "Tier-specific volatility guard",
                        f"Require 3x vol {window}d < {threshold:.0%} {trend_label}",
                        f"3x allowed only under vol/trend confirmation",
                        lambda p, b, s, e, c=col, th=threshold, tc=trend_col: (
                            apply_action(
                                b,
                                (b > 2.0)
                                & ((s[c] >= th) | (~s[tc].fillna(False) if tc else False)),
                                "3x_to_2x",
                            ),
                            {
                                "overlay_active_days": int(
                                    (
                                        (b > 2.0)
                                        & ((s[c] >= th) | (~s[tc].fillna(False) if tc else False))
                                    ).sum()
                                )
                            },
                        ),
                        "Keeps 2x intact; throttles only 3x recovery.",
                    )
                )

    for window in [10, 20, 60]:
        col = f"SPX_VOL_{window}D"
        for threshold in [0.25, 0.30, 0.35]:
            for high_b in [0.30, 0.35]:
                specs.append(
                    VariantSpec(
                        "Dynamic B trigger",
                        f"B {high_b:.0%} when vol {window}d > {threshold:.0%}",
                        "Raise tier-3 trigger in high-volatility regimes",
                        lambda p, b, s, e, c=col, th=threshold, hb=high_b: dynamic_b_leverage(
                            p, s[c], vol_threshold=th, high_vol_b=hb
                        ),
                        "Recomputes the guarded state machine instead of post-processing leverage.",
                    )
                )
            specs.append(
                VariantSpec(
                    "Dynamic B trigger",
                    f"A 10% / B 35% when vol {window}d > {threshold:.0%}",
                    "Raise both recovery triggers in high-volatility regimes",
                    lambda p, b, s, e, c=col, th=threshold: dynamic_b_leverage(
                        p, s[c], vol_threshold=th, high_vol_b=0.35, high_vol_a=0.10
                    ),
                    "Compact dynamic-A extension requested only if sensible.",
                )
            )

    for ramp_days in [3, 5, 10]:
        specs.append(
            VariantSpec(
                "Partial leverage / smoother transitions",
                f"Ramp into 3x over {ramp_days} days",
                "Fractional leverage transition into 3x recovery",
                lambda p, b, s, e, rd=ramp_days: (
                    ramp_into_3x(b, rd),
                    {"overlay_active_days": int((ramp_into_3x(b, rd) != b).sum())},
                ),
                "Uses fractional leverage supported by PortfolioEngine.",
            )
        )
    for map_name, mapping in [
        ("Use 1.5x/2.5x recovery tiers", {2.0: 1.5, 3.0: 2.5}),
        ("Use 2x/2.5x recovery tiers", {2.0: 2.0, 3.0: 2.5}),
        ("Use 1.5x/3x recovery tiers", {2.0: 1.5, 3.0: 3.0}),
    ]:
        specs.append(
            VariantSpec(
                "Partial leverage / smoother transitions",
                map_name,
                "Replace selected recovery tiers with fractional exposure",
                lambda p, b, s, e, m=mapping: (b.replace(m).astype(float), {"overlay_active_days": int((b.replace(m).astype(float) != b).sum())}),
                "Fractional leverage tier test.",
            )
        )

    for trigger in [0.10, 0.15, 0.20]:
        for cap in [1.0, 2.0]:
            for release in ["new_high", "spx_above_sma20", "spx_above_sma50"]:
                specs.append(
                    VariantSpec(
                        "Drawdown budget rule",
                        f"Portfolio DD {trigger:.0%}: cap {cap:.0f}x until {release}",
                        "Stateful drawdown budget based on overlay portfolio path",
                        lambda p, b, s, e, tr=trigger, cp=cap, rr=release: dd_budget_leverage(
                            p, b, trigger_dd=tr, cap=cp, release_rule=rr
                        ),
                        "Uses the same return, funding, inflow, and trading-cost assumptions to estimate cap state.",
                    )
                )

    for days in [20, 40, 60, 120]:
        for action, label in [("reduce_one_tier", "reduce one tier"), ("cap_2x", "cap max 2x"), ("cap_1x", "cap max 1x")]:
            specs.append(
                VariantSpec(
                    "Time-decay recovery tier",
                    f"Recovery older than {days}d: {label}",
                    "De-risk stale recovery tiers after N sessions without reset",
                    lambda p, b, s, e, d=days, a=action: (
                        apply_action(b, time_decay_condition(b, d), a),
                        {"overlay_active_days": int(time_decay_condition(b, d).sum())},
                    ),
                    "State resets when the base strategy leaves recovery leverage.",
                )
            )

    for cond_col, label in [
        ("SPX_ABOVE_SMA50", "SPX above SMA50"),
        ("RSP_SPY_REL_ABOVE_SMA50", "RSP/SPY above relative SMA50"),
        ("IWM_SPY_REL_ABOVE_SMA50", "IWM/SPY above relative SMA50"),
    ]:
        if cond_col not in signals:
            continue
        specs.append(
            VariantSpec(
                "Breadth/trend confirmation proxy",
                f"Require 3x confirmation: {label}",
                "Throttle 3x unless trend/breadth proxy is confirmed",
                lambda p, b, s, e, c=cond_col: (
                    apply_action(b, (b > 2.0) & ~s[c].fillna(False), "3x_to_2x"),
                    {"overlay_active_days": int(((b > 2.0) & ~s[c].fillna(False)).sum())},
                ),
                "Uses public trend proxies only if Yahoo data is available.",
            )
        )
    for cond_col, label in [
        ("RSP_SPY_REL_RET_63D", "RSP/SPY 63d relative return > 0"),
        ("IWM_SPY_REL_RET_63D", "IWM/SPY 63d relative return > 0"),
    ]:
        if cond_col not in signals:
            continue
        specs.append(
            VariantSpec(
                "Breadth/trend confirmation proxy",
                f"Require 3x confirmation: {label}",
                "Throttle 3x unless relative strength is positive",
                lambda p, b, s, e, c=cond_col: (
                    apply_action(b, (b > 2.0) & ~(s[c] > 0.0), "3x_to_2x"),
                    {"overlay_active_days": int(((b > 2.0) & ~(s[c] > 0.0)).sum())},
                ),
                "Uses public trend proxies only if Yahoo data is available.",
            )
        )

    return specs


def run_leverage_backtest(
    prices: pd.DataFrame,
    leverage: pd.Series,
    strategy: str,
    category: str,
    detail: str,
    notes: str,
    extra: dict[str, float | int | str] | None = None,
) -> tuple[dict[str, float | int | str], pd.Series, pd.Series]:
    result = make_engine().run(prices, leverage, name=strategy)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    row: dict[str, float | int | str] = {
        "category": category,
        "strategy": strategy,
        "detail": detail,
        "notes": notes,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats["sortino"],
        "calmar": stats["calmar"],
        "max_drawdown": stats["max_drawdown"],
        "ulcer_index": stats["ulcer_index"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "turnover_notional": result.turnover_notional,
        "avg_leverage": float(result.leverage.mean()),
        "pct_days_cash": float((result.leverage <= 0).mean() * 100.0),
        "pct_days_1x": float((result.leverage == 1.0).mean() * 100.0),
        "pct_days_2x": float((result.leverage == 2.0).mean() * 100.0),
        "pct_days_3x": float((result.leverage == 3.0).mean() * 100.0),
        "pct_days_fractional": float((~result.leverage.isin([0.0, 1.0, 2.0, 3.0])).mean() * 100.0),
    }
    if extra:
        row.update(extra)
    return row, result.equity, result.daily_returns


def run_synthetic_protection_rows(
    baseline_returns: pd.Series,
    baseline_row: dict[str, float | int | str],
) -> tuple[list[dict[str, float | int | str]], dict[str, pd.Series]]:
    rows: list[dict[str, float | int | str]] = []
    equity_by_name: dict[str, pd.Series] = {}
    for period in ["monthly", "quarterly"]:
        for threshold in [0.08, 0.12, 0.15]:
            for cost in [0.02, 0.04, 0.06]:
                for protection in [0.50, 1.00]:
                    name = f"Synthetic {period} hedge: protect {protection:.0%} beyond -{threshold:.0%}, cost {cost:.0%}/yr"
                    equity, adjusted_returns = synthetic_protection_equity(
                        baseline_returns,
                        period=period,
                        loss_threshold=threshold,
                        annual_cost=cost,
                        protection_ratio=protection,
                    )
                    stats = comprehensive_stats(equity, adjusted_returns)
                    row = {
                        "category": "Options/protection proxy",
                        "strategy": name,
                        "detail": f"Synthetic {period} return floor after -{threshold:.0%}; annual drag {cost:.0%}",
                        "notes": "Synthetic/proxy only; not a real options backtest and ignores option path/pricing details.",
                        "cagr": stats["cagr"],
                        "ann_volatility": stats["volatility"],
                        "sharpe": stats["sharpe"],
                        "sortino": stats["sortino"],
                        "calmar": stats["calmar"],
                        "max_drawdown": stats["max_drawdown"],
                        "ulcer_index": stats["ulcer_index"],
                        "end_$": float(equity.iloc[-1]),
                        "rebalances": int(baseline_row["rebalances"]),
                        "trading_costs_total": baseline_row["trading_costs_total"],
                        "funding_costs_total": baseline_row["funding_costs_total"],
                        "turnover_notional": baseline_row["turnover_notional"],
                        "avg_leverage": baseline_row["avg_leverage"],
                        "pct_days_cash": baseline_row["pct_days_cash"],
                        "pct_days_1x": baseline_row["pct_days_1x"],
                        "pct_days_2x": baseline_row["pct_days_2x"],
                        "pct_days_3x": baseline_row["pct_days_3x"],
                        "pct_days_fractional": 0.0,
                        "overlay_active_days": int((adjusted_returns != baseline_returns.reindex(adjusted_returns.index).fillna(0.0)).sum()),
                    }
                    rows.append(row)
                    equity_by_name[name] = equity
    return rows, equity_by_name


def add_comparison_columns(df: pd.DataFrame, baseline: dict[str, float | int | str]) -> pd.DataFrame:
    out = df.copy()
    base_cagr = float(baseline["cagr"])
    base_dd = float(baseline["max_drawdown"])
    base_sharpe = float(baseline["sharpe"])
    out["cagr_delta_pp"] = (out["cagr"] - base_cagr) * 100.0
    out["cagr_retention_pct"] = out["cagr"] / base_cagr * 100.0
    out["max_dd_delta_pp"] = (out["max_drawdown"] - base_dd) * 100.0
    out["max_dd_improvement_pp"] = out["max_dd_delta_pp"]
    out["max_dd_worse_pp"] = (base_dd - out["max_drawdown"]).clip(lower=0.0) * 100.0
    out["sharpe_delta"] = out["sharpe"] - base_sharpe
    out["significantly_better_cagr"] = out["cagr_delta_pp"] >= 2.0
    return out


def selected_annual_equity(equity_by_name: dict[str, pd.Series], selected_names: list[str]) -> pd.DataFrame:
    rows = []
    for name in selected_names:
        if name not in equity_by_name:
            continue
        eq = equity_by_name[name].resample("YE").last()
        for dt, value in eq.items():
            rows.append({"year": int(dt.year), "strategy": name, "equity_$": float(value)})
    return pd.DataFrame(rows)


def synthetic_market_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        sampled_idx: list[np.ndarray] = []
        while sum(len(x) for x in sampled_idx) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_idx.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(sampled_idx)[:HORIZON_DAYS]
        returns = spx_ret[idx]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {
                    "spx_close": 1000.0 * np.cumprod(1.0 + returns),
                    "tbill_rate": tbill[idx],
                },
                index=index,
            )
        )
    return paths


def find_variant(specs: list[VariantSpec], name: str) -> VariantSpec | None:
    return next((spec for spec in specs if spec.name == name), None)


def monte_carlo(prices: pd.DataFrame, selected_specs: list[VariantSpec]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for sim, path in enumerate(synthetic_market_paths(prices)):
        if sim % 20 == 0:
            print(f"Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        signals, _ = load_mechanics_signals(path, include_external=False)
        base_lev, base_counts = baseline_leverage(path)
        baseline_result = make_engine().run(path, base_lev, name=BASELINE_NAME)
        base_row, _, _ = run_leverage_backtest(
            path,
            base_lev,
            BASELINE_NAME,
            "Baseline",
            "Current default strategy",
            "Monte Carlo baseline",
            base_counts,
        )
        base_row["simulation"] = sim
        rows.append(base_row)
        for spec in selected_specs:
            try:
                lev, extra = spec.builder(path, base_lev, signals, baseline_result.equity)
            except KeyError:
                continue
            row, _, _ = run_leverage_backtest(path, lev, spec.name, spec.category, spec.detail, spec.notes, extra)
            row["simulation"] = sim
            rows.append(row)

    paths_df = pd.DataFrame(rows)
    summary_rows = []
    for strategy, group in paths_df.groupby("strategy"):
        summary_rows.append(
            {
                "strategy": strategy,
                "category": str(group["category"].iloc[0]),
                "median_cagr": float(group["cagr"].median()),
                "p10_cagr": float(group["cagr"].quantile(0.10)),
                "p90_cagr": float(group["cagr"].quantile(0.90)),
                "median_max_drawdown": float(group["max_drawdown"].median()),
                "p10_max_drawdown": float(group["max_drawdown"].quantile(0.10)),
                "p90_max_drawdown": float(group["max_drawdown"].quantile(0.90)),
                "median_sharpe": float(group["sharpe"].median()),
                "median_end_$": float(group["end_$"].median()),
                "prob_beats_baseline_cagr_by_sim": np.nan,
                "prob_improves_baseline_dd_by_sim": np.nan,
                "prob_max_dd_worse_35pct": float((group["max_drawdown"] <= -0.35).mean()),
                "prob_max_dd_worse_40pct": float((group["max_drawdown"] <= -0.40).mean()),
            }
        )
    summary = pd.DataFrame(summary_rows)

    baseline_by_sim = paths_df[paths_df["strategy"] == BASELINE_NAME].set_index("simulation")
    for idx, row in summary.iterrows():
        if row["strategy"] == BASELINE_NAME:
            continue
        strategy_rows = paths_df[paths_df["strategy"] == row["strategy"]].set_index("simulation")
        joined = strategy_rows[["cagr", "max_drawdown"]].join(
            baseline_by_sim[["cagr", "max_drawdown"]],
            lsuffix="_variant",
            rsuffix="_baseline",
            how="inner",
        )
        if not joined.empty:
            summary.loc[idx, "prob_beats_baseline_cagr_by_sim"] = float(
                (joined["cagr_variant"] > joined["cagr_baseline"]).mean()
            )
            summary.loc[idx, "prob_improves_baseline_dd_by_sim"] = float(
                (joined["max_drawdown_variant"] > joined["max_drawdown_baseline"]).mean()
            )
    return paths_df, summary


def print_table(df: pd.DataFrame, cols: list[str], n: int = 12) -> None:
    disp = df.head(n).copy()
    for col in ["cagr", "max_drawdown", "ann_volatility"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x) * 100:.2f}%")
    for col in ["cagr_delta_pp", "max_dd_improvement_pp", "max_dd_worse_pp"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{float(x):+.2f}pp")
    if "cagr_retention_pct" in disp:
        disp["cagr_retention_pct"] = disp["cagr_retention_pct"].map(lambda x: f"{float(x):.1f}%")
    if "sharpe" in disp:
        disp["sharpe"] = disp["sharpe"].map(lambda x: f"{float(x):.3f}")
    if "end_$" in disp:
        disp["end_$"] = disp["end_$"].map(lambda x: f"${float(x):,.0f}")
    print(disp[cols].to_string(index=False))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")

    signals, availability = load_mechanics_signals(prices, include_external=True)
    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, baseline_equity, baseline_returns = run_leverage_backtest(
        prices,
        base_lev,
        BASELINE_NAME,
        "Baseline",
        "Current default strategy",
        "Baseline Guarded A5/B25/X40/Y15 with 0.75% SMA20 lead guard.",
        base_counts,
    )
    baseline_row["overlay_active_days"] = 0

    specs = build_variants(signals)
    rows: list[dict[str, float | int | str]] = []
    equity_by_name = {BASELINE_NAME: baseline_equity}

    print(f"Testing {len(specs)} mechanics variants...", flush=True)
    for i, spec in enumerate(specs, start=1):
        if i % 50 == 0:
            print(f"  variant {i}/{len(specs)}", flush=True)
        try:
            lev, extra = spec.builder(prices, base_lev, signals, baseline_equity)
        except KeyError as exc:
            print(f"Skipping {spec.name}: missing signal {exc}", flush=True)
            continue
        if lev.reindex(prices.index).isna().any():
            raise ValueError(f"Variant produced NaN leverage: {spec.name}")
        changed = (lev.astype(float) != base_lev.astype(float)).reindex(prices.index).fillna(False)
        if not bool(changed.any()):
            continue
        extra = dict(extra)
        extra.setdefault("overlay_active_days", int(changed.sum()))
        extra["pct_leverage_changed"] = float(changed.mean() * 100.0)
        row, equity, _ = run_leverage_backtest(
            prices, lev, spec.name, spec.category, spec.detail, spec.notes, extra
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    baseline_total_returns = baseline_equity.pct_change().fillna(0.0)
    protection_rows, protection_equity = run_synthetic_protection_rows(baseline_total_returns, baseline_row)
    rows.extend(protection_rows)
    equity_by_name.update(protection_equity)

    all_df = add_comparison_columns(pd.DataFrame([baseline_row] + rows), baseline_row)
    results = all_df[all_df["category"] != "Baseline"].copy()
    drawdown_retention_95 = results[
        (results["max_dd_improvement_pp"] > 0.0) & (results["cagr_retention_pct"] >= 95.0)
    ].sort_values(["max_dd_improvement_pp", "cagr_retention_pct", "sharpe"], ascending=[False, False, False])
    drawdown_retention_90 = results[
        (results["max_dd_improvement_pp"] > 0.0) & (results["cagr_retention_pct"] >= 90.0)
    ].sort_values(["max_dd_improvement_pp", "cagr_retention_pct", "sharpe"], ascending=[False, False, False])
    drawdown_leaderboard = pd.concat(
        [
            drawdown_retention_95.assign(leaderboard="DD improvement, CAGR retention >=95%"),
            drawdown_retention_90.assign(leaderboard="DD improvement, CAGR retention >=90%"),
        ],
        ignore_index=True,
    ).drop_duplicates(subset=["leaderboard", "strategy"])

    cagr_leaderboards = []
    for allowance in [0.0, 2.0, 5.0]:
        eligible = results[(results["cagr_delta_pp"] > 0.0) & (results["max_dd_worse_pp"] <= allowance)].copy()
        eligible["leaderboard"] = f"CAGR improvement, max DD no worse by >{allowance:.0f}pp"
        cagr_leaderboards.append(eligible.sort_values(["cagr_delta_pp", "sharpe"], ascending=[False, False]))
    cagr_leaderboard = pd.concat(cagr_leaderboards, ignore_index=True) if cagr_leaderboards else pd.DataFrame()

    category_best = (
        results.sort_values(
            ["category", "max_dd_improvement_pp", "cagr_delta_pp", "sharpe"],
            ascending=[True, False, False, False],
        )
        .groupby("category", as_index=False)
        .head(5)
    )

    all_df.to_csv(RESULTS_CSV, index=False)
    drawdown_leaderboard.to_csv(TOP_DRAWDOWN_CSV, index=False)
    cagr_leaderboard.to_csv(TOP_CAGR_CSV, index=False)
    category_best.to_csv(CATEGORY_BEST_CSV, index=False)

    selected_names = [BASELINE_NAME]
    if not drawdown_retention_95.empty:
        selected_names.append(str(drawdown_retention_95.iloc[0]["strategy"]))
    elif not drawdown_retention_90.empty:
        selected_names.append(str(drawdown_retention_90.iloc[0]["strategy"]))
    if not cagr_leaderboard.empty:
        selected_names.append(str(cagr_leaderboard.iloc[0]["strategy"]))
    for name in list(category_best["strategy"].head(8)):
        if name not in selected_names:
            selected_names.append(str(name))
    selected_annual_equity(equity_by_name, selected_names).to_csv(ANNUAL_EQUITY_CSV, index=False)

    selected_for_mc: list[VariantSpec] = []
    mc_candidate_sets = [
        drawdown_retention_95[drawdown_retention_95["category"] != "Options/protection proxy"],
        cagr_leaderboard[cagr_leaderboard["category"] != "Options/protection proxy"] if not cagr_leaderboard.empty else cagr_leaderboard,
    ]
    for candidate_df in mc_candidate_sets:
        if candidate_df.empty:
            continue
        name = str(candidate_df.iloc[0]["strategy"])
        spec = find_variant(specs, name)
        if spec is not None and spec not in selected_for_mc:
            selected_for_mc.append(spec)
    if selected_for_mc:
        print(f"Running focused Monte Carlo for {len(selected_for_mc)} mechanics leader(s)...", flush=True)
        mc_paths, mc_summary = monte_carlo(prices, selected_for_mc)
        mc_paths.to_csv(MC_PATHS_CSV, index=False)
        mc_summary.to_csv(MC_SUMMARY_CSV, index=False)
    else:
        mc_summary = pd.DataFrame()

    best_dd = drawdown_retention_95.iloc[0].to_dict() if not drawdown_retention_95.empty else (
        drawdown_retention_90.iloc[0].to_dict() if not drawdown_retention_90.empty else {}
    )
    best_cagr = cagr_leaderboard.iloc[0].to_dict() if not cagr_leaderboard.empty else {}
    metadata = {
        "source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data; optional RSP/SPY and IWM/SPY Yahoo proxies when available",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "baseline": {"strategy": BASELINE_NAME, **BASELINE_SPEC},
        "initial_capital": INITIAL_CAPITAL,
        "annual_inflow_usd": ANNUAL_INFLOW_USD,
        "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
        "tested_mechanics_count": int(len(results)),
        "variant_specs_built": int(len(specs)),
        "signal_availability": availability,
        "leader_summary": {
            "baseline": {
                "cagr": float(baseline_row["cagr"]),
                "max_drawdown": float(baseline_row["max_drawdown"]),
                "sharpe": float(baseline_row["sharpe"]),
                "end_$": float(baseline_row["end_$"]),
            },
            "best_drawdown_with_95pct_cagr_retention": {
                k: best_dd.get(k)
                for k in ["strategy", "category", "cagr", "max_drawdown", "sharpe", "cagr_retention_pct", "max_dd_improvement_pp"]
            },
            "best_cagr_with_dd_allowance": {
                k: best_cagr.get(k)
                for k in ["strategy", "category", "cagr", "max_drawdown", "sharpe", "cagr_delta_pp", "max_dd_worse_pp"]
            },
        },
        "monte_carlo": {
            "ran": bool(selected_for_mc),
            "selected_strategies": [spec.name for spec in selected_for_mc],
            "n_sims": N_SIMS if selected_for_mc else 0,
            "horizon_trading_days": HORIZON_DAYS,
            "block_days": BLOCK_DAYS,
            "seed": SEED,
            "note": "Block-bootstrap uses SPX/tbill history only; external breadth-relative variants are not MC-tested here.",
        },
    }
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)

    display_cols = [
        "category",
        "strategy",
        "cagr",
        "cagr_retention_pct",
        "cagr_delta_pp",
        "max_drawdown",
        "max_dd_improvement_pp",
        "max_dd_worse_pp",
        "sharpe",
        "end_$",
    ]
    print("\nBaseline:")
    print_table(all_df[all_df["category"] == "Baseline"], display_cols, 1)
    print("\nTop drawdown improvers with >=95% CAGR retention:")
    print_table(drawdown_retention_95, display_cols, 12)
    print("\nTop drawdown improvers with >=90% CAGR retention:")
    print_table(drawdown_retention_90, display_cols, 12)
    print("\nTop CAGR improvers with drawdown guardrails:")
    if not cagr_leaderboard.empty:
        print_table(cagr_leaderboard, ["leaderboard", *display_cols], 12)
    else:
        print("None.")
    if not mc_summary.empty:
        print("\nMonte Carlo summary:")
        mc_disp = mc_summary.copy()
        for col in ["median_cagr", "p10_cagr", "p90_cagr", "median_max_drawdown", "p10_max_drawdown", "p90_max_drawdown"]:
            mc_disp[col] = mc_disp[col].map(lambda x: f"{float(x) * 100:.2f}%")
        for col in ["prob_beats_baseline_cagr_by_sim", "prob_improves_baseline_dd_by_sim", "prob_max_dd_worse_35pct", "prob_max_dd_worse_40pct"]:
            mc_disp[col] = mc_disp[col].map(lambda x: "" if pd.isna(x) else f"{float(x) * 100:.1f}%")
        mc_disp["median_sharpe"] = mc_disp["median_sharpe"].map(lambda x: f"{float(x):.3f}")
        print(mc_disp.to_string(index=False))

    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {TOP_DRAWDOWN_CSV}")
    print(f"Wrote {TOP_CAGR_CSV}")
    print(f"Wrote {CATEGORY_BEST_CSV}")
    print(f"Wrote {ANNUAL_EQUITY_CSV}")
    if selected_for_mc:
        print(f"Wrote {MC_SUMMARY_CSV}")
        print(f"Wrote {MC_PATHS_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
