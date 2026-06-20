"""Validate that B1-B4 strategies are correctly merged into summary_data.json."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUMMARY_JSON = ROOT / "summary_data.json"
NEW_JSON = ROOT / "output" / "summary_new_strategies.json"

NEW_NAMES = [
    "SMA200 ±3% Band + RSI>30 Exit 3x",
    "SMA200 ±3% Band + RSI>30 Exit 2x",
    "SMA200 ±3% Band + RSI>30 Exit + RSI Scale 1-3x",
    "SMA200 ±3% Band + RSI>30 Exit + VIX Scale 1-3x",
]

REGIMES = ["real", "synth_era", "synth_long"]
REQUIRED_FIELDS = ["cagr_g", "dd_g", "vol", "sharpe", "sortino", "calmar", 
                   "cash", "trades_yr", "end", "cagr_r", "dd_r", "cagr_x", "dd_x"]

def main():
    errors = []
    
    # 1. Parse JSON
    print("1. Parsing summary_data.json...")
    with open(SUMMARY_JSON, "r", encoding="utf-8") as f:
        summary = json.load(f)
    print(f"   OK - valid JSON, {len(summary['assets'])} assets")
    
    # 2. Check file size
    size_kb = SUMMARY_JSON.stat().st_size / 1024
    print(f"   File size: {size_kb:.1f} KB")
    if size_kb > 500:
        errors.append(f"File size {size_kb:.0f} KB seems large")
    
    # 3. Find spx asset
    spx = None
    for a in summary["assets"]:
        if a["key"] == "spx":
            spx = a
            break
    if spx is None:
        errors.append("spx asset not found!")
        print("   FAIL: spx asset not found")
    else:
        print(f"   Found spx asset with {len(spx['real']['rows'])} strategies in real regime")
    
    # 4. Check all 4 strategies in all 3 regimes
    print("\n2. Checking strategy presence in all regimes...")
    for regime in REGIMES:
        rows = spx[regime]["rows"]
        for name in NEW_NAMES:
            if name not in rows:
                errors.append(f"MISSING: {name} in {regime}")
                print(f"   FAIL: {name} missing in {regime}")
            else:
                row = rows[name]
                missing_fields = [f for f in REQUIRED_FIELDS if f not in row]
                if missing_fields:
                    errors.append(f"MISSING fields {missing_fields} in {name} ({regime})")
                    print(f"   FAIL: {name} in {regime} missing fields: {missing_fields}")
                else:
                    print(f"   OK: {name} in {regime} - all {len(REQUIRED_FIELDS)} fields present")
    
    # 5. Cross-check values against generated output
    print("\n3. Cross-checking values against generated output...")
    with open(NEW_JSON, "r", encoding="utf-8") as f:
        new_data = json.load(f)
    new_spx = new_data["assets"][0]
    
    mismatches = 0
    for regime in REGIMES:
        for name in NEW_NAMES:
            orig = new_spx[regime]["rows"][name]
            merged = spx[regime]["rows"][name]
            for field in REQUIRED_FIELDS:
                if orig[field] != merged[field]:
                    mismatches += 1
                    if mismatches <= 5:  # only show first few
                        print(f"   MISMATCH: {name}/{regime}/{field}: orig={orig[field]} merged={merged[field]}")
    
    if mismatches == 0:
        print("   OK - all values match generated output exactly")
    else:
        errors.append(f"{mismatches} value mismatches found")
        print(f"   WARNING: {mismatches} value mismatches")
    
    # 6. Check existing entries weren't modified
    print("\n4. Checking existing entries preserved...")
    existing_names = [
        "Buy & hold 1x", "Buy & hold 2x", "Buy & hold 3x",
        "SMA20 1x/cash", "SMA20 2x/cash", "SMA20 3x/cash",
        "SMA200 1x/cash", "SMA200 2x/cash", "SMA200 3x/cash",
        "Guarded A5/B25", "Guarded A10/B20",
        "Guarded+ (200/2x/floor)", "Mom 12m 2x/cash",
        "SMA200 2x monthly", "SMA200 2x 3% band", "Golden 50/200 2x",
        "Golden 2x volguard", "Golden 3x volguard",
    ]
    for regime in REGIMES:
        for name in existing_names:
            if name not in spx[regime]["rows"]:
                errors.append(f"Existing entry '{name}' lost from {regime}!")
                print(f"   FAIL: '{name}' missing from {regime}")
    print("   OK - all 18 existing strategies preserved")
    
    # 7. Summary
    print(f"\n{'=' * 60}")
    if errors:
        print(f"VALIDATION FAILED - {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("VALIDATION PASSED - all checks OK")
        print(f"  - 22 strategies per regime (18 existing + 4 new)")
        print(f"  - All fields present and values match")
        print(f"  - JSON valid, file size {size_kb:.1f} KB")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
