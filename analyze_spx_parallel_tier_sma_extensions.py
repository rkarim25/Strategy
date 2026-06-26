"""
Extended parallel tier SMA variants for SPX (1996+).

Variants:
  1. Hybrid — latched Guarded DD arming + parallel tier SMA pick (no +X% exit)
  2. Risk cap — parallel pick capped at 2x unless SPX DD <= -25%
  3. Hysteresis — 2/3-day confirmation before tier switch
  4. Score blend — margin_k - lambda * vol_k (20d rolling daily return std)

Writes output/spx_parallel_tier_sma_extensions/
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyze_spx_ndx_rotation_guarded import apply_hysteresis
from analyze_spx_parallel_tier_sma import (
    DEFAULT_SPEC,
    LEAD_PCT,
    SMA_WINDOW,
    TRIGGER_A,
    TRIGGER_B,
    _pick_best_margin,
    _pick_greedy_tier,
    _spx_recovery_guard,
    benchmark_prices_from_etp,
    download_spx_panel,
    leverage_stats,
    run_leverage_row,
    run_strategy,
    tier_margins,
)
from core.etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_DIR = Path("output") / "spx_parallel_tier_sma_extensions"


def guarded_latched_dd_cap(prices: pd.DataFrame) -> pd.Series:
    """Latched A5/B25 arming: disarm when DD recovers above trigger (no +X% exit)."""
    close = prices["spx_close"].astype(float)
    dd = close / close.cummax() - 1.0
    cap = pd.Series(1.0, index=prices.index)
    armed_2 = False
    armed_3 = False

    for dt in prices.index:
        d = float(dd.loc[dt])
        if d <= -TRIGGER_B:
            armed_3 = True
        if d <= -TRIGGER_A:
            armed_2 = True

        if d > -TRIGGER_A:
            armed_2 = False
            armed_3 = False
        elif d > -TRIGGER_B:
            armed_3 = False

        if armed_3:
            cap.loc[dt] = 3.0
        elif armed_2:
            cap.loc[dt] = 2.0
        else:
            cap.loc[dt] = 1.0

    return cap


def risk_cap_2x_unless_dd25(prices: pd.DataFrame) -> pd.Series:
    """Max 2x unless SPX drawdown <= -25%, then allow 3x."""
    close = prices["spx_close"].astype(float)
    dd = close / close.cummax() - 1.0
    cap = pd.Series(2.0, index=prices.index)
    cap.loc[dd <= -TRIGGER_B] = 3.0
    return cap


def tier_rolling_vol(bench: pd.DataFrame, window: int = SMA_WINDOW) -> pd.DataFrame:
    """Rolling window std of tier benchmark daily returns (not annualized)."""
    vols = pd.DataFrame(index=bench.index)
    for tier, col in ((1, "p_1x"), (2, "p_2x"), (3, "p_3x")):
        ret = bench[col].astype(float).pct_change()
        vols[f"vol_{tier}x"] = ret.rolling(window, min_periods=window).std()
    return vols


def pick_score_blend_greedy(
    margins: pd.DataFrame,
    vols: pd.DataFrame,
    lam: float,
    *,
    max_lev: float = 3.0,
) -> pd.Series:
    """Highest tier k with score_k = margin_k - lam * vol_k > 0."""
    lev = pd.Series(0.0, index=margins.index)
    for dt in margins.index:
        chosen = 0.0
        for tier in (3, 2, 1):
            if tier > max_lev:
                continue
            m = margins.loc[dt, f"m_{tier}x"]
            v = vols.loc[dt, f"vol_{tier}x"]
            if pd.isna(m) or pd.isna(v):
                continue
            score = float(m) - lam * float(v)
            if score > 0:
                chosen = float(tier)
                break
        lev.loc[dt] = chosen
    return lev


def apply_cap_and_lead(
    raw: pd.Series,
    cap: pd.Series,
    spx_ok: pd.Series,
) -> tuple[pd.Series, dict[str, int]]:
    lev = pd.Series(0.0, index=raw.index)
    capped = 0
    lead_blocked = 0
    for dt in raw.index:
        target = float(raw.loc[dt])
        if not bool(spx_ok.loc[dt]):
            if target > 0:
                lead_blocked += 1
            lev.loc[dt] = 0.0
            continue
        c = float(cap.loc[dt])
        if target > c:
            capped += 1
            target = c
        lev.loc[dt] = target
    return lev, {"dd_cap_days": capped, "lead_blocked_days": lead_blocked}


def tier_native_3x_lead(prices: pd.DataFrame, bench: pd.DataFrame) -> pd.Series:
    p3 = bench["p_3x"].astype(float)
    sma3 = p3.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    lev = pd.Series(0.0, index=prices.index)
    lev.loc[p3 >= sma3 * (1.0 - LEAD_PCT)] = 3.0
    return lev


def run_baseline_parallel(prices, bench, etp, mode: str) -> dict:
    margins = tier_margins(bench)
    if mode == "greedy":
        raw = _pick_greedy_tier(margins)
    else:
        raw = _pick_best_margin(margins)
    lev, extra = apply_cap_and_lead(raw, pd.Series(3.0, index=prices.index), pd.Series(True, index=prices.index))
    label = "Parallel greedy tier SMA" if mode == "greedy" else "Parallel best SMA margin"
    return run_leverage_row(prices, lev, label, etp, {"family": "baseline", **leverage_stats(lev), **extra})


def write_strategy_plan(path: Path) -> None:
    path.write_text(
        """# Parallel tier SMA extensions (SPX)

