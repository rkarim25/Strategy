# Website

The static site at https://rkarim25.github.io/Strategy/ is served **from the repo root** by GitHub Pages.
Pages, scripts, and the data files they fetch all live at root and reference each other by **relative path** —
this is why none of them can be moved (see the golden rules in [`AGENTS.md`](../AGENTS.md)).

## Nav — 11-tab sidebar

`site-nav.js` renders a single fixed left sidebar (the **single source of truth** is the
`STRATEGY_NAV_ITEMS` array). Two groups:

- **Strategies (11 tabs):** `spx_water`, `spx` (Octane, the bespoke `index.html`), `ndx_water*`,
  `ndx_octane*`, `ftse250`, `dax`, `msci_em`, `msci_world`, `gold`, `lqq3`, `3bal`.
- **Tools & research:** `summary`, `instruments`.

Each tab shows an **asset label + one-line strategy** (e.g. "S&P 500 Water — SMA200 ±3% Band 1x/cash").
The `*` on the two Nasdaq tabs flags that no leverage configuration clears the drawdown gate (see
[`strategies.md`](strategies.md)). Pages **dropped from the nav** but still present as files: S&P 3x
Levered (`index.html` `spx3x` tab), the old standalone Nasdaq Guarded, and the Research pages.

**When you change the nav, bump the `site-nav.js?v=` query string on every page that includes it** so the
browser cache doesn't serve a stale menu.

## Pages (`*.html`, root)

| File | Shows |
|------|-------|
| `index.html` | S&P 500 Octane (the **bespoke** page). Tabs: Guarded, Momentum, SPX 3x Levered (`spx3x`, unlinked from nav), plus the Octane `SMA200 ±3% Band + RSI>20 Exit 2x` |
| `spx_water.html` | **Shared-renderer** page — S&P 500 Water, `SMA200 ±3% Band 1x/cash` |
| `ndx_water.html` | **Shared-renderer** page — Nasdaq 100 Water*, `SMA50/200 Golden Cross 1x/cash` |
| `ndx_octane.html` | **Shared-renderer** page — Nasdaq 100 Octane*, `GC 50/200 1x; +2x when VIX<20 & idxDD>-12%` |
| `gold_guarded.html` | Gold Guarded (1x) — pulls a **live** intraday quote via the Cloudflare Worker |
| `ftse250_guarded.html`, `dax_guarded.html`, `msci_em_guarded.html`, `msci_world_guarded.html`, `lqq3_guarded.html` | Template-driven guarded pages (1x), now also live-quote enabled |
| `3bal_guarded.html` | 3-asset balanced sleeve (bespoke guarded JS) |
| `summary.html` | Cross-asset overview table + per-asset Water/Octane drill-down (reads `summary_excel.json`) |
| `instruments.html` | ETF / Halal instrument browser |
| `live_guarded_sma20_leverage.html` | Standalone live SMA20 leverage view |
| `ndx_guarded.html` | Old standalone Nasdaq Guarded — **kept on disk, dropped from nav** |

### Shared-renderer pages (`spx_water` / `ndx_water` / `ndx_octane`)

These three are **thin host pages**: ~25 lines of HTML that set three globals and include
`site-nav.js` + `strategy_page.js`. The renderer builds the entire Signal / Back-test / Monte-Carlo
experience from a precomputed `*_site_data.json` payload — so a new full-parity page is just a host
page + a JSON. The globals:

```html
window.STRATEGY_DATA_URL  = "spx_water_band_site_data.json"; // the precomputed payload
window.STRATEGY_PAGE_TITLE = "S&P 500 Water — …";
window.STRATEGY_QUOTE      = { symbol: "spx", ticker: "^GSPC" }; // live-quote slug + safeguard ticker
```

`strategy_page.js` handles both strategy families from the same payload shape: **band** (S&P Water/Octane,
keyed by `price_sma_data.sma200_upper_band`) and **golden cross** (Nasdaq Water*/Octane*, keyed by
`sma50`/`sma200`; the Octane variant also fetches a live `^VIX` quote for the 2× bump). See *Live data flow*.

## Scripts (`*.js`, root)

