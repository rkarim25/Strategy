"""Generate summary_data.json entries for B1-B4 S&P 500 strategies.

Runs each of the 4 best strategies in all 3 data regimes (real, synth_era,
synth_long) at 3 trading-cost levels (gross 0%, realistic 0.10%, conservative
1%) and outputs a JSON snippet ready to merge into summary_data.json.

All signal logic is self-contained (copied from sweep_spx_pareto.py); no
existing files are modified.
"""

from __future__ import annotations

import json
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
from indicators import sma, rsi
from metrics import comprehensive_stats

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_JSON = OUTPUT_DIR / "summary_new_strategies.json"

# ---------------------------------------------------------------------------
# Constants (matching existing sweeps and summary_data.json conventions)
# ---------------------------------------------------------------------------
ANNUAL_INFLOW_USD = 10.0       # $10/yr on $100 base
SIGNAL_DELAY_DAYS = 1
TRADING_DAYS_PER_YEAR = 252

# Date window for "real" and "synth_era" regimes (matches existing summary_data.json)
REAL_START = "2009-06-25"
REAL_END = "2026-06-16"

# Cost levels for CAGR sensitivity
COST_LEVELS = {
    "gross": 0.0,       # cagr_g, dd_g
    "realistic": 0.001, # cagr_r, dd_r (also vol, sharpe, sortino, calmar, cash, trades_yr, end)
    "conservative": 0.01,  # cagr_x, dd_x
}

# ---------------------------------------------------------------------------
# Strategy display names (matching the task specification)
# ---------------------------------------------------------------------------
STRATEGY_NAMES = {
    "B1": "SMA200 ±3% Band + RSI>30 Exit 3x",
    "B2": "SMA200 ±3% Band + RSI>30 Exit 2x",
    "B3": "SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x",
    "B4": "SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x",
}

# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

def make_engine(trading_cost_pct: float) -> PortfolioEngine:
    """Standard engine matching existing sweeps: no DD protection, honest execution."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=trading_cost_pct,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        signal_delay_days=SIGNAL_DELAY_DAYS,
    )


# ===================================================================
# SIGNAL FUNCTIONS (copied from sweep_spx_pareto.py — self-contained)
# ===================================================================

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


def rsi_exit_filter_on_series(
    lev_series: pd.Series,
    prices: pd.DataFrame,
    rsi_threshold: float = 30.0,
    rsi_period: int = 14,
) -> pd.Series:
    """Don't exit if RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash (0) but RSI is below the threshold
    (deeply oversold), we stay at the previous non-zero leverage instead.
    Works with dynamic leverage (1-3x), preserving the current leverage level.
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    result = lev_series.copy()
    in_position = False
    current_lev = 0.0

    for i in range(len(result)):
        bl = lev_series.iloc[i]
        rsi_val = r.iloc[i]

        if pd.isna(bl):
            continue

        if not in_position:
            if bl > 0.0:  # base signal says enter
                in_position = True
                current_lev = bl
                result.iloc[i] = bl
            # else: stay cash (already 0.0)
        else:
            if bl == 0.0:  # base signal says exit
                if pd.notna(rsi_val) and rsi_val < rsi_threshold:
                    # Oversold — block exit, stay at current leverage
                    result.iloc[i] = current_lev
                else:
                    in_position = False
                    current_lev = 0.0
                    result.iloc[i] = 0.0
            else:
                # Update current leverage (may have changed)
                current_lev = bl
                result.iloc[i] = bl
    return result


def rsi_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
    rsi_period: int = 14,
) -> pd.Series:
    """Return leverage (0-3) based on RSI zone.

    zones: list of (rsi_threshold, leverage) sorted by threshold ascending.
    Example: [(30, 3), (50, 2), (70, 1), (100, 0)]
    """
    close = prices["spx_close"]
    r = rsi(close, rsi_period)
    lev = pd.Series(0.0, index=prices.index)

    for i in range(len(prices)):
        rsi_val = r.iloc[i]
        if pd.isna(rsi_val):
            continue
        for threshold, leverage in zones:
            if rsi_val <= threshold:
                lev.iloc[i] = leverage
                break
    return lev


