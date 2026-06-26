"""
LQQ3.L asymmetric SMA20 entry/exit sweep (x=exit_pct, y=entry_pct).

Semantics (SMA20, 1x/cash):
  - EXIT (firm/slow): close < SMA * (1 - x)
  - ENTRY (quicker):   close > SMA * (1 - y)

x=exit_pct widens the exit band below SMA; y=entry_pct lowers the entry
threshold so re-entry happens sooner after a dip. y <= x is the typical
hysteresis case (easier in, harder out).

Compares vs SMA20 1x/cash and Guarded A5/B25 max 1x on real LQQ3 since 2012.
Writes output/lqq3_sma_asymmetric_xy/.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from analyze_lqq3_turnover_reduction import no_sacrifice_filter
from analyze_spx_sma20_entry_exit import pareto_3d
from backtest_lqq3_guarded import (
    DEFAULT_SPEC,
    LQQ3_START,
    LQQ3_TICKER,
    download_panel,
    make_engine,
)
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "lqq3_sma_asymmetric_xy"

EXIT_PCTS = [0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05]
ENTRY_PCTS = [0.0, 0.005, 0.01, 0.015, 0.02, 0.03]
SMA_WINDOW = BASE_SMA_WINDOW


def format_pct(pct: float) -> str:
    if pct == 0.0:
        return "0"
    return f"{pct * 100:.1f}".rstrip("0").rstrip(".")


def asymmetric_label(*, exit_pct: float, entry_pct: float) -> str:
    if exit_pct == 0.0 and entry_pct == 0.0:
        return "SMA20 1x/cash (baseline)"
    return (
        f"SMA20 1x/cash entry-{format_pct(entry_pct)}%/exit-{format_pct(exit_pct)}%"
    )


def sma_asymmetric_xy_leverage(
    prices: pd.DataFrame,
    *,
    window: int = SMA_WINDOW,
    exit_pct: float = 0.0,
    entry_pct: float = 0.0,
    leverage: float = 1.0,
) -> pd.Series:
    """
    Stateful SMA hysteresis with user x/y semantics.

    exit_pct (x): sell when close < SMA * (1 - x)
    entry_pct (y): buy when close > SMA * (1 - y)
    """
    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()

    lev = pd.Series(0.0, index=prices.index)
    in_position = False

    for dt in prices.index:
        px = float(close.loc[dt])
        s = float(sma.loc[dt]) if pd.notna(sma.loc[dt]) else float("nan")

        if not np.isfinite(s) or s <= 0:
            lev.loc[dt] = 0.0
            in_position = False
            continue

        entry_thresh = s * (1.0 - entry_pct)
        exit_thresh = s * (1.0 - exit_pct)

        if in_position:
            if px < exit_thresh:
                in_position = False
        else:
            if px > entry_thresh:
                in_position = True

        lev.loc[dt] = float(leverage) if in_position else 0.0

    return lev


def run_row(prices: pd.DataFrame, lev: pd.Series, label: str, **meta) -> dict:
    res = make_engine().run(prices, lev, name=label)
    stats = comprehensive_stats(res.equity, res.daily_returns)
    cash = invested_vs_tbills_sessions(res.leverage)
    return {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(res.equity.iloc[-1]),
        "rebalances": int(res.rebalance_count),
        "trading_costs_total": res.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        **meta,
    }


def beats_baseline(row: pd.Series, baseline: pd.Series) -> dict[str, float | bool | int]:
    return {
        "beats_cagr": bool(row["cagr"] > baseline["cagr"]),
        "beats_sharpe": bool(row["sharpe"] > baseline["sharpe"]),
        "beats_max_dd": bool(row["max_drawdown"] > baseline["max_drawdown"]),
        "fewer_rebalances": bool(row["rebalances"] < baseline["rebalances"]),
        "cagr_delta_pp": float((row["cagr"] - baseline["cagr"]) * 100.0),
        "sharpe_delta": float(row["sharpe"] - baseline["sharpe"]),
        "max_dd_delta_pp": float((row["max_drawdown"] - baseline["max_drawdown"]) * 100.0),
        "rebalances_delta": int(row["rebalances"] - baseline["rebalances"]),
    }


def balanced_improvers(
    sweep: pd.DataFrame,
    baseline: pd.Series,
    *,
    max_dd_slack_pp: float = 1.0,
    min_rebal_reduction: int = 0,
) -> pd.DataFrame:
    """Configs that improve CAGR or Sharpe without material DD deterioration."""
    work = sweep.copy()
    dd_ok = work["max_drawdown"] >= baseline["max_drawdown"] - max_dd_slack_pp / 100.0
    improves = (work["cagr"] > baseline["cagr"]) | (work["sharpe"] > baseline["sharpe"])
    reb_ok = work["rebalances"] <= baseline["rebalances"] - min_rebal_reduction
    out = work[dd_ok & improves & reb_ok].copy()
    out["score"] = (
        out["sharpe_delta_vs_ref"]
        + out["cagr_delta_pp_vs_ref"] / 100.0
        - out["rebalances_delta_vs_ref"].clip(lower=0) * 0.002
    )
    return out.sort_values(["score", "sharpe", "cagr"], ascending=[False, False, False])


def annotate_vs_baseline(sweep: pd.DataFrame, baseline: pd.Series, prefix: str) -> pd.DataFrame:
    deltas = sweep.apply(lambda r: beats_baseline(r, baseline), axis=1, result_type="expand")
    out = pd.concat([sweep.reset_index(drop=True), deltas], axis=1)
    out = out.rename(
        columns={
            "cagr_delta_pp": f"cagr_delta_pp_vs_{prefix}",
            "sharpe_delta": f"sharpe_delta_vs_{prefix}",
            "max_dd_delta_pp": f"max_dd_delta_pp_vs_{prefix}",
            "rebalances_delta": f"rebalances_delta_vs_{prefix}",
        }
    )
    return out


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading LQQ3.L...", flush=True)
    prices = download_panel(LQQ3_TICKER, start=LQQ3_START)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)",
        flush=True,
    )

    rows: list[dict] = []

    lev_sma20 = sma_cash_leverage(prices, SMA_WINDOW, 1.0)
    rows.append(
        run_row(
            prices,
            lev_sma20,
            "SMA20 1x/cash (baseline)",
            family="baseline",
            exit_pct=0.0,
            entry_pct=0.0,
            y_le_x=True,
        )
    )

    lev_guard, gcounts = guarded_lead_leverage(prices, max_leverage=1.0)
    rows.append(
        run_row(
            prices,
            lev_guard,
            DEFAULT_SPEC["strategy"],
            family="baseline",
            **gcounts,
        )
    )

    configs: list[tuple[float, float]] = []
    for exit_pct, entry_pct in product(EXIT_PCTS, ENTRY_PCTS):
        if exit_pct == 0.0 and entry_pct == 0.0:
            continue
        configs.append((exit_pct, entry_pct))

    print(f"Running {len(configs)} asymmetric x/y configs...", flush=True)
    for i, (exit_pct, entry_pct) in enumerate(configs, 1):
        lev = sma_asymmetric_xy_leverage(
            prices,
            window=SMA_WINDOW,
            exit_pct=exit_pct,
            entry_pct=entry_pct,
            leverage=1.0,
        )
        label = asymmetric_label(exit_pct=exit_pct, entry_pct=entry_pct)
        rows.append(
            run_row(
                prices,
                lev,
                label,
                family="asymmetric_xy",
                exit_pct=exit_pct,
                entry_pct=entry_pct,
                y_le_x=entry_pct <= exit_pct,
            )
        )
        if i % 20 == 0:
            print(f"  ... {i}/{len(configs)}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    sma_base = df[df["strategy"] == "SMA20 1x/cash (baseline)"].iloc[0]
    guard_base = df[df["strategy"] == DEFAULT_SPEC["strategy"]].iloc[0]
    sweep = df[df["family"] == "asymmetric_xy"].copy()

    sweep_sma = annotate_vs_baseline(sweep, sma_base, "sma")
    sweep_guard = annotate_vs_baseline(sweep, guard_base, "guard")
    sweep_annot = sweep_sma.merge(
        sweep_guard[
            [
                "strategy",
                "cagr_delta_pp_vs_guard",
                "sharpe_delta_vs_guard",
                "max_dd_delta_pp_vs_guard",
                "rebalances_delta_vs_guard",
                "beats_cagr",
                "beats_sharpe",
                "beats_max_dd",
                "fewer_rebalances",
            ]
        ].rename(
            columns={
                "beats_cagr": "beats_cagr_vs_guard",
                "beats_sharpe": "beats_sharpe_vs_guard",
                "beats_max_dd": "beats_max_dd_vs_guard",
                "fewer_rebalances": "fewer_rebalances_vs_guard",
            }
        ),
        on="strategy",
        how="left",
    )
    sweep_annot = sweep_annot.rename(
        columns={
            "beats_cagr": "beats_cagr_vs_sma",
            "beats_sharpe": "beats_sharpe_vs_sma",
            "beats_max_dd": "beats_max_dd_vs_sma",
            "fewer_rebalances": "fewer_rebalances_vs_sma",
        }
    )

    sweep_annot.to_csv(OUTPUT_DIR / "sweep_annotated.csv", index=False)

    ranked_cagr = sweep_annot.sort_values("cagr", ascending=False)
    ranked_cagr.to_csv(OUTPUT_DIR / "ranked_cagr.csv", index=False)

    ranked_sharpe = sweep_annot.sort_values("sharpe", ascending=False)
    ranked_sharpe.to_csv(OUTPUT_DIR / "ranked_sharpe.csv", index=False)

    ranked_low_rebal = sweep_annot.sort_values("rebalances", ascending=True)
    ranked_low_rebal.to_csv(OUTPUT_DIR / "ranked_low_rebalances.csv", index=False)

    pareto = pareto_3d(sweep_annot.assign(family="asymmetric_xy"))
    pareto.to_csv(OUTPUT_DIR / "pareto_frontier.csv", index=False)

    no_sac_sma = no_sacrifice_filter(sweep_annot, sma_base).sort_values(
        ["rebalances", "sharpe"], ascending=[True, False]
    )
    no_sac_guard = no_sacrifice_filter(sweep_annot, guard_base).sort_values(
        ["rebalances", "sharpe"], ascending=[True, False]
    )
    no_sac_sma.to_csv(OUTPUT_DIR / "no_sacrifice_vs_sma20.csv", index=False)
    no_sac_guard.to_csv(OUTPUT_DIR / "no_sacrifice_vs_guarded.csv", index=False)

    balanced_sma = balanced_improvers(
        sweep_annot.assign(
            sharpe_delta_vs_ref=sweep_annot["sharpe_delta_vs_sma"],
            cagr_delta_pp_vs_ref=sweep_annot["cagr_delta_pp_vs_sma"],
            rebalances_delta_vs_ref=sweep_annot["rebalances_delta_vs_sma"],
        ),
        sma_base,
        max_dd_slack_pp=1.0,
    )
    balanced_guard = balanced_improvers(
        sweep_annot.assign(
            sharpe_delta_vs_ref=sweep_annot["sharpe_delta_vs_guard"],
            cagr_delta_pp_vs_ref=sweep_annot["cagr_delta_pp_vs_guard"],
            rebalances_delta_vs_ref=sweep_annot["rebalances_delta_vs_guard"],
        ),
        guard_base,
        max_dd_slack_pp=1.0,
    )
    balanced_sma.to_csv(OUTPUT_DIR / "balanced_improvers_vs_sma20.csv", index=False)
    balanced_guard.to_csv(OUTPUT_DIR / "balanced_improvers_vs_guarded.csv", index=False)

    any_dim_sma = sweep_annot[
        sweep_annot["beats_cagr_vs_sma"]
        | sweep_annot["beats_sharpe_vs_sma"]
        | sweep_annot["beats_max_dd_vs_sma"]
        | sweep_annot["fewer_rebalances_vs_sma"]
    ].sort_values(["sharpe", "cagr"], ascending=[False, False])
    any_dim_sma.to_csv(OUTPUT_DIR / "beats_any_vs_sma20.csv", index=False)

    any_dim_guard = sweep_annot[
        sweep_annot["beats_cagr_vs_guard"]
        | sweep_annot["beats_sharpe_vs_guard"]
        | sweep_annot["beats_max_dd_vs_guard"]
        | sweep_annot["fewer_rebalances_vs_guard"]
    ].sort_values(["sharpe", "cagr"], ascending=[False, False])
    any_dim_guard.to_csv(OUTPUT_DIR / "beats_any_vs_guarded.csv", index=False)

    sweep_annot["y_le_x"] = sweep_annot["entry_pct"] <= sweep_annot["exit_pct"]
    y_le_x = sweep_annot[sweep_annot["y_le_x"]].copy()
    y_gt_x = sweep_annot[~sweep_annot["y_le_x"]].copy()

    best_overall = sweep_annot.sort_values(
        ["sharpe", "cagr", "rebalances"],
        ascending=[False, False, True],
    ).head(15)

    true_improve_sma = sweep_annot[
        (sweep_annot["cagr"] >= sma_base["cagr"])
        & (sweep_annot["sharpe"] >= sma_base["sharpe"])
        & (sweep_annot["max_drawdown"] >= sma_base["max_drawdown"])
    ]
    true_improve_guard = sweep_annot[
        (sweep_annot["cagr"] >= guard_base["cagr"])
        & (sweep_annot["sharpe"] >= guard_base["sharpe"])
        & (sweep_annot["max_drawdown"] >= guard_base["max_drawdown"])
    ]

    verdict_parts: list[str] = []
    if len(true_improve_sma):
        verdict_parts.append(
            f"{len(true_improve_sma)} config(s) Pareto-dominate SMA20 on CAGR, Sharpe, and max DD."
        )
    else:
        verdict_parts.append("No config simultaneously beats SMA20 on CAGR, Sharpe, and max DD.")

    if len(true_improve_guard):
        verdict_parts.append(
            f"{len(true_improve_guard)} config(s) Pareto-dominate Guarded on CAGR, Sharpe, and max DD."
        )
    else:
        verdict_parts.append(
            "No config simultaneously beats Guarded on CAGR, Sharpe, and max DD."
        )

    if len(no_sac_sma):
        verdict_parts.append(
            f"{len(no_sac_sma)} no-sacrifice vs SMA20 (CAGR+DD held, fewer/same rebals possible)."
        )
    if len(no_sac_guard):
        verdict_parts.append(
            f"{len(no_sac_guard)} no-sacrifice vs Guarded."
        )

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "semantics": {
            "exit_pct_x": "exit when close < SMA * (1 - x)",
            "entry_pct_y": "enter when close > SMA * (1 - y)",
            "sma_window": SMA_WINDOW,
            "leverage": 1.0,
        },
        "grid": {
            "exit_pcts_x": EXIT_PCTS,
            "entry_pcts_y": ENTRY_PCTS,
            "n_configs": len(configs),
            "n_y_le_x": int(y_le_x.shape[0]),
            "n_y_gt_x": int(y_gt_x.shape[0]),
        },
        "sample": {
            "ticker": LQQ3_TICKER,
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": 10,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
        },
        "baselines": {
            "sma20": sma_base.to_dict(),
            "guarded": guard_base.to_dict(),
        },
        "counts": {
            "beats_any_dimension_vs_sma20": int(len(any_dim_sma)),
            "beats_any_dimension_vs_guarded": int(len(any_dim_guard)),
            "no_sacrifice_vs_sma20": int(len(no_sac_sma)),
            "no_sacrifice_vs_guarded": int(len(no_sac_guard)),
            "true_improve_vs_sma20": int(len(true_improve_sma)),
            "true_improve_vs_guarded": int(len(true_improve_guard)),
            "pareto_frontier": int(len(pareto)),
            "balanced_improvers_vs_sma20": int(len(balanced_sma)),
            "balanced_improvers_vs_guarded": int(len(balanced_guard)),
        },
        "best_by_sharpe": ranked_sharpe.head(10).to_dict(orient="records"),
        "best_by_cagr": ranked_cagr.head(10).to_dict(orient="records"),
        "lowest_rebalances": ranked_low_rebal.head(10).to_dict(orient="records"),
        "no_sacrifice_vs_sma20_top": no_sac_sma.head(10).to_dict(orient="records"),
        "no_sacrifice_vs_guarded_top": no_sac_guard.head(10).to_dict(orient="records"),
        "balanced_improvers_vs_sma20_top": balanced_sma.head(10).to_dict(orient="records"),
        "balanced_improvers_vs_guarded_top": balanced_guard.head(10).to_dict(orient="records"),
        "true_improve_vs_sma20": true_improve_sma.to_dict(orient="records"),
        "true_improve_vs_guarded": true_improve_guard.to_dict(orient="records"),
        "best_overall_top15": best_overall.to_dict(orient="records"),
        "verdict": " ".join(verdict_parts),
    }

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    def print_row(r: pd.Series) -> None:
        print(
            f"  {str(r['strategy'])[:56]:56}  "
            f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
            f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
            f"End ${r['end_$']:,.0f}  Rebals {int(r['rebalances']):4d}"
        )

    print("\n--- Baselines ---")
    print_row(sma_base)
    print_row(guard_base)

    print("\n--- Top 10 by Sharpe ---")
    for _, r in ranked_sharpe.head(10).iterrows():
        print_row(r)

    print("\n--- No sacrifice vs SMA20 (CAGR & DD held) ---")
    if no_sac_sma.empty:
        print("  (none)")
    else:
        for _, r in no_sac_sma.head(8).iterrows():
            print_row(r)

    print("\n--- Balanced improvers vs SMA20 (CAGR or Sharpe up, DD within 1pp) ---")
    if balanced_sma.empty:
        print("  (none)")
    else:
        for _, r in balanced_sma.head(8).iterrows():
            print_row(r)

    print(f"\n{summary['verdict']}")
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