## 1. Hybrid (latched Guarded arming + parallel pick)

SPX drawdown **arms** max allowed tier (latched until DD recovers):
- Base: max 1x
- DD <= -5% (A): arms tier-2 cap (max 2x) until DD > -5%
- DD <= -25% (B): arms tier-3 cap (max 3x) until DD > -25% (or -5% for full disarm)

**No fixed +40% / +15% recovery exit.** Within the cap, pick tier via parallel
SMA on 1x/2x/3x ETP benchmarks (greedy or best margin). Optional SPX 0.75% lead guard.

## 2. Risk cap

Parallel greedy / best-margin pick, but **hard cap at 2x** unless SPX DD <= -25%
(only then allow 3x).

## 3. Hysteresis

Raw parallel greedy or best-margin signal must persist **2 or 3 consecutive days**
before switching tier (reduces whipsaw / rebalance count).

## 4. Score blend

Greedy pick on `score_k = margin_k - lambda * vol_k` where `vol_k` is 20-day
rolling stdev of tier benchmark daily returns. Test lambda in {0.5, 1.0, 2.0};
tier chosen only if score > 0.

## Baselines (same window)

- Guarded A5/B25 SMA20 Lead (default)
- Parallel greedy / best margin (uncapped)
- 3x tier-native lead (3x benchmark >= SMA20 - 0.75%)

