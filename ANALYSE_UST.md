# Runbook: Autonomous UST Analysis & Site Update ("analyse UST")

Whenever Reza says **"analyse UST"**, **"update UST"**, **"run UST analysis"**, or **"UST curve check"**, any AI agent must execute this standardized 5-step operational runbook to analyze the US Treasury yield curve, evaluate macro and technical triggers, and deploy the updated analysis to the live site.

---

## 1. System Architecture & File Map

| File | Path | Role |
| :--- | :--- | :--- |
| **Dashboard Page** | `ust.html` | User-facing dashboard with executive recommendation, technical triggers, canvas yield curve visualizer, historical series, and scenario simulator. |
| **Client Engine** | `ust-page.js` | Interactive charting, trigger status badges, DV01-neutral steepener calculator, and scenario returns engine. |
| **Data Pipeline** | `generate_ust_data.py` | Python pipeline fetching Yahoo Finance par yields (`2YY=F`, `^FVX`, `^TNX`, `^TYX`), computing spreads, SMAs (50d/200d), RSI(14), and outputting JSON/CSV. |
| **Static Data Payload** | `ust_curve_data.json` | The single source of truth consumed by `ust.html` via GitHub Pages. |
| **Historical CSV** | `ust_daily.csv` | Daily historical time series of yields and spreads. |
| **Global Navigation** | `site-nav.js` | Shared sidebar navigation across all pages (`Rates & Yields` group). |

---

## 2. Standardized Execution Protocol (5 Steps)

### Step 1: Live Macro Headline Intelligence Search
Search the web for current data releases and bond market headlines:
1. **Inflation**: Headline CPI YoY, Core PCE YoY (Fed 2.0% target).
2. **Growth & Labor**: Real GDP growth (annualized pace), Non-Farm Payrolls, Unemployment rate.
3. **Monetary Policy**: Federal Reserve FOMC rate decision, dot plot, terminal rate expectation.
4. **Fiscal & Sovereign Supply**: Treasury auction demand (tails/bid-to-cover), annual budget deficit (~$2T), national debt milestones, 10-year term premium.

### Step 2: Ingest Fresh Market Yields & Compute Technical Indicators
Run the automated pipeline:
```bash
python generate_ust_data.py
```
This fetches:
- **2Y Note (`2YY=F`)**: Policy expectation & near-term liquidity anchor.
- **5Y Note (`^FVX`)**: The curve's belly; cyclical growth & r* bellwether.
- **10Y Note (`^TNX`)**: Global risk-free benchmark & borrowing cost anchor.
- **30Y Bond (`^TYX`)**: Long-term term premium & sovereign debt supply barometer.
- **Key Spreads**: 2s10s, 5s30s, 2s30s, 10s30s.
- **Technical Indicators**: 50d SMA, 200d SMA, and 14d RSI for both 10Y yield and 2s10s spread.

### Step 3: Evaluate Regime Decision Matrix & Invalidation Triggers

#### A. The 4-Regime Classification:
- **Bull Steepening**: Growth shock / Fed emergency rate cuts. Winners: **2Y & 5Y** (front end collapses; 2s10s steepeners win).
- **Bull Flattening**: Late-cycle peak to disinflation. Winners: **10Y & 30Y** (long duration captures maximum price upside as inflation expectations vanish).
- **Bear Flattening**: Hawkish Fed tightening / inflation shock. Winners: **Cash / Ultra-Short T-Bills / 2Y Defensive**. (Underweight all duration).
- **Bear Steepening (Current Regime)**: Reflation / Fiscal dominance / $2T deficit supply shock. Winners: **5Y Belly & 2Y Carry; 2s10s Steepener**. (Avoid 30Y duration).

#### B. The 3 Technical Invalidation Triggers:
1. **Pivot to Long Duration (Bull Flattening)**:
   - *Condition*: 10Y Yield breaks below **4.70%** (50d/200d SMA support) AND 2s10s breaks below **+25 bps** AND Unemployment rises above **4.6%**.
   - *Action*: Close steepeners. Immediately upgrade **10Y and 30Y to Overweight**.
2. **Accelerated Steepener (Bond Vigilante Breakout)**:
   - *Condition*: 10Y Yield closes above **5.05%** resistance ceiling with 30Y > **5.40%**.
   - *Action*: Add to 2s10s/2s30s steepeners. Short 30Y duration.
3. **Bear Flattener / Flight to Ultra-Short Cash**:
   - *Condition*: 2Y Yield breaks above **4.85%** (Fed hike repricing) AND Core CPI > **3.7%**.
   - *Action*: Shift sleeve 100% to T-Bills / cash.

#### C. Synthesize Executive Paragraph:
Formulate a concise 3-4 sentence institutional paragraph answering:
- What is the active recommendation on curve points?
- What is the recommended steepener/flattener trade?
- What specific technical or fundamental trigger would cause a pivot?

Update `executive_paragraph`, `technicals`, and `indicators` in `generate_ust_data.py`, then re-run `python generate_ust_data.py`.

### Step 4: Verify Local Rendering
Verify that `ust.html` loads cleanly, the yield curve canvas renders, the technical trigger metrics update, and no console errors occur:
```bash
python -m http.server 8088
```
Open `http://localhost:8088/ust.html` to confirm cards, indicators, and charts.

### Step 5: Commit and Deploy to GitHub Pages
```bash
git add site-nav.js ust.html ust-page.js generate_ust_data.py ust_curve_data.json ust_daily.csv ANALYSE_UST.md
git commit -m "Update UST yield curve analysis, technical triggers, and macro assessment"
git push origin main
```
GitHub Actions workflow `.github/workflows/deploy-pages.yml` will automatically build and publish to `https://rkarim25.github.io/Strategy/ust.html` within 45 seconds.

---

## 3. Quick Reference Metric Benchmarks

- **10-Year Duration / DV01**: ~8.2 years / $82.0 per $100,000 notional.
- **2-Year Duration / DV01**: ~1.9 years / $19.2 per $100,000 notional.
- **DV01 Hedge Ratio (2Y vs 10Y)**: $82.0 / $19.2 = **~4.27x** (Long $4.27M 2Y vs Short $1.00M 10Y for duration-neutral steepener).
- **Price Return Approximation**: $\Delta P \approx -D_{\text{mod}} \times \Delta y + \frac{1}{2} C \times (\Delta y)^2$.
