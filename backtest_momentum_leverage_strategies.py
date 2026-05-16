"""Backtest momentum-triggered leverage strategies over the last 30 years."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_guarded_tiered_sma20_50_200 import guarded_tiered_leverage, sma_cash_leverage
from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "momentum_leverage_strategies"


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def _empty_lev(prices: pd.DataFrame) -> pd.Series:
    return pd.Series(0.0, index=prices.index, dtype=float)


def sma_stack_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    lev = _empty_lev(prices)
    lev.loc[close > sma200] = 1.0
    lev.loc[(close > sma50) & (sma50 > sma200)] = 2.0
    lev.loc[(close > sma20) & (sma20 > sma50) & (sma50 > sma200)] = 3.0
    return lev.fillna(0.0)


def sma_slope_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    slope20 = sma20 / sma20.shift(20) - 1.0
    slope50 = sma50 / sma50.shift(20) - 1.0

    lev = _empty_lev(prices)
    lev.loc[close > sma200] = 1.0
    lev.loc[(close > sma50) & (slope50 > 0.0)] = 2.0
    lev.loc[(close > sma20) & (close > sma200) & (slope20 > 0.01) & (slope50 > 0.005)] = 3.0
    return lev.fillna(0.0)


def macd_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma200 = close.rolling(200, min_periods=200).mean()
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd - signal
    hist_rising_3d = (hist > hist.shift(1)) & (hist.shift(1) > hist.shift(2))

    lev = _empty_lev(prices)
    long_trend = close > sma200
    lev.loc[long_trend] = 1.0
    lev.loc[long_trend & (macd > signal)] = 2.0
    lev.loc[long_trend & (hist > 0.0) & hist_rising_3d] = 3.0
    return lev.fillna(0.0)


def rsi_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0.0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()

    lev = _empty_lev(prices)
    lev.loc[rsi > 50.0] = 1.0
    lev.loc[(rsi > 55.0) & (close > sma50)] = 2.0
    lev.loc[(rsi > 60.0) & (close > sma20)] = 3.0
    return lev.fillna(0.0)


def donchian_breakout_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma200 = close.rolling(200, min_periods=200).mean()
    high60 = close.rolling(60, min_periods=60).max().shift(1)
    high120 = close.rolling(120, min_periods=120).max().shift(1)
    low20 = close.rolling(20, min_periods=20).min().shift(1)

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = float(close.loc[dt])
        if not np.isfinite(px):
            lev.loc[dt] = current
            continue

        if np.isfinite(sma200.loc[dt]) and px < float(sma200.loc[dt]):
            current = 0.0
        elif np.isfinite(low20.loc[dt]) and px < float(low20.loc[dt]):
            current = min(current, 1.0)
        elif np.isfinite(high120.loc[dt]) and px >= float(high120.loc[dt]):
            current = 3.0
        elif np.isfinite(high60.loc[dt]) and px >= float(high60.loc[dt]):
            current = max(current, 2.0)
        elif np.isfinite(sma200.loc[dt]) and px > float(sma200.loc[dt]):
            current = max(current, 1.0)

        lev.loc[dt] = current
    return lev.fillna(0.0)


def vol_adjusted_momentum(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    base = sma_stack_momentum(prices)
    realized_vol20 = close.pct_change().rolling(20, min_periods=20).std() * np.sqrt(252)

    lev = base.copy()
    lev.loc[realized_vol20 > 0.25] = (lev.loc[realized_vol20 > 0.25] - 1.0).clip(lower=0.0)
    lev.loc[realized_vol20 > 0.35] = lev.loc[realized_vol20 > 0.35].clip(upper=1.0)
    return lev.fillna(0.0)


def exposure_mix(lev: pd.Series) -> dict[str, float]:
    return {
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def add_row(
    rows: list[dict],
    equity_curves: dict[str, pd.Series],
    prices: pd.DataFrame,
    engine: PortfolioEngine,
    strategy: str,
    rule_group: str,
    lev: pd.Series,
    description: str,
) -> None:
    result = engine.run(prices, lev, name=strategy)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    row = {
        "strategy": strategy,
        "group": rule_group,
        "description": description,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats["sortino"],
        "calmar": stats["calmar"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "funding_costs_total": result.funding_costs_total,
        "trading_costs_total": result.trading_costs_total,
        **exposure_mix(result.leverage),
    }
    rows.append(row)
    equity_curves[strategy] = result.equity


def annual_equity(equity_curves: dict[str, pd.Series], keep: list[str]) -> dict[str, list]:
    annual = {}
    for name in keep:
        eq = equity_curves[name]
        sampled = eq.resample("YE").last()
        annual[name] = [
            {"year": int(dt.year), "equity": float(value)}
            for dt, value in sampled.items()
            if pd.notna(value)
        ]
    return annual


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data(years=30)
    engine = make_engine()
    rows: list[dict] = []
    equity_curves: dict[str, pd.Series] = {}

    strategies: list[tuple[str, str, pd.Series, str]] = [
        (
            "SMA stack momentum",
            "Momentum trigger",
            sma_stack_momentum(prices),
            "0x below SMA200; 1x above SMA200; 2x when close > SMA50 > SMA200; 3x when close > SMA20 > SMA50 > SMA200.",
        ),
        (
            "SMA slope momentum",
            "Momentum trigger",
            sma_slope_momentum(prices),
            "0x below SMA200; 1x above SMA200; 2x on positive SMA50 slope; 3x on strong SMA20 and SMA50 slopes.",
        ),
        (
            "MACD momentum",
            "Momentum trigger",
            macd_momentum(prices),
            "0x below SMA200; 1x above SMA200; 2x when MACD > signal; 3x when MACD histogram is positive and rising.",
        ),
        (
            "RSI momentum",
            "Momentum trigger",
            rsi_momentum(prices),
            "1x when RSI > 50; 2x when RSI > 55 and close > SMA50; 3x when RSI > 60 and close > SMA20.",
        ),
        (
            "Donchian breakout momentum",
            "Momentum trigger",
            donchian_breakout_momentum(prices),
            "0x below SMA200; 1x above SMA200; 2x on 60-day high breakout; 3x on 120-day high breakout; reduce on 20-day low.",
        ),
        (
            "Vol-adjusted SMA stack",
            "Momentum trigger",
            vol_adjusted_momentum(prices),
            "SMA stack momentum, reduced by one tier when 20-day realized volatility exceeds 25%, capped at 1x above 35%.",
        ),
    ]

    for lev_value in (1.0, 2.0, 3.0):
        add_row(
            rows,
            equity_curves,
            prices,
            engine,
            f"Buy & hold {lev_value:.0f}x",
            "Reference",
            pd.Series(lev_value, index=prices.index),
            f"Constant {lev_value:.0f}x exposure.",
        )

    for lev_value in (1.0, 2.0, 3.0):
        add_row(
            rows,
            equity_curves,
            prices,
            engine,
            f"SMA20 {lev_value:.0f}x/cash",
            "Reference",
            sma_cash_leverage(prices, 20, lev_value),
            f"{lev_value:.0f}x when close is above SMA20, otherwise cash/T-bills.",
        )

    guarded_lev, _ = guarded_tiered_leverage(prices, 20)
    add_row(
        rows,
        equity_curves,
        prices,
        engine,
        "Guarded A10/B20 SMA20",
        "Reference",
        guarded_lev,
        "Drawdown-triggered recovery leverage reference from the current website strategy.",
    )

    for name, group, lev, description in strategies:
        add_row(rows, equity_curves, prices, engine, name, group, lev, description)

    results = pd.DataFrame(rows).sort_values(["group", "cagr"], ascending=[True, False])
    results_path = OUTPUT_DIR / "momentum_leverage_results.csv"
    results.to_csv(results_path, index=False)

    keep_for_chart = [
        "SMA stack momentum",
        "SMA slope momentum",
        "MACD momentum",
        "RSI momentum",
        "Donchian breakout momentum",
        "Vol-adjusted SMA stack",
        "Guarded A10/B20 SMA20",
        "SMA20 3x/cash",
        "Buy & hold 1x",
    ]
    chart_data = {
        "start_date": str(prices.index[0].date()),
        "end_date": str(prices.index[-1].date()),
        "annual_equity": annual_equity(equity_curves, keep_for_chart),
    }
    chart_path = OUTPUT_DIR / "momentum_leverage_chart_data.json"
    chart_path.write_text(json.dumps(chart_data, indent=2), encoding="utf-8")

    disp = results.copy()
    for col in ["cagr", "ann_volatility", "max_drawdown", "pct_days_cash", "pct_days_1x", "pct_days_2x", "pct_days_3x"]:
        disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%" if col in {"cagr", "ann_volatility", "max_drawdown"} else f"{x:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")
    print(f"Momentum leverage backtests: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print(disp[["strategy", "group", "cagr", "ann_volatility", "sharpe", "max_drawdown", "end_$", "rebalances"]].to_string(index=False))
    print(f"\nCSV: {results_path}")
    print(f"Chart data: {chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
