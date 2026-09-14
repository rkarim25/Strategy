---
name: analyse-gbi-em
description: Autonomous GBI-EM local currency sovereign debt and FX strategy workflow. Analyzes 8 core benchmark countries (Brazil, Mexico, South Africa, Indonesia, Poland, India, Colombia, Turkey), evaluates geopolitical transmission channels and how they influence trade recommendations, tracks dated catalysts (central bank meetings, CPI releases, budgets), incorporates live macro data anchors (Brent crude oil, copper, gold, DXY, UST 10Y), calculates real yields, checks 50d/200d SMAs and RSI14, formulates exact curve points & instruments (NTN-F 2029, M-Bono 2034, SAGB R2035, etc.), unhedged vs FX-hedged directives, flags sideways/rangebound regimes, and updates local_em.html and gbi_em_data.json on GitHub Pages (rkarim25/Strategy). Use when the user says "analyse GBI EM", "analyse Local EM", "analyse gbi em", "GBI EM analysis", or invokes /analyse-gbi-em.
---

# Analyse GBI-EM — Local Currency Sovereign Debt & FX Strategy Skill

This skill provides an autonomous execution protocol for analyzing local currency emerging market sovereign debt and foreign exchange (GBI-EM), ranking countries by real yields, formulating trade expressions (curve points, specific instruments, and unhedged vs FX-hedged directives), evaluating geopolitical transmission channels and their direct influence on trade structure, incorporating dated upcoming catalysts (central bank decisions, CPI releases, budget deadlines), embedding live macro commodity anchors (Brent crude, copper, gold, DXY, UST 10Y), identifying sideways/rangebound markets, and deploying updates to `local_em.html` on GitHub Pages (`rkarim25/Strategy`).

---

## 0. Non-Negotiables & Rules

1. **Reza's time is the scarce resource**: Deliver a concise executive summary (~10-15 lines) highlighting real yield ranking, top overweights, sideways warnings, and explicit trade expressions.
2. **Every country recommendation must have**:
   - **Specific curve point** (e.g. 5Y belly, 10Y duration, 3M-6M T-Bills).
   - **Specific instrument** (e.g. NTN-F 2029, M-Bono 2034, SAGB R2035, SUN FR0100, IGB 2033, TES 2029).
   - **Explicit FX Hedging Directive**: Unhedged vs FX-Hedged vs Sideways.
   - **Geopolitical Driver & Direct Trade Influence**: State the primary geopolitical factor (e.g. Middle East energy shocks, US election tariffs, Russia-NATO defense spending, GNU coalition stability) and explicitly explain *how geopolitics alters or dictates the trade recommendation* (e.g. why M-Bonos must be FX-hedged, why Colombia COP acts as an oil hedge, why South Africa SAGBs rally on GNU stability).
   - **Dated Upcoming Catalysts**: Include exact calendar dates for upcoming Central Bank policy meetings (Copom, Banxico, SARB, BI, NBP, RBI, BanRep, TCMB, FOMC), CPI prints, and budget statements.
   - **Macro Data Points**: Explicitly cite relevant commodity and macro data points (Brent Crude oil price, copper, gold, DXY index, US 10Y yield, domestic FX reserve cover, current account and fiscal balances).
3. **If a market is sideways/rangebound, state that explicitly** (e.g. Mexico 19.00-19.80 USD/MXN range; Colombia 4,050-4,300 USD/COP range).
4. **Repository location**: `C:\Users\Reza Karim\Strategy`. Remote: `origin main`.
5. **Never git add . / -A**: Stage explicit files (`local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py gbi_em_data.json docs/runbooks/analyse-gbi-em.md site-nav.js`).

---

## 1. Execution Workflow

### Step 1: Execute GBI-EM Engine
From `C:\Users\Reza Karim\Strategy`:
```powershell
python "C:\Users\Reza Karim\Strategy\generate_gbi_em_data.py"
```
This script computes:
- Real yields = 10Y benchmark yield minus latest headline CPI YoY.
- Policy rate spreads and central bank real policy rates.
- Technical indicators for local FX pairs (USD/BRL, USD/MXN, USD/ZAR, USD/IDR, USD/INR, EUR/PLN, USD/COP, USD/TRY): 50-day SMA, 200-day SMA, and 14-day RSI.
- Geopolitical transmission channels for all 8 countries and cross-desk risk radar.
- Chronologically sorted upcoming dated catalyst calendar (Central bank decisions, CPI releases).
- Live macro commodity anchors (Brent Crude, Copper, Gold, DXY, US 10Y).
- Generates `gbi_em_data.json`.

