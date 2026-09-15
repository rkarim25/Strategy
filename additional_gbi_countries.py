# -*- coding: utf-8 -*-
"""
expand_gbi_em_all_countries.py
Expands the GBI-EM universe to all 17 official constituents with institutional data:
LatAm: Brazil, Mexico, Colombia, Chile, Peru
EMEA: South Africa, Poland, Czech Republic, Hungary, Romania, Turkey, Egypt
Asia: Indonesia, India, Malaysia, Thailand, Philippines
"""

import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

# 9 New Countries Data
NEW_COUNTRIES = {
    "chile": {
        "id": "chile",
        "name": "Chile",
        "flag": "🇨🇱",
        "currency": "CLP",
        "region": "LatAm",
        "credit_rating": "A (S&P) / A2 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 5.50,
            "policy_rate_name": "Banco Central de Chile (BCCh) TPM",
            "trailing_cpi_yoy": 4.40,
            "forward_inflation_12m": 3.20,
            "forward_inflation_source": "BCCh Encuesta de Expectativas Económicas (EEE)",
            "ex_ante_real_policy_rate": 2.30,
            "ex_ante_math": "5.50% (Policy Rate) − 3.20% (12M Forward CPI) = +2.30%",
            "yield_10y_nominal": 5.35,
            "ex_ante_real_yield_10y": 2.15,
            "ex_post_real_yield_10y": 0.95,
            "ex_post_math": "5.35% (10Y Yield) − 4.40% (Trailing CPI) = +0.95%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -4.2,
            "reer_valuation_tag": "Slightly Undervalued (-4.2% vs 10Y Mean)",
            "terms_of_trade_index": 110.2,
            "terms_of_trade_trend": "Sharply Expanding (LME Copper at $4.22/lb; top copper exporter)",
            "current_account_pct_gdp": -3.2,
            "fx_reserves_bn": 44.8,
            "import_cover_months": 6.1,
            "quadrant_id": "quadrant_1",
            "quadrant_name": "Quadrant 1: Double Alpha (Copper Terms of Trade + Cheap REER)",
            "framework_recommendation": "Overweight 5Y/10Y BTP Duration unhedged or hedged; Long CLP on copper export windfalls."
        },
        "rates_execution": {
            "directive": "Receive Fixed (5Y/10Y BTP Duration)",
            "swap_instrument": "CLP Camara OIS (Promedio Cámara): 2Y, 5Y, 10Y tenors",
            "cash_instrument": "Bonos de Tesorería BTP 03/01/2034 5.30% (10Y Benchmark) & BCU (UF Linkers)",
            "liquidity_tier": "Tier 1 (LatAm High Grade Investment Grade)",
            "bid_ask_spread": "1.0 - 2.0 bps in BTP benchmark; 1.5 - 2.5 bps in Camara OIS",
            "standard_market_clip": "CLP 10,000M - CLP 25,000M ($11M - $27M USD notional)",
            "clearing_venue": "ComDer Contraparte Central / Bilateral ISDA",
            "dv01_per_unit": "~$750 USD DV01 per $1M notional (~CLP 7.0M DV01 / CLP 9.3B)",
            "recommended_sizing": "Target $10,000 DV01 ($10k / 1 bp move; ~CLP 93,000,000 DV01)",
            "recommended_notional": "Buy CLP 12.5 Billion BTP 2034 (~$13.5M USD notional)",
            "trader_lingo_playbook": "Receive 10Y BTP at 5.35%. BCCh continues its calibrated easing cycle toward a 4.5% terminal TPM. Copper strength ($4.22/lb) provides a strong external anchor for spot CLP."
        },
        "rates": {
            "policy_rate": 5.50,
            "yield_10y": 5.35,
            "yield_5y": 5.10,
            "yield_2y": 5.00,
            "cpi_yoy": 4.40,
            "real_yield_10y": 0.95,
            "ex_ante_real_rate": 2.30,
            "stance": "Overweight 5Y/10Y Duration (Copper Tailwinds)",
            "curve_point": "10-Year Benchmark (BTP 2034)",
            "instrument": "BTP 5.30% 03/01/2034 (Fixed Sovereign)",
            "hedging_recommendation": "Unhedged for Copper Beta, or FX-Hedged via Camara Swaps"
        },
        "fx": {
            "pair": "USD/CLP",
            "spot": 925.0,
            "sma50": 920.0,
            "sma200": 912.0,
            "rsi14": 54.0,
            "carry_3m_ann": 4.8,
            "reer_valuation": "-4.2% (Cheap vs 10Y Real Mean)",
            "stance": "Bullish CLP on Copper Terms of Trade"
        },
        "macro_anchors": {
            "net_oil_exposure": "-98% Net Energy Importer (Fuel imports balanced by copper)",
            "fx_reserves_bn": "$44.8B (6.1 months import cover)",
            "current_account_pct_gdp": "-3.2% of GDP (Structural narrowing)",
            "fiscal_deficit_pct_gdp": "-2.1% of GDP (Strict Fiscal Rule commitment)",
            "key_commodity_metric": "LME Copper: $4.22/lb · Lithium Carbonate: $11,500/MT"
        },
        "geopolitics": {
            "headline_theme": "Global Energy Transition & Critical Mineral Nationalization",
            "transmission_channel": "Chile supplies 28% of global mined copper and second largest lithium reserves. Bipartisan consensus maintains orthodox fiscal framework under Minister Marcel despite lithium partnership renegotiations.",
            "macro_data_anchor": "Copper export share: 52% of total exports · Sovereign Wealth Fund: $6.5B",
            "trade_influence": "High copper price elasticity ($4.22/lb) anchors the peso. Receive 10Y BTP duration as central bank eases toward neutral."
        },
        "executive_summary": "Chile combines high institutional credibility (A rating) with direct exposure to the global electrification theme via copper exports. Inflation is steadily decelerating toward the 3.0% target, giving BCCh room to ease policy rates toward 4.5%. Sovereign 10Y bonds (BTP 2034) offer attractive roll-down, while spot CLP is an optimal liquid vehicle to express bullish commodity views.",
        "catalysts": [
            {"date": "2026-10-15", "event": "BCCh Monetary Policy Meeting (TPM)", "consensus": "Cut 25 bps to 5.25%", "trade_implication": "Bullish front-to-belly curve rally."},
            {"date": "2026-11-08", "event": "INE Monthly CPI Release", "consensus": "3.1% YoY (Disinflation glide path)", "trade_implication": "Confirms ex-ante real yield expansion."}
        ],
        "sideways_condition": "USD/CLP rangebound in 905 - 945 if copper trades sideways between $4.10 - $4.30."
    },

    "peru": {
        "id": "peru",
        "name": "Peru",
        "flag": "🇵🇪",
        "currency": "PEN",
        "region": "LatAm",
        "credit_rating": "BBB (S&P) / Baa1 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 5.25,
            "policy_rate_name": "Banco Central de Reserva del Perú (BCRP) Tasa de Referencia",
            "trailing_cpi_yoy": 2.03,
            "forward_inflation_12m": 2.20,
            "forward_inflation_source": "BCRP Encuesta de Expectativas Macroeconómicas",
            "ex_ante_real_policy_rate": 3.05,
            "ex_ante_math": "5.25% (Policy Rate) − 2.20% (12M Forward CPI) = +3.05%",
            "yield_10y_nominal": 5.85,
            "ex_ante_real_yield_10y": 3.65,
            "ex_post_real_yield_10y": 3.82,
            "ex_post_math": "5.85% (10Y Yield) − 2.03% (Trailing CPI) = +3.82%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -2.5,
            "reer_valuation_tag": "Fair Value (-2.5% vs 10Y Mean)",
            "terms_of_trade_index": 108.5,
            "terms_of_trade_trend": "Expanding (Copper $4.22/lb + Record Gold $2,580/oz)",
            "current_account_pct_gdp": 1.2,
            "fx_reserves_bn": 82.5,
            "import_cover_months": 15.5,
            "quadrant_id": "quadrant_2",
            "quadrant_name": "Quadrant 2: High Real Yield + Controlled FX Volatility",
            "framework_recommendation": "Overweight 10Y Soberanos (BTP 2034) Unhedged. Massive $82.5B reserves insulate PEN currency."
        },
        "rates_execution": {
            "directive": "Receive Fixed (10Y Bonos Soberanos)",
            "swap_instrument": "PEN Tasa de Interés Interbancaria (OIS) & USD/PEN NDFs",
            "cash_instrument": "Bonos Soberanos 5.75% 12/08/2034 (BTP 2034 Benchmark)",
            "liquidity_tier": "Tier 2 (Liquid Cash Sovereign Bonds; Tight Central Bank Peg)",
            "bid_ask_spread": "1.5 - 2.5 bps in Soberanos 2034; 2.0 - 3.5 bps in swaps",
            "standard_market_clip": "PEN 30M - PEN 75M ($8M - $20M USD notional)",
            "clearing_venue": "CAVALI Central Depository / Bilateral ISDA",
            "dv01_per_unit": "~$720 USD DV01 per $1M notional (~PEN 2,700 DV01 / PEN 3.75M)",
            "recommended_sizing": "Target $7,500 DV01 ($7.5k / 1 bp move; ~PEN 28,000 DV01)",
            "recommended_notional": "Buy PEN 39 Million Soberanos 2034 (~$10.4M USD notional) Unhedged",
            "trader_lingo_playbook": "Receive 10Y Soberanos at 5.85%. Peru is the only LatAm country with headline inflation already back inside target (2.03% vs 1-3% band). BCRP holds $82.5B in FX reserves (~30% of GDP), eliminating currency drawdown risk."
        },
        "rates": {
            "policy_rate": 5.25,
            "yield_10y": 5.85,
            "yield_5y": 5.40,
            "yield_2y": 5.10,
            "cpi_yoy": 2.03,
            "real_yield_10y": 3.82,
            "ex_ante_real_rate": 3.05,
            "stance": "Overweight 10Y Soberanos (Inflation at 2% Target)",
            "curve_point": "10-Year Benchmark (Soberano 2034)",
            "instrument": "Bonos Soberanos 5.75% 12/08/2034",
            "hedging_recommendation": "Unhedged for Carry (BCRP manages Sol in tight range)"
        },
        "fx": {
            "pair": "USD/PEN",
            "spot": 3.76,
            "sma50": 3.75,
            "sma200": 3.74,
            "rsi14": 51.0,
            "carry_3m_ann": 4.5,
            "reer_valuation": "-2.5% (Fair Value)",
            "stance": "Neutral / Ultra-Low Volatility Sol"
        },
        "macro_anchors": {
            "net_oil_exposure": "-70% Net Energy Importer (Cushioned by mining surpluses)",
            "fx_reserves_bn": "$82.5B (15.5 months import cover; 30% of GDP)",
            "current_account_pct_gdp": "+1.2% of GDP (Current Account Surplus)",
            "fiscal_deficit_pct_gdp": "-2.8% of GDP",
            "key_commodity_metric": "Copper: $4.22/lb · Gold: $2,580/oz · Zinc: $2,900/MT"
        },
        "geopolitics": {
            "headline_theme": "Chancay Megaport Opening & Asian Commodity Gateway",
            "transmission_channel": "Opening of the $3.5B Cosco Chancay deep-water port cuts shipping time to Shanghai by 15 days, consolidating Peru as South America's primary Pacific trade hub. Insulates balance of payments.",
            "macro_data_anchor": "BCRP Total Net Reserves: $82.5B · External Debt: 35% of GDP",
            "trade_influence": "BCRP's immense reserve buffer neutralizes domestic political noise. Unhedged Soberano duration offers pure real yield with quasi-dollar stability."
        },
        "executive_summary": "Peru represents the most pristine inflation backdrop in GBI-EM, with headline CPI at 2.03% right in the center of BCRP's 1-3% target band. With a current account surplus, record gold prices, and $82.5B in FX reserves, Peruvian Bonos Soberanos offer an attractive +3.65% ex-ante real yield with near-zero currency tail risk.",
        "catalysts": [
            {"date": "2026-10-10", "event": "BCRP Monetary Policy Decision", "consensus": "Hold or cut 25 bps to 5.00%", "trade_implication": "Supports curve steepener out of belly."},
            {"date": "2026-11-14", "event": "APEC Leaders Summit & Chancay Port Inauguration", "consensus": "Boost to FDI commitments", "trade_implication": "Underpins Sol balance of payments."}
        ],
        "sideways_condition": "USD/PEN strictly pinned in 3.73 - 3.78 corridor by BCRP intervention."
    },

    "czech_republic": {
        "id": "czech_republic",
        "name": "Czech Republic",
        "flag": "🇨🇿",
        "currency": "CZK",
        "region": "EMEA",
        "credit_rating": "AA- (S&P) / Aa3 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 4.25,
            "policy_rate_name": "Czech National Bank (CNB) 2-Week Repo Rate",
            "trailing_cpi_yoy": 2.20,
            "forward_inflation_12m": 2.10,
            "forward_inflation_source": "CNB Survey of Financial Market Analysts (FMAS)",
            "ex_ante_real_policy_rate": 2.15,
            "ex_ante_math": "4.25% (Policy Rate) − 2.10% (12M Forward CPI) = +2.15%",
            "yield_10y_nominal": 3.85,
            "ex_ante_real_yield_10y": 1.75,
            "ex_post_real_yield_10y": 1.65,
            "ex_post_math": "3.85% (10Y Yield) − 2.20% (Trailing CPI) = +1.65%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": 1.5,
            "reer_valuation_tag": "Fair Value (+1.5% vs 10Y Mean)",
            "terms_of_trade_index": 101.0,
            "terms_of_trade_trend": "Neutral (German auto manufacturing supply chain linkage)",
            "current_account_pct_gdp": 0.8,
            "fx_reserves_bn": 142.5,
            "import_cover_months": 8.5,
            "quadrant_id": "quadrant_4",
            "quadrant_name": "Quadrant 4: High Grade Anchor / European Convergence",
            "framework_recommendation": "Overweight 5Y/10Y CZGB duration. Highest sovereign credit rating (AA-) in GBI-EM."
        },
        "rates_execution": {
            "directive": "Receive Fixed (10Y CZGB Duration)",
            "swap_instrument": "CZK PRIBOR IRS / CZEONIA OIS: 2Y, 5Y, 10Y tenors",
            "cash_instrument": "Czech Government Bonds (CZGB) 2.00% 10/13/2033 (10Y Benchmark)",
            "liquidity_tier": "Tier 1 (Highest Sovereign Rating in GBI-EM; LCH Cleared Swaps)",
            "bid_ask_spread": "0.75 - 1.25 bps in 5Y/10Y IRS; 1.0 - 1.5 bps in CZGBs",
            "standard_market_clip": "CZK 250M - CZK 500M ($11M - $22M USD notional)",
            "clearing_venue": "LCH Cleared (Offshore) / Centrální depozitář (CDCP) onshore",
            "dv01_per_unit": "~$780 USD DV01 per $1M notional (~CZK 17,500 DV01 / CZK 22.5M)",
            "recommended_sizing": "Target $10,000 DV01 ($10k / 1 bp move; ~CZK 225,000 DV01)",
            "recommended_notional": "Buy CZK 290 Million CZGB 2033 (~$12.8M USD notional)",
            "trader_lingo_playbook": "Receive 10Y CZGB at 3.85%. CNB has successfully returned headline inflation to the 2.0% target. Low debt-to-GDP (44%) and AA- rating make CZGBs the ultimate flight-to-quality sovereign asset in CEE."
        },
        "rates": {
            "policy_rate": 4.25,
            "yield_10y": 3.85,
            "yield_5y": 3.65,
            "yield_2y": 3.70,
            "cpi_yoy": 2.20,
            "real_yield_10y": 1.65,
            "ex_ante_real_rate": 2.15,
            "stance": "Overweight CZGB Duration (AA- Sovereign Quality)",
            "curve_point": "10-Year Benchmark (CZGB 2033)",
            "instrument": "CZGB 2.00% 10/13/2033 (Fixed Sovereign)",
            "hedging_recommendation": "Unhedged or FX-Hedged vs EUR via 3M Forwards"
        },
        "fx": {
            "pair": "EUR/CZK",
            "spot": 25.10,
            "sma50": 25.15,
            "sma200": 25.05,
            "rsi14": 49.0,
            "carry_3m_ann": 3.8,
            "reer_valuation": "+1.5% (Fair Value)",
            "stance": "Neutral / Resilient Koruna"
        },
        "macro_anchors": {
            "net_oil_exposure": "-95% Net Energy Importer (Nuclear & renewables expanding)",
            "fx_reserves_bn": "$142.5B (Massive 50% of GDP; 8.5 months import cover)",
            "current_account_pct_gdp": "+0.8% of GDP",
            "fiscal_deficit_pct_gdp": "-2.3% of GDP (Fiscal consolidation underway)",
            "key_commodity_metric": "Brent Crude: $74.20/bbl · European Natural Gas (TTF): €36/MWh"
        },
        "geopolitics": {
            "headline_theme": "European Automotive Transition & Energy Diversification",
            "transmission_channel": "Complete decoupling from Russian pipeline gas and heavy industrial integration into EU supply chains protects fiscal solvency.",
            "macro_data_anchor": "Debt-to-GDP: 44.0% (Lowest in Central Europe) · CNB FX Reserves: $142B",
            "trade_influence": "Fiscal consolidation and AA- rating provide immense duration anchor. Receive 10Y CZGB to capture European yield convergence."
        },
        "executive_summary": "The Czech Republic represents the highest credit quality in the J.P. Morgan GBI-EM benchmark (AA-). Inflation is anchored near the 2.0% target, and debt-to-GDP is among the lowest in the OECD at 44%. With massive central bank reserves ($142B), CZGBs offer the premier high-grade duration sanctuary in emerging markets.",
        "catalysts": [
            {"date": "2026-09-25", "event": "CNB Bank Board Rate Decision", "consensus": "Cut 25 bps to 4.00%", "trade_implication": "Drives front-end yield compression."},
            {"date": "2026-10-11", "event": "Czech Statistical Office CPI Release", "consensus": "2.1% YoY headline", "trade_implication": "Confirms price stability."}
        ],
        "sideways_condition": "EUR/CZK trading in tight 24.90 - 25.30 corridor."
    },

    "hungary": {
        "id": "hungary",
        "name": "Hungary",
        "flag": "🇭🇺",
        "currency": "HUF",
        "region": "EMEA",
        "credit_rating": "BBB- (S&P) / Baa2 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 6.75,
            "policy_rate_name": "Magyar Nemzeti Bank (MNB) Base Rate",
            "trailing_cpi_yoy": 3.40,
            "forward_inflation_12m": 3.50,
            "forward_inflation_source": "MNB Survey of Market Expectations",
            "ex_ante_real_policy_rate": 3.25,
            "ex_ante_math": "6.75% (Policy Rate) − 3.50% (12M Forward CPI) = +3.25%",
            "yield_10y_nominal": 6.45,
            "ex_ante_real_yield_10y": 2.95,
            "ex_post_real_yield_10y": 3.05,
            "ex_post_math": "6.45% (10Y Yield) − 3.40% (Trailing CPI) = +3.05%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -6.5,
            "reer_valuation_tag": "Undervalued (-6.5% vs 10Y Mean)",
            "terms_of_trade_index": 98.2,
            "terms_of_trade_trend": "Neutral / Net Energy Importer balanced by EV FDI (CATL, BYD)",
            "current_account_pct_gdp": 1.4,
            "fx_reserves_bn": 46.2,
            "import_cover_months": 4.5,
            "quadrant_id": "quadrant_2",
            "quadrant_name": "Quadrant 2: High CEE Carry + Cheap REER",
            "framework_recommendation": "Overweight 5Y HGB / BUBOR Swaps or tactical Long HUF carry vs EUR. Size disciplined due to EU dispute risk."
        },
        "rates_execution": {
            "directive": "Receive 5Y HGB / BUBOR IRS (Top Carry in CEE)",
            "swap_instrument": "HUF BUBOR IRS (6M BUBOR / HONIA OIS): 3Y & 5Y tenors",
            "cash_instrument": "Hungarian Government Bonds (HGB) 2034/A 6.75% 10/22/2034 (10Y Benchmark)",
            "liquidity_tier": "Tier 2 (High Beta European Market; Liquid Swaps on LCH)",
            "bid_ask_spread": "1.5 - 2.5 bps in 5Y BUBOR IRS; 2.0 - 3.5 bps in HGB cash",
            "standard_market_clip": "HUF 3,000M - HUF 6,000M ($8M - $17M USD notional)",
            "clearing_venue": "LCH Cleared (Offshore) / KELER CCP (Budapest)",
            "dv01_per_unit": "~$700 USD DV01 per $1M notional (~HUF 2.45M DV01 / HUF 350M)",
            "recommended_sizing": "Target $7,500 DV01 ($7.5k / 1 bp move; ~HUF 26,000,000 DV01)",
            "recommended_notional": "Buy HUF 3.8 Billion HGB 2034 (~$10.7M USD notional)",
            "trader_lingo_playbook": "Receive 5Y HGB at 6.30% or BUBOR swaps. Hungary offers the highest orthodox carry in Europe (6.75% base rate vs 3.4% CPI = +3.25% real). Express carry selectively; cap position sizing due to periodic EU fund withholding disputes."
        },
        "rates": {
            "policy_rate": 6.75,
            "yield_10y": 6.45,
            "yield_5y": 6.30,
            "yield_2y": 6.15,
            "cpi_yoy": 3.40,
            "real_yield_10y": 3.05,
            "ex_ante_real_rate": 3.25,
            "stance": "Overweight 5Y Belly (Top Carry in CEE)",
            "curve_point": "5-Year Belly (HGB 2029)",
            "instrument": "HGB 2034/A 6.75% 10/22/2034",
            "hedging_recommendation": "Unhedged for Carry (HUF +5.8% 3M carry over EUR)"
        },
        "fx": {
            "pair": "EUR/HUF",
            "spot": 394.50,
            "sma50": 393.20,
            "sma200": 390.50,
            "rsi14": 56.0,
            "carry_3m_ann": 5.8,
            "reer_valuation": "-6.5% (Cheap vs 10Y Real Mean)",
            "stance": "Bullish HUF Carry Play"
        },
        "macro_anchors": {
            "net_oil_exposure": "-90% Net Energy Importer (Oil & gas pipeline reliance)",
            "fx_reserves_bn": "$46.2B (4.5 months import cover)",
            "current_account_pct_gdp": "+1.4% of GDP (Current account in surplus)",
            "fiscal_deficit_pct_gdp": "-4.5% of GDP (Deficit reduction priority)",
            "key_commodity_metric": "TTF Natural Gas: €36/MWh · Crude: $74.20/bbl"
        },
        "geopolitics": {
            "headline_theme": "EU Rule-of-Law Negotiations & Chinese EV Battery Investments",
            "transmission_channel": "Tensions with Brussels over judicial reforms periodically delay EU recovery disbursements, but massive Chinese direct investment in EV battery plants (CATL Debrecen $7.6B, BYD Szeged) delivers heavy capital account financing.",
            "macro_data_anchor": "FDI Commitments: >$10B/yr · External Debt: 68% of GDP",
            "trade_influence": "High carry cushion (+3.25% ex-ante real) provides buffer against EU headlines. Size at $7.5k DV01 to harvest +5.8% carry."
        },
        "executive_summary": "Hungary provides the premier yield and carry vehicle in Central Europe, with a 6.75% base rate and a +3.25% ex-ante real policy rate. While headline risk regarding European Commission fund transfers persists, the current account has swung into surplus and the forint offers an attractive +5.8% carry against the euro.",
        "catalysts": [
            {"date": "2026-09-24", "event": "MNB Monetary Council Interest Rate Meeting", "consensus": "Hold at 6.75% (Cautious stance)", "trade_implication": "Locks in world-class European carry."},
            {"date": "2026-10-08", "event": "KSH Monthly Inflation Print", "consensus": "3.3% YoY headline", "trade_implication": "Validates real yield buffer."}
        ],
        "sideways_condition": "EUR/HUF oscillating in 390.00 - 398.00 range."
    },

    "romania": {
        "id": "romania",
        "name": "Romania",
        "flag": "🇷🇴",
        "currency": "RON",
        "region": "EMEA",
        "credit_rating": "BBB- (S&P) / Baa3 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 6.50,
            "policy_rate_name": "Banca Națională a României (NBR) Policy Rate",
            "trailing_cpi_yoy": 5.10,
            "forward_inflation_12m": 4.00,
            "forward_inflation_source": "NBR Survey of Financial Analysts",
            "ex_ante_real_policy_rate": 2.50,
            "ex_ante_math": "6.50% (Policy Rate) − 4.00% (12M Forward CPI) = +2.50%",
            "yield_10y_nominal": 6.65,
            "ex_ante_real_yield_10y": 2.65,
            "ex_post_real_yield_10y": 1.55,
            "ex_post_math": "6.65% (10Y Yield) − 5.10% (Trailing CPI) = +1.55%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": 5.2,
            "reer_valuation_tag": "Slightly Rich (+5.2% vs 10Y Mean)",
            "terms_of_trade_index": 97.0,
            "terms_of_trade_trend": "Pressured (Twin deficit expansion; fiscal deficit -6.9% of GDP)",
            "current_account_pct_gdp": -7.0,
            "fx_reserves_bn": 65.5,
            "import_cover_months": 5.8,
            "quadrant_id": "quadrant_3",
            "quadrant_name": "Quadrant 3: High Fiscal Risk + Managed Peg",
            "framework_recommendation": "Neutral / Underweight Duration. Receive 5Y ROGB strictly on an FX-Hedged basis; avoid long-end bonds."
        },
        "rates_execution": {
            "directive": "Receive 5Y ROGB strictly FX-Hedged / Avoid Long-End",
            "swap_instrument": "RON ROBOR IRS / EUR/RON FX Swaps",
            "cash_instrument": "Romanian Government Bonds (ROGB) 7.20% 10/28/2033 (10Y) & 2029",
            "liquidity_tier": "Tier 2 (Moderate Liquidity; High Sovereign Supply Burden)",
            "bid_ask_spread": "2.0 - 3.5 bps in 5Y ROGB; 3.0 - 5.0 bps in 10Y ROGB",
            "standard_market_clip": "RON 40M - RON 80M ($9M - $18M USD notional)",
            "clearing_venue": "Depozitarul Central onshore / Bilateral ISDA",
            "dv01_per_unit": "~$710 USD DV01 per $1M notional (~RON 3,200 DV01 / RON 4.5M)",
            "recommended_sizing": "Target $5,000 DV01 ($5k / 1 bp move; ~RON 22,500 DV01)",
            "recommended_notional": "Buy RON 32 Million ROGB 2029 (~$7.1M USD notional) FX-Hedged",
            "trader_lingo_playbook": "Receive 5Y ROGB at 6.40% FX-hedged. Romania carries the largest fiscal deficit in CEE (-6.9% GDP) and high election-year wage growth. NBR defends the EUR/RON peg tightly at ~4.975, but massive bond supply caps duration performance."
        },
        "rates": {
            "policy_rate": 6.50,
            "yield_10y": 6.65,
            "yield_5y": 6.40,
            "yield_2y": 6.20,
            "cpi_yoy": 5.10,
            "real_yield_10y": 1.55,
            "ex_ante_real_rate": 2.50,
            "stance": "Neutral / Underweight Long Duration (Fiscal Deficit Drag)",
            "curve_point": "3Y - 5Y Belly (ROGB 2029)",
            "instrument": "ROGB 7.20% 10/28/2033",
            "hedging_recommendation": "FX-Hedged vs EUR to isolate belly carry without deficit beta"
        },
        "fx": {
            "pair": "EUR/RON",
            "spot": 4.975,
            "sma50": 4.976,
            "sma200": 4.974,
            "rsi14": 50.0,
            "carry_3m_ann": 5.5,
            "reer_valuation": "+5.2% (Rich due to domestic wage growth)",
            "stance": "Managed Peg (NBR anchors rate at ~4.975)"
        },
        "macro_anchors": {
            "net_oil_exposure": "-40% Net Energy Importer (Domestic Black Sea offshore gas developing)",
            "fx_reserves_bn": "$65.5B (5.8 months import cover)",
            "current_account_pct_gdp": "-7.0% of GDP (Widest deficit in EU)",
            "fiscal_deficit_pct_gdp": "-6.9% of GDP (Excessive Deficit Procedure)",
            "key_commodity_metric": "Black Sea Gas · Brent Crude: $74.20/bbl"
        },
        "geopolitics": {
            "headline_theme": "NATO Black Sea Strategic Forward Hub & Presidential Elections",
            "transmission_channel": "Critical transit corridor for Ukrainian agricultural exports and major NATO airbase expansion (Kogalniceanu). Twin deficit expansion requires post-election fiscal tightening.",
            "macro_data_anchor": "Defense Spending: 2.5% of GDP · EU Fund Allocation: €29B PNRR",
            "trade_influence": "Persistent supply indigestion from fiscal deficit borrowing. Stick to 5Y belly paper with FX hedges; avoid 10Y duration."
        },
        "executive_summary": "Romania offers elevated nominal yields (10Y ROGB at 6.65%), but faces structural headwinds from twin deficits (fiscal deficit near 7% of GDP, current account deficit at 7%). The central bank strictly manages the EUR/RON exchange rate near 4.975, making 3Y to 5Y belly bonds with currency hedges the only viable institutional expression.",
        "catalysts": [
            {"date": "2026-10-04", "event": "NBR Board Monetary Policy Meeting", "consensus": "Hold at 6.50%", "trade_implication": "Maintains front-end carry anchor."},
            {"date": "2026-11-24", "event": "Romanian Presidential Election Round 1", "consensus": "Focus on post-election fiscal package", "trade_implication": "Key catalyst for bond supply outlook."}
        ],
        "sideways_condition": "EUR/RON artificially pegged in 4.970 - 4.985 corridor by NBR interventions."
    },

    "malaysia": {
        "id": "malaysia",
        "name": "Malaysia",
        "flag": "🇲🇾",
        "currency": "MYR",
        "region": "Asia",
        "credit_rating": "A- (S&P) / A3 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 3.00,
            "policy_rate_name": "Bank Negara Malaysia (BNM) Overnight Policy Rate (OPR)",
            "trailing_cpi_yoy": 2.00,
            "forward_inflation_12m": 2.20,
            "forward_inflation_source": "BNM / Market Consensus Inflation Forecast",
            "ex_ante_real_policy_rate": 0.80,
            "ex_ante_math": "3.00% (Policy Rate) − 2.20% (12M Forward CPI) = +0.80%",
            "yield_10y_nominal": 3.75,
            "ex_ante_real_yield_10y": 1.55,
            "ex_post_real_yield_10y": 1.75,
            "ex_post_math": "3.75% (10Y Yield) − 2.00% (Trailing CPI) = +1.75%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -8.5,
            "reer_valuation_tag": "Undervalued (-8.5% vs 10Y Mean)",
            "terms_of_trade_index": 109.0,
            "terms_of_trade_trend": "Expanding (Net LNG exporter + global semiconductor AI packaging boom)",
            "current_account_pct_gdp": 2.5,
            "fx_reserves_bn": 116.8,
            "import_cover_months": 5.5,
            "quadrant_id": "quadrant_1",
            "quadrant_name": "Quadrant 1: Double Alpha (Bullish MYR + Semiconductor Boom)",
            "framework_recommendation": "Long MYR Spot Currency (Repatriation flows); Neutral MGS duration due to slim real yield."
        },
        "rates_execution": {
            "directive": "Long MYR Currency / Neutral MGS Duration",
            "swap_instrument": "MYR KLIBOR IRS / MYOR OIS (Malaysia Overnight Rate): 5Y & 10Y",
            "cash_instrument": "Malaysian Government Securities (MGS) 3.899% 11/16/2034 (10Y) & MGII (Islamic)",
            "liquidity_tier": "Tier 1 (Deep Asian Local Market; Capped at 10% GBI-EM Weight)",
            "bid_ask_spread": "0.75 - 1.25 bps in benchmark MGS; 1.0 - 2.0 bps in KLIBOR IRS",
            "standard_market_clip": "MYR 50M - MYR 100M ($11M - $23M USD notional)",
            "clearing_venue": "PayNet / Bank Negara Malaysia RENTAS",
            "dv01_per_unit": "~$780 USD DV01 per $1M notional (~MYR 3,370 DV01 / MYR 4.32M)",
            "recommended_sizing": "Target $10,000 DV01 ($10k / 1 bp move; ~MYR 43,200 DV01)",
            "recommended_notional": "Buy MYR 55 Million MGS 2034 (~$12.8M USD notional) or Long $10M USD/MYR Forward",
            "trader_lingo_playbook": "Express Malaysian bullishness via Long MYR spot/forward. BNM OPR is steady at 3.00%; real yields are tight (+0.8% ex-ante), so MGS duration has limited alpha. However, ringgit repatriation mandates and semiconductor FDI make MYR the top trending currency in Asia."
        },
        "rates": {
            "policy_rate": 3.00,
            "yield_10y": 3.75,
            "yield_5y": 3.50,
            "yield_2y": 3.35,
            "cpi_yoy": 2.00,
            "real_yield_10y": 1.75,
            "ex_ante_real_rate": 0.80,
            "stance": "Neutral Duration / Bullish Currency (Trade via FX)",
            "curve_point": "10-Year Benchmark (MGS 2034)",
            "instrument": "MGS 3.899% 11/16/2034 (Fixed Sovereign)",
            "hedging_recommendation": "Unhedged for Ringgit Outperformance"
        },
        "fx": {
            "pair": "USD/MYR",
            "spot": 4.32,
            "sma50": 4.45,
            "sma200": 4.62,
            "rsi14": 35.0,
            "carry_3m_ann": 2.2,
            "reer_valuation": "-8.5% (Significantly Undervalued)",
            "stance": "Strong Bullish Ringgit Trend"
        },
        "macro_anchors": {
            "net_oil_exposure": "+15% Net Hydrocarbon Exporter (Petronas LNG & crude exports)",
            "fx_reserves_bn": "$116.8B (5.5 months import cover)",
            "current_account_pct_gdp": "+2.5% of GDP (Persistent surplus)",
            "fiscal_deficit_pct_gdp": "-4.3% of GDP (Subsidy rationalization underway)",
            "key_commodity_metric": "Crude Palm Oil (CPO): MYR 3,900/MT · LNG: $12.5/MMBtu"
        },
        "geopolitics": {
            "headline_theme": "Global Semiconductor Packaging Hub & Neutral Tech Sourcing",
            "transmission_channel": "Malaysia controls 13% of global semiconductor packaging, assembly, and test (OSAT) market. Benefits as the primary beneficiary of the 'China+1' supply chain relocation by Intel, Infineon, and Nvidia.",
            "macro_data_anchor": "Electronics Exports: 40% of total merchandise · Trade Surplus: +$4.5B/mo",
            "trade_influence": "Massive corporate export repatriation and tech FDI drive aggressive Ringgit appreciation. Express via short USD/MYR."
        },
        "executive_summary": "Malaysia is an economic powerhouse in the Asian GBI-EM segment, capped at the maximum 10% benchmark weight. While sovereign bond yields offer modest real yield (+0.8% policy ex-ante), the Ringgit is experiencing an institutional re-rating driven by government-linked repatriation mandates, semiconductor investment, and LNG surpluses.",
        "catalysts": [
            {"date": "2026-10-18", "event": "Malaysia Budget 2027 Tabling in Parliament", "consensus": "RON95 fuel subsidy rationalization", "trade_implication": "Strengthens fiscal sustainability."},
            {"date": "2026-11-06", "event": "Bank Negara Malaysia MPC Decision", "consensus": "Hold OPR at 3.00%", "trade_implication": "Anchors policy rate stability."}
        ],
        "sideways_condition": "USD/MYR trending downward; key support at 4.25."
    },

    "thailand": {
        "id": "thailand",
        "name": "Thailand",
        "flag": "🇹🇭",
        "currency": "THB",
        "region": "Asia",
        "credit_rating": "BBB+ (S&P) / Baa1 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 2.50,
            "policy_rate_name": "Bank of Thailand (BOT) Policy Repo Rate",
            "trailing_cpi_yoy": 0.35,
            "forward_inflation_12m": 1.20,
            "forward_inflation_source": "Bank of Thailand Inflation Report",
            "ex_ante_real_policy_rate": 1.30,
            "ex_ante_math": "2.50% (Policy Rate) − 1.20% (12M Forward CPI) = +1.30%",
            "yield_10y_nominal": 2.55,
            "ex_ante_real_yield_10y": 1.35,
            "ex_post_real_yield_10y": 2.20,
            "ex_post_math": "2.55% (10Y Yield) − 0.35% (Trailing CPI) = +2.20%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -4.5,
            "reer_valuation_tag": "Slightly Undervalued (-4.5% vs 10Y Mean)",
            "terms_of_trade_index": 105.5,
            "terms_of_trade_trend": "Expanding (Gold export windfalls + sub-$75 oil lowers import bill)",
            "current_account_pct_gdp": 2.1,
            "fx_reserves_bn": 225.4,
            "import_cover_months": 8.8,
            "quadrant_id": "quadrant_4",
            "quadrant_name": "Quadrant 4: Asian Anchor / Tourism Recovery",
            "framework_recommendation": "Overweight 5Y/10Y Thai LB Duration (BOT under easing pressure); Bullish THB on gold windfalls."
        },
        "rates_execution": {
            "directive": "Receive 5Y/10Y Thai Loan Bonds (LB Duration)",
            "swap_instrument": "THB THOR OIS (Thai Overnight Repurchase Rate) / THB IRS: 5Y & 10Y",
            "cash_instrument": "Thai Government Loan Bonds (LB) 2034 2.80% (10Y Benchmark)",
            "liquidity_tier": "Tier 1 (Core Asian Investment Grade Benchmark)",
            "bid_ask_spread": "0.75 - 1.25 bps in benchmark LB; 1.5 - 2.5 bps in THOR swaps",
            "standard_market_clip": "THB 300M - THB 600M ($9M - $18M USD notional)",
            "clearing_venue": "Bank of Thailand e-Bidding / Bilateral ISDA",
            "dv01_per_unit": "~$820 USD DV01 per $1M notional (~THB 27,400 DV01 / THB 33.4M)",
            "recommended_sizing": "Target $10,000 DV01 ($10k / 1 bp move; ~THB 334,000 DV01)",
            "recommended_notional": "Buy THB 410 Million Thai LB 2034 (~$12.2M USD notional) Unhedged",
            "trader_lingo_playbook": "Receive 10Y Thai LB at 2.55%. Headline inflation is near-zero (0.35%), creating intense government pressure on the BOT to cut rates by 25-50 bps. Record high gold prices ($2,580/oz) generate retail export windfalls that structurally support the Baht."
        },
        "rates": {
            "policy_rate": 2.50,
            "yield_10y": 2.55,
            "yield_5y": 2.30,
            "yield_2y": 2.15,
            "cpi_yoy": 0.35,
            "real_yield_10y": 2.20,
            "ex_ante_real_rate": 1.30,
            "stance": "Overweight Thai Duration (BOT Cut Cycle Coming)",
            "curve_point": "10-Year Benchmark (Thai LB 2034)",
            "instrument": "Thai LB 2.80% 2034 (Fixed Sovereign)",
            "hedging_recommendation": "Unhedged for Baht Rally on Gold Windfalls"
        },
        "fx": {
            "pair": "USD/THB",
            "spot": 33.40,
            "sma50": 34.80,
            "sma200": 35.80,
            "rsi14": 32.0,
            "carry_3m_ann": 1.8,
            "reer_valuation": "-4.5% (Slightly Undervalued)",
            "stance": "Bullish Baht on Gold Surge & Tourism"
        },
        "macro_anchors": {
            "net_oil_exposure": "-85% Net Energy Importer (Major beneficiary of sub-$75 crude)",
            "fx_reserves_bn": "$225.4B (Massive 8.8 months import cover)",
            "current_account_pct_gdp": "+2.1% of GDP (Tourism surplus)",
            "fiscal_deficit_pct_gdp": "-3.6% of GDP (Digital Wallet stimulus scaling)",
            "key_commodity_metric": "Gold: $2,580/oz (Heavy retail gold export trading) · Brent: $74.20/bbl"
        },
        "geopolitics": {
            "headline_theme": "Political Stabilization under Paetongtarn & Digital Wallet Rollout",
            "transmission_channel": "Confirmation of Paetongtarn Shinawatra as Prime Minister resolves months of political paralysis, while phased cash hand-outs boost domestic demand without derailing public debt ceiling.",
            "macro_data_anchor": "Tourist Arrivals: 36M projected · BOT FX Reserves: $225B",
            "trade_influence": "Sub-$75 Brent oil slashes energy import bill, widening current account surplus. Receive 10Y Thai LB duration as BOT pivots to easing."
        },
        "executive_summary": "Thailand provides a defensive high-grade profile in GBI-EM with headline inflation barely above zero (0.35%) and $225B in foreign reserves. The Baht is heavily correlated with gold, surging on bullion's push to record highs, while Thai government bonds (LB 2034) will benefit from impending BOT policy rate cuts.",
        "catalysts": [
            {"date": "2026-10-16", "event": "Bank of Thailand MPC Rate Decision", "consensus": "High chance of 25 bps cut to 2.25%", "trade_implication": "Triggers sovereign curve rally."},
            {"date": "2026-11-05", "event": "Ministry of Commerce CPI Report", "consensus": "0.5% YoY headline", "trade_implication": "Confirms low inflation runway."}
        ],
        "sideways_condition": "USD/THB testing strong technical support at 33.00."
    },

    "philippines": {
        "id": "philippines",
        "name": "Philippines",
        "flag": "🇵🇭",
        "currency": "PHP",
        "region": "Asia",
        "credit_rating": "BBB+ (S&P) / Baa2 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 6.25,
            "policy_rate_name": "Bangko Sentral ng Pilipinas (BSP) Target RRP",
            "trailing_cpi_yoy": 3.30,
            "forward_inflation_12m": 3.10,
            "forward_inflation_source": "BSP Survey of Private Sector Economists",
            "ex_ante_real_policy_rate": 3.15,
            "ex_ante_math": "6.25% (Policy Rate) − 3.10% (12M Forward CPI) = +3.15%",
            "yield_10y_nominal": 5.95,
            "ex_ante_real_yield_10y": 2.85,
            "ex_post_real_yield_10y": 2.65,
            "ex_post_math": "5.95% (10Y Yield) − 3.30% (Trailing CPI) = +2.65%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": 2.8,
            "reer_valuation_tag": "Fair Value (+2.8% vs 10Y Mean)",
            "terms_of_trade_index": 103.5,
            "terms_of_trade_trend": "Improving (Rice import tariff cuts + sub-$75 crude oil)",
            "current_account_pct_gdp": -2.6,
            "fx_reserves_bn": 107.9,
            "import_cover_months": 7.8,
            "quadrant_id": "quadrant_2",
            "quadrant_name": "Quadrant 2: High Asian Carry + Disinflation Easing",
            "framework_recommendation": "Overweight 5Y/10Y FXTN Duration as BSP continues front-loaded easing cycle."
        },
        "rates_execution": {
            "directive": "Receive 5Y/10Y FXTN (Fixed Rate Treasury Notes)",
            "swap_instrument": "PHP BVAL Swaps / USD/PHP NDFs: 2Y, 5Y, 10Y",
            "cash_instrument": "Fixed Rate Treasury Notes (FXTN) 10-68 6.25% 02/28/2034 (10Y Benchmark)",
            "liquidity_tier": "Tier 2 (Liquid Cash Benchmark; Semi-Liquid Swaps)",
            "bid_ask_spread": "1.5 - 2.5 bps in on-the-run FXTN; 2.5 - 4.0 bps in BVAL swaps",
            "standard_market_clip": "PHP 300M - PHP 600M ($5.3M - $10.7M USD notional)",
            "clearing_venue": "Bureau of the Treasury (BTr) RoSS / Bilateral ISDA",
            "dv01_per_unit": "~$740 USD DV01 per $1M notional (~PHP 41,500 DV01 / PHP 56M)",
            "recommended_sizing": "Target $7,500 DV01 ($7.5k / 1 bp move; ~PHP 420,000 DV01)",
            "recommended_notional": "Buy PHP 560 Million FXTN 2034 (~$10.1M USD notional)",
            "trader_lingo_playbook": "Receive 10Y FXTN 10-68 at 5.95%. BSP was the first Asian central bank to cut rates (down to 6.25%) and Governor Remolona has signaled an aggressive easing trajectory toward 5.0% by 2025 as food tariffs cool inflation."
        },
        "rates": {
            "policy_rate": 6.25,
            "yield_10y": 5.95,
            "yield_5y": 5.70,
            "yield_2y": 5.60,
            "cpi_yoy": 3.30,
            "real_yield_10y": 2.65,
            "ex_ante_real_rate": 3.15,
            "stance": "Overweight FXTN Duration (BSP Easing Leader)",
            "curve_point": "10-Year Benchmark (FXTN 10-68)",
            "instrument": "FXTN 10-68 6.25% 02/28/2034",
            "hedging_recommendation": "Unhedged for Carry (Steady $3B/mo overseas remittances)"
        },
        "fx": {
            "pair": "USD/PHP",
            "spot": 55.90,
            "sma50": 56.80,
            "sma200": 56.40,
            "rsi14": 42.0,
            "carry_3m_ann": 4.9,
            "reer_valuation": "+2.8% (Fair Value)",
            "stance": "Neutral / Steady Remittance Support"
        },
        "macro_anchors": {
            "net_oil_exposure": "-95% Net Energy Importer (Heavy crude & diesel import burden)",
            "fx_reserves_bn": "$107.9B (7.8 months import cover)",
            "current_account_pct_gdp": "-2.6% of GDP (Financed by $38B annual remittances)",
            "fiscal_deficit_pct_gdp": "-5.5% of GDP (Infrastructure buildout)",
            "key_commodity_metric": "Rice Import Tariff: cut to 15% · Brent Crude: $74.20/bbl"
        },
        "geopolitics": {
            "headline_theme": "South China Sea Maritime Stand-off & US Defense Cooperation",
            "transmission_channel": "Upgraded US-Philippine Enhanced Defense Cooperation Agreement (EDCA) brings US infrastructure financing and semiconductor packaging investment, offsetting maritime friction with Beijing.",
            "macro_data_anchor": "Overseas Worker Remittances: $3.2B/month · BSP Reserves: $108B",
            "trade_influence": "Rice tariff cuts have triggered sharp food disinflation. BSP easing leader status makes FXTN 10Y duration the highest yielding high-grade play in Southeast Asia."
        },
        "executive_summary": "The Philippines stands out as Southeast Asia's monetary easing leader, with the BSP having already initiated policy rate cuts as inflation normalized to 3.3%. Backed by $38B in resilient annual worker remittances and $108B in reserves, 10Y FXTN benchmark bonds offer an attractive +3.15% ex-ante real policy rate and steep roll-down.",
        "catalysts": [
            {"date": "2026-10-17", "event": "BSP Monetary Board Rate Decision", "consensus": "Cut 25 bps to 6.00%", "trade_implication": "Direct catalyst for FXTN belly rally."},
            {"date": "2026-11-05", "event": "PSA Inflation Announcement", "consensus": "2.9% YoY headline", "trade_implication": "Confirms sub-3% disinflation."}
        ],
        "sideways_condition": "USD/PHP consolidating between 55.50 - 56.50."
    },

    "egypt": {
        "id": "egypt",
        "name": "Egypt",
        "flag": "🇪🇬",
        "currency": "EGP",
        "region": "EMEA",
        "credit_rating": "B- (S&P) / Caa1 (Moody's)",
        "real_rate_breakdown": {
            "policy_rate": 27.25,
            "policy_rate_name": "Central Bank of Egypt (CBE) Overnight Deposit Rate",
            "trailing_cpi_yoy": 26.20,
            "forward_inflation_12m": 16.50,
            "forward_inflation_source": "CBE / IMF Program Inflation Trajectory",
            "ex_ante_real_policy_rate": 10.75,
            "ex_ante_math": "27.25% (Policy Rate) − 16.50% (12M Forward CPI) = +10.75%",
            "yield_10y_nominal": 25.50,
            "ex_ante_real_yield_10y": 9.00,
            "ex_post_real_yield_10y": -0.70,
            "ex_post_math": "25.50% (10Y Yield) − 26.20% (Trailing CPI) = -0.70%"
        },
        "tot_reer_framework": {
            "reer_deviation_pct": -22.0,
            "reer_valuation_tag": "Extremely Undervalued (-22.0% post-March 2024 float)",
            "terms_of_trade_index": 92.0,
            "terms_of_trade_trend": "Volatile (Suez Canal disruption balanced by $35B Ras El Hekma deal)",
            "current_account_pct_gdp": -3.8,
            "fx_reserves_bn": 46.5,
            "import_cover_months": 7.5,
            "quadrant_id": "quadrant_5",
            "quadrant_name": "Special Regime: Hyper-Carry Front-End Roll (Post-Devaluation)",
            "framework_recommendation": "Clip 3M - 9M Egyptian Treasury Bills unhedged (~28-29% nominal yield). Zero allocation to 10Y duration."
        },
        "rates_execution": {
            "directive": "Clip 3M-9M Front-End T-Bills / Do NOT Touch 10Y Duration",
            "swap_instrument": "USD/EGP 3M-6M Non-Deliverable Forwards (NDFs)",
            "cash_instrument": "Egyptian Treasury Bills (Azwn) 91-Day & 182-Day (Yielding ~28.5% - 29.5%)",
            "liquidity_tier": "Tier 1 (Front-End T-Bills post-$35B UAE FDI) / Tier 3 (Long-End Bonds)",
            "bid_ask_spread": "15 - 30 bps in primary T-Bill auctions; secondary market wider",
            "standard_market_clip": "EGP 100M - EGP 250M ($2M - $5M USD notional)",
            "clearing_venue": "Central Bank of Egypt / MCDR",
            "dv01_per_unit": "N/A - Managed on cash notional and carry cushion",
            "recommended_sizing": "Target $3M - $5M USD cash clip in 3M-6M T-Bills",
            "recommended_notional": "EGP 200 Million 3M T-Bills (~$4.1M USD notional) Unhedged",
            "trader_lingo_playbook": "Clip the 3M T-Bill carry at ~29% annualized. Following the historic March 2024 float and $35B UAE Ras El Hekma bailout, the CBE rebuilt reserves to $46.5B and cleared import backlogs. High nominal carry covers the controlled ~1% monthly currency slide."
        },
        "rates": {
            "policy_rate": 27.25,
            "yield_10y": 25.50,
            "yield_5y": 26.50,
            "yield_2y": 27.80,
            "cpi_yoy": 26.20,
            "real_yield_10y": -0.70,
            "ex_ante_real_rate": 10.75,
            "stance": "Ultra-Short T-Bills Carry Roll Only (Avoid Long Bonds)",
            "curve_point": "3M - 6M Front-End Treasury Bills",
            "instrument": "91-Day Egyptian Treasury Bills (~29.0% annualized yield)",
            "hedging_recommendation": "Unhedged Front-End Roll (Carry comfortably beats crawl)"
        },
        "fx": {
            "pair": "USD/EGP",
            "spot": 48.40,
            "sma50": 48.60,
            "sma200": 48.20,
            "rsi14": 48.0,
            "carry_3m_ann": 26.5,
            "reer_valuation": "-22.0% (Extremely Undervalued post-60% devaluation)",
            "stance": "Controlled Float / High Carry Play"
        },
        "macro_anchors": {
            "net_oil_exposure": "-50% Net Energy Importer (Domestic natural gas shortfalls)",
            "fx_reserves_bn": "$46.5B (Rebuilt to record high post-devaluation; 7.5 months cover)",
            "current_account_pct_gdp": "-3.8% of GDP (Stabilized by $8B IMF expanded package)",
            "fiscal_deficit_pct_gdp": "-7.5% of GDP (High interest service costs)",
            "key_commodity_metric": "Suez Canal Tolls (down 60% due to Red Sea) · Gold: $2,580/oz"
        },
        "geopolitics": {
            "headline_theme": "Red Sea Shipping Disruptions, Gaza Border Diplomacy & Gulf FDI",
            "transmission_channel": "Houthi attacks on Red Sea shipping have slashed Suez Canal revenues by ~$6B/year, but Egypt's pivotal diplomatic role and $35B UAE Ras El Hekma investment have eliminated sovereign default risk and unified the exchange rate.",
            "macro_data_anchor": "Ras El Hekma Deal: $35B · IMF Extended Facility: $8B · EU Package: €7.4B",
            "trade_influence": "Parallel market eliminated. Front-end 3M-6M T-Bills yield 29% in a stabilized currency regime. Harvest cash carry; avoid long-end duration."
        },
        "executive_summary": "Egypt represents the highest-carry frontier turnaround within the broader GBI-EM universe. The decisive March 2024 exchange rate unification, combined with the $35B UAE Ras El Hekma direct investment and an expanded $8B IMF facility, eliminated the foreign exchange backlog and rebuilt CBE net reserves to record levels. Yields of ~29% on 3M to 6M Treasury bills offer world-leading cash carry.",
        "catalysts": [
            {"date": "2026-10-17", "event": "CBE Monetary Policy Committee Meeting", "consensus": "Hold overnight deposit rate at 27.25%", "trade_implication": "Maintains 29% front-end carry."},
            {"date": "2026-11-10", "event": "CAPMAS Monthly Inflation Release", "consensus": "Deceleration toward 23% confirmed", "trade_implication": "Increases ex-ante real return."}
        ],
        "sideways_condition": "USD/EGP trading in stable 48.00 - 49.00 range post-unification."
    }
}

