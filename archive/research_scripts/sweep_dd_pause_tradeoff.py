"""Grid search: DD pause trigger vs days out — rank tradeoffs vs SMA20@3x baseline."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from sweep_sma_periods import leverage_daily_sma

OUTPUT_DIR = Path("output") / "dd_pause_tradeoff_sweep"

# Reasonable grid for ~20y sample with peak reset on re-entry
DD_PCTS = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0]
PAUSE_DAYS = [5, 10, 15, 21, 30, 42]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    lev = leverage_daily_sma(prices, window=20, levered=3.0)

    base_eng = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )
    r0 = base_eng.run(prices, lev, name="baseline")
    s0 = comprehensive_stats(r0.equity, r0.daily_returns)
    b_cagr = float(s0["cagr"])
    b_mdd = float(s0["max_drawdown"])

    rows: list[dict] = []
    for dd_pct in DD_PCTS:
        trig = dd_pct / 100.0
        for pause in PAUSE_DAYS:
            eng = PortfolioEngine(
                max_drawdown_limit=None,
                hard_drawdown_floor=False,
                trading_cost_pct=TRADING_COST_FROM_MID_PCT,
                dd_pause_trigger=trig,
                dd_pause_trading_days=pause,
                dd_pause_reset_peak_on_reentry=True,
            )
            res = eng.run(prices, lev, name=f"dd{dd_pct}_p{pause}")
            st = comprehensive_stats(res.equity, res.daily_returns)
            cagr = float(st["cagr"])
            mdd = float(st["max_drawdown"])
            # Shallower DD = larger mdd number (e.g. -0.35 > -0.44)
            mdd_improve_pp = (mdd - b_mdd) * 100.0
            cagr_rel = cagr / b_cagr if b_cagr else float("nan")
            cagr_drag_pp = (cagr - b_cagr) * 100.0
            rows.append(
                {
                    "dd_trigger_pct": dd_pct,
                    "pause_days": pause,
                    "cagr": cagr,
                    "cagr_vs_baseline": cagr_rel,
                    "cagr_drag_pp": cagr_drag_pp,
                    "max_drawdown": mdd,
                    "mdd_improve_pp": mdd_improve_pp,
                    "sharpe": st["sharpe"],
                    "risk_off_days": res.risk_off_days,
                    "rebalances": res.rebalance_count,
                    "end_$": float(res.equity.iloc[-1]),
                }
            )

    df = pd.DataFrame(rows)
    out = OUTPUT_DIR / "dd_pause_tradeoff_grid.csv"
    df.to_csv(out, index=False)

    # Pareto-ish: maximize mdd improvement subject to modest CAGR hit
    df2 = df.copy()
    df2["efficiency"] = df2["mdd_improve_pp"] / (
        (-df2["cagr_drag_pp"]).clip(lower=0.01)
    )

    tight = df2[
        (df2["cagr_vs_baseline"] >= 0.96) & (df2["mdd_improve_pp"] > 3.0)
    ].sort_values(
        ["mdd_improve_pp", "cagr_vs_baseline"],
        ascending=[False, False],
    )

    print(
        f"SMA20 @ 3x baseline | ${INITIAL_CAPITAL} start | "
        f"CAGR={b_cagr*100:.2f}% maxDD={b_mdd*100:.2f}%"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()}\n")

    print(
        "Top by maxDD improvement with CAGR >= 96% of baseline "
        "and at least +3pp shallower maxDD:\n"
    )
    cols = [
        "dd_trigger_pct",
        "pause_days",
        "cagr",
        "cagr_vs_baseline",
        "max_drawdown",
        "mdd_improve_pp",
        "risk_off_days",
    ]
    if len(tight):
        disp = tight[cols].head(12).copy()
        disp["cagr"] = disp["cagr"].map(lambda x: f"{x*100:.2f}%")
        disp["cagr_vs_baseline"] = disp["cagr_vs_baseline"].map(lambda x: f"{x*100:.1f}%")
        disp["max_drawdown"] = disp["max_drawdown"].map(lambda x: f"{x*100:.2f}%")
        disp["mdd_improve_pp"] = disp["mdd_improve_pp"].map(lambda x: f"+{x:.2f} pp")
        print(disp.to_string(index=False))
    else:
        print("(no rows — relax filters)")

    print("\nBest single 'balance' pick: highest mdd_improve_pp among cagr_vs_baseline >= 0.97:")
    ok = df2[df2["cagr_vs_baseline"] >= 0.97].sort_values(
        "mdd_improve_pp", ascending=False
    )
    if len(ok):
        top = ok.iloc[0]
        print(
            f"  DD trigger={top['dd_trigger_pct']:.0f}%  out {int(top['pause_days'])} sessions  |  "
            f"CAGR {top['cagr']*100:.2f}% ({top['cagr_vs_baseline']*100:.1f}% of base)  |  "
            f"maxDD {top['max_drawdown']*100:.2f}%  |  "
            f"DD improved {top['mdd_improve_pp']:.2f} pp vs baseline"
        )

    print(f"\nFull grid: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