def vix_leverage_signal(
    prices: pd.DataFrame,
    zones: list[tuple[float, float]],
) -> pd.Series:
    """Return leverage (0-3) based on VIX level.

    zones: list of (vix_threshold, leverage) sorted by threshold DESCENDING.
    Example: [(30, 3), (20, 2), (0, 1)]
    """
    vix_series = prices["vix"].ffill().fillna(0.0)
    lev = pd.Series(0.0, index=prices.index)

    for i in range(len(prices)):
        v = vix_series.iloc[i]
        if pd.isna(v):
            continue
        for threshold, leverage in zones:
            if v > threshold:
                lev.iloc[i] = leverage
                break
    return lev


def band_trend_hybrid(
    prices: pd.DataFrame,
    sma_window: int,
    band_pct: float,
    cc_lev: pd.Series,
) -> pd.Series:
    """SMA band hysteresis for trend detection + counter-cyclical leverage scaling.

    When the band signal says "long", use cc_lev to determine leverage (1-3x).
    When band says "cash", return 0.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    lev = pd.Series(0.0, index=prices.index)
    in_market = False
    upper_mult = 1.0 + band_pct
    lower_mult = 1.0 - band_pct

    for i in range(len(prices)):
        if i < sma_window:
            continue
        c = close.iloc[i]
        sma_val = s.iloc[i]
        if pd.isna(c) or pd.isna(sma_val):
            lev.iloc[i] = cc_lev.iloc[i] if in_market else 0.0
            continue
        if c > sma_val * upper_mult:
            in_market = True
        elif c < sma_val * lower_mult:
            in_market = False
        # else: within band → hold current state

        if in_market:
            cc_val = cc_lev.iloc[i]
            lev.iloc[i] = cc_val if not pd.isna(cc_val) and cc_val > 0.0 else 1.0
        else:
            lev.iloc[i] = 0.0
    return lev


# ===================================================================
# Strategy leverage series builders
# ===================================================================

def build_b1_leverage(prices: pd.DataFrame) -> pd.Series:
    """B1: SMA200 ±3% Band + RSI>30 Exit 3x"""
    base = sma_band_signal(prices, 200, 0.03, 3.0)
    return rsi_exit_filter_on_series(base, prices, rsi_threshold=30.0)


def build_b2_leverage(prices: pd.DataFrame) -> pd.Series:
    """B2: SMA200 ±3% Band + RSI>30 Exit 2x"""
    base = sma_band_signal(prices, 200, 0.03, 2.0)
    return rsi_exit_filter_on_series(base, prices, rsi_threshold=30.0)


def build_b3_leverage(prices: pd.DataFrame) -> pd.Series:
    """B3: SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x"""
    rsi_1_3x = rsi_leverage_signal(prices, [(30, 3.0), (50, 2.0), (70, 1.0), (100, 0.0)])
    hybrid = band_trend_hybrid(prices, 200, 0.03, rsi_1_3x)
    return rsi_exit_filter_on_series(hybrid, prices, rsi_threshold=30.0)


def build_b4_leverage(prices: pd.DataFrame) -> pd.Series:
    """B4: SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x"""
    vix_1_3x = vix_leverage_signal(prices, [(30, 3.0), (20, 2.0), (0, 1.0)])
    hybrid = band_trend_hybrid(prices, 200, 0.03, vix_1_3x)
    return rsi_exit_filter_on_series(hybrid, prices, rsi_threshold=30.0)


STRATEGY_BUILDERS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "B1": build_b1_leverage,
    "B2": build_b2_leverage,
    "B3": build_b3_leverage,
    "B4": build_b4_leverage,
}


# ===================================================================
# Run one strategy and extract metrics
# ===================================================================

@dataclass
class StrategyMetrics:
    """All metrics needed for one strategy entry in summary_data.json."""
    cagr_g: float
    dd_g: float
    cagr_r: float
    dd_r: float
    cagr_x: float
    dd_x: float
    vol: float
    sharpe: float
    sortino: float
    calmar: float
    cash: float
    trades_yr: float
    end: float


def run_strategy_all_costs(
    prices: pd.DataFrame,
    leverage: pd.Series,
    name: str,
    years: float,
    etp_panel: pd.DataFrame | None = None,
) -> StrategyMetrics:
    """Run a strategy at all 3 cost levels and return combined metrics."""
    
    # --- Gross (0% cost) ---
    eng_g = make_engine(COST_LEVELS["gross"])
    result_g = eng_g.run(prices, leverage, name=name, etp_returns=etp_panel)
    stats_g = comprehensive_stats(
        result_g.equity, result_g.daily_returns,
        trading_costs_total=result_g.trading_costs_total,
        turnover_notional=result_g.turnover_notional,
    )
    
    # --- Realistic (0.10% cost) ---
    eng_r = make_engine(COST_LEVELS["realistic"])
    result_r = eng_r.run(prices, leverage, name=name, etp_returns=etp_panel)
    stats_r = comprehensive_stats(
        result_r.equity, result_r.daily_returns,
        trading_costs_total=result_r.trading_costs_total,
        turnover_notional=result_r.turnover_notional,
    )
    
    # --- Conservative (1% cost) ---
    eng_x = make_engine(COST_LEVELS["conservative"])
    result_x = eng_x.run(prices, leverage, name=name, etp_returns=etp_panel)
    stats_x = comprehensive_stats(
        result_x.equity, result_x.daily_returns,
        trading_costs_total=result_x.trading_costs_total,
        turnover_notional=result_x.turnover_notional,
    )
    
    # Extract metrics
    cagr_g = stats_g.get("cagr", float("nan"))
    dd_g = stats_g.get("max_drawdown", float("nan"))
    cagr_r = stats_r.get("cagr", float("nan"))
    dd_r = stats_r.get("max_drawdown", float("nan"))
    cagr_x = stats_x.get("cagr", float("nan"))
    dd_x = stats_x.get("max_drawdown", float("nan"))
    
    # Vol, Sharpe, Sortino, Calmar from realistic run (pre-cost)
    vol = stats_r.get("volatility", float("nan"))
    sharpe = stats_r.get("sharpe", float("nan"))
    sortino = stats_r.get("sortino", float("nan"))
    calmar = stats_r.get("calmar", float("nan"))
    
    # Cash %, trades/yr, end value from realistic run
    lev_applied = result_r.leverage.astype(float).fillna(0.0)
    n = len(lev_applied)
    pct_cash = 100.0 * float((lev_applied <= 0.0).sum()) / n if n else 0.0
    
    trades = result_r.rebalance_count
    trades_yr = trades / years if years > 0 else 0.0
    
    end_value = float(result_r.equity.iloc[-1]) if len(result_r.equity) else float("nan")
    
    return StrategyMetrics(
        cagr_g=cagr_g, dd_g=dd_g,
        cagr_r=cagr_r, dd_r=dd_r,
        cagr_x=cagr_x, dd_x=dd_x,
        vol=vol, sharpe=sharpe, sortino=sortino, calmar=calmar,
        cash=pct_cash, trades_yr=trades_yr, end=end_value,
    )


def metrics_to_row_dict(m: StrategyMetrics) -> dict:
    """Convert StrategyMetrics to the exact row dict format used in summary_data.json."""
    return {
        "cagr_g": round(m.cagr_g, 4),
        "dd_g": round(m.dd_g, 4),
        "vol": round(m.vol, 4),
        "sharpe": round(m.sharpe, 2),
        "sortino": round(m.sortino, 2),
        "calmar": round(m.calmar, 2),
        "cash": round(m.cash, 1),
        "trades_yr": round(m.trades_yr, 1),
        "end": round(m.end, 0),
        "cagr_r": round(m.cagr_r, 4),
        "dd_r": round(m.dd_r, 4),
        "cagr_x": round(m.cagr_x, 4),
        "dd_x": round(m.dd_x, 4),
    }


# ===================================================================
# Regime metadata helpers
# ===================================================================

def regime_meta(prices: pd.DataFrame) -> dict:
    """Extract start, end, years, sessions from a prices DataFrame."""
    idx = prices.index
    start = idx[0].strftime("%Y-%m-%d") if hasattr(idx[0], "strftime") else str(idx[0])[:10]
    end = idx[-1].strftime("%Y-%m-%d") if hasattr(idx[-1], "strftime") else str(idx[-1])[:10]
    years = round((idx[-1] - idx[0]).days / 365.25, 1)
    sessions = len(idx)
    return {"start": start, "end": end, "years": years, "sessions": sessions}


# ===================================================================
# Main
# ===================================================================

def main() -> None:
    print("=" * 72)
    print("B1-B4 Summary Data Generator")
    print("=" * 72)
    
    # -------------------------------------------------------------------
    # 1. Load full data
    # -------------------------------------------------------------------
    print("\n[1/5] Loading market data (30y SPX + T-bills + VIX)...")
    full_prices = load_backtest_data(years=30)
    print(f"  -> {len(full_prices)} trading days, {full_prices.index[0].date()} to {full_prices.index[-1].date()}")
    
    # -------------------------------------------------------------------
    # 2. Slice data for each regime
    # -------------------------------------------------------------------
    print("\n[2/5] Preparing data slices for 3 regimes...")
    
    # Real / synth_era window
    real_mask = (full_prices.index >= REAL_START) & (full_prices.index <= REAL_END)
    era_prices = full_prices[real_mask].copy()
    print(f"  real/synth_era window: {len(era_prices)} days, {era_prices.index[0].date()} to {era_prices.index[-1].date()}")
    
    # Build ETP panel for real regime
    print("  Building ETP return panel (SPY/SSO/UPRO)...")
    etp_panel = build_etp_return_panel(era_prices, SPX_ETP)
    from etp_leverage import etp_coverage_summary
    cov = etp_coverage_summary(etp_panel)
    print(f"  -> ETP coverage: 2x real {cov['pct_real_2x']}%, 3x real {cov['pct_real_3x']}%")
    
    # Regime metadata
    real_meta = regime_meta(era_prices)
    synth_era_meta = regime_meta(era_prices)  # same window
    synth_long_meta = regime_meta(full_prices)
    
    print(f"  real:        {real_meta['start']} -> {real_meta['end']} ({real_meta['years']} yrs, {real_meta['sessions']} sessions)")
    print(f"  synth_era:   {synth_era_meta['start']} -> {synth_era_meta['end']} ({synth_era_meta['years']} yrs, {synth_era_meta['sessions']} sessions)")
    print(f"  synth_long:  {synth_long_meta['start']} -> {synth_long_meta['end']} ({synth_long_meta['years']} yrs, {synth_long_meta['sessions']} sessions)")
    
    # -------------------------------------------------------------------
    # 3. Build leverage series for each strategy (on each price slice)
    # -------------------------------------------------------------------
    print("\n[3/5] Building leverage series for B1-B4...")
    
    # For real and synth_era, use era_prices. For synth_long, use full_prices.
    # The leverage series must match the price DataFrame's index.
    
    leverage_map: dict[str, dict[str, pd.Series]] = {}  # {regime: {strategy_key: series}}
    
    for regime_key, prices_df in [("real", era_prices), ("synth_era", era_prices), ("synth_long", full_prices)]:
        leverage_map[regime_key] = {}
        for strat_key, builder in STRATEGY_BUILDERS.items():
            print(f"  Building {STRATEGY_NAMES[strat_key]} for {regime_key}...")
            leverage_map[regime_key][strat_key] = builder(prices_df)
    
    # -------------------------------------------------------------------
    # 4. Run all strategies × regimes × cost levels
    # -------------------------------------------------------------------
    print("\n[4/5] Running backtests (4 strategies × 3 regimes × 3 cost levels = 36 runs)...")
    
    # Results structure: {regime_key: {strategy_key: StrategyMetrics}}
    all_results: dict[str, dict[str, StrategyMetrics]] = {}
    
    total_runs = 4 * 3  # 4 strategies × 3 regimes (cost levels handled internally)
    run_count = 0
    
    for regime_key in ["real", "synth_era", "synth_long"]:
        all_results[regime_key] = {}
        prices_df = era_prices if regime_key in ("real", "synth_era") else full_prices
        years = real_meta["years"] if regime_key in ("real", "synth_era") else synth_long_meta["years"]
        etp = etp_panel if regime_key == "real" else None
        
        for strat_key in ["B1", "B2", "B3", "B4"]:
            run_count += 1
            name = STRATEGY_NAMES[strat_key]
            lev = leverage_map[regime_key][strat_key]
            
            print(f"  [{run_count}/{total_runs}] {name} @ {regime_key}...", end=" ", flush=True)
            
            try:
                metrics = run_strategy_all_costs(prices_df, lev, name, years, etp_panel=etp)
                all_results[regime_key][strat_key] = metrics
                print(f"CAGR_r={metrics.cagr_r*100:.2f}%  MaxDD_r={metrics.dd_r*100:.1f}%  "
                      f"Sharpe={metrics.sharpe:.3f}  Sortino={metrics.sortino:.3f}  "
                      f"Trades/yr={metrics.trades_yr:.1f}  End=${metrics.end:,.0f}")
            except Exception as exc:
                print(f"FAILED: {exc}")
                raise
    
    # -------------------------------------------------------------------
    # 5. Build output JSON and write
    # -------------------------------------------------------------------
    print("\n[5/5] Building output JSON...")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build the spx asset entry with only the new strategies
    spx_entry: dict = {
        "key": "spx",
        "label": "S&P 500",
        "idx": "^GSPC",
        "real_lev": True,
        "tickers": {"1x": "SPY", "2x": "SSO", "3x": "UPRO"},
    }
    
    # Real regime
    real_rows: dict = {}
    for strat_key in ["B1", "B2", "B3", "B4"]:
        m = all_results["real"][strat_key]
        real_rows[STRATEGY_NAMES[strat_key]] = metrics_to_row_dict(m)
    
    spx_entry["real"] = {
        **real_meta,
        "cov": {"pct_real_2x": cov["pct_real_2x"], "pct_real_3x": cov["pct_real_3x"]},
        "rows": real_rows,
    }
    
    # synth_era regime
    synth_era_rows: dict = {}
    for strat_key in ["B1", "B2", "B3", "B4"]:
        m = all_results["synth_era"][strat_key]
        synth_era_rows[STRATEGY_NAMES[strat_key]] = metrics_to_row_dict(m)
    
    spx_entry["synth_era"] = {
        **synth_era_meta,
        "rows": synth_era_rows,
    }
    
    # synth_long regime
    synth_long_rows: dict = {}
    for strat_key in ["B1", "B2", "B3", "B4"]:
        m = all_results["synth_long"][strat_key]
        synth_long_rows[STRATEGY_NAMES[strat_key]] = metrics_to_row_dict(m)
    
    spx_entry["synth_long"] = {
        **synth_long_meta,
        "rows": synth_long_rows,
    }
    
    # Wrap in the same top-level structure as summary_data.json
    output = {
        "generated": pd.Timestamp.now().isoformat(),
        "assets": [spx_entry],
    }
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 72}")
    print(f"Output written to: {OUTPUT_JSON}")
    print(f"{'=' * 72}")
    
    # Print summary table
    print("\nSUMMARY OF NEW STRATEGIES (realistic cost, real ETP regime):")
    print(f"{'Strategy':<52} {'CAGR':>8} {'MaxDD':>8} {'Vol':>8} {'Sharpe':>7} {'Sortino':>7} {'Calmar':>7} {'%Cash':>7} {'Trd/Yr':>7} {'End$':>10}")
    print("-" * 130)
    for strat_key in ["B1", "B2", "B3", "B4"]:
        m = all_results["real"][strat_key]
        name = STRATEGY_NAMES[strat_key]
        print(f"{name:<52} {m.cagr_r*100:>7.2f}% {m.dd_r*100:>7.1f}% {m.vol*100:>7.1f}% "
              f"{m.sharpe:>7.3f} {m.sortino:>7.3f} {m.calmar:>7.2f} "
              f"{m.cash:>6.1f}% {m.trades_yr:>7.1f} ${m.end:>9,.0f}")
    
    print(f"\n{'=' * 72}")
    print("Done. Next step: merge output/summary_new_strategies.json into summary_data.json")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    main()
