"""
(a) Tiered leverage: 0 / 1x / 2x / 3x from stacked trend signals (SMA + optional RSI/MACD).

(b) Joint optimization over a parameter grid:
    - maximize Sharpe
    - maximize Calmar
    - maximize CAGR subject to max drawdown <= 15% (no hard engine floor; filter on realized DD)
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from indicators import enrich_prices, rsi, sma
from metrics import comprehensive_stats
from reporting import BENCHMARK_LABEL

OUTPUT_DIR = Path("output") / "tiered_optim"
DD_CAP = 0.15


def lever_sma_stair(
    close: pd.Series,
    f: int,
    m: int,
    s: int,
    exclusive: bool,
) -> pd.Series:
    sf = sma(close, f)
    sm = sma(close, m)
    ss = sma(close, s)
    if exclusive:
        lev = np.select(
            [
                close <= sf,
                (close > sf) & (close <= sm),
                (close > sm) & (close <= ss),
                close > ss,
            ],
            [0.0, 1.0, 2.0, 3.0],
            default=0.0,
        )
        return pd.Series(lev, index=close.index)
    lev = pd.Series(0.0, index=close.index)
    lev.loc[close > sf] = 1.0
    lev.loc[close > sm] = 2.0
    lev.loc[close > ss] = 3.0
    return lev


def lever_sma_stair_rsi_cap(
    close: pd.Series,
    f: int,
    m: int,
    s: int,
    exclusive: bool,
    rsi_hi: float,
    rperiod: int,
) -> pd.Series:
    base = lever_sma_stair(close, f, m, s, exclusive)
    r = rsi(close, rperiod)
    out = base.copy()
    out.loc[(base >= 3.0) & (r <= rsi_hi)] = 2.0
    return out


def lever_sma_stair_macd_3x(
    close: pd.Series,
    macd_line: pd.Series,
    macd_sig: pd.Series,
    f: int,
    m: int,
    s: int,
    exclusive: bool,
) -> pd.Series:
    base = lever_sma_stair(close, f, m, s, exclusive)
    bull = macd_line > macd_sig
    out = base.copy()
    out.loc[(base >= 3.0) & (~bull)] = 2.0
    return out


def lever_rsi_stair(close: pd.Series, sf: pd.Series, t1: float, t2: float) -> pd.Series:
    r = rsi(close, 14)
    lev = pd.Series(0.0, index=close.index)
    above = close > sf
    lev.loc[above & (r <= t1)] = 1.0
    lev.loc[above & (r > t1) & (r <= t2)] = 2.0
    lev.loc[above & (r > t2)] = 3.0
    return lev


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    close = prices["spx_close"]
    enriched = enrich_prices(prices)

    engine = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    bh = engine.run(prices, 1.0, name=BENCHMARK_LABEL)

    triples = [
        (20, 50, 200),
        (20, 100, 200),
        (10, 50, 200),
        (50, 100, 200),
        (20, 60, 120),
        (30, 90, 180),
    ]
    exclusive_flags = [False, True]

    rows: list[dict] = []
    seen: set[str] = set()

    def add_row(name: str, lev: pd.Series) -> None:
        if name in seen:
            return
        seen.add(name)
        res = engine.run(prices, lev, name=name)
        st = comprehensive_stats(res.equity, res.daily_returns, benchmark_equity=bh.equity)
        rows.append(
            {
                "name": name,
                **st,
                "rebalances": res.rebalance_count,
                "avg_lev": float(res.leverage.mean()),
                "final": res.equity.iloc[-1],
            }
        )

    for (f, m, s), exc in itertools.product(triples, exclusive_flags):
        if not (f < m < s):
            continue
        tag = "excl" if exc else "stack"
        add_row(f"SMA stair {f}/{m}/{s} ({tag})", lever_sma_stair(close, f, m, s, exc))

    for (f, m, s), exc, rhi in itertools.product(
        [(20, 50, 200), (20, 100, 200), (10, 50, 200)],
        exclusive_flags,
        [50, 55, 60],
    ):
        if not (f < m < s):
            continue
        tag = "excl" if exc else "stack"
        add_row(
            f"SMA stair {f}/{m}/{s} ({tag}) + RSI>={rhi:.0f} for 3x",
            lever_sma_stair_rsi_cap(close, f, m, s, exc, rhi, 14),
        )

    for (f, m, s), exc in itertools.product([(20, 50, 200), (20, 100, 200)], exclusive_flags):
        if not (f < m < s):
            continue
        tag = "excl" if exc else "stack"
        add_row(
            f"SMA stair {f}/{m}/{s} ({tag}) + MACD bull for 3x",
            lever_sma_stair_macd_3x(
                close,
                enriched["macd"],
                enriched["macd_signal"],
                f,
                m,
                s,
                exc,
            ),
        )

    for fast, t1, t2 in itertools.product([20, 50], [45, 50], [58, 62, 65]):
        if not (t1 < t2):
            continue
        sf = sma(close, fast)
        add_row(
            f"RSI stair (>{fast}d SMA): tiers {t1}/{t2} -> 1x/2x/3x",
            lever_rsi_stair(close, sf, t1, t2),
        )

    dd_engine = PortfolioEngine(
        max_drawdown_limit=DD_CAP,
        hard_drawdown_floor=True,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    overlay_rows: list[dict] = []

    def add_overlay(base_name: str, lev: pd.Series) -> None:
        label = base_name + " | DD overlay 15%"
        res = dd_engine.run(prices, lev, name=label)
        st = comprehensive_stats(res.equity, res.daily_returns, benchmark_equity=bh.equity)
        overlay_rows.append(
            {
                "name": label,
                **st,
                "rebalances": res.rebalance_count,
                "risk_off_days": res.risk_off_days,
                "avg_lev": float(res.leverage.mean()),
                "final": res.equity.iloc[-1],
            }
        )

    for (f, m, s), exc in itertools.product(triples, exclusive_flags):
        if not (f < m < s):
            continue
        tag = "excl" if exc else "stack"
        lev = lever_sma_stair(close, f, m, s, exc)
        add_overlay(f"SMA stair {f}/{m}/{s} ({tag})", lev)

    for fast, t1, t2 in itertools.product([20, 50], [45, 50], [58, 62, 65]):
        if not (t1 < t2):
            continue
        sf = sma(close, fast)
        add_overlay(
            f"RSI stair (>{fast}d SMA): tiers {t1}/{t2}",
            lever_rsi_stair(close, sf, t1, t2),
        )

    pd.DataFrame(overlay_rows).to_csv(OUTPUT_DIR / "tiered_with_dd_overlay_15pct.csv", index=False)
    df_overlay = pd.DataFrame(overlay_rows)

    df = pd.DataFrame(rows).drop_duplicates(subset=["name"])
    df.to_csv(OUTPUT_DIR / "tiered_grid_results.csv", index=False)

    best_sharpe = df.nlargest(15, "sharpe")
    best_calmar = df.nlargest(15, "calmar")

    feasible = df[df["max_drawdown"] >= -DD_CAP - 1e-6]
    best_cagr_dd15 = feasible.nlargest(15, "cagr") if len(feasible) else pd.DataFrame()

    bh_st = comprehensive_stats(bh.equity, bh.daily_returns)
    print(
        f"\nTiered leverage sweep | ${INITIAL_CAPITAL} start | 10% inflow | "
        f"{TRADING_COST_FROM_MID_PCT*100:.1f}% rebalance\n"
        f"Benchmark B&H 1x: Sharpe {bh_st['sharpe']:.2f} | "
        f"CAGR {bh_st['cagr']*100:.2f}% | Max DD {bh_st['max_drawdown']*100:.2f}%\n"
    )

    cols = ["name", "cagr", "volatility", "sharpe", "calmar", "max_drawdown", "final"]

    print("=" * 90)
    print("(b1) TOP 15 BY SHARPE")
    print("=" * 90)
    print(_fmt_table(best_sharpe[cols]))

    print("\n" + "=" * 90)
    print("(b2) TOP 15 BY CALMAR")
    print("=" * 90)
    print(_fmt_table(best_calmar[cols]))

    print("\n" + "=" * 90)
    print(f"(b3) TOP BY CAGR SUBJECT TO MAX DD <= {DD_CAP*100:.0f}% (realized)")
    print("=" * 90)
    if best_cagr_dd15.empty:
        print("None in grid met DD <= 15% without an explicit portfolio stop.")
    else:
        print(_fmt_table(best_cagr_dd15[cols]))

    winners = [
        {"objective": "max_sharpe", "winner": str(df.loc[df["sharpe"].idxmax(), "name"])},
        {"objective": "max_calmar", "winner": str(df.loc[df["calmar"].idxmax(), "name"])},
    ]
    if len(feasible):
        winners.append(
            {
                "objective": f"max_cagr_dd<={DD_CAP*100:.0f}%",
                "winner": str(feasible.loc[feasible["cagr"].idxmax(), "name"]),
            }
        )
        print("\n" + "=" * 90)
        print(f"BEST SHARPE AMONG DD <= {DD_CAP*100:.0f}%")
        print("=" * 90)
        print(_fmt_table(feasible.nlargest(10, "sharpe")[cols]))

    overlay_best_row = df_overlay.loc[df_overlay["cagr"].idxmax()]
    winners.append(
        {
            "objective": "max_cagr_tiered_with_dd_overlay_15pct",
            "winner": str(overlay_best_row["name"]),
        }
    )
    pd.DataFrame(winners).to_csv(OUTPUT_DIR / "optimization_winners.csv", index=False)

    print("\n" + "=" * 90)
    print("(b4) TIERED + PORTFOLIO DD OVERLAY 15% — TOP 10 BY CAGR (overlay enforces floor)")
    print("=" * 90)
    oc = ["name", "cagr", "volatility", "sharpe", "calmar", "max_drawdown", "final", "risk_off_days"]
    print(_fmt_table(df_overlay.nlargest(10, "cagr")[oc]))

    print(f"\nFull grid: {OUTPUT_DIR / 'tiered_grid_results.csv'}")
    print(f"DD overlay runs: {OUTPUT_DIR / 'tiered_with_dd_overlay_15pct.csv'}")
    print(f"Winners:   {OUTPUT_DIR / 'optimization_winners.csv'}")
    return 0


def _fmt_table(sub: pd.DataFrame) -> str:
    t = sub.copy()
    for c in ("cagr", "volatility", "max_drawdown"):
        if c in t.columns:
            t[c] = t[c].map(lambda x: f"{x*100:.2f}%")
    for c in ("sharpe", "calmar"):
        if c in t.columns:
            t[c] = t[c].map(lambda x: f"{x:.2f}")
    if "final" in t.columns:
        t["final"] = t["final"].map(lambda x: f"${x:,.0f}")
    return t.to_string(index=False)


if __name__ == "__main__":
    sys.exit(main())
