"""Merge B1-B4 strategy entries from output/summary_new_strategies.json into summary_data.json.

Reads the existing summary_data.json, adds the 4 new strategy rows to spx under
all 3 regimes (real, synth_era, synth_long), and writes back. Preserves all
existing entries and metadata unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUMMARY_JSON = ROOT / "summary_data.json"
NEW_JSON = ROOT / "output" / "summary_new_strategies.json"

# Strategy keys to add (in order)
NEW_STRATEGY_NAMES = [
    "SMA200 ±3% Band + RSI>30 Exit 3x",
    "SMA200 ±3% Band + RSI>30 Exit 2x",
    "SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x",
    "SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x",
]

REGIMES = ["real", "synth_era", "synth_long"]


def main() -> None:
    # Load existing summary data
    print(f"Loading {SUMMARY_JSON}...")
    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        summary = json.load(f)
    
    # Load new strategy data
    print(f"Loading {NEW_JSON}...")
    with open(NEW_JSON, "r", encoding="utf-8") as f:
        new_data = json.load(f)
    
    # Find the spx asset in both
    spx_asset = None
    for asset in summary["assets"]:
        if asset["key"] == "spx":
            spx_asset = asset
            break
    
    if spx_asset is None:
        raise ValueError("spx asset not found in summary_data.json")
    
    new_spx = new_data["assets"][0]  # The new data only has spx
    
    # Merge rows into each regime
    for regime in REGIMES:
        existing_rows = spx_asset[regime]["rows"]
        new_rows = new_spx[regime]["rows"]
        
        for name in NEW_STRATEGY_NAMES:
            if name in existing_rows:
                print(f"  WARNING: '{name}' already exists in {regime}, overwriting...")
            existing_rows[name] = new_rows[name]
            print(f"  Added '{name}' to spx.{regime}")
    
    # Update generated timestamp
    from datetime import datetime
    summary["generated"] = datetime.now().isoformat()
    
    # Write back
    print(f"\nWriting updated {SUMMARY_JSON}...")
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")
    
    # Validate
    print("Validating...")
    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        validated = json.load(f)
    
    spx_validated = None
    for asset in validated["assets"]:
        if asset["key"] == "spx":
            spx_validated = asset
            break
    
    for regime in REGIMES:
        rows = spx_validated[regime]["rows"]
        for name in NEW_STRATEGY_NAMES:
            assert name in rows, f"MISSING: {name} in {regime}"
            row = rows[name]
            # Check required fields
            for field in ["cagr_g", "dd_g", "vol", "sharpe", "sortino", "calmar", 
                          "cash", "trades_yr", "end", "cagr_r", "dd_r", "cagr_x", "dd_x"]:
                assert field in row, f"MISSING field '{field}' in {name} ({regime})"
        print(f"  {regime}: {len(rows)} strategies (added {len(NEW_STRATEGY_NAMES)} new)")
    
    print("\nMerge complete and validated.")
    print(f"Total spx strategies per regime: {len(spx_validated['real']['rows'])}")


if __name__ == "__main__":
    main()
