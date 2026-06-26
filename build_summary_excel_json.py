"""Export the Excel sweep's Water / Octane / Stillwater results to summary_excel.json
for the website Summary page (reuses the same classification as the Excel workbook).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd

from build_strategy_results_excel import (
    ASSET_LABELS,
    ASSET_ORDER,
    TRADING_COST_LABELS,
    classify_all,
    classify_stillwater,
    is_bh_row,
    load_all_data,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "summary_excel.json")

# Columns surfaced in the per-asset drill-down tables.
DETAIL_FIELDS = [
    "Strategy", "Leverage_Max", "CAGR_pct", "Vol_pct", "Sharpe", "Sortino",
    "Calmar", "MaxDD_pct", "Trades_Per_Year", "Pct_Cash_Time", "End_Value",
]


def _num(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def row_to_dict(r):
    out = {"Strategy": str(r.get("Strategy"))}
    for f in DETAIL_FIELDS[1:]:
        out[f] = _num(r.get(f))
    return out


def main() -> int:
    df = classify_all(load_all_data())
    assets = []
    for key in ASSET_ORDER:
        adf = df[df["Asset"] == key]
        strat = adf[~adf["Strategy"].apply(is_bh_row)]
        bh1 = adf[adf["Strategy"] == "Buy & Hold 1x"]
        bh_cagr = _num(bh1.iloc[0]["CAGR_pct"]) if len(bh1) else None
        bh_maxdd = _num(bh1.iloc[0]["MaxDD_pct"]) if len(bh1) else None

        water = strat[strat["Classification"] == "Water"].sort_values("Sharpe", ascending=False)
        octane = strat[strat["Classification"] == "Octane"].sort_values("Calmar", ascending=False)

        best_water = None
        if len(water):
            bw = water.loc[water["CAGR_pct"].idxmax()]
            best_water = {"name": str(bw["Strategy"]), "cagr": _num(bw["CAGR_pct"])}
        best_octane = None
        if len(octane):
            bo = octane.loc[octane["Calmar"].idxmax()]
            best_octane = {"name": str(bo["Strategy"]), "calmar": _num(bo["Calmar"])}

        stillwater_rows = []
        if key == "ndx" and len(bh1):
            bhm = {k: float(bh1.iloc[0][k]) for k in
                   ["Sharpe", "Calmar", "MaxDD_pct", "CAGR_pct", "Sortino", "Vol_pct"]}
            sw = strat.copy()
            sw["SW"] = sw.apply(lambda r: classify_stillwater(r, bhm), axis=1)
            swq = sw[sw["SW"].isin(["Stillwater-Water", "Stillwater-Octane"])].sort_values("Calmar", ascending=False)
            stillwater_rows = [row_to_dict(r) for _, r in swq.iterrows()]

        assets.append({
            "key": key,
            "label": ASSET_LABELS[key],
            "cost": TRADING_COST_LABELS.get(key),
            "bh_cagr": bh_cagr,
            "bh_maxdd": bh_maxdd,
            "total": int(len(strat)),
            "water_count": int((strat["Classification"] == "Water").sum()),
            "octane_count": int((strat["Classification"] == "Octane").sum()),
            "neither_count": int((strat["Classification"] == "Neither").sum()),
            "best_water": best_water,
            "best_octane": best_octane,
            "water_rows": [row_to_dict(r) for _, r in water.iterrows()],
            "octane_rows": [row_to_dict(r) for _, r in octane.iterrows()],
            "stillwater_rows": stillwater_rows,
        })

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assets": assets,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, allow_nan=False)
    tot_w = sum(a["water_count"] for a in assets)
    tot_o = sum(a["octane_count"] for a in assets)
    print(f"Wrote {OUT}: {len(assets)} assets, {tot_w} Water, {tot_o} Octane total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
