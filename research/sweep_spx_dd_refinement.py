"""Refinement sweep: improve upon the top 9 drawdown protection strategies.

Tests band-width optimization, SMA window variation, protective overlays,
confirmation filters, and volatility-adjusted bands — all built on the
SMA200 ±3% Band base strategy at 2x and 3x leverage.

All signal logic is self-contained; no existing files are modified.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from core.data_manager import load_backtest_data
from core.engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    ANNUAL_CASH_INFLOW_PCT,
    PortfolioEngine,
)
from core.etp_leverage import SPX_ETP, build_etp_return_panel
from core.indicators import sma, ema, rsi, macd, enrich_prices
from core.metrics import comprehensive_stats

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "spx_dd_refinement"
OUTPUT_CSV = OUTPUT_DIR / "spx_dd_refinement_results.csv"

# ---------------------------------------------------------------------------
# Constants (matching sweep_spx_dd_protection.py)
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0
SIGNAL_DELAY_DAYS = 1

# ---------------------------------------------------------------------------
# Engine factory
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
# SIGNAL FUNCTIONS (reused from sweep_spx_dd_protection.py + new ones)
# ---------------------------------------------------------------------------


# --- SMA Band / Hysteresis (reused) ---

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


# --- VIX Filter Wrapper (reused) ---

def apply_vix_filter(
    base_lev: pd.Series, prices: pd.DataFrame, vix_threshold: float
) -> pd.Series:
    """Force cash (0.0) whenever VIX exceeds threshold, regardless of base signal."""
    vix = prices["vix"].ffill().fillna(0.0)
    result = base_lev.copy()
    result[vix > vix_threshold] = 0.0
    return result


# --- Trailing Stop Wrapper (reused) ---

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


# --- NEW: MACD Confirmation Wrapper ---

def macd_confirmation_wrapper(
    base_signal_fn: Callable[[pd.DataFrame, int, float, float], pd.Series],
    prices: pd.DataFrame,
    window: int,
    band_pct: float,
    leverage: float,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
) -> pd.Series:
    """Only allow long when MACD line > signal line AND the band signal says long.

    When MACD is bearish (line <= signal), force cash regardless of band signal.
    """
    close = prices["spx_close"]
    macd_line, macd_sig, _ = macd(close, macd_fast, macd_slow, macd_signal)

    # Generate the base band signal
    base_lev = base_signal_fn(prices, window, band_pct, leverage)

    # Override: force cash when MACD is bearish
    result = base_lev.copy()
    macd_bearish = macd_line <= macd_sig
    result[macd_bearish] = 0.0

    return result


# --- NEW: RSI Entry Filter Wrapper ---

def rsi_entry_filter_wrapper(
    base_signal_fn: Callable[[pd.DataFrame, int, float, float], pd.Series],
    prices: pd.DataFrame,
    window: int,
    band_pct: float,
    leverage: float,
    rsi_period: int = 14,
    rsi_threshold: float = 70.0,
) -> pd.Series:
    """Block long entry if RSI > threshold (overbought). Wait for pullback.

    The base band signal is generated, but when it says go long and RSI is
    above the threshold, we stay in cash instead. Once in a position, RSI
    does not force an exit — only the base signal controls exits.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)

    # Generate the base band signal
    base_lev = base_signal_fn(prices, window, band_pct, leverage)

    # Stateful: track whether we're in a position
    result = base_lev.copy()
    in_position = False

    for i in range(len(result)):
        bl = base_lev.iloc[i]
        rsi_val = r.iloc[i]

        if pd.isna(bl):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                if pd.notna(rsi_val) and rsi_val > rsi_threshold:
                    # Overbought — block entry, stay cash
                    result.iloc[i] = 0.0
                else:
                    in_position = True
                    result.iloc[i] = leverage
            # else: stay cash
        else:
            if bl == 0.0:  # base signal says exit
                in_position = False
                result.iloc[i] = 0.0
            else:
                result.iloc[i] = leverage

    return result


# --- NEW: RSI Exit Filter Wrapper ---

