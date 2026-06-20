"""
Parameter sweep: parallel tier SMA selection with SPX drawdown risk caps.

Explores flat caps (default max leverage until deep DD unlocks 3x), tiered caps
(A/B style), pick modes, SPX lead guard, min margin, and score-blend picks —
all under a risk cap.

Writes output/spx_parallel_risk_cap_sweep/
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_spx_parallel_tier_sma import (
    DEFAULT_SPEC,
    LEAD_PCT,
    SMA_WINDOW,
    _pick_best_margin,
    _pick_greedy_tier,
    _pick_momentum_score,
    _spx_recovery_guard,
    benchmark_prices_from_etp,
    download_spx_panel,
    leverage_stats,
    run_leverage_row,
    run_strategy,
    tier_margins,
)
from analyze_spx_parallel_tier_sma_extensions import (
    apply_cap_and_lead,
    pick_score_blend_greedy,
    tier_rolling_vol,
)
from etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_DIR = Path("output") / "spx_parallel_risk_cap_sweep"


def flat_risk_cap(prices: pd.DataFrame, *, default_cap: float, allow_3x_dd: float) -> pd.Series:
    close = prices["spx_close"].astype(float)
    dd = close / close.cummax() - 1.0
    cap = pd.Series(float(default_cap), index=prices.index)
    cap.loc[dd <= -allow_3x_dd] = 3.0
    return cap


def tiered_risk_cap(
    prices: pd.DataFrame,
    *,
    default_cap: float,
    trigger_a: float,
    trigger_b: float,
) -> pd.Series:
    close = prices["spx_close"].astype(float)
    dd = close / close.cummax() - 1.0
    cap = pd.Series(float(default_cap), index=prices.index)
    cap.loc[dd <= -trigger_a] = np.maximum(cap.loc[dd <= -trigger_a], 2.0)
    cap.loc[dd <= -trigger_b] = 3.0
    return cap


def pick_raw(
    mode: str,
    margins: pd.DataFrame,
    bench: pd.DataFrame,
    vols: pd.DataFrame | None = None,
    *,
    min_margin: float = 0.0,
    score_lambda: float | None = None,
) -> pd.Series:
    if mode == "greedy":
        return _pick_greedy_tier(margins, min_margin=min_margin)
    if mode == "best_margin":
        return _pick_best_margin(margins, min_margin=min_margin)
    if mode == "momentum":
        return _pick_momentum_score(bench)
    if mode == "score_blend":
        if vols is None or score_lambda is None:
            raise ValueError("score_blend requires vols and score_lambda")
        return pick_score_blend_greedy(margins, vols, score_lambda)
    raise ValueError(f"unknown mode: {mode}")


def run_config(
    prices: pd.DataFrame,
    bench: pd.DataFrame,
    etp: pd.DataFrame,
    margins: pd.DataFrame,
    vols: pd.DataFrame,
    *,
    cap: pd.Series,
    mode: str,
    use_spx_lead: bool,
    min_margin: float,
    score_lambda: float | None,
    label: str,
    meta: dict,
) -> dict:
    raw = pick_raw(
        mode,
        margins,
        bench,
        vols,
        min_margin=min_margin,
        score_lambda=score_lambda,
    )
    spx_ok = _spx_recovery_guard(prices) if use_spx_lead else pd.Series(True, index=prices.index)
    lev, extra = apply_cap_and_lead(raw, cap, spx_ok)
    return run_leverage_row(
        prices,
        lev,
        label,
        etp,
        {
            "family": "risk_cap_sweep",
            **leverage_stats(lev),
            **extra,
            **meta,
        },
    )


def pareto_frontier(df: pd.DataFrame) -> pd.DataFrame:
    """Non-dominated on CAGR, Sharpe (higher better), max_drawdown (less negative)."""
    rows = []
    for i, a in df.iterrows():
        dominated = False
        for j, b in df.iterrows():
            if i == j:
                continue
            if (
                b["cagr"] >= a["cagr"]
                and b["sharpe"] >= a["sharpe"]
                and b["max_drawdown"] >= a["max_drawdown"]
                and (
                    b["cagr"] > a["cagr"]
                    or b["sharpe"] > a["sharpe"]
                    or b["max_drawdown"] > a["max_drawdown"]
                )
            ):
                dominated = True
                break
        if not dominated:
            rows.append(a)
    return pd.DataFrame(rows).sort_values(["sharpe", "cagr"], ascending=False)


def write_strategy_plan(path: Path) -> None:
    path.write_text(
        """# Parallel tier SMA + risk cap sweep (SPX)

## Goal

Find parameter sets where **parallel tier SMA picking under a drawdown risk cap**
beats or matches default **Guarded A5/B25** on Sharpe and/or CAGR without
materially worse drawdown.

## Cap families

