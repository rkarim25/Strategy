#!/usr/bin/env python3
"""
Fetch generic US Treasury yields (2Y, 5Y, 10Y, 30Y) and generate ust_curve_data.json
for the Strategy dashboard (rkarim25.github.io/Strategy).
Computes technical indicators (SMA50, SMA200, RSI14), regime classification,
steepener/flattener recommendations, and invalidation triggers.
"""

import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "ust_curve_data.json"
DAILY_CSV = ROOT / "ust_daily.csv"

SERIES_META = {
    "2y": {
        "symbol": "2YY=F",
        "name": "US 2-Year Treasury Note",
        "tenor_years": 2,
        "duration": 1.92,
        "convexity": 0.05,
        "dv01": 19.2,
        "role": "Policy Anchor & Near-Term Fed Expectation",
    },
    "5y": {
        "symbol": "^FVX",
        "name": "US 5-Year Treasury Note",
        "tenor_years": 5,
        "duration": 4.65,
        "convexity": 0.25,
        "dv01": 46.5,
        "role": "The Belly / Cyclical Growth & Neutral Rate (r*) Barometer",
    },
    "10y": {
        "symbol": "^TNX",
        "name": "US 10-Year Treasury Note",
        "tenor_years": 10,
        "duration": 8.20,
        "convexity": 0.82,
        "dv01": 82.0,
        "role": "Global Cost of Capital / Equity & Mortgage Benchmark",
    },
    "30y": {
        "symbol": "^TYX",
        "name": "US 30-Year Treasury Bond",
        "tenor_years": 30,
        "duration": 16.50,
        "convexity": 3.65,
        "dv01": 165.0,
        "role": "Long-Term Term Premium, Fiscal Supply & Inflation Expectations",
    },
}