### Step 2: Review Core 8 Benchmark Countries
1. 🇧🇷 **Brazil (BRL)**: Top Real Yield (+8.00% nominal / +6.30% ex-ante). Long NTN-F 2029 (5Y belly), Unhedged BRL carry or 3M NDF hedged. Selic at 10.50%. Macro: Brent Crude $74.20, FX Reserves $355B. Geopolitics: Fiscal deficit debates require monitoring; high reserve buffer protects BRL.
2. 🇿🇦 **South Africa (ZAR)**: Real Yield (+4.55% / +4.20% ex-ante). Long SAGB R2035 (10Y), Unhedged ZAR. Top conviction call. Macro: Gold $2,580/oz (+1.4% terms of trade boom), Brent $74.20. Geopolitics: GNU coalition political stability + 170 days zero loadshedding.
3. 🇮🇳 **India (INR)**: Real Yield (+3.13% / +2.80% ex-ante). Long IGB 2033 (7.18% GS 2033), Unhedged INR. Core low-volatility anchor asset. Macro: Crude $74.20, RBI FX Reserves record $683B. Geopolitics: Middle East Hormuz oil chokepoint sensitivity balanced by discounted Russian crude and $683B reserve defense.
4. 🇲🇽 **Mexico (MXN)**: Real Yield (+4.47% / +4.60% ex-ante). **Neutral / Sideways Range (19.00-19.80)**, Strictly FX-Hedged M-Bonos or 2s10s flattener. Macro: US 10Y 4.96%, USD/MXN 19.32. Geopolitics: US election tariff rhetoric (10-20% universal tariff risk) and judicial reforms warrant strict currency hedging.
5. 🇮🇩 **Indonesia (IDR)**: Real Yield (+4.43% / +3.85% ex-ante). Long SUN FR0100 (10Y), FX-Hedged IDR. Macro: Headline CPI 2.12%, Nickel $16,200/MT, FX Reserves $150.2B. Geopolitics: Commodity downstreaming mandates and US-China Malacca transit.
6. 🇵🇱 **Poland (PLN)**: Real Yield (+1.05% / +1.40% ex-ante). **Underweight Local Bonds / Bullish PLN vs EUR**. Macro: Defense spending 4.7% GDP, Fiscal deficit -5.5% GDP, EU KPO Inflows €60B+. Geopolitics: NATO Eastern Flank defense burden crowds out bond real yields; EU fund conversion powers Zloty.
7. 🇨🇴 **Colombia (COP)**: Real Yield (+4.38% / +4.50% ex-ante). **Neutral / Sideways Range (4,050-4,300)**, FX-Hedged 5Y TES. Macro: Brent Crude $74.20 (40% of exports), Fiscal Deficit -5.6% GDP. Geopolitics: Hydrocarbon exploration ban and Fiscal Rule flexibility debates; long COP serves as tactical hedge against oil price surges.
8. 🇹🇷 **Turkey (TRY)**: Real Yield (-19.47% spot / +5.00% ex-ante). **Underweight Long Duration / Long Ultra-Short Carry**. 1M-3M T-Bills & TRY cash deposits, Unhedged roll. Macro: Policy rate 50.00%, Carry +44%, Brent $74.20. Geopolitics: NATO-Russia balancing act and Gulf FDI swap inflows ($50B+) anchoring TCMB reserves.

### Step 3: Check Upcoming Dated Catalysts & Invalidation Triggers
- Central bank interest rate decisions with exact dates (Copom, Banxico, SARB, BI, RBI, NBP, BanRep, TCMB, US FOMC).
- Commodity terms of trade (Brent crude for Colombia/India/Turkey, gold for South Africa, copper/nickel for Indonesia).
- Currency technical invalidation levels (e.g. USDBRL > 5.65, USDMXN > 19.80, USDZAR > 18.20).

### Step 4: Commit & Deploy
```powershell
git -C "C:\Users\Reza Karim\Strategy" add local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py gbi_em_data.json docs/runbooks/analyse-gbi-em.md site-nav.js
git -C "C:\Users\Reza Karim\Strategy" commit -m "Update GBI-EM with geopolitics, dated catalysts, and commodity macro anchors"
git -C "C:\Users\Reza Karim\Strategy" push origin main
```
Verify live deployment at `https://rkarim25.github.io/Strategy/local_em.html`.

### Step 5: Output Concise Executive Summary
Format the final response for Reza:
- Macro commodity anchors (Brent, Copper, Gold, DXY).
- Real Yield Ranking table.
- Top conviction trades (instruments, points, unhedged vs hedged).
- Geopolitical transmission & dated catalyst calendar highlights.
- Sideways rangebound warnings.
