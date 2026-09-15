---
name: analyse-gbi-em
description: Autonomous GBI-EM local currency sovereign debt and FX strategy workflow. Analyzes the full 17 liquid benchmark countries across LatAm (Brazil, Mexico, Colombia, Chile, Peru), EMEA (South Africa, Poland, Czech Republic, Hungary, Romania, Turkey, Egypt), and Asia (Indonesia, India, Malaysia, Thailand, Philippines). Features explicit ex-ante real rates arithmetic (Nominal Policy Rate − 12M Forward CPI = Ex-Ante Real Rate), Terms of Trade (ToT) & 10Y REER valuation matrix, Rates Pay / Receive & Institutional Execution Desk (DV01 risk sizing, standard market clips, liquidity tiers, clearing venues, and local trader lingo), geopolitical transmission channels, dated upcoming catalysts, and live trade tracking synced to GitHub Pages (rkarim25/Strategy). Use when the user says "analyse GBI EM", "analyse Local EM", "analyse gbi em", "GBI EM analysis", or invokes /analyse-gbi-em.
---

# Analyse GBI-EM — Local Currency Sovereign Debt & FX Strategy Skill

This skill provides an autonomous execution protocol for analyzing local currency emerging market sovereign debt and foreign exchange (GBI-EM), covering all **17 sovereign benchmark constituents** of the J.P. Morgan GBI-EM Global Diversified index where reliable institutional data exists:
- **Latin America (5):** Brazil (BRL), Mexico (MXN), Colombia (COP), Chile (CLP), Peru (PEN)
- **EMEA (7):** South Africa (ZAR), Poland (PLN), Czech Republic (CZK), Hungary (HUF), Romania (RON), Turkey (TRY), Egypt (EGP)
- **Emerging Asia (5):** Indonesia (IDR), India (INR), Malaysia (MYR), Thailand (THB), Philippines (PHP)

---

## 0. Non-Negotiables & Rules

1. **Reza's time is the scarce resource**: Deliver a concise executive summary (~10-15 lines) highlighting real yield ranking, top overweights, sideways warnings, and explicit trade expressions.
2. **Every country recommendation must have**:
   - **Specific curve point & instrument**: (e.g. 5Y belly NTN-F 2029, 10Y duration SAGB R2035, M-Bono 2034, 1M-3M T-Bills).
   - **Explicit Real Rate Arithmetic**: Always state the nominal policy rate, policy rate name, 12M forward-looking inflation expectation (with official central bank survey source), and the explicit formula (`Nominal Policy Rate − 12M Forward CPI = Ex-Ante Real Policy Rate`).
   - **Terms of Trade (ToT) & REER Strategic Directive**: State the 10Y REER valuation deviation (cheap vs rich), commodity Terms of Trade trend, and 5-quadrant macro mapping.
   - **Rates Pay / Receive & Execution Desk**: State trader directive (Receive Fixed, Pay Fixed, Curve Flattener, Carry Roll), benchmark swap/futures instrument, benchmark cash bond, liquidity tier, bid-ask spread, standard market clip, clearinghouse, DV01 risk sizing ($10,000 DV01 standard), and local trader lingo.
   - **Explicit FX Hedging Directive**: Unhedged vs FX-Hedged vs Sideways.
   - **Geopolitical Driver & Direct Trade Influence**: State the primary geopolitical factor and explain *how geopolitics alters or dictates the trade recommendation*.
   - **Dated Upcoming Catalysts**: Include exact calendar dates for upcoming Central Bank meetings, CPI prints, and budget deadlines.
   - **Macro Data Points**: Cite relevant commodity and macro data points (Brent Crude, copper, gold, DXY, US 10Y, FX reserves, current account).
   - **Trade Recommendation Tracking**: Every actionable trade idea must be stored in `macro_trade_tracker.json` and tracked with entry level, current MTM level, target, stop loss, and real-time P&L in bps and USD.
3. **If a market is sideways/rangebound, state that explicitly** (e.g. Mexico 19.00-19.80 USD/MXN range; Colombia 4,050-4,300 USD/COP range).
4. **Repository location**: `C:\Users\Reza Karim\Strategy`. Remote: `origin main`.
5. **Never git add . / -A**: Stage explicit files (`local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py additional_gbi_countries.py gbi_em_data.json trade_tracker.py macro_trade_tracker.json docs/runbooks/analyse-gbi-em.md site-nav.js`).

