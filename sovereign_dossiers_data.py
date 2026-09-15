# -*- coding: utf-8 -*-
"""
sovereign_dossiers_data.py
Provides comprehensive institutional macroeconomic dossiers for all 17 GBI-EM benchmark constituents:
- Latin America: Brazil, Mexico, Colombia, Chile, Peru
- EMEA: South Africa, Poland, Czech Republic, Hungary, Romania, Turkey, Egypt
- Emerging Asia: Indonesia, India, Malaysia, Thailand, Philippines

Each dossier contains:
- investment_thesis: Stance, horizon, high-conviction expression, narrative thesis.
- positives: 4-5 bulleted structural bull drivers.
- negatives: 4-5 bulleted structural bear risks / vulnerabilities.
- economic_structure: GDP composition (Services, Industry, Agriculture/Mining), Top exports, Top trading partners, Public debt % GDP, Foreign ownership % local debt, Banking system summary, Domestic institutional anchor.
- recent_developments: 3-4 chronological updates from the past 30-90 days.
- what_to_watch: Key trigger dates, technical invalidation levels, macro commodity sensitivity thresholds.
"""

SOVEREIGN_DOSSIERS = {
    "brazil": {
        "investment_thesis": {
            "stance": "Overweight 5Y Belly Rates (NTN-F 2029) Unhedged / Neutral Long Duration",
            "horizon": "3M - 6M Tactical Carry & Roll-Down",
            "expression": "Receive B3 DI1F29 Futures (Jan 2029) or Buy Cash NTN-F 10% 01/01/2029 at 12.05% Yield. Target $10,000 DV01 (~1,280 DI1 contracts or R$60M cash). Express unhedged for BRL carry, or hedge via 3M NDFs if USD/BRL breaks above 5.60.",
            "core_thesis": "Brazil provides one of the highest ex-ante real rates across global markets (+6.60% ex-ante: 10.50% Selic vs 3.90% 12M forward inflation survey). While fiscal sustainability debates surrounding the Lula administration's zero primary deficit target inject curve steepening volatility, the 5Y belly (NTN-F 2029) offers an optimal risk-adjusted roll-down cushion (~8.0% real yield ex-post). With $355B in FX reserves and a massive agricultural trade surplus, BRL is well-anchored against external commodity shocks, allowing investors to harvest ~10.2% annualized 3M carry."
        },
        "positives": [
            "Elite Ex-Ante Real Policy Rate (+6.60%): 10.50% Selic vs 3.90% Focus Survey forward inflation provides world-class carry insulation against EM volatility.",
            "Formidable External Balance & Reserve Buffer: $355B in central bank foreign exchange reserves provides over 12 months of import cover, eliminating external liquidity risks.",
            "Record Agribusiness Terms of Trade: World leadership in soybean (16% of exports), crude petroleum (14%), and iron ore (10%) exports delivers persistent structural trade surpluses ($80B+ annualized).",
            "Deep Domestic Institutional Base: Brazil's domestic pension fund (Previ, Petros) and local asset management industry manage over R$6.5 Trillion, providing continuous bids for sovereign paper.",
            "Disciplined Central Bank Credibility: Banco Central do Brasil demonstrated resolute independence by halting rate cuts at 10.50% when inflation expectations drifted from the 3.0% target."
        ],
        "negatives": [
            "Fiscal Framework & Primary Deficit Doubts: Ongoing Congressional and market skepticism regarding the government's ability to achieve zero primary deficit targets without mandatory spending cuts.",
            "Rising Public Debt Trajectory: Gross general government debt has climbed toward 78% of GDP, driving steep risk premia in the 10Y-30Y curve (NTN-F 2033 yielding 12.20%+).",
            "Heavy Debt-Servicing Crowding Out: High nominal borrowing costs mean interest expenditure absorbs over 7% of GDP, limiting fiscal leeway for productive public investment.",
            "Commodity Vulnerability to Chinese Demand: Softening Chinese real estate construction directly pressures iron ore prices and Brazilian mining export values.",
            "Currency Sensitivity to US Dollar Regimes: BRL exhibits high beta to US rate expectations and domestic political rhetoric, frequently testing the 5.40-5.65 USD/BRL range."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 63.0, "industry": 21.0, "agriculture_mining": 16.0},
            "top_exports": ["Soybeans (16%)", "Crude Petroleum (14%)", "Iron Ore (10%)", "Meat/Poultry (7%)", "Sugar (4%)"],
            "top_trading_partners": ["China (31%)", "United States (12%)", "European Union (11%)", "Argentina (5%)"],
            "public_debt_pct_gdp": 77.8,
            "foreign_ownership_pct_debt": 9.5,
            "banking_system_summary": "Highly capitalized, well-regulated private and state-owned banking system (Itaú, Bradesco, Banco do Brasil) with low NPLs (~3.2%) and strong return on equity (>18%).",
            "domestic_institutional_anchor": "Massive domestic institutional investor base (closed pension funds manage R$1.3T; local investment funds manage R$5.2T) holding over 80% of outstanding federal public debt."
        },
        "recent_developments": [
            "Copom paused Selic rate cuts at 10.50%, with unanimous committee signaling potential rate hikes if inflation expectations drift further above 4.0%.",
            "August IPCA-15 inflation printed at +0.22% MoM / 4.35% YoY, confirming that services disinflation remains sticky amidst tight labor markets (unemployment at 6.8%).",
            "Finance Minister Fernando Haddad submitted the 2025 Annual Budget Bill (PLOA) maintaining a zero primary deficit target, supported by R$25.9B in targeted spending cuts.",
            "Petrobras announced updated 5-year capital expenditure plans with disciplined dividend distribution, alleviating immediate fiscal drain concerns."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-18", "event": "Copom Monetary Policy Decision", "detail": "Watch for hawkish pause at 10.50% or 25bp hike signaling."},
                {"date": "2026-09-25", "event": "IPCA-15 Mid-Month CPI Release", "detail": "Confirmation of sub-4.3% trajectory validates belly yield buffer."},
                {"date": "2026-11-06", "event": "Copom Q4 Inflation Report", "detail": "Key signal for potential rate path and curve steepener roll-down."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/BRL Spot", "level": "> 5.65", "action": "Trigger strict 3M NDF forward hedges to protect carry."},
                {"metric": "10Y NTN-F Yield", "level": "> 12.50%", "action": "Stop loss on outright duration; rotate to 2s5s steepener."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "< $65/bbl", "impact": "Reduces Petrobras tax royalties and widens fiscal deficit by 0.3% GDP."},
                {"commodity": "Iron Ore (62% Fe)", "threshold": "< $90/MT", "impact": "Pressures mining export revenues and BRL terms of trade."}
            ]
        }
    },

    "mexico": {
        "investment_thesis": {
            "stance": "Overweight 10Y M-Bonos Strictly on an FX-Hedged Basis / 2s10s TIIE Curve Flattener",
            "horizon": "6M - 12M Structural Rates Trade",
            "expression": "Express via 2s10s TIIE Curve Flattener: Pay MXN 1,070M 2Y TIIE (26x1) vs Receive MXN 285M 10Y TIIE (130x1) at -23 bps spread (target -50 bps). For cash bond investors, Buy 10Y M-Bono 7.75% 2034 at 9.47% strictly FX-hedged against USD/MXN.",
            "core_thesis": "Mexico presents an extreme divergence between high nominal rates (10.50% TIIE), robust ex-ante real yields (+6.70%), and elevated external political risk. The US Presidential Election and universal tariff threats (10-20%), combined with domestic judicial reforms, create sharp currency depreciation pressure. However, domestic interest rates are exceptionally attractive: as Banxico continues cautious easing, the 10Y M-Bono yield (9.47%) offers substantial capital appreciation potential if isolated from currency volatility via FX hedges or curve flatteners."
        },
        "positives": [
            "Highest Real Policy Rate in LatAm (+6.70%): 10.50% Banxico target rate vs 3.80% 12M forward inflation survey anchors massive nominal carry.",
            "Long-Term Structural Nearshoring Beneficiary: Foreign Direct Investment (FDI) surpassed $36B annualized, driven by North American manufacturing re-shoring in automotive and aerospace.",
            "Moderate Public Debt Burden: Gross public debt stands at ~50% of GDP, significantly lower than regional peers (Brazil 78%, Colombia 57%).",
            "Strong Foreign Reserve Insurance: Bank of Mexico holds $221.5B in FX reserves plus an active $35B IMF Flexible Credit Line (FCL).",
            "Autonomous Central Bank Anchor: Banxico maintains strict anti-inflation credibility, executing a measured and data-dependent easing cycle."
        ],
        "negatives": [
            "US Election & USMCA Renegotiation Threat: Universal tariff threats (10-20%) from the US political cycle and the upcoming 2026 USMCA review create severe trade headwinds.",
            "Judicial Reform & Institutional Uncertainty: Legislative approval of popular election of federal judges has raised institutional concerns among foreign direct investors.",
            "Widening Fiscal Deficit: 2024 public sector borrowing requirement (PSBR) widened to -5.0% of GDP, requiring fiscal consolidation in 2025.",
            "Pemex Financial Liabilities: State oil company Pemex holds over $100B in debt, requiring continuous federal budget cash injections and tax deferrals.",
            "High FX Beta: Mexican Peso is the world's most liquid emerging market currency, making it the primary proxy hedging vehicle for global macro risk."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 60.0, "industry": 36.0, "agriculture_mining": 4.0},
            "top_exports": ["Automotive & Vehicle Parts (32%)", "Electronics & Computers (18%)", "Machinery (15%)", "Crude Oil (5%)", "Agricultural goods (4%)"],
            "top_trading_partners": ["United States (80%)", "Canada (3%)", "China (2%)", "Germany (2%)"],
            "public_debt_pct_gdp": 50.2,
            "foreign_ownership_pct_debt": 14.5,
            "banking_system_summary": "Highly capitalized, conservative commercial banking sector dominated by foreign subsidiaries (BBVA México, Banorte, Santander, Citibanamex) with average capital adequacy above 19%.",
            "domestic_institutional_anchor": "Afores (private mandatory pension funds) manage over MXN 6.0 Trillion (~$300B USD), acting as the primary structural buyers of long-dated M-Bonos and Udibonos."
        },
        "recent_developments": [
            "Banxico delivered a 25bp rate cut to 10.50% in a split 3-2 decision, with the majority noting ongoing headline and core disinflation toward the 3.0% target band.",
            "President Claudia Sheinbaum took office on October 1, 2024, committing to fiscal consolidation and confirming Marcelo Ebrard as Economy Minister to handle US trade relations.",
            "Congress enacted constitutional reforms for the popular election of judges, triggering a temporary depreciation of USD/MXN from 18.50 to 19.80.",
            "Headline inflation decelerated to 4.83% YoY in August, with core inflation slowing to 4.00% YoY, confirming the disinflation glide path."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-26", "event": "Banxico Monetary Policy Decision", "detail": "Consensus 25bp cut to 10.25%; watch voting split for pace guidance."},
                {"date": "2026-10-09", "event": "INEGI Headline & Core CPI Print", "detail": "Confirmation of core disinflation allows Banxico to maintain easing cycle."},
                {"date": "2026-11-03", "event": "US Presidential Election", "detail": "Critical binary event for MXN volatility and tariff policy horizon."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/MXN Spot", "level": "> 20.20", "action": "Strict stop loss on unhedged currency positions; roll NDF hedges."},
                {"metric": "2s10s TIIE Spread", "level": "> 0 bps", "action": "Exit curve flattener if 2Y yields drop faster than 10Y yields."}
            ],
            "commodity_sensitivities": [
                {"commodity": "US Automotive Demand", "threshold": "Sales < 15.0M annualized", "impact": "Reduces Mexican manufacturing export growth by 1.2% GDP."},
                {"commodity": "WTI Crude Oil", "threshold": "< $65/bbl", "impact": "Forces federal government to assume additional Pemex debt amortizations."}
            ]
        }
    },

    "south_africa": {
        "investment_thesis": {
            "stance": "Overweight Long 10Y SAGB Duration (R2035) Unhedged / Bullish ZAR Currency",
            "horizon": "6M - 12M Turnaround Play",
            "expression": "Buy SAGB 8.875% 28/02/2035 (R2035) at 9.15% yield unhedged. Target $10,000 DV01 (~ZAR 250M notional; ~$14.0M USD). Target yield 8.50% (+65 bps capital gain + 9.15% carry). Stop loss at 9.75% or USD/ZAR > 18.20.",
            "core_thesis": "South Africa is our highest-conviction sovereign turnaround call across the GBI-EM complex. The formation of the Government of National Unity (GNU) has ended political paralysis, while Eskom has achieved over 170 consecutive days of zero loadshedding, unlocking latent GDP growth. Concurrently, record gold prices ($2,580/oz) have ignited a terms of trade boom (+1.4% expansion), shifting the current account deficit toward balance. SAGB yields at 9.15% offer an extraordinary ex-post real yield (+4.80%), and ZAR remains deeply undervalued (-14.5% 10Y REER), offering double-alpha capital gains and currency appreciation."
        },
        "positives": [
            "Government of National Unity (GNU) Political Breakthrough: The coalition between ANC, DA, and IFP establishes policy stability, investor-friendly reforms, and fiscal discipline.",
            "End of Eskom Power Loadshedding: Over 170 consecutive days of continuous electricity generation, driving industrial recovery and boosting potential GDP growth toward 1.8%.",
            "Record Precious Metals Terms of Trade Boom: Gold at $2,580/oz and resilient platinum group metal prices support mining tax revenues and external trade balances.",
            "Substantial Real Yield Buffer: 10Y SAGB yielding 9.15% against 4.35% BER forward inflation delivers a +4.80% ex-ante real yield and ~9.0% carry.",
            "Deep Domestic Pension Market Anchor: Public Investment Corporation (PIC) and domestic retirement funds manage over ZAR 3.2 Trillion, absorbing over 70% of sovereign issuance."
        ],
        "negatives": [
            "High Public Debt & Debt Servicing Costs: Gross debt-to-GDP at 74.1%, with interest payments consuming over 21% of total government revenue.",
            "Transnet Freight Rail & Port Bottlenecks: Inefficient logistics infrastructure continues to constrain bulk coal, iron ore, and manganese export throughput.",
            "Persistent Structural Unemployment: Official unemployment remains critically high at 33.5% (youth unemployment >60%), constraining broad domestic consumption.",
            "Municipal Financial Distress: Over 60% of local municipalities are in financial distress, accumulating arrears to water and power utilities.",
            "Emerging Market Risk Beta: High sensitivity of ZAR to global risk-off sentiment and US rate volatility."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 67.0, "industry": 30.0, "agriculture_mining": 3.0},
            "top_exports": ["Platinum Group Metals & Gold (25%)", "Coal & Iron Ore (15%)", "Vehicles & Transport Equipment (10%)", "Diamonds (4%)", "Agricultural Citrus/Wine (4%)"],
            "top_trading_partners": ["China (12%)", "United States (8%)", "Germany (7%)", "United Kingdom (5%)", "Japan (4%)"],
            "public_debt_pct_gdp": 74.1,
            "foreign_ownership_pct_debt": 25.5,
            "banking_system_summary": "World-class, highly capitalized commercial banking system (Standard Bank, FirstRand, Absa, Nedbank) with Tier 1 capital adequacy over 15.5% and conservative credit underwriting.",
            "domestic_institutional_anchor": "Massive institutional retirement savings pool (ZAR 3.2 Trillion PIC and private pension funds) providing durable sovereign bond absorption."
        },
        "recent_developments": [
            "The multi-party GNU government passed its initial 100-day mark with cross-party consensus on structural growth reforms and fiscal deficit reduction.",
            "Eskom reported that its Energy Availability Factor (EAF) stabilized above 63%, with zero planned power cuts across the winter season.",
            "SARB held the repo rate at 8.25% in July, with Governor Kganyago indicating that disinflation toward the 4.5% midpoint opens the door for a measured easing cycle.",
            "Credit rating agencies (S&P, Moody's, Fitch) signaled that South Africa's sovereign rating outlook could be revised from stable to positive if fiscal targets hold."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-19", "event": "SARB Monetary Policy Committee Decision", "detail": "Consensus 25bp cut to 8.00%; watch forward guidance on terminal rate."},
                {"date": "2026-10-23", "event": "Medium-Term Budget Policy Statement (MTBPS)", "detail": "Finance Minister Godongwana targets 4.3% deficit ceiling; sovereign rating upgrades possible."},
                {"date": "2026-11-21", "event": "SARB MPC Final 2024 Rate Decision", "detail": "Potential second 25bp cut to 7.75% cementing lower rates glidepath."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/ZAR Spot", "level": "> 18.20", "action": "Reduce ZAR currency exposure; hedge bond duration via 3M FX forwards."},
                {"metric": "10Y SAGB Yield", "level": "> 9.80%", "action": "Stop loss on R2035 position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Gold Spot", "threshold": "< $2,400/oz", "impact": "Trims mining trade surplus by 0.6% GDP."},
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "South Africa imports 95% of crude; surges headline fuel inflation."}
            ]
        }
    },

    "indonesia": {
        "investment_thesis": {
            "stance": "Overweight 10Y SUN Duration (FR0100) on an FX-Hedged Basis / Carry Accumulation",
            "horizon": "6M - 12M Duration Harvesting",
            "expression": "Buy Surat Utang Negara SUN FR0100 6.625% 15/02/2034 at 6.55% yield. Sized to $7,500 DV01 (~IDR 150 Billion; ~$9.75M USD). Hedge FX via 3M USD/IDR NDFs to lock in ~4.15% ex-ante real yield without currency volatility.",
            "core_thesis": "Indonesia offers premier macroeconomic stability within Emerging Asia, supported by disciplined inflation (2.12% YoY) firmly anchored inside Bank Indonesia's 1.5-3.5% target band. The ongoing mineral downstreaming boom in nickel, copper, and EV battery supply chains has generated persistent merchandise trade surpluses. While the political transition to President-elect Prabowo Subianto introduces market scrutiny regarding fiscal deficit expansion (free school meal programs), the statutory 3% GDP deficit ceiling remains a durable institutional constraint. 10Y SUN yields at 6.55% offer high-quality real carry (+3.85% ex-ante), best harvested with currency hedging."
        },
        "positives": [
            "Pristine Inflation Anchoring: Headline CPI at 2.12% YoY is among the lowest in GBI-EM, providing Bank Indonesia ample room to support economic growth.",
            "Mineral Downstreaming & Trade Surpluses: Strict nickel ore export bans have forced $30B+ in domestic smelting FDI, turning Indonesia into the world's leading nickel and stainless steel exporter.",
            "Statutory 3.0% Fiscal Deficit Discipline: Decades-old legal requirement capping public deficits at 3.0% GDP anchors fiscal credibility and sovereign debt ratios (~39.5% GDP).",
            "Robust FX Reserve Cushion: Bank Indonesia holds $150.2B in foreign exchange reserves, providing over 6.5 months of import cover and external debt service.",
            "Low Foreign Curve Concentration: Foreign ownership of local currency government bonds has stabilized at ~14%, minimizing capital flight contagion risks."
        ],
        "negatives": [
            "Fiscal Policy Transition Risk: Prabowo administration's social spending programs (free school meals, defense modernization) risk pushing fiscal deficits against the 3.0% statutory ceiling.",
            "Softening Commodity Prices: Declining global thermal coal and palm oil prices have compressed Indonesia's trade surplus from peak 2022 levels.",
            "Bank Indonesia FX Intervention Burden: BI must periodically deploy reserves and issue high-yielding Bank Indonesia Rupiah Securities (SRBI) to defend the 15,300-15,600 USD/IDR band.",
            "Subdued Domestic Tax Revenue Base: Low tax-to-GDP ratio (~10.5%) restricts government capital spending capacity without higher debt issuance.",
            "Sensitivity to US Dollar Strength: Sharp spikes in DXY trigger immediate Rupiah depreciation pressure and foreign portfolio outflows."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 44.0, "industry": 42.0, "agriculture_mining": 14.0},
            "top_exports": ["Thermal Coal & Lignite (18%)", "Palm Oil (12%)", "Nickel & Iron/Steel (12%)", "Petroleum & Gas (7%)", "Electrical Appliances (4%)"],
            "top_trading_partners": ["China (26%)", "United States (9%)", "Japan (8%)", "India (7%)", "Singapore (6%)"],
            "public_debt_pct_gdp": 39.5,
            "foreign_ownership_pct_debt": 14.0,
            "banking_system_summary": "Extremely profitable and well-capitalized banking system (Bank Mandiri, BRI, BCA, BNI) with net interest margins (NIM) above 5.0% and Tier 1 CAR over 24%.",
            "domestic_institutional_anchor": "BPJS Ketenagakerjaan (National Social Security) and local commercial banks hold over 65% of outstanding SUN bonds, ensuring domestic liquidity absorption."
        },
        "recent_developments": [
            "Bank Indonesia surprised markets with a pre-emptive 25bp rate cut to 6.00% in September 2024, signaling confidence in inflation stability and Rupiah resilience.",
            "President-elect Prabowo Subianto repeatedly affirmed commitment to maintaining the fiscal deficit within the 3.0% statutory limit in the 2025 State Budget.",
            "Indonesia's trade balance printed its 52nd consecutive monthly surplus in August at +$2.9B, led by non-oil manufactured exports.",
            "Foreign exchange reserves climbed to an all-time record of $150.2B, bolstered by government global bond issuance and foreign portfolio inflows."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-18", "event": "Bank Indonesia Board of Governors Rate Decision", "detail": "Assessment of Rupiah stability and potential further easing space."},
                {"date": "2026-10-01", "event": "BPS Monthly Inflation & Trade Balance", "detail": "Confirmation of inflation remaining anchored near 2.1% midpoint."},
                {"date": "2026-10-20", "event": "Presidential Inauguration & Cabinet Announcement", "detail": "Appointment of Finance Minister is critical for sovereign bond market confidence."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/IDR Spot", "level": "> 15,800", "action": "Increase NDF hedge ratio to 100%; Bank Indonesia intervention zone."},
                {"metric": "10Y SUN Yield", "level": "> 7.00%", "action": "Reduce duration exposure on fiscal deficit concerns."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Thermal Coal (Newcastle)", "threshold": "< $120/MT", "impact": "Reduces trade surplus by $500M/month and pressures export tax revenue."},
                {"commodity": "LME Nickel", "threshold": "< $15,000/MT", "impact": "Slows new smelter construction and private capital expenditure."}
            ]
        }
    },

    "poland": {
        "investment_thesis": {
            "stance": "Underweight Local Sovereign Duration (POLGB) / Long Polish Zloty (PLN) vs EUR",
            "horizon": "6M - 12M Relative Value Trade",
            "expression": "Pay Fixed PLN 10Y WIBOR IRS at 5.35% (target 5.80%; $10,000 DV01 ~PLN 52M notional) to hedge heavy bond supply. Concurrently, Buy PLN vs EUR spot/forward at 4.28 (target 4.18, stop 4.35) to capture €60B+ in EU Recovery Fund currency conversion inflows.",
            "core_thesis": "Poland exhibits the slimmest real yields in GBI-EM (~1.05% on 10Y nominal vs 4.30% trailing inflation), rendering domestic bond duration unattractive compared to Latin America or South Africa. Furthermore, massive defense expenditure (4.7% of GDP, highest in NATO) drives heavy sovereign bond issuance and pushes the 2025 budget deficit to 5.5% of GDP. Conversely, the currency thesis is exceptionally bullish: the unfreezing of €60B+ in European Union Recovery and Resilience (KPO) funds creates sustained, price-inelastic FX conversion flows that will power Zloty outperformance against the Euro."
        },
        "positives": [
            "Massive EU Structural Inflow Wave: Over €60B in KPO grants and loans plus €76B in Cohesion Funds unlocked by Brussels, supporting long-term infrastructure investment.",
            "Resilient Economic Growth Engine: Strongest consumer spending growth in Central Europe, with real GDP expanding by +3.2% in 2024 and projected at +3.8% in 2025.",
            "Pro-European Governance Stability: Donald Tusk administration has restored constructive relations with European institutions and unlocked judicial reform milestones.",
            "Strong Sovereign Credit Rating (A-/A2): Poland maintains the second-highest credit rating in GBI-EM, backed by a diversified, high-tech industrial economy.",
            "Zloty External Support: Large capital transfers from the European Commission provide persistent structural support for PLN appreciation against EUR."
        ],
        "negatives": [
            "Heavy Defense Spending & Fiscal Deficit: Defense expenditure at 4.7% of GDP pushes the general government deficit to -5.5% of GDP, driving record bond supply.",
            "Slim Real Yield Cushion: 10Y POLGB yielding 5.35% against 3.70% forward inflation offers an ex-ante real yield of only +1.65%, highly vulnerable to global rate shifts.",
            "Persistent Inflation Pressures: Gradual phase-out of energy price caps and minimum wage hikes maintain core CPI near 3.8%, delaying NBP rate cuts.",
            "NATO Eastern Flank Geopolitical Risk: Geographic proximity to the Ukraine war exposes Poland to regional security tensions and hybrid threats.",
            "Domestic Political Friction: Co-habitation between the Tusk government and President Duda creates legislative veto friction on tax and regulatory bills."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 62.0, "industry": 35.0, "agriculture_mining": 3.0},
            "top_exports": ["Machinery & Electrical Equipment (24%)", "Vehicles & Automotive Parts (14%)", "Furniture & Manufactured Goods (10%)", "Chemicals & Plastics (9%)", "Agro-food (11%)"],
            "top_trading_partners": ["Germany (27%)", "Czech Republic (6%)", "France (6%)", "United Kingdom (5%)", "Italy (4%)"],
            "public_debt_pct_gdp": 52.5,
            "foreign_ownership_pct_debt": 16.0,
            "banking_system_summary": "Highly liquid, well-capitalized banking sector (PKO BP, Pekao, Santander Bank Polska) that has successfully absorbed CHF mortgage provisioning costs.",
            "domestic_institutional_anchor": "Domestic commercial banks, state funds (BGK), and PPK (Employee Capital Plans) hold over 75% of local government debt."
        },
        "recent_developments": [
            "European Commission finalized the disbursement of Poland's first €6.3B KPO tranche, with continuous transfers scheduled throughout 2024-2026.",
            "NBP Monetary Policy Council held the reference rate at 5.75%, with Governor Glapiński ruling out rate cuts until mid-2025 due to inflation rebound risks.",
            "Government approved the 2025 Draft Budget with a projected deficit of 5.5% of GDP, allocating a record PLN 187B (~$48B) to national defense.",
            "EUR/PLN consolidated in a tight 4.26-4.30 range, reflecting heavy corporate and EU fund conversion liquidity."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-02", "event": "NBP Monetary Policy Council Decision", "detail": "Consensus hold at 5.75%; hawkish guidance keeps carry intact vs ECB."},
                {"date": "2026-10-15", "event": "2027 Draft Deficit Budget Submission to Parliament", "detail": "Focus on bond supply and EU Excessive Deficit Procedure guidelines."},
                {"date": "2026-11-06", "event": "NBP Rate Decision & Inflation Projection Report", "detail": "Updated inflation trajectory for 2025-2026."}
            ],
            "technical_invalidation_levels": [
                {"metric": "EUR/PLN Spot", "level": "> 4.35", "action": "Stop loss on Long PLN trade; indicates geopolitical escalation or European growth slump."},
                {"metric": "10Y POLGB Yield", "level": "< 5.10%", "action": "Cover IRS payer position as yields approach fair value."}
            ],
            "commodity_sensitivities": [
                {"commodity": "TTF Natural Gas", "threshold": "> €45/MWh", "impact": "Widens energy import bill and adds 0.4% to headline CPI."},
                {"commodity": "German Industrial Production", "threshold": "< -2.0% YoY", "impact": "Slows Polish manufacturing export orders."}
            ]
        }
    },

    "india": {
        "investment_thesis": {
            "stance": "Overweight 10Y IGB (7.18% GS 2033) Unhedged / Low-Volatility Anchor Asset",
            "horizon": "12M Structural Index Inclusion Horizon",
            "expression": "Buy Indian Government Bond 7.18% 14/08/2033 (FAR Category) at 6.78% yield unhedged. Sized to $10,000 DV01 (~INR 115 Crore notional; ~$13.8M USD). Target yield 6.50%. Express unhedged as Reserve Bank of India manages USD/INR into a stable 83.70-84.00 range.",
            "core_thesis": "India serves as the definitive structural anchor asset of the GBI-EM asset class, supported by its ongoing phased 10-month inclusion into the J.P. Morgan GBI-EM Global Diversified index (reaching a capped 10% weight by March 2025). This inclusion drives ~$2B per month in automated passive foreign debt inflows. Combined with record-high foreign exchange reserves ($683B, covering 11.5 months of imports) actively deployed by the RBI to suppress currency volatility, 10Y IGBs function as an unhedged, quasi-dollar yielding asset delivering a reliable 6.78% nominal yield with negligible currency downside."
        },
        "positives": [
            "J.P. Morgan Index Inclusion Inflows: Phased 1% monthly weighting increases generate ~$25B in automated, structural foreign portfolio debt inflows through 2025.",
            "Historic FX Reserves Shield ($683B): Reserve Bank of India has accumulated the world's fourth-largest foreign currency reserves, neutralizing currency volatility.",
            "World-Leading GDP Growth (+7.0%): Robust domestic investment and public infrastructure capex insulate India from global manufacturing slowdowns.",
            "Committed Fiscal Consolidation: Central government budget deficit is steadily narrowing toward 4.9% of GDP in FY25 and sub-4.5% in FY26.",
            "Dominant Domestic Savings Anchor: Domestic life insurers (LIC), provident funds (EPFO), and state banks hold >90% of federal debt, preventing sharp sell-offs."
        ],
        "negatives": [
            "Crude Oil Import Vulnerability: India imports over 85% of its crude oil requirements; a $10/bbl spike in Brent widens the current account deficit by 0.5% GDP.",
            "Narrow Duration Spread: 10Y IGB yield at 6.78% trades with a narrow spread over US Treasuries (~180 bps), limiting capital appreciation upside.",
            "Persistent Food Price Volatility: Volatile monsoon rainfall patterns frequently trigger spikes in vegetable, pulse, and cereal prices, delaying RBI rate cuts.",
            "Elevated General Government Debt: Combined central and state public debt stands at ~82.5% of GDP, requiring ongoing fiscal consolidation.",
            "Geopolitical Chokepoint Sensitivity: Strait of Hormuz or Red Sea escalations threaten Indian crude import shipping lanes."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 54.0, "industry": 28.0, "agriculture_mining": 18.0},
            "top_exports": ["Refined Petroleum (18%)", "Pharmaceuticals (6%)", "Gems & Jewelry (9%)", "Electrical Machinery & Electronics (7%)", "Textiles (4%)"],
            "top_trading_partners": ["United States (18%)", "United Arab Emirates (8%)", "Netherlands (6%)", "China (5%)", "Singapore (4%)"],
            "public_debt_pct_gdp": 82.5,
            "foreign_ownership_pct_debt": 3.8,
            "banking_system_summary": "Cleaned up commercial banking system (SBI, HDFC Bank, ICICI Bank) with decade-low non-performing assets (Gross NPA < 2.8%) and robust credit growth (>14%).",
            "domestic_institutional_anchor": "Domestic institutional investors (EPFO, LIC, mutual funds, commercial banks via statutory liquidity ratio - SLR) absorb over 92% of government gross borrowing."
        },
        "recent_developments": [
            "J.P. Morgan completed Tranche 4 of India's index inclusion, with foreign portfolio investment (FPI) debt inflows exceeding $11B since June 2024.",
            "Headline CPI inflation dropped to 3.65% YoY in August, marking the first time inflation printed below the RBI's 4.0% target in nearly five years.",
            "Reserve Bank of India maintained the repo rate at 6.50% in August, maintaining a withdrawal of accommodation stance to ensure inflation durable alignment.",
            "Finance Minister Nirmala Sitharaman presented the Union Budget for FY25, lowering the fiscal deficit target to 4.9% of GDP while expanding capital capex to INR 11.11 Lakh Crore."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-09", "event": "RBI Monetary Policy Committee Meeting", "detail": "Consensus hold at 6.50%; watch for shift in stance from withdrawal to neutral."},
                {"date": "2026-10-12", "event": "MoSPI Headline CPI Release", "detail": "Confirmation of sub-4.0% print keeps real rate cushion solid."},
                {"date": "2026-11-30", "event": "J.P. Morgan Index Tranche 6 Weight Increase", "detail": "Monthly automated passive inflow wave (~$2.2B)."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/INR Spot", "level": "> 84.15", "action": "Watch for RBI aggressive FX intervention defending the 84.00 handle."},
                {"metric": "10Y IGB Yield", "level": "> 7.05%", "action": "Add to duration positions; strong sovereign buying support."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Widens current account deficit by $15B/year; pressures INR."},
                {"commodity": "Russian Urals Discount", "threshold": "< -$8/bbl vs Brent", "impact": "Increases crude import costs if discounted barrels diminish."}
            ]
        }
    },

    "colombia": {
        "investment_thesis": {
            "stance": "Sideways / Selective 5Y TES Duration Strictly on an FX-Hedged Basis",
            "horizon": "3M - 6M Tactical Range Trading",
            "expression": "Buy TES Tasa Fija 03/11/2029 at 10.15% yield strictly FX-hedged via 3M USD/COP NDFs. Sized to $5,000 DV01 (~COP 52 Billion; ~$12.5M USD). Stand aside on unhedged COP currency exposure due to oil exploration halts.",
            "core_thesis": "Colombia provides high nominal yields (10.15% on 5Y TES) and an attractive ex-ante real policy rate (+5.95%: 10.75% BanRep vs 4.80% survey), but is constrained by severe domestic fiscal and energy policy friction. President Gustavo Petro's prohibition on new oil and gas exploration contracts threatens Colombia's primary export earner (hydrocarbons represent 40% of exports), while debates over loosening the Fiscal Rule inject risk premia into local debt. While long COP can serve as an opportunistic portfolio hedge against Middle East crude spikes, sovereign duration should be strictly FX-hedged."
        },
        "positives": [
            "Generous Ex-Ante Real Yield Cushion (+5.95%): 10.75% BanRep policy rate vs 4.80% 12M forward inflation survey delivers strong carry compensation.",
            "Organic Energy Shock Portfolio Hedge: High export concentration in crude petroleum (32%) and coal (16%) makes COP a natural hedge against Middle East energy spikes.",
            "Independent Central Bank Discipline: Banco de la República has resisted political pressure for faster rate cuts, executing a prudent 50bp easing pace.",
            "Solid Foreign Reserve Backstop: $59.5B in FX reserves provides 6.8 months of import cover, complemented by an active IMF Flexible Credit Line ($8.1B).",
            "Active Foreign Debt Participation: Foreign institutional investors hold ~22% of local TES bonds, providing liquidity in the 2029-2034 tenors."
        ],
        "negatives": [
            "Hydrocarbon Exploration Ban: Executive policy halting new oil and gas exploration contracts threatens long-term export revenues and sovereign credit ratings.",
            "Fiscal Rule Uncertainty & Budget Deficit: 2024 fiscal deficit projected at -5.6% of GDP, with government proposing flexible adjustments to the Autonomous Fiscal Rule.",
            "Subdued Private Investment Sentiment: Private fixed capital formation has contracted for multiple consecutive quarters amidst policy uncertainty.",
            "Sticky Core & Services Inflation: Headline inflation at 6.12% YoY remains elevated, driven by food logistics and index-linked public utility tariffs.",
            "Currency Volatility in USD/COP: High sensitivity to domestic headlines and political friction, frequently swinging between 4,050 and 4,300."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 64.0, "industry": 28.0, "agriculture_mining": 8.0},
            "top_exports": ["Crude Petroleum (32%)", "Coal & Briquettes (16%)", "Coffee (7%)", "Cut Flowers (4%)", "Gold & Nickel (5%)"],
            "top_trading_partners": ["United States (27%)", "Panama (9%)", "China (7%)", "India (4%)", "Brazil (4%)"],
            "public_debt_pct_gdp": 56.5,
            "foreign_ownership_pct_debt": 22.0,
            "banking_system_summary": "Consolidated and well-capitalized domestic banking system (Bancolombia, Banco de Bogotá, Davivienda) with solvency ratios averaging 14.5%.",
            "domestic_institutional_anchor": "Local pension funds (Porvenir, Proteccion) manage over COP 380 Trillion, although pension reform transitions introduce uncertainty over future sovereign demand."
        },
        "recent_developments": [
            "BanRep cut the overnight intervention rate by 50bps to 10.75% in a split 5-2 vote, resisting Finance Ministry calls for an accelerated 75bp cut.",
            "Government presented the 2025 National Budget to Congress, sparking intense debate over tax reform measures to cover an estimated COP 12T revenue shortfall.",
            "National truckers strike in September briefly blockaded major highways, resolved through a negotiated phased diesel price increase.",
            "Headline CPI decelerated to 6.12% YoY in August, with core inflation trending downward to 5.5% YoY."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-30", "event": "BanRep Board of Directors Rate Decision", "detail": "Watch for potential acceleration to 75bp cut if inflation falls faster."},
                {"date": "2026-10-05", "event": "DANE CPI Inflation Release", "detail": "Consensus 5.95% YoY; breaking below 6.0% reinforces easing pace."},
                {"date": "2026-10-31", "event": "Congressional Budget Approval Deadline", "detail": "Crucial test of government's fiscal credibility and borrowing plans."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/COP Spot", "level": "> 4,350", "action": "Exit long currency positions; trigger full NDF forward hedging."},
                {"metric": "5Y TES Yield", "level": "> 10.75%", "action": "Stop loss on 2029 TES position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "< $70/bbl", "impact": "Widens Colombian current account deficit and pressures fiscal royalty income."},
                {"commodity": "Arabica Coffee", "threshold": "> $2.40/lb", "impact": "Provides rural household income windfall and agricultural export support."}
            ]
        }
    },

    "turkey": {
        "investment_thesis": {
            "stance": "Clip 1M-3M Front-End Cash Carry / Underweight Inverted Long-End Duration",
            "horizon": "1M - 3M Rolling Cash Carry",
            "expression": "Roll 1M - 3M Turkish Treasury Bills (Hazine Bonosu) or unhedged TRY cash deposits at ~46% - 50% annualized nominal yield. Target $5M - $10M USD notional allocation. Do NOT buy 10Y fixed-rate sovereign bonds (inversion risk).",
            "core_thesis": "Turkey represents a classic front-end hyper-carry regime. Under Finance Minister Mehmet Simsek and TCMB Governor Fatih Karahan, orthodox monetary management has anchored the policy rate at 50.00%. With 12M forward inflation expected to decline sharply toward 28.50%, the ex-ante real policy rate is an extraordinary +21.50%. The nominal carry (~44% annualized on 3M bills) generates ~$225,000 per month on $5.9M notional, easily outstripping the central bank's tightly controlled ~1.0% - 1.5% monthly TRY crawl. However, long-end 10Y bonds yield 32.50% (deeply inverted by ~1,750 bps below cash), making long duration uninvestable."
        },
        "positives": [
            "World-Class Ex-Ante Real Rate (+21.50%): 50.00% 1-week repo rate against 28.50% TCMB market participant forward survey offers the highest real cushion in the world.",
            "Credible Orthodox Economic Management: Team led by Simsek and Karahan has eliminated distortionary regulations, simplified reserve requirements, and restored central bank credibility.",
            "Spectacular Reserve Accumulation: TCMB net foreign exchange reserves (excluding swaps) turned positive by over $50B, eliminating balance of payments crisis risk.",
            "Accelerating Sovereign Credit Rating Upgrades: Fitch upgraded Turkey to BB- and Moody's upgraded to B1, with both agencies maintaining positive outlooks.",
            "De-Dollarization Momentum: Domestic households and corporations have shifted over $30B from FX and FX-protected deposits (KKM) back into standard Turkish Lira deposits."
        ],
        "negatives": [
            "Severe Yield Curve Inversion: 10Y benchmark bond yields 32.50% while 2Y yields 42.0% and policy rate is 50.0%, creating massive negative carry for duration holders.",
            "High Headline Inflation Persistence: Headline CPI at 51.97% YoY means trailing real yields remain negative (-19.5%), requiring ongoing monetary tightness.",
            "Heavy Net Energy Import Dependence: Turkey imports 95% of its crude oil and natural gas, leaving the current account vulnerable to Middle East energy spikes.",
            "Controlled Currency Crawl: TCMB permits gradual monthly TRY depreciation (~15-20% annualized) to preserve export competitiveness.",
            "Geopolitical Complexities: Turkey's balancing act between NATO, Russia, and Middle Eastern regional conflicts creates periodic headline volatility."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 58.0, "industry": 31.0, "agriculture_mining": 11.0},
            "top_exports": ["Automotive & Vehicle Parts (14%)", "Machinery & Appliances (10%)", "Textiles & Apparel (9%)", "Iron & Steel (6%)", "Chemical Products (5%)"],
            "top_trading_partners": ["Germany (8%)", "United States (6%)", "United Kingdom (5%)", "Italy (5%)", "Russia (5%)"],
            "public_debt_pct_gdp": 29.5,
            "foreign_ownership_pct_debt": 9.0,
            "banking_system_summary": "Extremely robust, well-capitalized commercial banking system (Akbank, Garanti BBVA, Isbank, Yapi Kredi) with capital adequacy ratios above 18% and resilient asset quality.",
            "domestic_institutional_anchor": "Domestic retail and corporate depositors hold over TRY 10 Trillion in local currency deposits; domestic pension and mutual funds are expanding rapidly."
        },
        "recent_developments": [
            "Fitch Ratings upgraded Turkey's sovereign credit rating to BB- from B+ with a stable outlook, citing reserve accumulation and falling inflation expectations.",
            "TCMB held the 1-week repo auction rate at 50.00% for the fifth consecutive month, pledging to tighten further if inflation expectations deteriorate.",
            "TurkStat reported that headline inflation fell to 51.97% YoY in August (from 61.8% in July), confirming that the disinflation process is firmly underway.",
            "Central bank net reserves turned positive, with total gross reserves exceeding $153B (highest level in Turkish history)."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-19", "event": "TCMB Monetary Policy Committee Meeting", "detail": "Consensus hold at 50.00%; watch for hawkish language on domestic demand cooling."},
                {"date": "2026-10-03", "event": "TurkStat Monthly CPI Release", "detail": "Consensus 48.2% YoY; breaking below 50% provides psychological boost."},
                {"date": "2026-10-17", "event": "TCMB Rate Decision & Q4 Inflation Assessment", "detail": "Confirmation of year-end inflation target glidepath toward 38%."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/TRY Crawl Rate", "level": "> 2.5% MoM", "action": "Reduce T-Bill carry allocation if monthly depreciation outpaces 3.5% carry."},
                {"metric": "TCMB Net Reserves", "level": "Declines by > $5B in 2 weeks", "action": "Warning sign of de-dollarization reversal."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Adds $5B to annual energy import bill and widens current account deficit."},
                {"commodity": "Gold Imports", "threshold": "> $2.5B/month", "impact": "Depletes foreign reserves if retail gold hoarding resumes."}
            ]
        }
    },

    "chile": {
        "investment_thesis": {
            "stance": "Overweight 5Y/10Y BTP Duration / Bullish CLP on Copper Terms of Trade",
            "horizon": "6M - 12M Bullish Rates & FX",
            "expression": "Buy Bonos de Tesorería BTP 03/01/2034 at 5.35% yield unhedged. Target $10,000 DV01 (~CLP 12.5 Billion; ~$13.5M USD). Target yield 4.85% (+50 bps capital gain). CLP benefits directly from LME copper at $4.22/lb.",
            "core_thesis": "Chile combines high institutional credibility (A rating, lowest debt in LatAm at 39.8% GDP) with direct exposure to the global electrification theme through its world-leading copper industry (28% of global supply). With LME copper trading strongly at $4.22/lb (+8.4% YoY), Chile's terms of trade are expanding sharply. Concurrently, Banco Central de Chile (BCCh) has navigated a smooth disinflation trajectory toward 3.0%, allowing steady TPM cuts toward a 4.5% neutral rate. 10Y BTP bonds (5.35%) offer attractive roll-down, while spot CLP is an optimal vehicle to express structural copper bullishness."
        },
        "positives": [
            "Global Electrification Windfall: World's #1 copper exporter (52% of total exports) benefiting from sustained high copper prices ($4.22/lb) and lithium demand.",
            "Lowest Public Debt in Latin America: Sovereign debt-to-GDP at 39.8% anchored by strict structural fiscal rule legislation.",
            "High Sovereign Credit Quality (A/A2): High-grade institutional framework provides safety against emerging market contagion.",
            "Predictable Central Bank Easing Cycle: BCCh TPM rate at 5.50% is steadily easing toward 4.5% terminal, providing bond duration tailwinds.",
            "Deep Domestic Pension System: Chilean AFPs manage over $175B USD, providing structural long-end demand for BTP and BCU (UF linker) paper."
        ],
        "negatives": [
            "Vulnerability to Chinese Construction Slump: China purchases over 39% of Chilean exports; property slowdown risks weighing on copper volume.",
            "Moderate Real Rate Cushion: +2.30% ex-ante real rate (5.50% TPM − 3.20% inflation) offers lower carry than Brazil or Mexico.",
            "Domestic Mining Tax & Regulatory Scrutiny: Ongoing debates over environmental permits and state lithium partnerships dampen private mining capex.",
            "Persistent Current Account Deficit: -3.2% of GDP deficit due to capital imports for energy transition infrastructure.",
            "Currency Sensitivity to Global Risk: CLP exhibits high volatility during risk-off episodes and Chinese market sell-offs."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 61.0, "industry": 24.0, "agriculture_mining": 15.0},
            "top_exports": ["Refined & Raw Copper (52%)", "Lithium Carbonate (8%)", "Fresh Fruit & Wine (6%)", "Fish & Salmon (5%)", "Wood Pulp (4%)"],
            "top_trading_partners": ["China (39%)", "United States (14%)", "Japan (8%)", "South Korea (6%)", "Brazil (4%)"],
            "public_debt_pct_gdp": 39.8,
            "foreign_ownership_pct_debt": 18.5,
            "banking_system_summary": "Extremely stable, sophisticated commercial banking system (Banco de Chile, Santander Chile, BCI) with lowest NPLs in LatAm (< 2.2%) and strong capitalization.",
            "domestic_institutional_anchor": "Administradoras de Fondos de Pensiones (AFPs) hold over 50% of outstanding local sovereign and inflation-linked debt."
        },
        "recent_developments": [
            "BCCh lowered the TPM rate by 25bps to 5.50% in August, signaling that policy will reach its neutral range (4.0-4.5%) by mid-2025.",
            "LME Copper prices rebounded strongly above $4.20/lb following Chinese monetary stimulus announcements, boosting the Chilean Peso.",
            "Ministry of Finance reaffirmed its commitment to the 2024 structural deficit target of -1.9% GDP.",
            "Headline inflation printed at 4.4% YoY, driven by electricity tariff adjustments, but 12M forward expectations remain anchored at 3.2%."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-15", "event": "BCCh Monetary Policy Meeting", "detail": "Consensus 25bp cut to 5.25%; watch forward rate path projections."},
                {"date": "2026-11-08", "event": "INE Monthly CPI Release", "detail": "Confirmation of electricity tariff absorption confirms disinflation glidepath."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/CLP Spot", "level": "> 950", "action": "Hedge CLP exposure via Camara swaps if copper breaks below $4.00/lb."},
                {"metric": "10Y BTP Yield", "level": "> 5.75%", "action": "Stop loss on BTP 2034 duration."}
            ],
            "commodity_sensitivities": [
                {"commodity": "LME Copper", "threshold": "< $3.90/lb", "impact": "Widens current account deficit and weakens CLP toward 960."},
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Chile imports 98% of crude; adds 0.5% to headline inflation."}
            ]
        }
    },

    "peru": {
        "investment_thesis": {
            "stance": "Overweight 10Y Bonos Soberanos (2034) Unhedged / Quasi-Dollar Stability",
            "horizon": "12M Structural High-Grade Allocation",
            "expression": "Buy Bonos Soberanos 5.75% 12/08/2034 at 5.85% yield unhedged. Target $7,500 DV01 (~PEN 39 Million notional; ~$10.4M USD). Target yield 5.25%. PEN currency volatility is virtually zero due to BCRP intervention.",
            "core_thesis": "Peru represents the most pristine inflation environment in emerging markets, with headline CPI at 2.03% YoY already inside the BCRP's 1-3% target band. Despite recurrent executive-legislative political friction, the central bank (led by Julio Velarde) holds an immense $82.5B in foreign exchange reserves (over 30% of GDP, covering 15.5 months of imports), which it actively uses to keep the Sol tightly pegged around 3.73-3.78 USD/PEN. Backed by booming copper ($4.22/lb) and gold ($2,580/oz) exports and a low public debt burden (33% GDP), 10Y Soberanos offer a pure +3.65% ex-ante real yield with near-zero currency risk."
        },
        "positives": [
            "Pristine Inflation Target Compliance: Headline CPI at 2.03% YoY is perfectly anchored inside the 1-3% target band, leading the Latin American disinflation cycle.",
            "Massive FX Reserve Fortress ($82.5B): Central bank reserves equal 30% of GDP and cover 15.5 months of imports, insulating Peru from currency shocks.",
            "Low Public Debt Ratio (33.2% GDP): One of the cleanest fiscal balance sheets in the emerging market universe.",
            "Commodity Windfall in Copper & Gold: World's #2 copper producer and major gold exporter harvesting simultaneous terms of trade price expansions.",
            "Chancay Mega-Port Strategic Hub: $3.5B Chinese-built deep-water port opening in late 2024 cuts South America-to-Asia shipping transit times by 15 days, boosting export competitiveness."
        ],
        "negatives": [
            "Chronic Political Instability: Deeply unpopular executive administration and highly fragmented Congress prone to political confrontations.",
            "Repeated Pension Fund Withdrawal Bills: Congressional approval of repeated AFP retirement fund withdrawals temporarily forces local funds to liquidate assets.",
            "Social Unrest in Southern Mining Corridor: Community protests occasionally disrupt haulage roads from Las Bambas and other key copper deposits.",
            "Subdued Domestic Consumer Confidence: Political uncertainty dampens long-term private fixed capital investment outside the mining sector.",
            "High Dollarization Legacy: Partial dollarization of banking credit makes BCRP cautious regarding sudden exchange rate depreciation."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 58.0, "industry": 25.0, "agriculture_mining": 17.0},
            "top_exports": ["Copper & Concentrates (35%)", "Gold (15%)", "Zinc & Lead (8%)", "Agricultural goods/Avocados/Berries (10%)", "Fishmeal (4%)"],
            "top_trading_partners": ["China (32%)", "United States (14%)", "Canada (5%)", "Japan (4%)", "South Korea (4%)"],
            "public_debt_pct_gdp": 33.2,
            "foreign_ownership_pct_debt": 38.0,
            "banking_system_summary": "Extremely resilient, highly profitable commercial banking sector (Credicorp/BCP, BBVA Perú, Scotiabank) with capital ratios over 16% and conservative provisioning.",
            "domestic_institutional_anchor": "Private pension system (AFPs) and domestic insurance companies hold ~40% of local sovereign debt."
        },
        "recent_developments": [
            "Banco Central de Reserva del Perú (BCRP) cut the reference rate by 25bps to 5.25% in September, affirming that inflation is firmly anchored at 2.0%.",
            "Chancay Mega-Port infrastructure reached 92% completion, scheduled for formal inauguration during the November APEC Leaders Summit in Lima.",
            "Fiscal deficit for the trailing 12 months stood at 2.8% of GDP, with Ministry of Economy projecting return toward 2.0% ceiling by 2025.",
            "Copper output from Quellaveco and Cerro Verde drove a +12% YoY expansion in national mining export volumes."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-10", "event": "BCRP Monetary Policy Decision", "detail": "Consensus hold or 25bp cut to 5.00%; watch forward guidance on terminal rate."},
                {"date": "2026-11-14", "event": "APEC Leaders Summit & Chancay Port Inauguration", "detail": "Major international spotlight on Peru's Asian trade corridor."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/PEN Spot", "level": "> 3.82", "action": "Watch for BCRP spot FX selling and swap interventions."},
                {"metric": "10Y Soberano Yield", "level": "> 6.25%", "action": "Add to duration positions on cheap valuation."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Copper Price", "threshold": "< $3.80/lb", "impact": "Trims trade surplus and reduces government mining royalties."},
                {"commodity": "Gold Spot", "threshold": "> $2,500/oz", "impact": "Provides massive current account surplus boost."}
            ]
        }
    },

    "czech_republic": {
        "investment_thesis": {
            "stance": "Overweight 10Y CZGB Duration with EUR/CZK Forward Hedge / AA- High Grade Anchor",
            "horizon": "6M - 12M Core European Rates Trade",
            "expression": "Buy Czech Government Bond (CZGB) 2.00% 10/13/2033 at 3.85% yield. Sized to $10,000 DV01 (~CZK 290 Million; ~$12.8M USD). Hedge FX via EUR/CZK forward contracts to isolate +1.75% ex-ante real yield without German industrial drag.",
            "core_thesis": "The Czech Republic represents the highest credit quality in GBI-EM (AA-/Aa3), inflation is fully anchored at the 2.0% target, and sovereign debt-to-GDP is among the lowest in Europe (44.2%). With the Czech National Bank (CNB) having delivered substantial rate cuts to 4.25%, 10Y CZGB yields at 3.85% offer an exceptional high-grade sovereign spread over German Bunds (~165 bps). While heavy automotive linkages to the struggling German economy warrant hedging the Koruna against the Euro, Czech sovereign duration provides prime risk-off defensive characteristics."
        },
        "positives": [
            "Highest Sovereign Credit Rating in GBI-EM (AA-/Aa3): Rock-solid institutional framework, EU membership, and superior fiscal credibility.",
            "Fully Anchored 2.0% Inflation: Headline CPI at 2.20% YoY is back to central bank target, successfully defeating the 2022-2023 inflation shock.",
            "Low Public Debt Burden (44.2% GDP): Fiscally conservative sovereign with constitutional debt brake mechanisms.",
            "Substantial FX Reserve Backstop ($142.5B): Reserves equal 50% of GDP, covering over 8.5 months of imports, one of the highest ratios in Europe.",
            "Diversified High-Tech Industrial Base: Leading European manufacturing hub with skilled labor force and high foreign direct investment."
        ],
        "negatives": [
            "Heavy Dependence on German Automotive Sector: German industrial recession and EV transition friction directly pressure Czech component suppliers.",
            "Modest Real Yield Spread: +2.15% ex-ante real rate (4.25% CNB − 2.10% survey) leaves yields sensitive to European Central Bank and Bund movements.",
            "Energy Transition Costs: Decoupling from Russian pipeline gas requires substantial infrastructure capex in LNG interconnectors.",
            "Aging Demographics & Labor Shortages: Tight domestic labor market with lowest unemployment rate in the EU (2.7%) creates wage pressure.",
            "Narrow Carry Buffer: 3M carry over EUR (+1.5%) is modest compared to Hungary (+5.8%) or Poland (+2.0%)."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 62.0, "industry": 36.0, "agriculture_mining": 2.0},
            "top_exports": ["Motor Vehicles & Parts (21%)", "Machinery & Computers (18%)", "Electrical Equipment (16%)", "Base Metals (8%)", "Chemicals (6%)"],
            "top_trading_partners": ["Germany (32%)", "Slovakia (8%)", "Poland (7%)", "France (5%)", "Austria (4%)"],
            "public_debt_pct_gdp": 44.2,
            "foreign_ownership_pct_debt": 28.0,
            "banking_system_summary": "Extremely sound, well-capitalized banking system dominated by top European banking groups (ČSOB/KBC, Česká spořitelna/Erste, Komerční banka/SocGen) with Tier 1 capital over 20%.",
            "domestic_institutional_anchor": "Domestic banks, pension funds, and insurance firms hold ~72% of outstanding CZGBs, providing reliable domestic placement."
        },
        "recent_developments": [
            "CNB slowed its easing pace, cutting the 2-week repo rate by 25bps to 4.25% in September amidst cautious communication on services inflation.",
            "Headline inflation printed at 2.20% YoY in August, right on the CNB's 2.0% tolerance midpoint.",
            "Government consolidated fiscal spending, narrowing the 2024 budget deficit target to 2.3% of GDP.",
            "Automotive production rebounded by +4.5% YoY led by hybrid and electric vehicle assemblies at Škoda Auto."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-25", "event": "CNB Board Rate Decision", "detail": "Consensus 25bp cut to 4.00%; watch voting split for terminal rate hints."},
                {"date": "2026-10-11", "event": "Czech Statistical Office CPI Release", "detail": "Confirmation of 2.0-2.2% range validates duration trade."}
            ],
            "technical_invalidation_levels": [
                {"metric": "EUR/CZK Spot", "level": "> 25.50", "action": "Watch for CNB verbal intervention; hedge Koruna exposure."},
                {"metric": "10Y CZGB Yield", "level": "> 4.25%", "action": "Stop loss on CZGB 2033 position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "TTF Natural Gas", "threshold": "> €45/MWh", "impact": "Increases heating and industrial electricity costs."},
                {"commodity": "German Ifo Business Climate", "threshold": "< 85.0", "impact": "Signals deeper German manufacturing drag on Czech exports."}
            ]
        }
    },

    "hungary": {
        "investment_thesis": {
            "stance": "Overweight 5Y HGB / BUBOR IRS (Top Carry in CEE) with NDF Currency Hedge",
            "horizon": "3M - 6M High Carry Capture",
            "expression": "Receive 5Y HGB / BUBOR IRS at 6.30% or Buy Hungarian Government Bond HGB 6.75% 22/10/2034 at 6.45% yield. Sized to $7,500 DV01 (~HUF 3.8 Billion; ~$10.7M USD). Express carry selectively; cap position sizing due to periodic EU fund withholding disputes.",
            "core_thesis": "Hungary provides the premier yield and carry vehicle in Central Europe, with a 6.75% base rate and a +3.25% ex-ante real policy rate. While headline risk regarding European Commission fund freezes persists, the current account has swung into surplus (+1.4% GDP), and massive foreign direct investment in EV battery gigafactories (CATL's €7.3B Debrecen plant, BYD) anchors capital inflows. The Forint offers an attractive +5.8% carry over EUR, best harvested on an unhedged or dynamically hedged basis in 3Y to 5Y belly bonds."
        },
        "positives": [
            "Highest Real Policy Rate in Central Europe (+3.25%): 6.75% MNB base rate vs 3.50% expected inflation offers the top carry cushion in the region.",
            "Massive Foreign Direct Investment in EV Batteries: Inflows from CATL (€7.3B), BYD, and Samsung SDI transform Hungary into Europe's EV manufacturing center.",
            "Current Account Shift to Surplus: From a deep -8% GDP deficit in 2022, the current account has shifted to +1.4% GDP surplus due to falling energy import costs.",
            "Disciplined Central Bank Anchor: Magyar Nemzeti Bank has prioritized currency stability, pacing rate cuts carefully to defend HUF.",
            "High Nominal Yield Buffer: 10Y HGB at 6.45% offers over 400 bps spread over German Bunds."
        ],
        "negatives": [
            "EU Cohesion Fund Freezes: Over €19B in EU funds remain suspended by the European Commission over rule-of-law and corruption concerns.",
            "Elevated Public Debt Ratio (73.5% GDP): Highest sovereign debt-to-GDP in Central Europe, driving substantial interest payment costs.",
            "High Fiscal Deficit: 2024 general government deficit projected at -4.5% of GDP, requiring ongoing sovereign issuance.",
            "Exposure to Russian Energy: Reliance on Druzhba oil pipeline and TurkStream gas creates vulnerability to transit disruptions.",
            "High Forint Volatility: EUR/HUF is prone to sharp swings during regional geopolitical escalations and EU disputes."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 64.0, "industry": 28.0, "agriculture_mining": 4.0},
            "top_exports": ["Machinery & Electrical/Batteries (38%)", "Vehicles & Automotive Parts (17%)", "Chemicals & Pharmaceuticals (10%)", "Manufactured Goods (10%)"],
            "top_trading_partners": ["Germany (26%)", "Italy (6%)", "Romania (5%)", "Slovakia (5%)", "Austria (4%)"],
            "public_debt_pct_gdp": 73.5,
            "foreign_ownership_pct_debt": 22.0,
            "banking_system_summary": "Liquid commercial banking sector (OTP Bank, K&H, Erste Bank Hungary) with strong Tier 1 capital (>18%) and solid profitability.",
            "domestic_institutional_anchor": "Domestic retail bonds (MÁP+) and institutional funds hold ~78% of total sovereign debt."
        },
        "recent_developments": [
            "MNB cut the base rate by 25bps to 6.75% in August, signaling a cautious, data-driven approach to future easing.",
            "Headline inflation printed at 3.40% YoY, within the central bank's 3.0% ± 1.0% tolerance band.",
            "Government revised the 2024 budget deficit target to 4.5% of GDP and announced extraordinary tax adjustments on retail banks and energy firms.",
            "Construction of CATL's €7.3B battery plant in Debrecen reached major structural milestones, with initial production targeted for 2025."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-09-24", "event": "MNB Monetary Council Interest Rate Meeting", "detail": "Consensus hold at 6.75% (cautious stance); locks in world-class carry."},
                {"date": "2026-10-08", "event": "KSH Monthly Inflation Print", "detail": "Consensus 3.3% YoY headline validates real yield buffer."}
            ],
            "technical_invalidation_levels": [
                {"metric": "EUR/HUF Spot", "level": "> 400.0", "action": "Watch for emergency MNB hawkish rhetoric; hedge currency exposure."},
                {"metric": "10Y HGB Yield", "level": "> 7.10%", "action": "Stop loss on Hungarian duration position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "TTF Natural Gas", "threshold": "> €45/MWh", "impact": "Widens energy import bill and pressures current account surplus."},
                {"commodity": "Russian Pipeline Flow", "threshold": "Transit disruption", "impact": "Triggers immediate EUR/HUF spike above 400."}
            ]
        }
    },

    "romania": {
        "investment_thesis": {
            "stance": "Receive 5Y ROMGB Strictly FX-Hedged / Avoid Unhedged Long-End Duration",
            "horizon": "3M - 6M Hedged Carry Trade",
            "expression": "Buy Romanian Government Bonds (ROMGB) 7.20% 10/28/2033 at 6.65% yield, strictly FX-hedged against EUR/RON. Sized to $5,000 DV01 (~RON 32 Million; ~$7.1M USD). Stand aside on unhedged exposure due to large fiscal deficit.",
            "core_thesis": "Romania offers elevated nominal yields (6.65% on 10Y ROMGB and 7.20% on 5Y), but faces significant structural headwinds from wide twin deficits (fiscal deficit near 7% of GDP, current account deficit at -7.0% GDP). The central bank (NBR) strictly manages the EUR/RON exchange rate near 4.975, making 3Y to 5Y belly bonds with currency hedges the only viable institutional expression. Avoid unhedged long-end sovereign duration into the late-2024 presidential and parliamentary elections."
        },
        "positives": [
            "Strong EU Capital Inflow Pipeline: Over €29B in EU Recovery (PNRR) and Cohesion funding driving public highway and energy infrastructure.",
            "Managed Currency Stability: National Bank of Romania (NBR) maintains a de-facto crawling peg near 4.975 EUR/RON, virtually eliminating day-to-day FX vol.",
            "Investment Grade Sovereign Anchor (BBB-/Baa3): S&P and Fitch maintain stable investment grade outlooks, supported by EU membership.",
            "Domestic Gas Independence: Neptun Deep offshore Black Sea gas project scheduled to double domestic natural gas production by 2027.",
            "High Nominal Yield Spread: 10Y ROMGB at 6.65% offers a 430 bp spread over German Bunds."
        ],
        "negatives": [
            "Widest Fiscal Deficit in Central Europe: General government deficit projected at -7.2% of GDP in 2024, triggering EU Excessive Deficit Procedure.",
            "Large Current Account Deficit: Current account deficit at -7.0% of GDP reflects persistent consumer import demand.",
            "Heavy Sovereign Borrowing Requirement: Ministry of Finance requires continuous debt issuance onshore and in Eurobonds to fund budget gaps.",
            "Late-2024 Election Uncertainty: Presidential and parliamentary elections in Nov/Dec 2024 delay necessary fiscal consolidation and tax reforms.",
            "Inflation Persistence: Headline inflation at 5.10% YoY requires NBR to maintain elevated interest rates."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 63.0, "industry": 27.0, "agriculture_mining": 10.0},
            "top_exports": ["Automotive & Vehicle Parts/Dacia (17%)", "Electrical Machinery (16%)", "Agricultural/Wheat/Corn (7%)", "Metals (6%)", "IT & Software Services (dominant)"],
            "top_trading_partners": ["Germany (20%)", "Italy (10%)", "France (6%)", "Hungary (5%)", "Bulgaria (4%)"],
            "public_debt_pct_gdp": 49.8,
            "foreign_ownership_pct_debt": 23.0,
            "banking_system_summary": "Highly profitable and solvent banking sector (Banca Transilvania, BCR/Erste, BRD/SocGen) with capital adequacy above 22% and low NPLs (< 2.8%).",
            "domestic_institutional_anchor": "Pillar II mandatory private pension funds manage over RON 140B (~$31B USD), holding over 25% of total domestic sovereign bonds."
        },
        "recent_developments": [
            "National Bank of Romania cut the policy rate by 25bps to 6.50% in August, signaling a cautious approach ahead of elections.",
            "Ministry of Finance increased its 2024 gross financing target to RON 215B (~$47B) to cover widening fiscal deficits.",
            "Headline inflation printed at 5.10% YoY in August, trending downward from 5.4% in July.",
            "OMV Petrom and Romgaz confirmed construction milestones on the €4B Neptun Deep offshore gas development."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-04", "event": "NBR Board Monetary Policy Meeting", "detail": "Consensus hold at 6.50%; watch forward guidance on fiscal deficit impact."},
                {"date": "2026-11-24", "event": "Romanian Presidential Election Round 1", "detail": "Crucial catalyst for post-election fiscal reform and tax package."}
            ],
            "technical_invalidation_levels": [
                {"metric": "EUR/RON Spot", "level": "> 5.00", "action": "Watch for NBR active FX reserve defense; hedge currency exposure."},
                {"metric": "10Y ROMGB Yield", "level": "> 7.25%", "action": "Stop loss on Romanian duration positions."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Widens energy import deficit."},
                {"commodity": "Agricultural Harvest", "threshold": "Drought conditions", "impact": "Reduces grain export receipts and widens trade deficit."}
            ]
        }
    },

    "malaysia": {
        "investment_thesis": {
            "stance": "Long Malaysian Ringgit (MYR) Spot/Forward / Neutral MGS Duration",
            "horizon": "6M - 12M Bullish Currency Play",
            "expression": "Buy Malaysian Ringgit (MYR) vs USD spot/forward at 4.32 (target 4.10; stop 4.45). In sovereign debt, hold neutral MGS 3.899% 11/16/2034 at 3.75% yield. Sized to $10,000 DV01 (~MYR 43.2M / $10M USD notional).",
            "core_thesis": "Malaysia is an economic powerhouse in the Asian GBI-EM segment, capped at the maximum 10% benchmark index weight. While sovereign bond yields offer modest real cushions (+0.80% ex-ante: 3.00% BNM OPR vs 2.20% inflation), the Malaysian Ringgit is experiencing an institutional re-rating. Surging foreign direct investment in artificial intelligence data centers, global semiconductor back-end assembly (Malaysia controls 13% of global chip testing), and state-led repatriation of overseas corporate profits have made the Ringgit the top-performing currency in Asia."
        },
        "positives": [
            "Global AI & Semiconductor Supply Chain Hub: Dominates 13% of global semiconductor assembly, testing, and packaging (OSAT), attracting tens of billions in tech FDI from Intel, Infineon, and Nvidia.",
            "Strong Current Account Surplus (+2.8% GDP): Net exporter of petroleum, liquefied natural gas (LNG), and palm oil, providing a resilient external trade balance.",
            "Government Profit Repatriation Coordination: Government-linked investment companies (GLICs) and corporations have systematically repatriated foreign earnings, driving MYR appreciation.",
            "High Sovereign Credit Quality (A-/A3): Backed by deep institutional capital, political stability under Prime Minister Anwar Ibrahim, and robust economic growth (+5.1%).",
            "Deepest Domestic Debt Market in ASEAN: Employees Provident Fund (EPF) manages over RM 1.1 Trillion (~$250B USD), anchoring local sovereign MGS and Sukuk markets."
        ],
        "negatives": [
            "Modest Real Yield Cushion: 3.00% OPR policy rate offers narrow +0.80% ex-ante real spread, leaving bond duration sensitive to US Treasury yield swings.",
            "Fiscal Subsidy Rationalization Risk: Planned phase-out of blanket RON95 fuel subsidies in late 2024/early 2025 will temporarily boost headline inflation.",
            "Public Debt Near Statutory Ceiling: Federal government debt stands at 64.3% of GDP, requiring fiscal deficit narrowing toward 4.3% in 2024.",
            "Vulnerability to Global Tech Downcycles: Semiconductor export slowdowns directly impact manufacturing GDP and corporate tax revenue.",
            "Chinese Economic Linkages: China is Malaysia's largest bilateral trading partner (14% of exports), exposing trade to Chinese growth slowdowns."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 58.0, "industry": 35.0, "agriculture_mining": 7.0},
            "top_exports": ["Electrical & Electronics/Semiconductors (40%)", "Petroleum & LNG (15%)", "Palm Oil & Agricultural (7%)", "Chemicals (6%)", "Optical & Scientific Equipment (4%)"],
            "top_trading_partners": ["Singapore (15%)", "China (14%)", "United States (11%)", "Japan (6%)", "European Union (8%)"],
            "public_debt_pct_gdp": 64.3,
            "foreign_ownership_pct_debt": 35.0,
            "banking_system_summary": "Extremely well-capitalized, liquid banking system (Maybank, CIMB, Public Bank) with capital ratios over 18% and lowest NPLs in ASEAN (< 1.6%).",
            "domestic_institutional_anchor": "EPF, KWAP (Retirement Fund Inc.), and PNB manage over RM 1.5 Trillion, holding over 60% of outstanding MGS and Government Investment Issues (MGII)."
        },
        "recent_developments": [
            "Bank Negara Malaysia kept the Overnight Policy Rate (OPR) unchanged at 3.00% in September, affirming that monetary policy remains supportive of growth.",
            "Malaysian Ringgit rallied over 8% against the US Dollar in Q3 2024, outperforming all emerging market currencies.",
            "Q2 GDP expanded by an impressive +5.9% YoY, driven by household spending, tech exports, and surging tourist arrivals.",
            "Government announced that targeted RON95 petrol subsidy rationalization will be detailed in the Budget 2025 presentation."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-18", "event": "Malaysia Budget 2025 Presentation in Parliament", "detail": "Details of RON95 fuel subsidy rationalization and fiscal deficit path."},
                {"date": "2026-11-06", "event": "Bank Negara Malaysia MPC Rate Decision", "detail": "Consensus hold at 3.00%; watch inflation commentary."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/MYR Spot", "level": "> 4.45", "action": "Take profit on Ringgit long positions; indicates global tech sell-off."},
                {"metric": "10Y MGS Yield", "level": "> 4.00%", "action": "Add to duration positions on attractive domestic value."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Crude Palm Oil (CPO)", "threshold": "< RM 3,700/MT", "impact": "Trims rural export incomes and plantation tax receipts."},
                {"commodity": "Brent Crude", "threshold": "> $80/bbl", "impact": "Expands Petronas oil & LNG dividends to federal budget."}
            ]
        }
    },

    "thailand": {
        "investment_thesis": {
            "stance": "Overweight 5Y/10Y Thai Loan Bonds (Thai LB Duration) / Bullish THB on Gold & Tourism",
            "horizon": "6M - 12M Monetary Easing Play",
            "expression": "Buy Thai Government Loan Bonds (Thai LB) 2.80% 2034 at 2.55% yield. Target $10,000 DV01 (~THB 410 Million; ~$12.2M USD). Express unhedged as Baht benefits from surging tourism and gold export receipts. Target yield 2.25%.",
            "core_thesis": "Thailand provides a defensive high-grade sovereign profile in GBI-EM (BBB+/Baa1). With headline inflation printing near zero (0.35% YoY) and substantial foreign exchange reserves ($225B, covering 8.8 months of imports), the Bank of Thailand (BOT) faces intense pressure to initiate rate cuts from 2.50%. Sovereign bond duration (10Y Thai LB at 2.55%) is primed for capital gains as the yield curve bull-steepens. Concurrently, the Thai Baht is heavily supported by a tourism current account surplus (+2.2% GDP) and historic gold prices ($2,580/oz), which generate large retail gold export cash inflows."
        },
        "positives": [
            "Ultra-Low Inflation (0.35% YoY): Headline inflation is well below the BOT's 1-3% target band, creating compelling macro justification for monetary easing.",
            "Surging Tourism & Current Account Surplus: Foreign tourist arrivals targeted at 36M in 2024, shifting the current account firmly into surplus (+2.2% GDP).",
            "Massive FX Reserves Backstop ($225B): Central bank reserves equal 45% of GDP and cover 8.8 months of imports, ensuring currency defense capacity.",
            "Gold Export Windfall: Record gold prices ($2,580/oz) generate substantial foreign exchange inflows as Thai retail investors liquidate gold holdings for cash.",
            "High Domestic Savings Liquidity: Domestic banks and Government Pension Fund (GPF) hold over 85% of outstanding government debt."
        ],
        "negatives": [
            "Executive vs Central Bank Friction: Government pressure on BOT Governor Sethaput to cut interest rates creates temporary institutional tension.",
            "High Household Debt Burden (90% GDP): Elevated consumer debt constrains domestic private credit growth and vehicle sales.",
            "Political Transition Volatility: Constitutional Court dissolution of the Move Forward Party and dismissal of former PM Srettha Thavisin highlight political instability.",
            "Manufacturing Competitiveness Headwinds: Automotive assembly faces challenges from Chinese EV imports and slowing domestic pickup truck demand.",
            "Modest Nominal Yield: 10Y Thai LB yield at 2.55% offers low nominal carry for foreign investors."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 59.0, "industry": 33.0, "agriculture_mining": 8.0},
            "top_exports": ["Machinery & Computers (18%)", "Automotive & Vehicle Parts (14%)", "Electrical Appliances (12%)", "Rubber Products & Plastics (8%)", "Precious Metals/Gold (6%)"],
            "top_trading_partners": ["United States (17%)", "China (12%)", "Japan (9%)", "Australia (4%)", "Singapore (4%)"],
            "public_debt_pct_gdp": 63.8,
            "foreign_ownership_pct_debt": 11.5,
            "banking_system_summary": "Extremely conservative commercial banking system (Bangkok Bank, SCB, Kasikornbank, Krungthai) with capital adequacy over 20% and robust provisioning.",
            "domestic_institutional_anchor": "Social Security Office (SSO), Government Pension Fund (GPF), and local mutual funds absorb over 85% of sovereign bond issuance."
        },
        "recent_developments": [
            "Paetongtarn Shinawatra sworn in as Prime Minister following the Constitutional Court's dismissal of Srettha Thavisin, ensuring coalition continuity.",
            "Government launched Phase 1 of its 10,000-baht cash handout program for 14.5 million welfare cardholders and vulnerable citizens.",
            "Bank of Thailand maintained the policy repo rate at 2.50% in August in a 6-1 vote, but signaled readiness to adjust policy if outlook shifts.",
            "Thai Baht appreciated sharply from 36.8 to 33.4 USD/THB, bolstered by tourism revenues and global gold price rallies."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-16", "event": "Bank of Thailand Monetary Policy Committee Decision", "detail": "High probability of initial 25bp rate cut to 2.25%."},
                {"date": "2026-11-05", "event": "Ministry of Commerce CPI Report", "detail": "Confirmation of low inflation validates ongoing easing cycle."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/THB Spot", "level": "> 35.50", "action": "Watch for BOT currency intervention; hedge THB exposure."},
                {"metric": "10Y Thai LB Yield", "level": "> 2.85%", "action": "Stop loss on duration position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Gold Spot", "threshold": "< $2,400/oz", "impact": "Slows retail gold liquidation export inflows and dampens Baht support."},
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Thailand imports 85% of energy; surges utility and transport costs."}
            ]
        }
    },

    "philippines": {
        "investment_thesis": {
            "stance": "Overweight 5Y/10Y FXTN Duration (Monetary Easing Leader) Unhedged",
            "horizon": "6M - 12M Rates Bull Market",
            "expression": "Buy Fixed Rate Treasury Notes FXTN 10-68 6.25% 02/28/2034 at 5.95% yield. Sized to $7,500 DV01 (~PHP 560 Million notional; ~$10.1M USD). Express unhedged as steady $38B annual remittances cushion currency risk.",
            "core_thesis": "The Philippines stands out as Southeast Asia's monetary easing leader. Bangko Sentral ng Pilipinas (BSP) initiated its easing cycle ahead of regional peers, lowering the target RRP to 6.25% with Governor Remolona signaling continuous cuts toward 5.00%. Rapid disinflation—accelerated by presidential executive orders slashing rice import tariffs from 35% to 15%—has anchored 12M forward inflation at 3.10%, leaving an ex-ante real policy rate of +3.15%. Sizable resilient remittances ($38B+ annually) and $107.9B in FX reserves provide currency stability, making 10Y FXTN duration a top-tier rates performer."
        },
        "positives": [
            "Regional Monetary Easing Front-Runner: BSP initiated rate cuts early, providing clear forward guidance for a multi-meeting easing cycle that powers bond capital gains.",
            "Aggressive Rice Tariff Disinflation Dividend: Executive Order reducing rice import tariffs from 35% to 15% sharply lowers food inflation (rice represents 9% of CPI basket).",
            "Steadiest External Inflow Anchor in EM: Remittances from Overseas Filipino Workers (OFW) exceed $38B annually (9% of GDP), providing a massive, non-cyclical dollar supply.",
            "Rapid Economic Growth (+6.0%): Leading ASEAN in GDP expansion, driven by public infrastructure investment ('Build-Better-More') and private services consumption.",
            "Strong Foreign Reserve Shield ($107.9B): Reserves cover 7.8 months of imports, fully insulating the external debt service requirement."
        ],
        "negatives": [
            "Persistent Trade Deficit: Chronic merchandise trade deficit (-$4.5B/month) requires remittances and BPO exports to maintain currency balance.",
            "Heavy Infrastructure Borrowing: Ambitious infrastructure spending keeps the public deficit wide at -5.5% of GDP and debt near 60.5% of GDP.",
            "Net Energy & Food Commodity Importer: Heavy dependence on imported crude oil, wheat, and fertilizer leaves headline inflation vulnerable to supply shocks.",
            "Geopolitical Flashpoint in South China Sea: Rising maritime confrontations with China over Second Thomas Shoal create periodic headline risks.",
            "Low Foreign Bond Market Participation: Foreign investors hold only ~6.5% of local currency government debt, limiting secondary market offshore liquidity."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 61.0, "industry": 29.0, "agriculture_mining": 10.0},
            "top_exports": ["Integrated Circuits & Semiconductors (48%)", "Business Process Outsourcing (BPO Services)", "Electrical Machinery (10%)", "Nickel Ore & Minerals (5%)", "Coconut Oil & Bananas (4%)"],
            "top_trading_partners": ["United States (16%)", "Japan (14%)", "China (12%)", "Hong Kong (11%)", "Singapore (6%)"],
            "public_debt_pct_gdp": 60.5,
            "foreign_ownership_pct_debt": 6.5,
            "banking_system_summary": "Extremely healthy, well-capitalized banking system (BDO Unibank, BPI, Metrobank) with capital adequacy ratios over 16.5% and low NPLs (~3.4%).",
            "domestic_institutional_anchor": "Government Service Insurance System (GSIS), Social Security System (SSS), and domestic trust entities absorb over 90% of local Treasury offerings."
        },
        "recent_developments": [
            "BSP lowered the target Reverse Repurchase (RRP) rate by 25bps to 6.25% in August, signaling another 25bp cut before year-end.",
            "Headline inflation decelerated sharply to 3.3% YoY in August (from 4.4% in July), driven by falling food and transport costs.",
            "Executive Order 62 took full effect, reducing imported rice tariffs from 35% to 15% and lowering retail staple prices across major metropolitan areas.",
            "Gross international reserves climbed to $107.9B, reaching the highest level in over two years."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-17", "event": "BSP Monetary Board Rate Decision", "detail": "Consensus 25bp cut to 6.00%; watch forward guidance on 2025 terminal rate."},
                {"date": "2026-11-05", "event": "PSA Inflation Announcement", "detail": "Consensus 2.9% YoY headline confirms sustainable sub-3% disinflation."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/PHP Spot", "level": "> 57.20", "action": "Watch for BSP currency defense; consider short-term NDF hedges."},
                {"metric": "10Y FXTN Yield", "level": "> 6.35%", "action": "Stop loss on Philippine duration position."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Global Rice Prices (Thai 5% broken)", "threshold": "> $650/MT", "impact": "Threatens food disinflation and slows BSP rate cuts."},
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Widens trade deficit and increases pump fuel prices."}
            ]
        }
    },

    "egypt": {
        "investment_thesis": {
            "stance": "Clip 3M-9M Front-End T-Bills Carry Roll / Avoid Long-End 10Y Bond Duration",
            "horizon": "3M - 6M Rolling High Carry",
            "expression": "Invest in 3M - 6M Egyptian Treasury Bills (Azwn) at ~28.5% - 29.5% annualized nominal yield unhedged. Target $3M - $5M USD cash allocation (~EGP 200 Million). Avoid long-end fixed-rate bonds (25.50% yield offers no term premium).",
            "core_thesis": "Egypt has executed an unprecedented macroeconomic stabilization program following its March 2024 currency float and 600bp emergency rate hike to 27.25%. Backed by the UAE's $35B Ras El Hekma direct investment, an expanded $8B IMF program, and $8B from the EU, the acute foreign currency liquidity crisis has been resolved. While headline inflation remains elevated (26.2% YoY), 12M forward inflation is projected to plummet toward 16.50%, generating a colossal +10.75% ex-ante real policy rate. Rolling 3M T-Bills yields ~2.4% per month, generating massive carry with controlled currency crawl."
        },
        "positives": [
            "Colossal Ex-Ante Real Policy Rate (+10.75%): 27.25% CBE overnight deposit rate vs 16.50% IMF forward trajectory delivers elite carry protection.",
            "Game-Changing UAE Ras El Hekma Bailout ($35B): The largest inward FDI deal in Egyptian history immediately eliminated the parallel foreign exchange market and replenished reserves.",
            "Restored FX Liquidity & Net Foreign Asset Reversal: Net foreign assets across the commercial banking system turned positive for the first time in over two years.",
            "Multilateral Financing Shield: Over $50B in combined commitments from the IMF, World Bank, European Union, and Gulf sovereign wealth funds.",
            "Extremely Undervalued REER (-32.5%): Currency float from 30.9 to 48.5 USD/EGP restored export competitiveness and spurred tourism and remittances."
        ],
        "negatives": [
            "Severe Red Sea Shipping Crisis: Houthi attacks in the Bab el-Mandeb strait have slashed Suez Canal transit revenues by over 60% (~$5B/year loss).",
            "High Headline Inflation Burden: Trailing CPI at 26.20% YoY driven by mandatory subsidy phase-outs on fuel, electricity, and subsidized bread.",
            "Massive Public Debt-to-GDP (88.5%): Heavy domestic interest expenditure consumes over 55% of total government revenues.",
            "Severe Regional Geopolitical Exposure: Proximity to the Gaza conflict and Middle East escalations poses ongoing tourism and regional security risks.",
            "Inverted Sovereign Curve: 10Y government bond yields 25.50%, trading 175 bps below the policy rate and offering no duration risk premium."
        ],
        "economic_structure": {
            "gdp_mix": {"services": 54.0, "industry": 34.0, "agriculture_mining": 12.0},
            "top_exports": ["Refined Petroleum & LNG (25%)", "Fertilizers & Chemicals (15%)", "Textiles & Ready-Made Garments (6%)", "Agricultural Citrus & Potatoes (8%)", "Building Materials (5%)"],
            "top_trading_partners": ["United Arab Emirates (12%)", "Italy (8%)", "Saudi Arabia (7%)", "Turkey (6%)", "United States (5%)"],
            "public_debt_pct_gdp": 88.5,
            "foreign_ownership_pct_debt": 18.0,
            "banking_system_summary": "Liquid, resilient banking system anchored by dominant state banks (National Bank of Egypt, Banque Misr, CIB) with capital adequacy above 18%.",
            "domestic_institutional_anchor": "State-owned banks and domestic insurance entities hold over 75% of local Treasury bill and bond stock."
        },
        "recent_developments": [
            "Central Bank of Egypt held the overnight deposit rate at 27.25% in September, affirming that monetary policy will remain restrictive until disinflation is sustained.",
            "Foreign portfolio investment in Egyptian Treasury bills reached an all-time record of over $38B, driven by global carry trade accounts.",
            "Headline inflation printed at 26.2% YoY in August, reflecting the impact of domestic fuel price adjustments.",
            "Prime Minister Mostafa Madbouly confirmed receipt of all $35B installments from Abu Dhabi Developmental Holding Company (ADQ)."
        ],
        "what_to_watch": {
            "key_triggers": [
                {"date": "2026-10-17", "event": "CBE Monetary Policy Committee Meeting", "detail": "Consensus hold at 27.25%; watch for forward guidance on 2025 rate cut timeline."},
                {"date": "2026-11-10", "event": "CAPMAS Monthly Inflation Release", "detail": "Consensus disinflation momentum toward 23% confirms ex-ante real return."}
            ],
            "technical_invalidation_levels": [
                {"metric": "USD/EGP Spot", "level": "> 50.50", "action": "Watch for parallel market recurrence; exit unhedged T-Bill positions."},
                {"metric": "Commercial Banks NFA", "level": "Turns negative by > $2B", "action": "Warning signal of foreign exchange drainage."}
            ],
            "commodity_sensitivities": [
                {"commodity": "Brent Crude", "threshold": "> $85/bbl", "impact": "Increases domestic fuel subsidy burden on federal budget."},
                {"commodity": "Global Wheat (CBOT)", "threshold": "> $7.00/bushel", "impact": "Pressures state grain buyer (GASC) import bill."}
            ]
        }
    }
}
