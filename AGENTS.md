# AGENTS.md — Systematic Backtester

> **Any AI/agent working on this repo: read this file first.** It is the durable map of
> the project. Deeper detail lives in [`docs/`](docs/) — open only the one doc you need so
> you don't burn context. This file + the right `docs/` page should make you productive in
> ~2 minutes without reading source.

---

## What this is

A personal, single-user **systematic leveraged backtesting + live-signal platform**. Two halves:

1. **Python engine** (runs locally) — historical simulations → risk/return metrics → JSON / CSV / Excel.
2. **Static website** (GitHub Pages) — live leverage signals, interactive charts, Monte Carlo, cross-asset comparison.

| | |
|---|---|
| **Live site** | https://rkarim25.github.io/Strategy/ |
| **GitHub repo** | `rkarim25/Strategy` (branch `main`, deployed via GitHub Pages) |
| **Local path** | `C:\Users\Reza Karim\OneDrive\Systematic_Backstester` |
| **Sub-site** | `holdings_web/` is a **git submodule** (`rkarim25/holdings`) — separate repo, separate concerns |

---

## ⛔ Golden rules (break these and you break production)

1. **The website is served from the repo ROOT.** `index.html`, `*_guarded.html` / `*_guarded.js`,
   `*_daily.csv`, `*_site_data.json`, `latest_*_signal.json`, `*_etp_returns.json` etc. **must stay at root** —
   the HTML fetches them by relative path. **Do not relocate website or data files.**
2. **Deploy only via the isolated git worktree — never a plain push.** OneDrive locks `.git` and open Excel.
   Full procedure in [`docs/deploy.md`](docs/deploy.md).
3. **Never `git add .` / `git add -A`.** Always stage an explicit file list and confirm
   `git diff --cached --name-only` before committing. Over-pushing 21 files has happened here.
4. **A second Cursor agent + cron jobs also push to this repo.** Expect `*_daily.csv`,
   `latest_*_signal.json`, `holdings_*.json`, `news_score.json` to change under you — that's the automated
   market-data refresh, **not your work**. Never bundle it into your commits; leave it alone.
5. **Committed website pages are hand-hydrated snapshots, not raw builder output.** Re-running a page
   builder can silently regress static Legacy/OOS tables. **Don't blindly commit builder output** — diff first.
6. **Quant correctness is mandatory** (enforced by `.cursorrules`): 1-day signal lag (no look-ahead),
   ≥10 bps cost per trade, VIX-linked borrow costs, vectorized Pandas/NumPy (never `.iterrows()`).
7. **Do not read `archive/roohistory.md`** (~18k lines) unless you genuinely need deep history — it's a token sink.

---

## 30-second architecture

```
Yahoo Finance ──> *_daily.csv ──> Python engine (engine.py + strategies.py)
                                      │
                  ┌───────────────────┼─────────────────────┐
                  ▼                    ▼                     ▼
          *_site_data.json     output/strategy_results/   Results/strategy_results.xlsx
          latest_*_signal.json   *.csv (sweep output)      (Water/Octane/Stillwater)
                  │
                  ▼
   Static HTML/JS pages (root)  ──GitHub Pages──>  https://rkarim25.github.io/Strategy/
                  ▲
                  └── live intraday prices via Cloudflare Worker proxy (gold page)
```

Two **separate** result pipelines exist — don't confuse them:
- **Excel pipeline** — full history, per-asset costs, Water/Octane/Stillwater classification.
- **Website summary pipeline** — shorter "real ETP" window, 3 cost levels, Balance-score view.

See [`docs/backtesting.md`](docs/backtesting.md) and [`docs/strategies.md`](docs/strategies.md).

---

## Assets & portfolio

Target five-sleeve allocation (Guarded A5/B25 + SMA20 lead guard): **S&P 500 40% (≤3x), Nasdaq 100 15% (≤3x),
FTSE 250 16% (1x), MSCI EM 14% (1x), Gold 15% (1x).** Full detail in [`PORTFOLIO.md`](PORTFOLIO.md).

| Asset | Page | Lev cap | Notes |
|-------|------|---------|-------|
| S&P 500 | `index.html` | up to 3x | History from 1950. Tabs: Guarded, Momentum, SPX 3x Levered, + Octane `SMA200 ±3% Band + RSI>20 Exit 2x` |
| Nasdaq 100 | `ndx_guarded.html` | up to 3x | From 1985 |
| Gold | `gold_guarded.html` | 1x | Uses the Cloudflare Worker for **live** intraday price |
| FTSE 250 | `ftse250_guarded.html` | 1x | `^FTMC` |
| DAX | `dax_guarded.html` | 1x | `^GDAXI` |
| MSCI EM | `msci_em_guarded.html` | 1x | `EEM` |
| MSCI World | `msci_world_guarded.html` | 1x | `SWDA.L`, history clamped to 2009-12-01 |
| LQQ3 (3x Nasdaq ETP) | `lqq3_guarded.html` | "1x" = cash vs full 3x ETP | `LQQ3.L` |
| 3-asset balanced | `3bal_guarded.html` | — | Blended sleeve |
| Cross-asset summary | `summary.html` | — | Overview table + per-asset drill-down |
| Instruments browser | `instruments.html` | — | ETF / Halal instrument reference |

