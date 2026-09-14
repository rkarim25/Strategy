#!/usr/bin/env python3
"""
trade_tracker.py — Institutional Trade Recommendation & Mark-to-Market P&L Engine
Manages macro_trade_tracker.json at repo root.
Tracks trade entry levels, targets, stops, and computes live P&L in bps and USD.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRACKER_FILE = ROOT / "macro_trade_tracker.json"

DEFAULT_TRADES = [
    {
        "id": "UST-20260914-01",
        "desk": "US Treasuries",
        "asset_class": "Rates",
        "date_opened": "2026-09-14",
        "title": "2s10s Curve Steepener (DV01 Neutral)",
        "type": "Curve Spread",
        "direction": "Long Steepener",
        "instrument": "Long 2Y Note (^2YY=F) / Short 10Y Note (^TNX)",
        "sizing": "DV01 $10,000 / bp (Long $4.27M 2Y vs Short $1.00M 10Y)",
        "dv01_usd": 10000.0,
        "entry_level": 57.9,
        "entry_unit": "bps",
        "current_level": 57.9,
        "target_level": 95.0,
        "stop_loss_level": 25.0,
        "status": "OPEN",
        "pnl_bps": 0.0,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "rationale": "Overweight front-to-belly; 10Y term premium expansion and relentless fiscal supply shocks drive curve steepening out of inversion.",
        "invalidation_trigger": "10Y < 4.70% & 2s10s < +25 bps & Unemployment > 4.6%."
    },
    {
        "id": "UST-20260914-02",
        "desk": "US Treasuries",
        "asset_class": "Rates",
        "date_opened": "2026-09-14",
        "title": "5-Year Note Belly Carry & Roll-Down",
        "type": "Outright Duration",
        "direction": "Long Duration",
        "instrument": "US 5-Year Treasury Note (^FVX)",
        "sizing": "$1,000,000 Notional ($465 DV01)",
        "dv01_usd": 465.0,
        "entry_level": 4.78,
        "entry_unit": "% yield",
        "current_level": 4.78,
        "target_level": 4.25,
        "stop_loss_level": 5.10,
        "status": "OPEN",
        "pnl_bps": 0.0,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "rationale": "Locks in 4.78% yield (90% of 30Y yield) while bearing only 28% of duration volatility. Optimal roll-down along front steepness.",
        "invalidation_trigger": "5Y closes above 5.10% or headline inflation accelerates > 3.8%."
    },
    {
        "id": "GBI-20260914-01",
        "desk": "Local EM",
        "asset_class": "EM Sovereign & FX",
        "date_opened": "2026-09-14",
        "title": "Long Brazil NTN-F 2029 (Unhedged BRL Carry)",
        "type": "Outright Sovereign & FX Carry",
        "direction": "Long Rates & Long FX",
        "instrument": "Brazil NTN-F 10% Jan 2029 (5Y belly)",
        "sizing": "$100,000 Notional ($420 DV01)",
        "dv01_usd": 420.0,
        "entry_level": 12.35,
        "entry_unit": "% yield",
        "current_level": 12.35,
        "target_level": 11.20,
        "stop_loss_level": 13.10,
        "status": "OPEN",
        "pnl_bps": 0.0,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "rationale": "+8.10% real yield provides massive cushion against volatility. Selic paused at 10.50% keeps carry pristine.",
        "invalidation_trigger": "USDBRL > 5.70 or Copom inflation target de-anchoring."
    },
    {
        "id": "GBI-20260914-02",
        "desk": "Local EM",
        "asset_class": "EM Sovereign & FX",
        "date_opened": "2026-09-14",
        "title": "Long South Africa SAGB R2035 (FX-Hedged ZAR)",
        "type": "Sovereign Duration",
        "direction": "Long Rates / Hedged FX",
        "instrument": "South Africa SAGB 8.875% 2035 (10Y)",
        "sizing": "$100,000 Notional ($720 DV01)",
        "dv01_usd": 720.0,
        "entry_level": 10.85,
        "entry_unit": "% yield",
        "current_level": 10.85,
        "target_level": 9.80,
        "stop_loss_level": 11.40,
        "status": "OPEN",
        "pnl_bps": 0.0,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "rationale": "GNU coalition governance delivers fiscal discipline rerate. +6.25% real yield with currency risk insulated via forward hedge.",
        "invalidation_trigger": "USDZAR > 18.60 or fiscal slippage in Medium-Term Budget Policy Statement."
    },
    {
        "id": "CDX-20260914-01",
        "desk": "Credit Derivatives",
        "asset_class": "Credit",
        "date_opened": "2026-09-14",
        "title": "Sell CDX.NA.HY Belly Protection / Harvest Carry",
        "type": "Synthetic Credit Carry",
        "direction": "Short Protection (Long Credit Risk)",
        "instrument": "CDX.NA.HY Series 42 5Y",
        "sizing": "$1,000,000 Notional ($450 Spread DV01)",
        "dv01_usd": 450.0,
        "entry_level": 322.5,
        "entry_unit": "bps",
        "current_level": 322.5,
        "target_level": 290.0,
        "stop_loss_level": 360.0,
        "status": "OPEN",
        "pnl_bps": 0.0,
        "pnl_usd": 0.0,
        "pnl_pct": 0.0,
        "rationale": "High yield carry (~7.6%) with default rate expectations muted at 2.1%. Refinancing wall manageable into 2026.",
        "invalidation_trigger": "CDX.NA.HY > 360 bps & iTraxx Xover > 340 bps."
    }
]

def load_tracker():
    if TRACKER_FILE.exists():
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read {TRACKER_FILE}, initializing default: {e}")
    
    tracker = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "portfolio_summary": {
            "total_trades": len(DEFAULT_TRADES),
            "open_trades": len(DEFAULT_TRADES),
            "closed_trades": 0,
            "total_pnl_bps": 0.0,
            "total_pnl_usd": 0.0,
            "win_rate_pct": 100.0
        },
        "trades": DEFAULT_TRADES
    }
    save_tracker(tracker)
    return tracker

def save_tracker(tracker):
    tracker["last_updated"] = datetime.now(timezone.utc).isoformat()
    compute_summary(tracker)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2)

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

def update_ust_trades(yields_dict, spreads_dict):
    """
    Mark to market UST trades with fresh yields and spreads.
    yields_dict: {"2y": {"yield": 4.38}, "5y": {"yield": 4.78}, "10y": {"yield": 4.96}, "30y": {"yield": 5.33}}
    spreads_dict: {"2s10s": {"bps": 57.9}, "5s30s": {"bps": 54.7}, "2s30s": {"bps": 95.1}, "5s10s": {"bps": 18.0}}
    """
    tracker = load_tracker()
    
    for t in tracker.get("trades", []):
        if t.get("desk") != "US Treasuries" or t.get("status") != "OPEN":
            continue
        
        # 1. 2s10s Steepener
        if "2s10s" in t.get("title", "").lower() and "spread" in str(t.get("type", "")).lower():
            if "2s10s" in spreads_dict:
                curr = spreads_dict["2s10s"]["bps"]
                t["current_level"] = curr
                entry = t["entry_level"]
                pnl_bps = round(curr - entry, 1)
                t["pnl_bps"] = pnl_bps
                t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 10000.0), 2)
                t["pnl_pct"] = round((pnl_bps / entry) * 100, 2) if entry != 0 else 0.0
                
                if curr >= t["target_level"]:
                    t["status"] = "TARGET_HIT"
                elif curr <= t["stop_loss_level"]:
                    t["status"] = "STOPPED"
        
        # 2. 5Y Note Outright Long Duration
        elif "5-year" in t.get("title", "").lower() and "5y" in yields_dict:
            curr = yields_dict["5y"]["yield"]
            t["current_level"] = curr
            entry = t["entry_level"]
            pnl_bps = round((entry - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 465.0), 2)
            t["pnl_pct"] = round(pnl_bps / 100.0 * 4.65, 2)
            
            if curr <= t["target_level"]:
                t["status"] = "TARGET_HIT"
            elif curr >= t["stop_loss_level"]:
                t["status"] = "STOPPED"

    save_tracker(tracker)
    return tracker

def update_credit_trades(indices_dict):
    """
    Mark to market Credit trades.
    indices_dict: {"cdx_hy": {"spread": 322.5}, "xover": {"spread": 296.0}, "cdx_em": {"spread": 174.5}}
    """
    tracker = load_tracker()
    for t in tracker.get("trades", []):
        if t.get("desk") != "Credit Derivatives" or t.get("status") != "OPEN":
            continue
        
        if "cdx.na.hy" in t.get("instrument", "").lower() and "cdx_hy" in indices_dict:
            curr = indices_dict["cdx_hy"]["spread"]
            t["current_level"] = curr
            entry = t["entry_level"]
            pnl_bps = round(entry - curr, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 450.0), 2)
            t["pnl_pct"] = round((pnl_bps / entry) * 100, 2)
            
            if curr <= t["target_level"]:
                t["status"] = "TARGET_HIT"
            elif curr >= t["stop_loss_level"]:
                t["status"] = "STOPPED"
                
    save_tracker(tracker)
    return tracker

def update_gbi_em_trades(countries_dict):
    """
    Mark to market GBI-EM trades.
    countries_dict: {"brazil": {"rates": {"yield_10y": 12.35}}, "south_africa": ...}
    """
    tracker = load_tracker()
    for t in tracker.get("trades", []):
        if t.get("desk") != "Local EM" or t.get("status") != "OPEN":
            continue
        
        if "brazil" in t.get("id", "").lower() or "brazil" in t.get("title", "").lower():
            if "brazil" in countries_dict:
                curr = countries_dict["brazil"]["rates"].get("yield_5y") or countries_dict["brazil"]["rates"]["yield_10y"]
                t["current_level"] = curr
                entry = t["entry_level"]
                pnl_bps = round((entry - curr) * 100, 1)
                t["pnl_bps"] = pnl_bps
                t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 420.0), 2)
                t["pnl_pct"] = round(pnl_bps / 100.0 * 4.2, 2)
                
                if curr <= t["target_level"]:
                    t["status"] = "TARGET_HIT"
                elif curr >= t["stop_loss_level"]:
                    t["status"] = "STOPPED"
                    
        elif "south africa" in t.get("title", "").lower() and "south_africa" in countries_dict:
            curr = countries_dict["south_africa"]["rates"]["yield_10y"]
            t["current_level"] = curr
            entry = t["entry_level"]
            pnl_bps = round((entry - curr) * 100, 1)
            t["pnl_bps"] = pnl_bps
            t["pnl_usd"] = round(pnl_bps * t.get("dv01_usd", 720.0), 2)
            t["pnl_pct"] = round(pnl_bps / 100.0 * 7.2, 2)
            
            if curr <= t["target_level"]:
                t["status"] = "TARGET_HIT"
            elif curr >= t["stop_loss_level"]:
                t["status"] = "STOPPED"

    save_tracker(tracker)
    return tracker

if __name__ == "__main__":
    t = load_tracker()
    print(f"Loaded Trade Tracker: {len(t['trades'])} trades, Total P&L: ${t['portfolio_summary']['total_pnl_usd']:.2f}")