---

## 1. Execution Workflow

### Step 1: Execute GBI-EM Engine & Trade Tracker
From `C:\Users\Reza Karim\Strategy`:
```powershell
python "C:\Users\Reza Karim\Strategy\generate_gbi_em_data.py"
python "C:\Users\Reza Karim\Strategy\trade_tracker.py"
```
This script computes:
- Real rates breakdown for all 17 countries: Nominal policy rate, trailing CPI, 12M forward inflation survey, and ex-ante arithmetic.
- Rates Pay / Receive Execution Desk matrix: Directives, swaps, cash bonds, liquidity tiers, standard clips, and DV01 sizing.
- Terms of Trade (ToT) & REER 5-quadrant framework.
- Trade tracker sync: Marks all open and closed trade recommendations across desks to market.
- Technical indicators (50d/200d SMAs, RSI14) for all local currencies.
- Geopolitical transmission channels across energy, tariffs, and defense.
- 40+ upcoming dated catalyst calendar events.
- Live macro commodity anchors (Brent Crude, Copper, Gold, DXY, US 10Y).
- Generates `gbi_em_data.json` and updates `local_em.html`.

### Step 2: Review Benchmark Constituents by Region
- **LatAm (5):** Brazil (NTN-F 2029 / B3 DI1F29), Mexico (M-Bono 2034 / TIIE 2s10s flattener), Colombia (TES 2029 / IBR OIS), Chile (BTP 2034 / Camara OIS), Peru (Soberano 2034 / PEN TIIE).
- **EMEA (7):** South Africa (SAGB R2035 / ZAR IRS), Poland (POLGB / Pay 10Y WIBOR IRS), Czech Republic (CZGB 2033 / PRIBOR IRS), Hungary (HGB 2034 / BUBOR IRS), Romania (ROMGB 2029 / ROBOR IRS), Turkey (1M-3M T-Bills Carry Roll), Egypt (3M T-Bills Carry Roll).
- **Asia (5):** Indonesia (SUN FR0100 / NDS OIS), India (IGB 7.18% 2033 FAR / MIBOR OIS), Malaysia (MGS 2034 / Long MYR spot), Thailand (Thai LB 2034 / THOR OIS), Philippines (FXTN 2034 / BVAL swaps).
1. 🇧🇷 **Brazil (BRL)**: Selic 10.50% − 3.90% Focus Survey = +6.60% Ex-Ante Real Policy Rate. 10Y Yield 12.20% (Ex-Ante Real 8.30%). Quadrant 2: High Carry Belly Rates. Long NTN-F 2029 (5Y belly), Unhedged BRL carry or 3M NDF hedged. REER -9.2% (Cheap). Macro: Brent $74.20, FX Reserves $355B.
2. 🇿🇦 **South Africa (ZAR)**: Repo 8.25% − 4.35% BER Survey = +3.90% Ex-Ante Real Policy Rate. 10Y Yield 9.15% (Ex-Ante Real 4.80%). Quadrant 1: Double Alpha. Long SAGB R2035 (10Y), Unhedged ZAR. Top conviction call. REER -14.5% (Extremely Undervalued). Macro: Gold $2,580/oz (+1.4% terms of trade boom), Brent $74.20. Geopolitics: GNU coalition stability + 170 days zero loadshedding.
3. 🇮🇳 **India (INR)**: Repo 6.50% − 4.10% RBI Survey = +2.40% Ex-Ante Real Policy Rate. 10Y Yield 6.78% (Ex-Ante Real 2.68%). Quadrant 4: Capital Inflow / Peg Proxy. Long IGB 2033 (7.18% GS 2033), Unhedged INR. Core low-volatility anchor asset. Macro: Crude $74.20, RBI FX Reserves record $683B. Geopolitics: Middle East Hormuz oil chokepoint sensitivity balanced by discounted Russian crude and $683B reserve defense.
4. 🇲🇽 **Mexico (MXN)**: TIIE 10.50% − 3.80% Banxico Survey = +6.70% Ex-Ante Real Policy Rate. 10Y Yield 9.47% (Ex-Ante Real 5.67%). Quadrant 3: FX-Hedged Rates Duration. **Neutral / Sideways Range (19.00-19.80)**, Strictly FX-Hedged M-Bonos or 2s10s flattener. REER +4.1% (Slightly Rich). Macro: US 10Y 4.96%, USD/MXN 19.32. Geopolitics: US election tariff rhetoric (10-20% universal tariff risk) and judicial reforms warrant strict currency hedging.
5. 🇮🇩 **Indonesia (IDR)**: BI 7-Day Repo 6.25% − 2.40% BI Consensus = +3.85% Ex-Ante Real Policy Rate. 10Y Yield 6.55% (Ex-Ante Real 4.15%). Quadrant 3: FX-Hedged Duration. Long SUN FR0100 (10Y), FX-Hedged IDR. REER -3.2% (Fair Value). Macro: Headline CPI 2.12%, Nickel $16,200/MT, FX Reserves $150.2B. Geopolitics: Commodity downstreaming mandates and US-China Malacca transit.
6. 🇵🇱 **Poland (PLN)**: NBP 5.75% − 3.70% NBP Survey = +2.05% Ex-Ante Real Policy Rate. 10Y Yield 5.35% (Ex-Ante Real 1.65%). Quadrant 4: Structural Capital Inflows. **Underweight Local Bonds / Bullish PLN vs EUR**. Macro: Defense spending 4.7% GDP, Fiscal deficit -5.5% GDP, EU KPO Inflows €60B+. Geopolitics: NATO Eastern Flank defense burden crowds out bond real yields; EU fund conversion powers Zloty.
7. 🇨🇴 **Colombia (COP)**: BanRep 10.75% − 4.80% BanRep Survey = +5.95% Ex-Ante Real Policy Rate. 10Y Yield 10.50% (Ex-Ante Real 5.70%). Quadrant 3: FX-Hedged Duration. **Neutral / Sideways Range (4,050-4,300)**, FX-Hedged 5Y TES. REER -4.8% (Slightly Cheap). Macro: Brent Crude $74.20 (40% of exports), Fiscal Deficit -5.6% GDP. Geopolitics: Hydrocarbon exploration ban and Fiscal Rule flexibility debates; long COP serves as tactical hedge against oil price surges.
8. 🇹🇷 **Turkey (TRY)**: TCMB 50.00% − 28.50% TCMB Survey = +21.50% Ex-Ante Real Policy Rate. 10Y Yield 32.50% (Ex-Ante Real 4.00%, trailing CPI -19.47% is misleading). Quadrant 5: Front-End Hyper-Carry Roll. **Underweight Long Duration / Long Ultra-Short Carry**. 1M-3M T-Bills & TRY cash deposits, Unhedged roll. Macro: Policy rate 50.00%, Carry +44%, Brent $74.20. Geopolitics: NATO-Russia balancing act and Gulf FDI swap inflows ($50B+) anchoring TCMB reserves.
9. 🇨🇱 **Chile (CLP)**: BCCh TPM 5.50% − 3.20% EEE Survey = +2.30% Ex-Ante Real Policy Rate. 10Y BTP 5.35% (Ex-Ante Real 2.15%). Quadrant 1: Double Alpha. Long BTP 2034 / Receive 5Y/10Y Camara OIS, Unhedged CLP. REER -8.2% (Cheap). Macro: Copper $4.22/lb (+8.4% YoY), FX Reserves $43.8B.
10. 🇵🇪 **Peru (PEN)**: BCRP 5.25% − 2.20% Survey = +3.05% Ex-Ante Real Policy Rate. 10Y Soberano 5.85% (Ex-Ante Real 3.65%). Quadrant 1: Double Alpha. Long Soberano 2034 / PEN TIIE, Unhedged PEN. REER -5.5% (Cheap). Macro: Headline CPI 2.03% (anchored inside target), FX Reserves $82.5B (30% GDP eliminates FX vol).
11. 🇨🇿 **Czech Republic (CZK)**: CNB 4.25% − 2.10% FMAS Survey = +2.15% Ex-Ante Real Policy Rate. 10Y CZGB 3.85% (Ex-Ante Real 1.75%). Quadrant 3: FX-Hedged Duration. Long 10Y CZGB / Receive PRIBOR IRS with EUR/CZK forward hedge. REER +3.5%. Macro: AA- sovereign credit, debt 44% GDP.
12. 🇭🇺 **Hungary (HUF)**: MNB 6.75% − 3.50% Survey = +3.25% Ex-Ante Real Policy Rate. 10Y HGB 6.45% (Ex-Ante Real 2.95%). Quadrant 2: High Carry Belly Rates. Receive 5Y HGB / BUBOR IRS, NDF hedged. REER -6.1% (Cheap). Macro: Highest carry in CEE (+5.8% 3M carry over EUR).
13. 🇷🇴 **Romania (RON)**: NBR 6.50% − 4.00% Survey = +2.50% Ex-Ante Real Policy Rate. 10Y ROMGB 6.65% (Ex-Ante Real 2.65%). Quadrant 3: FX-Hedged Duration. Receive 5Y ROMGB strictly FX-hedged / avoid long end. REER +6.8% (Overvalued). Macro: High budget deficit (7.2% GDP).
14. 🇲🇾 **Malaysia (MYR)**: BNM OPR 3.00% − 2.20% Survey = +0.80% Ex-Ante Real Policy Rate. 10Y MGS 3.75% (Ex-Ante Real 1.55%). Quadrant 4: Balance of Payments Inflow Anchor. Long MYR spot/forward; neutral MGS duration. Macro: Tech FDI surge, current account surplus +2.8% GDP, FX Reserves $116.8B.
15. 🇹🇭 **Thailand (THB)**: BOT 2.50% − 1.20% Survey = +1.30% Ex-Ante Real Policy Rate. 10Y Thai LB 2.55% (Ex-Ante Real 1.35%). Quadrant 4: Balance of Payments Inflow Anchor. Receive 5Y/10Y Thai LB duration (headline CPI 0.35% creates rate cut pressure). REER -2.5%. Macro: Current account surplus +2.2% GDP, FX Reserves $225B.
16. 🇵🇭 **Philippines (PHP)**: BSP 6.25% − 3.10% Survey = +3.15% Ex-Ante Real Policy Rate. 10Y FXTN 5.95% (Ex-Ante Real 2.85%). Quadrant 2: High Carry Belly Rates. Receive 5Y/10Y FXTN duration / BVAL swaps unhedged. REER -4.2%. Macro: Easing front-runner in ASEAN, FX Reserves $106.5B.
17. 🇪🇬 **Egypt (EGP)**: CBE 27.25% − 16.50% Forward CPI = +10.75% Ex-Ante Real Policy Rate. 3M T-Bills 29.50% (Ex-Ante Real 13.00%). Special Regime: Front-End Hyper-Carry Roll. Clip 3M T-Bills roll unhedged. REER -32.5% (Extremely undervalued post-float). Macro: $35B ADQ investment, FX Reserves $46.5B.

