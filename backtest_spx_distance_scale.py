"""Backtest and Monte Carlo for S&P 500 "SMA200 ±3% Band + RSI>20 Exit 2x" (Octane).

Default S&P 500 strategy on the website. Strategy: SMA200 ±3% hysteresis band →
2x long when close > SMA200 x 1.03, cash when close < SMA200 x 0.97, hold prior
state within the band. RSI>20 exit filter: while the band says cash but RSI(14) < 20
(oversold), stay invested at 2x instead of selling into the panic. Full 1950+ history
at 0.10% trading cost — matches the Excel sweep (13.31% CAGR / -41.5% MaxDD / Calmar 0.32).

Writes spx_distance_scale_site_data.json and spx_distance_scale_etp_returns.json for the website
(filename kept for URL stability even though the strategy is no longer "distance scale").
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    PortfolioEngine,
)
from etp_leverage import (
    MC_ETP_METHOD,
    SPX_ETP,
    bootstrap_etp_paths,
    build_etp_return_panel,
    etp_coverage_summary,
    export_etp_returns_json,
)
from indicators import sma, rsi
from metrics import comprehensive_stats
from price_cleaning import clean_close_series

ROOT = Path(__file__).resolve().parent
SPX_TICKER = "^GSPC"
TBILL_TICKER = "^IRX"
VIX_TICKER = "^VIX"
YEARS = 80  # full S&P 500 history (yfinance ^GSPC starts 1950) — match the Excel sweep window
OUTPUT_DIR = ROOT / "output" / "spx_distance_scale"
SITE_DATA_JSON = ROOT / "spx_distance_scale_site_data.json"
ETP_JSON = ROOT / "spx_distance_scale_etp_returns.json"

ANNUAL_INFLOW_USD = 10.0  # $100 base + $10/yr (same as guarded)

N_SIMS = 200
HORIZON_DAYS = 2520  # 10 years
BLOCK_DAYS = 21
SEED = 20260619

# ---------------------------------------------------------------------------
# Strategy spec
# ---------------------------------------------------------------------------

DEFAULT_SPEC = {
    "strategy": "SMA200 ±3% Band + RSI>20 Exit 2x",
    "sma_window": 200,
    "band_pct": 0.03,
    "leverage": 2.0,
    "rsi_threshold": 20.0,  # block exit to cash while RSI(14) < 20 (oversold) — Octane strategy from the Excel
    "rsi_period": 14,
}

# ---------------------------------------------------------------------------
# Signal functions (adapted from backtest_spx_3x_levered.py and sweep_spx_pareto.py)
# ---------------------------------------------------------------------------


def sma_band_signal(
    prices: pd.DataFrame,
    window: int = 200,
    band_pct: float = 0.03,
) -> pd.Series:
    """SMA crossover with hysteresis band — returns 0 (cash) or 1 (long).

    Rules:
      - price > SMA × (1 + band_pct)  →  long (1)
      - price < SMA × (1 - band_pct)  →  cash (0)
      - price within band              →  hold previous state
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
            current = 1.0
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
    """Block exit when RSI < threshold (oversold). Avoid selling into panic.

    When the base signal says go to cash (0) but RSI is below the threshold
    (deeply oversold), stay at the previous non-zero leverage instead.
    Entry is controlled normally by the base signal.
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


def distance_leverage_scale(
    base_lev: pd.Series,
    prices: pd.DataFrame,
    sma_window: int = 200,
) -> pd.Series:
    """Scale leverage 1-3 based on price/SMA ratio when base signal says long.

    ratio ≤ 1.05 → 3x, 1.05 < ratio ≤ 1.10 → 2x, ratio > 1.10 → 1x.
    When base_lev is 0 (cash signal), stays 0.
    """
    close = prices["spx_close"]
    s = sma(close, sma_window)
    result = base_lev.copy()

    for i in range(len(result)):
        if i < sma_window:
            result.iloc[i] = 0.0
            continue
        bl = base_lev.iloc[i]
        if bl <= 0.0:
            result.iloc[i] = 0.0
            continue
        sma_val = s.iloc[i]
        c = close.iloc[i]
        if pd.isna(sma_val) or pd.isna(c) or sma_val <= 0:
            result.iloc[i] = 1.0
            continue
        ratio = c / sma_val
        if ratio <= 1.05:
            result.iloc[i] = 3.0
        elif ratio <= 1.10:
            result.iloc[i] = 2.0
        else:
            result.iloc[i] = 1.0
    return result


# ---------------------------------------------------------------------------
# Strategy leverage computation
# ---------------------------------------------------------------------------


def compute_strategy_leverage(
    prices: pd.DataFrame,
    spec: dict | None = None,
) -> tuple[pd.Series, dict]:
    """Compute the leverage series and usage counts for the 1x/cash band strategy."""
    if spec is None:
        spec = DEFAULT_SPEC

    sma_w = int(spec["sma_window"])
    band_p = float(spec["band_pct"])
    leverage = float(spec.get("leverage", 1.0))

    # SMA200 ±3% band → 0 or 1, then scale by leverage (e.g. 2x)
    base_signal = sma_band_signal(prices, sma_w, band_p)
    final_lev = base_signal * leverage

    # Optional RSI exit filter: when the band says cash but RSI < threshold, stay invested
    if spec.get("rsi_threshold") is not None:
        final_lev = rsi_exit_filter_on_series(
            final_lev, prices, float(spec["rsi_threshold"]), int(spec.get("rsi_period", 14))
        )

    # Compute usage counts (generalised across leverage tiers)
    n = len(final_lev)
    pct_cash = float((final_lev <= 0.0).mean() * 100.0) if n > 0 else 0.0
    pct_1x = float(((final_lev > 0.0) & (final_lev < 1.5)).mean() * 100.0) if n > 0 else 0.0
    pct_2x = float(((final_lev >= 1.5) & (final_lev < 2.5)).mean() * 100.0) if n > 0 else 0.0
    pct_3x = float((final_lev >= 2.5).mean() * 100.0) if n > 0 else 0.0
    avg_lev = float(final_lev[final_lev > 0.0].mean()) if (final_lev > 0.0).any() else 0.0

    # Count trades (signal changes where leverage crosses 0)
    trades = int((final_lev.diff().fillna(0.0) != 0.0).sum())

    counts = {
        "pct_days_cash": pct_cash,
        "pct_days_1x": pct_1x,
        "pct_days_2x": pct_2x,
        "pct_days_3x": pct_3x,
        "avg_leverage": avg_lev,
        "total_trades": trades,
    }
    return final_lev, counts


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------


def download_spx_panel(years: int = YEARS) -> pd.DataFrame:
    """Download the S&P 500 index, T-bill rate, and VIX over full history (1950+).

    Mirrors the sweep's load_asset_data: ^GSPC sets the date index; ^IRX/^VIX are
    reindexed onto it with ffill and pre-inception defaults (3% T-bill, VIX 20), so
    the panel spans the full S&P history (1950) rather than the shorter ^IRX window.
    (`years` is retained for signature compatibility but no longer limits the start.)
    """
    start = "1950-01-03"
    spx_raw = yf.download(SPX_TICKER, start=start, auto_adjust=True, progress=False)
    if spx_raw.empty:
        raise ValueError("No ^GSPC data returned from yfinance.")
    spx_close = spx_raw["Close"]
    if isinstance(spx_close, pd.DataFrame):
        spx_close = spx_close.iloc[:, 0]
    spx_close = spx_close.astype(float).sort_index()
    spx_close = spx_close[spx_close > 0]
    idx = spx_close.index

    aux = yf.download([TBILL_TICKER, VIX_TICKER], start=start, auto_adjust=True, progress=False)
    aux_close = aux["Close"] if isinstance(aux.columns, pd.MultiIndex) else aux
    tbill = (aux_close[TBILL_TICKER].astype(float) / 100.0).reindex(idx).ffill().fillna(0.03)
    vix = aux_close[VIX_TICKER].astype(float).reindex(idx).ffill().fillna(20.0)

    panel = pd.DataFrame({"spx_close": spx_close, "tbill_rate": tbill, "vix": vix}, index=idx)
    panel = panel.dropna(subset=["spx_close"]).ffill()
    panel["spx_close"] = clean_close_series(panel["spx_close"])
    if len(panel) < 260:
        raise ValueError(f"Not enough SPX rows: {len(panel)}")
    return panel


# ---------------------------------------------------------------------------
# Engine factory (guarded-style: $100 base + $10/yr absolute inflow)
# ---------------------------------------------------------------------------


def make_engine() -> PortfolioEngine:
    """Standard engine: no DD protection, ETP mode, honest execution, $10/yr inflow."""
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


# ---------------------------------------------------------------------------
# Strategy runner
# ---------------------------------------------------------------------------


def run_strategy(
    prices: pd.DataFrame,
    spec: dict | None = None,
    *,
    etp_returns: pd.DataFrame | None = None,
) -> dict:
    """Run the distance-scale strategy through PortfolioEngine and return stats + counts."""
    if spec is None:
        spec = DEFAULT_SPEC
    lev, counts = compute_strategy_leverage(prices, spec)
    run_kw: dict = {"name": str(spec["strategy"])}
    leverage = float(spec.get("leverage", 1.0))
    if leverage > 1.0:
        if etp_returns is not None:
            run_kw["etp_returns"] = etp_returns
        else:
            run_kw["etp_bundle"] = SPX_ETP
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns, risk_free=float(prices["tbill_rate"].mean()))
    return {
        "strategy": spec["strategy"],
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats.get("sortino"),
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "win_rate": stats.get("win_rate"),
        "profit_factor": stats.get("profit_factor"),
        "beta": stats.get("beta"),
        "alpha": stats.get("alpha"),
        **counts,
    }


def buy_hold_row(
    prices: pd.DataFrame,
    leverage: float,
    label: str,
    etp_returns: pd.DataFrame | None = None,
) -> dict:
    """Run a buy-and-hold strategy at fixed leverage."""
    lev = pd.Series(float(leverage), index=prices.index)
    run_kw: dict = {"name": label}
    if leverage > 1.0 and etp_returns is not None:
        run_kw["etp_returns"] = etp_returns
    elif leverage > 1.0:
        run_kw["etp_bundle"] = SPX_ETP
    result = make_engine().run(prices, lev, **run_kw)
    stats = comprehensive_stats(result.equity, result.daily_returns, risk_free=float(prices["tbill_rate"].mean()))
    return {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats.get("sortino"),
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "win_rate": stats.get("win_rate"),
        "profit_factor": stats.get("profit_factor"),
        "beta": stats.get("beta"),
        "alpha": stats.get("alpha"),
        "pct_days_cash": 0.0 if leverage > 0 else 100.0,
        "pct_days_1x": 100.0 if 0 < leverage < 1.5 else 0.0,
        "pct_days_2x": 100.0 if 1.5 <= leverage < 2.5 else 0.0,
        "pct_days_3x": 100.0 if leverage >= 2.5 else 0.0,
        "avg_leverage": float(leverage) if leverage > 0 else 0.0,
        "total_trades": 0,
    }


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


def monte_carlo(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    spec: dict | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Run block-bootstrap Monte Carlo for the distance-scale strategy."""
    if spec is None:
        spec = DEFAULT_SPEC
    rows: list[dict] = []
    paths = bootstrap_etp_paths(
        prices,
        etp_panel,
        n_sims=N_SIMS,
        horizon_days=HORIZON_DAYS,
        block_days=BLOCK_DAYS,
        seed=SEED,
    )
    for sim, (path, path_etp) in enumerate(paths):
        if sim % 25 == 0:
            print(f"  Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        row = run_strategy(path, spec, etp_returns=path_etp)
        row["simulation"] = sim
        rows.append(row)
    df = pd.DataFrame(rows)

    cagr = df["cagr"].dropna()
    max_dd = df["max_drawdown"].dropna()
    end_val = df["end_$"].dropna()

    summary = {
        "strategy": spec["strategy"],
        "n_sims": N_SIMS,
        "horizon_years": HORIZON_DAYS / 252.0,
        "block_days": BLOCK_DAYS,
        "seed": SEED,
        "method": MC_ETP_METHOD,
        "median_cagr": float(cagr.median()) if len(cagr) else None,
        "p10_cagr": float(cagr.quantile(0.10)) if len(cagr) else None,
        "p90_cagr": float(cagr.quantile(0.90)) if len(cagr) else None,
        "median_max_drawdown": float(max_dd.median()) if len(max_dd) else None,
        "p10_max_drawdown": float(max_dd.quantile(0.10)) if len(max_dd) else None,
        "p90_max_drawdown": float(max_dd.quantile(0.90)) if len(max_dd) else None,
        "median_sharpe": float(df["sharpe"].median()) if "sharpe" in df.columns else None,
        "median_end_$": float(end_val.median()) if len(end_val) else None,
        "prob_max_dd_worse_35pct": float((max_dd <= -0.35).mean()) if len(max_dd) else None,
        "prob_max_dd_worse_40pct": float((max_dd <= -0.40).mean()) if len(max_dd) else None,
        "prob_max_dd_worse_50pct": float((max_dd <= -0.50).mean()) if len(max_dd) else None,
        "prob_end_below_start": float((end_val < INITIAL_CAPITAL).mean()) if len(end_val) else None,
    }
    return df, summary


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def pct(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x) * 100:.2f}%"


