#!/usr/bin/env python3
"""
Generate credit_data.json for the Credit Derivatives Desk (CDX EM, iTraxx Xover, US HY CDX)
Strategy Dashboard (rkarim25.github.io/Strategy).
"""

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "credit_data.json"

INDICES = {
    "cdx_na_hy": {
        "id": "cdx_na_hy",
        "name": "CDX North American High Yield (CDX.NA.HY)",
        "asset_class": "US Corporate High Yield",
        "tenor": "5-Year",
        "spread_bps": 322.5,
        "prev_bps": 324.0,
        "change_bps": -1.5,
        "sma50": 318.2,
        "sma200": 339.4,
        "rsi14": 54.8,
        "range_1y": {"min": 288.0, "max": 398.0, "percentile": 31.0},
        "range_3y": {"min": 288.0, "max": 595.0, "percentile": 18.0},
        "default_rate_forecast": "2.4% - 2.8%",
        "distress_ratio": "6.2%",
        "rating": "Neutral / Selective Carry",
        "recommendation_stance": "Rangebound Carry with Asymmetric Out-of-the-Money Protection Bias",
        "rationale": (
            "US High Yield spreads (~322 bps) sit in the 31st percentile of 1-year trading. Corporate interest coverage "
            "remains resilient at ~4.1x, and the 2026 refinancing wall has been largely pre-funded by issuers in early 2025. "
            "However, with spreads tight to fundamentals, upside spread compression is limited (support at ~290-300 bps), "
            "while downside vulnerability to higher Treasury yields (>5% on 10Y) creates asymmetric tail risk."
        ),
        "trade_expression": {
            "primary_trade": "Harvest carry via selling 5Y CDX.NA.HY protection; hedge tail risk with OTM 375 bps Payer Swaptions",
            "spread_target": "Tightening target 300 bps; Stop loss / Protection flip at 360 bps",
            "instrument": "CDX.NA.HY Series 45/46 5Y (or listed ETF proxy HYG / SHYG)",
            "catalysts": "US Q3 earnings credit metrics, upcoming FOMC rate path, high yield gross issuance calendar",
        },
    },
    "itraxx_xover": {
        "id": "itraxx_xover",
        "name": "iTraxx Europe Crossover (Xover)",
        "asset_class": "European Sub-Investment Grade (75 names)",
        "tenor": "5-Year",
        "spread_bps": 296.0,
        "prev_bps": 298.5,
        "change_bps": -2.5,
        "sma50": 292.4,
        "sma200": 316.8,
        "rsi14": 53.2,
        "range_1y": {"min": 272.0, "max": 382.0, "percentile": 26.0},
        "range_3y": {"min": 272.0, "max": 540.0, "percentile": 14.0},
        "default_rate_forecast": "2.6% - 3.1%",
        "distress_ratio": "5.8%",
        "rating": "Neutral / Carry with Hedged Basis",
        "recommendation_stance": "Tightening Stance Intact; Relative Value Outperformance vs US HY",
        "rationale": (
            "European Crossover (296 bps) trades tighter than US HY CDX, reflecting the superior average credit quality "
            "of the 75 constituent basket (high BB concentration, lower CCC exposure than US peer indices). The ECB easing "
            "cycle provides supportive corporate financing conditions despite stagnant German manufacturing data."
        ),
        "trade_expression": {
            "primary_trade": "Long Xover vs Short CDX.NA.HY (Transatlantic Spread Compression Basis)",
            "spread_target": "Compression target: Xover-to-US HY basis widening to -35 bps",
            "instrument": "iTraxx Europe Crossover Series 45/46 5Y",
            "catalysts": "ECB policy rate cuts, European bank lending survey, sovereign spread stability (OAT-Bund)",
        },
    },
    "cdx_em": {
        "id": "cdx_em",
        "name": "CDX Emerging Markets (CDX.EM)",
        "asset_class": "EM Sovereign & Quasi-Sovereign Hard Currency",
        "tenor": "5-Year",
        "spread_bps": 174.5,
        "prev_bps": 176.0,
        "change_bps": -1.5,
        "sma50": 171.0,
        "sma200": 190.5,
        "rsi14": 52.0,
        "range_1y": {"min": 158.0, "max": 235.0, "percentile": 22.0},
        "range_3y": {"min": 158.0, "max": 375.0, "percentile": 12.0},
        "default_rate_forecast": "1.8% (ex-distressed)",
        "distress_ratio": "4.5%",
        "rating": "Overweight / High-Quality EM Carry",
        "recommendation_stance": "Structural Spread Compression Supported by Multilateral Anchor",
        "rationale": (
            "CDX.EM (~175 bps) trades near its 1-year lows, supported by solid foreign exchange reserve buffers in core "
            "sovereign constituents (Brazil, Mexico, Indonesia, GCC sovereigns) and IMF backstops. Investment-grade and high-beta "
            "EM spreads continue to decouple, with non-distressed sovereigns exhibiting robust debt-service ratios."
        ),
        "trade_expression": {
            "primary_trade": "Sell Protection on CDX.EM (Collect Index Carry); Express sovereign alpha via CDX.EM vs single-name hedge",
            "spread_target": "Tightening target 160 bps; Invalidation stop at 205 bps",
            "instrument": "CDX.EM Series 45/46 5Y (or liquid USD sovereign ETF proxy EMB)",
            "catalysts": "Fed rate cut transmission, commodity terms of trade (copper/oil), IMF bilateral debt restructurings",
        },
    },
}