1. **Flat cap** — default max leverage (1x or 2x); allow 3x only when SPX DD <= threshold.
2. **Tiered cap** — default cap, then 2x when DD <= trigger_a, 3x when DD <= trigger_b
   (Guarded-style arming as a hard ceiling, not latched).

## Pick modes (all subject to cap + optional SPX 0.75% lead guard)

- greedy tier SMA
- best SMA margin
- 20d momentum
- score blend: margin_k - lambda * vol_k (under cap)

## Baselines

Guarded A5/B25, uncapped parallel greedy/best margin, prior best flat cap (2x / DD<=-25%).

Assumptions: SPX_ETP, $100 + $10/yr, 1% rebalance cost, 1996+ window.
""",
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_strategy_plan(OUTPUT_DIR / "strategy_plan.md")

    print("Downloading SPX panel...", flush=True)
    prices = download_spx_panel()
    etp = build_etp_return_panel(prices, SPX_ETP)
    bench = benchmark_prices_from_etp(etp)
    margins = tier_margins(bench)
    vols = tier_rolling_vol(bench)
    cov = etp_coverage_summary(etp)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days) | ETP real 2x/3x: {cov['pct_real_2x']}% / {cov['pct_real_3x']}%",
        flush=True,
    )

    rows: list[dict] = []

    # Baselines
    rows.append(run_strategy(prices, DEFAULT_SPEC, etp_returns=etp) | {"family": "baseline"})
    for mode, name in (("greedy", "Parallel greedy tier SMA"), ("best_margin", "Parallel best SMA margin")):
        raw = pick_raw(mode, margins, bench)
        lev, extra = apply_cap_and_lead(raw, pd.Series(3.0, index=prices.index), pd.Series(True, index=prices.index))
        rows.append(
            run_leverage_row(prices, lev, name, etp, {"family": "baseline", **leverage_stats(lev), **extra})
        )

    # Prior best flat cap reference
    cap_ref = flat_risk_cap(prices, default_cap=2.0, allow_3x_dd=0.25)
    for mode, tag in (("greedy", "greedy"), ("best_margin", "best margin")):
        rows.append(
            run_config(
                prices,
                bench,
                etp,
                margins,
                vols,
                cap=cap_ref,
                mode=mode,
                use_spx_lead=False,
                min_margin=0.0,
                score_lambda=None,
                label=f"Ref flat 2x cap / 3x if DD<=-25% + {tag}",
                meta={
                    "cap_type": "flat",
                    "default_cap": 2.0,
                    "allow_3x_dd": 0.25,
                    "mode": mode,
                    "use_spx_lead": False,
                    "min_margin": 0.0,
                },
            )
        )

    configs: list[dict] = []

    # Flat cap grid
    for default_cap, allow_3x_dd, mode, use_lead, min_m in product(
        [1.0, 2.0],
        [0.15, 0.20, 0.25, 0.30, 0.35],
        ["greedy", "best_margin", "momentum"],
        [False, True],
        [0.0, 0.005],
    ):
        configs.append(
            {
                "cap_type": "flat",
                "default_cap": default_cap,
                "allow_3x_dd": allow_3x_dd,
                "mode": mode,
                "use_spx_lead": use_lead,
                "min_margin": min_m,
                "score_lambda": None,
            }
        )

    # Tiered cap grid
    for default_cap, trigger_a, trigger_b, mode, use_lead in product(
        [1.0, 2.0],
        [0.05, 0.10, 0.15],
        [0.20, 0.25, 0.30],
        ["greedy", "best_margin", "momentum"],
        [False, True],
    ):
        if trigger_b <= trigger_a:
            continue
        configs.append(
            {
                "cap_type": "tiered",
                "default_cap": default_cap,
                "trigger_a": trigger_a,
                "trigger_b": trigger_b,
                "mode": mode,
                "use_spx_lead": use_lead,
                "min_margin": 0.0,
                "score_lambda": None,
            }
        )

    # Score blend under flat cap (focused grid)
    for allow_3x_dd, lam in product([0.20, 0.25, 0.30], [0.25, 0.5, 0.75, 1.0]):
        configs.append(
            {
                "cap_type": "flat",
                "default_cap": 2.0,
                "allow_3x_dd": allow_3x_dd,
                "mode": "score_blend",
                "use_spx_lead": False,
                "min_margin": 0.0,
                "score_lambda": lam,
            }
        )

    print(f"Running {len(configs)} risk-cap configs...", flush=True)
    for i, cfg in enumerate(configs, start=1):
        if cfg["cap_type"] == "flat":
            cap = flat_risk_cap(
                prices,
                default_cap=cfg["default_cap"],
                allow_3x_dd=cfg["allow_3x_dd"],
            )
            cap_desc = f"flat cap {cfg['default_cap']:.0f}x, 3x if DD<=-{cfg['allow_3x_dd']*100:.0f}%"
        else:
            cap = tiered_risk_cap(
                prices,
                default_cap=cfg["default_cap"],
                trigger_a=cfg["trigger_a"],
                trigger_b=cfg["trigger_b"],
            )
            cap_desc = (
                f"tiered cap base {cfg['default_cap']:.0f}x, "
                f"2x@<=-{cfg['trigger_a']*100:.0f}%, 3x@<=-{cfg['trigger_b']*100:.0f}%"
            )

        mode = cfg["mode"]
        mode_desc = mode if mode != "score_blend" else f"score_blend λ={cfg['score_lambda']}"
        lead_tag = " + SPX lead" if cfg["use_spx_lead"] else ""
        min_tag = f" min_m={cfg['min_margin']*100:.1f}%" if cfg["min_margin"] > 0 else ""
        label = f"{cap_desc} + {mode_desc}{lead_tag}{min_tag}"

        rows.append(
            run_config(
                prices,
                bench,
                etp,
                margins,
                vols,
                cap=cap,
                mode=mode,
                use_spx_lead=cfg["use_spx_lead"],
                min_margin=cfg["min_margin"],
                score_lambda=cfg.get("score_lambda"),
                label=label,
                meta=cfg,
            )
        )
        if i % 50 == 0:
            print(f"  ... {i}/{len(configs)}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    guarded = df[df["strategy"] == DEFAULT_SPEC["strategy"]].iloc[0]
    sweep = df[df["family"] == "risk_cap_sweep"].copy()

    # Candidates that improve on Guarded
    beats_sharpe = sweep[sweep["sharpe"] > guarded["sharpe"]].sort_values("sharpe", ascending=False)
    beats_cagr = sweep[sweep["cagr"] > guarded["cagr"]].sort_values("cagr", ascending=False)
    beats_both = sweep[(sweep["sharpe"] > guarded["sharpe"]) & (sweep["cagr"] > guarded["cagr"])].sort_values(
        "sharpe", ascending=False
    )
    similar_dd_better_sharpe = sweep[
        (sweep["sharpe"] > guarded["sharpe"]) & (sweep["max_drawdown"] >= guarded["max_drawdown"] - 0.05)
    ].sort_values("sharpe", ascending=False)

    pareto = pareto_frontier(sweep)
    pareto.to_csv(OUTPUT_DIR / "pareto_frontier.csv", index=False)
    beats_sharpe.head(25).to_csv(OUTPUT_DIR / "ranked_beats_sharpe.csv", index=False)
    beats_cagr.head(25).to_csv(OUTPUT_DIR / "ranked_beats_cagr.csv", index=False)
    beats_both.head(25).to_csv(OUTPUT_DIR / "ranked_beats_both.csv", index=False)
    similar_dd_better_sharpe.head(25).to_csv(OUTPUT_DIR / "ranked_similar_dd_better_sharpe.csv", index=False)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "etp_coverage": cov,
        "config_count": len(configs),
        "guarded_baseline": guarded.to_dict(),
        "counts": {
            "beats_sharpe": int(len(beats_sharpe)),
            "beats_cagr": int(len(beats_cagr)),
            "beats_both": int(len(beats_both)),
            "similar_dd_better_sharpe": int(len(similar_dd_better_sharpe)),
            "pareto_frontier": int(len(pareto)),
        },
        "best_beats_both": beats_both.head(10).to_dict(orient="records"),
        "best_similar_dd_sharpe": similar_dd_better_sharpe.head(10).to_dict(orient="records"),
        "best_sharpe_overall": sweep.sort_values("sharpe", ascending=False).head(10).to_dict(orient="records"),
        "best_cagr_overall": sweep.sort_values("cagr", ascending=False).head(10).to_dict(orient="records"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    def print_table(sub: pd.DataFrame, title: str, n: int = 8) -> None:
        print(f"\n=== {title} ===")
        if sub.empty:
            print("  (none)")
            return
        for _, r in sub.head(n).iterrows():
            print(
                f"  {str(r['strategy'])[:58]:58}  "
                f"CAGR {r['cagr']*100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
                f"MaxDD {r['max_drawdown']*100:6.2f}%  End ${r['end_$']:,.0f}  "
                f"Rebal {int(r['rebalances']):4d}"
            )

    print(
        f"\nGuarded baseline: CAGR {guarded['cagr']*100:.2f}%  Sharpe {guarded['sharpe']:.2f}  "
        f"MaxDD {guarded['max_drawdown']*100:.2f}%  End ${guarded['end_$']:,.0f}",
        flush=True,
    )
    print_table(beats_both, f"Beat Guarded on Sharpe AND CAGR ({len(beats_both)} configs)")
    print_table(similar_dd_better_sharpe, f"Beat Sharpe with MaxDD within 5pp of Guarded ({len(similar_dd_better_sharpe)})")
    print_table(beats_sharpe, f"Beat Sharpe only ({len(beats_sharpe)} configs)")
    print_table(sweep.sort_values("cagr", ascending=False), "Top CAGR in sweep")

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
