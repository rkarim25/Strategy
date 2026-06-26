# AGENTS.md — Systematic Backtester (AI factory hub)

> **Every AI/agent: read this first, then [`docs/runbooks/START-HERE.md`](docs/runbooks/START-HERE.md).**
> This repo is edited **entirely by AIs in fresh, separate sessions**. Treat it like a factory: check what
> already exists before you build, don't duplicate, don't clash with other agents, leave it clean.
> The human only reads **results + the website** — everything underneath is ours to run.

## ⚡ The loop (every session)
1. **Sync** — `git fetch origin` (the cron and other agents push to `main`).
2. **Check before building (no duplication):** [`catalog/data.md`](catalog/data.md) before downloading data ·
   [`catalog/experiments.md`](catalog/experiments.md) before running a backtest.
3. **Do the work** via the matching runbook in [`docs/runbooks/`](docs/runbooks/), obeying
   [`docs/coding-standards.md`](docs/coding-standards.md).
4. **Register → commit → deploy → verify** — `python tools/build_catalog.py`, commit *explicit* files,
   deploy via [`docs/deploy.md`](docs/deploy.md), `curl` the live site.

Full checklist: [`docs/runbooks/START-HERE.md`](docs/runbooks/START-HERE.md).

## What this is
A personal **systematic leveraged backtesting + live-signal platform**. Two halves:
1. **Python engine** (local) — historical simulations → metrics → JSON/CSV/Excel.
2. **Static website** (GitHub Pages) — live leverage signals, charts, Monte Carlo, cross-asset comparison.

| | |
|---|---|
| **Live site** | https://rkarim25.github.io/Strategy/ |
| **GitHub repo** | `rkarim25/Strategy` (branch `main`, GitHub Pages) |
| **Local path** | `C:\Users\Reza Karim\OneDrive\Systematic_Backstester` |
| **Sub-site** | `holdings_web/` is a **git submodule** (`rkarim25/holdings`) — separate repo |

## ⛔ Golden rules (break these and you break production)
1. **The website is served from the repo ROOT.** `index.html`, `*_guarded.html/js`, `*_daily.csv`,
   `*_site_data.json`, `latest_*_signal.json`, `*_etp_returns.json` **must stay at root** — the HTML fetches
   them by relative path. Don't relocate website or data files.
2. **No duplication.** Check [`catalog/data.md`](catalog/data.md) before downloading and
   [`catalog/experiments.md`](catalog/experiments.md) before backtesting. Reuse the engine
   (`from core import engine, metrics, etp_leverage`) — never re-implement it.
3. **No clashing.** Sync first; respect ownership zones; claim shared work. See
   [`docs/runbooks/coordination.md`](docs/runbooks/coordination.md).
4. **Deploy via the isolated worktree, never a plain push** (OneDrive locks `.git`). See [`docs/deploy.md`](docs/deploy.md).
5. **Never `git add .` / `-A`.** Stage explicit files; check `git diff --cached --name-only`.
6. **The cron + other agents also push** (`*_daily.csv`, `latest_*_signal.json`, `holdings_*.json` churn) —
   never bundle that into your commits; leave it alone.
7. **Committed website pages are hand-hydrated snapshots** — re-running a builder can silently regress static
   tables. Diff before committing.
8. **Quant correctness is mandatory** — [`docs/coding-standards.md`](docs/coding-standards.md) (1-day signal
   lag, ≥10 bps cost, VIX borrow, vectorized).
9. **Don't read `archive/roohistory.md`** (~18k lines) unless you truly need deep history.

## 30-second architecture
```
Yahoo Finance ──> *_daily.csv ──> Python engine (core/engine.py + core/strategies.py)
                                      │
                  ┌───────────────────┼─────────────────────┐
                  ▼                    ▼                     ▼
          *_site_data.json     output/strategy_results/   Results/strategy_results.xlsx
          latest_*_signal.json   *.csv (sweep output)      (Water/Octane/Stillwater)
                  │
                  ▼
   Static HTML/JS (root)  ──GitHub Pages──> rkarim25.github.io/Strategy/  (+ Cloudflare Worker for live gold price)
```
Two **separate** result pipelines: the **Excel** (full history, per-asset costs, classification) and the
**website summary** (shorter real-ETP window, Balance score). Don't conflate them — see [`docs/backtesting.md`](docs/backtesting.md).

## Assets & portfolio
Target sleeves (Guarded A5/B25 + SMA20 guard): **S&P 500 40% (≤3x), Nasdaq 100 15% (≤3x), FTSE 250 16% (1x),
MSCI EM 14% (1x), Gold 15% (1x).** Full table + sources: [`catalog/data.md`](catalog/data.md). Allocation: [`PORTFOLIO.md`](PORTFOLIO.md).