Assumptions: SPX_ETP P&L, $100 start, $10/yr inflow, 1% rebalance cost.
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

    # --- Baselines ---
    rows.append(run_strategy(prices, DEFAULT_SPEC, etp_returns=etp) | {"family": "baseline"})
    rows.append(run_baseline_parallel(prices, bench, etp, "greedy"))
    rows.append(run_baseline_parallel(prices, bench, etp, "best_margin"))

    lev_3x = tier_native_3x_lead(prices, bench)
    rows.append(
        run_leverage_row(
            prices,
            lev_3x,
            "3x tier-native lead (3x benchmark >= SMA20 - 0.75%)",
            etp,
            {"family": "baseline", **leverage_stats(lev_3x)},
        )
    )

    latched_cap = guarded_latched_dd_cap(prices)
    risk_cap = risk_cap_2x_unless_dd25(prices)
    spx_ok = _spx_recovery_guard(prices)
    spx_ok_off = pd.Series(True, index=prices.index)

    # --- 1. Hybrid ---
    for mode, tag in (("greedy", "greedy"), ("best_margin", "best margin")):
        raw = _pick_greedy_tier(margins) if mode == "greedy" else _pick_best_margin(margins)
        for use_lead, lead_tag in ((False, ""), (True, " + SPX lead")):
            lev, extra = apply_cap_and_lead(raw, latched_cap, spx_ok if use_lead else spx_ok_off)
            name = f"Hybrid latched DD + parallel {tag}{lead_tag}"
            rows.append(
                run_leverage_row(
                    prices,
                    lev,
                    name,
                    etp,
                    {"family": "hybrid", "variant": "hybrid", **leverage_stats(lev), **extra},
                )
            )

    # --- 2. Risk cap ---
    for mode, tag in (("greedy", "greedy"), ("best_margin", "best margin")):
        raw = _pick_greedy_tier(margins) if mode == "greedy" else _pick_best_margin(margins)
        lev, extra = apply_cap_and_lead(raw, risk_cap, spx_ok_off)
        rows.append(
            run_leverage_row(
                prices,
                lev,
                f"Risk cap 2x (3x if DD<=-25%) + parallel {tag}",
                etp,
                {"family": "risk_cap", "variant": "risk_cap", **leverage_stats(lev), **extra},
            )
        )

    # --- 3. Hysteresis ---
    for mode, tag in (("greedy", "greedy"), ("best_margin", "best margin")):
        raw = _pick_greedy_tier(margins) if mode == "greedy" else _pick_best_margin(margins)
        for confirm in (2, 3):
            hyst = apply_hysteresis(raw, confirm).astype(float)
            lev, extra = apply_cap_and_lead(hyst, pd.Series(3.0, index=prices.index), spx_ok_off)
            rows.append(
                run_leverage_row(
                    prices,
                    lev,
                    f"Hysteresis {confirm}d + parallel {tag}",
                    etp,
                    {
                        "family": "hysteresis",
                        "variant": "hysteresis",
                        "confirm_days": confirm,
                        **leverage_stats(lev),
                        **extra,
                    },
                )
            )

    # --- 4. Score blend ---
    for lam in (0.5, 1.0, 2.0):
        raw = pick_score_blend_greedy(margins, vols, lam)
        lev, extra = apply_cap_and_lead(raw, pd.Series(3.0, index=prices.index), spx_ok_off)
        rows.append(
            run_leverage_row(
                prices,
                lev,
                f"Score blend greedy (lambda={lam})",
                etp,
                {"family": "score_blend", "variant": "score_blend", "lambda": lam, **leverage_stats(lev), **extra},
            )
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    new_variants = df[df["family"].isin(["hybrid", "risk_cap", "hysteresis", "score_blend"])].copy()

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "etp_coverage": cov,
        "new_variant_count": len(new_variants),
        "top_sharpe": new_variants.sort_values("sharpe", ascending=False).head(10).to_dict(orient="records"),
        "top_cagr": new_variants.sort_values("cagr", ascending=False).head(10).to_dict(orient="records"),
        "all_results": rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    def print_table(sub: pd.DataFrame, title: str) -> None:
        print(f"\n=== {title} ===")
        for _, r in sub.iterrows():
            print(
                f"  {str(r['strategy'])[:52]:52}  "
                f"CAGR {r['cagr']*100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
                f"MaxDD {r['max_drawdown']*100:6.2f}%  End ${r['end_$']:,.0f}  "
                f"Rebal {int(r['rebalances']):4d}  3x {r.get('pct_days_3x', 0):5.1f}%"
            )

    print_table(new_variants.sort_values("sharpe", ascending=False), "New variants by Sharpe")
    print_table(new_variants.sort_values("cagr", ascending=False), "New variants by CAGR")

    baselines = df[df["family"] == "baseline"]
    print_table(baselines.sort_values("sharpe", ascending=False), "Baselines")

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