def money(x: float | None) -> str | None:
    if x is None:
        return None
    return f"${float(x):,.0f}"


def fmt3(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x):.3f}"


def fmt2(x: float | None) -> str | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return f"{float(x):.2f}"


# ---------------------------------------------------------------------------
# Signal history builder
# ---------------------------------------------------------------------------


def build_signal_history(
    prices: pd.DataFrame,
    spec: dict | None = None,
) -> list[dict]:
    """Build daily signal history for the Signal page table and charts.

    One entry per trading day with: date, signal, leverage, spx_close,
    sma200, rsi14, action.
    """
    if spec is None:
        spec = DEFAULT_SPEC

    close = prices["spx_close"]
    sma_w = int(spec["sma_window"])
    band_p = float(spec["band_pct"])

    s = sma(close, sma_w)

    # Compute the full strategy signal for action tracking
    final_lev, _ = compute_strategy_leverage(prices, spec)

    history: list[dict] = []
    prev_lev = 0.0

    for i in range(len(prices)):
        dt = prices.index[i]
        c = float(close.iloc[i]) if not pd.isna(close.iloc[i]) else None
        sma_val = float(s.iloc[i]) if not pd.isna(s.iloc[i]) else None
        lev_val = float(final_lev.iloc[i]) if not pd.isna(final_lev.iloc[i]) else 0.0

        # Determine signal label
        if lev_val <= 0.0:
            signal_label = "cash"
        else:
            signal_label = "long"

        # Determine action
        if i == 0:
            action = "start"
        elif prev_lev <= 0.0 and lev_val > 0.0:
            action = "enter_long"
        elif prev_lev > 0.0 and lev_val <= 0.0:
            action = "exit_to_cash"
        else:
            action = "hold"

        history.append({
            "date": dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10],
            "signal": signal_label,
            "leverage": round(lev_val, 1),
            "spx_close": round(c, 2) if c is not None else None,
            "sma200": round(sma_val, 2) if sma_val is not None else None,
            "rsi14": None,
            "action": action,
        })
        prev_lev = lev_val

    return history


