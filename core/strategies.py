"""Systematic leverage strategies with documented entry / exit rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from core.indicators import enrich_prices, macd


@dataclass(frozen=True)
class StrategySpec:
    name: str
    target_leverage: float
    description: str
    buy_condition: str
    sell_condition: str
    buy_levels: str
    sell_levels: str


class LeverageStrategy(ABC):
    spec: StrategySpec

    @abstractmethod
    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        pass

    def rule_summary(self) -> dict[str, str]:
        s = self.spec
        return {
            "strategy": s.name,
            "target_leverage": str(s.target_leverage),
            "overview": s.description,
            "buy_condition": s.buy_condition,
            "sell_condition": s.sell_condition,
            "buy_levels": s.buy_levels,
            "sell_levels": s.sell_levels,
        }


def _run_state_machine(
    index: pd.DatetimeIndex,
    entry: pd.Series,
    exit_: pd.Series,
    levered_level: float,
    warmup: int = 0,
) -> pd.Series:
    lev = pd.Series(1.0, index=index)
    active = False
    for i in range(len(index)):
        if i < warmup:
            continue
        if not active and bool(entry.iloc[i]):
            active = True
        elif active and bool(exit_.iloc[i]):
            active = False
        lev.iloc[i] = levered_level if active else 1.0
    return lev


class Sma200TrendStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="SMA200 Trend 3x",
        target_leverage=3.0,
        description="Trend-following: scale to 3x in bull regime above long-term average.",
        buy_condition="SPX close crosses above / holds above 200-day SMA (signal day).",
        sell_condition="SPX close falls below 200-day SMA.",
        buy_levels="Leverage 3x when Close > SMA(200). Base state 1x.",
        sell_levels="Unwind to 1x when Close < SMA(200).",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        entry = df["spx_close"] > df["sma_200"]
        exit_ = df["spx_close"] < df["sma_200"]
        return _run_state_machine(df.index, entry, exit_, 3.0, warmup=200)


class GoldenCrossStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="Golden Cross 3x",
        target_leverage=3.0,
        description="Medium-term trend shift: 50-day MA crossing above 200-day MA.",
        buy_condition="SMA(50) crosses above SMA(200) on daily close.",
        sell_condition="SMA(50) crosses below SMA(200) (death cross).",
        buy_levels="Leverage 3x on golden cross event.",
        sell_levels="Unwind to 1x on death cross event.",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        cross_up = (df["sma_50"] > df["sma_200"]) & (
            df["sma_50"].shift(1) <= df["sma_200"].shift(1)
        )
        cross_dn = (df["sma_50"] < df["sma_200"]) & (
            df["sma_50"].shift(1) >= df["sma_200"].shift(1)
        )
        return _run_state_machine(
            df.index, cross_up.fillna(False), cross_dn.fillna(False), 3.0, warmup=200
        )


@dataclass(frozen=True)
class MacdParams:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    hist_entry_pct: float = 0.0  # min histogram as % of SPX price for entry (0=off)
    confirm_days: int = 1
    require_above_sma200: bool = False
    exit_below_sma200: bool = False
    levered_level: float = 3.0


class TunableMacdStrategy(LeverageStrategy):
    """MACD crossover with optional histogram threshold, confirmation, SMA filter."""

    def __init__(self, params: MacdParams | None = None, name_suffix: str = "") -> None:
        self.params = params or MacdParams()
        p = self.params
        suffix = f" ({name_suffix})" if name_suffix else ""
        filt = []
        if p.require_above_sma200:
            filt.append("above SMA200 to enter")
        if p.exit_below_sma200:
            filt.append("exit if below SMA200")
        if p.hist_entry_pct > 0:
            filt.append(f"hist >= {p.hist_entry_pct:.2f}% of price")
        if p.confirm_days > 1:
            filt.append(f"{p.confirm_days}d confirmation")
        filt_txt = "; ".join(filt) if filt else "standard cross only"

        self.spec = StrategySpec(
            name=f"MACD {p.fast}/{p.slow}/{p.signal} {p.levered_level:.0f}x{suffix}".strip(),
            target_leverage=p.levered_level,
            description=f"Tunable MACD: {filt_txt}.",
            buy_condition=(
                f"MACD({p.fast},{p.slow}) bull cross Signal({p.signal})"
                + (f" + hist >= {p.hist_entry_pct}% of price" if p.hist_entry_pct else "")
                + (" + Close > SMA200" if p.require_above_sma200 else "")
                + (f" + {p.confirm_days}d confirm" if p.confirm_days > 1 else "")
            ),
            sell_condition=(
                f"MACD bear cross"
                + (" OR Close < SMA200" if p.exit_below_sma200 else "")
            ),
            buy_levels=f"Leverage {p.levered_level}x on confirmed bull signal.",
            sell_levels="Unwind to 1x on bear cross or trend filter breach.",
        )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        p = self.params
        close = prices["spx_close"]
        line, sig, hist = macd(close, p.fast, p.slow, p.signal)
        sma200 = close.rolling(200, min_periods=200).mean()

        bull_cross = (line > sig) & (line.shift(1) <= sig.shift(1))
        bear_cross = (line < sig) & (line.shift(1) >= sig.shift(1))

        if p.confirm_days > 1:
            above = (line > sig).astype(int).rolling(p.confirm_days).min() == 1
            bull_cross = bull_cross & above

        if p.hist_entry_pct > 0:
            hist_thresh = close * (p.hist_entry_pct / 100.0)
            bull_cross = bull_cross & (hist >= hist_thresh)

        if p.require_above_sma200:
            bull_cross = bull_cross & (close > sma200)

        exit_sig = bear_cross.copy()
        if p.exit_below_sma200:
            exit_sig = exit_sig | (close < sma200)

        warmup = max(p.slow + p.signal, 200 if p.require_above_sma200 or p.exit_below_sma200 else 0)
        return _run_state_machine(
            prices.index,
            bull_cross.fillna(False),
            exit_sig.fillna(False),
            p.levered_level,
            warmup=warmup,
        )


class MacdMomentumStrategy(TunableMacdStrategy):
    """Default 12/26/9 MACD."""

    def __init__(self) -> None:
        super().__init__(MacdParams(), name_suffix="")
        self.spec = StrategySpec(
            name="MACD Momentum 3x",
            target_leverage=3.0,
            description="MACD line crossing signal line indicates momentum shift.",
            buy_condition="MACD(12,26) crosses above Signal(9).",
            sell_condition="MACD crosses below Signal.",
            buy_levels="Leverage 3x on bullish MACD crossover.",
            sell_levels="Unwind to 1x on bearish MACD crossover.",
        )


class RsiMomentumStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="RSI Momentum 3x",
        target_leverage=3.0,
        description="RSI crossing midline signals improving momentum.",
        buy_condition="RSI(14) crosses up through 50.",
        sell_condition="RSI > 70 (overbought) OR RSI < 45 (momentum failure).",
        buy_levels="Leverage 3x when RSI crosses above 50.",
        sell_levels="Unwind to 1x when RSI > 70 or RSI < 45.",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        cross_50 = (df["rsi_14"] > 50) & (df["rsi_14"].shift(1) <= 50)
        exit_sig = (df["rsi_14"] > 70) | (df["rsi_14"] < 45)
        return _run_state_machine(
            df.index, cross_50.fillna(False), exit_sig.fillna(False), 3.0, warmup=20
        )


class RsiOversoldBounceStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="RSI Oversold 2x",
        target_leverage=2.0,
        description="Mean-reversion bounce after oversold RSI.",
        buy_condition="RSI(14) crosses up through 30 from below.",
        sell_condition="RSI > 55 (normalization complete).",
        buy_levels="Leverage 2x on RSI cross above 30.",
        sell_levels="Unwind to 1x when RSI > 55.",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        entry = (df["rsi_14"] > 30) & (df["rsi_14"].shift(1) <= 30)
        exit_ = df["rsi_14"] > 55
        return _run_state_machine(df.index, entry.fillna(False), exit_.fillna(False), 2.0, warmup=20)


class DrawdownRecoveryStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="DD Recovery 3x",
        target_leverage=3.0,
        description="Buy recovery after deep index drawdown with short-term confirmation.",
        buy_condition="SPX drawdown from peak < -10% AND 5-day return > 0.",
        sell_condition="SPX drawdown from peak worsens below -8% while in trade.",
        buy_levels="Leverage 3x when DD < -10% and 5d momentum turns positive.",
        sell_levels="Unwind to 1x when DD < -8% (stop / failed recovery).",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        ret5 = df["spx_close"].pct_change(5)
        entry = (df["spx_dd"] < -0.10) & (ret5 > 0)
        exit_ = df["spx_dd"] < -0.08
        return _run_state_machine(df.index, entry.fillna(False), exit_.fillna(False), 3.0, warmup=10)


class DualFilterStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="SMA200 + RSI 3x",
        target_leverage=3.0,
        description="Dual confirmation: long-term trend plus momentum.",
        buy_condition="Close > SMA(200) AND RSI(14) > 50 simultaneously.",
        sell_condition="Close < SMA(200) OR RSI(14) < 50.",
        buy_levels="Leverage 3x when both trend and RSI filters are true.",
        sell_levels="Unwind to 1x if either filter fails.",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        entry = (df["spx_close"] > df["sma_200"]) & (df["rsi_14"] > 50)
        exit_ = (df["spx_close"] < df["sma_200"]) | (df["rsi_14"] < 50)
        return _run_state_machine(df.index, entry, exit_, 3.0, warmup=200)


class MacdWithTrendFilterStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="MACD + SMA200 3x",
        target_leverage=3.0,
        description="MACD entries only permitted in long-term uptrend.",
        buy_condition="MACD bull cross AND Close > SMA(200).",
        sell_condition="MACD bear cross OR Close < SMA(200).",
        buy_levels="Leverage 3x on MACD cross while above SMA(200).",
        sell_levels="Unwind to 1x on MACD bear cross or loss of SMA(200) support.",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        bull = (df["macd"] > df["macd_signal"]) & (
            df["macd"].shift(1) <= df["macd_signal"].shift(1)
        )
        bear = (df["macd"] < df["macd_signal"]) & (
            df["macd"].shift(1) >= df["macd_signal"].shift(1)
        )
        above = df["spx_close"] > df["sma_200"]
        return _run_state_machine(
            df.index,
            (bull & above).fillna(False),
            (bear | (~above)).fillna(False),
            3.0,
            warmup=200,
        )


class BollingerReversionStrategy(LeverageStrategy):
    spec = StrategySpec(
        name="BB Mean Reversion 2x",
        target_leverage=2.0,
        description="Short-term mean reversion from lower Bollinger band.",
        buy_condition="Close < Lower Bollinger Band (20, 2σ).",
        sell_condition="Close >= Middle Bollinger Band (20-day SMA).",
        buy_levels="Leverage 2x when price pierces lower band.",
        sell_levels="Unwind to 1x at middle band (fair value).",
    )

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        entry = df["spx_close"] < df["bb_lower"]
        exit_ = df["spx_close"] >= df["bb_mid"]
        return _run_state_machine(df.index, entry.fillna(False), exit_.fillna(False), 2.0, warmup=25)


BENCHMARK_RULES = {
    "strategy": "Buy & Hold 1x SPX",
    "target_leverage": "1.0",
    "overview": "Passive benchmark: fully invested in S&P 500 at 1x with no tactical leverage.",
    "buy_condition": "Fully invested from first valid day; no tactical entry signal.",
    "sell_condition": "Never tactical exit; remains 1x long SPX throughout.",
    "buy_levels": "Leverage 1x (100% notional to SPX) at all times.",
    "sell_levels": "No systematic sell; hold continuous 1x exposure.",
}


class DrawdownScalingStrategy(LeverageStrategy):
    """
    Scale leverage up as SPX drawdown from peak deepens; exit on SPX recovery
    from entry price (not portfolio return).
    """

    spec = StrategySpec(
        name="DD Scale 2x/3x",
        target_leverage=3.0,
        description=(
            "Buy-the-dip leverage ladder on SPX drawdown from peak; "
            "exit on index recovery from entry."
        ),
        buy_condition=(
            "Enter 2x when SPX drawdown from peak reaches -20%. "
            "Enter or upgrade to 3x when drawdown reaches -50%."
        ),
        sell_condition=(
            "From 2x: return to 1x after SPX rises +50% from entry price. "
            "From 3x: return to 1x after SPX rises +100% from entry price."
        ),
        buy_levels="2x at SPX DD <= -20%; 3x at SPX DD <= -50% (escalate from 2x).",
        sell_levels="1x after +50% SPX from 2x entry; 1x after +100% SPX from 3x entry.",
    )

    DD_2X = -0.20
    DD_3X = -0.50
    EXIT_2X_RETURN = 0.50
    EXIT_3X_RETURN = 1.00

    def generate_leverage(self, prices: pd.DataFrame) -> pd.Series:
        df = enrich_prices(prices)
        close = df["spx_close"]
        dd = df["spx_dd"]
        lev = pd.Series(1.0, index=df.index)

        state = 1.0
        entry_price = float("nan")

        for i in range(len(df)):
            c = float(close.iloc[i])
            d = dd.iloc[i]

            if pd.isna(d):
                lev.iloc[i] = state
                continue

            if state == 1.0:
                if d <= self.DD_3X:
                    state = 3.0
                    entry_price = c
                elif d <= self.DD_2X:
                    state = 2.0
                    entry_price = c
            elif state == 2.0:
                gain = c / entry_price - 1.0
                if gain >= self.EXIT_2X_RETURN:
                    state = 1.0
                    entry_price = float("nan")
                elif d <= self.DD_3X:
                    state = 3.0
                    entry_price = c
            elif state == 3.0:
                gain = c / entry_price - 1.0
                if gain >= self.EXIT_3X_RETURN:
                    state = 1.0
                    entry_price = float("nan")

            lev.iloc[i] = state

        return lev


def all_strategies() -> list[LeverageStrategy]:
    return [
        Sma200TrendStrategy(),
        GoldenCrossStrategy(),
        MacdMomentumStrategy(),
        RsiMomentumStrategy(),
        RsiOversoldBounceStrategy(),
        DrawdownRecoveryStrategy(),
        DualFilterStrategy(),
        MacdWithTrendFilterStrategy(),
        BollingerReversionStrategy(),
    ]
