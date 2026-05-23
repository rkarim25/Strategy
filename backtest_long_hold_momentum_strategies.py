"""Backtest long-hold momentum leverage strategies with slower exits."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from backtest_guarded_tiered_sma20_50_200 import guarded_tiered_leverage, sma_cash_leverage
from data_manager import SPX_TICKER, TBILL_TICKER
from engine import TRADING_COST_FROM_MID_PCT, PortfolioEngine
from etp_leverage import SPX_ETP, build_etp_return_panel
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "long_hold_momentum_strategies"


def load_ohlc_data(years: int = 30) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    raw = yf.download(
        [SPX_TICKER, TBILL_TICKER],
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No data returned from yfinance.")

    if not isinstance(raw.columns, pd.MultiIndex):
        raise ValueError("Expected MultiIndex data from yfinance.")

    out = pd.DataFrame(index=raw.index)
    out["spx_close"] = raw["Close"][SPX_TICKER]
    out["spx_high"] = raw["High"][SPX_TICKER]
    out["spx_low"] = raw["Low"][SPX_TICKER]
    out["tbill_rate"] = raw["Close"][TBILL_TICKER] / 100.0
    return out.sort_index().ffill().dropna(how="any")


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


def long_hold_time_series_momentum(prices: pd.DataFrame) -> pd.Series:
    """3/6/12 month absolute momentum with explicit slow exits."""
    close = prices["spx_close"].astype(float)
    ret3 = close / close.shift(63) - 1.0
    ret6 = close / close.shift(126) - 1.0
    ret12 = close / close.shift(252) - 1.0
    sma200 = close.rolling(200, min_periods=200).mean()

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = close.loc[dt]
        if pd.isna(px) or pd.isna(ret12.loc[dt]) or pd.isna(sma200.loc[dt]):
            lev.loc[dt] = current
            continue

        if px < sma200.loc[dt] or ret12.loc[dt] < 0.0:
            current = 0.0
        elif current >= 3.0:
            current = 3.0 if ret6.loc[dt] >= 0.0 else 2.0
        elif current >= 2.0:
            current = 2.0 if ret12.loc[dt] >= 0.0 else 1.0

        if ret3.loc[dt] > 0.0 and ret6.loc[dt] > 0.0 and ret12.loc[dt] > 0.0:
            current = max(current, 3.0)
        elif ret6.loc[dt] > 0.0 and ret12.loc[dt] > 0.0:
            current = max(current, 2.0)
        elif ret12.loc[dt] > 0.0:
            current = max(current, 1.0)

        lev.loc[dt] = current
    return lev.fillna(0.0)


def sma_stack_hysteresis(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma100 = close.rolling(100, min_periods=100).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = close.loc[dt]
        if pd.isna(sma200.loc[dt]):
            lev.loc[dt] = current
            continue
        if px < sma200.loc[dt]:
            current = 0.0
        elif current == 3.0 and (px < sma100.loc[dt] or sma50.loc[dt] < sma100.loc[dt]):
            current = 2.0
        elif current == 2.0 and px < sma200.loc[dt]:
            current = 1.0
        elif sma20.loc[dt] > sma50.loc[dt] > sma200.loc[dt] and px > sma20.loc[dt]:
            current = 3.0
        elif sma50.loc[dt] > sma200.loc[dt] and px > sma50.loc[dt]:
            current = max(current, 2.0)
        elif px > sma200.loc[dt]:
            current = max(current, 1.0)
        lev.loc[dt] = current
    return lev.fillna(0.0)


def absolute_momentum_trailing_stop(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    ret6 = close / close.shift(126) - 1.0
    ret12 = close / close.shift(252) - 1.0
    low63 = close.rolling(63, min_periods=63).min().shift(1)
    sma100 = close.rolling(100, min_periods=100).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = close.loc[dt]
        if pd.isna(ret12.loc[dt]) or pd.isna(sma200.loc[dt]):
            lev.loc[dt] = current
            continue
        if px < sma200.loc[dt] or ret12.loc[dt] < 0.0:
            current = 0.0
        elif current >= 2.0 and (px < low63.loc[dt] or px < sma100.loc[dt]):
            current = 1.0
        elif ret6.loc[dt] > 0.0 and ret12.loc[dt] > 0.0:
            current = 3.0
        elif ret12.loc[dt] > 0.0:
            current = max(current, 1.0)
        lev.loc[dt] = current
    return lev.fillna(0.0)


def adx_trend_strength(prices: pd.DataFrame) -> pd.Series:
    high = prices["spx_high"].astype(float)
    low = prices["spx_low"].astype(float)
    close = prices["spx_close"].astype(float)
    sma100 = close.rolling(100, min_periods=100).mean()
    sma200 = close.rolling(200, min_periods=200).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=prices.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=prices.index)
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    plus_di = 100.0 * plus_dm.rolling(14, min_periods=14).mean() / atr
    minus_di = 100.0 * minus_dm.rolling(14, min_periods=14).mean() / atr
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(14, min_periods=14).mean()

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = close.loc[dt]
        if pd.isna(adx.loc[dt]) or pd.isna(sma200.loc[dt]):
            lev.loc[dt] = current
            continue
        if px < sma200.loc[dt] or (current > 1.0 and adx.loc[dt] < 18.0) or px < sma100.loc[dt]:
            current = 0.0 if px < sma200.loc[dt] else 1.0
        elif px > sma200.loc[dt] and plus_di.loc[dt] > minus_di.loc[dt] and adx.loc[dt] > 25.0:
            current = 3.0
        elif px > sma200.loc[dt] and plus_di.loc[dt] > minus_di.loc[dt] and adx.loc[dt] > 20.0:
            current = max(current, 2.0)
        elif px > sma200.loc[dt]:
            current = max(current, 1.0)
        lev.loc[dt] = current
    return lev.fillna(0.0)


def keltner_trend_channel(prices: pd.DataFrame) -> pd.Series:
    high = prices["spx_high"].astype(float)
    low = prices["spx_low"].astype(float)
    close = prices["spx_close"].astype(float)
    ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema100 = close.ewm(span=100, adjust=False, min_periods=100).mean()
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr20 = tr.rolling(20, min_periods=20).mean()
    upper = ema50 + 1.5 * atr20

    lev = _empty_lev(prices)
    current = 0.0
    for dt in prices.index:
        px = close.loc[dt]
        if pd.isna(ema100.loc[dt]) or pd.isna(upper.loc[dt]):
            lev.loc[dt] = current
            continue
        if px < ema100.loc[dt]:
            current = 0.0
        elif current >= 2.0 and px < ema50.loc[dt]:
            current = 1.0
        elif px > upper.loc[dt]:
            current = 3.0
        elif px > ema50.loc[dt]:
            current = max(current, 2.0)
        lev.loc[dt] = current
    return lev.fillna(0.0)


def monthly_momentum_regime(prices: pd.DataFrame) -> pd.Series:
    close = prices["spx_close"].astype(float)
    month_end = close.resample("ME").last()
    ret3 = month_end / month_end.shift(3) - 1.0
    ret6 = month_end / month_end.shift(6) - 1.0
    ret12 = month_end / month_end.shift(12) - 1.0
    sma10m = month_end.rolling(10, min_periods=10).mean()

    monthly_lev = pd.Series(0.0, index=month_end.index)
    monthly_lev.loc[(month_end > sma10m) & (ret12 > 0.0)] = 1.0
    monthly_lev.loc[(month_end > sma10m) & (ret6 > 0.0) & (ret12 > 0.0)] = 2.0
    monthly_lev.loc[(month_end > sma10m) & (ret3 > 0.0) & (ret6 > 0.0) & (ret12 > 0.0)] = 3.0

    daily = monthly_lev.reindex(prices.index, method="ffill").fillna(0.0)
    return daily


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
    group: str,
    lev: pd.Series,
    description: str,
    etp_returns: pd.DataFrame | None,
) -> None:
    result = engine.run(prices, lev, name=strategy, etp_returns=etp_returns)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    rows.append(
        {
            "strategy": strategy,
            "group": group,
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
    )
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
    prices = load_ohlc_data(years=30)
    engine = make_engine()
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    rows: list[dict] = []
    equity_curves: dict[str, pd.Series] = {}

    strategies: list[tuple[str, pd.Series, str]] = [
        ("Long-hold 3/6/12m momentum", long_hold_time_series_momentum(prices), "Enter 1x/2x/3x using 12m/6m/3m absolute momentum; exit high leverage slowly using 6m and 12m momentum."),
        ("SMA stack hysteresis", sma_stack_hysteresis(prices), "Enter 3x on SMA20 > SMA50 > SMA200; stay leveraged until slower SMA100/SMA50 exits trigger."),
        ("Absolute momentum trailing stop", absolute_momentum_trailing_stop(prices), "Enter leverage on 6m/12m absolute momentum; stay until a 3-month low or SMA100 trailing stop breaks."),
        ("ADX trend strength", adx_trend_strength(prices), "Use true ADX/+DI/-DI from daily high/low/close; add leverage only in strong upward trends and exit on ADX or SMA weakness."),
        ("Keltner trend channel", keltner_trend_channel(prices), "Use EMA50/EMA100 and ATR channel: 3x above upper Keltner channel; stay until EMA50/EMA100 breaks."),
        ("Monthly momentum regime", monthly_momentum_regime(prices), "Month-end 3/6/12m momentum and 10-month SMA regime, rebalanced monthly to reduce churn."),
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
            etp_panel,
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
            etp_panel,
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
        etp_panel,
    )

    for name, lev, description in strategies:
        add_row(rows, equity_curves, prices, engine, name, "Long-hold momentum", lev, description, etp_panel)

    results = pd.DataFrame(rows).sort_values(["group", "cagr"], ascending=[True, False])
    results_path = OUTPUT_DIR / "long_hold_momentum_results.csv"
    results.to_csv(results_path, index=False)

    keep_for_chart = [
        "Long-hold 3/6/12m momentum",
        "SMA stack hysteresis",
        "Absolute momentum trailing stop",
        "ADX trend strength",
        "Keltner trend channel",
        "Monthly momentum regime",
        "Guarded A10/B20 SMA20",
        "SMA20 3x/cash",
        "Buy & hold 1x",
    ]
    chart_data = {
        "start_date": str(prices.index[0].date()),
        "end_date": str(prices.index[-1].date()),
        "annual_equity": annual_equity(equity_curves, keep_for_chart),
    }
    chart_path = OUTPUT_DIR / "long_hold_momentum_chart_data.json"
    chart_path.write_text(json.dumps(chart_data, indent=2), encoding="utf-8")

    disp = results.copy()
    for col in ["cagr", "ann_volatility", "max_drawdown", "pct_days_cash", "pct_days_1x", "pct_days_2x", "pct_days_3x"]:
        disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%" if col in {"cagr", "ann_volatility", "max_drawdown"} else f"{x:.2f}%")
    disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.2f}")
    print(f"Long-hold momentum backtests: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print(disp[["strategy", "group", "cagr", "ann_volatility", "sharpe", "max_drawdown", "end_$", "rebalances", "pct_days_3x"]].to_string(index=False))
    print(f"\nCSV: {results_path}")
    print(f"Chart data: {chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
