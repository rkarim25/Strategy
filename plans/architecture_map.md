# Strategy Website — Architecture Map

> Generated from full source inspection of `C:\Users\Reza Karim\OneDrive\Systematic_Backstester\`
> Live site: https://rkarim25.github.io/Strategy/

---

## 1. Site Map — Pages, Tabs & Relationships

```
https://rkarim25.github.io/Strategy/
│
├── index.html                    ← Main strategy dashboard (S&P 500)
│   ├── #guardedStrategy          ← Top-level strategy container (default active)
│   │   ├── #signalPage           ← Signal: live EOD/intraday, charts, calculator, optimizer
│   │   ├── #backtestPage         ← Back-test: KPIs, drawdowns, equity chart, comparison tables
│   │   └── #monteCarloPage       ← Monte Carlo: MC comparison, risk probabilities, diagnostics
│   │
│   └── #momentumStrategy         ← Top-level strategy container (hidden by default)
│       ├── #momentumSignalPage   ← Signal: rule descriptions, design KPIs
│       ├── #momentumBacktestPage ← Back-test: KPIs, bar chart, trigger/long-hold tables, benchmarks
│       └── #momentumMonteCarloPage ← Monte Carlo: 75-path screening results (hardcoded)
│
├── summary.html                  ← Cross-asset backtest comparison (standalone page)
│   (Loads summary_data.json; 10 asset classes, 17 strategies, 3 data regimes)
│
├── instruments.html              ← Instruments/tools page (referenced in site-nav.js)
│
├── lqq3_guarded.html             ← LQQ3 3x Nasdaq strategy page
├── 3bal_guarded.html             ← 3BAL 3x EU Banks strategy page
├── ndx_guarded.html              ← Nasdaq 100 strategy page
├── ftse250_guarded.html          ← FTSE 250 strategy page
├── msci_em_guarded.html          ← MSCI EM strategy page
├── dax_guarded.html              ← DAX strategy page
├── msci_world_guarded.html       ← MSCI World strategy page
├── gold_guarded.html             ← Gold strategy page
│
└── Shared JS:
    ├── site-nav.js               ← Fixed sidebar nav, hash routing, auto-refresh
    ├── etp-leverage.js           ← Browser-side ETP daily return lookup + synthetic fallback
    └── site-scroll-init.js       ← Scroll-to-top on navigation
```

### Navigation Architecture

**Top-level (sidebar):** Rendered by [`site-nav.js`](site-nav.js:266) into `<nav aria-label="Strategies">`. Four groups:
- **Leveraged equity**: LQQ3 3x Nasdaq, 3BAL 3x EU Banks, Nasdaq 100, S&P 500
- **Equity (max 1x)**: FTSE 250, MSCI EM, DAX, MSCI World
- **Other**: Gold
- **Tools & research**: Summary results, Momentum strategy, Instruments

**Sub-page tabs:** Each strategy has a `<nav>` with `data-page-target` buttons for Signal / Back-test / Monte Carlo. Tab switching is driven by [`showPage()`](index.html:1832) which toggles `.page.active` CSS class.

**Hash routing:** [`site-nav.js`](site-nav.js:131) maps URL hash fragments to page IDs:
- `#signalPage`, `#backtestPage`, `#monteCarloPage` → Guarded strategy sub-pages
- `#momentumSignalPage`, `#momentumBacktestPage`, `#momentumMonteCarloPage` → Momentum sub-pages
- `?strategy=guarded` / `?strategy=momentum` → top-level strategy switch

---

## 2. Tab Structure — index.html Deep Dive

### 2.1 CSS Architecture

Two key CSS class pairs control visibility:

| CSS Class | Purpose |
|-----------|---------|
| [`.strategy` / `.strategy.active`](index.html:478) | Top-level strategy containers (`#guardedStrategy`, `#momentumStrategy`) |
| [`.page` / `.page.active`](index.html:394) | Sub-page containers within each strategy |

### 2.2 Guarded Strategy — Signal Page (`#signalPage`)

Lines 649–913. Contains:

