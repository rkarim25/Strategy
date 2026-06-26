"""Comprehensive S&P 500 strategy sweep — test all strategy variants against benchmarks.

Runs every strategy from strategies.py plus additional SMA/EMA/guarded variants
through the same PortfolioEngine used by the dashboard. Outputs a ranked CSV.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from etp_leverage import SPX_ETP, build_etp_return_panel
from indicators import enrich_prices, sma, ema, rsi, macd, bollinger_bands
from metrics import comprehensive_stats
from strategies import (
    _run_state_machine,
    BollingerReversionStrategy,
    DrawdownRecoveryStrategy,
    DrawdownScalingStrategy,
    DualFilterStrategy,
    GoldenCrossStrategy,
    MacdMomentumStrategy,
    MacdWithTrendFilterStrategy,
    MacdParams,
    RsiMomentumStrategy,
    RsiOversoldBounceStrategy,
    Sma200TrendStrategy,
    TunableMacdStrategy,
)
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "spx_strategy_sweep"
OUTPUT_CSV = OUTPUT_DIR / "spx_sweep_results.csv"


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


@dataclass
class SweepResult:
    strategy: str
    cagr: float
    ann_volatility: float
    sharpe: float
    max_drawdown: float
    calmar: float
    sortino: float
    end_value: float
    rebalances: int
    trading_costs_total: float
    funding_costs_total: float
    turnover_notional: float
    pct_days_cash: float
    pct_days_1x: float
    pct_days_2x: float
    pct_days_3x: float
    win_rate: float
    profit_factor: float


def run_one(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    name: str,
    leverage: pd.Series | float,
    *,
    use_etp: bool = True,
) -> SweepResult:
    """Run a single strategy through the engine and return metrics."""
    run_kw: dict = {"name": name}
    if use_etp:
        run_kw["etp_returns"] = etp_panel
    result = make_engine().run(prices, leverage, **run_kw)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    # Count leverage exposure days
    lev = result.leverage.astype(float).fillna(0.0)
    n = len(lev)
    pct_cash = 100.0 * float((lev <= 0.0).sum()) / n if n else 0.0
    pct_1x = 100.0 * float(((lev > 0.0) & (lev <= 1.5)).sum()) / n if n else 0.0
    pct_2x = 100.0 * float(((lev > 1.5) & (lev <= 2.5)).sum()) / n if n else 0.0
    pct_3x = 100.0 * float((lev > 2.5).sum()) / n if n else 0.0

    return SweepResult(
        strategy=name,
        cagr=stats.get("cagr", float("nan")),
        ann_volatility=stats.get("volatility", float("nan")),
        sharpe=stats.get("sharpe", float("nan")),
        max_drawdown=stats.get("max_drawdown", float("nan")),
        calmar=stats.get("calmar", float("nan")),
        sortino=stats.get("sortino", float("nan")),
        end_value=float(result.equity.iloc[-1]) if len(result.equity) else float("nan"),
        rebalances=result.rebalance_count,
        trading_costs_total=result.trading_costs_total,
        funding_costs_total=result.funding_costs_total,
        turnover_notional=result.turnover_notional,
        pct_days_cash=pct_cash,
        pct_days_1x=pct_1x,
        pct_days_2x=pct_2x,
        pct_days_3x=pct_3x,
        win_rate=stats.get("win_rate", float("nan")),
        profit_factor=stats.get("profit_factor", float("nan")),
    )


# ---------------------------------------------------------------------------
# Strategy builders — each returns (name, leverage_series)
# ---------------------------------------------------------------------------

def _sma_cash_lev(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s] = leverage
    return lev


def _ema_cash_lev(prices: pd.DataFrame, span: int, leverage: float) -> pd.Series:
    close = prices["spx_close"]
    e = ema(close, span)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > e] = leverage
    return lev


def _sma_tiered_lev(
    prices: pd.DataFrame,
    base_window: int,
    guard_window: int,
    lev_2x: float = 2.0,
    lev_3x: float = 3.0,
) -> pd.Series:
    """Tiered: 1x above base SMA, 2x above guard SMA, 3x above both + momentum."""
    close = prices["spx_close"]
    base_sma = sma(close, base_window)
    guard_sma = sma(close, guard_window)
    ret5 = close.pct_change(5)
    lev = pd.Series(0.0, index=prices.index)
    for dt in prices.index:
        px = float(close.loc[dt])
        b = float(base_sma.loc[dt]) if not pd.isna(base_sma.loc[dt]) else float("nan")
        g = float(guard_sma.loc[dt]) if not pd.isna(guard_sma.loc[dt]) else float("nan")
        r5 = float(ret5.loc[dt]) if not pd.isna(ret5.loc[dt]) else 0.0
        if pd.isna(b) or pd.isna(g):
            continue
        if px > g and r5 > 0:
            lev.loc[dt] = lev_3x
        elif px > g:
            lev.loc[dt] = lev_2x
        elif px > b:
            lev.loc[dt] = 1.0
        # else stays 0.0 (cash)
    return lev


def _sma_dual_tiered_lev(
    prices: pd.DataFrame,
    fast_window: int,
    slow_window: int,
) -> pd.Series:
    """Dual SMA: 3x when above both fast & slow, 1x when above slow only, cash otherwise."""
    close = prices["spx_close"]
    fast_sma = sma(close, fast_window)
    slow_sma = sma(close, slow_window)
    lev = pd.Series(0.0, index=prices.index)
    for dt in prices.index:
        px = float(close.loc[dt])
        f = float(fast_sma.loc[dt]) if not pd.isna(fast_sma.loc[dt]) else float("nan")
        s = float(slow_sma.loc[dt]) if not pd.isna(slow_sma.loc[dt]) else float("nan")
        if pd.isna(f) or pd.isna(s):
            continue
        if px > f and px > s:
            lev.loc[dt] = 3.0
        elif px > s:
            lev.loc[dt] = 1.0
    return lev


def _sma_cross_lev(prices: pd.DataFrame, fast: int, slow: int, leverage: float) -> pd.Series:
    """Golden/death cross style: levered when fast SMA > slow SMA."""
    close = prices["spx_close"]
    fast_sma = sma(close, fast)
    slow_sma = sma(close, slow)
    entry = fast_sma > slow_sma
    exit_ = fast_sma < slow_sma
    return _run_state_machine(prices.index, entry.fillna(False), exit_.fillna(False), leverage, warmup=max(fast, slow))


def _rsi_range_lev(
    prices: pd.DataFrame,
    period: int,
    entry_low: float,
    entry_high: float,
    exit_high: float,
    exit_low: float,
    leverage: float,
) -> pd.Series:
    """RSI range-bound: enter when RSI crosses into [low, high], exit above high or below low."""
    close = prices["spx_close"]
    r = rsi(close, period)
    cross_in = (r > entry_low) & (r.shift(1) <= entry_low)
    exit_sig = (r > exit_high) | (r < exit_low)
    return _run_state_machine(prices.index, cross_in.fillna(False), exit_sig.fillna(False), leverage, warmup=period + 5)


def _bb_reversion_lev(prices: pd.DataFrame, window: int, num_std: float, leverage: float) -> pd.Series:
    """Bollinger band mean reversion."""
    close = prices["spx_close"]
    lower, mid, upper = bollinger_bands(close, window, num_std)
    entry = close < lower
    exit_ = close >= mid
    return _run_state_machine(prices.index, entry.fillna(False), exit_.fillna(False), leverage, warmup=window + 5)


def _dd_scale_lev(prices: pd.DataFrame) -> pd.Series:
    """Drawdown scaling ladder from strategies.py."""
    strat = DrawdownScalingStrategy()
    return strat.generate_leverage(prices)


def _dd_recovery_lev(prices: pd.DataFrame) -> pd.Series:
    """Drawdown recovery from strategies.py."""
    strat = DrawdownRecoveryStrategy()
    return strat.generate_leverage(prices)


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
    """Tunable MACD variant."""
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
    return strat.generate_leverage(prices)


def _guarded_variant_lev(
    prices: pd.DataFrame,
    trigger_a: float,
    trigger_b: float,
    lead_pct: float,
    x_return: float,
    y_return: float,
) -> pd.Series:
    """Guarded tiered variant from test_guarded_balanced_candidate."""
    lev, _ = guarded_strategy_leverage(
        prices,
        trigger_a=trigger_a,
        trigger_b=trigger_b,
        lead_pct_below_sma20=lead_pct,
        x_return=x_return,
        y_return=y_return,
    )
    return lev


# ---------------------------------------------------------------------------
# Strategy catalogue
# ---------------------------------------------------------------------------

def build_catalogue(prices: pd.DataFrame) -> list[tuple[str, pd.Series | float]]:
    """Return list of (name, leverage) for all strategies to test."""
    catalogue: list[tuple[str, pd.Series | float]] = []

    # --- Benchmarks ---
    catalogue.append(("Buy & Hold 1x", 1.0))
    catalogue.append(("Buy & Hold 2x", 2.0))
    catalogue.append(("Buy & Hold 3x", 3.0))

    # --- Simple SMA cash/levered (2x) ---
    for w in [10, 20, 50, 100, 200]:
        catalogue.append((f"SMA{w} Cash/2x", _sma_cash_lev(prices, w, 2.0)))

    # --- Simple SMA cash/levered (3x) ---
    for w in [10, 20, 50, 100, 200]:
        catalogue.append((f"SMA{w} Cash/3x", _sma_cash_lev(prices, w, 3.0)))

    # --- EMA cash/levered (2x) ---
    for s in [10, 20, 50, 100, 200]:
        catalogue.append((f"EMA{s} Cash/2x", _ema_cash_lev(prices, s, 2.0)))

    # --- EMA cash/levered (3x) ---
    for s in [10, 20, 50, 100, 200]:
        catalogue.append((f"EMA{s} Cash/3x", _ema_cash_lev(prices, s, 3.0)))

    # --- SMA cross (golden cross variants) ---
    for fast, slow, lev in [(20, 50, 2.0), (20, 50, 3.0), (50, 200, 2.0), (50, 200, 3.0), (20, 100, 3.0), (10, 50, 3.0)]:
        catalogue.append((f"SMA{fast}/{slow} Cross {lev:.0f}x", _sma_cross_lev(prices, fast, slow, lev)))

    # --- Dual SMA tiered ---
    for fast, slow in [(10, 50), (20, 50), (20, 100), (50, 200)]:
        catalogue.append((f"Dual SMA{fast}/{slow} Tiered 1x/3x", _sma_dual_tiered_lev(prices, fast, slow)))

    # --- SMA tiered (base + guard) ---
    for base, guard in [(20, 50), (20, 100), (50, 200)]:
        catalogue.append((f"SMA{base}/SMA{guard} Tiered 1x/2x/3x", _sma_tiered_lev(prices, base, guard)))

    # --- Strategy classes from strategies.py ---
    catalogue.append(("SMA200 Trend 3x", Sma200TrendStrategy().generate_leverage(prices)))
    catalogue.append(("Golden Cross 3x", GoldenCrossStrategy().generate_leverage(prices)))
    catalogue.append(("MACD Momentum 3x", MacdMomentumStrategy().generate_leverage(prices)))
    catalogue.append(("MACD + SMA200 3x", MacdWithTrendFilterStrategy().generate_leverage(prices)))
    catalogue.append(("RSI Momentum 3x", RsiMomentumStrategy().generate_leverage(prices)))
    catalogue.append(("RSI Oversold 2x", RsiOversoldBounceStrategy().generate_leverage(prices)))
    catalogue.append(("Dual SMA200+RSI 3x", DualFilterStrategy().generate_leverage(prices)))
    catalogue.append(("BB Mean Reversion 2x", BollingerReversionStrategy().generate_leverage(prices)))
    catalogue.append(("DD Recovery 3x", DrawdownRecoveryStrategy().generate_leverage(prices)))
    catalogue.append(("DD Scale 2x/3x", DrawdownScalingStrategy().generate_leverage(prices)))

    # --- MACD variants ---
    for fast, slow, sig, lev in [(12, 26, 9, 3.0), (5, 35, 5, 3.0), (8, 17, 9, 3.0), (12, 26, 9, 2.0)]:
        label = f"MACD {fast}/{slow}/{sig} {lev:.0f}x"
        catalogue.append((label, _macd_variant_lev(prices, fast, slow, sig, lev)))

    # MACD with SMA200 filter
    for fast, slow, sig, lev in [(12, 26, 9, 3.0), (5, 35, 5, 3.0)]:
        label = f"MACD {fast}/{slow}/{sig} +SMA200 {lev:.0f}x"
        catalogue.append((
            label,
            _macd_variant_lev(prices, fast, slow, sig, lev, require_above_sma200=True, exit_below_sma200=True),
        ))

    # MACD with confirmation
    catalogue.append(("MACD 12/26/9 2d Confirm 3x", _macd_variant_lev(prices, 12, 26, 9, 3.0, confirm_days=2)))
    catalogue.append(("MACD 12/26/9 3d Confirm 3x", _macd_variant_lev(prices, 12, 26, 9, 3.0, confirm_days=3)))

    # --- RSI variants ---
    for period, entry_low, entry_high, exit_high, exit_low, lev in [
        (14, 30, 70, 75, 25, 3.0),
        (14, 40, 80, 85, 35, 3.0),
        (14, 45, 75, 80, 40, 2.0),
        (21, 30, 70, 75, 25, 3.0),
    ]:
        label = f"RSI{period} Range {entry_low}-{entry_high} {lev:.0f}x"
        catalogue.append((label, _rsi_range_lev(prices, period, entry_low, entry_high, exit_high, exit_low, lev)))

    # --- Bollinger variants ---
    for w, std, lev in [(20, 2.0, 2.0), (20, 2.0, 3.0), (20, 2.5, 2.0), (50, 2.0, 2.0)]:
        label = f"BB({w},{std}) Reversion {lev:.0f}x"
        catalogue.append((label, _bb_reversion_lev(prices, w, std, lev)))

    # --- Guarded tiered variants (different A/B/X/Y) ---
    guarded_specs = [
        (0.05, 0.25, 0.0075, 0.40, 0.15, "A5/B25/X40/Y15 (current)"),
        (0.05, 0.20, 0.0075, 0.40, 0.15, "A5/B20/X40/Y15"),
        (0.10, 0.25, 0.0075, 0.40, 0.15, "A10/B25/X40/Y15"),
        (0.05, 0.25, 0.0100, 0.50, 0.20, "A5/B25/L1.0/X50/Y20"),
        (0.05, 0.25, 0.0050, 0.30, 0.10, "A5/B25/L0.5/X30/Y10"),
        (0.10, 0.30, 0.0075, 0.50, 0.20, "A10/B30/X50/Y20"),
        (0.05, 0.25, 0.0075, 0.25, 0.10, "A5/B25/X25/Y10"),
        (0.03, 0.20, 0.0075, 0.40, 0.15, "A3/B20/X40/Y15"),
    ]
    for a, b, lead, x, y, label in guarded_specs:
        catalogue.append((f"Guarded {label}", _guarded_variant_lev(prices, a, b, lead, x, y)))

    return catalogue


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("S&P 500 Strategy Sweep")
    print("=" * 70)

    # 1. Download data
    print("\n[1/3] Downloading market data (30y SPX + T-bills + VIX)...")
    prices = load_backtest_data(years=30)
    print(f"  -> {len(prices)} trading days, {prices.index[0].date()} to {prices.index[-1].date()}")

    # 2. Build ETP panel
    print("\n[2/3] Building ETP return panel...")
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    print(f"  -> {len(etp_panel.columns)} ETP columns, {len(etp_panel)} rows")

    # 3. Build catalogue and run
    print("\n[3/3] Running strategy sweep...")
    catalogue = build_catalogue(prices)
    print(f"  -> {len(catalogue)} strategies to test\n")

    results: list[SweepResult] = []
    for i, (name, leverage) in enumerate(catalogue):
        pct = (i + 1) / len(catalogue) * 100
        print(f"  [{i+1:3d}/{len(catalogue)} {pct:5.1f}%] {name}...", end=" ", flush=True)
        try:
            r = run_one(prices, etp_panel, name, leverage)
            results.append(r)
            print(f"CAGR={r.cagr*100:.2f}%  MaxDD={r.max_drawdown*100:.1f}%  Sharpe={r.sharpe:.3f}  Rebal={r.rebalances}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # 4. Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "strategy", "cagr", "ann_volatility", "sharpe", "max_drawdown", "calmar", "sortino",
        "end_value", "rebalances", "trading_costs_total", "funding_costs_total",
        "turnover_notional", "pct_days_cash", "pct_days_1x", "pct_days_2x", "pct_days_3x",
        "win_rate", "profit_factor",
    ]
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow({k: getattr(r, k, None) for k in fieldnames})

    # 5. Print summary rankings
    print(f"\n{'=' * 70}")
    print(f"Results written to: {OUTPUT_CSV}")
    print(f"{'=' * 70}\n")

    # Sort by CAGR descending
    sorted_by_cagr = sorted(results, key=lambda r: r.cagr if not pd.isna(r.cagr) else -999, reverse=True)
    print("TOP 15 BY CAGR:")
    print(f"{'Rank':<5} {'Strategy':<45} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Calmar':>7} {'Rebal':>6} {'Turnover':>10}")
    print("-" * 100)
    for rank, r in enumerate(sorted_by_cagr[:15], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        ca_s = f"{r.calmar:.3f}" if not pd.isna(r.calmar) else "N/A"
        to_s = f"${r.turnover_notional:,.0f}" if not pd.isna(r.turnover_notional) else "N/A"
        print(f"{rank:<5} {r.strategy:<45} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {ca_s:>7} {r.rebalances:>6} {to_s:>10}")

    print("\nTOP 15 BY SHARPE:")
    sorted_by_sharpe = sorted(results, key=lambda r: r.sharpe if not pd.isna(r.sharpe) else -999, reverse=True)
    print(f"{'Rank':<5} {'Strategy':<45} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Calmar':>7} {'Rebal':>6}")
    print("-" * 90)
    for rank, r in enumerate(sorted_by_sharpe[:15], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        ca_s = f"{r.calmar:.3f}" if not pd.isna(r.calmar) else "N/A"
        print(f"{rank:<5} {r.strategy:<45} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {ca_s:>7} {r.rebalances:>6}")

    print("\nTOP 15 BY LOWEST MAX DRAWDOWN:")
    sorted_by_dd = sorted(results, key=lambda r: r.max_drawdown if not pd.isna(r.max_drawdown) else 999)
    print(f"{'Rank':<5} {'Strategy':<45} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Calmar':>7} {'Rebal':>6}")
    print("-" * 90)
    for rank, r in enumerate(sorted_by_dd[:15], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        ca_s = f"{r.calmar:.3f}" if not pd.isna(r.calmar) else "N/A"
        print(f"{rank:<5} {r.strategy:<45} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {ca_s:>7} {r.rebalances:>6}")

    print("\nTOP 15 BY LOWEST TURNOVER (rebalances):")
    sorted_by_rebal = sorted(results, key=lambda r: r.rebalances)
    print(f"{'Rank':<5} {'Strategy':<45} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Rebal':>6} {'Turnover':>10}")
    print("-" * 90)
    for rank, r in enumerate(sorted_by_rebal[:15], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        to_s = f"${r.turnover_notional:,.0f}" if not pd.isna(r.turnover_notional) else "N/A"
        print(f"{rank:<5} {r.strategy:<45} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {r.rebalances:>6} {to_s:>10}")

    print("\nDone.")


if __name__ == "__main__":
    main()