def build_price_sma_data(
    prices: pd.DataFrame,
    spec: dict | None = None,
) -> dict:
    """Build price + SMA200 + band data for the price chart."""
    if spec is None:
        spec = DEFAULT_SPEC

    close = prices["spx_close"]
    sma_w = int(spec["sma_window"])
    band_p = float(spec["band_pct"])

    s = sma(close, sma_w)
    upper_mult = 1.0 + band_p
    lower_mult = 1.0 - band_p

    dates: list[str] = []
    spx_close_list: list[float | None] = []
    sma200_list: list[float | None] = []
    upper_band_list: list[float | None] = []
    lower_band_list: list[float | None] = []

    for i in range(len(prices)):
        dt = prices.index[i]
        dates.append(dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10])
        c = float(close.iloc[i]) if not pd.isna(close.iloc[i]) else None
        sma_val = float(s.iloc[i]) if not pd.isna(s.iloc[i]) else None
        spx_close_list.append(round(c, 2) if c is not None else None)
        sma200_list.append(round(sma_val, 2) if sma_val is not None else None)
        upper_band_list.append(round(sma_val * upper_mult, 2) if sma_val is not None else None)
        lower_band_list.append(round(sma_val * lower_mult, 2) if sma_val is not None else None)

    return {
        "dates": dates,
        "spx_close": spx_close_list,
        "sma200": sma200_list,
        "sma200_upper_band": upper_band_list,
        "sma200_lower_band": lower_band_list,
    }


