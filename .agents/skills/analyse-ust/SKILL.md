---
name: analyse-ust
description: Autonomous US Treasury curve, macro regime, and rate recommendation workflow. Fetches live generic yields (2Y, 5Y, 10Y, 30Y), calculates curve spreads (2s10s, 2s30s, 5s10s, 5s30s, 10s30s), marks to market active trade recommendations,, evaluates 50d/200d SMAs and RSI14, scans economic headlines, and updates the live UST page (ust.html) on GitHub Pages. Use when the user says "analyse UST", "update UST", "analyse ust", "UST curve analysis", or invokes /analyse-ust.
---

# Analyse UST — US Treasury Curve & Macro Regime Strategy Skill

This skill provides an autonomous execution protocol for analyzing the US Treasury yield curve, classifying the macroeconomic regime, computing curve spreads, and refreshing the live **US Treasuries** dashboard (`ust.html`) on GitHub Pages (`rkarim25/Strategy`).

---

## 0. Non-Negotiables & Rules
1. **Reza's time is the scarce resource**: Never make him read a long report — present about ten lines with clear trade expressions, then the question.
2. **Never invent a number**: Every yield, spread, SMA, and RSI must be computed directly from live data or historical series in this session.
3. **Repository location**: All files live at `C:\Users\Reza Karim\Strategy`. The remote is `https://github.com/rkarim25/Strategy.git` (`main` branch).
4. **Never git add . / -A**: Stage explicit files (`git add ust.html ust-page.js generate_ust_data.py ust_curve_data.json ust_daily.csv docs/runbooks/analyse-ust.md site-nav.js`).

---

## 1. Execution Workflow

### Step 1: Fetch Live Yields & Historical Series
Execute the Python yield curve engine from `C:\Users\Reza Karim\Strategy`:
```powershell
python "C:\Users\Reza Karim\Strategy\generate_ust_data.py"
```
This script:
- Fetches generic benchmarks from Yahoo Finance (`2YY=F`, `^FVX`, `^TNX`, `^TYX`).
- Computes core curve spreads:
  - **2s10s** (Benchmark slope)
  - **5s30s** (Belly to long-end slope)
  - **2s30s** (Total curve slope)
  - **10s30s** (Long-end term premium)
- Computes technical indicators: 50-day SMA, 200-day SMA, and 14-day RSI for each tenor.
- Generates `ust_curve_data.json` and updates historical records.

### Step 2: Review Macro Telemetry & Headlines
Verify current economic conditions via headline search:
- **Inflation**: Headline CPI YoY, Core PCE YoY.
- **Labor**: Non-Farm Payrolls, Unemployment Rate.
- **Fiscal / Supply**: Treasury refunding announcements, annual deficit projections, term premium estimates (ACM/NY Fed model).
- **Fed Expectations**: Implied Fed Funds terminal rate and FOMC rate path.

### Step 3: Classify Yield Curve Regime & Curve Point Preference
Classify into one of the core regimes:
1. **Bear Steepening** (Fiscal Dominance / Sticky Inflation): Overweight 5Y Note belly & 2Y; Underweight 30Y Bond. Favor 2s10s or 5s30s curve steepeners.
2. **Bull Flattening** (Recession / Emergency Easing): Overweight 10Y/30Y duration; buy long bonds.
3. **Bear Flattening** (Aggressive Fed Hikes): Underweight all duration; hide in ultra-short cash / T-Bills.
4. **Bull Steepening** (Disinflationary Fed Normalization): Overweight front-end (2Y/5Y); curve steepeners outperform.

### Step 4: Evaluate Technical Invalidation Triggers
Check the three quantitative trigger conditions:
- **Pivot to Long Duration (Bull Flattening)**: 10Y < 4.70% & 2s10s < +25 bps & Unemployment > 4.6%.
- **Accelerated Steepener (Bond Vigilantes)**: 10Y > 5.05% & 30Y > 5.40%.
- **Bear Flattener (Ultra-Short Cash)**: 2Y > 4.85% & CPI > 3.7%.

### Step 5: Update Data & Deploy
1. Re-run `python generate_ust_data.py` if custom headline commentary or updated trigger flags are required.
2. Stage and commit:
```powershell
git -C "C:\Users\Reza Karim\Strategy" add ust.html ust-page.js generate_ust_data.py ust_curve_data.json ust_daily.csv docs/runbooks/analyse-ust.md site-nav.js
git -C "C:\Users\Reza Karim\Strategy" commit -m "Refresh UST curve analysis, macro regime, and rate recommendations"
git -C "C:\Users\Reza Karim\Strategy" push origin main
```
3. Verify live deployment at `https://rkarim25.github.io/Strategy/ust.html`.

### Step 6: Output Concise Executive Summary
Format the final response for Reza:
- Table of generic yields (2Y, 5Y, 10Y, 30Y) and spreads (2s10s, 5s30s).
- Current Macro Regime & Top Tenor Pick.
- DV01-neutral steepener/flattener trade expression.
- Key technical invalidation triggers.\n