print(f"[OK] Defined {len(NEW_COUNTRIES)} additional sovereign profiles with institutional data.")


EXPANDED_TOT_REER_QUADRANT_MATRIX = [
    {
        "quadrant": "Quadrant 1: Double Alpha",
        "theme": "High Real Rate + Deeply Undervalued REER + Expanding ToT",
        "countries": [
            "South Africa (ZAR)",
            "Chile (CLP)",
            "Peru (PEN)"
        ],
        "macro_driver": "Record gold ($2,580/oz) and copper ($4.22/lb) boom expanding Andean and South African terms of trade; real policy rates (+2.3% to +4.3%) with structurally cheap currencies.",
        "trade_directive": "Unhedged 10Y Duration (SAGB R2035 9.15%, BTP 2034 5.35%, Soberano 2034 5.85%) + Long Currency exposure."
    },
    {
        "quadrant": "Quadrant 2: High Carry Belly Rates",
        "theme": "High Real Policy Rate + Cheap REER + Resilient ToT",
        "countries": [
            "Brazil (BRL)",
            "Indonesia (IDR)",
            "Hungary (HUF)",
            "Philippines (PHP)"
        ],
        "macro_driver": "Ex-ante real policy rates (+3.15% to +6.60%) provide robust carry buffer against global vol; inflation anchored or falling.",
        "trade_directive": "Receive 5Y-10Y Belly Rates / Swaps (NTN-F 2029, SUN FR0100, HUF IRS, PHP BVAL) unhedged or NDF-hedged."
    },
    {
        "quadrant": "Quadrant 3: FX-Hedged Duration",
        "theme": "High Real Rate + Rich/Fair REER + Tariff / Fiscal Shock Exposure",
        "countries": [
            "Mexico (MXN)",
            "Colombia (COP)",
            "Czech Republic (CZK)",
            "Romania (RON)"
        ],
        "macro_driver": "Trade and fiscal friction (USMCA tariffs for MXN, oil exploration bans for COP, European industrial stagnation & heavy bond supply for CZK & RON) requiring rates insulation.",
        "trade_directive": "Express rates via 2s10s curve flatteners (Mexico TIIE) or duration with strict FX hedging (10Y M-Bono, 5Y TES, 10Y CZGB, 10Y ROMGB)."
    },
    {
        "quadrant": "Quadrant 4: Capital Inflows / Balance of Payments Anchor",
        "theme": "Low Real Rate or Managed FX + Massive External Surplus / Foreign Inflows",
        "countries": [
            "Poland (PLN)",
            "India (INR)",
            "Malaysia (MYR)",
            "Thailand (THB)"
        ],
        "macro_driver": "Heavy structural inflows: Poland (€60B+ EU KPO conversions), India ($683B RBI reserves & $2B/mo index inflows), Malaysia (tech FDI & corporate repatriation), Thailand (tourism current account surplus).",
        "trade_directive": "Poland: Long PLN vs EUR (pay duration); India: Unhedged 10Y IGB (quasi-dollar anchor); Malaysia: Long MYR FX; Thailand: Receive 5Y/10Y Thai LB duration."
    },
    {
        "quadrant": "Special Regime: Front-End Hyper-Carry Roll",
        "theme": "Extremely High Nominal Rate + Colossal Forward Disinflation Carry",
        "countries": [
            "Turkey (TRY)",
            "Egypt (EGP)"
        ],
        "macro_driver": "Extraordinary nominal rates (TRY 50%, EGP 27.25%) backed by credible orthodox stabilization programs (CBE post-float & $35B ADQ deal; CBRT disinflation). Forward ex-ante real rates (+10.75% to +21.50%) easily absorb controlled currency crawl.",
        "trade_directive": "1M - 3M Front-End Treasury Bills (TRY Hazine Bonosu & EGP T-Bills) rolled monthly unhedged; avoid long-end duration."
    }
]

