# Runbook: US Treasury Curve & Macro Regime Analysis

Operational guide for refreshing the US Treasury yield curve model on [ust.html](../../ust.html).  
Invoked via: `/analyse-ust` or `"analyse UST"`. Skill: [`.agents/skills/analyse-ust`](../../.agents/skills/analyse-ust/SKILL.md).

---

## 1. File Architecture
- **Dashboard Page**: `ust.html` (served at root, includes `site-nav.js` and `ust-page.js`)
- **Client Engine**: `ust-page.js` (canvas curve visualizer, DV01 calculator, scenario simulator)
- **Data Pipeline**: `generate_ust_data.py` (pulls `2YY=F`, `^FVX`, `^TNX`, `^TYX`, computes spreads & SMAs)
- **Data Payload**: `ust_curve_data.json` and `ust_daily.csv` (consumed directly by `ust.html`)

---

## 2. Refresh Protocol
1. **Run Engine**:
   ```bash
   python generate_ust_data.py
   ```
2. **Review Macro Telemetry**:
   - Inflation (CPI YoY, Core PCE YoY) & Labor (Unemployment rate, Non-Farm Payrolls).
   - Deficit & Treasury auction supply ($2T annual coupon issuance, term premium).
3. **Check Invalidation Triggers**:
   - *Bull Flattening (Pivot to Long Duration)*: 10Y < 4.70% & 2s10s < +25 bps & Unemployment > 4.6%.
   - *Accelerated Steepener (Bond Vigilantes)*: 10Y > 5.05% & 30Y > 5.40%.
   - *Bear Flattener (Ultra-Short Cash)*: 2Y > 4.85% & CPI > 3.7%.
4. **Deploy**:
   ```bash
   git add ust.html ust-page.js generate_ust_data.py ust_curve_data.json ust_daily.csv site-nav.js docs/runbooks/analyse-ust.md
   git commit -m "Refresh UST curve analysis and macro regime"
   git push origin main
   ```
