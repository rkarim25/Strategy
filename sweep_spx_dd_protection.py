"""Comprehensive sweep of levered S&P 500 strategies focused on drawdown reduction.

Tests SMA band/hysteresis, DD circuit breakers, VIX filters, trailing stops,
and existing strategies — all at 1x, 2x, and 3x leverage levels.
Strategies with max DD > 60% are collapsed in the final report.

All new signal logic is implemented in this script; no existing files are modified.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    ANNUAL_CASH_INFLOW_PCT,
    PortfolioEngine,
)
from etp_leverage import SPX_ETP, build_etp_return_panel
from indicators import sma, ema, rsi, macd, enrich_prices
from metrics import comprehensive_stats
from strategies import _run_state_machine, MacdParams, TunableMacdStrategy

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "spx_dd_protection_sweep"
OUTPUT_CSV = OUTPUT_DIR / "spx_dd_protection_results.csv"

# ---------------------------------------------------------------------------
# Constants (matching existing sweeps)
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0
DD_PAUSE_TRADING_DAYS = 5  # 1 trading week pause after DD breach
SIGNAL_DELAY_DAYS = 1

# ---------------------------------------------------------------------------
# Engine factories
# ---------------------------------------------------------------------------


def make_engine() -> PortfolioEngine:
    """Standard engine: no DD protection, ETP mode, honest execution."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=SIGNAL_DELAY_DAYS,
    )


