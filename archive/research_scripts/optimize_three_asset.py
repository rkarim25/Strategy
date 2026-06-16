"""
Optimize static weights among S&P 500, gold (GC=F), and T-Bills (cash yield).

Same mechanics as rest of stack: $100 start, 10% AUM inflow first trading day each year.

Objectives:
  - maximize CAGR (end wealth)
  - maximize Sharpe (daily excess vs TBill yield / 252)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_three_asset import GOLD_TICKER, load_three_asset_data
from engine import ANNUAL_CASH_INFLOW_PCT, INITIAL_CAPITAL, TRADING_DAYS

OUTPUT_DIR = Path("output") / "tthree_asset_alloc"

SIMPLEX_GRID_STEP = 0.05  # 5% increments on {w_sp, w_au, w_tb}; 231 combos


def tbill_daily_yield(tbill_annual: pd.Series) -> pd.Series:
    return tbill_annual / TRADING_DAYS


def simulate_buy_hold_equity(
    weights: np.ndarray,
    df: pd.DataFrame,
    initial: float = INITIAL_CAPITAL,
    inflow_pct: float = ANNUAL_CASH_INFLOW_PCT,
) -> tuple[pd.Series, pd.Series]:
    """
    Daily rebalance implicit via constant weights on arithmetic components:
    r_p = w_sp*r_sp + w_au*r_au + w_tb*r_rf

    Returns equity curve and daily portfolio returns (aligned with df.index).
    """
    w_sp, w_au, w_tb = weights
    sp_ret = df["spx_close"].pct_change()
    au_ret = df["gold_close"].pct_change()
    rf_d = tbill_daily_yield(df["tbill_rate"])

    port_ret = w_sp * sp_ret + w_au * au_ret + w_tb * rf_d

    equity = pd.Series(index=df.index, dtype=float)
    aum = initial
    prev_year: int | None = None

    for i, dt in enumerate(df.index):
        if prev_year is not None and dt.year != prev_year:
            aum *= 1.0 + inflow_pct

        if i > 0:
            r = float(port_ret.iloc[i]) if not pd.isna(port_ret.iloc[i]) else 0.0
            aum *= 1.0 + r

        equity.iloc[i] = aum
        prev_year = dt.year

    return equity, port_ret.fillna(0.0)


def portfolio_stats(
    equity: pd.Series,
    port_ret: pd.Series,
    tbill_annual: pd.Series,
) -> dict[str, float]:
    eq = equity.dropna()
    ret = eq.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0
    vol = float(ret.std() * np.sqrt(TRADING_DAYS))

    rf_d = tbill_daily_yield(tbill_annual).reindex(port_ret.index).fillna(0.0)
    excess = port_ret - rf_d
    excess = excess.dropna()
    sharpe = (
        float(np.sqrt(TRADING_DAYS) * excess.mean() / excess.std())
        if excess.std() > 0
        else np.nan
    )

    peak = eq.cummax()
    max_dd = float(((eq - peak) / peak).min())

    return {
        "cagr": float(cagr),
        "ann_volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "final_value": float(eq.iloc[-1]),
        "start_value": float(eq.iloc[0]),
    }


def iter_simplex_grid(step: float = SIMPLEX_GRID_STEP) -> list[np.ndarray]:
    """Non-negative weights on the 3-simplex with grid spacing `step`."""
    n = int(round(1.0 / step))
    weights: list[np.ndarray] = []
    for i in range(n + 1):
        w_sp = i * step
        for j in range(n + 1 - i):
            w_au = j * step
            w_tb = 1.0 - w_sp - w_au
            weights.append(np.array([w_sp, w_au, w_tb], dtype=float))
    return weights


def optimize_portfolio(df: pd.DataFrame, objective: str) -> tuple[np.ndarray, dict]:
    tb = df["tbill_rate"]

    def scalar_score(w: np.ndarray) -> float:
        eq, pret = simulate_buy_hold_equity(w, df)
        st = portfolio_stats(eq, pret, tb)
        if objective == "cagr":
            return float(st["cagr"])
        if objective == "sharpe":
            return float(st["sharpe"]) if not np.isnan(st["sharpe"]) else -np.inf
        raise ValueError(objective)

    best_w: np.ndarray | None = None
    best_score = -np.inf
    for w in iter_simplex_grid():
        s = scalar_score(w)
        if s > best_score:
            best_score = s
            best_w = w.copy()

    assert best_w is not None
    eq, pret = simulate_buy_hold_equity(best_w, df)
    stats = portfolio_stats(eq, pret, tb)
    return best_w, stats


def equal_weight_benchmark(df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    w = np.array([1 / 3, 1 / 3, 1 / 3], dtype=float)
    eq, pret = simulate_buy_hold_equity(w, df)
    stats = portfolio_stats(eq, pret, df["tbill_rate"])
    return w, stats


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading ~30y daily data (^GSPC, GC=F gold futures, ^IRX)...")
    df = load_three_asset_data()
    print(f"{len(df)} days | {df.index[0].date()} -> {df.index[-1].date()}")

    rows = []

    w_eq, st_eq = equal_weight_benchmark(df)
    rows.append(
        {
            "label": "Equal weight 33/33/33",
            "w_sp500": w_eq[0],
            "w_gold": w_eq[1],
            "w_tbills": w_eq[2],
            **st_eq,
        }
    )

    w_cagr, st_cagr = optimize_portfolio(df, "cagr")
    rows.append(
        {
            "label": "Max CAGR (5% grid)",
            "w_sp500": w_cagr[0],
            "w_gold": w_cagr[1],
            "w_tbills": w_cagr[2],
            **st_cagr,
        }
    )

    w_sh, st_sh = optimize_portfolio(df, "sharpe")
    rows.append(
        {
            "label": "Max Sharpe (5% grid)",
            "w_sp500": w_sh[0],
            "w_gold": w_sh[1],
            "w_tbills": w_sh[2],
            **st_sh,
        }
    )

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_DIR / "optimal_allocations.csv", index=False)

    print("\n" + "=" * 84)
    print(
        f"Start ${INITIAL_CAPITAL:.2f} | {ANNUAL_CASH_INFLOW_PCT*100:.0f}% annual inflow | "
        f"Gold proxy: {GOLD_TICKER}"
    )
    print("Weights apply to daily component returns (constant mix).\n")

    display = out.copy()
    for c in ("w_sp500", "w_gold", "w_tbills"):
        display[c] = display[c].map(lambda x: f"{x*100:.2f}%")
    for c in ("cagr", "ann_volatility", "max_drawdown"):
        display[c] = display[c].map(lambda x: f"{x*100:.2f}%")
    display["sharpe"] = display["sharpe"].map(lambda x: f"{x:.3f}")
    display["start_value"] = display["start_value"].map(lambda x: f"${x:,.2f}")
    display["final_value"] = display["final_value"].map(lambda x: f"${x:,.2f}")

    cols = [
        "label",
        "w_sp500",
        "w_gold",
        "w_tbills",
        "cagr",
        "ann_volatility",
        "sharpe",
        "max_drawdown",
        "start_value",
        "final_value",
    ]
    print(display[cols].to_string(index=False))
    print("=" * 84)
    print(f"\nCSV: {OUTPUT_DIR / 'optimal_allocations.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
