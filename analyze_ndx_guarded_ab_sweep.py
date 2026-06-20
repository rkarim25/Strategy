"""Grid-search NDX Guarded drawdown trigger parameters (A, B) — and optional X/Y hysteresis sweep.

Parameter convention (verified against engine.py + test_guarded_balanced_candidate.py):
    A  = trigger_a            -> DD-from-peak threshold to ARM 2x (decimal, e.g. 0.05 = 5%)
    B  = trigger_b            -> DD-from-peak threshold to BOOST to 3x (decimal; constraint A < B)
    X  = x_return             -> upward price recovery from tier-2 entry to step BACK to base
    Y  = y_return             -> upward price recovery from tier-3 entry to step BACK to base
    lead_pct_below_sma20      -> SMA20 lead filter for tier re-engagement (kept at default 0.0075)

Recovery thresholds (X, Y) are NOT DD-from-peak hysteresis values — they are upward
price-return thresholds measured from the tier-entry close. They live alongside A/B,
not symmetric to them. For the primary sweep we keep X/Y at the website default
(X=0.40, Y=0.15) and vary only A and B. A focused secondary sweep around the
winning (A, B) varies (X, Y) for sensitivity.

Reuses engine.py + etp_leverage.py + guarded_strategy_leverage() verbatim — no
internal logic is modified. Same ETP+VIX cost model and date range as the live
website backtest (backtest_ndx_guarded.py) by calling its `download_ndx_panel`
and `build_etp_return_panel` once and caching the panels for the entire sweep.

Outputs to output/ndx_guarded_ab_sweep/:
    ab_sweep_results.csv     full grid with all metrics
    ab_sweep_ranked.csv      ranked by Calmar, then CAGR, then |MaxDD|
    pareto_frontier.csv      non-dominated (CAGR vs MaxDD) points
    comparison_table.md      markdown ranking table
    summary.json             top 10, baseline, Pareto, heat-map directions
    secondary_xy_sweep.csv   X/Y sensitivity around winning A/B
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_ndx_guarded import (
    DEFAULT_SPEC,
    download_ndx_panel,
    make_engine,
)
from etp_leverage import NDX_ETP, build_etp_return_panel, etp_coverage_summary
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "ndx_guarded_ab_sweep"

A_GRID_PCT = [3, 4, 5, 7, 10, 12, 15]
B_GRID_PCT = [15, 20, 25, 30, 35, 40, 45]

X_DEFAULT = float(DEFAULT_SPEC["x_return"])
Y_DEFAULT = float(DEFAULT_SPEC["y_return"])
LEAD_DEFAULT = float(DEFAULT_SPEC["lead_pct_below_sma20"])

BASELINE_A_PCT = 5
BASELINE_B_PCT = 25
BASELINE_CAGR = 0.8995
BASELINE_MAX_DD = -0.3551


def run_one(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    *,
    a: float,
    b: float,
    x: float = X_DEFAULT,
    y: float = Y_DEFAULT,
    lead: float = LEAD_DEFAULT,
) -> dict:
    label = f"A{int(round(a * 100))}/B{int(round(b * 100))}"
    lev, counts = guarded_strategy_leverage(
        prices,
        trigger_a=a,
        trigger_b=b,
        lead_pct_below_sma20=lead,
        x_return=x,
        y_return=y,
    )
    result = make_engine().run(prices, lev, name=label, etp_returns=etp_panel)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "label": label,
        "A_pct": a * 100.0,
        "B_pct": b * 100.0,
        "X_pct": x * 100.0,
        "Y_pct": y * 100.0,
        "trigger_a": a,
        "trigger_b": b,
        "x_return": x,
        "y_return": y,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats["calmar"],
        "end_$": float(result.equity.iloc[-1]),
        "ulcer_index": stats["ulcer_index"],
        "max_dd_duration_days": stats["max_dd_duration_days"],
        "rebalances": int(result.rebalance_count),
        "tier2_entries": int(counts["tier2_entries"]),
        "tier3_entries": int(counts["tier3_entries"]),
        "lead_only_days": int(counts["lead_only_days"]),
        "pct_days_cash": float(counts["pct_days_cash"]),
        "pct_days_1x": float(counts["pct_days_1x"]),
        "pct_days_2x": float(counts["pct_days_2x"]),
        "pct_days_3x": float(counts["pct_days_3x"]),
    }


def primary_sweep(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    combos = [
        (a_pct / 100.0, b_pct / 100.0)
        for a_pct in A_GRID_PCT
        for b_pct in B_GRID_PCT
        if a_pct < b_pct
    ]
    print(f"Primary sweep: {len(combos)} (A,B) combos.", flush=True)
    t0 = time.time()
    for i, (a, b) in enumerate(combos, 1):
        row = run_one(prices, etp_panel, a=a, b=b)
        elapsed = time.time() - t0
        avg = elapsed / i
        eta = avg * (len(combos) - i)
        print(
            f"  [{i:>2}/{len(combos)}] {row['label']:>9}  "
            f"CAGR={row['cagr']*100:6.2f}%  DD={row['max_drawdown']*100:6.2f}%  "
            f"Calmar={row['calmar']:5.2f}  Sharpe={row['sharpe']:5.2f}  "
            f"end=${row['end_$']/1e9:6.2f}B  rebals={row['rebalances']:>4}  "
            f"[elapsed {elapsed:5.1f}s, eta {eta:4.0f}s]",
            flush=True,
        )
        rows.append(row)
    return pd.DataFrame(rows)


def pareto_frontier(
    df: pd.DataFrame,
    *,
    cagr_tol: float = 1e-6,
    dd_tol: float = 1e-4,
) -> pd.DataFrame:
    """Non-dominated points: CAGR up is better, MaxDD up (closer to 0) is better.

    Tolerances ignore float-precision noise (e.g. when two configs produce DDs that
    differ only at the 9th decimal). Within a tolerance bucket the points are treated
    as ties and a point with strictly higher metric on the other axis dominates them.
    """
    points = df[["cagr", "max_drawdown"]].to_numpy()
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            better_or_equal_cagr = points[j, 0] >= points[i, 0] - cagr_tol
            better_or_equal_dd = points[j, 1] >= points[i, 1] - dd_tol
            strictly_better = (points[j, 0] > points[i, 0] + cagr_tol) or (
                points[j, 1] > points[i, 1] + dd_tol
            )
            if better_or_equal_cagr and better_or_equal_dd and strictly_better:
                keep[i] = False
                break
    return df[keep].sort_values("cagr", ascending=False).reset_index(drop=True)


def write_markdown(ranked: pd.DataFrame, baseline_row: dict | None, out_path: Path) -> None:
    cols = [
        ("label", "Config"),
        ("cagr", "CAGR"),
        ("max_drawdown", "MaxDD"),
        ("calmar", "Calmar"),
        ("sharpe", "Sharpe"),
        ("end_$", "End $"),
        ("ann_volatility", "Vol"),
        ("rebalances", "Rebals"),
        ("tier2_entries", "T2 ent"),
        ("tier3_entries", "T3 ent"),
        ("pct_days_1x", "% 1x"),
        ("pct_days_2x", "% 2x"),
        ("pct_days_3x", "% 3x"),
    ]
    header = "| " + " | ".join(c[1] for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    lines = [
        "# NDX Guarded A/B sweep — ranked by Calmar",
        "",
        f"Baseline (current website default): A5/B25  -> "
        f"CAGR {BASELINE_CAGR*100:.2f}%, MaxDD {BASELINE_MAX_DD*100:.2f}%, "
        f"Calmar {BASELINE_CAGR/abs(BASELINE_MAX_DD):.2f}",
        "",
        header,
        sep,
    ]

    def fmt_row(r: pd.Series) -> str:
        return (
            f"| {r['label']} "
            f"| {r['cagr']*100:.2f}% "
            f"| {r['max_drawdown']*100:.2f}% "
            f"| {r['calmar']:.2f} "
            f"| {r['sharpe']:.2f} "
            f"| ${r['end_$']/1e9:,.2f}B "
            f"| {r['ann_volatility']*100:.1f}% "
            f"| {int(r['rebalances'])} "
            f"| {int(r['tier2_entries'])} "
            f"| {int(r['tier3_entries'])} "
            f"| {r['pct_days_1x']:.1f}% "
            f"| {r['pct_days_2x']:.1f}% "
            f"| {r['pct_days_3x']:.1f}% |"
        )

    for _, r in ranked.iterrows():
        lines.append(fmt_row(r))

    if baseline_row is not None:
        lines.append("")
        lines.append("**Baseline row in sweep:**")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        lines.append(fmt_row(pd.Series(baseline_row)))

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def heat_map_insight(df: pd.DataFrame) -> dict:
    """Direction of CAGR/MaxDD as A and B move."""
    g = df.groupby("A_pct").agg(mean_cagr=("cagr", "mean"), mean_dd=("max_drawdown", "mean")).reset_index()
    h = df.groupby("B_pct").agg(mean_cagr=("cagr", "mean"), mean_dd=("max_drawdown", "mean")).reset_index()
    return {
        "by_A": g.to_dict(orient="records"),
        "by_B": h.to_dict(orient="records"),
    }


def secondary_xy_sweep(
    prices: pd.DataFrame, etp_panel: pd.DataFrame, *, a: float, b: float
) -> pd.DataFrame:
    """Focused X/Y sensitivity around the winning A/B."""
    xy_grid = [
        (X_DEFAULT, Y_DEFAULT),
        (0.30, 0.10),
        (0.30, 0.20),
        (0.50, 0.10),
        (0.50, 0.20),
        (0.40, 0.10),
        (0.40, 0.20),
    ]
    rows: list[dict] = []
    print(f"\nSecondary X/Y sweep around A{int(a*100)}/B{int(b*100)}: {len(xy_grid)} combos.", flush=True)
    for i, (x, y) in enumerate(xy_grid, 1):
        row = run_one(prices, etp_panel, a=a, b=b, x=x, y=y)
        row["label"] = (
            f"A{int(a*100)}/B{int(b*100)} X{int(x*100)}/Y{int(y*100)}"
        )
        print(
            f"  [{i}/{len(xy_grid)}] {row['label']:>20}  "
            f"CAGR={row['cagr']*100:6.2f}%  DD={row['max_drawdown']*100:6.2f}%  "
            f"Calmar={row['calmar']:5.2f}",
            flush=True,
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading NDX + T-bill panel (one shot, cached for all combos)...", flush=True)
    prices = download_ndx_panel()
    print(
        f"Loaded {len(prices)} sessions: "
        f"{prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    print("Building NDX ETP return panel (one shot, cached for all combos)...", flush=True)
    etp_panel = build_etp_return_panel(prices, NDX_ETP)
    coverage = etp_coverage_summary(etp_panel)
    print(
        f"ETP coverage: real 2x={coverage.get('pct_real_2x', 0):.1f}% "
        f"real 3x={coverage.get('pct_real_3x', 0):.1f}%",
        flush=True,
    )

    df = primary_sweep(prices, etp_panel)
    df.to_csv(OUTPUT_DIR / "ab_sweep_results.csv", index=False)

    ranked = df.sort_values(
        by=["calmar", "cagr", "max_drawdown"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    ranked.to_csv(OUTPUT_DIR / "ab_sweep_ranked.csv", index=False)

    pareto = pareto_frontier(df)
    pareto.to_csv(OUTPUT_DIR / "pareto_frontier.csv", index=False)

    baseline_row = (
        df[(df["A_pct"] == BASELINE_A_PCT) & (df["B_pct"] == BASELINE_B_PCT)]
        .iloc[0]
        .to_dict()
    )

    write_markdown(ranked.head(20), baseline_row, OUTPUT_DIR / "comparison_table.md")

    top5_calmar = ranked.head(5)
    keep_cagr_mask = df["cagr"] >= BASELINE_CAGR
    keep_cagr = df[keep_cagr_mask].sort_values("max_drawdown", ascending=False).head(5)

    measured_baseline_dd = float(baseline_row["max_drawdown"])
    measured_baseline_cagr = float(baseline_row["cagr"])
    dominated_baseline = df[
        (df["cagr"] >= measured_baseline_cagr - 1e-6)
        & (df["max_drawdown"] > measured_baseline_dd + 1e-4)
    ].sort_values("max_drawdown", ascending=False)
    no_sacrifice = df[
        (df["cagr"] >= measured_baseline_cagr - 1e-6)
    ].sort_values(["max_drawdown", "cagr"], ascending=[False, False])

    winner = ranked.iloc[0]
    winner_a = float(winner["trigger_a"])
    winner_b = float(winner["trigger_b"])
    xy_df = secondary_xy_sweep(prices, etp_panel, a=winner_a, b=winner_b)
    xy_df.to_csv(OUTPUT_DIR / "secondary_xy_sweep.csv", index=False)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start_date": prices.index[0].date().isoformat(),
            "end_date": prices.index[-1].date().isoformat(),
            "trading_days": int(len(prices)),
        },
        "baseline_default_A5_B25": {
            "A_pct": BASELINE_A_PCT,
            "B_pct": BASELINE_B_PCT,
            "X_pct": X_DEFAULT * 100.0,
            "Y_pct": Y_DEFAULT * 100.0,
            "expected_cagr": BASELINE_CAGR,
            "expected_max_drawdown": BASELINE_MAX_DD,
            "expected_calmar": BASELINE_CAGR / abs(BASELINE_MAX_DD),
            "measured_in_sweep": baseline_row,
        },
        "grid": {
            "A_pct": A_GRID_PCT,
            "B_pct": B_GRID_PCT,
            "constraint": "A < B",
            "X_pct": X_DEFAULT * 100.0,
            "Y_pct": Y_DEFAULT * 100.0,
            "lead_pct_below_sma20": LEAD_DEFAULT,
        },
        "top10_by_calmar": ranked.head(10).to_dict(orient="records"),
        "top5_lowest_DD_with_CAGR_>=_baseline": keep_cagr.to_dict(orient="records"),
        "pareto_frontier": pareto.to_dict(orient="records"),
        "dominate_baseline_strict_DD_and_CAGR_>=_baseline": dominated_baseline.to_dict(
            orient="records"
        ),
        "directional_means": heat_map_insight(df),
        "secondary_xy_sweep": xy_df.to_dict(orient="records"),
        "etp_coverage": coverage,
    }

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=float) + "\n", encoding="utf-8"
    )

    print("\n" + "=" * 90)
    print("BASELINE  A5/B25 (measured in this sweep):")
    print(
        f"  CAGR={baseline_row['cagr']*100:6.2f}%  "
        f"DD={baseline_row['max_drawdown']*100:6.2f}%  "
        f"Calmar={baseline_row['calmar']:.2f}  "
        f"Sharpe={baseline_row['sharpe']:.2f}  "
        f"end=${baseline_row['end_$']/1e9:.2f}B  "
        f"rebals={int(baseline_row['rebalances'])}"
    )

    print("\nTop 5 by Calmar:")
    for _, r in top5_calmar.iterrows():
        print(
            f"  {r['label']:>9}  CAGR={r['cagr']*100:6.2f}%  DD={r['max_drawdown']*100:6.2f}%  "
            f"Calmar={r['calmar']:5.2f}  Sharpe={r['sharpe']:5.2f}  "
            f"end=${r['end_$']/1e9:6.2f}B  rebals={int(r['rebalances']):>4}"
        )

    print(f"\nTop 5 by lowest |DD| with CAGR >= {BASELINE_CAGR*100:.2f}%:")
    if keep_cagr.empty:
        print("  (none found)")
    else:
        for _, r in keep_cagr.iterrows():
            print(
                f"  {r['label']:>9}  CAGR={r['cagr']*100:6.2f}%  DD={r['max_drawdown']*100:6.2f}%  "
                f"Calmar={r['calmar']:5.2f}  Sharpe={r['sharpe']:5.2f}  "
                f"end=${r['end_$']/1e9:6.2f}B"
            )

    print(f"\nPareto frontier ({len(pareto)} points, descending CAGR):")
    for _, r in pareto.iterrows():
        print(
            f"  {r['label']:>9}  CAGR={r['cagr']*100:6.2f}%  DD={r['max_drawdown']*100:6.2f}%  "
            f"Calmar={r['calmar']:5.2f}"
        )

    print(f"\nConfigs that DOMINATE the baseline (CAGR>={BASELINE_CAGR*100:.2f}% AND DD>{BASELINE_MAX_DD*100:.2f}%):")
    if dominated_baseline.empty:
        print("  (none — baseline is on the Pareto frontier)")
    else:
        for _, r in dominated_baseline.iterrows():
            print(
                f"  {r['label']:>9}  CAGR={r['cagr']*100:6.2f}%  DD={r['max_drawdown']*100:6.2f}%  "
                f"Calmar={r['calmar']:5.2f}"
            )

    def _fmt_dir(frame: pd.DataFrame) -> str:
        out = frame.copy()
        out["mean_cagr"] = out["mean_cagr"].map(lambda v: f"{v*100:6.2f}%")
        out["mean_dd"] = out["mean_dd"].map(lambda v: f"{v*100:6.2f}%")
        out["mean_calmar"] = out["mean_calmar"].map(lambda v: f"{v:5.2f}")
        return out.to_string()

    print("\nDirectional sensitivity (means across the other axis):")
    by_a = df.groupby("A_pct").agg(
        mean_cagr=("cagr", "mean"), mean_dd=("max_drawdown", "mean"), mean_calmar=("calmar", "mean")
    )
    print("  As A increases:")
    print(_fmt_dir(by_a))
    by_b = df.groupby("B_pct").agg(
        mean_cagr=("cagr", "mean"), mean_dd=("max_drawdown", "mean"), mean_calmar=("calmar", "mean")
    )
    print("\n  As B increases:")
    print(_fmt_dir(by_b))

    print(f"\nFiles written to {OUTPUT_DIR}:")
    for p in sorted(OUTPUT_DIR.iterdir()):
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
