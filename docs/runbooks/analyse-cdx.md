# Runbook: CDX & Synthetic Credit Derivatives Analysis

Operational guide for refreshing the CDX & Credit Desk on [cdx.html](../../cdx.html).  
Invoked via: `/analyse-cdx` or `"analyse CDX"` / `"analyse credit"`. Skill: [`.agents/skills/analyse-cdx`](../../.agents/skills/analyse-cdx/SKILL.md).

---

## 1. File Architecture
- **Dashboard Page**: `cdx.html` (served at root; `credit.html` provides backwards-compatible redirect)
- **Client Engine**: `credit-page.js` (canvas spread comparison, Transatlantic basis, and trigger cards)
- **Data Pipeline**: `generate_credit_data.py` (spread history, SMAs, RSI14, percentiles, distress ratios)
- **Data Payload**: `credit_data.json` (consumed directly by `cdx.html`)

---

## 2. Refresh Protocol
1. **Run Engine**:
   ```bash
   python generate_credit_data.py
   ```
2. **Review Relative Value & Basis**:
   - Spreads: CDX.NA.HY (~322 bps, 28th %ile), iTraxx Xover (~296 bps, 21st %ile), CDX.EM (~174 bps, 22nd %ile).
   - Transatlantic Basis: CDX.NA.HY minus iTraxx Xover (+26.5 bps; fair value ~25 bps).
   - Distress Ratios & 12M Default Forecasts.
3. **Evaluate Quantitative Triggers**:
   - *Risk-Off Widener*: US HY > 360 bps & Xover > 340 bps -> Shift to Long Protection.
   - *Transatlantic Divergence*: US HY - Xover basis > 50 bps -> Long Xover / Short US HY spread compression.
   - *EM Compression Breakout*: CDX.EM < 160 bps -> Accelerated EM risk compression.
4. **Deploy**:
   ```bash
   git add cdx.html credit.html credit-page.js generate_credit_data.py credit_data.json site-nav.js docs/runbooks/analyse-cdx.md
   git commit -m "Refresh CDX credit derivatives spreads and triggers"
   git push origin main
   ```
