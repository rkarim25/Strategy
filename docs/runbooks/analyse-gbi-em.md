# Runbook: GBI-EM Local Sovereign Debt & FX Analysis

Operational guide for refreshing the Local EM Strategy Desk on [local_em.html](../../local_em.html).  
Invoked via: `/analyse-gbi-em` or `"analyse Local EM"` / `"analyse GBI EM"`. Skill: [`.agents/skills/analyse-gbi-em`](../../.agents/skills/analyse-gbi-em/SKILL.md).

---

## 1. File Architecture
- **Dashboard Page**: `local_em.html` (served at root; `gbi_em.html` provides backwards-compatible redirect)
- **Client Engine**: `gbi-em-page.js` (real yield ranking canvas, regional filters, country cards)
- **Data Pipeline**: `generate_gbi_em_data.py` (aggregates 8 benchmark countries, inflation, real yields, FX technicals)
- **Data Payload**: `gbi_em_data.json` (consumed directly by `local_em.html`)

---

## 2. Refresh Protocol
1. **Run Engine**:
   ```bash
   python generate_gbi_em_data.py
   ```
2. **Review Real Yield Rankings & Directives (8 Countries)**:
   - Brazil: Real yield +8.10%, Long NTN-F 2029 (5Y belly), Unhedged BRL carry.
   - South Africa: Real yield +6.25%, Long SAGB R2035 (10Y), FX-Hedged ZAR.
   - Indonesia: Real yield +4.70%, Long SUN FR0100 (10Y), Unhedged IDR carry.
   - India: Real yield +3.44%, Long IGB 2033 (10Y), FX-Hedged INR.
   - Mexico: Real yield +3.67%, **Sideways Range (8.40%–8.90%)**, FX-Hedged MXN.
   - Colombia: Real yield +3.80%, **Sideways Range (10.40%–10.90%)**, FX-Hedged COP.
   - Poland: Real yield +1.05%, Underweight / Pay 5Y PLN IRS, FX-Hedged.
   - Turkey: Real yield -23.57% spot, Buy 3M–6M T-Bills only, Unhedged TRY carry.
3. **Upcoming Catalysts & Currency Stops**:
   - Central bank rate decisions (Copom, Banxico, SARB, BI, RBI, NBP, BanRep, TCMB).
   - Invalidation stops: USDBRL > 5.70, USDMXN > 20.20, USDZAR > 18.60.
4. **Deploy**:
   ```bash
   git add local_em.html gbi_em.html gbi-em-page.js generate_gbi_em_data.py gbi_em_data.json site-nav.js docs/runbooks/analyse-gbi-em.md
   git commit -m "Refresh GBI-EM local sovereign debt and FX recommendations"
   git push origin main
   ```