def build_equity_curve(
    prices: pd.DataFrame,
    default_lev: pd.Series,
) -> dict:
    """Build daily equity curves for strategy and B&H 1x."""
    # Strategy equity (no ETP needed for 1x)
    strat_result = make_engine().run(
        prices, default_lev,
        name="SMA200 ±3% Band 1x/cash",
    )
    strat_eq = strat_result.equity

    # B&H 1x
    bh1_lev = pd.Series(1.0, index=prices.index)
    bh1_result = make_engine().run(prices, bh1_lev, name="B&H 1x")
    bh1_eq = bh1_result.equity

    dates: list[str] = []
    strat_list: list[float] = []
    bh1_list: list[float] = []

    for i in range(len(prices)):
        dt = prices.index[i]
        dates.append(dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10])
        strat_list.append(round(float(strat_eq.iloc[i]), 2) if i < len(strat_eq) and not pd.isna(strat_eq.iloc[i]) else None)
        bh1_list.append(round(float(bh1_eq.iloc[i]), 2) if i < len(bh1_eq) and not pd.isna(bh1_eq.iloc[i]) else None)

    return {
        "dates": dates,
        "strategy_equity": strat_list,
        "buy_hold_1x_equity": bh1_list,
    }


# ---------------------------------------------------------------------------
# Site data payload builder
# ---------------------------------------------------------------------------


