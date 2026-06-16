"""Triple-check validation for LQQ3.L Guarded max 1x (real data since 2012-12-13).

Tests:
  1. Re-run backtest matches stored summary.json (within tolerance)
  2. Duplicate engine runs produce identical equity
  3. Leverage series is binary 0/1 only (max 1x cap)
  4. Block-bootstrap CI on full-sample CAGR / max DD
  5. Cost sensitivity (0%, 1%, 2% rebalance cost)
  6. Sub-period stability (2012-2018 vs 2018-present)
  7. Guarded beats buy-and-hold on Sharpe and max DD

Outputs to output/lqq3_guarded_validation/ — does not modify website files.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "lqq3_guarded_validation"
SUMMARY_PATH = ROOT / "output" / "lqq3_guarded" / "summary.json"

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from backtest_lqq3_guarded import (
    LQQ3_START,
    LQQ3_TICKER,
    buy_hold_row,
    download_panel,
    lqq3_site_comparison,
    run_guarded_1x,
    sma_row,
)
from engine import TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

BOOTSTRAP_N = 500
BOOTSTRAP_BLOCK = 21
BOOTSTRAP_SEED = 20260604


def make_engine(cost: float) -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=cost,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def test_rerun_matches_summary(prices: pd.DataFrame, stored: dict) -> dict:
    rows = lqq3_site_comparison(prices)
    guarded = rows[2]
    stored_g = stored["lqq3"]["site_strategies"][2] if "site_strategies" in stored["lqq3"] else None
    if stored_g is None:
        stored_rows = [r for r in stored["lqq3"]["strategies"] if "Guarded" in r["strategy"]]
        stored_g = stored_rows[0]

    tol = 1e-6
    checks = {
        "cagr_match": abs(guarded["cagr"] - stored_g["cagr"]) < tol,
        "sharpe_match": abs(guarded["sharpe"] - stored_g["sharpe"]) < tol,
        "max_dd_match": abs(guarded["max_drawdown"] - stored_g["max_drawdown"]) < tol,
        "end_match": abs(guarded["end_$"] - stored_g["end_$"]) < 1.0,
    }
    return {
        "test": "rerun_vs_summary",
        "pass": all(checks.values()),
        "fresh": guarded,
        "stored": {k: stored_g[k] for k in ("cagr", "sharpe", "max_drawdown", "end_$")},
        "checks": checks,
    }


def test_duplicate_engine(prices: pd.DataFrame) -> dict:
    a = run_guarded_1x(prices)
    b = run_guarded_1x(prices)
    return {
        "test": "duplicate_engine",
        "pass": a["end_$"] == b["end_$"] and a["cagr"] == b["cagr"],
        "end_a": a["end_$"],
        "end_b": b["end_$"],
    }


def test_leverage_binary(prices: pd.DataFrame) -> dict:
    lev, _ = guarded_lead_leverage(prices, max_leverage=1.0)
    unique = sorted(set(float(x) for x in lev.unique()))
    ok = all(x in (0.0, 1.0) for x in unique)
    return {"test": "leverage_binary_0_1", "pass": ok, "unique_levels": unique}


def test_bootstrap_ci(prices: pd.DataFrame) -> dict:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    n = len(prices)
    starts = np.arange(1, n - BOOTSTRAP_BLOCK + 1)
    cagrs: list[float] = []
    dds: list[float] = []
    for _ in range(BOOTSTRAP_N):
        idx_parts: list[np.ndarray] = []
        while sum(len(x) for x in idx_parts) < n:
            s = int(rng.choice(starts))
            idx_parts.append(np.arange(s, s + BOOTSTRAP_BLOCK))
        idx = np.concatenate(idx_parts)[:n]
        path = pd.DataFrame(
            {
                "spx_close": 1000.0 * np.cumprod(1.0 + ret[idx]),
                "tbill_rate": tbill[idx],
            },
            index=prices.index,
        )
        row = run_guarded_1x(path)
        cagrs.append(row["cagr"])
        dds.append(row["max_drawdown"])
    cagrs_a = np.array(cagrs)
    dds_a = np.array(dds)
    full = run_guarded_1x(prices)
    return {
        "test": "block_bootstrap_ci",
        "pass": bool(
            float(np.quantile(cagrs_a, 0.05)) < full["cagr"] < float(np.quantile(cagrs_a, 0.95))
        ),
        "n_sims": BOOTSTRAP_N,
        "full_cagr": full["cagr"],
        "cagr_p5": float(np.quantile(cagrs_a, 0.05)),
        "cagr_p50": float(np.quantile(cagrs_a, 0.50)),
        "cagr_p95": float(np.quantile(cagrs_a, 0.95)),
        "dd_p5": float(np.quantile(dds_a, 0.05)),
        "dd_p50": float(np.quantile(dds_a, 0.50)),
        "dd_p95": float(np.quantile(dds_a, 0.95)),
    }


def test_cost_sensitivity(prices: pd.DataFrame) -> dict:
    rows = []
    for cost in (0.0, TRADING_COST_FROM_MID_PCT, 0.02):
        row = run_guarded_1x(prices, trading_cost_pct=cost)
        rows.append({"cost_pct": cost, "cagr": row["cagr"], "end_$": row["end_$"]})
    monotonic = rows[0]["end_$"] >= rows[1]["end_$"] >= rows[2]["end_$"]
    return {"test": "cost_sensitivity", "pass": monotonic, "rows": rows}


def test_subperiods(prices: pd.DataFrame) -> dict:
    split = pd.Timestamp("2018-01-01")
    early = prices.loc[prices.index < split]
    late = prices.loc[prices.index >= split]
    early_g = run_guarded_1x(early)
    late_g = run_guarded_1x(late)
    return {
        "test": "subperiod_stability",
        "pass": early_g["sharpe"] > 0 and late_g["sharpe"] > 0,
        "early": {
            "start": str(early.index[0].date()),
            "end": str(early.index[-1].date()),
            "cagr": early_g["cagr"],
            "sharpe": early_g["sharpe"],
            "max_dd": early_g["max_drawdown"],
        },
        "late": {
            "start": str(late.index[0].date()),
            "end": str(late.index[-1].date()),
            "cagr": late_g["cagr"],
            "sharpe": late_g["sharpe"],
            "max_dd": late_g["max_drawdown"],
        },
    }


def test_vs_buyhold(prices: pd.DataFrame) -> dict:
    bh = buy_hold_row(prices)
    guarded = run_guarded_1x(prices)
    sma = sma_row(prices)
    return {
        "test": "guarded_vs_buyhold",
        "pass": guarded["sharpe"] > bh["sharpe"] and guarded["max_drawdown"] > bh["max_drawdown"],
        "bh_sharpe": bh["sharpe"],
        "guarded_sharpe": guarded["sharpe"],
        "bh_max_dd": bh["max_drawdown"],
        "guarded_max_dd": guarded["max_drawdown"],
        "guarded_cagr": guarded["cagr"],
        "sma_cagr": sma["cagr"],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Loading {LQQ3_TICKER} from {LQQ3_START}...", flush=True)
    prices = download_panel(LQQ3_TICKER, start=LQQ3_START)

    stored = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")) if SUMMARY_PATH.exists() else {}

    tests = [
        test_rerun_matches_summary(prices, stored) if stored else {"test": "rerun_vs_summary", "pass": True, "skipped": True},
        test_duplicate_engine(prices),
        test_leverage_binary(prices),
        test_bootstrap_ci(prices),
        test_cost_sensitivity(prices),
        test_subperiods(prices),
        test_vs_buyhold(prices),
    ]

    all_pass = all(t.get("pass", False) for t in tests)
    report = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": LQQ3_TICKER,
        "start": str(prices.index[0].date()),
        "end": str(prices.index[-1].date()),
        "days": len(prices),
        "all_pass": all_pass,
        "tests": tests,
    }
    (OUT / "validation_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    lines = ["# LQQ3 Guarded max 1x — validation report", ""]
    for t in tests:
        status = "PASS" if t.get("pass") else "FAIL"
        lines.append(f"- **{t['test']}**: {status}")
    lines.append("")
    lines.append(f"**Overall: {'PASS' if all_pass else 'FAIL'}**")
    (OUT / "final_verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n=== Validation ===")
    for t in tests:
        print(f"  {t['test']}: {'PASS' if t.get('pass') else 'FAIL'}")
    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print(f"Wrote {OUT}/")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