| Section | Content | Data Source |
|---------|---------|-------------|
| Strategy Rules card | 5 bullet rules for A5/B25/X40/Y15 lead-guard logic | Hardcoded |
| Data Source card | Refresh button, manual SPX price input, status display | Live worker / static CSV |
| Official Signal (EOD) | Target leverage, close, SMA20, drawdown, regime, entry P&L | [`computeSignal()`](index.html:1928) from `latestRows` |
| Live Intraday Signal | Same fields, provisional from live quote or manual override | Worker quote / manual input |
| SPX Close vs 20-Day SMA Chart | SVG chart with trade markers, range controls | [`renderChart()`](index.html:2830) |
| Selected Window Equity P&L Chart | Strategy vs SPX equity for selected window | [`renderSignalPnlChart()`](index.html:3093) |
| Shared Strategy State | High-water, tier levels, SMA status | [`render()`](index.html:2452) |
| Guarded Strategy Calculator | A/B/X/Y parameter inputs, run button, KPI output | [`runCalculator()`](index.html:2246) → [`backtestParameterizedGuarded()`](index.html:2169) |
| Goal Seek / Optimizer | Grid search over A/B/X/Y ranges, diversified results | [`runOptimizer()`](index.html:2312) |

### 2.3 Guarded Strategy — Back-test Page (`#backtestPage`)

Lines 915–1055. Contains:

| Section | Content | Patched? |
|---------|---------|----------|
| Back-test Overview | 8 KPI cards (CAGR, max DD, Sharpe, vol, Calmar, end value, NPV, multiple) | **Yes** — KPIs patched from `spx_guarded_site_data.json` |
| Backtest Callout | Comparison vs original A10/B20 | **Yes** — regex replacement |
| Top 20 Strategy Drawdowns | Client-side computed table | No — computed by [`renderTopDrawdownsTable()`](index.html:2650) |
| SPX vs Default Strategy Equity Chart | SVG log-scale equity chart | No — [`renderBacktestEquityChart()`](index.html:3372) |
| Full-Sample Strategy Comparison | 8-strategy comparison table | **Yes** — patched from `spx_guarded_comparison.csv` |
| Legacy Guard SMA Sensitivity | SMA20/50/200 tiered comparison | **Yes** — patched from `guarded_tiered_sma20_50_200_results.csv` |
| Forward and Out-of-Sample Checks | 2006-2026 / 2006-2015 / 2016-2026 periods | No — hardcoded |

### 2.4 Guarded Strategy — Monte Carlo Page (`#monteCarloPage`)

Lines 1057–1130. Contains:

| Section | Content | Patched? |
|---------|---------|----------|
| Monte Carlo Validation | 4 KPI cards (simulations, horizon, median CAGR, median max DD) | **Yes** — 2 KPIs patched from `spx_guarded_site_data.json` |
| Monte Carlo Comparison | 3-strategy comparison table | **Yes** — patched from `guarded_balanced_candidate_monte_carlo_summary.csv` |
| Risk Probabilities | 4 probability rows (DD > -35%, -40%, -50%, end below start) | **Yes** — 4 cells patched from site data |
| Default Strategy Diagnostics | Cash/1x/2x/3x days, entries, costs | **Yes** — patched from site data |

### 2.5 Momentum Strategy (`#momentumStrategy`)

Lines 1134–1376. Three sub-pages with similar structure but simpler content:

- **Signal Page**: Rule description tables (hardcoded), design KPIs (hardcoded)
- **Back-test Page**: KPIs (hardcoded), CAGR bar chart (patched), Daily Momentum Trigger Backtests table (**patched** from `momentum_leverage_results.csv`), Long-Hold Momentum Backtests table (**patched** from `long_hold_momentum_results.csv`), Reference Benchmarks table (**patched** from `spx_guarded_comparison.csv`)
- **Monte Carlo Page**: All content **hardcoded** (75-path screening results, not patched)

---

