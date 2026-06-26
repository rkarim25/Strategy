"""Focused sweep of 1x-levered S&P 500 strategies — SPY (1x) vs cash only.

Tests every strategy class and indicator variant constrained to max_leverage=1.0.
Outputs a ranked CSV for direct comparison.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import csv
from dataclasses import dataclass
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
    DrawdownScalingStrategy,
    DualFilterStrategy,
    MacdWithTrendFilterStrategy,
    MacdParams,
    RsiOversoldBounceStrategy,
    TunableMacdStrategy,
)
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "spx_1x_sweep"
OUTPUT_CSV = OUTPUT_DIR / "spx_1x_sweep_results.csv"


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


# ---------------------------------------------------------------------------
# 1x conversion helper
# ---------------------------------------------------------------------------

def _to_1x_cash(lev_series: pd.Series) -> pd.Series:
    """Convert a base-1.0 / levered-Nx series to cash-0.0 / invested-1.0.

    Strategies that use _run_state_machine produce 1.0 (base/unlevered) and
    levered_level (e.g. 2.0 or 3.0).  For a 1x-only mandate we map:
      - original > 1.0  →  1.0  (invested in SPY at 1x)
      - original ≤ 1.0  →  0.0  (cash / T-bills)
    NaN values are preserved (pre-warmup / missing data).
    """
    result = pd.Series(0.0, index=lev_series.index)
    mask = lev_series > 1.0
    result[mask] = 1.0
    result[lev_series.isna()] = float("nan")
    return result


# ---------------------------------------------------------------------------
# Strategy builders — each returns (name, leverage_series)
# ---------------------------------------------------------------------------

def _sma_cash_lev(prices: pd.DataFrame, window: int, leverage: float) -> pd.Series:
    """Price > SMA → levered; else cash.  Already 0.0 base so 1x works natively."""
    close = prices["spx_close"]
    s = sma(close, window)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > s] = leverage
    return lev


def _ema_cash_lev(prices: pd.DataFrame, span: int, leverage: float) -> pd.Series:
    """Price > EMA → levered; else cash.  Already 0.0 base so 1x works natively."""
    close = prices["spx_close"]
    e = ema(close, span)
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[close > e] = leverage
    return lev


def _sma_cross_lev(prices: pd.DataFrame, fast: int, slow: int, leverage: float) -> pd.Series:
    """Golden/death cross: levered when fast SMA > slow SMA, else base 1.0."""
    close = prices["spx_close"]
    fast_sma = sma(close, fast)
    slow_sma = sma(close, slow)
    entry = fast_sma > slow_sma
    exit_ = fast_sma < slow_sma
    return _run_state_machine(
        prices.index, entry.fillna(False), exit_.fillna(False), leverage, warmup=max(fast, slow)
    )


def _rsi_range_lev(
    prices: pd.DataFrame,
    period: int,
    entry_low: float,
    entry_high: float,
    exit_high: float,
    exit_low: float,
    leverage: float,
) -> pd.Series:
    """RSI range-bound: enter when RSI crosses above entry_low, exit above exit_high or below exit_low."""
    close = prices["spx_close"]
    r = rsi(close, period)
    cross_in = (r > entry_low) & (r.shift(1) <= entry_low)
    exit_sig = (r > exit_high) | (r < exit_low)
    return _run_state_machine(
        prices.index, cross_in.fillna(False), exit_sig.fillna(False), leverage, warmup=period + 5
    )


def _bb_reversion_lev(
    prices: pd.DataFrame, window: int, num_std: float, leverage: float
) -> pd.Series:
    """Bollinger band mean reversion: enter below lower band, exit at mid."""
    close = prices["spx_close"]
    lower, mid, upper = bollinger_bands(close, window, num_std)
    entry = close < lower
    exit_ = close >= mid
    return _run_state_machine(
        prices.index, entry.fillna(False), exit_.fillna(False), leverage, warmup=window + 5
    )


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


# ---------------------------------------------------------------------------
# Strategy catalogue — all 1x-only
# ---------------------------------------------------------------------------

def build_catalogue(prices: pd.DataFrame) -> list[tuple[str, pd.Series | float]]:
    """Return list of (name, leverage) for all 1x-only strategies to test."""
    catalogue: list[tuple[str, pd.Series | float]] = []

    # --- Benchmarks ---
    catalogue.append(("Buy & Hold SPY 1x", 1.0))
    catalogue.append(("Buy & Hold 60/40 SPY/T-bills", 0.6))

    # --- SMA cash/1x (native 0.0/1.0 base — no conversion needed) ---
    for w in [10, 20, 50, 100, 200]:
        catalogue.append((f"SMA{w} 1x/Cash", _sma_cash_lev(prices, w, 1.0)))

    # --- EMA cash/1x (native 0.0/1.0 base — no conversion needed) ---
    for s in [10, 20, 50, 100, 200]:
        catalogue.append((f"EMA{s} 1x/Cash", _ema_cash_lev(prices, s, 1.0)))

    # --- SMA cross 1x (uses _run_state_machine → convert) ---
    for fast, slow in [(20, 50), (50, 200)]:
        raw = _sma_cross_lev(prices, fast, slow, 3.0)  # generate with 3.0 for proper switching
        catalogue.append((f"SMA{fast}/{slow} Cross 1x", _to_1x_cash(raw)))

    # --- MACD variants 1x (uses _run_state_machine → convert) ---
    macd_specs = [
        (12, 26, 9, "MACD 12/26/9 1x/Cash"),
        (6, 19, 6, "MACD 6/19/6 1x/Cash"),
        (19, 39, 12, "MACD 19/39/12 1x/Cash"),
    ]
    for fast, slow, sig, label in macd_specs:
        raw = _macd_variant_lev(prices, fast, slow, sig, 3.0)
        catalogue.append((label, _to_1x_cash(raw)))

    # --- RSI variants 1x (uses _run_state_machine → convert) ---
    # RSI 30/70: enter when RSI crosses above 30, exit > 70 or < 25
    raw_30_70 = _rsi_range_lev(prices, 14, 30, 70, 75, 25, 3.0)
    catalogue.append(("RSI14 30/70 1x/Cash", _to_1x_cash(raw_30_70)))

    # RSI 25/75: enter when RSI crosses above 25, exit > 75 or < 20
    raw_25_75 = _rsi_range_lev(prices, 14, 25, 75, 80, 20, 3.0)
    catalogue.append(("RSI14 25/75 1x/Cash", _to_1x_cash(raw_25_75)))

    # RSI Oversold Bounce 1x (enter RSI crosses above 30, exit RSI > 55)
    raw_oversold = RsiOversoldBounceStrategy().generate_leverage(prices)
    catalogue.append(("RSI Oversold Bounce 1x", _to_1x_cash(raw_oversold)))

    # --- Bollinger Bands 1x (uses _run_state_machine → convert) ---
    for w, std, label in [(20, 2.0, "BB(20,2.0) Reversion 1x"), (20, 1.5, "BB(20,1.5) Reversion 1x")]:
        raw = _bb_reversion_lev(prices, w, std, 2.0)
        catalogue.append((label, _to_1x_cash(raw)))

    # --- Strategy classes adapted to 1x ---
    # DualFilterStrategy (SMA200 + RSI): normally 1.0/3.0 → convert to 0.0/1.0
    raw_dual = DualFilterStrategy().generate_leverage(prices)
    catalogue.append(("DualFilter (SMA200+RSI) 1x", _to_1x_cash(raw_dual)))

    # MacdWithTrendFilterStrategy (MACD + SMA200): normally 1.0/3.0 → convert to 0.0/1.0
    raw_macd_trend = MacdWithTrendFilterStrategy().generate_leverage(prices)
    catalogue.append(("MACD+SMA200 Trend 1x", _to_1x_cash(raw_macd_trend)))

    # DrawdownScalingStrategy: normally 1.0/2.0/3.0 → convert to 0.0/1.0
    raw_dd_scale = DrawdownScalingStrategy().generate_leverage(prices)
    catalogue.append(("DD Scale 1x", _to_1x_cash(raw_dd_scale)))

    # BollingerReversionStrategy: normally 1.0/2.0 → convert to 0.0/1.0
    raw_bb = BollingerReversionStrategy().generate_leverage(prices)
    catalogue.append(("BB Mean Reversion 1x", _to_1x_cash(raw_bb)))

    return catalogue


# ---------------------------------------------------------------------------
# Run one strategy
# ---------------------------------------------------------------------------

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
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("S&P 500 1x-Only Strategy Sweep")
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
    print("\n[3/3] Running 1x-only strategy sweep...")
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
    print("ALL STRATEGIES RANKED BY CAGR:")
    print(f"{'Rank':<5} {'Strategy':<40} {'CAGR':>8} {'MaxDD':>8} {'AnnVol':>8} {'Sharpe':>7} {'Sortino':>7} {'%Cash':>7} {'EndVal':>10}")
    print("-" * 110)
    for rank, r in enumerate(sorted_by_cagr, 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        vol_s = f"{r.ann_volatility*100:.1f}%" if not pd.isna(r.ann_volatility) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        cash_s = f"{r.pct_days_cash:.1f}%" if not pd.isna(r.pct_days_cash) else "N/A"
        ev_s = f"${r.end_value:,.0f}" if not pd.isna(r.end_value) else "N/A"
        print(f"{rank:<5} {r.strategy:<40} {cagr_s:>8} {dd_s:>8} {vol_s:>8} {sh_s:>7} {so_s:>7} {cash_s:>7} {ev_s:>10}")

    print("\nTOP 10 BY SHARPE:")
    sorted_by_sharpe = sorted(results, key=lambda r: r.sharpe if not pd.isna(r.sharpe) else -999, reverse=True)
    print(f"{'Rank':<5} {'Strategy':<40} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Sortino':>7}")
    print("-" * 80)
    for rank, r in enumerate(sorted_by_sharpe[:10], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        print(f"{rank:<5} {r.strategy:<40} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {so_s:>7}")

    print("\nTOP 10 BY LOWEST MAX DRAWDOWN:")
    sorted_by_dd = sorted(results, key=lambda r: r.max_drawdown if not pd.isna(r.max_drawdown) else 999)
    print(f"{'Rank':<5} {'Strategy':<40} {'CAGR':>8} {'MaxDD':>8} {'Sharpe':>7} {'Sortino':>7}")
    print("-" * 80)
    for rank, r in enumerate(sorted_by_dd[:10], 1):
        cagr_s = f"{r.cagr*100:.2f}%" if not pd.isna(r.cagr) else "N/A"
        dd_s = f"{r.max_drawdown*100:.1f}%" if not pd.isna(r.max_drawdown) else "N/A"
        sh_s = f"{r.sharpe:.3f}" if not pd.isna(r.sharpe) else "N/A"
        so_s = f"{r.sortino:.3f}" if not pd.isna(r.sortino) else "N/A"
        print(f"{rank:<5} {r.strategy:<40} {cagr_s:>8} {dd_s:>8} {sh_s:>7} {so_s:>7}")

    print("\nDone.")


if __name__ == "__main__":
    main()
