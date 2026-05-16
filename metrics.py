"""Institutional-style portfolio analytics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine import TRADING_DAYS


def _drawdown_series(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return (equity - peak) / peak


def _max_drawdown_duration(drawdown: pd.Series) -> int:
    underwater = drawdown < 0
    if not underwater.any():
        return 0
    groups = (~underwater).cumsum()
    durations = underwater.groupby(groups).sum()
    return int(durations.max())


def invested_vs_tbills_sessions(leverage: pd.Series) -> dict[str, float]:
    """Share of sessions with risky exposure (lev > 0) vs T-bill cash (lev <= 0)."""
    lev = leverage.astype(float).fillna(0.0)
    n = len(lev)
    if n == 0:
        return {"pct_sessions_invested": float("nan"), "pct_sessions_tbills": float("nan")}
    invested = float((lev > 0).sum())
    tbills = float((lev <= 0).sum())
    return {
        "pct_sessions_invested": 100.0 * invested / n,
        "pct_sessions_tbills": 100.0 * tbills / n,
    }


def comprehensive_stats(
    equity: pd.Series,
    daily_returns: pd.Series,
    benchmark_equity: pd.Series | None = None,
    risk_free: float = 0.0,
    trading_costs_total: float = 0.0,
    turnover_notional: float = 0.0,
) -> dict[str, float]:
    eq = equity.dropna()
    if len(eq) < 2:
        return {}

    ret = daily_returns.reindex(eq.index).fillna(0.0)
    bench_ret = None
    if benchmark_equity is not None:
        bench_ret = benchmark_equity.reindex(eq.index).pct_change().fillna(0.0)

    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total_return = eq.iloc[-1] / eq.iloc[0] - 1.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0

    dd = _drawdown_series(eq)
    max_dd = float(dd.min())
    avg_dd = float(dd[dd < 0].mean()) if (dd < 0).any() else 0.0
    ulcer = float(np.sqrt((dd**2).mean()))

    vol = float(ret.std() * np.sqrt(TRADING_DAYS))
    downside = ret[ret < 0]
    downside_vol = float(downside.std() * np.sqrt(TRADING_DAYS)) if len(downside) else np.nan

    rf_daily = risk_free / TRADING_DAYS
    excess = ret - rf_daily
    sharpe = (
        float(np.sqrt(TRADING_DAYS) * excess.mean() / excess.std())
        if excess.std() > 0
        else np.nan
    )
    sortino = (
        float(np.sqrt(TRADING_DAYS) * excess.mean() / downside.std())
        if len(downside) and downside.std() > 0
        else np.nan
    )
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan

    wins = ret[ret > 0]
    losses = ret[ret < 0]
    win_rate = float(len(wins) / len(ret[ret != 0])) if len(ret[ret != 0]) else np.nan
    profit_factor = (
        float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan
    )
    expectancy = float(ret.mean() * TRADING_DAYS)

    monthly = eq.resample("ME").last().pct_change().dropna()
    best_month = float(monthly.max()) if len(monthly) else np.nan
    worst_month = float(monthly.min()) if len(monthly) else np.nan

    beta = alpha = info_ratio = tracking_error = np.nan
    if bench_ret is not None and bench_ret.std() > 0:
        cov = np.cov(ret, bench_ret)[0, 1]
        var_b = bench_ret.var()
        beta = float(cov / var_b) if var_b > 0 else np.nan
        alpha = float(cagr - (risk_free + beta * (bench_ret.mean() * TRADING_DAYS - risk_free)))
        active = ret - bench_ret
        tracking_error = float(active.std() * np.sqrt(TRADING_DAYS))
        info_ratio = (
            float(active.mean() * TRADING_DAYS / tracking_error)
            if tracking_error > 0
            else np.nan
        )

    skew = float(ret.skew())
    kurt = float(ret.kurtosis())

    return {
        "cagr": float(cagr),
        "total_return": float(total_return),
        "max_drawdown": max_dd,
        "avg_drawdown": avg_dd,
        "ulcer_index": ulcer,
        "max_dd_duration_days": float(_max_drawdown_duration(dd)),
        "volatility": vol,
        "downside_volatility": downside_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy_ann": expectancy,
        "best_day": float(ret.max()),
        "worst_day": float(ret.min()),
        "best_month": best_month,
        "worst_month": worst_month,
        "beta": beta,
        "alpha": alpha,
        "information_ratio": info_ratio,
        "tracking_error": tracking_error,
        "skewness": skew,
        "excess_kurtosis": kurt,
        "final_value": float(eq.iloc[-1]),
        "total_trading_costs": float(trading_costs_total),
        "turnover_notional": float(turnover_notional),
        "cost_drag_pct": float(trading_costs_total / eq.iloc[0]) if eq.iloc[0] else np.nan,
    }
