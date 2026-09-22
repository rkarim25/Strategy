---
name: process-notion-inbox
description: Autonomous Notion research inbox processing and website database dual-persistence workflow. Ingests raw analyst notes, broker decks, earnings dumps, and restructuring notes from Notion Inbox. Extracts structured issuer financials, debt structures, guidance, and news, writes database/issuers/<id>.json, appends credit_news.json, compiles SQLite credit_master.db and js/issuers_data.js, creates Notion research dossiers, appends processed receipts to the Notion receipt table, clears processed raw inbox blocks, and deploys live to GitHub Pages. Use when the user says "process notion inbox", "process inbox", "process my inbox", "inbox dump", or invokes /process-notion-inbox.
---

# Process Notion Inbox — Autonomous Credit Research Intake & Website Dual-Persistence Skill

This skill provides an autonomous execution protocol for reading raw research dumps, analyst notes, earnings reports, and credit catalysts from Reza's Notion Inbox (`3df1d0ad-68c6-813c-9f07-e7c847880346`), extracting structured corporate credit intelligence, persisting the data directly into the **CEMBI Credit website database** (`cembicredit`), compiling the SQLite master database and web bundles, creating permanent research dossiers in Notion, logging processed receipts, whisking away raw text blocks, and deploying live to GitHub Pages.

---

## 0. Non-Negotiables & Architectural Rules

1. **The Default Dual-Persistence Rule (Mandatory)**:
   - Any data, earnings numbers, notes, broker reports, or models posted on companies **must** be stored on the website (`cembicredit`) by default as an integral part of processing any Notion inbox dump or research intake.
   - **Processing a note into Notion alone without persisting to the website database is STRICTLY PROHIBITED.**
   - Every ingest must update:
     * `database/issuers/<issuer_id>.json`: Master document containing metadata, financials, capital structure, debt maturities, recovery analysis, broker models, and annotations.
     * `database/credit_news.json`: Live credit news intelligence feed.
     * Rebuild with `python scripts/build_database.py`: Compiles `database/credit_master.db` (SQLite), `database/annotations.json`, and `js/issuers_data.js`.
     * Git Commit & Push: Push immediately to `origin/main` so that updates appear live on `https://rkarim25.github.io/cembicredit/`.

2. **Reza's time is the scarce resource**:
   - Never make him read a long dump or status report.
   - Present about ten lines summarizing what was processed, the key credit takeaways, and live links, followed by the decision question.

3. **Multi-Source Data Integrity**:
   - Canonical historical financials (Revenue, Cash, Gross Debt) must never be silently overwritten or corrupted by conflicting broker estimates.
   - Model-derived or calculated metrics (Calculated EBITDA, FCF identity, broker consensus) must be tagged with explicit sources.

4. **Structured Guidance Extraction**:
   - Management targets (capex, leverage ceilings, volumes) must be extracted into `management_guidance_targets` and linked to forward financial forecasts.

5. **Whisk Away & Receipt Logging**:
   - Every processed dump must have an executive receipt logged into the Notion Processed Receipts Table (`3df1d0ad-68c6-81f5-89f7-e450bf669dcc`).
   - The to-do block in the inbox must be marked completed.
   - All processed raw dump blocks must be deleted from the Notion Inbox, leaving the inbox clean for the next dump.

---

## 1. Execution Protocol

### Step 1: Scan & Read Notion Inbox
Run the inbox inspection engine:
```powershell
python "C:\Users\Reza Karim\cembicredit\scripts\read_inbox.py"
```
Or query via Notion REST API:
- Endpoint: `https://api.notion.com/v1/blocks/3df1d0ad-68c6-813c-9f07-e7c847880346/children?page_size=100`
- Token: Environment variable `NOTION_TOKEN_WORK` or `NOTION_TOKEN`.
- Inspect blocks below the divider (`📝 Raw Data Dump`).