def make_engine_dd_breaker(breaker_pct: float) -> PortfolioEngine:
    """Engine with built-in DD pause circuit breaker."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=SIGNAL_DELAY_DAYS,
        dd_pause_trigger=breaker_pct,
        dd_pause_trading_days=DD_PAUSE_TRADING_DAYS,
        dd_pause_reset_peak_on_reentry=True,
    )


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    strategy: str
    cagr: float
    ann_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    end_value: float
    trades: int
    pct_cash: float
    leverage: float


# ---------------------------------------------------------------------------
# Helper: convert 1.0/base → 0.0/cash leverage series
# ---------------------------------------------------------------------------


def _to_cash_base(lev_series: pd.Series) -> pd.Series:
    """Convert a _run_state_machine-style series (1.0=base, N=levered) to
    0.0=cash, N=levered.  Preserves NaN for pre-warmup rows."""
    result = lev_series.copy()
    result[result <= 1.0] = 0.0
    result[lev_series.isna()] = float("nan")
    return result


# ---------------------------------------------------------------------------
# NEW SIGNAL FUNCTIONS
# ---------------------------------------------------------------------------


# --- SMA Band / Hysteresis ---

def sma_band_signal(
    prices: pd.DataFrame, window: int, band_pct: float, leverage: float
) -> pd.Series:
    """SMA crossover with hysteresis band to reduce whipsaws.

    Rules:
      - price > sma * (1 + band)  →  long at `leverage`
      - price < sma * (1 - band)  →  cash (0.0)
      - price within band          →  hold previous position
    """
    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    upper_mult = 1.0 + band_pct
    lower_mult = 1.0 - band_pct

    for i in range(len(prices)):
        if i < window:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        if pd.isna(c) or pd.isna(sma_val):
            lev.iloc[i] = current
            continue
        if c > sma_val * upper_mult:
            current = leverage
        elif c < sma_val * lower_mult:
            current = 0.0
        # else: within band → hold current
        lev.iloc[i] = current
    return lev


# --- SMA Cross with Band ---

def sma_cross_band_signal(
    prices: pd.DataFrame, fast: int, slow: int, band_pct: float, leverage: float
) -> pd.Series:
    """SMA cross with hysteresis band on the fast/slow ratio.

    Rules:
      - fast/slow > 1 + band  →  long at `leverage`
      - fast/slow < 1 - band  →  cash (0.0)
      - within band            →  hold previous position
    """
    close = prices["spx_close"]
    fast_sma = sma(close, fast)
    slow_sma = sma(close, slow)
    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    warmup = max(fast, slow)
    upper_mult = 1.0 + band_pct
    lower_mult = 1.0 - band_pct

    for i in range(len(prices)):
        if i < warmup:
            continue
        f_val = fast_sma.iloc[i]
        s_val = slow_sma.iloc[i]
        if pd.isna(f_val) or pd.isna(s_val) or s_val == 0:
            lev.iloc[i] = current
            continue
        ratio = f_val / s_val
        if ratio > upper_mult:
            current = leverage
        elif ratio < lower_mult:
            current = 0.0
        # else: within band → hold current
        lev.iloc[i] = current
    return lev


# --- VIX Filter Wrapper ---

def apply_vix_filter(
    base_lev: pd.Series, prices: pd.DataFrame, vix_threshold: float
) -> pd.Series:
    """Force cash (0.0) whenever VIX exceeds threshold, regardless of base signal."""
    vix = prices["vix"].ffill().fillna(0.0)
    result = base_lev.copy()
    result[vix > vix_threshold] = 0.0
    return result


# --- Trailing Stop Wrapper ---

def apply_trailing_stop(
    base_lev: pd.Series, prices: pd.DataFrame, stop_pct: float, leverage: float
) -> pd.Series:
    """Apply a trailing stop to a base leverage series.

    Tracks the highest close since entry.  Exits to cash if price drops more
    than `stop_pct` from that peak.  Re-enters only when the base signal says
    enter again.

    `base_lev` must already be in 0.0/cash format (not 1.0/base).
    """
    close = prices["spx_close"]
    result = base_lev.copy()
    in_position = False
    peak = 0.0
    stop_mult = 1.0 - stop_pct

    for i in range(len(result)):
        bl = base_lev.iloc[i]
        c = close.iloc[i]
        if pd.isna(bl) or pd.isna(c):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                in_position = True
                peak = c
                result.iloc[i] = leverage
            # else: stay cash (already 0.0)
        else:
            if c > peak:
                peak = c
            if c < peak * stop_mult:  # trailing stop hit
                in_position = False
                result.iloc[i] = 0.0
            elif bl == 0.0:  # base signal says exit
                in_position = False
                # result already 0.0 from base
            else:
                result.iloc[i] = leverage  # ensure correct leverage level

    return result


# ---------------------------------------------------------------------------
# EXISTING STRATEGY BUILDERS (adapted for multi-leverage, 0.0/cash base)
# ---------------------------------------------------------------------------


def _sma_cash_lev(
    prices: pd.DataFrame, window: int, leverage: float
) -> pd.Series:
    """Price > SMA → levered; else cash (0.0)."""
    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s] = leverage
    return lev


def _ema_cash_lev(
    prices: pd.DataFrame, span: int, leverage: float
) -> pd.Series:
    """Price > EMA → levered; else cash (0.0)."""
    close = prices["spx_close"]
    e = ema(close, span)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > e] = leverage
    return lev


def _sma_cross_lev(
    prices: pd.DataFrame, fast: int, slow: int, leverage: float
) -> pd.Series:
    """Golden/death cross: levered when fast SMA > slow SMA, else cash (0.0)."""
    close = prices["spx_close"]
    fast_sma = sma(close, fast)
    slow_sma = sma(close, slow)
    entry = fast_sma > slow_sma
    exit_ = fast_sma < slow_sma
    raw = _run_state_machine(
        prices.index,
        entry.fillna(False),
        exit_.fillna(False),
        leverage,
        warmup=max(fast, slow),
    )
    return _to_cash_base(raw)


def _macd_variant_lev(
    prices: pd.DataFrame,
    fast: int,
    slow: int,
    signal: int,
    leverage: float,
    *,
    require_above_sma200: bool = False,
    exit_below_sma200: bool = False,
    confirm_days: int = 1,
    hist_entry_pct: float = 0.0,
) -> pd.Series:
    """Tunable MACD variant, converted to 0.0/cash base."""
    params = MacdParams(
        fast=fast,
        slow=slow,
        signal=signal,
        levered_level=leverage,
        require_above_sma200=require_above_sma200,
        exit_below_sma200=exit_below_sma200,
        confirm_days=confirm_days,
        hist_entry_pct=hist_entry_pct,
    )
    strat = TunableMacdStrategy(params)
    raw = strat.generate_leverage(prices)
    return _to_cash_base(raw)


def _rsi_range_lev(
    prices: pd.DataFrame,
    period: int,
    entry_low: float,
    entry_high: float,
    exit_high: float,
    exit_low: float,
    leverage: float,
) -> pd.Series:
    """RSI range-bound: enter when RSI crosses above entry_low,
    exit above exit_high or below exit_low.  Converted to 0.0/cash base."""
    close = prices["spx_close"]
    r = rsi(close, period)
    cross_in = (r > entry_low) & (r.shift(1) <= entry_low)
    exit_sig = (r > exit_high) | (r < exit_low)
    raw = _run_state_machine(
        prices.index,
        cross_in.fillna(False),
        exit_sig.fillna(False),
        leverage,
        warmup=period + 5,
    )
    return _to_cash_base(raw)


# ---------------------------------------------------------------------------
# Strategy catalogue builder
# ---------------------------------------------------------------------------


def build_catalogue(
    prices: pd.DataFrame,
) -> list[tuple[str, pd.Series | float, str]]:
    """Return list of (name, leverage_series_or_float, engine_mode) tuples.

    engine_mode is one of:
      - "standard"  → use make_engine()
      - "dd_NNN"    → use make_engine_dd_breaker(NNN)  e.g. "dd_0.15"
    """
    catalogue: list[tuple[str, pd.Series | float, str]] = []

    # -------------------------------------------------------------------
    # Benchmarks
    # -------------------------------------------------------------------
    catalogue.append(("Buy & Hold SPY 1x", 1.0, "standard"))
    catalogue.append(("Buy & Hold SSO 2x", 2.0, "standard"))
    catalogue.append(("Buy & Hold UPRO 3x", 3.0, "standard"))

    # -------------------------------------------------------------------
    # Category 6: Existing strategies at 1x, 2x, 3x
    # -------------------------------------------------------------------
    for lev in [1.0, 2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        catalogue.append((f"SMA200 {lev_label}", _sma_cash_lev(prices, 200, lev), "standard"))
        catalogue.append((f"SMA50/200 Cross {lev_label}", _sma_cross_lev(prices, 50, 200, lev), "standard"))
        catalogue.append((f"EMA200 {lev_label}", _ema_cash_lev(prices, 200, lev), "standard"))
        catalogue.append((f"MACD 19/39/12 {lev_label}", _macd_variant_lev(prices, 19, 39, 12, lev), "standard"))
        catalogue.append((f"RSI 25/75 {lev_label}", _rsi_range_lev(prices, 14, 25, 75, 80, 20, lev), "standard"))

    # -------------------------------------------------------------------
    # Category 1: SMA Band / Hysteresis
    # -------------------------------------------------------------------
    band_configs = [
        (200, [0.02, 0.03, 0.05], "SMA200"),
        (50, [0.02, 0.03], "SMA50"),
        (100, [0.03], "SMA100"),
    ]
    for window, bands, label_prefix in band_configs:
        for band in bands:
            band_label = f"{band*100:.0f}%"
            for lev in [1.0, 2.0, 3.0]:
                lev_label = f"{lev:.0f}x"
                name = f"{label_prefix} ±{band_label} Band {lev_label}"
                sig = sma_band_signal(prices, window, band, lev)
                catalogue.append((name, sig, "standard"))

    # -------------------------------------------------------------------
    # Category 2: SMA Cross with Band
    # -------------------------------------------------------------------
    for band in [0.02, 0.03]:
        band_label = f"{band*100:.0f}%"
        for lev in [1.0, 2.0, 3.0]:
            lev_label = f"{lev:.0f}x"
            name = f"SMA50/200 Cross ±{band_label} Band {lev_label}"
            sig = sma_cross_band_signal(prices, 50, 200, band, lev)
            catalogue.append((name, sig, "standard"))

    # -------------------------------------------------------------------
    # Category 3: Drawdown Circuit Breakers
    #   Base signal generated at the target leverage; engine applies the
    #   DD pause when portfolio drawdown exceeds breaker_pct.
    # -------------------------------------------------------------------
    dd_breaker_specs = [
        ("SMA200 2x + DD15% Breaker", _sma_cash_lev(prices, 200, 2.0), 0.15),
        ("SMA200 2x + DD20% Breaker", _sma_cash_lev(prices, 200, 2.0), 0.20),
        ("SMA200 3x + DD20% Breaker", _sma_cash_lev(prices, 200, 3.0), 0.20),
        ("SMA50/200 Cross 2x + DD15% Breaker", _sma_cross_lev(prices, 50, 200, 2.0), 0.15),
        ("SMA50/200 Cross 3x + DD20% Breaker", _sma_cross_lev(prices, 50, 200, 3.0), 0.20),
    ]
    for name, sig, breaker_pct in dd_breaker_specs:
        catalogue.append((name, sig, f"dd_{breaker_pct}"))

    # -------------------------------------------------------------------
    # Category 4: VIX Filter
    # -------------------------------------------------------------------
    vix_filter_specs = [
        ("SMA200 2x + VIX>30 Filter", _sma_cash_lev(prices, 200, 2.0), 30.0),
        ("SMA200 3x + VIX>30 Filter", _sma_cash_lev(prices, 200, 3.0), 30.0),
        ("SMA200 2x + VIX>25 Filter", _sma_cash_lev(prices, 200, 2.0), 25.0),
        ("SMA50/200 Cross 2x + VIX>30 Filter", _sma_cross_lev(prices, 50, 200, 2.0), 30.0),
        ("SMA50/200 Cross 3x + VIX>30 Filter", _sma_cross_lev(prices, 50, 200, 3.0), 30.0),
    ]
    for name, base_sig, vix_thresh in vix_filter_specs:
        filtered = apply_vix_filter(base_sig, prices, vix_thresh)
        catalogue.append((name, filtered, "standard"))

    # -------------------------------------------------------------------
    # Category 5: Trailing Stop
    # -------------------------------------------------------------------
    trailing_stop_specs = [
        ("SMA200 2x + 10% Trailing Stop", _sma_cash_lev(prices, 200, 2.0), 0.10, 2.0),
        ("SMA200 2x + 15% Trailing Stop", _sma_cash_lev(prices, 200, 2.0), 0.15, 2.0),
        ("SMA200 3x + 15% Trailing Stop", _sma_cash_lev(prices, 200, 3.0), 0.15, 3.0),
        ("SMA50/200 Cross 2x + 10% Trailing Stop", _sma_cross_lev(prices, 50, 200, 2.0), 0.10, 2.0),
    ]
    for name, base_sig, stop_pct, lev in trailing_stop_specs:
        stopped = apply_trailing_stop(base_sig, prices, stop_pct, lev)
        catalogue.append((name, stopped, "standard"))

    return catalogue


# ---------------------------------------------------------------------------
# Run one strategy
# ---------------------------------------------------------------------------


def run_one(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    name: str,
    leverage: pd.Series | float,
    engine_mode: str = "standard",
) -> SweepResult:
    """Run a single strategy through the appropriate engine and return metrics."""
    # Select engine
    if engine_mode.startswith("dd_"):
        breaker_pct = float(engine_mode.split("_")[1])
        engine = make_engine_dd_breaker(breaker_pct)
    else:
        engine = make_engine()

    result = engine.run(prices, leverage, name=name, etp_returns=etp_panel)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )

    # Count cash days
    lev_applied = result.leverage.astype(float).fillna(0.0)
    n = len(lev_applied)
    pct_cash = 100.0 * float((lev_applied <= 0.0).sum()) / n if n else 0.0

    # Determine nominal leverage from the strategy name or the series
    if isinstance(leverage, (int, float)):
        nom_lev = float(leverage)
    else:
        vals = leverage.dropna()
        vals = vals[vals > 0.0]
        nom_lev = float(vals.median()) if len(vals) > 0 else 1.0

    return SweepResult(
        strategy=name,
        cagr=stats.get("cagr", float("nan")),
        ann_volatility=stats.get("volatility", float("nan")),
        sharpe=stats.get("sharpe", float("nan")),
        sortino=stats.get("sortino", float("nan")),
        max_drawdown=stats.get("max_drawdown", float("nan")),
        end_value=float(result.equity.iloc[-1]) if len(result.equity) else float("nan"),
        trades=result.rebalance_count,
        pct_cash=pct_cash,
        leverage=nom_lev,
    )


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 72)
    print("S&P 500 Drawdown Protection Strategy Sweep")
    print("=" * 72)

    # 1. Download data
    print("\n[1/4] Downloading market data (30y SPX + T-bills + VIX)...")
    prices = load_backtest_data(years=30)
    print(f"  -> {len(prices)} trading days, {prices.index[0].date()} to {prices.index[-1].date()}")

    # 2. Build ETP panel
    print("\n[2/4] Building ETP return panel (SPY/SSO/UPRO)...")
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    print(f"  -> {len(etp_panel.columns)} ETP columns, {len(etp_panel)} rows")

    # 3. Build catalogue
    print("\n[3/4] Building strategy catalogue...")
    catalogue = build_catalogue(prices)
    print(f"  -> {len(catalogue)} strategies to test\n")

    # 4. Run all strategies
    print("[4/4] Running sweep...\n")
    results: list[SweepResult] = []
    for i, (name, leverage, engine_mode) in enumerate(catalogue):
        pct = (i + 1) / len(catalogue) * 100
        print(f"  [{i+1:3d}/{len(catalogue)} {pct:5.1f}%] {name}...", end=" ", flush=True)
        try:
            r = run_one(prices, etp_panel, name, leverage, engine_mode)
            results.append(r)
            cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
            dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
            sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
            print(f"CAGR={cagr_s}  MaxDD={dd_s}  Sharpe={sh_s}  Trades={r.trades}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # 5. Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "strategy", "cagr", "ann_volatility", "sharpe", "sortino",
        "max_drawdown", "end_value", "trades", "pct_cash", "leverage",
    ]
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow({k: getattr(r, k, None) for k in fieldnames})

    print(f"\n{'=' * 72}")
    print(f"Results written to: {OUTPUT_CSV}")
    print(f"{'=' * 72}\n")

    # -------------------------------------------------------------------
    # 6. Print formatted report
    # -------------------------------------------------------------------
    DD_THRESHOLD = -0.60  # collapse strategies with DD worse than -60%

    passing = [r for r in results if not pd.isna(r.max_drawdown) and r.max_drawdown >= DD_THRESHOLD]
    collapsed = [r for r in results if not pd.isna(r.max_drawdown) and r.max_drawdown < DD_THRESHOLD]
    nan_dd = [r for r in results if pd.isna(r.max_drawdown)]

    # --- A. Top Strategies (DD ≤ 60%) ---
    print("=" * 120)
    print("A. TOP STRATEGIES (Max DD <= 60%) -- Ranked by CAGR")
    print("=" * 120)
    sorted_by_cagr = sorted(passing, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999, reverse=True)
    print(f"{'Rank':<5} {'Strategy':<48} {'Lev':>4} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'%Cash':>7} {'EndVal':>10} {'Trades':>7}")
    print("-" * 120)
    for rank, r in enumerate(sorted_by_cagr, 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        vol_s = f"{r.ann_volatility*100:.1f}%" if not pd.isna(r.ann_volatility) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        cash_s = f"{r.pct_cash:.1f}%" if not pd.isna(r.pct_cash) else "N/A"
        ev_s = f"${r.end_value:,.0f}" if not pd.isna(r.end_value) else "N/A"
        lev_s = f"{r.leverage:.0f}x"
        print(f"{rank:<5} {r.strategy:<48} {lev_s:>4} {cagr_s:>8} {dd_s:>8} {vol_s:>8} {sh_s:>7} {so_s:>7} {cash_s:>7} {ev_s:>10} {r.trades:>7}")

    # --- B. Collapsed Group (DD > 60%) ---
    print(f"\n{'=' * 120}")
    print(f"B. COLLAPSED GROUP -- {len(collapsed)} strategies excluded due to Max DD > 60%")
    print(f"{'=' * 120}")
    if collapsed:
        collapsed_names = [r.strategy for r in sorted(collapsed, key=lambda r: r.max_drawdown)]
        for name in collapsed_names:
            print(f"    * {name}")
    else:
        print("    (none)")

    if nan_dd:
        print(f"\n    {len(nan_dd)} strategies had NaN drawdown (excluded):")
        for r in nan_dd:
            print(f"    * {r.strategy}")

    # --- C. Winners by Category ---
    print(f"\n{'=' * 120}")
    print("C. WINNERS BY CATEGORY (DD <= 60% only)")
    print(f"{'=' * 120}")

    def best_by(passing_results, key_fn, reverse=True, label="CAGR"):
        valid = [r for r in passing_results if not pd.isna(key_fn(r))]
        if not valid:
            return None
        return max(valid, key=key_fn) if reverse else min(valid, key=key_fn)

    def fmt_res(r):
        if r is None:
            return "N/A"
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        return f"{r.strategy} | CAGR={cagr_s} MaxDD={dd_s} Sharpe={sh_s} Sortino={so_s}"

    best_cagr = best_by(passing, lambda r: r.cagr)
    best_sharpe = best_by(passing, lambda r: r.sharpe)
    best_sortino = best_by(passing, lambda r: r.sortino)
    best_lowest_dd = best_by(passing, lambda r: r.max_drawdown, reverse=False)

    print(f"  ** Best CAGR:        {fmt_res(best_cagr)}")
    print(f"  ** Best Sharpe:      {fmt_res(best_sharpe)}")
    print(f"  ** Best Sortino:     {fmt_res(best_sortino)}")
    print(f"  ** Lowest Max DD:    {fmt_res(best_lowest_dd)}")

    # Sub-category winners
    def best_in_category(passing_results, prefix, key_fn=lambda r: r.cagr):
        subset = [r for r in passing_results if r.strategy.startswith(prefix)]
        if not subset:
            return None
        valid = [r for r in subset if not pd.isna(key_fn(r))]
        return max(valid, key=key_fn) if valid else None

    print(f"\n  >> Best SMA200 Band Variant:          {fmt_res(best_in_category(passing, 'SMA200 +'))}")
    print(f"  >> Best SMA50 Band Variant:           {fmt_res(best_in_category(passing, 'SMA50 +'))}")
    print(f"  >> Best SMA100 Band Variant:          {fmt_res(best_in_category(passing, 'SMA100 +'))}")
    print(f"  >> Best SMA Cross Band Variant:       {fmt_res(best_in_category(passing, 'SMA50/200 Cross +'))}")
    print(f"  >> Best DD Circuit Breaker:           {fmt_res(best_in_category(passing, 'SMA200 2x + DD') or best_in_category(passing, 'SMA200 3x + DD') or best_in_category(passing, 'SMA50/200 Cross 2x + DD') or best_in_category(passing, 'SMA50/200 Cross 3x + DD'))}")
    # More specific DD breaker
    dd_breaker_subset = [r for r in passing if "DD" in r.strategy and "Breaker" in r.strategy]
    if dd_breaker_subset:
        best_dd_breaker = max(dd_breaker_subset, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999)
        print(f"  >> Best DD Circuit Breaker (detailed): {fmt_res(best_dd_breaker)}")

    vix_subset = [r for r in passing if "VIX" in r.strategy and "Filter" in r.strategy]
    if vix_subset:
        best_vix = max(vix_subset, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999)
        print(f"  >> Best VIX Filter:                   {fmt_res(best_vix)}")

    ts_subset = [r for r in passing if "Trailing Stop" in r.strategy]
    if ts_subset:
        best_ts = max(ts_subset, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999)
        print(f"  >> Best Trailing Stop:                 {fmt_res(best_ts)}")

    # Best existing strategy
    existing_subset = [r for r in passing if r.strategy in [
        "SMA200 1x", "SMA200 2x", "SMA200 3x",
        "SMA50/200 Cross 1x", "SMA50/200 Cross 2x", "SMA50/200 Cross 3x",
        "EMA200 1x", "EMA200 2x", "EMA200 3x",
        "MACD 19/39/12 1x", "MACD 19/39/12 2x", "MACD 19/39/12 3x",
        "RSI 25/75 1x", "RSI 25/75 2x", "RSI 25/75 3x",
    ]]
    if existing_subset:
        best_existing = max(existing_subset, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999)
        print(f"  >> Best Existing Strategy:             {fmt_res(best_existing)}")

    # --- D. Key Insights ---
    print(f"\n{'=' * 120}")
    print("D. KEY INSIGHTS")
    print(f"{'=' * 120}")

    # Insight 1: SMA200 3% band vs plain SMA200
    sma200_plain = {r.leverage: r for r in passing if r.strategy == f"SMA200 {r.leverage:.0f}x"}
    sma200_3pct = {r.leverage: r for r in passing if r.strategy == f"SMA200 ±3% Band {r.leverage:.0f}x"}

    print("\n  1. Does the SMA200 +/-3% band improve over plain SMA200?")
    for lev in [1.0, 2.0, 3.0]:
        plain = sma200_plain.get(lev)
        banded = sma200_3pct.get(lev)
        if plain and banded:
            dd_diff = (banded.max_drawdown - plain.max_drawdown) * 100
            cagr_diff = (banded.cagr - plain.cagr) * 100
            print(f"     {lev:.0f}x: Plain SMA200 -> CAGR={plain.cagr*100:.2f}% DD={plain.max_drawdown*100:.1f}%")
            print(f"          +/-3% Band  -> CAGR={banded.cagr*100:.2f}% DD={banded.max_drawdown*100:.1f}%")
            print(f"          dDD={dd_diff:+.1f}pp, dCAGR={cagr_diff:+.2f}pp, Trades: {plain.trades}->{banded.trades}")
        elif plain:
            print(f"     {lev:.0f}x: Plain SMA200 -> CAGR={plain.cagr*100:.2f}% DD={plain.max_drawdown*100:.1f}%")
            print(f"          +/-3% Band -> EXCLUDED (DD > 60%)")
        elif banded:
            print(f"     {lev:.0f}x: +/-3% Band -> CAGR={banded.cagr*100:.2f}% DD={banded.max_drawdown*100:.1f}% (plain excluded)")

    # Insight 2: Which DD protection mechanism works best?
    print("\n  2. Which drawdown protection mechanism works best?")
    # Compare SMA200 2x with each protection
    sma200_2x = next((r for r in passing if r.strategy == "SMA200 2x"), None)
    if sma200_2x:
        print(f"     Baseline SMA200 2x: CAGR={sma200_2x.cagr*100:.2f}% DD={sma200_2x.max_drawdown*100:.1f}%")
        protections_2x = [
            r for r in passing
            if "SMA200 2x" in r.strategy and r.strategy != "SMA200 2x"
        ]
        for p in sorted(protections_2x, key=lambda r: r.max_drawdown):
            dd_imp = (p.max_drawdown - sma200_2x.max_drawdown) * 100
            cagr_imp = (p.cagr - sma200_2x.cagr) * 100
            print(f"     + {p.strategy.replace('SMA200 2x + ', '')}: DD={p.max_drawdown*100:.1f}% (d{dd_imp:+.1f}pp) CAGR={p.cagr*100:.2f}% (d{cagr_imp:+.2f}pp)")

    # Insight 3: 2x vs 3x effect on protected strategies
    print("\n  3. How does 2x vs 3x affect the protected strategies?")
    for base_name in ["SMA200", "SMA50/200 Cross"]:
        for prot_type in ["+/-3% Band", "+/-2% Band", "+/-5% Band"]:
            r2x = next((r for r in passing if r.strategy == f"{base_name} {prot_type} 2x"), None)
            r3x = next((r for r in passing if r.strategy == f"{base_name} {prot_type} 3x"), None)
            if r2x and r3x:
                print(f"     {base_name} {prot_type}: 2x->CAGR={r2x.cagr*100:.2f}% DD={r2x.max_drawdown*100:.1f}% | 3x->CAGR={r3x.cagr*100:.2f}% DD={r3x.max_drawdown*100:.1f}%")
            elif r2x:
                print(f"     {base_name} {prot_type}: 2x->CAGR={r2x.cagr*100:.2f}% DD={r2x.max_drawdown*100:.1f}% | 3x->EXCLUDED (DD>60%)")
            elif r3x:
                print(f"     {base_name} {prot_type}: 2x->EXCLUDED | 3x->CAGR={r3x.cagr*100:.2f}% DD={r3x.max_drawdown*100:.1f}%")

    # Insight 4: Best overall strategy
    print("\n  4. Best overall strategy considering both return and risk:")
    # Score: Sortino * (1 + CAGR) / (1 + |MaxDD|) — rewards high Sortino+CAGR, penalizes DD
    scored = []
    for r in passing:
        if pd.isna(r.sortino) or pd.isna(r.cagr) or pd.isna(r.max_drawdown):
            continue
        score = r.sortino * (1.0 + r.cagr) / (1.0 + abs(r.max_drawdown))
        scored.append((score, r))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        print(f"     Top 5 by composite score (Sortino * (1+CAGR) / (1+|MaxDD|)):")
        for rank, (score, r) in enumerate(scored[:5], 1):
            print(f"     #{rank}: {r.strategy} | Score={score:.3f} | CAGR={r.cagr*100:.2f}% DD={r.max_drawdown*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f}")

    # Benchmark comparison
    print("\n  5. Benchmark reference:")
    for bench_name in ["Buy & Hold SPY 1x", "Buy & Hold SSO 2x", "Buy & Hold UPRO 3x"]:
        b = next((r for r in results if r.strategy == bench_name), None)
        if b:
            print(f"     {b.strategy}: CAGR={b.cagr*100:.2f}% DD={b.max_drawdown*100:.1f}% Sharpe={b.sharpe:.3f} Sortino={b.sortino:.3f} EndVal=${b.end_value:,.0f}")

    print(f"\n{'=' * 120}")
    print("Sweep complete.")
    print(f"{'=' * 120}")


if __name__ == "__main__":
    main()
