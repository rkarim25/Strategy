# Website

The static site at https://rkarim25.github.io/Strategy/ is served **from the repo root** by GitHub Pages
(`deploy-pages.yml`). Pages, scripts, and the JSON they fetch all live at root and reference each other by
**relative path** — none of them can be moved (see the golden rules in [`AGENTS.md`](../AGENTS.md)).
Deploy via the worktree/cherry-pick procedure in [`deploy.md`](deploy.md) (OneDrive locks `.git`).

## One shared renderer for (almost) every page

Every asset/strategy page is now a **thin host** on the shared renderer **`strategy_page.js`**: ~25 lines of
HTML that set three globals and include `site-nav.js` + `strategy_page.js`. The renderer fetches a precomputed
`*_site_data.json` and builds the whole Signal / Back-test / Monte-Carlo experience.

```html
window.STRATEGY_DATA_URL  = "ftse250_guarded_site_data.json"; // the precomputed payload
window.STRATEGY_PAGE_TITLE = "FTSE 250 — SMA20 1x/cash";
window.STRATEGY_QUOTE      = { symbol: "ftse250", ticker: "^FTMC" }; // live-quote slug + safeguard ticker
```

What the renderer shows:
- **Signal view** (default tab): current-signal banner (live or last close), a **manual-price box**
  (recomputes the *current* signal only), the **price & SMA chart with on-chart signal markers**, and the
  **rebased %-equity P&L chart** (strategy vs buy-&-hold, 0% at window start, markers overlaid, **opens at 1Y**,
  range buttons + custom date pickers), then a recent-signal-history table.
- **Back-test view**: KPI cards, a growth-of-$100 (log) chart, and the comparison table.
- **Monte-Carlo view**: block-bootstrap distribution summary.

**Two pages are NOT thin hosts:** `index.html` (S&P 500 Octane — a bespoke multi-tab page) and the Tools pages
(`summary.html`, `instruments.html`). The old 2,200-line per-asset thick-client pages were **retired**; their
backups are in `archive/guarded_legacy/` and the dead `*_guarded.js` files remain on disk but are unreferenced.

### Strategy families (how the renderer knows the rule)

The renderer supports **three families**, keyed off the `price_sma_data` shape + `strategy_params.family`. Each
has its own price-chart lines and its own `liveLeverage()` branch (used by the manual-price + live-quote recompute):

| family | `price_sma_data` keys | rule |
|--------|------------------------|------|
| `sma_cash` | `sma_main` | close > SMA(window) → in, else cash |
| `band` | `sma200`, `sma200_upper_band`, `sma200_lower_band` | ±band hysteresis around SMA(window) |
| `gc` | `sma50`, `sma200` | golden cross SMA(fast) > SMA(slow) (+ optional Octane 2× bump) |

## Nav — sidebar (`site-nav.js`)

