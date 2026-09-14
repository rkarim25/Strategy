# Runbook: Autonomous GBI-EM Analysis & Site Update ("analyse GBI EM")

Whenever Reza says **"analyse GBI EM"**, **"update GBI EM"**, **"run GBI-EM analysis"**, or **"EM local debt check"**, any AI agent must execute this standardized 5-step operational runbook to refresh the macroeconomic fundamentals, evaluate technical indicators, update country recommendations, and deploy the updated analysis to the live site.

---

## 1. System Architecture & File Map

| File | Path | Role |
| :--- | :--- | :--- |
| **Dashboard Page** | `gbi_em.html` | User-facing GBI-EM strategy desk with regional filters, real yield chart, country cards, and hedging instructions. |
| **Client Engine** | `gbi-em-page.js` | Interactive charting, regional filtering, and country card renderer. |
| **Data Pipeline** | `generate_gbi_em_data.py` | Python pipeline aggregating yields, inflation, real rates, FX carry, technical indicators, and supporting paragraphs. |
| **Static Data Payload** | `gbi_em_data.json` | The single source of truth consumed by `gbi_em.html` via GitHub Pages. |
| **Global Navigation** | `site-nav.js` | Shared sidebar navigation across all pages (`Rates, Credit & FX` group). |

---

## 2. Standardized Execution Protocol (5 Steps)

### Step 1: Emerging Market Macroeconomic & FX Telemetry
Perform targeted web searches for recent developments across the 8 core GBI-EM countries:
1. **Brazil**: Copom Selic decisions, IPCA inflation releases, Ministry of Finance fiscal target debates.
2. **Mexico**: Banxico rate cut pace, judicial reform headlines, US election / USMCA tariff rhetoric, USD/MXN volatility.
3. **South Africa**: Government of National Unity (GNU) policy progress, Eskom loadshedding metrics, SARB inflation targeting.
4. **Indonesia**: Bank Indonesia policy rates, domestic CPI inflation, incoming administration fiscal appointments.
5. **Poland**: NBP policy guidance, energy price cap removal impact, EU Recovery Fund (KPO) disbursements.
6. **India**: J.P. Morgan GBI-EM index inclusion inflows ($2B/mo), RBI FX reserve management, CPI inflation.
7. **Colombia**: BanRep rate trajectory, CARF fiscal rule committee reports, oil/fiscal deficit headwinds.
8. **Turkey**: TCMB rate decisions, disinflation progress from 50% toward 38%, FX reserve reconstitution.

### Step 2: Ingest Fresh Data & Update `generate_gbi_em_data.py`
Run or update `generate_gbi_em_data.py`:
```bash
python generate_gbi_em_data.py
```
Ensure each country object contains:
- **Rates metrics**: Policy Rate, 10Y/5Y/2Y sovereign yields, Headline CPI, 10Y Real Yield, and Ex-ante real rate.
- **FX metrics**: Spot exchange rate, 3M implied carry (annualized), 50d/200d SMAs, 14d RSI, and REER valuation.
- **Explicit Curve Point**: e.g. *5-Year Belly (Jan 2029)*, *10-Year Duration*, or *1M-3M Front-End*.
- **Explicit Instrument**: e.g. `NTN-F Jan 2029`, `M-Bono Nov 2034`, `SAGB R2035`, `SUN FR0100`, `IGB 7.18% 2033`.
- **Unhedged vs FX-Hedged Directive**: Explicitly dictate whether to run the trade unhedged (collect full nominal carry) or FX-hedged (insulate the real rate against currency drawdown).
- **Sideways Rule**: If a market lacks a directional edge, explicitly label it: `Neutral / Sideways Range (No compelling edge; clip carry only or stand aside)`.

### Step 3: Evaluate Country Decision Matrix
- **Overweight Criteria**:
  - High ex-ante real yield (>4.5%) with a credible central bank disinflation path (e.g. Brazil, South Africa).
  - Structural capital inflow anchor with low FX volatility (e.g. India GBI-EM inclusion).
- **Neutral / Sideways Range Criteria**:
  - High nominal yield offset by institutional/political or tariff headline volatility (e.g. Mexico, Colombia).
  - *Action*: Suggest FX-hedged expression or curve flatteners; avoid unhedged directional beta.
- **Underweight Criteria**:
  - Slim real yield (<2.0%) despite high nominal rates (e.g. Poland local bonds).
  - Deeply inverted curves with unanchored multi-year inflation (e.g. Turkey long-end duration).

### Step 4: Verify Local Rendering
```bash
python -m http.server 8088
```
Open `http://localhost:8088/gbi_em.html` to confirm cards, regional filters, and the Real Yield ranking bar chart.

### Step 5: Commit and Deploy to GitHub Pages
```bash
git add site-nav.js gbi_em.html gbi-em-page.js generate_gbi_em_data.py gbi_em_data.json ANALYSE_GBI_EM.md
git commit -m "Update GBI-EM local sovereign debt & FX analysis, trade expressions, and catalysts"
git push origin main
```
GitHub Actions will automatically deploy to `https://rkarim25.github.io/Strategy/gbi_em.html`.