## 3. Data Pipeline — Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    BACKTEST SCRIPTS (Python)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  backtest_spx_guarded.py                                         │
│  ├── Downloads SPX + T-bill data (yfinance, 30 years)            │
│  ├── Builds ETP return panel (SPY/SSO/UPRO + VIX-linked synth)   │
│  ├── Runs 8 strategies (B&H 1x/2x/3x, SMA20 1x/2x/3x/cash,      │
│  │    Guarded A5/B25, Original A10/B20)                          │
│  ├── Runs 200-path Monte Carlo (21-day block bootstrap)          │
│  └── Outputs:                                                    │
│      ├── spx_guarded_site_data.json          ← PRIMARY SITE DATA │
│      ├── spx_etp_returns.json                ← ETP daily returns │
│      ├── output/spx_guarded/spx_guarded_comparison.csv           │
│      ├── output/spx_guarded/spx_guarded_default_backtest.csv     │
│      └── output/spx_guarded/spx_guarded_monte_carlo_paths.csv   │
│                                                                  │
│  backtest_momentum_leverage_strategies.py                        │
│  ├── Runs 6 daily momentum triggers + 7 references               │
│  └── Outputs:                                                    │
│      └── output/momentum_leverage_strategies/                    │
│          ├── momentum_leverage_results.csv                       │
│          └── momentum_leverage_chart_data.json                   │
│                                                                  │
│  backtest_long_hold_momentum_strategies.py                       │
│  ├── Runs 6 long-hold momentum + 7 references                    │
│  └── Outputs:                                                    │
│      └── output/long_hold_momentum_strategies/                   │
│          ├── long_hold_momentum_results.csv                      │
│          └── long_hold_momentum_chart_data.json                  │
│                                                                  │
│  backtest_guarded_tiered_sma20_50_200.py                         │
│  └── Outputs:                                                    │
│      └── output/guarded_tiered_sma20_50_200/                     │
│          └── guarded_tiered_sma20_50_200_results.csv             │
│                                                                  │
│  test_guarded_balanced_candidate.py                              │
│  └── Outputs:                                                    │
│      └── output/guarded_balanced_candidate/                      │
│          └── guarded_balanced_candidate_monte_carlo_summary.csv  │
│                                                                  │
│  summary_data.json (generated separately, feeds summary.html)    │
│                                                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              patch_index_html_backtests.py (Python)              │
│              Patches ONLY index.html                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Uses marker-based replace_tbody() — finds <h2> heading text,   │
│  then replaces the next <tbody>...</tbody> block.               │
│                                                                  │
│  SECTION                    ← DATA SOURCE                        │
│  ─────────────────────────────────────────────────────────────   │
│  Full-Sample Strategy       ← spx_guarded_comparison.csv        │
│  Comparison                                                        │
│                                                                  │
│  Legacy Guard SMA            ← guarded_tiered_sma20_50_200_      │
│  Sensitivity                   results.csv (Guarded A10/B20)     │
│                                                                  │
│  Daily Momentum Trigger      ← momentum_leverage_results.csv     │
│  Backtests                     (group="Momentum trigger")        │
│                                                                  │
│  Long-Hold Momentum          ← long_hold_momentum_results.csv    │
│  Backtests                     (group="Long-hold momentum")     │
│                                                                  │
│  Monte Carlo Comparison      ← guarded_balanced_candidate_       │
│                                monte_carlo_summary.csv           │
│                                                                  │
│  Reference Benchmarks        ← spx_guarded_comparison.csv       │
│                                (5 specific strategies)           │
│                                                                  │
│  Default Strategy            ← spx_guarded_site_data.json       │
│  Diagnostics                   (default_backtest)                │
│                                                                  │
│  KPI cards (6 regex)         ← spx_guarded_site_data.json       │
│  MC KPI cards (2 regex)      ← spx_guarded_site_data.json       │
│  Risk Probabilities (4)      ← spx_guarded_site_data.json       │
│  Backtest callout            ← spx_guarded_site_data.json       │
│  Overview note               ← hardcoded in patcher             │
│  Bar chart CAGR values       ← spx_guarded_comparison.csv       │
│                                                                  │
│  Does NOT touch summary.html                                     │
│                                                                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BROWSER (index.html)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Static files loaded on page init:                               │
│  ├── spx_daily.csv              ← Historical daily closes        │
│  ├── latest_signal.json         ← Static signal metadata        │
│  ├── spx_guarded_site_data.json ← KPI cards, MC, diagnostics    │
│  └── spx_etp_returns.json       ← ETP daily return panel        │
│                                                                  │
│  Live data (on refresh):                                        │
│  ├── Cloudflare Worker (daily)  ← Full SPX history CSV          │
│  └── Cloudflare Worker (quote)  ← Live intraday SPX price       │
│                                                                  │
│  Client-side computation:                                        │
│  ├── computeSignal()            ← Guarded A5/B25 logic in JS    │
│  ├── backtestParameterizedGuarded() ← Full backtest in JS      │
│  ├── renderChart()              ← SVG price + SMA20 chart       │
│  ├── renderSignalPnlChart()     ← SVG equity P&L chart          │
│  ├── renderBacktestEquityChart() ← SVG cumulative return chart  │
│  └── EtpLeverage.dailyReturn()  ← ETP P&L lookup/synthetic      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Data Files Summary