EXPANDED_GEOPOLITICAL_RISK_MATRIX = {
    "energy_shock_hormuz": {
        "title": "Middle East Energy Shock & Strait of Hormuz Chokepoint",
        "macro_metric": "Brent Crude ($74.20/bbl)",
        "winners": [
            "Colombia (COP)",
            "Brazil (BRL)",
            "Malaysia (MYR)"
        ],
        "losers": [
            "India (INR)",
            "South Africa (ZAR)",
            "Turkey (TRY)",
            "Thailand (THB)",
            "Philippines (PHP)",
            "Egypt (EGP)"
        ],
        "neutral": [
            "Indonesia (IDR)",
            "Poland (PLN)",
            "Chile (CLP)",
            "Peru (PEN)",
            "Czech Republic (CZK)",
            "Hungary (HUF)",
            "Romania (RON)"
        ],
        "strategic_guidance": "Every $10/bbl surge in Brent expands LatAm and Malaysian terms of trade while widening current account deficits across energy-poor Asia and EMEA. Long Colombia COP and Malaysia MYR serve as organic portfolio hedges against Middle East energy spikes."
    },
    "us_election_tariffs": {
        "title": "US Election Protectionism & 10-20% Universal Tariffs",
        "macro_metric": "US Dollar Index (DXY 101.40) & US 10Y (4.96%)",
        "winners": [
            "India (Domestic demand / service exports)",
            "South Africa (Commodity insulation)",
            "Malaysia (China+1 semiconductor investment hub)"
        ],
        "losers": [
            "Mexico (MXN manufacturing supply chain)",
            "Poland (German export linkage)",
            "Czech Republic (German automotive industrial linkages)",
            "Hungary (Central European auto export base)",
            "Romania (European trade dependence)"
        ],
        "neutral": [
            "Brazil (BRL)",
            "Indonesia (IDR)",
            "Chile (CLP)",
            "Peru (PEN)",
            "Thailand (THB)",
            "Philippines (PHP)",
            "Egypt (EGP)",
            "Turkey (TRY)"
        ],
        "strategic_guidance": "Looming USMCA review and European tariff exposure require strict FX hedging on Mexican M-Bonos and CEE local debt (CZGB, ROMGB) to isolate domestic interest rate carry without unhedged currency beta."
    },
    "eastern_flank_defense": {
        "title": "NATO Eastern Flank Defense Burden & Russia-Ukraine War",
        "macro_metric": "CEE Defense Spending (Poland 4.7% GDP, Romania 2.5% GDP)",
        "winners": [
            "Poland Zloty (via €60B+ EU Recovery Fund disbursements)",
            "Czech Koruna (AA- fiscal credibility & CNB policy anchor)"
        ],
        "losers": [
            "Poland & Romania Local Sovereign Bonds (Heavy supply crowding out real yields; Romanian 7.2% budget deficit)",
            "Hungary Forint (EU funding freezes & geopolitical vulnerabilities)"
        ],
        "neutral": [
            "LatAm (Brazil, Mexico, Colombia, Chile, Peru)",
            "Asia (Indonesia, India, Malaysia, Thailand, Philippines)",
            "South Africa & Egypt"
        ],
        "strategic_guidance": "Long PLN vs EUR captures sovereign EU structural conversion flows, while underweighting CEE long bond duration in favor of front-end swaps or high-yield Latin American carry."
    }
}
