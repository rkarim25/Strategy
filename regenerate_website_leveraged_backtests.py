"""
Regenerate all website backtests that use 2x/3x with listed ETP daily returns.

Run from repo root: python regenerate_website_leveraged_backtests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS: list[tuple[str, list[str]]] = [
    ("S&P Guarded site JSON + ETP returns", [sys.executable, "backtest_spx_guarded.py"]),
    ("Nasdaq Guarded site JSON + ETP returns", [sys.executable, "backtest_ndx_guarded.py"]),
    ("Guarded balanced candidate (SPX)", [sys.executable, "test_guarded_balanced_candidate.py"]),
    ("Momentum leverage table (index.html)", [sys.executable, "backtest_momentum_leverage_strategies.py"]),
    ("Long-hold momentum table (index.html)", [sys.executable, "backtest_long_hold_momentum_strategies.py"]),
    ("Guarded tiered SMA20/50/200 tables", [sys.executable, "backtest_guarded_tiered_sma20_50_200.py"]),
    ("Tiered SMA chart JSON", [sys.executable, "generate_guarded_tiered_chart_data.py"]),
    ("Patch index.html static tables", [sys.executable, "patch_index_html_backtests.py"]),
]

# After regeneration, refresh: index.html, ndx_guarded_site_data.json, spx_guarded_site_data.json,
# spx_etp_returns.json, ndx_etp_returns.json, and CSVs under output/.


def main() -> int:
    for label, cmd in STEPS:
        print(f"\n=== {label} ===", flush=True)
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            print(f"FAILED: {' '.join(cmd)}", flush=True)
            return result.returncode
    print("\nAll website leveraged backtests regenerated.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