def build_site_payload(
    prices: pd.DataFrame,
    comparison: list[dict],
    default_row: dict,
    mc_summary: dict,
    etp_panel: pd.DataFrame,
    signal_history: list[dict],
    price_sma_data: dict,
    equity_curve: dict,
) -> dict:
    """Assemble the full site_data.json payload matching spx_guarded_site_data.json structure."""
    bh1 = next(r for r in comparison if r["strategy"] == "Buy & Hold SPY 1x")
    bh2 = next(r for r in comparison if r["strategy"] == "Buy & Hold SSO 2x")
    bh3 = next(r for r in comparison if r["strategy"] == "Buy & Hold UPRO 3x")

    # Try to load original guarded from existing site data
    original_guarded = None
    guarded_json_path = ROOT / "spx_guarded_site_data.json"
    if guarded_json_path.exists():
        try:
            guarded_data = json.loads(guarded_json_path.read_text(encoding="utf-8"))
            original_guarded = guarded_data.get("original_guarded")
        except Exception:
            pass

    return {
        "ticker": SPX_TICKER,
        "asset_label": "S&P 500",
        "strategy_params": DEFAULT_SPEC,
        "sample": {
            "start_date": prices.index[0].date().isoformat(),
            "end_date": prices.index[-1].date().isoformat(),
            "trading_days": len(prices),
        },
        "default_backtest": {
            **default_row,
            "cagr_pct": pct(default_row["cagr"]),
            "max_drawdown_pct": pct(default_row["max_drawdown"]),
            "ann_volatility_pct": pct(default_row["ann_volatility"]),
            "sharpe_fmt": fmt3(default_row["sharpe"]),
            "sortino_fmt": fmt3(default_row.get("sortino")),
            "end_value_fmt": money(default_row["end_$"]),
            "calmar_fmt": fmt2(default_row.get("calmar")),
            "win_rate_pct": pct(default_row.get("win_rate")),
            "profit_factor_fmt": fmt2(default_row.get("profit_factor")),
            "beta_fmt": fmt2(default_row.get("beta")),
            "alpha_pct": pct(default_row.get("alpha")),
        },
        "buy_and_hold_1x": {
            **bh1,
            "cagr_pct": pct(bh1["cagr"]),
            "max_drawdown_pct": pct(bh1["max_drawdown"]),
            "ann_volatility_pct": pct(bh1["ann_volatility"]),
            "sharpe_fmt": fmt3(bh1["sharpe"]),
            "end_value_fmt": money(bh1["end_$"]),
        },
        "buy_and_hold_2x": {
            **bh2,
            "cagr_pct": pct(bh2["cagr"]),
            "max_drawdown_pct": pct(bh2["max_drawdown"]),
            "ann_volatility_pct": pct(bh2["ann_volatility"]),
            "sharpe_fmt": fmt3(bh2["sharpe"]),
            "end_value_fmt": money(bh2["end_$"]),
        },
        "buy_and_hold_3x": {
            **bh3,
            "cagr_pct": pct(bh3["cagr"]),
            "max_drawdown_pct": pct(bh3["max_drawdown"]),
            "ann_volatility_pct": pct(bh3["ann_volatility"]),
            "sharpe_fmt": fmt3(bh3["sharpe"]),
            "end_value_fmt": money(bh3["end_$"]),
        },
        "comparison_table": [
            {
                **row,
                "cagr_pct": pct(row["cagr"]),
                "ann_volatility_pct": pct(row.get("ann_volatility")),
                "max_drawdown_pct": pct(row["max_drawdown"]),
                "sharpe_fmt": fmt3(row.get("sharpe")),
                "sortino_fmt": fmt3(row.get("sortino")),
                "end_value_fmt": money(row.get("end_$")),
                "calmar_fmt": fmt2(row.get("calmar")),
                "win_rate_pct": pct(row.get("win_rate")),
                "profit_factor_fmt": fmt2(row.get("profit_factor")),
                "beta_fmt": fmt2(row.get("beta")),
                "alpha_pct": pct(row.get("alpha")),
                "cash_pct": pct(row.get("pct_days_cash", 0.0) / 100.0),
                "avg_leverage_fmt": fmt2(row.get("avg_leverage")),
            }
            for row in comparison
        ],
        "monte_carlo": {
            **mc_summary,
            "median_cagr_pct": pct(mc_summary.get("median_cagr")),
            "p10_cagr_pct": pct(mc_summary.get("p10_cagr")),
            "p90_cagr_pct": pct(mc_summary.get("p90_cagr")),
            "median_max_drawdown_pct": pct(mc_summary.get("median_max_drawdown")),
            "p10_max_drawdown_pct": pct(mc_summary.get("p10_max_drawdown")),
            "p90_max_drawdown_pct": pct(mc_summary.get("p90_max_drawdown")),
            "median_sharpe_fmt": fmt3(mc_summary.get("median_sharpe")),
            "median_end_value_fmt": money(mc_summary.get("median_end_$")),
            "prob_max_dd_worse_35pct_fmt": pct(mc_summary.get("prob_max_dd_worse_35pct")),
            "prob_max_dd_worse_40pct_fmt": pct(mc_summary.get("prob_max_dd_worse_40pct")),
            "prob_max_dd_worse_50pct_fmt": pct(mc_summary.get("prob_max_dd_worse_50pct")),
            "prob_end_below_start_fmt": pct(mc_summary.get("prob_end_below_start")),
        },
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "levered_pnl_model": (
            "1x unlevered S&P 500 exposure (SPY or VUSA.L/VUAG.L UCITS); "
            "no ETP leverage decay. "
            f"Monte Carlo: {MC_ETP_METHOD}"
        ),
        "etp_coverage": etp_coverage_summary(etp_panel),
        "original_guarded": original_guarded,
        "monte_carlo_variants": [],
        "price_sma_data": price_sma_data,
        "signal_history": signal_history,
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading S&P 500, T-bill, and VIX data...", flush=True)
    prices = download_spx_panel()
    print(
        f"Loaded {len(prices)} sessions: "
        f"{prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    print("Building S&P ETP return panel (SPY/SSO/UPRO)...", flush=True)
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    export_etp_returns_json(etp_panel, SPX_ETP, ETP_JSON)
    print(f"  ETP coverage: {etp_coverage_summary(etp_panel)}", flush=True)

    # -----------------------------------------------------------------------
    # Run all strategies for comparison table
    # -----------------------------------------------------------------------
    print("\nRunning strategy backtests...", flush=True)

    # Benchmarks: Buy & Hold
    comparison: list[dict] = [
        buy_hold_row(prices, 1.0, "Buy & Hold SPY 1x", etp_panel),
        buy_hold_row(prices, 2.0, "Buy & Hold SSO 2x", etp_panel),
        buy_hold_row(prices, 3.0, "Buy & Hold UPRO 3x", etp_panel),
    ]

    # Benchmarks: Plain SMA200 band (no RSI filter, no distance scale)
    for lev_val, label in [(3.0, "SMA200 ±3% Band 3x"), (2.0, "SMA200 ±3% Band 2x")]:
        base_signal = sma_band_signal(prices, 200, 0.03)
        plain_lev = base_signal * lev_val
        result = make_engine().run(
            prices, plain_lev,
            name=label,
            etp_returns=etp_panel,
        )
        stats = comprehensive_stats(result.equity, result.daily_returns, risk_free=float(prices["tbill_rate"].mean()))
        comparison.append({
            "strategy": label,
            "cagr": stats["cagr"],
            "ann_volatility": stats["volatility"],
            "sharpe": stats["sharpe"],
            "sortino": stats.get("sortino"),
            "max_drawdown": stats["max_drawdown"],
            "calmar": stats.get("calmar"),
            "end_$": float(result.equity.iloc[-1]),
            "rebalances": result.rebalance_count,
            "trading_costs_total": result.trading_costs_total,
            "funding_costs_total": result.funding_costs_total,
            "win_rate": stats.get("win_rate"),
            "profit_factor": stats.get("profit_factor"),
            "beta": stats.get("beta"),
            "alpha": stats.get("alpha"),
            "pct_days_cash": float((plain_lev <= 0.0).mean() * 100.0),
            "pct_days_1x": 0.0,
            "pct_days_2x": 100.0 if lev_val == 2.0 else 0.0,
            "pct_days_3x": 100.0 if lev_val == 3.0 else 0.0,
            "avg_leverage": float((plain_lev[plain_lev > 0.0].mean())) if (plain_lev > 0.0).any() else 0.0,
            "total_trades": int((plain_lev.diff().fillna(0.0) != 0.0).sum()),
        })

    # SMA200 ±3% Band 1x/cash (for additional context)
    base_signal = sma_band_signal(prices, 200, 0.03)
    sma1_lev = base_signal * 1.0
    sma1_result = make_engine().run(prices, sma1_lev, name="SMA200 ±3% Band 1x/cash")
    sma1_stats = comprehensive_stats(sma1_result.equity, sma1_result.daily_returns, risk_free=float(prices["tbill_rate"].mean()))
    comparison.append({
        "strategy": "SMA200 ±3% Band 1x/cash",
        "cagr": sma1_stats["cagr"],
        "ann_volatility": sma1_stats["volatility"],
        "sharpe": sma1_stats["sharpe"],
        "sortino": sma1_stats.get("sortino"),
        "max_drawdown": sma1_stats["max_drawdown"],
        "calmar": sma1_stats.get("calmar"),
        "end_$": float(sma1_result.equity.iloc[-1]),
        "rebalances": sma1_result.rebalance_count,
        "trading_costs_total": sma1_result.trading_costs_total,
        "funding_costs_total": sma1_result.funding_costs_total,
        "win_rate": sma1_stats.get("win_rate"),
        "profit_factor": sma1_stats.get("profit_factor"),
        "beta": sma1_stats.get("beta"),
        "alpha": sma1_stats.get("alpha"),
        "pct_days_cash": float((sma1_lev <= 0.0).mean() * 100.0),
        "pct_days_1x": float((sma1_lev > 0.0).mean() * 100.0),
        "pct_days_2x": 0.0,
        "pct_days_3x": 0.0,
        "avg_leverage": 1.0 if (sma1_lev > 0.0).any() else 0.0,
        "total_trades": int((sma1_lev.diff().fillna(0.0) != 0.0).sum()),
    })

    # The default strategy: SMA200 ±3% Band 1x/cash
    default_row = run_strategy(prices, DEFAULT_SPEC)
    comparison.append(default_row)
    print(
        f"  {DEFAULT_SPEC['strategy']}: CAGR={pct(default_row['cagr'])}, "
        f"Max DD={pct(default_row['max_drawdown'])}, "
        f"Sharpe={fmt3(default_row['sharpe'])}, "
        f"Sortino={fmt3(default_row.get('sortino'))}, "
        f"End={money(default_row['end_$'])}",
        flush=True,
    )

    # -----------------------------------------------------------------------
    # Write comparison CSV
    # -----------------------------------------------------------------------
    csv_path = OUTPUT_DIR / "spx_distance_scale_comparison.csv"
    csv_cols = [
        "strategy", "cagr", "ann_volatility", "sharpe", "sortino",
        "max_drawdown", "calmar", "end_$", "rebalances",
        "trading_costs_total", "funding_costs_total",
        "win_rate", "profit_factor", "beta", "alpha",
        "pct_days_cash", "pct_days_1x", "pct_days_2x", "pct_days_3x",
        "avg_leverage", "total_trades",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        for row in comparison:
            writer.writerow({k: row.get(k) for k in csv_cols})
    print(f"\nWrote comparison CSV: {csv_path}", flush=True)

    # -----------------------------------------------------------------------
    # Build signal history, price/SMA data, and equity curve
    # -----------------------------------------------------------------------
    print("\nBuilding signal history...", flush=True)
    signal_history = build_signal_history(prices, DEFAULT_SPEC)
    print(f"  {len(signal_history)} daily entries", flush=True)

    print("Building price/SMA data...", flush=True)
    price_sma_data = build_price_sma_data(prices, DEFAULT_SPEC)

    print("Building equity curves...", flush=True)
    default_lev, _ = compute_strategy_leverage(prices, DEFAULT_SPEC)
    equity_curve = build_equity_curve(prices, default_lev)

    # -----------------------------------------------------------------------
    # Monte Carlo
    # -----------------------------------------------------------------------
    print("\nRunning Monte Carlo (200 paths × 10yr, 21-day blocks)...", flush=True)
    mc_paths, mc_summary = monte_carlo(prices, etp_panel, DEFAULT_SPEC)
    mc_paths.to_csv(
        OUTPUT_DIR / "spx_distance_scale_monte_carlo_paths.csv",
        index=False,
    )
    print(
        f"  Median CAGR: {pct(mc_summary.get('median_cagr'))}, "
        f"Median Max DD: {pct(mc_summary.get('median_max_dd'))}",
        flush=True,
    )

    # -----------------------------------------------------------------------
    # Build and write site data JSON
    # -----------------------------------------------------------------------
    print("\nBuilding site data payload...", flush=True)
    payload = build_site_payload(
        prices, comparison, default_row, mc_summary, etp_panel,
        signal_history, price_sma_data, equity_curve,
    )

    # NaN/Inf are invalid JSON (browsers reject them) — convert to null before writing.
    def _json_safe(o):
        if isinstance(o, dict):
            return {k: _json_safe(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_json_safe(v) for v in o]
        if isinstance(o, (float, np.floating)):
            f = float(o)
            return None if (f != f or f in (float("inf"), float("-inf"))) else f
        if isinstance(o, np.integer):
            return int(o)
        return o
    payload = _json_safe(payload)

    # Write to both locations
    site_json_str = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    SITE_DATA_JSON.write_text(site_json_str, encoding="utf-8")
    (OUTPUT_DIR / "spx_distance_scale_site_data.json").write_text(
        site_json_str, encoding="utf-8"
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    bh1_row = comparison[0]
    print("\n=== S&P 500 SMA200 ±3% Band 1x/cash ===", flush=True)
    print(
        f"Default: CAGR={pct(default_row['cagr'])}, "
        f"Max DD={pct(default_row['max_drawdown'])}, "
        f"Vol={pct(default_row['ann_volatility'])}, "
        f"Sharpe={fmt3(default_row['sharpe'])}, "
        f"Sortino={fmt3(default_row.get('sortino'))}",
        flush=True,
    )
    print(
        f"End value: {money(default_row['end_$'])}  "
        f"vs B&H 1x CAGR={pct(bh1_row['cagr'])} / "
        f"DD={pct(bh1_row['max_drawdown'])}",
        flush=True,
    )
    print(
        f"% cash: {pct(default_row['pct_days_cash'] / 100.0)}, "
        f"% 1x: {pct(default_row['pct_days_1x'] / 100.0)}, "
        f"% 2x: {pct(default_row['pct_days_2x'] / 100.0)}, "
        f"% 3x: {pct(default_row['pct_days_3x'] / 100.0)}, "
        f"avg lev: {fmt2(default_row['avg_leverage'])}, "
        f"rebalances: {default_row['rebalances']}",
        flush=True,
    )
    print(
        f"\nMonte Carlo median CAGR: {pct(mc_summary.get('median_cagr'))}, "
        f"median max DD: {pct(mc_summary.get('median_max_dd'))}",
        flush=True,
    )
    print(
        f"P(DD < -35%): {pct(mc_summary.get('prob_max_dd_worse_35pct'))}, "
        f"P(DD < -40%): {pct(mc_summary.get('prob_max_dd_worse_40pct'))}, "
        f"P(DD < -50%): {pct(mc_summary.get('prob_max_dd_worse_50pct'))}",
        flush=True,
    )
    print(f"\nWrote {SITE_DATA_JSON.name} and {ETP_JSON.name}", flush=True)
    print(f"Wrote {csv_path.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