| File | Format | Generated By | Consumed By |
|------|--------|-------------|-------------|
| `spx_guarded_site_data.json` | JSON (261 lines) | `backtest_spx_guarded.py` | `index.html` (browser) + `patch_index_html_backtests.py` |
| `spx_etp_returns.json` | JSON (1 line, large arrays) | `backtest_spx_guarded.py` | `index.html` → `etp-leverage.js` |
| `spx_daily.csv` | CSV | External/manual | `index.html` (browser) |
| `latest_signal.json` | JSON | External/manual | `index.html` (browser) |
| `summary_data.json` | JSON | Separate generator | `summary.html` (browser) |
| `output/spx_guarded/spx_guarded_comparison.csv` | CSV | `backtest_spx_guarded.py` | `patch_index_html_backtests.py` |
| `output/momentum_leverage_strategies/momentum_leverage_results.csv` | CSV | `backtest_momentum_leverage_strategies.py` | `patch_index_html_backtests.py` |
| `output/long_hold_momentum_strategies/long_hold_momentum_results.csv` | CSV | `backtest_long_hold_momentum_strategies.py` | `patch_index_html_backtests.py` |
| `output/guarded_tiered_sma20_50_200/guarded_tiered_sma20_50_200_results.csv` | CSV | `backtest_guarded_tiered_sma20_50_200.py` | `patch_index_html_backtests.py` |
| `output/guarded_balanced_candidate/guarded_balanced_candidate_monte_carlo_summary.csv` | CSV | `test_guarded_balanced_candidate.py` | `patch_index_html_backtests.py` |

---

## 4. Charting Infrastructure

### 4.1 Technology: Pure SVG (No External Library)

The site uses **zero charting libraries** — no Plotly, no Chart.js, no D3, no Canvas. All three charts are hand-built SVG rendered by JavaScript functions that construct `<polyline>`, `<line>`, `<text>`, `<circle>`, and `<polygon>` elements directly into inline `<svg>` elements.

### 4.2 Three Charts

| Chart | SVG Element | Dimensions | Render Function | Data Source |
|-------|------------|------------|-----------------|-------------|
| SPX Close vs SMA20 | [`#priceChart`](index.html:739) | 900×360 | [`renderChart()`](index.html:2830) | `chartDataForRange()` → `latestRows` |
| Selected Window Equity P&L | [`#signalPnlChart`](index.html:755) | 900×260 | [`renderSignalPnlChart()`](index.html:3093) | `selectedWindowPnlData()` → `latestRows` |
| SPX vs Strategy Equity | [`#equityChart`](index.html:983) | 900×360 | [`renderBacktestEquityChart()`](index.html:3372) | `equityDataForRange()` → `latestRows` |

### 4.3 Chart Features

