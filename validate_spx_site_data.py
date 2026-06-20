"""Validate website spx_guarded_site_data.json against independent sweep results."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SITE_JSON = ROOT / "spx_guarded_site_data.json"
SWEEP_CSV = ROOT / "output" / "spx_strategy_sweep" / "spx_sweep_results.csv"


def main() -> None:
    # Load website data
    site = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    sweep = pd.read_csv(SWEEP_CSV)

    print("=" * 80)
    print("CROSS-VALIDATION: Website (spx_guarded_site_data.json) vs Independent Sweep")
    print("=" * 80)

    # Map website strategy names to sweep names
    mapping = {
        "Buy & hold 1x": "Buy & Hold 1x",
        "Buy & hold 2x": "Buy & Hold 2x",
        "Buy & hold 3x": "Buy & Hold 3x",
        "SMA20 1x/cash": None,  # Not in sweep (sweep only tested 2x/3x SMA cash)
        "SMA20 2x/cash": "SMA20 Cash/2x",
        "SMA20 3x/cash": "SMA20 Cash/3x",
        "Guarded A5/B25 SMA20 Lead": "Guarded A5/B25/X40/Y15 (current)",
        "Original Guarded A10/B20 SMA20": None,  # Not in sweep
    }

    print(f"\n{'Strategy':<40} {'Metric':<12} {'Website':>10} {'Sweep':>10} {'Delta':>10} {'Match':>6}")
    print("-" * 90)

    all_ok = True
    for site_row in site["comparison_table"]:
        name = site_row["strategy"]
        sweep_name = mapping.get(name)
        if sweep_name is None:
            continue

        sweep_row = sweep[sweep["strategy"] == sweep_name]
        if sweep_row.empty:
            print(f"  {name:<38} NOT FOUND in sweep")
            all_ok = False
            continue

        sr = sweep_row.iloc[0]

        checks = [
            ("CAGR", site_row["cagr"], sr["cagr"], 0.005),  # 0.5% tolerance
            ("MaxDD", site_row["max_drawdown"], sr["max_drawdown"], 0.02),  # 2% tolerance
            ("Sharpe", site_row["sharpe"], sr["sharpe"], 0.03),
            ("Rebal", site_row["rebalances"], sr["rebalances"], 5),
        ]

        for metric, site_val, sweep_val, tol in checks:
            delta = abs(site_val - sweep_val)
            rel_delta = delta / max(abs(site_val), 1e-9) if site_val != 0 else delta
            ok = delta <= tol or rel_delta <= 0.02
            flag = "OK" if ok else "MISMATCH"
            if not ok:
                all_ok = False
            print(f"  {name:<38} {metric:<12} {site_val:>10.4f} {sweep_val:>10.4f} {delta:>10.4f} {flag:>6}")

    # Also check default_backtest vs comparison_table for Guarded
    print(f"\n{'=' * 80}")
    print("INTERNAL CONSISTENCY: default_backtest vs comparison_table (Guarded)")
    print(f"{'=' * 80}")
    db = site["default_backtest"]
    ct_guarded = next(r for r in site["comparison_table"] if r["strategy"] == "Guarded A5/B25 SMA20 Lead")
    internal_checks = [
        ("CAGR", db["cagr"], ct_guarded["cagr"]),
        ("MaxDD", db["max_drawdown"], ct_guarded["max_drawdown"]),
        ("Sharpe", db["sharpe"], ct_guarded["sharpe"]),
        ("Rebal", db["rebalances"], ct_guarded["rebalances"]),
    ]
    for metric, v1, v2 in internal_checks:
        delta = abs(v1 - v2)
        flag = "OK" if delta < 1e-9 else "MISMATCH"
        if delta >= 1e-9:
            all_ok = False
        print(f"  {metric:<12} default_backtest={v1:.6f}  comparison_table={v2:.6f}  delta={delta:.2e}  {flag}")

    # Check buy_and_hold_1x vs comparison_table
    print(f"\n{'=' * 80}")
    print("INTERNAL CONSISTENCY: buy_and_hold_1x vs comparison_table")
    print(f"{'=' * 80}")
    bh = site["buy_and_hold_1x"]
    ct_bh = next(r for r in site["comparison_table"] if r["strategy"] == "Buy & hold 1x")
    for metric in ["cagr", "max_drawdown", "sharpe", "end_$", "rebalances"]:
        v1 = bh[metric]
        v2 = ct_bh[metric]
        delta = abs(v1 - v2)
        flag = "OK" if delta < 1e-9 else "MISMATCH"
        if delta >= 1e-9:
            all_ok = False
        print(f"  {metric:<12} buy_and_hold={v1:.6f}  comparison_table={v2:.6f}  delta={delta:.2e}  {flag}")

    # Check original_guarded vs comparison_table
    print(f"\n{'=' * 80}")
    print("INTERNAL CONSISTENCY: original_guarded vs comparison_table")
    print(f"{'=' * 80}")
    og = site["original_guarded"]
    ct_og = next(r for r in site["comparison_table"] if r["strategy"] == "Original Guarded A10/B20 SMA20")
    for metric in ["cagr", "max_drawdown", "sharpe", "end_$", "rebalances"]:
        v1 = og[metric]
        v2 = ct_og[metric]
        delta = abs(v1 - v2)
        flag = "OK" if delta < 1e-9 else "MISMATCH"
        if delta >= 1e-9:
            all_ok = False
        print(f"  {metric:<12} original_guarded={v1:.6f}  comparison_table={v2:.6f}  delta={delta:.2e}  {flag}")

    # Check sample dates
    print(f"\n{'=' * 80}")
    print("DATA WINDOW CHECK")
    print(f"{'=' * 80}")
    print(f"  Website start: {site['sample']['start_date']}")
    print(f"  Website end:   {site['sample']['end_date']}")
    print(f"  Trading days:  {site['sample']['trading_days']}")
    print(f"  Sweep days:    7549")
    print(f"  Generated UTC: {site['generated_at_utc']}")

    # Check Monte Carlo probabilities sanity
    print(f"\n{'=' * 80}")
    print("MONTE CARLO SANITY CHECKS")
    print(f"{'=' * 80}")
    mc = site["monte_carlo"]
    print(f"  N sims: {mc['n_sims']}, horizon: {mc['horizon_years']}y, block: {mc['block_days']}d")
    print(f"  Median CAGR: {mc['median_cagr_pct']}  (P10: {mc['p10_cagr_pct']}, P90: {mc['p90_cagr_pct']})")
    print(f"  Median MaxDD: {mc['median_max_drawdown_pct']}")
    print(f"  Prob(DD > -35%): {mc['prob_max_dd_worse_35pct_fmt']}")
    print(f"  Prob(DD > -40%): {mc['prob_max_dd_worse_40pct_fmt']}")
    print(f"  Prob(DD > -50%): {mc['prob_max_dd_worse_50pct_fmt']}")
    print(f"  Prob(end < start): {mc['prob_end_below_start_fmt']}")

    # Sanity: probabilities should be monotonic
    p35 = mc["prob_max_dd_worse_35pct"]
    p40 = mc["prob_max_dd_worse_40pct"]
    p50 = mc["prob_max_dd_worse_50pct"]
    if p35 >= p40 >= p50:
        print(f"  Monotonicity check: OK (P35={p35:.2f} >= P40={p40:.2f} >= P50={p50:.2f})")
    else:
        print(f"  Monotonicity check: FAIL — probabilities not decreasing!")
        all_ok = False

    # ETP coverage
    print(f"\n{'=' * 80}")
    print("ETP COVERAGE")
    print(f"{'=' * 80}")
    cov = site["etp_coverage"]
    print(f"  Real 2x ETP coverage: {cov['pct_real_2x']}%")
    print(f"  Real 3x ETP coverage: {cov['pct_real_3x']}%")

    print(f"\n{'=' * 80}")
    if all_ok:
        print("VERDICT: ALL CHECKS PASSED — Website data is consistent and correct.")
    else:
        print("VERDICT: SOME MISMATCHES FOUND — see details above.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
