# Strategy Lab — reproducible backtests & adding new strategies

**Read this before testing any new strategy or reproducing an old backtest.** It exists
so that every number you generate is on the *same basis* as every number already in
`Results/strategy_results.xlsx` and on the website — comparable, reproducible, and
date-consistent. Harness: [`research/strategy_lab/`](../research/strategy_lab/).

## ⛔ The Golden Rule of Consistency

> **Every backtest in the Excel + website uses the canonical loader**
> `sweep_all_assets_strategies.load_asset_data(asset, tbill, vix)` **+** `run_one_backtest()`.
> **Never** use `backtest_*.download_*` (e.g. `download_spx_panel`) for a strategy you
> want to compare to existing results.

Why: `download_spx_panel` pulls a *different yfinance auto-adjust vintage* and gives
**SPX B&H 1x CAGR ≈ 9.3% / DD −56.7%**, whereas the canonical loader (and therefore the
whole workbook) gives **≈ 9.99% / −55.1%**. Same engine, same dates — different data
vintage = non-comparable. This bit us once; the harness now always uses the canonical loader.

A quick self-check any script can run: the plain `SMA200 ±3% Band 1x/cash` must reproduce
the value in `output/strategy_results/<asset>_results.csv` to the cent. `strategy_lab._basis_check()`
does exactly this.

## The canonical basis (one source of truth)

| Knob | Value | Where |
|------|-------|-------|
| Data loader | `load_asset_data(asset, tbill, vix)` → column `spx_close` (generic index close for ALL assets) | `sweep_all_assets_strategies.py` |
| Engine | `PortfolioEngine(max_drawdown_limit=None, hard_drawdown_floor=False, annual_inflow_abs=10.0, trading_cost_pct=cost, signal_delay_days=1)` | `core/engine.py` |
| Cost | per-asset (SPX/NDX 0.10%, others 0.15–0.20%) from mid on each leverage change | `ASSETS[asset]["trading_cost"]` |
| Leverage returns | real ETP returns (SPY/SSO/UPRO, QQQ/QLD/TQQQ…) via the ETP panel; **1x also uses `ret_1` = index − TER** | `build_asset_etp_panel` |
| Inflow | $100 base + $10/yr absolute | engine |
| Signal lag | 1 day (close[T] → fills T+1) | engine |
| Window | full history per asset (SPX 1950+, NDX 1985+) | loader |
| Classification | vs a freshly-computed **B&H 1x**; Water / Octane / Stillwater | `build_strategy_results_excel.classify_strategy` / `classify_stillwater` |

The fast numpy replica `research/strategy_lab/fast_engine.py` reproduces this engine to the
penny (validated for SPX **and** NDX) — use it for big screens; use `run_one_backtest`
(via `strategy_lab.run`) for anything you will report.

## Workflow A — test a new strategy (nothing written)

```python
# from research/strategy_lab on the path, repo root as cwd
import strategy_lab as lab, signals as S
from core.indicators import sma as sma_ind
prices, panel, cfg = lab.load("spx")
close = prices["spx_close"].to_numpy(float); sma200 = sma_ind(prices["spx_close"], 200).to_numpy(float)
sig = S.variant_b_accel(close, sma200, 0.03, "conv", 10, 0.02, 0.03)   # your 0/1 signal
lab.quicktest("spx", "my new rule", sig, leverage=1.0)
# -> prints CAGR/Sharpe/Calmar/MaxDD + B&H 1x + classification (Water/Octane/Stillwater)
```
New signal shapes go in `research/strategy_lab/signals.py` (each returns a 0/1 numpy
array on `prices["spx_close"]`). Existing: conventional & early-in/out bands, fixed &
trailing stops, variant-B decay/accelerate exits, variant-C RSI/MACD entries.

## Workflow B — reproduce an OLD backtest with NEW dates

`lab.load(asset)` always fetches **current** data, so re-running gives today's numbers
(the strategy on a longer window). To compare against a *frozen* result, align the window:

```python
prices, panel, cfg = lab.load("spx", end_date="2026-06-24")   # the CSV's End_Date
```
With the window matched, the plain band 1x reproduces the frozen CSV to the cent, so your
new strategy sits on the *identical* basis as the frozen incumbents.

## Workflow C — add a winner to the Excel tabs

`lab.add_strategies` rebuilds **only** the asset's Water/Octane(/Stillwater) tabs from the
179-strategy source CSV (the frozen source of the existing tabs) + your new strategies,
recomputed on the CSV's window. Every incumbent row and every other asset's tab is left
untouched.

```python
import strategy_lab as lab, signals as S
from core.indicators import sma as sma_ind
def accel(prices, cfg):
    close = prices["spx_close"].to_numpy(float)
    sma200 = sma_ind(prices["spx_close"], 200).to_numpy(float)
    return S.variant_b_accel(close, sma200, 0.03, "conv", 10, 0.02, 0.03)
lab.add_strategies("spx", [("SMA200 +-3% Band + Accel-Exit N10 1x/cash", accel, 1.0)])
```

## Workflow D — push a new winner to the website

1. Add it to the per-asset CSV + `all_assets_combined.csv` (so the Summary page sees it).
2. Flip the pick in `build_summary_excel_json.SITE_DEFAULTS` (and `core/site_default_strategy.py`
   if it should become an asset page's rendered default) → `python build_summary_excel_json.py`.
3. New signal *family* on a page renderer? add a `kind` to `core/site_default_strategy.py`
   AND mirror it in `strategy_page.js` (live signal + manual-price recompute).
4. Regenerate the page's `*_site_data.json`, then **deploy via [`deploy.md`](deploy.md)** and `curl` the live `?v=`.

## The full multi-strategy sweep

`research/spx_band_variant_sweep/` (SPX) and the NDX equivalent screen ~4,800 A/B/C
variants through `fast_engine` and report only winners. Use them as templates for new
hypotheses; they already obey the Golden Rule (canonical loader).