### Step 3: Check Upcoming Dated Catalysts & Invalidation Triggers
- Central bank interest rate decisions with exact dates (Copom, Banxico, SARB, BI, RBI, NBP, BanRep, TCMB, BCCh, BCRP, CNB, MNB, NBR, BNM, BOT, BSP, CBE, US FOMC).
- Commodity terms of trade (Brent crude for Colombia/India/Turkey, gold for South Africa, copper for Chile/Peru, nickel for Indonesia).
- Currency technical invalidation levels (e.g. USDBRL > 5.65, USDMXN > 19.80, USDZAR > 18.20).

### Step 4: Commit & Deploy
```powershell
git -C "C:\Users\Reza Karim\Strategy" add local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py additional_gbi_countries.py gbi_em_data.json trade_tracker.py macro_trade_tracker.json ust_curve_data.json docs/runbooks/analyse-gbi-em.md site-nav.js
git -C "C:\Users\Reza Karim\Strategy" commit -m "Expand GBI-EM desk to full 17-country benchmark universe with real rates arithmetic and derivatives execution"
git -C "C:\Users\Reza Karim\Strategy" push origin main
```
Verify live deployment at `https://rkarim25.github.io/Strategy/local_em.html`.

### Step 5: Output Concise Executive Summary
Format the final response for Reza:
- Real Rates Breakdown (Policy Rate − 12M Forward CPI = Ex-Ante Real Rate).
- Terms of Trade & REER Decision Matrix Directives (Quadrants).
- Active Trade Recommendations & Live Mark-to-Market P&L.
- Top conviction trades (instruments, points, unhedged vs hedged).
- Geopolitical transmission & dated catalyst calendar highlights.
- Sideways rangebound warnings.
