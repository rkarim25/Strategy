---
name: analyse-cdx
description: Autonomous credit derivatives workflow covering CDX.NA.HY, iTraxx Europe Crossover, and CDX.EM. Computes spread percentiles, Transatlantic basis, technical indicators (SMA50/200, RSI14), distress ratios, 12M default forecasts, and updates cdx.html and credit_data.json on GitHub Pages (rkarim25/Strategy). Use when the user says "analyse CDX", "analyse credit", "credit spreads", or invokes /analyse-cdx.
---

# Analyse CDX — Credit Derivatives & Spreads Strategy Skill

This skill provides an autonomous execution protocol for tracking synthetic credit default swap index spreads (**CDX.NA.HY**, **iTraxx Europe Crossover**, and **CDX.EM**), evaluating corporate credit cycles, assessing Transatlantic basis divergences, and refreshing the live **CDX Desk** dashboard (`cdx.html`) on GitHub Pages (`rkarim25/Strategy`).

---

## 0. Non-Negotiables & Rules
1. **Reza's time is the scarce resource**: Provide a high-density, ~10-line executive update with clear quantitative triggers and derivative trade expressions.
2. **Never invent spread levels**: Every spread, basis, SMA, and RSI must come from the simulation or live data feed.
3. **Repository location**: `C:\Users\Reza Karim\Strategy`. Remote: `origin main`.
4. **Never git add . / -A**: Stage explicit files (`cdx.html credit.html credit-page.js generate_credit_data.py credit_data.json ANALYSE_CREDIT.md site-nav.js`).

---

## 1. Execution Workflow

### Step 1: Execute Credit Derivatives Engine
From `C:\Users\Reza Karim\Strategy`:
```powershell
python "C:\Users\Reza Karim\Strategy\generate_credit_data.py"
```
This script computes:
- Spreads and 1D changes for:
  - **CDX.NA.HY** (US High Yield)
  - **iTraxx Europe Crossover** (European High Yield / Sub-IG)
  - **CDX.EM** (Emerging Markets Sovereign)
- 52-week spread percentiles and distress ratios (% constituents > 1,000 bps).
- 12-month expected default rate forecasts.
- Technical indicators: 50-day SMA, 200-day SMA, and 14-day RSI.
- Transatlantic Basis: CDX.NA.HY minus iTraxx Europe Crossover.
- Generates `credit_data.json`.

### Step 2: Review Relative Value & Trade Expressions
- **CDX.NA.HY**: Tactical Carry / Tight Range. Yield carry ~7.6% is attractive, but with spreads at the ~28th percentile, upside compression is capped. Express via selling belly protection or OTM payer swaptions.
- **iTraxx Europe Crossover**: Long Risk / Outperformer vs US HY. ECB rate cuts support corporate refinancing.
- **CDX.EM**: Overweight Compression vs DM HY. Driven by resilient Gulf balance sheets and strong Latin American terms of trade.
- **Transatlantic Basis**: Check if US HY - Xover basis exceeds 50 bps (historical fair value ~25 bps).

### Step 3: Evaluate Quantitative Triggers
- **Risk-Off Widener**: US HY > 360 bps & Xover > 340 bps -> Shift to Long Protection.
- **Transatlantic Divergence**: US HY - Xover basis > 50 bps -> Long Xover / Short US HY basis compression trade.
- **EM Spread Compression Breakout**: CDX.EM < 160 bps with stable commodity basket -> Accelerated risk compression.

### Step 4: Commit & Deploy
```powershell
git -C "C:\Users\Reza Karim\Strategy" add cdx.html credit.html credit-page.js generate_credit_data.py credit_data.json ANALYSE_CREDIT.md site-nav.js
git -C "C:\Users\Reza Karim\Strategy" commit -m "Refresh CDX credit derivatives spreads and recommendations"
git -C "C:\Users\Reza Karim\Strategy" push origin main
```
Verify live deployment at `https://rkarim25.github.io/Strategy/cdx.html`.

### Step 5: Output Concise Executive Summary
Format the final response for Reza:
- Spread telemetry table with percentiles and SMAs.
- Transatlantic basis status.
- Derivative trade expressions (protection selling vs OTM swaptions).
- Quantitative triggers.\n