| File | Role |
|------|------|
| `site-nav.js` | Shared left sidebar nav, hash-based routing (edit this to change the menu; bump `?v=` everywhere on change) |
| `strategy_page.js` | **Shared full-parity renderer** for the host pages (`spx_water`/`ndx_water`/`ndx_octane`) — builds Signal/Back-test/Monte-Carlo from a `*_site_data.json` + live quote |
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
- `spx_water_band_site_data.json` — feeds `spx_water.html` (from `backtest_spx_water_band.py`).
- `ndx_water_site_data.json`, `ndx_octane_site_data.json` — feed `ndx_water.html` / `ndx_octane.html` (both from `backtest_ndx_gc_strategies.py`).
- `summary_excel.json` — feeds `summary.html`.
- `output/strategy_results/all_assets_combined.csv` — also fetched by the site (note the `output/` path is live).

## Live data flow

1. `cloudflare_spx_quote_worker.js` (deployed at Cloudflare Workers, `spx-quote-proxy`) proxies Yahoo
   Finance for CORS and **maps every page slug → ticker**.
2. `?mode=daily&symbol=…` → 30y CSV of daily closes; `?mode=quote&symbol=…` → latest intraday price.
3. **All pages are now intraday-live** — the 4 strategy pages (`spx_water`/`ndx_water`/`ndx_octane` via
   `strategy_page.js`, plus S&P Octane) and all 7 guarded pages fetch a live quote and recompute the
   current signal client-side.
4. **Ticker-match safeguard (critical):** every live fetch checks `quote.ticker === EXPECTED_TICKER`
   (passed via `STRATEGY_QUOTE.ticker` / the guarded JS). If they differ — e.g. a stale worker serving
   `^GSPC` for everything — the quote is **rejected** and the page falls back to the last completed close.
   This is what fixed the old *Gold-shows-SPX* bug.
5. Auto-refresh every 30 min during UK LSE hours (Mon–Fri 08:00–16:30 London) via
   `SiteNav.registerAutoRefresh`.
6. The signal is computed **client-side** (SMA windows, drawdown from peak, band/golden-cross gates,
   leverage recommendation) — mirroring the Python logic (see [`strategies.md`](strategies.md)).
7. **Claude cannot deploy the worker** (no wrangler auth in-session). Any change to
   `cloudflare_spx_quote_worker.js` needs the **user** to run `npx wrangler deploy` (or the CF dashboard).

## Adding / editing pages

Three kinds of page, three workflows:

1. **Shared-renderer pages** (`spx_water`, `ndx_water`, `ndx_octane`) — *preferred for new full-parity
   strategy pages.* Write a backtest that emits a `*_site_data.json` (see `backtest_spx_water_band.py` /
   `backtest_ndx_gc_strategies.py` for the payload shape), copy a thin host page, point its
   `STRATEGY_DATA_URL` / `STRATEGY_QUOTE` at the new JSON + slug, then add a row to `STRATEGY_NAV_ITEMS`
   in `site-nav.js` (and bump `site-nav.js?v=` everywhere). No HTML/JS hand-hydration needed.
2. **Template-driven guarded pages** (ftse250, msci_em, dax, msci_world, lqq3) — from
   `guarded_asset_registry.py` (metadata) + `build_guarded_asset_pages.py` (generator, gold template).
   Regenerate **JS only**, never the `.html` (see Gotchas).
3. **Bespoke pages** — `index.html` (S&P Octane) and `3bal_guarded.html` are hand-maintained.

## ⚠️ Gotchas

- **Committed pages are hand-hydrated snapshots, not pure builder output.** Re-running a page builder can
  regress static Legacy/OOS tables. **Diff before committing.**
- **`build_ndx` fails *silently* on drift and is currently drifted**; `build_gold` fails *loud*. Don't assume
  a clean re-run.
- **Invalid JSON kills the page silently:** if a builder writes `NaN`/`Inf` into a `*.json`, the browser's
  `JSON.parse` throws and `staticSiteData` becomes `null` (page shows stale/blank). Sanitize `NaN`/`Inf` → `null`
  and dump with `allow_nan=False`.
- After deploying, the nav label / JSON may need a hard refresh (Ctrl+Shift+R) past the browser cache.