The 5 template-driven guarded pages (ftse250, msci_em, dax, msci_world, lqq3) are generated from
`guarded_asset_registry.py` + `build_guarded_asset_pages.py`. SPX/NDX/Gold/3bal have bespoke pages.

---

## Repo map (top level)

**Root files** (cluttered by necessity — see categories, don't move the live ones):

| Group | Examples | Move OK? |
|-------|----------|----------|
| Website pages/JS | `*.html`, `site-nav.js`, `*_guarded.js`, `instruments-*.js`, `etp-leverage.js`, `favicon.svg` | ❌ served at root |
| Live data | `*_daily.csv`, `*_site_data.json`, `latest_*_signal.json`, `*_etp_returns.json`, `summary_excel.json` | ❌ fetched at root + cron-written |
| Core engine modules | `engine.py`, `strategies.py`, `metrics.py`, `indicators.py`, `data_manager.py`, `etp_leverage.py`, `guarded_asset_registry.py`, `price_cleaning.py`, `reporting.py` | ❌ imported widely |
| Strategy impl libs | `test_tiered_dd_recovery_guarded.py`, `test_guarded_balanced_candidate.py` (imported despite `test_` name) | ❌ imported widely |
| Research/build scripts | `analyze_*.py`, `backtest_*.py`, `sweep_*.py`, `build_*.py`, `verify_*`, `validate_*`, `merge_*` | ⚠️ tracked — coordinate |
| Cron entrypoints | `update_static_market_data.py`, `refresh_holdings_prices.py` (cross-repo) | ❌ referenced by workflow |
| Cloudflare worker | `cloudflare_spx_quote_worker.js`, `wrangler.toml` | — |

**Folders:**

| Folder | Purpose |
|--------|---------|
| [`docs/`](docs/) | **AI-facing project documentation (this set)** |
| `output/strategy_results/` | CSV outputs of the master sweep (feeds Excel + summary JSON) |
| `output/<analysis>/` | Per-analysis outputs (one subdir per `analyze_*` script) |
| `Results/` | Excel workbooks (`strategy_results.xlsx` is the main one); `Results/backups/` |
| `scratch/` | Experiments, one-off scripts, logs, WIP — **put throwaway work here, not root** |
| `scripts/` | Automation helpers (`run_backtests.py`, `collect_results.py`); mostly untracked temp |
| `archive/` | Old research, `roohistory.md`, legacy docs |
| `plans/` | Design / architecture plans |
| `workers/` | Cloudflare Worker subprojects (`spx-signal-alert`) |
| `holdings_web/` | **git submodule** (`rkarim25/holdings`) — separate site |
| `.github/workflows/` | `deploy-pages.yml`, `update-market-data.yml` |

---

## Docs index — open only what you need

| Doc | Read it when you're… |
|-----|----------------------|
| [`docs/architecture.md`](docs/architecture.md) | understanding the engine + data pipeline + module responsibilities |
| [`docs/website.md`](docs/website.md) | editing a page, adding an asset, or touching live data flow / the Cloudflare worker |
| [`docs/backtesting.md`](docs/backtesting.md) | changing strategies, running the sweep, regenerating the Excel, data sources/costs |
| [`docs/strategies.md`](docs/strategies.md) | working with Guarded A5/B25 or Water / Octane / Stillwater classification |
| [`docs/deploy.md`](docs/deploy.md) | committing or deploying anything to the live site (read this before you push) |
| [`docs/directory-map.md`](docs/directory-map.md) | answering "where is X?" — exhaustive file/folder index |
| [`docs/conventions.md`](docs/conventions.md) | adding new files and unsure where they go (keeps this repo from rotting) |
| [`docs/session-notes/`](docs/session-notes/) | wanting context on a specific past piece of work |

Other root docs: [`PORTFOLIO.md`](PORTFOLIO.md) (allocation), [`EMAIL_ALERTS.md`](EMAIL_ALERTS.md) (signal email alerts).

---

## Common tasks → start here

- **Change a strategy / re-run the sweep** → [`docs/backtesting.md`](docs/backtesting.md)
- **Edit a website page or add an asset** → [`docs/website.md`](docs/website.md)
- **Regenerate `strategy_results.xlsx`** → [`docs/backtesting.md`](docs/backtesting.md)
- **Deploy a change to the live site** → [`docs/deploy.md`](docs/deploy.md)
- **Understand Water/Octane/Stillwater** → [`docs/strategies.md`](docs/strategies.md)
- **"Where does this new file go?"** → [`docs/conventions.md`](docs/conventions.md)

---

## Current health / known drift (update as it changes)

- **`build_ndx` page builder fails *silently* on drift and is currently drifted**; `build_gold` fails *loud*.
  Treat per-asset page builders with suspicion — diff their output before committing (see [`docs/deploy.md`](docs/deploy.md)).
- **Summary classification counts:** S&P 500 has 11 Water + 11 Octane; **Nasdaq 100 structurally has no
  Water/Octane** (its 16.5% CAGR needs 2x, which breaches the −45% DD gate) — don't go re-hunting for them.
- Local `main` may trail `origin/main` by a few `Update static market data` commits (the concurrent
  agent/cron) — that's benign. Resync with `git reset --mixed origin/main` (keeps your uncommitted work).
