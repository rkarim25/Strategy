# Website

The static site at https://rkarim25.github.io/Strategy/ is served **from the repo root** by GitHub Pages.
Pages, scripts, and the data files they fetch all live at root and reference each other by **relative path** —
this is why none of them can be moved (see the golden rules in [`AGENTS.md`](../AGENTS.md)).

## Pages (`*.html`, root)

| File | Shows |
|------|-------|
| `index.html` | S&P 500. Tabs: Guarded, Momentum, SPX 3x Levered, plus the Octane `SMA200 ±3% Band + RSI>20 Exit 2x` |
| `ndx_guarded.html` | Nasdaq 100 Guarded (≤3x) |
| `gold_guarded.html` | Gold Guarded (1x) — the one page that pulls **live** intraday price via the Cloudflare Worker |
| `ftse250_guarded.html`, `dax_guarded.html`, `msci_em_guarded.html`, `msci_world_guarded.html`, `lqq3_guarded.html` | Template-driven guarded pages (1x) |
| `3bal_guarded.html` | 3-asset balanced sleeve |
| `summary.html` | Cross-asset overview table + per-asset Water/Octane drill-down (reads `summary_excel.json`) |
| `instruments.html` | ETF / Halal instrument browser |
| `live_guarded_sma20_leverage.html` | Standalone live SMA20 leverage view |

## Scripts (`*.js`, root)

| File | Role |
|------|------|
| `site-nav.js` | Shared left sidebar nav, hash-based routing (edit this to change the menu) |
| `site-scroll-init.js` | Scroll/section init shared across pages |
| `{slug}_guarded.js` | Per-asset client-side re-implementation of the Guarded signal (live leverage rec) |
| `etp-leverage.js` | Browser ETP-leverage helpers for charts |
| `all-instruments-data.js`, `instruments-data.js`, `instruments-page.js`, `halal-comparison-data.js` | Data + rendering for `instruments.html` |
| `cloudflare_spx_quote_worker.js` | **Not part of Pages** — source of the deployed Cloudflare Worker CORS proxy (config in `wrangler.toml`) |

## Data files the site fetches (root — do not move)

- `{slug}_daily.csv` — historical daily prices (also rewritten by the cron refresh).
- `{slug}_guarded_site_data.json` — pre-computed backtest metrics + equity curve for charts.
- `latest_{slug}_signal.json` — current signal metadata.
- `{slug}_etp_returns.json` — ETP daily return series for browser-side backtests.
- `spx_distance_scale_site_data.json`, `spx_3x_levered_site_data.json` (+ their `*_etp_returns.json`) — S&P tabs.
- `summary_excel.json` — feeds `summary.html`.
- `output/strategy_results/all_assets_combined.csv` — also fetched by the site (note the `output/` path is live).

## Live data flow

1. `cloudflare_spx_quote_worker.js` (deployed at Cloudflare Workers) proxies Yahoo Finance for CORS.
2. `?mode=daily&symbol=…` → 30y CSV of daily closes; `?mode=quote&symbol=…` → latest intraday price.
3. **Only `gold_guarded.js` uses the Worker live**; other assets use static CSV + manual price override.
4. Auto-refresh every 30 min during UK LSE hours (Mon–Fri 08:00–16:30 London).
5. The signal is computed **client-side**: SMA20, drawdown from peak, recovery tier, leverage recommendation —
   this mirrors the Python Guarded logic (see [`strategies.md`](strategies.md)).

## Adding / editing a guarded asset page

The 5 template-driven pages (ftse250, msci_em, dax, msci_world, lqq3) come from:
`guarded_asset_registry.py` (metadata) + `build_guarded_asset_pages.py` (generator, gold template).
SPX / NDX / Gold / 3bal are **bespoke** pages, hand-maintained.

## ⚠️ Gotchas

- **Committed pages are hand-hydrated snapshots, not pure builder output.** Re-running a page builder can
  regress static Legacy/OOS tables. **Diff before committing.**
- **`build_ndx` fails *silently* on drift and is currently drifted**; `build_gold` fails *loud*. Don't assume
  a clean re-run.
- **Invalid JSON kills the page silently:** if a builder writes `NaN`/`Inf` into a `*.json`, the browser's
  `JSON.parse` throws and `staticSiteData` becomes `null` (page shows stale/blank). Sanitize `NaN`/`Inf` → `null`
  and dump with `allow_nan=False`.
- After deploying, the nav label / JSON may need a hard refresh (Ctrl+Shift+R) past the browser cache.