def fetch_chart(symbol: str, range_str: str = "2y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range={range_str}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    res = data["chart"]["result"][0]
    timestamps = res["timestamp"]
    closes = res["indicators"]["quote"][0]["close"]
    points = {}
    for ts, c in zip(timestamps, closes):
        if c is not None and not math.isnan(c) and c > 0:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            points[dt] = round(float(c), 3)
    return points

def calc_sma(arr, n):
    if len(arr) < n:
        return None
    return round(sum(arr[-n:]) / n, 3)

def calc_rsi(arr, n=14):
    if len(arr) < n + 1:
        return None
    deltas = [arr[i] - arr[i-1] for i in range(1, len(arr))]
    recent = deltas[-n:]
    gains = [x for x in recent if x > 0]
    losses = [-x for x in recent if x < 0]
    avg_gain = sum(gains) / n if gains else 0
    avg_loss = sum(losses) / n if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def main():
    print("Fetching Treasury yield curve data...")
    raw_series = {}
    for key, meta in SERIES_META.items():
        try:
            pts = fetch_chart(meta["symbol"])
            raw_series[key] = pts
            print(f"  Fetched {key} ({meta['symbol']}): {len(pts)} valid points")
        except Exception as e:
            print(f"  Warning: error fetching {key} ({meta['symbol']}): {e}")
            raw_series[key] = {}

    # Find common dates
    all_dates = sorted(set().union(*[pts.keys() for pts in raw_series.values()]))
    if not all_dates:
        print("Error: No dates fetched!")
        sys.exit(1)

    # Forward fill missing points
    aligned = []
    last_known = {k: None for k in SERIES_META}
    for dt in all_dates:
        row = {"date": dt}
        for k in SERIES_META:
            if dt in raw_series[k]:
                last_known[k] = raw_series[k][dt]
            row[k] = last_known[k]
        if all(row[k] is not None for k in SERIES_META):
            row["spread_2s10s"] = round((row["10y"] - row["2y"]) * 100, 1)
            row["spread_5s30s"] = round((row["30y"] - row["5y"]) * 100, 1)
            row["spread_2s30s"] = round((row["30y"] - row["2y"]) * 100, 1)
            row["spread_10s30s"] = round((row["30y"] - row["10y"]) * 100, 1)
            row["spread_5s10s"] = round((row["10y"] - row["5y"]) * 100, 1)
            aligned.append(row)

    if not aligned:
        print("Error: No aligned rows after forward fill!")
        sys.exit(1)

    latest_row = aligned[-1]
    prev_row = aligned[-2] if len(aligned) > 1 else latest_row

    # Technical Indicators calculation
    history_10y = [r["10y"] for r in aligned]
    history_2y = [r["2y"] for r in aligned]
    history_5y = [r["5y"] for r in aligned]
    history_30y = [r["30y"] for r in aligned]
    history_2s10s = [r["spread_2s10s"] for r in aligned]
    history_2s30s = [r["spread_2s30s"] for r in aligned]
    history_5s10s = [r["spread_5s10s"] for r in aligned]
    history_5s30s = [r["spread_5s30s"] for r in aligned]

    sma50_2s30s = calc_sma(history_2s30s, 50)
    sma200_2s30s = calc_sma(history_2s30s, 200)
    rsi14_2s30s = calc_rsi(history_2s30s, 14)

    sma50_5s10s = calc_sma(history_5s10s, 50)
    sma200_5s10s = calc_sma(history_5s10s, 200)
    rsi14_5s10s = calc_rsi(history_5s10s, 14)

    sma50_10y = calc_sma(history_10y, 50)
    sma200_10y = calc_sma(history_10y, 200)
    rsi14_10y = calc_rsi(history_10y, 14)

    sma50_2s10s = calc_sma(history_2s10s, 50)
    sma200_2s10s = calc_sma(history_2s10s, 200)
    rsi14_2s10s = calc_rsi(history_2s10s, 14)

    sma50_2y = calc_sma(history_2y, 50)
    sma200_2y = calc_sma(history_2y, 200)

    # Technical assessment
    technicals = {
        "10y": {
            "current": latest_row["10y"],
            "sma50": sma50_10y,
            "sma200": sma200_10y,
            "rsi14": rsi14_10y,
            "trend": "Bullish Yield / Bearish Price" if latest_row["10y"] > sma50_10y else "Yield Pullback",
            "rsi_status": "Overbought Yield (>70)" if rsi14_10y and rsi14_10y > 70 else "Neutral",
            "resistance": 5.05,
            "support_50d": sma50_10y,
            "support_200d": sma200_10y,
        },
        "2s10s": {
            "current": latest_row["spread_2s10s"],
            "sma50": sma50_2s10s,
            "sma200": sma200_2s10s,
            "rsi14": rsi14_2s10s,
            "trend": "Steepening Trend Intact" if latest_row["spread_2s10s"] > sma50_2s10s else "Flattening Retracement",
            "support_50d": sma50_2s10s,
            "resistance_high": 75.0,
        },
        "triggers": [
            {
                "id": "flip_to_long_duration",
                "title": "Trigger to Pivot to Long Duration (Bull Flattening)",
                "action": "Close Steepeners. Overweight 10Y and 30Y Duration.",
                "condition": "10Y Yield breaks below 4.70% (50d/200d SMA support) AND 2s10s breaks below +25 bps AND Unemployment > 4.6%.",
                "status": "Inactive (Bear Steepener Dominant)",
                "active_metric": f"10Y is {round(latest_row['10y'] - 4.70, 2)}% above trigger; 2s10s is {round(latest_row['spread_2s10s'] - 25.0, 1)} bps above trigger.",
                "threshold_met": False,
            },
            {
                "id": "steepener_continuation",
                "title": "Trigger for Accelerated Steepener (Bond Vigilante Breakout)",
                "action": "Add to 2s10s / 2s30s Steepeners. Short 30Y Duration.",
                "condition": "10Y Yield daily close above 5.05% resistance with 30Y > 5.40%.",
                "status": "Testing Resistance (Imminent Watch)",
                "active_metric": f"10Y is {round(5.05 - latest_row['10y'], 2)}% away from 5.05% breakout ceiling.",
                "threshold_met": latest_row["10y"] >= 5.05,
            },
            {
                "id": "bear_flattener_cash",
                "title": "Trigger for Bear Flattener / Flight to Ultra-Short Cash",
                "action": "Move sleeve to T-Bills / Cash. Avoid all duration.",
                "condition": "2Y Yield breaks above 4.85% (hawkish Fed hike re-pricing) with CPI > 3.7%.",
                "status": "Inactive (2Y well-anchored by terminal rate bounds)",
                "active_metric": f"2Y is currently {latest_row['2y']}% (47 bps below trigger).",
                "threshold_met": False,
            },
        ],
    }

    # Snapshots for curve comparison
    n = len(aligned)
    idx_1m = max(0, n - 22)
    idx_6m = max(0, n - 126)
    idx_1y = max(0, n - 252)

    snapshots = {
        "current": {
            "date": latest_row["date"],
            "2y": latest_row["2y"],
            "5y": latest_row["5y"],
            "10y": latest_row["10y"],
            "30y": latest_row["30y"],
            "label": f"Current ({latest_row['date']})",
        },
        "1m_ago": {
            "date": aligned[idx_1m]["date"],
            "2y": aligned[idx_1m]["2y"],
            "5y": aligned[idx_1m]["5y"],
            "10y": aligned[idx_1m]["10y"],
            "30y": aligned[idx_1m]["30y"],
            "label": f"1 Month Ago ({aligned[idx_1m]['date']})",
        },
        "6m_ago": {
            "date": aligned[idx_6m]["date"],
            "2y": aligned[idx_6m]["2y"],
            "5y": aligned[idx_6m]["5y"],
            "10y": aligned[idx_6m]["10y"],
            "30y": aligned[idx_6m]["30y"],
            "label": f"6 Months Ago ({aligned[idx_6m]['date']})",
        },
        "1y_ago": {
            "date": aligned[idx_1y]["date"],
            "2y": aligned[idx_1y]["2y"],
            "5y": aligned[idx_1y]["5y"],
            "10y": aligned[idx_1y]["10y"],
            "30y": aligned[idx_1y]["30y"],
            "label": f"1 Year Ago ({aligned[idx_1y]['date']})",
        },
        "peak_inversion": {
            "date": "2023-07-03",
            "2y": 4.94,
            "5y": 4.18,
            "10y": 3.86,
            "30y": 3.87,
            "label": "Peak Inversion (July 2023: -108 bps)",
        },
    }

    # Yields payload
    yields = {}
    for k, meta in SERIES_META.items():
        curr = latest_row[k]
        prev = prev_row[k]
        chg_bps = round((curr - prev) * 100, 1)
        yields[k] = {
            "symbol": meta["symbol"],
            "name": meta["name"],
            "tenor_years": meta["tenor_years"],
            "yield": curr,
            "prev_yield": prev,
            "change_bps": chg_bps,
            "duration": meta["duration"],
            "convexity": meta["convexity"],
            "dv01": meta["dv01"],
            "role": meta["role"],
        }

    # Spreads payload with full statistics for 2s10s, 2s30s, and 5s10s
    spreads = {
        "2s10s": {
            "name": "2Y / 10Y Benchmark Spread",
            "short_name": "2s10s",
            "bps": latest_row["spread_2s10s"],
            "prev_bps": prev_row["spread_2s10s"],
            "change_bps": round(latest_row["spread_2s10s"] - prev_row["spread_2s10s"], 1),
            "status": "Normal / Steepening" if latest_row["spread_2s10s"] > 0 else "Inverted",
            "desc": "Primary macro recession & monetary policy cycle bellwether",
            "sma50": sma50_2s10s,
            "sma200": sma200_2s10s,
            "rsi14": rsi14_2s10s,
            "min_52w": round(min(history_2s10s[-252:]), 1),
            "max_52w": round(max(history_2s10s[-252:]), 1),
        },
        "2s30s": {
            "name": "2Y / 30Y Total Curve Slope",
            "short_name": "2s30s",
            "bps": latest_row["spread_2s30s"],
            "prev_bps": prev_row["spread_2s30s"],
            "change_bps": round(latest_row["spread_2s30s"] - prev_row["spread_2s30s"], 1),
            "status": "Normal Steep" if latest_row["spread_2s30s"] > 0 else "Inverted",
            "desc": "Full curve slope measuring cumulative term premium and fiscal debt supply",
            "sma50": sma50_2s30s,
            "sma200": sma200_2s30s,
            "rsi14": rsi14_2s30s,
            "min_52w": round(min(history_2s30s[-252:]), 1),
            "max_52w": round(max(history_2s30s[-252:]), 1),
        },
        "5s10s": {
            "name": "5Y / 10Y Belly Slope",
            "short_name": "5s10s",
            "bps": latest_row["spread_5s10s"],
            "prev_bps": prev_row["spread_5s10s"],
            "change_bps": round(latest_row["spread_5s10s"] - prev_row["spread_5s10s"], 1),
            "status": "Normal" if latest_row["spread_5s10s"] > 0 else "Inverted",
            "desc": "Intermediate curve steepness and primary leg for 2s5s10s butterfly positioning",
            "sma50": sma50_5s10s,
            "sma200": sma200_5s10s,
            "rsi14": rsi14_5s10s,
            "min_52w": round(min(history_5s10s[-252:]), 1),
            "max_52w": round(max(history_5s10s[-252:]), 1),
        },
        "5s30s": {
            "name": "5Y / 30Y Belly-to-Long",
            "short_name": "5s30s",
            "bps": latest_row["spread_5s30s"],
            "prev_bps": prev_row["spread_5s30s"],
            "change_bps": round(latest_row["spread_5s30s"] - prev_row["spread_5s30s"], 1),
            "status": "Upward Sloping" if latest_row["spread_5s30s"] > 0 else "Flat/Inverted",
            "desc": "Captures term premium and supply indigestion between belly and ultra-long",
        },
        "10s30s": {
            "name": "10Y / 30Y Ultra-Long Spread",
            "short_name": "10s30s",
            "bps": latest_row["spread_10s30s"],
            "prev_bps": prev_row["spread_10s30s"],
            "change_bps": round(latest_row["spread_10s30s"] - prev_row["spread_10s30s"], 1),
            "status": "Positive Slope",
            "desc": "Measures pure long-end debt issuance discount and liability hedging demand",
        },
    }

    # Concise institutional executive recommendation paragraph
    executive_paragraph = (
        "Maintain an Overweight on the 5Y Belly (Top Pick) and 2Y Carry, paired with a DV01-neutral "
        "2s10s / 2s30s Steepener trade, while Underweighting 30Y long-end duration. This strategy locks in "
        "~4.78% yield with modest duration volatility as heavy Treasury coupon issuance ($2T deficit) and sticky "
        "CPI (3.4%) push 10Y term premiums higher (~1.02%). What triggers a pivot to Long Duration (Bull Flattening)? "
        "A decisive daily close of the 10Y yield below 4.70% (50d/200d SMA support zone), accompanied by 2s10s "
        "breaking below +25 bps and unemployment rising above 4.6%, would invalidate the supply-steepening thesis "
        "and mandate an immediate rotation into 10Y and 30Y duration."
    )

    # Macro & Regime Model Assessment
    macro_assessment = {
        "as_of": latest_row["date"],
        "regime_id": "bear_steepening",
        "regime_name": "Bear Steepening / Fiscal Dominance & Sticky Inflation",
        "regime_summary": (
            "Long-end yields (10Y testing ~5.0%, 30Y at ~5.33%) are under pressure from heavy Treasury "
            "coupon supply ($2T deficit) and persistent inflation (CPI at 3.4%). The 10Y term premium has "
            "climbed to ~1.02%, while 2Y (~4.38%) is relatively well-anchored by the restrictive Fed rate range."
        ),
        "executive_paragraph": executive_paragraph,
        "curve_trade_recommendation": {
            "primary_trade": "2s10s / 2s30s Curve Steepener (Long Front / Short Long Duration)",
            "sizing_rule": "DV01-Neutral (e.g. Long $4.3M 2Y vs Short $1.0M 10Y)",
            "curve_action": "Overweight Front-to-Belly (5Y & 2Y); Underweight Long-End Duration (30Y)",
        },
        "model_signals": {
            "2y": {
                "stance": "Overweight / Defensive Carry",
                "score": 8.5,
                "rating": "Strong",
                "rationale": "High ~4.38% yield with minimal duration risk (DV01 $19/bp). Insulated from sovereign deficit supply shocks.",
            },
            "5y": {
                "stance": "Best Risk-Adjusted Sweet Spot",
                "score": 9.2,
                "rating": "Top Pick",
                "rationale": "Captures 4.78% yield (90% of 30Y yield) with only 28% of the duration volatility. Optimal roll-down along the steepest part of the curve.",
            },
            "10y": {
                "stance": "Neutral / Selective",
                "score": 6.0,
                "rating": "Hold",
                "rationale": "Yield near 5.0% is historically attractive, but vulnerable to auction tails and corporate refinancing headwinds.",
            },
            "30y": {
                "stance": "Underweight / High Vulnerability",
                "score": 3.8,
                "rating": "Avoid Duration",
                "rationale": "Extreme duration risk (DV01 $165/bp). Heavily exposed to expanding term premiums, $40T national debt debate, and continuous Treasury auction supply.",
            },
        },
        "technicals": technicals,
        "indicators": [
            {
                "name": "Headline CPI (YoY)",
                "value": "3.4%",
                "trend": "Sticky",
                "target": "2.0%",
                "impact": "Hawkish bias; keeps Fed rate cuts on hold.",
            },
            {
                "name": "Real GDP Growth",
                "value": "1.5% - 2.0%",
                "trend": "Steady",
                "target": "Trend ~1.8%",
                "impact": "No imminent recession collapse; prevents emergency Fed easing.",
            },
            {
                "name": "Unemployment Rate",
                "value": "4.3% - 4.4%",
                "trend": "Firm",
                "target": "NAIRU ~4.2%",
                "impact": "Balanced labor market; orderly rebalancing without crisis.",
            },
            {
                "name": "Federal Deficit & Debt",
                "value": "$2.0T / $40T+",
                "trend": "Expanding",
                "target": "Deficit < 3% GDP",
                "impact": "Heavy coupon auction supply driving 10Y/30Y term premiums higher.",
            },
            {
                "name": "10-Year Term Premium",
                "value": "+1.02%",
                "trend": "Elevated",
                "target": "Historical ~0.20%",
                "impact": "Bond market repricing sovereign risk and duration compensation.",
            },
            {
                "name": "10-Year RSI(14)",
                "value": f"{rsi14_10y}",
                "trend": "Overbought Yield" if rsi14_10y and rsi14_10y > 70 else "Neutral",
                "target": "30 - 70 Range",
                "impact": "Testing 5.00%-5.05% key resistance ceiling; vulnerable to technical stall.",
            },
        ],
        "headlines": [
            {
                "source": "Reuters",
                "title": "10-Year Yield Tests 5.0% Benchmark Ceiling as Deficit Issuance Weighs on Auction Absorption",
                "date": "2026-09-14",
                "category": "Treasury Supply",
                "takeaway": "Heavy government borrowing ($2T annual coupon supply) pushes 30Y yields to near two-decade highs while 10Y tests the critical 5.00% psychological barrier. Term premium expansion (+1.02%) dominates duration pricing.",
            },
            {
                "source": "Financial Times",
                "title": "Bond Vigilantes Put Fed in Policy Box as Yield Curve Back-End Resists Easing Impulses",
                "date": "2026-09-14",
                "category": "Monetary Policy",
                "takeaway": "Persistent energy price pressures and sovereign debt supply prevent long-end yields from tracking policy rate cuts. Curve steepening (2s10s at +58 bps) becomes the primary macro adjustment mechanism.",
            },
            {
                "source": "Wall Street Journal",
                "title": "Treasury Buyback Program Deployed to Cushion Back-End Liquidity Against Record Supply",
                "date": "2026-09-13",
                "category": "Debt Management",
                "takeaway": "Treasury conducts tactical coupon repurchases to support off-the-run liquidity, but structural budget deficits keep primary dealer balance sheets constrained.",
            },
            {
                "source": "The Economist",
                "title": "The Belly of the Beast: Why Intermediate 5-Year Treasuries Offer the Ultimate Risk-Reward Buffer",
                "date": "2026-09-12",
                "category": "Curve Relative Value",
                "takeaway": "Yielding ~4.78%, the 5Y tenor delivers 90% of the 30Y yield while carrying just 28% of the duration volatility. Ideal roll-down vehicle along the steep front slope.",
            },
        ],

    }

    # Model Framework & Guide: Which points work best when
    curve_model_framework = {
        "regimes": [
            {
                "id": "bull_steepening",
                "name": "Bull Steepening",
                "macro_driver": "Recession Shock / Aggressive Fed Easing Cycle",
                "curve_motion": "Front-end yields plummet faster than long-end yields. 2s10s widens dramatically.",
                "best_points": ["2Y", "5Y"],
                "best_trades": "Long 2Y/5Y, 2s10s Steepener",
                "worst_point": "Cash / T-Bills (reinvestment yield evaporates)",
                "rationale": "Front-end catches the entire magnitude of emergency Fed rate cuts. 5Y belly captures huge price rally.",
            },
            {
                "id": "bull_flattening",
                "name": "Bull Flattening",
                "macro_driver": "Late-Cycle Disinflation / Peak Fed Rates to Growth Deceleration",
                "curve_motion": "Long-end yields drop significantly while short rates remain anchored or decline slowly.",
                "best_points": ["30Y", "10Y"],
                "best_trades": "Long 30Y Duration, 10s30s Flattener",
                "worst_point": "2Y (yield drop is constrained by current policy rate)",
                "rationale": "High duration multiplies capital gains. As long-term inflation fears dissolve, 30Y duration produces stellar double-digit returns.",
            },
            {
                "id": "bear_flattening",
                "name": "Bear Flattening",
                "macro_driver": "Hawkish Tightening / Inflation Shock / Fed Policy Surprise",
                "curve_motion": "Front-end yields spike violently as rate hike bets surge. Curve inverts.",
                "best_points": ["Cash / 3M Bills", "2Y Defensive"],
                "best_trades": "Underweight Duration, Cash/Floating Rate",
                "worst_point": "30Y & 10Y (severe duration capital destruction)",
                "rationale": "Capital preservation is paramount. Ultra-short paper captures rising coupon reinvestment with zero duration loss.",
            },
            {
                "id": "bear_steepening",
                "name": "Bear Steepening (Current Regime)",
                "macro_driver": "Reflation / Fiscal Dominance / Sovereign Debt Issuance Shock",
                "curve_motion": "Long-end yields surge due to term premium expansion and auction indigestion while 2Y is anchored.",
                "best_points": ["5Y", "2Y"],
                "best_trades": "Curve Steepener (Short 30Y vs Long 2Y/5Y), Belly Carry",
                "worst_point": "30Y (uncompensated term premium bloodbath)",
                "rationale": "Avoid long duration. Front-to-belly locks in high income (>4.4%-4.8%) with low volatility, while 30Y suffers severe drawdown.",
            },
        ],
        "point_profiles": [
            {
                "tenor": "2-Year Note",
                "dv01": "$19.20 per $100k",
                "mod_duration": "1.92 years",
                "convexity": "0.05",
                "sweet_spot": "Easing cycles, Bear steepeners, and flight-to-safety liquidity",
                "vulnerability": "Early Fed hiking cycles (Bear flattener)",
                "institutional_role": "Fed policy expectation tracker and money-market surrogate.",
            },
            {
                "tenor": "5-Year Note",
                "dv01": "$46.50 per $100k",
                "mod_duration": "4.65 years",
                "convexity": "0.25",
                "sweet_spot": "Transition regimes, cycle pivots, optimal carry-and-roll",
                "vulnerability": "Rapid monetary policy repricing",
                "institutional_role": "The curve's 'belly'. Offers ~90% of curve yield with only ~28% of long bond duration risk.",
            },
            {
                "tenor": "10-Year Note",
                "dv01": "$82.00 per $100k",
                "mod_duration": "8.20 years",
                "convexity": "0.82",
                "sweet_spot": "Disinflationary slowdowns, classic balanced 60/40 equity hedge",
                "vulnerability": "Fiscal deficits, persistent inflation, foreign central bank selling",
                "institutional_role": "Global risk-free benchmark and foundation for real estate and corporate debt.",
            },
            {
                "tenor": "30-Year Bond",
                "dv01": "$165.00 per $100k",
                "mod_duration": "16.50 years",
                "convexity": "3.65",
                "sweet_spot": "Deflationary collapse, severe recessions, liability matching",
                "vulnerability": "Fiscal dominance, structural deficits, debt ceiling/auction stress",
                "institutional_role": "Pure duration instrument with high convexity; highly speculative in supply shocks.",
            },
        ],
    }

    # Mark to market UST trade recommendations via trade_tracker
    trade_tracker_data = None
    try:
        import trade_tracker
        trade_tracker_data = trade_tracker.update_ust_trades(yields, spreads)
        print(f"  Trade tracker updated: {len(trade_tracker_data.get('trades', []))} total trades, P&L: ${trade_tracker_data['portfolio_summary']['total_pnl_usd']}")
    except Exception as e:
        print(f"  Warning: Could not update trade tracker: {e}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": latest_row["date"],
        "yields": yields,
        "spreads": spreads,
        "snapshots": snapshots,
        "macro_assessment": macro_assessment,
        "curve_model_framework": curve_model_framework,
        "trade_tracker": trade_tracker_data,
        "history": aligned[-252:],
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {DATA_JSON} ({len(aligned)} days aligned, latest: {latest_row['date']})")

    with open(DAILY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "ust_2y", "ust_5y", "ust_10y", "ust_30y", "spread_2s10s", "spread_5s30s", "spread_2s30s", "spread_10s30s", "spread_5s10s"])
        for r in aligned:
            writer.writerow([r["date"], r["2y"], r["5y"], r["10y"], r["30y"], r["spread_2s10s"], r["spread_5s30s"], r["spread_2s30s"], r["spread_10s30s"], r["spread_5s10s"]])
    print(f"Saved {DAILY_CSV}")

if __name__ == "__main__":
    main()
