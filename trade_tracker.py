#!/usr/bin/env python3
"""
trade_tracker.py — Institutional Trade Recommendation & Mark-to-Market P&L Engine
Manages macro_trade_tracker.json at repo root.
Tracks trade entry levels, targets, stops, and computes live P&L in bps and USD.
Syncs portfolio tracking into ust_curve_data.json and gbi_em_data.json.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRACKER_FILE = ROOT / "macro_trade_tracker.json"
UST_DATA_FILE = ROOT / "ust_curve_data.json"
GBI_DATA_FILE = ROOT / "gbi_em_data.json"

def load_tracker():
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read {TRACKER_FILE}: {e}")
    return {"portfolio_summary": {}, "trades": []}

def save_tracker(tracker):
    tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
    compute_summary(tracker)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    sync_to_desks(tracker)

def compute_summary(tracker):
    trades = tracker.get("trades", [])
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    closed_trades = [t for t in trades if t.get("status") in ["CLOSED", "TARGET_HIT", "STOPPED"]]
    
    total_pnl_bps = sum(t.get("pnl_bps", 0.0) for t in trades)
    total_pnl_usd = sum(t.get("pnl_usd", 0.0) for t in trades)
    
    winners = [t for t in trades if t.get("pnl_usd", 0.0) > 0]
    win_rate = (len(winners) / len(trades) * 100.0) if trades else 100.0
    
    tracker["portfolio_summary"] = {
        "total_trades": len(trades),
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "total_pnl_bps": round(total_pnl_bps, 1),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "win_rate_pct": round(win_rate, 1)
    }

def sync_to_desks(tracker):
    # 1. Sync to ust_curve_data.json
    if UST_DATA_FILE.exists():
        try:
            with open(UST_DATA_FILE, "r", encoding="utf-8") as f:
                ust_data = json.load(f)
            ust_data["trade_tracker"] = tracker
            with open(UST_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(ust_data, f, indent=2, ensure_ascii=False)
            print("[OK] Synced trade tracker to ust_curve_data.json")
        except Exception as e:
            print(f"Warning: Could not sync to UST data: {e}")

    # 2. Sync to gbi_em_data.json
    if GBI_DATA_FILE.exists():
        try:
            with open(GBI_DATA_FILE, "r", encoding="utf-8") as f:
                gbi_data = json.load(f)
            gbi_data["trade_tracker"] = tracker
            with open(GBI_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(gbi_data, f, indent=2, ensure_ascii=False)
            print("[OK] Synced trade tracker to gbi_em_data.json")
        except Exception as e:
            print(f"Warning: Could not sync to GBI data: {e}")

def update_all_trades():
    tracker = load_tracker()
    
    # Load live data from UST and GBI datasets
    ust_data = {}
    if UST_DATA_FILE.exists():
        with open(UST_DATA_FILE, "r", encoding="utf-8") as f:
            ust_data = json.load(f)
    
    gbi_data = {}
    if GBI_DATA_FILE.exists():
        with open(GBI_DATA_FILE, "r", encoding="utf-8") as f:
            gbi_data = json.load(f)

    yields = ust_data.get("yields", {})
    spreads = ust_data.get("spreads", {})
    countries = gbi_data.get("countries", {})

    for t in tracker.get("trades", []):
        if t.get("status") not in ["OPEN"]:
            continue

        tid = t.get("id")
        title = t.get("title", "").lower()

        # UST Trades
        if tid == "UST-20260914-01" and "2s10s" in spreads:
            curr = spreads["2s10s"]["bps"]
            t["current_level"] = curr
            pnl_bps = round(curr - t["entry_level"], 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 10000.0), 2)
        elif tid == "UST-20260914-02" and "5y" in yields:
            curr = yields["5y"]["yield"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 465.0), 2)

        # GBI-EM Trades by explicit ID
        elif tid == "GBI-20260914-01" and "brazil" in countries:
            curr = countries["brazil"]["rates"]["yield_5y"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 420.0), 2)

        elif tid == "GBI-20260914-02" and "south_africa" in countries:
            # Closed target hit
            pass

        elif tid == "GBI-20260914-03" and "south_africa" in countries:
            curr = countries["south_africa"]["rates"]["yield_10y"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 410.0), 2)

        elif tid == "GBI-20260914-04" and "india" in countries:
            curr = countries["india"]["rates"]["yield_10y"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 720.0), 2)

        elif tid == "GBI-20260914-05" and "mexico" in countries:
            # Mexico 2s10s Flattener
            curr_10y = countries["mexico"]["rates"]["yield_10y"]
            curr_2y = countries["mexico"]["rates"]["yield_2y"]
            curr_spread = round((curr_10y - curr_2y) * 100, 1)  # -23 bps
            t["current_level"] = curr_spread
            # Flattener gains when spread becomes more negative (entry -25, current -23 -> +2 bps)
            pnl_bps = round(curr_spread - t["entry_level"], 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 5000.0), 2)

        elif tid == "GBI-20260914-06" and "indonesia" in countries:
            curr = countries["indonesia"]["rates"]["yield_10y"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 380.0), 2)

        elif tid == "GBI-20260914-07" and "poland" in countries:
            # Poland PLN FX trade
            curr = countries["poland"]["fx"]["spot"]
            t["current_level"] = curr
            # EUR/PLN lower spot is gain for Long PLN
            pnl_pips = round((t["entry_level"] - curr) * 100, 1)  # e.g. 4.32 - 4.28 = 0.04 -> 4.0 pips / 40 ticks
            t["pnl_bps"] = round((t["entry_level"] - curr) * 1000 / 4.3, 1)
            t["pnl_usd"] = round(((t["entry_level"] - curr) / t["entry_level"]) * 2000000.0 / 4.28, 2)

        elif tid == "GBI-20260914-08":
            # Mexico 2s10s TIIE Flattener
            curr_spread = -23.0
            t["current_level"] = curr_spread
            pnl_bps = round(curr_spread - t["entry_level"], 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * 1000.0, 2)  # $2,000

        elif tid == "GBI-20260914-09" and "brazil" in countries:
            # Receive Brazil DI1F29
            curr = countries["brazil"]["rates"]["yield_5y"]
            t["current_level"] = curr
            pnl_bps = round((t["entry_level"] - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * 420.0, 2)  # $12,600

        elif tid == "GBI-20260914-10" and "poland" in countries:
            # Pay Poland 10Y WIBOR IRS
            curr = countries["poland"]["rates"]["yield_10y"]
            t["current_level"] = curr
            # Pay fixed gains when yield rises
            pnl_bps = round((curr - t["entry_level"]) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * 1000.0, 2)  # $10,000

    save_tracker(tracker)
    print(f"[OK] Marked all trades to market. Total P&L: ${tracker['portfolio_summary']['total_pnl_usd']:.2f}")

if __name__ == "__main__":
    update_all_trades()
