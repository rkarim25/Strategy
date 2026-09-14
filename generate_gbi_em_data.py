#!/usr/bin/env python3
"""
Generate gbi_em_data.json for GBI-EM Local Currency Sovereign Debt & FX Strategy Desk
Strategy Dashboard (rkarim25.github.io/Strategy).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "gbi_em_data.json"

COUNTRIES = {
    "brazil": {
        "id": "brazil",
        "name": "Brazil",
        "flag": "🇧🇷",
        "currency": "BRL",
        "region": "LatAm",
        "credit_rating": "BB (S&P) / Ba2 (Moody's)",
        "rates": {
            "policy_rate": 10.50,
            "yield_10y": 12.20,
            "yield_5y": 12.05,
            "yield_2y": 11.75,
            "cpi_yoy": 4.20,
            "real_yield_10y": 8.00,
            "ex_ante_real_rate": 6.30,
            "stance": "Overweight Rates",
            "curve_point": "5-Year Belly (Jan 2029)",
            "instrument": "NTN-F 10.00% 01/01/2029 (Fixed-Rate Sovereign)",
            "hedging_recommendation": "Unhedged for High Carry, or FX-Hedged via 3M USD/BRL NDF to Lock in 12% Nominal",
        },
        "fx": {
            "pair": "USD/BRL",
            "spot": 5.48,
            "sma50": 5.54,
            "sma200": 5.28,
            "rsi14": 46.2,
            "carry_3m_ann": 10.2,
            "reer_valuation": "-9.2% (Cheap)",
            "stance": "Neutral / High Carry Filter",
        },
        "executive_summary": (
            "Brazil offers the highest real yields in the entire GBI-EM benchmark (~6.3% ex-ante, 8.0% nominal ex-post), "
            "providing an enormous margin of safety against currency volatility. The Copom central bank maintains an orthodox "
            "stance amidst fiscal debate. The 5Y belly of the DI curve (NTN-F 2029) is the optimal risk-adjusted point, offering "
            "steep roll-down. If currency volatility is a concern, hedging FX via 3M NDFs leaves an attractive ~6.5% carry spread over SOFR."
        ),
        "catalysts": [
            "Copom Interest Rate Decision & Monetary Policy Statement",
            "Ministry of Finance Fiscal Target Compliance (Meta Fiscal Report)",
            "National Broad Consumer Price Index (IPCA) monthly release",
        ],
        "sideways_condition": "If BRL trades in 5.40-5.60 range, clip high carry and avoid aggressive duration extensions beyond 5Y.",
    },
    "mexico": {
        "id": "mexico",
        "name": "Mexico",
        "flag": "🇲🇽",
        "currency": "MXN",
        "region": "LatAm",
        "credit_rating": "BBB (S&P) / Baa2 (Moody's)",
        "rates": {
            "policy_rate": 10.50,
            "yield_10y": 9.47,
            "yield_5y": 9.25,
            "yield_2y": 9.70,
            "cpi_yoy": 5.00,
            "real_yield_10y": 4.47,
            "ex_ante_real_rate": 4.60,
            "stance": "Neutral / Sideways Range (Flattener Bias)",
            "curve_point": "10-Year Duration vs 2Y Short (2s10s Flattener)",
            "instrument": "M-Bono 7.75% 13/11/2034 vs Short M-Bono Mar 2026",
            "hedging_recommendation": "FX-Hedged Recommended (High political & US election tariff noise on MXN)",
        },
        "fx": {
            "pair": "USD/MXN",
            "spot": 19.32,
            "sma50": 19.10,
            "sma200": 17.85,
            "rsi14": 57.4,
            "carry_3m_ann": 9.8,
            "reer_valuation": "+4.1% (Fair to Slightly Rich)",
            "stance": "Sideways / Volatile Range",
        },
        "executive_summary": (
            "Mexico presents a classic divergence between high interest rate carry and elevated institutional uncertainty. "
            "Banxico has cautiously initiated rate cuts, but judicial reform headlines and prospective USMCA tariff discussions "
            "have driven USD/MXN from 16.50 up toward 19.30+. Nominal 10Y M-Bono yields near 9.50% are historically attractive, but "
            "we recommend expressing this strictly on an FX-Hedged basis or via a 2s10s curve flattener to isolate Banxico's easing cycle."
        ),
        "catalysts": [
            "Banxico Monetary Policy Decision (pace of 25bp cuts)",
            "Implementation guidelines for judicial constitutional reforms",
            "US-Mexico bilateral trade rhetoric and cross-border manufacturing flows",
        ],
        "sideways_condition": "Market is currently sideways/rangebound (19.00 - 19.80). Avoid unhedged directional long MXN bets; focus on yield carry.",
    },
    "south_africa": {
        "id": "south_africa",
        "name": "South Africa",
        "flag": "🇿🇦",
        "currency": "ZAR",
        "region": "EMEA",
        "credit_rating": "BB- (S&P) / Ba2 (Moody's)",
        "rates": {
            "policy_rate": 8.25,
            "yield_10y": 9.15,
            "yield_5y": 8.55,
            "yield_2y": 8.10,
            "cpi_yoy": 4.60,
            "real_yield_10y": 4.55,
            "ex_ante_real_rate": 4.20,
            "stance": "Overweight Rates & FX (Top Pick EMEA)",
            "curve_point": "10-Year / Long End (R2035 Benchmark)",
            "instrument": "SAGB 8.875% 28/02/2035 (R2035)",
            "hedging_recommendation": "Unhedged (Capture Dual Tailwind of Sovereign Compression & ZAR Appreciation)",
        },
        "fx": {
            "pair": "USD/ZAR",
            "spot": 17.65,
            "sma50": 17.95,
            "sma200": 18.52,
            "rsi14": 42.1,
            "carry_3m_ann": 7.9,
            "reer_valuation": "-14.5% (Extremely Undervalued)",
            "stance": "Bullish ZAR",
        },
        "executive_summary": (
            "South Africa is the premier turnaround story in GBI-EM following the formation of the Government of National Unity (GNU). "
            "Structural power outages (loadshedding) have ceased for over 170 consecutive days, boosting GDP growth expectations. "
            "Inflation has dropped toward the SARB's 4.5% midpoint, clearing the runway for easing. The 10Y SAGB (R2035) yields ~9.15% "
            "with steep roll-down, and ZAR remains significantly undervalued on REER models. Unhedged long duration is our highest conviction EMEA call."
        ),
        "catalysts": [
            "SARB Monetary Policy Committee Interest Rate Cut announcement",
            "Medium-Term Budget Policy Statement (MTBPS) in October",
            "Eskom generation performance metrics and Transnet logistics reform updates",
        ],
        "sideways_condition": "If USD/ZAR holds below 17.90 (200d SMA), bullish trend remains intact with a target of 17.20.",
    },
    "indonesia": {
        "id": "indonesia",
        "name": "Indonesia",
        "flag": "🇮🇩",
        "currency": "IDR",
        "region": "Asia",
        "credit_rating": "BBB (S&P) / Baa2 (Moody's)",
        "rates": {
            "policy_rate": 6.25,
            "yield_10y": 6.55,
            "yield_5y": 6.40,
            "yield_2y": 6.30,
            "cpi_yoy": 2.12,
            "real_yield_10y": 4.43,
            "ex_ante_real_rate": 3.85,
            "stance": "Overweight Rates (FX-Hedged) / Neutral FX",
            "curve_point": "10-Year Benchmark (FR0100)",
            "instrument": "Surat Utang Negara (SUN) Series FR0100 6.625% 15/02/2034",
            "hedging_recommendation": "FX-Hedged via USD/IDR NDF (Current Account deficit transition implies IDR drift)",
        },
        "fx": {
            "pair": "USD/IDR",
            "spot": 15410,
            "sma50": 15720,
            "sma200": 15840,
            "rsi14": 44.0,
            "carry_3m_ann": 5.8,
            "reer_valuation": "-3.2% (Fair Value)",
            "stance": "Neutral / Sideways",
        },
        "executive_summary": (
            "Indonesia boasts exceptional price stability, with headline CPI at just 2.12%, giving Bank Indonesia (BI) substantial "
            "headroom to cut policy rates. Foreign ownership of government bonds (SUN) is historically low (~14%), providing "
            "technical headroom for inflows as global rates ease. However, transition to a modest current account deficit under "
            "the incoming administration's fiscal spending plans warrants hedging IDR currency risk via NDFs."
        ),
        "catalysts": [
            "Bank Indonesia Board of Governors rate decision",
            "Inauguration of new administration and cabinet fiscal appointments",
            "Trade balance and commodity export figures (nickel/palm oil)",
        ],
        "sideways_condition": "USD/IDR trading within 15,300 - 15,600 band. Rangebound carry play.",
    },
    "poland": {
        "id": "poland",
        "name": "Poland",
        "flag": "🇵🇱",
        "currency": "PLN",
        "region": "EMEA",
        "credit_rating": "A- (S&P) / A2 (Moody's)",
        "rates": {
            "policy_rate": 5.75,
            "yield_10y": 5.35,
            "yield_5y": 5.20,
            "yield_2y": 4.95,
            "cpi_yoy": 4.30,
            "real_yield_10y": 1.05,
            "ex_ante_real_rate": 1.40,
            "stance": "Underweight Rates / Bullish PLN vs EUR",
            "curve_point": "Short 5Y POLGB vs Long German Bunds; Long PLN vs EUR",
            "instrument": "POLGB 5.75% 25/04/2029 (DS0429)",
            "hedging_recommendation": "Long PLN currency vs EUR; Avoid domestic unhedged duration",
        },
        "fx": {
            "pair": "EUR/PLN",
            "spot": 4.28,
            "sma50": 4.29,
            "sma200": 4.31,
            "rsi14": 47.0,
            "carry_3m_ann": 3.8,
            "reer_valuation": "+2.0% (Fair)",
            "stance": "Bullish PLN (Structural Fund Inflows)",
        },
        "executive_summary": (
            "Poland has the slimmest real yields in GBI-EM (~1.05% on 10Y), rendering local bonds unappealing compared to LatAm or "
            "South Africa. The Monetary Policy Council (NBP) remains hawkish due to unfreezing energy prices, keeping policy rates "
            "at 5.75%. Conversely, substantial EU Recovery Fund disbursements provide powerful balance-of-payments support for the Zloty. "
            "The trade is Long PLN vs EUR, while underweighting domestic bond duration."
        ),
        "catalysts": [
            "NBP Rate Decision and Governor Glapinski press conference",
            "European Commission approval of subsequent KPO fund disbursements",
            "Q3 GDP flash reading and energy price subsidy legislation",
        ],
        "sideways_condition": "EUR/PLN is pinned tightly around 4.26-4.30. Low volatility carry collector.",
    },
    "india": {
        "id": "india",
        "name": "India",
        "flag": "🇮🇳",
        "currency": "INR",
        "region": "Asia",
        "credit_rating": "BBB- (S&P) / Baa3 (Moody's)",
        "rates": {
            "policy_rate": 6.50,
            "yield_10y": 6.78,
            "yield_5y": 6.72,
            "yield_2y": 6.65,
            "cpi_yoy": 3.65,
            "real_yield_10y": 3.13,
            "ex_ante_real_rate": 2.80,
            "stance": "Overweight Rates / Steady Low-Vol FX Carry",
            "curve_point": "10-Year Benchmark (7.18% GS 2033)",
            "instrument": "Indian Government Bond (IGB) 7.18% 14/08/2033 (FAR Category)",
            "hedging_recommendation": "Unhedged (RBI suppresses INR volatility; capture full 6.78% yield)",
        },
        "fx": {
            "pair": "USD/INR",
            "spot": 83.88,
            "sma50": 83.82,
            "sma200": 83.45,
            "rsi14": 58.0,
            "carry_3m_ann": 4.5,
            "reer_valuation": "+3.5% (Stable Peg-like)",
            "stance": "Ultra-Low Volatility Carry",
        },
        "executive_summary": (
            "India is the anchor asset of the GBI-EM universe following its phased 10% weight inclusion in the J.P. Morgan GBI-EM "
            "Global Diversified index. Foreign institutional inflows have averaged ~$2B/month through the Fully Accessible Route (FAR). "
            "The Reserve Bank of India (RBI) aggressively manages the rupee in an extremely narrow band (83.70 - 83.95), effectively "
            "converting IGBs into a low-volatility 6.8% dollar-equivalent carry asset. Unhedged 10Y IGB is an essential core allocation."
        ),
        "catalysts": [
            "Monthly foreign debt inflow figures into FAR sovereign bonds",
            "RBI Monetary Policy Committee meeting and inflation trajectory",
            "Union Budget fiscal deficit glide path toward 4.5% by FY26",
        ],
        "sideways_condition": "USD/INR is artificially pinned by RBI intervention. Pristine sideways carry environment.",
    },
    "colombia": {
        "id": "colombia",
        "name": "Colombia",
        "flag": "🇨🇴",
        "currency": "COP",
        "region": "LatAm",
        "credit_rating": "BB+ (S&P) / Baa2 (Moody's)",
        "rates": {
            "policy_rate": 10.75,
            "yield_10y": 10.50,
            "yield_5y": 10.15,
            "yield_2y": 9.80,
            "cpi_yoy": 6.12,
            "real_yield_10y": 4.38,
            "ex_ante_real_rate": 4.50,
            "stance": "Sideways Range / Selective Belly Carry",
            "curve_point": "5-Year TES (Nov 2029)",
            "instrument": "TES B 10.75% 28/11/2029",
            "hedging_recommendation": "FX-Hedged (Oil price volatility and fiscal deficit debate pressure COP)",
        },
        "fx": {
            "pair": "USD/COP",
            "spot": 4210,
            "sma50": 4120,
            "sma200": 3980,
            "rsi14": 62.5,
            "carry_3m_ann": 9.2,
            "reer_valuation": "-4.8% (Slightly Cheap)",
            "stance": "Neutral / Sideways Volatility",
        },
        "executive_summary": (
            "Colombia offers high nominal yields (~10.50%) and double-digit policy rates (10.75%), but fiscal rule flexibility "
            "debates and oil production decline risks create drag. While carry is attractive, COP is prone to sudden headline "
            "depreciation spikes. We classify Colombia as Sideways Range: clip carry in the 5Y TES belly on an FX-hedged basis, "
            "with tight stop losses on unhedged exposure above 4,300 on USD/COP."
        ),
        "catalysts": [
            "BanRep interest rate decision and cut increments",
            "Fiscal Rule Autonomous Committee (CARF) deficit updates",
            "Brent crude oil price action and hydrocarbon tax reform debates",
        ],
        "sideways_condition": "Market is sideways/choppy between 4,050 and 4,300 USD/COP. Stand aside or hedge.",
    },
    "turkey": {
        "id": "turkey",
        "name": "Turkey",
        "flag": "🇹🇷",
        "currency": "TRY",
        "region": "EMEA",
        "credit_rating": "BB- (S&P) / B1 (Moody's)",
        "rates": {
            "policy_rate": 50.00,
            "yield_10y": 32.50,
            "yield_5y": 36.80,
            "yield_2y": 42.10,
            "cpi_yoy": 51.97,
            "real_yield_10y": -19.47,
            "ex_ante_real_rate": 5.00,
            "stance": "Ultra-Short Carry Only / Avoid Long-End Duration",
            "curve_point": "1M - 3M Front-End Deposits & T-Bills",
            "instrument": "Short-dated Turkish Treasury Bills / TRY Cash Deposits",
            "hedging_recommendation": "Unhedged Short-Term Roll (50% annualized nominal carry exceeds 25-30% annualized TRY depreciation)",
        },
        "fx": {
            "pair": "USD/TRY",
            "spot": 33.95,
            "sma50": 33.50,
            "sma200": 32.10,
            "rsi14": 68.0,
            "carry_3m_ann": 44.0,
            "reer_valuation": "+12.0% (Real Appreciation Driven by Inflation)",
            "stance": "Controlled Depreciation (High Carry Play)",
        },
        "executive_summary": (
            "Turkey's transition to orthodox economic management under Minister Simsek and TCMB Governor Karahan has rebuilt foreign "
            "exchange reserves to record highs and triggered sovereign credit upgrades. While nominal headline inflation is ~52%, "
            "it is rapidly decelerating toward ~38% year-end. Long-end bonds (10Y at 32.5%) have deeply inverted curves and unanchored "
            "term premiums. The trade is strictly 1M to 3M front-end cash carry (earning ~45-50% annualized) where carry comfortably "
            "outpaces the controlled ~20-25% annual pace of currency depreciation."
        ),
        "catalysts": [
            "TCMB Monetary Policy Committee policy rate decision",
            "Monthly headline and core CPI inflation releases",
            "Central bank gross and net international reserve accumulation reports",
        ],
        "sideways_condition": "USD/TRY crawls upward in a controlled linear slope. Continuous roll required.",
    },
}

def main():
    print("Generating GBI-EM Local Currency Sovereign Debt & FX dataset...")
    
    # Calculate rankings by real yield
    ranked_by_real_yield = sorted(
        COUNTRIES.values(),
        key=lambda x: x["rates"]["real_yield_10y"],
        reverse=True
    )
    
    executive_paragraph = (
        "Across GBI-EM local currency debt, real yield differentials remain the dominant performance driver. "
        "Brazil (NTN-F 2029 at ~12.05%, real yield ~6.3%) and South Africa (SAGB R2035 at ~9.15%, real yield ~4.5%) "
        "are our highest-conviction Overweights. South Africa benefits from a historic political turnaround (GNU) and "
        "undervalued ZAR, while Brazil offers unmatched carry buffer. India provides an exceptional low-volatility anchor "
        "via ongoing GBI-EM index inclusion inflows. Conversely, Mexico and Colombia are classified as Sideways/Rangebound: "
        "attractive nominal carry is offset by institutional headline noise and US election trade policy risks, dictating "
        "an FX-hedged approach or selective curve flatteners."
    )
    
    # Mark to market GBI-EM trades
    trade_tracker_data = None
    try:
        import trade_tracker
        trade_tracker_data = trade_tracker.update_gbi_em_trades(COUNTRIES)
        print(f"  GBI-EM trade tracker updated: Total P&L: ${trade_tracker_data['portfolio_summary']['total_pnl_usd']}")
    except Exception as e:
        print(f"  Warning: Could not update trade tracker in GBI-EM: {e}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "executive_paragraph": executive_paragraph,
        "trade_tracker": trade_tracker_data,
        "countries": COUNTRIES,
        "ranking_by_real_yield": [c["id"] for c in ranked_by_real_yield],
        "regional_breakdown": {
            "LatAm": ["brazil", "mexico", "colombia"],
            "EMEA": ["south_africa", "poland", "turkey"],
            "Asia": ["indonesia", "india"],
        },
    }
    
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {DATA_JSON} ({len(COUNTRIES)} countries)")

if __name__ == "__main__":
    main()
