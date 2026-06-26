# Runbook: add / change a website feature (without breaking the live site)

**The human reads the website — do not break it.** It is served from the repo **root** by GitHub Pages.

## Rules
1. **Website files stay at root** — HTML fetches `*_daily.csv` / `*_site_data.json` by relative path.
2. **Claim the file(s)** in `.claims/` (one agent per page at a time) — see [`coordination.md`](coordination.md).
3. **Per-asset guarded pages are generated:** edit `guarded_asset_registry.py` + run
   `build_guarded_asset_pages.py`. `index.html` / `summary.html` / gold are **bespoke** — edit directly.
4. **Committed pages are hand-hydrated snapshots** — re-running a builder can regress static Legacy/OOS tables.
   **Diff before committing.** (`build_ndx` fails silently and is drifted; `build_gold` fails loud.)
5. **Data the page reads must exist at root** (`*_site_data.json`, etc.) — generate it via the right
   backtest/build script ([`run-backtest.md`](run-backtest.md)).
6. **JSON must be valid** — `NaN`/`Inf` makes the browser's `JSON.parse` throw → blank page. Dump with
   `allow_nan=False` and sanitize `NaN`/`Inf` → `null`.

## Steps
7. Make the change (registry + builder, or edit the bespoke page).
8. Verify locally if you can (open the file / a local server).
9. Commit **explicit** files (never `git add .`).
10. Deploy via [`../deploy.md`](../deploy.md) (worktree procedure).
11. `curl` the live URL (or hard-refresh, Ctrl+Shift+R) to confirm it renders.
12. Delete your claim file.

## Scaling up (many future features)
Keep new shared JS in its own file and include it; reuse `site-nav.js` for the menu and the existing CSS shell.
Add new pages with a clear `{slug}_*.html` name and register data in `catalog/` so other agents find it.