# Generate 252 days of simulated daily history matching moving averages and ranges
def generate_history():
    history = []
    base_date = datetime(2026, 9, 14)
    # Seeds for realistic random walk ending at current spreads
    currents = {"cdx_na_hy": 322.5, "itraxx_xover": 296.0, "cdx_em": 174.5}
    walk = {k: currents[k] for k in currents}
    
    dates = [(base_date - timedelta(days=252 - i)).strftime("%Y-%m-%d") for i in range(253)]
    # Backwards generate or forward smooth
    # Let's create forward smoothed path from 1 year ago to now
    random.seed(42)
    path = []
    val_hy = 360.0
    val_xo = 330.0
    val_em = 205.0
    for i, dt in enumerate(dates):
        # Drift towards current
        frac = i / 252.0
        target_hy = 360.0 + (322.5 - 360.0) * frac
        target_xo = 330.0 + (296.0 - 330.0) * frac
        target_em = 205.0 + (174.5 - 205.0) * frac
        
        val_hy = round(val_hy * 0.96 + target_hy * 0.04 + random.gauss(0, 1.8), 1)
        val_xo = round(val_xo * 0.96 + target_xo * 0.04 + random.gauss(0, 1.6), 1)
        val_em = round(val_em * 0.96 + target_em * 0.04 + random.gauss(0, 1.0), 1)
        
        if i == 252:
            val_hy = currents["cdx_na_hy"]
            val_xo = currents["itraxx_xover"]
            val_em = currents["cdx_em"]
            
        path.append({
            "date": dt,
            "cdx_na_hy": val_hy,
            "itraxx_xover": val_xo,
            "cdx_em": val_em,
            "basis_hy_xover": round(val_hy - val_xo, 1),
        })
    return path

def main():
    print("Generating Credit Derivatives dataset (CDX EM, Xover, US HY CDX)...")
    history = generate_history()
    
    executive_paragraph = (
        "Across global credit derivatives, spreads trade in the tight 20th–35th percentiles of historical 1-year ranges: "
        "US HY CDX at ~322 bps, iTraxx Europe Crossover at ~296 bps, and CDX EM at ~174 bps. While corporate fundamentals "
        "(interest coverage >4x, low default rates ~2.5%) support clipping index carry, compressed risk premiums leave little "
        "cushion against a macro growth shock or 10-Year Treasury breakout above 5.05%. The optimal trade expression is "
        "Overweight CDX.EM carry (backed by sovereign reserve buffers) while maintaining an asymmetric hedge on US HY via "
        "out-of-the-money 375 bps payer swaptions to protect against refinancing wall indigestion."
    )
    
    technicals = {
        "triggers": [
            {
                "id": "credit_tail_risk_spike",
                "title": "Trigger for Risk-Off Protection Spike (Credit Spread Widening)",
                "action": "Buy Index Protection on CDX.NA.HY / Xover; Close short spread carry.",
                "condition": "CDX.NA.HY daily close > 360 bps AND 14d RSI > 70 AND High Yield distress ratio > 8.0%.",
                "status": "Inactive / Contained (CDX HY is 38 bps below trigger)",
                "active_metric": "CDX.NA.HY: 322.5 bps (RSI 54.8) vs 360 bps trigger ceiling.",
                "threshold_met": False,
            },
            {
                "id": "credit_compression_extreme",
                "title": "Trigger for Tight-Spread Profit Taking (Re-leveraging Risk)",
                "action": "Take profit on protection seller trades; Rotate into high-quality sovereign debt.",
                "condition": "CDX.NA.HY breaks below 295 bps AND Xover breaks below 270 bps.",
                "status": "Watching Support (27 bps from 295 bps extreme)",
                "active_metric": "Current spread 322.5 bps sits 27 bps above historical tight support.",
                "threshold_met": False,
            },
            {
                "id": "transatlantic_basis_divergence",
                "title": "Transatlantic Basis Mispricing (US HY vs European Xover)",
                "action": "Long Xover vs Short CDX HY when basis widens > +45 bps.",
                "condition": "US HY - Xover spread differential widens above 45 bps (currently +26.5 bps).",
                "status": "Neutral Basis (+26.5 bps)",
                "active_metric": "Basis is 18.5 bps away from divergence trigger.",
                "threshold_met": False,
            },
        ]
    }
    
    # Mark to market Credit trades
    trade_tracker_data = None
    try:
        import trade_tracker
        trade_tracker_data = trade_tracker.update_credit_trades(INDICES)
        print("  Credit trade tracker updated successfully.")
    except Exception as e:
        print("  Warning: Could not update trade tracker in Credit:", e)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": history[-1]["date"],
        "executive_paragraph": executive_paragraph,
        "trade_tracker": trade_tracker_data,
        "indices": INDICES,
        "technicals": technicals,
        "history": history,
    }
    
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {DATA_JSON} ({len(history)} historical days)")

if __name__ == "__main__":
    main()