- **Range controls**: 1W/1M/3M/1Y/5Y/10Y/20Y/30Y/Full preset buttons + custom date range inputs + nudge (pan) buttons
- **Tooltips**: Custom `<div>` overlays positioned via SVG coordinate transformation (`getScreenCTM()`)
- **Trade markers**: Buy (upward triangle, green/blue) and sell (downward triangle, red/orange) markers on price and P&L charts
- **Hover layers**: `#signalPnlHoverLayer` and `#equityHoverLayer` with dashed vertical line + colored circles
- **Grid lines**: Auto-scaled Y-axis with nice-number tick generation
- **Date ticks**: Adaptive density based on data length (fewer ticks for longer ranges)
- **Log scale**: Equity chart uses return-based (percentage) Y-axis, rebased to 0% at range start

### 4.4 ETP Leverage Integration

[`etp-leverage.js`](etp-leverage.js:50) provides `EtpLeverage.dailyReturn(leverage, indexRet, cashRate, dateIso)` which:
1. Looks up the date in `spx_etp_returns.json` date index
2. Returns the real ETP daily return if available (from `ret_1`, `ret_2`, `ret_3` columns)
3. Falls back to [`syntheticDailyReturn()`](etp-leverage.js:33) with VIX-linked funding spread, volatility drag, and TER

---

## 5. Monte Carlo Infrastructure

### 5.1 Python-Side (backtest_spx_guarded.py)

- **Method**: Block bootstrap of joint historical segments (21-trading-day blocks)
- **Parameters**: 200 simulations, 10-year horizon (2520 days), seed 20260519
- **ETP handling**: Bootstraps both index returns AND ETP return columns together, preserving the joint distribution
- **Output**: 
  - `spx_guarded_monte_carlo_paths.csv` — per-path results (200 rows)
  - Summary stats embedded in `spx_guarded_site_data.json` under `monte_carlo` key

### 5.2 MC Summary Stats (in site data JSON)

```json
{
  "monte_carlo": {
    "n_sims": 200,
    "horizon_years": 10.0,
    "block_days": 21,
    "median_cagr": 0.0807,        // 8.07%
    "p10_cagr": -0.0227,          // -2.27%
    "p90_cagr": 0.1688,           // 16.88%
    "median_max_drawdown": -0.5282, // -52.82%
    "prob_max_dd_worse_35pct": 0.94,
    "prob_max_dd_worse_40pct": 0.875,
    "prob_max_dd_worse_50pct": 0.60,
    "prob_end_below_start": 0.18
  }
}
```

### 5.3 Browser-Side Display

- [`applySiteData()`](index.html:1540) reads `data.monte_carlo` and populates:
  - `#mcMedianCagr`, `#mcMedianMaxDd` — KPI cards
  - `#mcProbDd35`, `#mcProbDd40`, `#mcProbDd50`, `#mcProbBelowStart` — risk probability cells
- MC Comparison table is patched by `patch_index_html_backtests.py` from `guarded_balanced_candidate_monte_carlo_summary.csv`

### 5.4 Momentum Monte Carlo

- Separate 75-path screening run (results **hardcoded** in HTML, lines 1301–1375)
- Not patched; not regenerated by the standard pipeline
- Uses same 21-day block bootstrap method

---

## 6. Signals & Alerts Infrastructure

### Current State: Browser-Only, No Backend

| Feature | Implementation | Location |
|---------|---------------|----------|
| EOD Signal | [`computeSignal()`](index.html:1928) — full Guarded A5/B25 logic in JS | Client-side |
| Live Intraday Signal | Same `computeSignal()` with appended intraday row | Client-side |
| Data Refresh | Manual button or auto-refresh every 30 min | Client-side |
| Live Quote Source | Cloudflare Worker proxy: `https://spx-quote-proxy.rkarim88.workers.dev/` | External service |
| Manual Override | [`#manualIntradayPrice`](index.html:669) text input | Client-side |
| Static Fallback | [`latest_signal.json`](index.html:1386) — pre-generated signal metadata | Static file |
| Auto-Refresh Schedule | UK LSE hours only (Mon-Fri 08:00-16:30 London) | [`site-nav.js`](site-nav.js:604) |
| Email Alerts | **None** | — |
| Push Notifications | **None** | — |
| SMS/Telegram | **None** | — |
| Backend Service | **None** (static GitHub Pages site) | — |