### Step 2: Extract & Structure Research Data
Classify the dump into:
1. **Issuer Identification**:
   - Existing issuer: Locate matching `database/issuers/<issuer_id>.json`.
   - New issuer: Generate standard metadata (`id`, `name`, `ticker`, `country`, `region`, `sector`, `rating`, `benchmark_bond`, `price`, `ytm`, `spread_bp`).
2. **Financials & Multi-Year P&L**:
   - Revenue, EBITDA (both Reported and Calculated Cash EBITDA).
   - Capex, Cash Interest, Working Capital changes, Taxes, and strict FCF bridge:
     `FCF = EBITDA - Capex - Cash Interest - ΔNWC - Tax`.
3. **Capital Structure & Debt Maturing Schedule**:
   - Tranche amounts, currency, coupon, maturity dates, seniority tier, and security pledges.
4. **Credit News / Catalyst Entry**:
   - Headline, summary, credit impact (`Positive`, `Neutral`, `Negative`, `Watch`), category, and clickable source URL.
5. **Restructuring & Valuation Mechanics (if distressed)**:
   - EV multiples, recovery waterfalls, and exchange terms.

### Step 3: Dual-Persistence — Website Database Update
Execute the database update and compiler:
1. Save or update `database/issuers/<issuer_id>.json`.
2. Append new event to `database/credit_news.json`.
3. Run compiler:
```powershell
python "C:\Users\Reza Karim\cembicredit\scripts\build_database.py"
```
This automatically updates:
- `database/credit_master.db` (SQLite tables: `issuers`, `financials_multi_year`, `debt_maturities`, `recovery_waterfalls`, `qualitative_annotations`, `credit_news`, `notes_search`).
- `database/annotations.json`.
- `js/issuers_data.js` (Web frontend bundle).

### Step 4: Notion Research Repository Sync
If the research constitutes a detailed issuer tear-sheet:
1. Create a structured research dossier in the Notion Research Database (`3df1d0ad-68c6-815e-b5c2-cffb3b540b1b`) using `scripts/notion_dossier_helper.py`.
2. Link the generated Notion page ID into the issuer's JSON metadata (`notion_id`).

### Step 5: Whisk Away & Clean Notion Inbox
1. Append an executive receipt row to the Notion Processed Receipts Table (`3df1d0ad-68c6-81f5-89f7-e450bf669dcc`):
   - Cell 1: Current Date (e.g. `22 Sep 2026`).
   - Cell 2: Company / Entity name & Ticker.
   - Cell 3: Executive bullet points summarizing key metrics, discrepancies resolved, and where the data was deployed.
2. Mark the to-do item in the inbox as checked (`[checked=True]`).
3. Delete all raw dump blocks from the Notion Inbox page (`DELETE https://api.notion.com/v1/blocks/<block_id>`).
4. Restore clean placeholder block: `— Drop your text, bullets, or broker notes right here —`.

### Step 6: Commit & Deploy Live to GitHub Pages
```powershell
cd "C:\Users\Reza Karim\cembicredit"
git add database/ js/issuers_data.js
git commit -m "Process Notion Inbox: update <company> database, compile SQLite master & sync web [Automated]"
git push origin main
```
If relevant models or calculators were modified, mirror to `C:\Users\Reza Karim\Strategy` and push both repos.

---

## 2. Interactive Output Format
Deliver a concise executive update (~10 lines):
1. **Inbox Dumps Ingested**: Companies / topics identified.
2. **Website Database Updated**: Confirmed update of `database/issuers/<id>.json`, `credit_master.db`, and `credit_news.json`.
3. **Key Credit Takeaways**: 2–3 highest impact data points (e.g., FCF conversion, leverage inflection, restructuring recovery).
4. **Notion Inbox Status**: Confirmed receipt logged in Processed Receipts table and raw dump blocks whisked away.
5. **Live Links**: Direct link to the company drawer on `https://rkarim25.github.io/cembicredit/` or Notion dossier.