`site-nav.js` renders the fixed left sidebar; the **single source of truth** is `STRATEGY_NAV_ITEMS`. Each tab
shows asset + the **actual default strategy name** (kept in sync with the page's `default_backtest.strategy`):

| Tab | Default strategy | Family |
|-----|------------------|--------|
| S&P 500 Water | SMA175 ±3% Band 1x/cash | band |
| S&P 500 Octane | SMA200 ±3% Band + RSI>20 Exit 2x | *(bespoke `index.html`)* |
| Nasdaq 100 Water\* | SMA50/200 Golden Cross 1x/cash | gc |
| Nasdaq 100 Octane\* | GC 50/200 1x; +2x when VIX<20 & idxDD>-12% | gc (octane) |
| FTSE 250 | SMA20 1x/cash | sma_cash |
| DAX | SMA200 ±3% Band 1x/cash | band |
| MSCI EM | SMA100 1x/cash | sma_cash |
| MSCI World | SMA200 1x/cash | sma_cash |
| Gold | SMA50/150 Golden Cross 1x/cash | gc |
| LQQ3 3x Nasdaq | SMA200 1x/cash | sma_cash |
| 3BAL 3x EU Banks | SMA20 1x/cash | sma_cash |
| *Tools* | Lab, Charts, Summary results, Instruments | — |

The `\*` on the Nasdaq tabs flags Stillwater picks (strict Water unreachable). Gold/MSCI EM/MSCI World/LQQ3
have **no strict Water** either (their buy-&-hold is too strong) — they use the best available 1x/cash trend.
`ndx_guarded.html` (old standalone Nasdaq Guarded) is kept on disk but dropped from the nav.

**Bump the `site-nav.js?v=` / `strategy_page.js?v=` query strings site-wide on every page** when you change
either file, or the browser serves a stale cached copy.

## Per-asset default strategy (the one place to change a pick)

- **`core/site_default_strategy.py`** — `SITE_DEFAULT_STRATEGY` maps slug → spec
  (`{name, kind: "sma"|"band"|"gc", window/band_pct/fast/slow/leverage}`). Slugs absent here fall back to the
  legacy Guarded A5/B25 default.
- **`core/guarded_site_series.py`** — `leverage_for(prices, spec)`, `strategy_params_for(spec)`,
  `build_price_sma_data_for(prices, spec)` (correct shape per family) + `build_signal_history` /
  `build_equity_curve`. All values NaN/Inf-sanitised.

To change an asset's default: edit `SITE_DEFAULT_STRATEGY`, re-run its emitter (below), update the nav label +
the page's `<title>`/`STRATEGY_PAGE_TITLE`, and bump `?v=`.

## Charts workstation + US-curve desk (`price.html` / `price.js`, Tools → "Charts")

A standalone TradingView/Bloomberg-style charting app on **vendored KLineChart v9.8.12** (`klinecharts.min.js`,
MIT, ~205 KB — keep vendored, no CDN runtime dep). Self-contained (only reuses `window.SP` styles).
**Regenerate all data with `python make_price_data.py`** (Yahoo); it writes every `price_<id>.json`,
`price_assets.json` (the registry), `ust_curve.json` (live curve) — all at root.

- **Assets (29, registry `price_assets.json`):** Indices (incl. **FTSE 250** `^FTMC`) / **Leveraged ETPs** (LQQ3 3×
  Nasdaq `LQQ3.L`, 3BAL 3× Euro banks `3BAL.L`, XS2D 2× S&P `XS2D.L`) / Commodities / Crypto / FX (`kind:"price"`),
  **Rates** = UST yields 3M `^IRX` / 2Y `2YY=F` / 5Y `^FVX` / 7Y(interp) / 10Y `^TNX` / 30Y `^TYX` (`kind:"yield"`),
  **Steepness** = 2s10s/3m10y/5s10s/5s30s and **Butterfly** = 2s5s10s/5s10s30s + RW-fly variants (`kind:"spread"`,
  carry `legs:[{t,w}]`). **Add an asset = one row in `make_price_data.py`** (then regen, or generate just that file
  + merge into the registry). **CACHE CAVEAT:** `price_assets.json` is fetched without a cache-buster → a newly-added
  asset only appears after the ~10-min Pages cache expires or a hard-refresh.
- **Backtest models (per `kind`):** price → long/cash, %-returns, $100 growth. **UST (`yield`+`spread`) → DIRECTIONAL,
  P&L = position × daily Δ(series) in bps** (`isDelta` path): yield long = *long rates* (profit when yield rises),
  spread long = *steepener*, fly = *RV reversion*. Columns switch to Ann bps/Max DD bps/Sharpe/Hit %/Total bps, or
  **DV01 $** (toggle + editable $/bp = trade DV01 from `TICKER_DV01`).
- **RW-flies** (`build_fly_beta`): belly hedged by wings via a **rolling ~3y-window OLS** (out-of-sample, lagged,
  tracks regime drift). Honest finding: OOS the simple 50-50 fly (= equal-weight `2×belly−wings`) **beats** the
  regression fly. **Carry/roll** can be baked into the UST backtest (toggle): each day adds the position's carry+roll
  drift. **Historical/time-varying** — `make_price_data.add_carry_history()` writes a per-date `cr` series (bps/3m,
  long-the-instrument, from the curve on *that* date) into each UST file, so the drift flips sign with the regime
  (long rates *earns* carry when the curve is inverted, *pays* when normal). Carry term uses exact yield levels; the
  roll term interpolates the available tenors (cruder pre-2021). Falls back to today's-curve-held-flat if `cr` absent.
- **Layout (max chart):** the on-page title/intro is gone (browser-tab title kept per asset); Asset/TF/Type/Axis/Range/live
  live in one compact top bar; the Draw tools sit in a collapsed-by-default `<details>`; chart height is responsive
  (`clamp(460px,74vh,840px)`). **Pan** control (‹ back · "now" `scrollToRealTime` · › forward = `chart.scrollByDistance ±½-width`).
- **Chart types:** **Bars (forced default)**/Candles/Area · linear/log/% axis (spreads forced linear — they go negative) ·
  range presets. **Bars = a custom symmetric HLOC renderer**, NOT KLineChart's built-in `ohlc` (whose close tick rendered
  ~⅓ shorter than open): in Bars mode the built-in candle is made transparent and an `HLOC` `registerIndicator` draws the
  H-L line + equal-length open(left)/close(right) ticks (`applyBarMode`/`BAR_MODE`). Bars is forced on every load (`applySnapshot`
  ignores saved type).