def rsi_exit_filter_wrapper(
    base_signal_fn: Callable[[pd.DataFrame, int, float, float], pd.Series],
    prices: pd.DataFrame,
    window: int,
    band_pct: float,
    leverage: float,
    rsi_period: int = 14,
    rsi_threshold: float = 30.0,
) -> pd.Series:
    """Don't exit if RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash but RSI is below the threshold
    (deeply oversold), we stay long instead. Entry is controlled normally
    by the base signal.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)

    # Generate the base band signal
    base_lev = base_signal_fn(prices, window, band_pct, leverage)

    # Stateful: track whether we're in a position
    result = base_lev.copy()
    in_position = False

    for i in range(len(result)):
        bl = base_lev.iloc[i]
        rsi_val = r.iloc[i]

        if pd.isna(bl):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                in_position = True
                result.iloc[i] = leverage
            # else: stay cash
        else:
            if bl == 0.0:  # base signal says exit
                if pd.notna(rsi_val) and rsi_val < rsi_threshold:
                    # Oversold — block exit, stay long
                    result.iloc[i] = leverage
                else:
                    in_position = False
                    result.iloc[i] = 0.0
            else:
                result.iloc[i] = leverage

    return result


# --- NEW: ATR Band Signal (volatility-adjusted band) ---

def _close_based_atr(close: pd.Series, window: int = 20) -> pd.Series:
    """Approximate ATR using absolute daily percentage changes smoothed with EMA.

    Since we only have close data (no high/low), we use |daily_return| as a
    proxy for the true range, then smooth with EMA(window).
    Returns a series in the same units as price (dollar range).
    """
    daily_pct_change = close.pct_change().abs()
    # EMA-smoothed absolute pct change
    avg_pct_range = daily_pct_change.ewm(span=window, min_periods=window, adjust=False).mean()
    # Convert to dollar range: avg_pct_range * current close
    atr_dollar = avg_pct_range * close
    return atr_dollar


def atr_band_signal(
    prices: pd.DataFrame,
    sma_window: int = 200,
    atr_window: int = 20,
    atr_multiple: float = 3.0,
    leverage: float = 3.0,
) -> pd.Series:
    """SMA band where the band width is volatility-adjusted.

    Band width = atr_multiple × ATR(atr_window) / close

    This makes the band wider in volatile markets (harder to whipsaw out)
    and tighter in calm markets (more responsive).

    Rules:
      - price > sma * (1 + band_pct)  →  long at `leverage`
      - price < sma * (1 - band_pct)  →  cash (0.0)
      - price within band              →  hold previous position

    where band_pct = atr_multiple * ATR / close (varies daily).
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    atr_series = _close_based_atr(close, atr_window)

    lev = pd.Series(0.0, index=prices.index)
    current = 0.0
    warmup = max(sma_window, atr_window)

    for i in range(len(prices)):
        if i < warmup:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        atr_val = atr_series.iloc[i]
        if pd.isna(c) or pd.isna(sma_val) or pd.isna(atr_val) or c == 0:
            lev.iloc[i] = current
            continue

        # Dynamic band: atr_multiple * ATR / close
        band_pct = atr_multiple * atr_val / c
        # Clamp band to reasonable range (0.5% to 15%)
        band_pct = max(0.005, min(0.15, band_pct))

        upper_mult = 1.0 + band_pct
        lower_mult = 1.0 - band_pct

        if c > sma_val * upper_mult:
            current = leverage
        elif c < sma_val * lower_mult:
            current = 0.0
        # else: within band → hold current
        lev.iloc[i] = current

    return lev


# ---------------------------------------------------------------------------
# Strategy catalogue builder
# ---------------------------------------------------------------------------


