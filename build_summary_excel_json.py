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

# The strategy each asset's site page features as its DEFAULT/chosen pick. Maps asset ->
# {exact strategy name: role label}; the role shows as a badge. Every asset's default is also
# surfaced as a `site_default` line on the Summary page (even when it's not a strict Water/Octane,
# so it can't earn the ★ row-highlight inside the Water/Octane drill-down tables).
# Role labels: "Water" / "Octane" = strict classification; "Water*" = a Stillwater serving as the
# Water pick (Nasdaq has no strict Water/Octane); "Trend" = the best available 1x/cash trend rule
# where no strict Water/Octane/Stillwater exists (buy-&-hold is too strong) — see
# core/site_default_strategy.py for the canonical per-asset config the live pages use.
SITE_DEFAULTS = {
    "spx": {
        "SMA200 +-3% Band + RSI>20 Exit 2x": "Octane",
        "SMA200 +-3% Band + Accel-Exit N10 1x/cash": "Water",
    },
    "ndx": {
        "GC 50/200 1x; +2x when VIX<20 & idxDD>-12%": "Octane",
        "SMA100 +1/-3% Band + 8% Trailing 1x/cash": "Water*",
    },
    "dax": {
        "SMA200 +-3% Band 1x/cash": "Water",
    },
    "ftse250": {
        "SMA20 1x/cash": "Water",
    },
    "gold": {
        "SMA50/150 Golden Cross 1x/cash": "Trend",
    },
    "msci_em": {
        "SMA100 1x/cash": "Trend",
    },
    "msci_world": {
        "SMA200 1x/cash": "Trend",
    },
}


def mark_defaults(rows: list[dict], defaults: dict[str, str]) -> list[dict]:
    for r in rows:
        role = defaults.get(r["Strategy"])
        r["default"] = role is not None
        if role:
            r["default_role"] = role
    return rows


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

        defaults = SITE_DEFAULTS.get(key, {})
        water_rows = mark_defaults([row_to_dict(r) for _, r in water.iterrows()], defaults)
        octane_rows = mark_defaults([row_to_dict(r) for _, r in octane.iterrows()], defaults)
        stillwater_rows = mark_defaults(stillwater_rows, defaults)

        assets.append({
            "key": key,
            "label": ASSET_LABELS[key],
            "cost": TRADING_COST_LABELS.get(key),
            "site_default": [{"name": name, "role": role} for name, role in defaults.items()],
            "bh_cagr": bh_cagr,
            "bh_maxdd": bh_maxdd,
            "total": int(len(strat)),
            "water_count": int((strat["Classification"] == "Water").sum()),
            "octane_count": int((strat["Classification"] == "Octane").sum()),
            "neither_count": int((strat["Classification"] == "Neither").sum()),
            "stillwater_count": len(stillwater_rows),
            "best_water": best_water,
            "best_octane": best_octane,
            "water_rows": water_rows,
            "octane_rows": octane_rows,
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