12 datasets (spx, ndx, gold, ftse250, dax, msci_em, msci_world, lqq3, 3bal, rut, spxew, tlt). Pages:
`index.html` (S&P, ≤3x), `ndx_guarded.html` (≤3x), `gold_guarded.html` (1x, live price), the 5 template
pages (ftse250/dax/msci_em/msci_world/lqq3), `3bal_guarded.html`, `summary.html`, `instruments.html`.

## Repo map
| Path | What | Move OK? |
|------|------|----------|
| `index.html`, `*_guarded.html/js`, `site-nav.js`, `instruments-*.js`, `etp-leverage.js`, `favicon.svg` | website (served at root) | ❌ |
| `*_daily.csv`, `*_site_data.json`, `latest_*_signal.json`, `*_etp_returns.json`, `summary_excel.json` | live data (root + cron-written) | ❌ |
| `core/` package — `engine.py`, `strategies.py`, `metrics.py`, `indicators.py`, `data_manager.py`, `etp_leverage.py`, `price_cleaning.py`, `guarded_asset_registry.py`, `reporting.py`, `data_three_asset.py` (import via `from core import …`) | core engine (imported widely) | ❌ |
| `test_tiered_dd_recovery_guarded.py`, `test_guarded_balanced_candidate.py` | strategy libs (imported despite `test_` name) | ❌ |
| root: `build_*.py`, master sweeps, site-data `backtest_*` · `research/`: exploratory `analyze_/sweep_/verify_` | build pipeline vs exploration | ⚠️ coordinate |
| `update_static_market_data.py`, `refresh_holdings_prices.py` | cron entrypoints (`refresh_holdings_prices` is cross-repo) | ❌ |
| **`catalog/`** | **data + experiment registries (anti-duplication) — generated by `tools/build_catalog.py`** | |
| **`tools/`** | factory tooling (`build_catalog.py`) | |
| **`docs/`** | references + **`docs/runbooks/`** (idiot-proof how-tos) | |
| `output/strategy_results/` · `output/<analysis>/` | sweep CSVs · per-experiment outputs | 📦 |
| `research/` · `Results/` (+ `backups/`) · `scratch/` · `scripts/` · `archive/` · `plans/` · `workers/` | exploratory scripts · Excel · experiments · automation · old · plans · CF workers | |
| `holdings_web/` | **git submodule** (`rkarim25/holdings`) | submodule |
| `.github/workflows/` | `deploy-pages.yml`, `update-market-data.yml` | |

## The factory floor — catalogs, runbooks, coordination
- **[`catalog/`](catalog/)** — `data.md`/`data.json` (every dataset + source + coverage),
  `experiments.md`/`experiments.json` (every backtest output dir), `sources.json` (curated sources).
  **Generated** by `python tools/build_catalog.py` — re-run it after adding data or experiments.
- **[`docs/runbooks/`](docs/runbooks/)** — `START-HERE.md`, `add-data-source.md`, `run-backtest.md`,
  `add-website-feature.md`, `coordination.md`. Numbered, copy-paste, weak-model-safe.
- **Coordination** — ownership zones + claims in [`docs/runbooks/coordination.md`](docs/runbooks/coordination.md).

## Docs index — open only what you need
| Doc | When |
|-----|------|
| [`docs/runbooks/START-HERE.md`](docs/runbooks/START-HERE.md) | **start of every session** |
| [`catalog/data.md`](catalog/data.md) · [`catalog/experiments.md`](catalog/experiments.md) | before downloading / backtesting |
| [`docs/architecture.md`](docs/architecture.md) | engine + pipeline + module roles |
| [`docs/website.md`](docs/website.md) | editing a page / live data flow |
| [`docs/backtesting.md`](docs/backtesting.md) | engine params, costs, regeneration |
| [`docs/strategies.md`](docs/strategies.md) | Guarded A5/B25, Water/Octane/Stillwater |
| [`docs/coding-standards.md`](docs/coding-standards.md) | the mandatory quant rules |
| [`docs/deploy.md`](docs/deploy.md) | before any commit/push |
| [`docs/directory-map.md`](docs/directory-map.md) · [`docs/conventions.md`](docs/conventions.md) | "where is X?" / "where does new X go?" |
| [`docs/session-notes/`](docs/session-notes/) | context on a past piece of work |

## Current health / known drift (keep this updated)
- **`build_ndx` page builder fails *silently* on drift and is currently drifted**; `build_gold` fails *loud*.
  Diff builder output before committing.
- **Classification counts:** S&P 500 = 11 Water + 11 Octane; **Nasdaq 100 structurally has none** (16.5% CAGR
  needs 2x → breaches the −45% DD gate) — don't re-hunt.
- **Data note:** `spx_daily.csv`/`ndx_daily.csv` cache only ~30y (1996+); full 1950 SPX history is fetched on
  demand by `backtest_spx_distance_scale.py` (not cached). See [`catalog/data.md`](catalog/data.md).
- Local `main` may trail `origin/main` by a few `Update static market data` commits (cron) — benign; resync with
  `git reset --mixed origin/main`.
