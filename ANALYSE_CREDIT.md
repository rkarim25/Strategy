# Runbook: Autonomous Credit Analysis & Site Update ("analyse credit" / "analyse CDX")

Whenever Reza says **"analyse credit"**, **"update credit"**, **"analyse CDX"**, or **"credit spreads check"**, any AI agent must execute this standardized operational runbook to analyze global synthetic credit indices (CDX EM, iTraxx Xover, US HY CDX) and deploy the updated analysis to the live site.

---

## 1. System Architecture & File Map

| File | Path | Role |
| :--- | :--- | :--- |
| **Dashboard Page** | `cdx.html` | User-facing Credit Derivatives Desk with spread charts, percentile bars, triggers, and index deep dives. |
| **Client Engine** | `credit-page.js` | Interactive charting, Transatlantic basis toggle, and trigger card renderer. |
| **Data Pipeline** | `generate_credit_data.py` | Python pipeline generating spreads, SMAs (50d/200d), RSI14, percentiles, default rate outlooks, and trade expressions. |
| **Static Data Payload** | `credit_data.json` | The single source of truth consumed by `cdx.html` via GitHub Pages. |
| **Global Navigation** | `site-nav.js` | Shared sidebar navigation across all pages (`Rates, Credit & FX` group). |

---

## 2. Standardized Execution Protocol (5 Steps)

### Step 1: Corporate Credit & Spread Telemetry Search
Search for latest developments in:
1. **US High Yield CDX (`CDX.NA.HY`)**: Spread levels (current on-the-run series), ICE BofA US HY OAS, default rates, high-yield distress ratios, corporate refinancing wall.
2. **iTraxx Europe Crossover (`Xover`)**: Spread levels, ECB policy transmission, European sub-IG constituent credit metrics.
3. **CDX Emerging Markets (`CDX.EM`)**: Spread levels, sovereign default risk, IMF bilateral restructuring programs, foreign reserve coverage.

### Step 2: Ingest Fresh Data & Update `generate_credit_data.py`
Run or update `generate_credit_data.py`:
```bash
python generate_credit_data.py
```
Ensure each index structure contains:
- Current spread (bps), 1D change, 50d SMA, 200d SMA, 14d RSI.
- 1-year and 3-year percentile ranges.
- Default rate forecast and distress ratio.
- Quantitative/qualitative recommendation paragraph.
- Trade expressions: Index carry selling vs Tail hedge payer swaptions, Transatlantic basis trades (Xover vs US HY).
- Invalidation triggers: Risk-off spread blowout trigger (>360 bps on US HY) vs tight spread profit taking (<295 bps).

### Step 3: Verify Local Rendering
```bash
python -m http.server 8088
```
Open `http://localhost:8088/cdx.html` to confirm cards, triggers, and canvas charts.

### Step 4: Commit and Deploy to GitHub Pages
```bash
git add site-nav.js cdx.html credit-page.js generate_credit_data.py credit_data.json ANALYSE_CREDIT.md
git commit -m "Update Credit derivatives analysis, spreads, technical triggers, and trade expressions"
git push origin main
```
GitHub Actions will automatically deploy to `https://rkarim25.github.io/Strategy/cdx.html`.