### Signal Computation Logic

The [`computeSignal()`](index.html:1928) function implements the full Guarded A5/B25/X40/Y15 lead-guard logic:
1. Computes SMA20 rolling average
2. Tracks high-water mark and drawdown
3. Applies tier logic: base (cash/1x) → tier2 (2x at -5% DD) → tier3 (3x at -25% DD)
4. Lead guard: recovery leverage only when close ≥ 99.25% of SMA20
5. Exit conditions: 2x releases after +40% from entry, 3x releases after +15%

---

## 7. ETP Data Available

### 7.1 ETP Bundles Defined in [`etp_leverage.py`](etp_leverage.py:38)

| Bundle | Index | 1x ETF | 2x ETF | 3x ETF | Calendar |
|--------|-------|--------|--------|--------|----------|
| `SPX_ETP` | ^GSPC | SPY | SSO | UPRO | US (same-calendar) |
| `NDX_ETP` | ^NDX | QQQ | QLD | TQQQ | US (same-calendar) |

### 7.2 3USL Status

**3USL (European 3x S&P 500 UCITS ETF) is NOT used for daily-timed backtests.** The [`etp_leverage.py`](etp_leverage.py:50) docstring explains:

> *"The UCITS XS2D.L / 3USL.L (LSE) and LQQ.PA / LQQ3.L (Paris) were dropped from the daily-timed backtest because their Yahoo daily returns are calendar-offset vs the US index (corr ~0.57, ratio ~1.2x): long-run totals match but a daily-timed strategy gets badly inflated."*

However, the site data JSON explicitly references 3USL for implementation:
> *"implement via UCITS XS2D.L 2x / 3USL.L 3x"* — [`spx_guarded_site_data.json`](spx_guarded_site_data.json:235)

And the patcher overview note references European tickers:
> *"listed 2x/3x ETP daily returns (SPYL/XS2D/3USL) when available"* — [`patch_index_html_backtests.py`](patch_index_html_backtests.py:266)

### 7.3 ETP Return Panel (`spx_etp_returns.json`)

- **Bundle**: S&P 500
- **Tickers**: 1x=SPY, 2x=SSO, 3x=UPRO
- **Model**: `listed_etp_with_synthetic_pre_inception`
- **Coverage**: 66.6% real 2x, 56.6% real 3x
- **Date range**: 1996-06-17 to 2026-06-15 (~7547 trading days)
- **Columns**: `dates`, `ret_0` (cash/T-bill), `ret_1` (1x), `ret_2` (2x), `ret_3` (3x), `vix`
- **Borrow spread model**: VIX-linked: 0.6% base + 30bp/10pts above VIX 15 (cap 2.6%), +20bp at 3x

### 7.4 Browser-Side ETP Usage

[`etp-leverage.js`](etp-leverage.js:50) loads `spx_etp_returns.json` and provides:
- `EtpLeverage.load(url)` — fetches and indexes the JSON
- `EtpLeverage.dailyReturn(leverage, indexRet, cashRate, dateIso)` — returns real ETP return or synthetic fallback
- Synthetic model includes: TER (0.3%/0.6%/0.9% for 1x/2x/3x), VIX-linked funding spread, volatility drag

---

## 8. Gaps — What Would Need to Be Built for a New S&P 500 3x (3USL) Tab

Adding a dedicated 3USL (European 3x S&P 500) tab with full parity to the existing Guarded S&P 500 tab would require:

### 8.1 HTML Structure
- [ ] New `.strategy` container (e.g., `#spx3uslStrategy`) in `index.html` or a new standalone page
- [ ] Three `.page` sub-pages: Signal, Back-test, Monte Carlo
- [ ] Sub-page tab navigation (`<nav>` with `data-page-target` buttons)
- [ ] Register in [`site-nav.js`](site-nav.js:34) `STRATEGY_NAV_ITEMS` array with appropriate group

