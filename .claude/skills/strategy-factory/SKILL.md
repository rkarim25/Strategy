---
name: strategy-factory
description: >-
  Fast path for the two core jobs in this Systematic Backtester repo — (1) running a
  backtest / sweep, and (2) adding or editing a website strategy page (HTML/JS) — and
  shipping the result safely. Use whenever the task is "run/extend a backtest", "regenerate
  site data", "edit/add a strategy page or guarded page", "build_* / sweep_*", or "deploy
  the site". Encodes the factory loop, the worktree deploy, and the known gotchas
  (silent build_ndx drift, hand-hydrated pages, NaN-breaks-JSON, OneDrive .git locks) so
  you don't rediscover them each session.
---

# Strategy Factory — backtest & website fast path

This repo is an **AI factory**: edited by fresh agent sessions, OneDrive-hosted, with a
concurrent agent + cron also pushing to `main`. The slow/dangerous part isn't the work —
it's *not duplicating it* and *shipping it without breaking production*. This skill is the
muscle memory for both. Detail lives in the runbooks; this is the index + the gotchas.

> Read order if unsure: `AGENTS.md` → `docs/runbooks/START-HERE.md` → the specific runbook.

## The loop (every session, both job types)
1. **Sync first:** `git fetch origin` (cron + the other agent push to `main`).
2. **Check before building (no duplication):**
   - backtest → `catalog/experiments.md`, `Results/strategy_results.xlsx`, `output/strategy_results/all_assets_combined.csv`
   - data → `catalog/data.md` (don't re-download)
3. **Do the work** (pick a path below), obeying `docs/coding-standards.md`.
4. **Register → commit → deploy → verify.**

---

## Path A — Run / extend a backtest
Runbook: `docs/runbooks/run-backtest.md`. Engine docs: `docs/backtesting.md`.

- **Reuse the engine — never re-implement it:** `from core import engine, strategies, metrics, etp_leverage`
  (`PortfolioEngine` is in `core.engine`). Add strategies by extending `core/strategies.py`.
- **Mandatory quant correctness** (`docs/coding-standards.md`): 1-day signal lag, ≥10 bps cost,
  VIX borrow, vectorized. Non-negotiable.
- **Outputs go to `output/<experiment-id>/`** — one dir per experiment so parallel agents never collide.
  Never dump at repo root or inside another experiment's dir.
- Exploratory `analyze_/sweep_/verify_` scripts live in `research/` (run from repo root). Only pipeline
  generators that write site data stay at root.
- **Extend the master grid:**
  ```bash
  python sweep_all_assets_strategies.py     # -> output/strategy_results/*.csv
  python build_strategy_results_excel.py    # -> Results/strategy_results.xlsx
  ```
- **Register:** `python tools/build_catalog.py` (adds your output dir to the catalog).
- Don't blindly re-run a page builder and commit it (see Path B drift warning).

## Path B — Add / edit a website strategy page
Runbook: `docs/runbooks/add-website-feature.md`. Page/data flow: `docs/website.md`.

- **Website files stay at repo root** — pages fetch `*_daily.csv` / `*_site_data.json` by relative path. Don't relocate.
- **Claim the file** in `.claims/` (one agent per page) — `docs/runbooks/coordination.md`.
- **Two kinds of page:**
  - **Generated per-asset guarded pages** → edit `guarded_asset_registry.py` then run `build_guarded_asset_pages.py`.
  - **Bespoke pages** (`index.html`, `summary.html`, gold) → edit directly.
- ⚠️ **Committed pages are hand-hydrated snapshots — re-running a builder can silently regress static
  Legacy/OOS tables. Always `git diff` builder output before committing.**
  `build_ndx_guarded_html.py` fails **silently** and is currently **drifted**; `build_gold_guarded_html.py` fails **loud**.
- ⚠️ **JSON must be valid:** `NaN`/`Inf` makes the browser's `JSON.parse` throw → blank page. Dump with
  `allow_nan=False` and sanitize `NaN`/`Inf` → `null`.
- The page's data must already exist at root — generate it via the right backtest/build script (Path A).
- **Verify locally before shipping:** open the file or use the `preview` tools (start a server, reload,
  snapshot, check console for errors) instead of eyeballing.

---

## Ship it — deploy & verify (shared tail, where things break)
Full procedure + gotchas: `docs/deploy.md`. **Read it before any push.**

OneDrive locks `.git`; a plain `git push` races the concurrent agent/cron. So: commit locally, then
deploy through a **throwaway detached worktree** built from fresh `origin/main`.

```bash
cd "C:/Users/Reza Karim/OneDrive/Systematic_Backstester"   # Git Bash

# 1) Stage ONLY intended files — NEVER `git add .` / -A
git add <explicit files>
git diff --cached --name-only      # confirm EXACTLY what ships
git commit -m "..."

# 2) Cherry-pick onto fresh origin/main in an isolated worktree (FRESH name each time)
MYSHA=$(git rev-parse HEAD)
git fetch origin -q
WT="C:/Users/Reza Karim/_dwtN"     # _dwt1, _dwt2, ... never reuse
git worktree add --detach "$WT" origin/main
git -C "$WT" cherry-pick "$MYSHA"
git -C "$WT" push origin HEAD:main

# 3) Trigger Pages build
gh workflow run deploy-pages.yml --ref main

# 4) Resync local, keeping uncommitted work
git reset --mixed origin/main
```

**Verify live (don't trust the push):** `curl` the deployed JSON/page and `gh run list --workflow deploy-pages.yml -L 1`.

### Non-negotiable gotchas
- **Never `git add .` / `-A`.** A `git checkout <ref> -- …` can leave files staged that a later commit sweeps in.
  Stage explicitly; check `git diff --cached`.
- **Don't bundle the cron churn:** `*_daily.csv`, `latest_*_signal.json`, `holdings_*.json`, `news_score.json`
  move constantly from the other agent/cron — keep them out of your commits.
- **`refresh_holdings_prices.py` is consumed cross-repo** by the holdings repo — don't delete/relocate it.
- Worktree "Permission denied" prune errors are harmless OneDrive locks; just use a fresh worktree name.

## Don't
- Don't rebuild the engine or re-implement `metrics` / `etp_leverage`.
- Don't blindly re-run + commit a page builder (regresses hand-hydrated tables).
- Don't relocate website/data files off root.
- Don't re-hunt Nasdaq-100 Water/Octane families — structurally none exist (16.5% CAGR needs 2x → breaches −45% DD gate).
