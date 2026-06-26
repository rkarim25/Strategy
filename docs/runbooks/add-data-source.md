# Runbook: add a data source (without duplicating downloads)

## STOP — check first
1. Open [`../../catalog/data.md`](../../catalog/data.md). Is your asset already there with enough history?
   - **YES** → STOP. Load the existing `<slug>_daily.csv`. Do **not** download.
   - **Partial** → you may extend it, but reuse the existing slug/file — don't create a parallel copy.
2. Read the "Known data notes" at the bottom of `data.md` (e.g. SPX 1950 history is fetched on demand, not cached).
3. Check [`../../catalog/sources.json`](../../catalog/sources.json) for the canonical slug + ticker.

## Add a genuinely new dataset
4. Add an entry to `catalog/sources.json`: `slug`, `name`, `ticker`, `source`, `file` (`<slug>_daily.csv`), `refresh`.
5. Download with the **existing** machinery — reuse `data_manager.py` / `yfinance`; obey
   [`../coding-standards.md`](../coding-standards.md). Write `<slug>_daily.csv` to the repo **root**
   (the website fetches data from root).
6. Clean it with `price_cleaning.py` (the shared round-trip spike filter — keep parity with the cron cleaner).
7. Regenerate the catalog: `python tools/build_catalog.py`.
8. If it should appear on the site, follow [`add-website-feature.md`](add-website-feature.md).
9. Commit **explicit** files (`catalog/*`, `<slug>_daily.csv`, any new/edited script). Deploy via [`../deploy.md`](../deploy.md).

## Don't
- Don't write a new download script if `data_manager.py` already covers the pattern — extend it.
- Don't store the same series under two slugs/files.
- Don't hand-edit a `*_daily.csv` the cron owns.