def build_catalogue(
    prices: pd.DataFrame,
) -> list[tuple[str, pd.Series | float, str]]:
    """Return list of (name, leverage_series_or_float, engine_mode) tuples.

    engine_mode is always "standard" for this refinement sweep.
    """
    catalogue: list[tuple[str, pd.Series | float, str]] = []

    # -------------------------------------------------------------------
    # Benchmarks (re-run for consistency)
    # -------------------------------------------------------------------
    catalogue.append(("Buy & Hold SPY 1x", 1.0, "standard"))
    catalogue.append(("Buy & Hold SSO 2x", 2.0, "standard"))
    catalogue.append(("Buy & Hold UPRO 3x", 3.0, "standard"))

    # -------------------------------------------------------------------
    # Baseline references: SMA200 ±3% Band 2x and 3x
    # -------------------------------------------------------------------
    catalogue.append(
        ("SMA200 ±3% Band 2x (baseline)", sma_band_signal(prices, 200, 0.03, 2.0), "standard")
    )
    catalogue.append(
        ("SMA200 ±3% Band 3x (baseline)", sma_band_signal(prices, 200, 0.03, 3.0), "standard")
    )

    # -------------------------------------------------------------------
    # Category 1: Band Width Optimization
    # -------------------------------------------------------------------
    # SMA200 ±4% Band (1x, 2x, 3x) — the gap between 3% and 5%
    for lev in [1.0, 2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±4% Band {lev_label}"
        sig = sma_band_signal(prices, 200, 0.04, lev)
        catalogue.append((name, sig, "standard"))

    # SMA200 ±2.5% Band (2x, 3x) — between 2% and 3%
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±2.5% Band {lev_label}"
        sig = sma_band_signal(prices, 200, 0.025, lev)
        catalogue.append((name, sig, "standard"))

    # SMA200 ±3.5% Band (2x, 3x) — between 3% and 5%
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3.5% Band {lev_label}"
        sig = sma_band_signal(prices, 200, 0.035, lev)
        catalogue.append((name, sig, "standard"))

    # -------------------------------------------------------------------
    # Category 2: SMA Window Variation with ±3% Band
    # -------------------------------------------------------------------
    # SMA150 ±3% Band (2x, 3x) — slightly faster trend detection
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA150 ±3% Band {lev_label}"
        sig = sma_band_signal(prices, 150, 0.03, lev)
        catalogue.append((name, sig, "standard"))

    # SMA250 ±3% Band (2x, 3x) — slightly slower, more stable
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA250 ±3% Band {lev_label}"
        sig = sma_band_signal(prices, 250, 0.03, lev)
        catalogue.append((name, sig, "standard"))

    # -------------------------------------------------------------------
    # Category 3: SMA200 ±3% Band + Protective Overlays
    # -------------------------------------------------------------------
    # VIX>30 Filter
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + VIX>30 {lev_label}"
        base = sma_band_signal(prices, 200, 0.03, lev)
        filtered = apply_vix_filter(base, prices, 30.0)
        catalogue.append((name, filtered, "standard"))

    # VIX>35 Filter (stricter)
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + VIX>35 {lev_label}"
        base = sma_band_signal(prices, 200, 0.03, lev)
        filtered = apply_vix_filter(base, prices, 35.0)
        catalogue.append((name, filtered, "standard"))

    # 15% Trailing Stop
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + 15% Trailing Stop {lev_label}"
        base = sma_band_signal(prices, 200, 0.03, lev)
        stopped = apply_trailing_stop(base, prices, 0.15, lev)
        catalogue.append((name, stopped, "standard"))

    # 10% Trailing Stop (tighter)
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + 10% Trailing Stop {lev_label}"
        base = sma_band_signal(prices, 200, 0.03, lev)
        stopped = apply_trailing_stop(base, prices, 0.10, lev)
        catalogue.append((name, stopped, "standard"))

    # -------------------------------------------------------------------
    # Category 4: SMA200 ±3% Band + Confirmation Filters
    # -------------------------------------------------------------------
    # MACD Confirmation
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + MACD Confirm {lev_label}"
        sig = macd_confirmation_wrapper(sma_band_signal, prices, 200, 0.03, lev)
        catalogue.append((name, sig, "standard"))

    # RSI<70 Entry Filter
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + RSI<70 Entry {lev_label}"
        sig = rsi_entry_filter_wrapper(sma_band_signal, prices, 200, 0.03, lev, rsi_threshold=70.0)
        catalogue.append((name, sig, "standard"))

    # RSI>30 Exit Filter
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3% Band + RSI>30 Exit {lev_label}"
        sig = rsi_exit_filter_wrapper(sma_band_signal, prices, 200, 0.03, lev, rsi_threshold=30.0)
        catalogue.append((name, sig, "standard"))

    # -------------------------------------------------------------------
    # Category 5: SMA200 ±3% ATR Band (volatility-adjusted)
    # -------------------------------------------------------------------
    for lev in [2.0, 3.0]:
        lev_label = f"{lev:.0f}x"
        name = f"SMA200 ±3xATR Band {lev_label}"
        sig = atr_band_signal(prices, sma_window=200, atr_window=20, atr_multiple=3.0, leverage=lev)
        catalogue.append((name, sig, "standard"))

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
    """Run a single strategy through the engine and return metrics."""
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
    print("S&P 500 Drawdown Protection — REFINEMENT SWEEP")
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
    print("\n[3/4] Building refinement strategy catalogue...")
    catalogue = build_catalogue(prices)
    print(f"  -> {len(catalogue)} strategies to test\n")

    # 4. Run all strategies
    print("[4/4] Running refinement sweep...\n")
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

    # --- Full results table ---
    print("=" * 120)
    print("REFINEMENT RESULTS — All Strategies Ranked by CAGR")
    print("=" * 120)
    sorted_by_cagr = sorted(results, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999, reverse=True)
    print(f"{'Rank':<5} {'Strategy':<52} {'Lev':>4} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'%Cash':>7} {'EndVal':>10} {'Trades':>7}")
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
        print(f"{rank:<5} {r.strategy:<52} {lev_s:>4} {cagr_s:>8} {dd_s:>8} {vol_s:>8} {sh_s:>7} {so_s:>7} {cash_s:>7} {ev_s:>10} {r.trades:>7}")

    # --- Comparison: Refinement vs Baselines ---
    print(f"\n{'=' * 120}")
    print("COMPARISON: Refinement Variants vs SMA200 ±3% Band Baselines")
    print(f"{'=' * 120}")

    baseline_2x = next((r for r in results if r.strategy == "SMA200 ±3% Band 2x (baseline)"), None)
    baseline_3x = next((r for r in results if r.strategy == "SMA200 ±3% Band 3x (baseline)"), None)

    if baseline_2x:
        print(f"\n  Baseline 2x: CAGR={baseline_2x.cagr*100:.2f}%  MaxDD={baseline_2x.max_drawdown*100:.1f}%  "
              f"AnnVol={baseline_2x.ann_volatility*100:.1f}%  Sharpe={baseline_2x.sharpe:.3f}  "
              f"Sortino={baseline_2x.sortino:.3f}  Trades={baseline_2x.trades}  EndVal=${baseline_2x.end_value:,.0f}")
        print(f"  {'-' * 100}")
        # Find 2x variants that improve on baseline
        variants_2x = [r for r in results if r.leverage == 2.0 and r.strategy != "SMA200 ±3% Band 2x (baseline)"
                       and "Buy & Hold" not in r.strategy]
        improvements_2x = []
        for v in variants_2x:
            better_cagr = v.cagr > baseline_2x.cagr if not pd.isna(v.cagr) else False
            better_dd = v.max_drawdown > baseline_2x.max_drawdown if not pd.isna(v.max_drawdown) else False  # less negative = better
            better_vol = v.ann_volatility < baseline_2x.ann_volatility if not pd.isna(v.ann_volatility) else False
            better_sharpe = v.sharpe > baseline_2x.sharpe if not pd.isna(v.sharpe) else False
            better_sortino = v.sortino > baseline_2x.sortino if not pd.isna(v.sortino) else False
            if better_cagr or better_dd or better_vol or better_sharpe or better_sortino:
                improvements_2x.append((v, better_cagr, better_dd, better_vol, better_sharpe, better_sortino))

        if improvements_2x:
            print(f"  Improvements over baseline 2x ({len(improvements_2x)} found):")
            for v, bc, bd, bv, bs, bso in sorted(improvements_2x, key=lambda x: x[0].cagr, reverse=True):
                flags = []
                if bc: flags.append("CAGR↑")
                if bd: flags.append("DD↓")
                if bv: flags.append("Vol↓")
                if bs: flags.append("Sharpe↑")
                if bso: flags.append("Sortino↑")
                print(f"    {v.strategy}: CAGR={v.cagr*100:.2f}% DD={v.max_drawdown*100:.1f}% "
                      f"Vol={v.ann_volatility*100:.1f}% Sharpe={v.sharpe:.3f} Sortino={v.sortino:.3f} "
                      f"[{', '.join(flags)}]")
        else:
            print(f"  No 2x variants improved on the baseline.")

    if baseline_3x:
        print(f"\n  Baseline 3x: CAGR={baseline_3x.cagr*100:.2f}%  MaxDD={baseline_3x.max_drawdown*100:.1f}%  "
              f"AnnVol={baseline_3x.ann_volatility*100:.1f}%  Sharpe={baseline_3x.sharpe:.3f}  "
              f"Sortino={baseline_3x.sortino:.3f}  Trades={baseline_3x.trades}  EndVal=${baseline_3x.end_value:,.0f}")
        print(f"  {'-' * 100}")
        variants_3x = [r for r in results if r.leverage == 3.0 and r.strategy != "SMA200 ±3% Band 3x (baseline)"
                       and "Buy & Hold" not in r.strategy]
        improvements_3x = []
        for v in variants_3x:
            better_cagr = v.cagr > baseline_3x.cagr if not pd.isna(v.cagr) else False
            better_dd = v.max_drawdown > baseline_3x.max_drawdown if not pd.isna(v.max_drawdown) else False
            better_vol = v.ann_volatility < baseline_3x.ann_volatility if not pd.isna(v.ann_volatility) else False
            better_sharpe = v.sharpe > baseline_3x.sharpe if not pd.isna(v.sharpe) else False
            better_sortino = v.sortino > baseline_3x.sortino if not pd.isna(v.sortino) else False
            if better_cagr or better_dd or better_vol or better_sharpe or better_sortino:
                improvements_3x.append((v, better_cagr, better_dd, better_vol, better_sharpe, better_sortino))

        if improvements_3x:
            print(f"  Improvements over baseline 3x ({len(improvements_3x)} found):")
            for v, bc, bd, bv, bs, bso in sorted(improvements_3x, key=lambda x: x[0].cagr, reverse=True):
                flags = []
                if bc: flags.append("CAGR↑")
                if bd: flags.append("DD↓")
                if bv: flags.append("Vol↓")
                if bs: flags.append("Sharpe↑")
                if bso: flags.append("Sortino↑")
                print(f"    {v.strategy}: CAGR={v.cagr*100:.2f}% DD={v.max_drawdown*100:.1f}% "
                      f"Vol={v.ann_volatility*100:.1f}% Sharpe={v.sharpe:.3f} Sortino={v.sortino:.3f} "
                      f"[{', '.join(flags)}]")
        else:
            print(f"  No 3x variants improved on the baseline.")

    # --- Category Winners ---
    print(f"\n{'=' * 120}")
    print("WINNERS BY REFINEMENT CATEGORY")
    print(f"{'=' * 120}")

    def best_in_cat(subset, key_fn=lambda r: r.cagr, reverse=True):
        valid = [r for r in subset if not pd.isna(key_fn(r))]
        return max(valid, key=key_fn) if valid else None

    def fmt_res(r):
        if r is None:
            return "N/A"
        return (f"{r.strategy} | CAGR={r.cagr*100:.2f}% MaxDD={r.max_drawdown*100:.1f}% "
                f"Vol={r.ann_volatility*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f}")

    # Category 1: Band Width
    band_variants = [r for r in results if "±" in r.strategy and "Band" in r.strategy
                     and "baseline" not in r.strategy and "ATR" not in r.strategy
                     and "VIX" not in r.strategy and "Trailing" not in r.strategy
                     and "MACD" not in r.strategy and "RSI" not in r.strategy]
    print(f"  Best Band Width Variant:        {fmt_res(best_in_cat(band_variants))}")

    # Category 2: SMA Window
    window_variants = [r for r in results if ("SMA150" in r.strategy or "SMA250" in r.strategy)]
    print(f"  Best SMA Window Variant:        {fmt_res(best_in_cat(window_variants))}")

    # Category 3: Protective Overlays
    overlay_variants = [r for r in results if "VIX" in r.strategy or "Trailing Stop" in r.strategy]
    print(f"  Best Protective Overlay:        {fmt_res(best_in_cat(overlay_variants))}")

    # Category 4: Confirmation Filters
    confirm_variants = [r for r in results if "MACD" in r.strategy or "RSI" in r.strategy]
    print(f"  Best Confirmation Filter:       {fmt_res(best_in_cat(confirm_variants))}")

    # Category 5: ATR Band
    atr_variants = [r for r in results if "ATR" in r.strategy]
    print(f"  Best ATR Band:                  {fmt_res(best_in_cat(atr_variants))}")

    # --- Benchmark reference ---
    print(f"\n{'=' * 120}")
    print("BENCHMARK REFERENCE")
    print(f"{'=' * 120}")
    for bench_name in ["Buy & Hold SPY 1x", "Buy & Hold SSO 2x", "Buy & Hold UPRO 3x"]:
        b = next((r for r in results if r.strategy == bench_name), None)
        if b:
            print(f"  {b.strategy}: CAGR={b.cagr*100:.2f}% DD={b.max_drawdown*100:.1f}% "
                  f"Sharpe={b.sharpe:.3f} Sortino={b.sortino:.3f} EndVal=${b.end_value:,.0f}")

    # --- Composite Score Ranking ---
    print(f"\n{'=' * 120}")
    print("TOP 10 BY COMPOSITE SCORE (Sortino * (1+CAGR) / (1+|MaxDD|))")
    print(f"{'=' * 120}")
    scored = []
    for r in results:
        if pd.isna(r.sortino) or pd.isna(r.cagr) or pd.isna(r.max_drawdown):
            continue
        score = r.sortino * (1.0 + r.cagr) / (1.0 + abs(r.max_drawdown))
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    for rank, (score, r) in enumerate(scored[:10], 1):
        print(f"  #{rank}: {r.strategy} | Score={score:.3f} | CAGR={r.cagr*100:.2f}% "
              f"DD={r.max_drawdown*100:.1f}% Sharpe={r.sharpe:.3f} Sortino={r.sortino:.3f}")

    print(f"\n{'=' * 120}")
    print("Refinement sweep complete.")
    print(f"{'=' * 120}")


if __name__ == "__main__":
    main()