### 8.2 Data Pipeline
- [ ] New backtest script (or modify `backtest_spx_guarded.py`) to use 3USL calendar-aligned returns
- [ ] **Critical challenge**: 3USL Yahoo daily returns are calendar-offset vs US index. Would need either:
  - A calendar-alignment solution (resampling to US calendar)
  - Accepting synthetic model for daily-timed backtests
  - Using a different data source for 3USL
- [ ] New site data JSON (e.g., `spx_3usl_site_data.json`)
- [ ] New ETP returns JSON (e.g., `spx_3usl_etp_returns.json`)
- [ ] New comparison CSV output
- [ ] Update [`patch_index_html_backtests.py`](patch_index_html_backtests.py) to patch the new sections

### 8.3 Charting
- [ ] Duplicate the three SVG chart elements with new IDs
- [ ] Wire up render functions (can reuse existing `renderChart()` etc. if data structure matches)
- [ ] Range controls for the new charts

### 8.4 Monte Carlo
- [ ] Run new MC with 3USL ETP returns (or synthetic)
- [ ] Store results in new site data JSON
- [ ] Add MC KPI cards and risk probability table

### 8.5 Signals
- [ ] Signal computation can reuse [`computeSignal()`](index.html:1928) — it operates on SPX closes, not ETP-specific
- [ ] Would need separate live quote handling if using European market hours

### 8.6 Sidebar Navigation
- [ ] Add entry in [`site-nav.js`](site-nav.js:34) `STRATEGY_NAV_ITEMS`
- [ ] Decide group placement (likely "Leveraged equity")

### 8.7 Summary Integration
- [ ] If adding to cross-asset comparison, update `summary_data.json` generation

### 8.8 Key Architectural Constraint

The site is **static GitHub Pages** — no server-side computation, no database. All interactivity is client-side JavaScript. The patcher (`patch_index_html_backtests.py`) is a build-time tool run locally to update hardcoded HTML tables before deployment. Any new tab must follow this same pattern: Python backtest → CSV/JSON outputs → patcher updates HTML → deploy static files.

---

## Appendix: Key File Reference

| File | Lines | Role |
|------|-------|------|
| [`index.html`](index.html) | 3,558 | Main dashboard — two strategies, six sub-pages, all charts, signals, calculator |
| [`summary.html`](summary.html) | 295 | Cross-asset comparison — loads `summary_data.json` |
| [`site-nav.js`](site-nav.js) | 642 | Fixed sidebar, hash routing, auto-refresh scheduling |
| [`etp-leverage.js`](etp-leverage.js) | 84 | Browser-side ETP return lookup + synthetic fallback |
| [`patch_index_html_backtests.py`](patch_index_html_backtests.py) | 364 | Build-time HTML patcher — 13 sections updated from CSV/JSON |
| [`backtest_spx_guarded.py`](backtest_spx_guarded.py) | 398 | Primary backtest + MC + site data generation |
| [`backtest_momentum_leverage_strategies.py`](backtest_momentum_leverage_strategies.py) | 326 | 6 daily momentum trigger strategies |
| [`backtest_long_hold_momentum_strategies.py`](backtest_long_hold_momentum_strategies.py) | 393 | 6 long-hold momentum strategies |
| [`etp_leverage.py`](etp_leverage.py) | 360 | Python ETP return panel builder, bundles, MC bootstrap |
| [`data_manager.py`](data_manager.py) | 66 | Market data download (SPX, T-bill, VIX) |
| [`engine.py`](engine.py) | — | Portfolio backtest engine |
| [`strategies.py`](strategies.py) | — | Strategy definitions |
| [`indicators.py`](indicators.py) | — | Technical indicators |
| [`metrics.py`](metrics.py) | — | Performance metrics |
| [`spx_guarded_site_data.json`](spx_guarded_site_data.json) | 261 | Primary site data payload |
| [`spx_etp_returns.json`](spx_etp_returns.json) | 1 (large) | ETP daily return panel |
