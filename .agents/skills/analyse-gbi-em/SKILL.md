---
name: analyse-gbi-em
description: Autonomous GBI-EM local currency sovereign debt and FX strategy workflow. Analyzes 8 core benchmark countries (Brazil, Mexico, South Africa, Indonesia, Poland, India, Colombia, Turkey), calculates real yields, checks 50d/200d SMAs and RSI14, evaluates central bank policies and fiscal dynamics, formulates exact curve points & instruments (NTN-F 2029, M-Bono 2034, SAGB R2035, etc.), unhedged vs FX-hedged directives, flags sideways/rangebound regimes, and updates local_em.html and gbi_em_data.json on GitHub Pages (rkarim25/Strategy). Use when the user says "analyse GBI EM", "analyse Local EM", "analyse gbi em", "GBI EM analysis", or invokes /analyse-gbi-em.
---

# Analyse GBI-EM — Local Currency Sovereign Debt & FX Strategy Skill

This skill provides an autonomous execution protocol for analyzing local currency emerging market sovereign debt and foreign exchange (GBI-EM), ranking countries by real yields, formulating trade expressions (curve points, specific instruments, and unhedged vs FX-hedged directives), identifying sideways/rangebound markets, and deploying updates to `local_em.html` on GitHub Pages (`rkarim25/Strategy`).

---

## 0. Non-Negotiables & Rules
1. **Reza's time is the scarce resource**: Deliver a concise executive summary (~10-15 lines) highlighting real yield ranking, top overweights, sideways warnings, and explicit trade expressions.
2. **Every country recommendation must have**:
   - **Specific curve point** (e.g. 5Y belly, 10Y duration, 3M-6M T-Bills).
   - **Specific instrument** (e.g. NTN-F 2029, M-Bono 2034, SAGB R2035, SUN FR0100, IGB 2033, TES 2033).
   - **Explicit FX Hedging Directive**: Unhedged vs FX-Hedged vs Sideways.
   - **Upcoming catalysts to watch**.
3. **If a market is sideways/rangebound, state that explicitly** (e.g. Mexico 8.40-8.90% M-Bono range; Colombia 10.40-10.90% TES range).
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
- Sorts countries into the Real Yield Ranking table.
- Generates `gbi_em_data.json`.

### Step 2: Review Core 8 Benchmark Countries
1. 🇧🇷 **Brazil (BRL)**: Top Real Yield (+8.10%). Long NTN-F 2029 (5Y belly), Unhedged BRL carry. Selic at 10.50%.
2. 🇿🇦 **South Africa (ZAR)**: Real Yield (+6.25%). Long SAGB R2035 (10Y), FX-Hedged ZAR. GNU political stability; hedge high-beta currency volatility.
3. 🇮🇩 **Indonesia (IDR)**: Real Yield (+4.70%). Long SUN FR0100 (10Y), Unhedged IDR. Low inflation (2.12%), strict statutory fiscal deficit (<3%).
4. 🇮🇳 **India (INR)**: Real Yield (+3.44%). Long IGB 2033 (7.18% GS 2033), FX-Hedged INR. Structural index inclusion inflows ($2B/mo).
5. 🇲🇽 **Mexico (MXN)**: Real Yield (+3.67%). **Neutral / Sideways Range (8.40%–8.90%)**, Strictly FX-Hedged MXN. Banxico easing offset by constitutional judicial reforms.
6. 🇨🇴 **Colombia (COP)**: Real Yield (+3.80%). **Neutral / Sideways Range (10.40%–10.90%)**, FX-Hedged COP. Fiscal rule suspension overhang and sticky 6.85% inflation.
7. 🇵🇱 **Poland (PLN)**: Real Yield (+1.05%). **Underweight / Pay 5Y PLN IRS**, FX-Hedged. Real yield compressed to +1.05% as inflation rebounds to 4.3%.
8. 🇹🇷 **Turkey (TRY)**: Real Yield (-23.57% spot). **Underweight Long Duration / Long Ultra-Short Carry**. Buy 3M-6M T-Bills, Unhedged TRY. Harvest 50% Selic carry with strict stops.

### Step 3: Check Upcoming Catalysts & Invalidation Triggers
- Central bank interest rate decisions (Copom, Banxico, SARB, BI, RBI, NBP, BanRep, CBRT).
- Commodity terms of trade (Brent crude for Colombia, iron ore for Brazil, coal/gold for South Africa).
- Currency technical invalidation levels (e.g. USDBRL > 5.70, USDMXN > 20.20, USDZAR > 18.60).

### Step 4: Commit & Deploy
```powershell
git -C "C:\Users\Reza Karim\Strategy" add local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py gbi_em_data.json docs/runbooks/analyse-gbi-em.md site-nav.js
git -C "C:\Users\Reza Karim\Strategy" commit -m "Refresh GBI-EM local sovereign debt & FX recommendations"
git -C "C:\Users\Reza Karim\Strategy" push origin main
```
Verify live deployment at `https://rkarim25.github.io/Strategy/local_em.html`.

### Step 5: Output Concise Executive Summary
Format the final response for Reza:
- Real Yield Ranking table.
- Top conviction trades (instruments, points, unhedged vs hedged).
- Sideways rangebound calls.
- Key catalysts to watch.\n