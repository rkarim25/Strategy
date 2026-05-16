"""Portfolio simulation: leverage, funding, trading costs, hard drawdown cap."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
FUNDING_SPREAD = 0.006
INITIAL_CAPITAL = 100.0
ANNUAL_CASH_INFLOW_PCT = 0.10
DEFAULT_MAX_DRAWDOWN = 0.20
# 1% of traded notional from mid on each leverage rebalance
TRADING_COST_FROM_MID_PCT = 0.01
# ~1 trading week (Mon–Fri)
DEFAULT_DD_PAUSE_TRADING_DAYS = 5


def funding_cost_daily(leverage: float, tbill_rate: float) -> float:
    if leverage <= 1.0:
        return 0.0
    return ((leverage - 1.0) * (tbill_rate + FUNDING_SPREAD)) / TRADING_DAYS


def levered_return(
    spx_return: float,
    leverage: float,
    tbill_rate: float,
) -> float:
    if leverage <= 0.0:
        return tbill_rate / TRADING_DAYS
    gross = leverage * spx_return
    funding = funding_cost_daily(leverage, tbill_rate)
    return gross - funding


def trading_cost(notional_traded: float) -> float:
    return notional_traded * TRADING_COST_FROM_MID_PCT


@dataclass
class BacktestResult:
    equity: pd.Series
    daily_returns: pd.Series
    leverage: pd.Series
    risk_off_days: int = 0
    trading_costs_total: float = 0.0
    funding_costs_total: float = 0.0
    turnover_notional: float = 0.0
    rebalance_count: int = 0


class PortfolioEngine:
    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        annual_inflow_pct: float = ANNUAL_CASH_INFLOW_PCT,
        annual_inflow_abs: float | None = None,
        max_drawdown_limit: float | None = DEFAULT_MAX_DRAWDOWN,
        hard_drawdown_floor: bool = True,
        trading_cost_pct: float = TRADING_COST_FROM_MID_PCT,
        dd_pause_trigger: float | None = None,
        dd_pause_trading_days: int = DEFAULT_DD_PAUSE_TRADING_DAYS,
        dd_pause_reset_peak_on_reentry: bool = True,
    ) -> None:
        self.initial_capital = initial_capital
        self.annual_inflow_pct = annual_inflow_pct
        self.annual_inflow_abs = annual_inflow_abs
        self.max_drawdown_limit = max_drawdown_limit
        self.hard_drawdown_floor = hard_drawdown_floor
        self.trading_cost_pct = trading_cost_pct
        self.dd_pause_trigger = dd_pause_trigger
        self.dd_pause_trading_days = dd_pause_trading_days
        self.dd_pause_reset_peak_on_reentry = dd_pause_reset_peak_on_reentry

    def run(
        self,
        prices: pd.DataFrame,
        leverage: pd.Series | float,
        name: str = "strategy",
    ) -> BacktestResult:
        df = prices.copy()
        spx_ret = df["spx_close"].pct_change()
        tbill = df["tbill_rate"]

        if isinstance(leverage, (int, float)):
            lev_series = pd.Series(float(leverage), index=df.index)
        else:
            lev_series = leverage.reindex(df.index).ffill().fillna(1.0)

        equity, port_ret, applied, risk_off_days, tc, fc, turnover, rebal = self._simulate(
            df.index, spx_ret, tbill, lev_series
        )
        equity.name = name
        return BacktestResult(
            equity=equity,
            daily_returns=port_ret,
            leverage=applied,
            risk_off_days=risk_off_days,
            trading_costs_total=tc,
            funding_costs_total=fc,
            turnover_notional=turnover,
            rebalance_count=rebal,
        )

    def _simulate(
        self,
        index: pd.DatetimeIndex,
        spx_ret: pd.Series,
        tbill: pd.Series,
        target_leverage: pd.Series,
    ) -> tuple[pd.Series, pd.Series, pd.Series, int, float, float, float, int]:
        equity = pd.Series(index=index, dtype=float)
        port_ret = pd.Series(0.0, index=index)
        applied = pd.Series(1.0, index=index)

        aum = self.initial_capital
        peak = aum
        prev_lev = 1.0
        prev_year: int | None = None
        risk_off = False
        risk_off_days = 0
        trading_costs_total = 0.0
        funding_costs_total = 0.0
        turnover_notional = 0.0
        rebalance_count = 0
        limit = self.max_drawdown_limit
        use_dd_pause = self.dd_pause_trigger is not None
        pause_remaining = 0
        pause_trigger = float(self.dd_pause_trigger) if use_dd_pause else 0.0
        pause_len = int(self.dd_pause_trading_days)
        reset_peak_next_bar = False

        for i, dt in enumerate(index):
            if prev_year is not None and dt.year != prev_year:
                if self.annual_inflow_abs is not None:
                    aum += float(self.annual_inflow_abs)
                else:
                    aum *= 1.0 + self.annual_inflow_pct
                peak = max(peak, aum)

            if (
                use_dd_pause
                and self.dd_pause_reset_peak_on_reentry
                and reset_peak_next_bar
            ):
                peak = aum
                reset_peak_next_bar = False

            lev = float(target_leverage.iloc[i])

            if use_dd_pause and i > 0:
                dd = (aum - peak) / peak if peak > 0 else 0.0
                if pause_remaining > 0:
                    lev = 0.0
                elif dd <= -pause_trigger:
                    pause_remaining = pause_len
                    lev = 0.0
            elif limit is not None and i > 0:
                dd = (aum - peak) / peak if peak > 0 else 0.0
                trigger = -limit * 0.85
                release = -limit * 0.15
                if dd <= trigger:
                    risk_off = True
                elif risk_off and (dd > release or aum >= peak * (1.0 - limit * 0.5)):
                    risk_off = False
                if risk_off:
                    lev = 0.0

            if abs(lev - prev_lev) > 1e-9:
                traded = abs(lev - prev_lev) * aum
                cost = traded * self.trading_cost_pct
                aum -= cost
                trading_costs_total += cost
                turnover_notional += traded
                rebalance_count += 1
                prev_lev = lev

            if i > 0 and not pd.isna(spx_ret.iloc[i]):
                tb = float(tbill.iloc[i]) if not pd.isna(tbill.iloc[i]) else 0.0
                if lev > 1.0:
                    daily_funding = funding_cost_daily(lev, tb)
                    funding_costs_total += aum * daily_funding
                r = levered_return(float(spx_ret.iloc[i]), lev, tb)
                aum *= 1.0 + r
                port_ret.iloc[i] = r

            peak = max(peak, aum)

            if not use_dd_pause and limit is not None and self.hard_drawdown_floor and peak > 0:
                floor = peak * (1.0 - limit)
                if aum < floor:
                    aum = floor
                    risk_off = True
                    lev = 0.0
                    prev_lev = 0.0

            if not use_dd_pause and limit is not None and i > 0:
                dd_after = (aum - peak) / peak if peak > 0 else 0.0
                if dd_after <= -limit:
                    risk_off = True
                    lev = 0.0
                    prev_lev = 0.0

            equity.iloc[i] = aum
            applied.iloc[i] = lev
            if use_dd_pause:
                if pause_remaining > 0:
                    risk_off_days += 1
                    if (
                        self.dd_pause_reset_peak_on_reentry
                        and pause_remaining == 1
                    ):
                        reset_peak_next_bar = True
                    pause_remaining -= 1
            elif risk_off:
                risk_off_days += 1
            prev_year = dt.year

        return (
            equity,
            port_ret,
            applied,
            risk_off_days,
            trading_costs_total,
            funding_costs_total,
            turnover_notional,
            rebalance_count,
        )


def passes_drawdown_limit(equity: pd.Series, limit: float = DEFAULT_MAX_DRAWDOWN) -> bool:
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min()) >= -limit - 1e-9