- **Timeframes** 1m/5m/15m/30m/1h/4h/1D. **1D is real-time too:** the committed `price_<id>.json` lags a few days, so
  `extendDailyLive()` merges fresh daily bars (incl. today's forming bar) from the quote-proxy `?mode=intraday&interval=1d`
  by exact timestamp, every 60 s; intraday TFs fetch `?mode=intraday`; **spreads/flies combine each leg's intraday client-side**
  via `fetchIntradayBars`/`combineLegs`; 4h aggregated. Live readout shows the price + **last-update time in UK** (`ukClock`,
  Europe/London).
- **Indicators:** 6 overlays + 20 studies w/ editable calcParams. **Drawing:** trend/ray/lines/price/parallel/
  fibonacci/text + **Measure %** + **free-draw** (sketch, then right-click **Enhance** → circle/square/rect/trend/
  ray/channel) + **rectangle/circle** tools + an **erase tool** (click a drawing, or drag a box to clear an area) +
  **notes that link to a drawing** and ride along when it moves. Every overlay gets a **stable id** (passed to
  `createOverlay`) so note-links and alerts survive `applyNewData`/reload (drawings tracked in JS — v9 has no
  `getOverlays`; persisted with private notes via the store worker). **Right-click a drawing →** colour swatches
  (persisted via `color` through record/snapshot/reapply), **📐 Show angle** for trend lines (visual angle vs horizontal
  + % move, via `chart.convertToPixel` resolving each point by `dataIndex` so future-area endpoints still measure), Erase,
  alert, linked note; **Enhance is freeDraw-only** (`ENHANCEABLE={freeDraw}`). KLineChart's per-endpoint date/price **axis
  tags are suppressed** (`needDefaultX/YAxisFigure:false`) — they overlapped into unreadable blocks. **Stability:** a
  drawing's null/future-area endpoint timestamp is clamped to the last bar, and drawings re-anchor after `extendDailyLive`
  appends a new bar, so trend lines don't jump on reload. **Display toggles** for all drawings / all
  alert markers. Everything (notes/drawings/indicators/alerts) **auto-saves** — instant local + auto cloud-sync once
  signed in via the top-bar **☁ Save** button. **NBER recession shading** (`RECESSION`, "▦ Recessions") + **curve-inversion shading** (`INVERSION`,
  "⊘ Inversions"; amber bands over the 16 sustained 2s10s/3m10y inverted periods in `ust_inversions.json`) — both
  custom `draw`-callback indicators; they paint only over the visible window (verify by slicing data to end mid-band).
- **Signal Playbook (14 rules):** Golden/EMA Cross, Trend, Band trend (Water), MACD/MACD-zero, RSI momentum/reversion,
  Bollinger, Donchian, Williams %R, Stochastic, CCI, RSI-dip+SMA-exit. Live param inputs → live backtest; **plot**
  (draws the indicator), **signals** (▲/▼ markers via custom-indicator `draw`), **notes** (preloaded why). Optional
  **2×/3× when-safe leverage** (DD+vol gated) + costs toggle for `price` assets.
- **Signal dashboard (SPX/NDX only, below the chart):** reads `signals_{spx,ndx}.json` — technical indicators
  graded **A–D** by their backtested edge vs buy-and-hold (from `output/comprehensive_sweep`, via
  `research/build_signal_dashboard.py` + `signal_state.py`; **no re-backtesting**), each with a live **0–100
  strength** computed in-browser, a trust-weighted **composite → independent suggested leverage**, **show-on-chart**
  (plots the indicator + ▲/▼ markers) and a **view-backtest** modal. VIX overlay pulls live VIX from the quote proxy.
- **🧠 One-click Analyst:** the "hours of chart-reading in one click". Builds a live bundle (graded signals +
  official mechanical signal + news + **the chart you're viewing** + a screenshot) and renders a deterministic
  quant report + **copy-prompt (+ image)** for any Claude chat; an optional Cloudflare worker
  (`cloudflare_market_analyst_worker.js`) does it inline via the Claude API. Shared "brain" = `analyst_prompt.md`
  (used by the website, the worker, and the `oneclick-analyst` skill / `research/build_analyst_bundle.py`). Full
  architecture + replication notes in [`oneclick-analyst.md`](oneclick-analyst.md).
- **Price alerts:** set on any line/level (right-click a drawing, the chart, or the 🔔 marker), denoted on the
  chart by a dashed 🔔 line (a managed **Price alerts** section lists them with edit-level/rename/delete; drag the
  line to change the level). Alerts on a **trend/ray line follow the line** (trigger updates each bar); a tracked sloped
  line is **highlighted amber** on the chart (`applyDrawingColors`) and its row shows the line's **angle** + current
  crossing level, so you can tell which line is tracked. Fire a toast+beep+notification on the live-quote tick; persisted
  with the private chart.
- **Curve strategy leaderboard** (`ust_strategies.json` ← `scratch/ust_strategy_sweep.py`): best rule per UST instrument
  ranked by Sharpe + explanation + **live signal** + Load; the **best rule is auto-applied as the default** for each
  UST trade. Plus a **live curve snapshot** (`ust_curve.json`: SVG 3M→30Y + 2s10s/3m10y/5s30s slope/inversion flags +
  3m **roll-down**/carry per tenor) and a **rich/cheap** readout (z-score, percentile, 1y range).
- **Persistence:** private per-asset notes + drawings + params via the **`lab-strategy-store` worker**
  (`GET`/`POST /api/chart/:asset`, **both passphrase-gated**), localStorage fallback + autosave. **Mobile:** wide tables
  scroll inside their cards (`overflow-x:auto`); chart 60vh.
- **⚠ Preview gotcha:** KLineChart renders via `requestAnimationFrame`, which the headless preview throttles → the
  page's canvases stay blank (300×150) and animated scrolls don't move. NOT a bug — it renders fine in a real browser.
  The chart instance is exposed as **`window.__chart`** for headless debugging: read state (`getVisibleRange`,
  `convertToPixel`), or spy a method call to verify a handler fires (the visible result needs a real browser). Verify
  drawing/canvas features by DOM geometry + method spies, not screenshots.
- **⚠ Windows:** non-ASCII chars (β, −) in Python `print`/labels crash on cp1252 — use ASCII (`RW`, `-`).

## Scripts (`*.js`, root)

| File | Role |
|------|------|
| `strategy_page.js` | **Shared renderer** (Signal/Back-test/MC; markers, %-equity, manual-price; sma_cash/band/gc families) |
| `site-nav.js` | Shared left sidebar nav + `STRATEGY_NAV_ITEMS` (bump `?v=` everywhere on change) |
| `lab.js` | **Lab** — strategy builder on `band_lab_*`/`lab_ndx.json` (S&P/Nasdaq only). AND/OR condition stacks with **level + cross** states per indicator (cross-up/down through line/level, golden/death, MACD signal/zero, Bollinger band crosses, Donchian breakout — momentary `crossUp/crossDn`, fire on the cross bar). **"Leverage on"** toggle: *Index* (signal on index, hold N×) vs *Synthetic* (`buildSynthetic` = daily-rebalanced N×+financing series; indicators **and** equity run on it). **Stop-loss % / Target %** exits (from the entry close). Cloud save (passphrase) + portable `#s=` links |
| `price.js` + `klinecharts.min.js` | **Charts** workstation (KLineChart) — see the Charts section above |
| `cloudflare_lab_store_worker.js` | **Not part of Pages** — `lab-strategy-store` Worker (KV) for Lab cloud-save + private chart notes (`wrangler.lab-store.toml`) |
| `site-scroll-init.js` | Scroll/section init shared across pages |
| `{slug}_guarded.js` | **Dead** — legacy thick-client logic, no longer referenced (kept on disk) |
| `etp-leverage.js`, `all-instruments-data.js`, `instruments-*.js`, `halal-comparison-data.js` | `instruments.html` data/render |
| `cloudflare_spx_quote_worker.js` | **Not part of Pages** — source of the deployed quote-proxy Worker (config in `wrangler.toml`) |
| `cloudflare_market_analyst_worker.js` | **Not part of Pages, not deployed** — optional Analyst worker (Claude API) for inline AI; drop-in per [`oneclick-analyst.md`](../docs/oneclick-analyst.md) |

## Data files the site fetches (root — do not move)

- `{slug}_guarded_site_data.json` / `spx_water_band_site_data.json` / `ndx_water_site_data.json` /
  `ndx_octane_site_data.json` — the per-page payload. Each carries `default_backtest`, `comparison_table`,
  `monte_carlo`, **`strategy_params`** (family + params), **`price_sma_data`**, **`signal_history`**,
  **`equity_curve`** (the last three drive the price chart, markers and %-equity chart).
- `spx_distance_scale_site_data.json` (+ `*_etp_returns.json`) — the bespoke `index.html`.
- `{slug}_daily.csv`, `latest_{slug}_signal.json` — cron-refreshed price/signal data (don't bundle in feature commits).
- `summary_excel.json` — feeds `summary.html`.
- `price_assets.json` + `price_<id>.json` (29) — the **Charts** page registry + per-asset OHLCV (regenerate with
  `python make_price_data.py`). `band_lab_spx.json` / `lab_ndx.json` — the **Lab** datasets.
- `signals_{spx,ndx}.json` — the **signal dashboard** data (graded indicators + live-eval rules + evidence;
  regenerate with `python research/build_signal_dashboard.py`). `analyst_prompt.md` — the shared **Analyst brain**
  (fetched by the website copy-prompt + the worker). `analyst_bundle.json` is a regenerated local artifact — **not
  served, not committed** (gitignored).

## Backtest emitters (regenerate the payloads)

| Emitter | Pages | Notes |
|---------|-------|-------|
| `backtest_guarded_assets.py` | ftse250, dax, msci_em, msci_world, lqq3 | dispatches per `SITE_DEFAULT_STRATEGY`; `--slug` to run one |
| `backtest_gold_guarded.py` | gold | SMA50/150 golden cross default |
| `backtest_3bal_guarded.py` | 3bal | SMA20 1x/cash default |
| `backtest_spx_water_band.py`, `backtest_ndx_gc_strategies.py` | spx_water, ndx_water, ndx_octane | band / golden-cross Water pages |
| `backtest_spx_distance_scale.py` | index.html (S&P Octane) | bespoke |

All dump with `allow_nan=False` (fail loud rather than write invalid JSON).

## Live data flow

1. `cloudflare_spx_quote_worker.js` (deployed `spx-quote-proxy`) proxies Yahoo for CORS and maps every slug → ticker.
2. Pages fetch a live quote; the renderer recomputes the **current** signal via `liveLeverage()` for that family.
3. **Ticker-match safeguard:** the quote is used only if `ticker === STRATEGY_QUOTE.ticker`, else it falls back to
   the last completed close (this is what fixed the old Gold-shows-SPX bug).
4. Auto-refresh every 30 min during UK LSE hours via `SiteNav.registerAutoRefresh`.
5. **Deploying the Workers (AI can do this here):** `npx --no-install wrangler` works and the user is already
   OAuth-logged-in (account `3554b8ca…`, rkarim88@gmail.com). Quote proxy: `npx --no-install wrangler deploy`
   (root `wrangler.toml`). Store/notes worker (`cloudflare_lab_store_worker.js`):
   `npx --no-install wrangler deploy -c wrangler.lab-store.toml`. A **Cloudflare MCP** is also connected for KV/D1.
   (The store worker is passphrase-gated via the `LAB_SECRET` secret; rotate with `wrangler secret put LAB_SECRET`.)
   The intraday feed (`?mode=intraday&symbol&interval&range`) and `?mode=quote` both come from the quote proxy.
6. **Charts is self-healing real-time:** the **1D** view doesn't just rely on the committed `price_<id>.json` (which lags
   a few days) — `extendDailyLive()` merges fresh daily bars (incl. today's forming bar) from the proxy's
   `?mode=intraday&interval=1d` every 60 s, so SPX/NDX/etc. are always current with no paid feed. Daily-bar timestamps
   match the committed file's exactly, so the merge is by exact timestamp.

## ⚠️ Gotchas

- **Invalid JSON kills a page silently:** `NaN`/`Inf` → `JSON.parse` throws → blank/stale page. Emitters use
  `allow_nan=False` and the series builders sanitise non-finite → `null`. (Pre-existing exception: `index.html`'s
  `spx_3x_levered_site_data.json` still contains NaN and falls back to synthetic — unaddressed.)
- **Bump `?v=` site-wide** when changing `site-nav.js` / `strategy_page.js`, or returning visitors get a stale cache.
- **`index.html` is still the bespoke S&P Octane page** (its own chart code + Momentum/SPX-3x tabs); it has not
  been migrated to the shared renderer.
- The dead `*_guarded.js` thick-clients and `archive/guarded_legacy/*.bak` can be deleted later — git history
  preserves the originals.
