# Architecture

How the engine and the data pipeline fit together. For the website side see [`website.md`](website.md);
for parameters/regeneration see [`backtesting.md`](backtesting.md).

## Two halves

1. **Python backtesting engine** (local) — runs historical simulations, computes metrics, emits JSON/CSV/Excel.
2. **Static website** (GitHub Pages) — displays live signals, charts, Monte Carlo, cross-asset comparison.

## Core Python modules (root)

These are imported widely — **moving any of them breaks dozens of scripts.** Import counts (approx) show how load-bearing they are.

| Module | Role | ~importers |
|--------|------|-----------|
| `engine.py` | `PortfolioEngine`: day-by-day sim with 1-day signal delay (no look-ahead), VIX-linked borrow costs, trading costs, annual inflow, optional DD floor | 48 |
| `metrics.py` | `comprehensive_stats()`: CAGR, MaxDD, Sharpe, Sortino, Calmar, win rate, beta, alpha, skew, kurtosis | 51 |
| `etp_leverage.py` | Models real listed ETP returns (SPY/SSO/UPRO, QQQ/QLD/TQQQ) with synthetic daily-reset fills pre-inception | 36 |
| `data_manager.py` | Downloads `^GSPC`, `^IRX`, `^VIX` from Yahoo (yfinance) → CSV | 18 |
| `indicators.py` | Pure-Pandas SMA, EMA, RSI, MACD, Bollinger, drawdown | 12 |
| `price_cleaning.py` | Shared round-trip spike filter (kept in parity with the cron `clean_price_spikes`) | 8 |
| `strategies.py` | Abstract `LeverageStrategy` + 10+ built-ins (SMA200, Golden Cross, MACD, RSI, Bollinger, DD Recovery, DD Scaling) | — |
| `guarded_asset_registry.py` | Per-asset metadata (slug, title, ticker, lev cap, history start) for the 5 template-driven guarded pages | — |
| `reporting.py` | Report/output helpers | — |
| `data_three_asset.py` | Data assembly for the 3-asset balanced sleeve | — |

**Strategy implementation libs** (imported as libraries despite the `test_` prefix — **do not treat as throwaway tests**):

| Module | Role | ~importers |
|--------|------|-----------|
| `test_tiered_dd_recovery_guarded.py` | The tiered DD-recovery Guarded strategy implementation | 40 |
| `test_guarded_balanced_candidate.py` | `guarded_strategy_leverage` — the primary Guarded A5/B25 logic | 14 |

## Data pipeline

```
Yahoo Finance (yfinance)
   └─ data_manager.py / cron ─> {slug}_daily.csv          (root, ~30y or full history)
                                    │
                 sweep_all_assets_strategies.py
                                    │
                 output/strategy_results/{slug}_results.csv + all_assets_combined.csv
                       │                                   │
       build_strategy_results_excel.py            build_summary_excel_json.py
                       │                                   │
            Results/strategy_results.xlsx          summary_excel.json (root)
                       
   per-asset backtests ─> {slug}_guarded_site_data.json,  latest_{slug}_signal.json,
                          {slug}_etp_returns.json          (root, read by the website)
```

## Two result pipelines (keep them straight)

| | Excel pipeline | Website summary pipeline |
|---|---|---|
| Output | `Results/strategy_results.xlsx` | `summary_excel.json` (current) / older `summary_data.json` |
| History | Full (76y for SPX) | Shorter "real ETP" window |
| Costs | Per-asset (see [`backtesting.md`](backtesting.md)) | 3 levels (0% / 0.10% / 1%) |
| Classification | Water / Octane / Stillwater | Balance-score ranking (older view) |
| Builder | `sweep_all_assets_strategies.py` → `build_strategy_results_excel.py` | `build_summary_excel_json.py` (current `summary.html`) |

Both are correct within their own assumptions; a change to one does not affect the other.

## Dependencies

- **Python:** yfinance, pandas, numpy, openpyxl, scipy (`requirements.txt`).
- **Website:** vanilla JS + Canvas (no framework).
- **Infra:** GitHub Pages (static hosting), Cloudflare Workers (live-price proxy).
