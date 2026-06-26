"""Portfolio simulation: leverage, funding, trading costs, hard drawdown cap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from core.etp_leverage import EtpBundle

TRADING_DAYS = 252
FUNDING_SPREAD = 0.006
VIX_SPREAD_BASE = 0.006
VIX_STRESS_THRESHOLD = 15.0
VIX_SPREAD_BPS_PER_10 = 0.003
VIX_SPREAD_CAP = 0.026
VIX_3X_SPREAD_BUMP = 0.002
INITIAL_CAPITAL = 100.0
ANNUAL_CASH_INFLOW_PCT = 0.10
DEFAULT_MAX_DRAWDOWN = 0.20
# 0.10% of traded notional from mid on each leverage rebalance. Realistic-to-conservative
# for liquid ETPs (real half-spreads on SPY/SSO/UPRO are ~0.01-0.05%); the prior 0.01 (1%)
# was ~20-50x reality and silently destroyed high-turnover strategies (~28 trades/yr) over
# long windows — it only looked survivable when paired with calendar-inflated UCITS returns.
TRADING_COST_FROM_MID_PCT = 0.001
# ~1 trading week (Mon–Fri)
DEFAULT_DD_PAUSE_TRADING_DAYS = 5


def vix_linked_spread_annual(vix: float, leverage: float) -> float:
    """Annual borrow spread: 0.6% base + VIX stress above 15 (+30bp/10pts, cap ~2.6%), +20bp at 3x."""
    spread = VIX_SPREAD_BASE + max(
        0.0, (float(vix) - VIX_STRESS_THRESHOLD) / 10.0 * VIX_SPREAD_BPS_PER_10
    )
    if leverage >= 2.5:
        spread += VIX_3X_SPREAD_BUMP
    return min(spread, VIX_SPREAD_CAP)


def funding_cost_daily(
    leverage: float,
    tbill_rate: float,
    vix: float | None = None,
) -> float:
    if leverage <= 1.0:
        return 0.0
    spread = (
        vix_linked_spread_annual(vix, leverage)
        if vix is not None
        else FUNDING_SPREAD
    )
    return ((leverage - 1.0) * (tbill_rate + spread)) / TRADING_DAYS


def levered_return(
    spx_return: float,
    leverage: float,
    tbill_rate: float,
    vix: float | None = None,
) -> float:
    if leverage <= 0.0:
        return tbill_rate / TRADING_DAYS
    gross = leverage * spx_return
    funding = funding_cost_daily(leverage, tbill_rate, vix=vix)
    return gross - funding


def block_bootstrap_paths(
    prices: pd.DataFrame,
    *,
    n_sims: int,
    horizon_days: int,
    block_days: int,
    seed: int,
    start_date: str = "2000-01-03",
) -> list[pd.DataFrame]:
    """Block-bootstrap index returns (and VIX when present) for Monte Carlo paths."""
    rng = np.random.default_rng(seed)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    vix_arr = None
    if "vix" in prices.columns:
        vix_arr = prices["vix"].ffill().fillna(VIX_STRESS_THRESHOLD).to_numpy(dtype=float)

    block_starts = np.arange(1, len(prices) - block_days + 1)
    if len(block_starts) == 0:
        raise ValueError("prices too short for block bootstrap")

    paths: list[pd.DataFrame] = []
    for _ in range(n_sims):
        chunks: list[np.ndarray] = []
        while sum(len(x) for x in chunks) < horizon_days:
            start = int(rng.choice(block_starts))
            chunks.append(np.arange(start, start + block_days))
        idx = np.concatenate(chunks)[:horizon_days]
        index = pd.bdate_range(start_date, periods=horizon_days)
        data: dict[str, np.ndarray | pd.Series] = {
            "spx_close": 1000.0 * np.cumprod(1.0 + spx_ret[idx]),
            "tbill_rate": tbill[idx],
        }
        if vix_arr is not None:
            data["vix"] = vix_arr[idx]
        paths.append(pd.DataFrame(data, index=index))
    return paths


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
    etp_mode: bool = False
    etp_coverage: dict[str, float] | None = None


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
        signal_delay_days: int = 1,
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
        # A close-based signal cannot be acted on until the NEXT session: the
        # leverage decided from close[i] earns return[i+1] onward, not return[i].
        # signal_delay_days=1 enforces this (no look-ahead). Use 0 only to
        # reproduce the legacy same-bar convention for comparison.
        self.signal_delay_days = signal_delay_days

    def run(
        self,
        prices: pd.DataFrame,
        leverage: pd.Series | float,
        name: str = "strategy",
        *,
        etp_returns: pd.DataFrame | None = None,
        etp_bundle: "EtpBundle | None" = None,
    ) -> BacktestResult:
        df = prices.copy()
        spx_ret = df["spx_close"].pct_change()
        tbill = df["tbill_rate"]

        if isinstance(leverage, (int, float)):
            lev_series = pd.Series(float(leverage), index=df.index)
        else:
            lev_series = leverage.reindex(df.index).ffill().fillna(1.0)

        # Honest execution: hold cash until the first actionable (lagged) signal.
        if self.signal_delay_days > 0:
            lev_series = lev_series.shift(self.signal_delay_days).fillna(0.0)

        etp_panel = etp_returns
        etp_cov: dict[str, float] | None = None
        if etp_panel is None and etp_bundle is not None:
            from core.etp_leverage import build_etp_return_panel, etp_coverage_summary

            etp_panel = build_etp_return_panel(df, etp_bundle)
            etp_cov = etp_coverage_summary(etp_panel)
        elif etp_panel is not None:
            from core.etp_leverage import etp_coverage_summary

            etp_cov = etp_coverage_summary(etp_panel)

        equity, port_ret, applied, risk_off_days, tc, fc, turnover, rebal = self._simulate(
            df.index, spx_ret, tbill, lev_series, etp_panel, df.get("vix")
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
            etp_mode=etp_panel is not None,
            etp_coverage=etp_cov,
        )

    def _simulate(
        self,
        index: pd.DatetimeIndex,
        spx_ret: pd.Series,
        tbill: pd.Series,
        target_leverage: pd.Series,
        etp_returns: pd.DataFrame | None = None,
        vix: pd.Series | None = None,
    ) -> tuple[pd.Series, pd.Series, pd.Series, int, float, float, float, int]:
        from core.etp_leverage import daily_return_for_leverage

        use_etp = etp_returns is not None
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
                idx_r = float(spx_ret.iloc[i])
                vix_val = None
                if vix is not None:
                    raw_vix = vix.iloc[i]
                    if not pd.isna(raw_vix):
                        vix_val = float(raw_vix)
                if use_etp:
                    row = etp_returns.iloc[i]
                    r = daily_return_for_leverage(lev, idx_r, tb, row)
                else:
                    if lev > 1.0:
                        daily_funding = funding_cost_daily(lev, tb, vix=vix_val)
                        funding_costs_total += aum * daily_funding
                    r = levered_return(idx_r, lev, tb, vix=vix_val)
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
