# Session Handover — S&P Octane page + Summary page rebuild

> Transient session note (NOT the permanent project guide in `HANDOVER.md`). Created 2026-06-26.

## Metadata
- **Date:** 2026-06-26
- **Repo:** `C:\Users\Reza Karim\OneDrive\Systematic_Backstester` → GitHub `rkarim25/Strategy` (GitHub Pages site)
- **Live site:** https://rkarim25.github.io/Strategy/
- **Branch / HEAD:** `main @ 9ce833c` — **== origin/main, already deployed live**
- **OneDrive note:** `.git` and the open Excel get locked by OneDrive; deploys go through an **isolated git worktree** (see below), not a plain push from the repo dir.

## Goal — ✅ COMPLETE & DEPLOYED
Two independent pieces, both built, verified in the local preview, deployed, and confirmed on the live site:
1. **S&P 500 page** (`index.html`) now features the real Excel **Octane** strategy **`SMA200 ±3% Band + RSI>20 Exit 2x`** (replacing the non-Octane "Distance Scale 1-3x"), with regenerated backtest, Monte Carlo, and full-history charts.
2. **Summary page** (`summary.html`) rebuilt from the Excel results as an **overview table + per-asset drill-down** (was a Balance-score view).

## What shipped — commit `9ce833c` (exactly 6 files)
`index.html`, `site-nav.js`, `summary.html`, `summary_excel.json`, `spx_distance_scale_site_data.json`, `spx_distance_scale_etp_returns.json`.

**Verified live (curl against the deployed Pages site):**
- S&P page heading "RSI>20 Exit 2x Signal" + rule "Fixed 2x leverage".
- `spx_distance_scale_site_data.json`: strategy `SMA200 ±3% Band + RSI>20 Exit 2x`, **CAGR 13.59% / MaxDD −41.53% / Calmar 0.33 / Sharpe 0.493**, sample since **1950-01-03** — matches the Excel (13.31% / −41.52% / 0.32; MaxDD essentially exact).
- `summary_excel.json`: 10 assets, S&P **11 Octane / 11 Water**, best Octane = the new strategy. 40 Octane / 23 Water total.
- Deploy run `28202263233` (deploy-pages.yml) = success.

## The strategy (exact logic — already implemented in both Python and JS)
- **2×** when close > SMA200 × 1.03 (upper band).
- **Cash** when close < SMA200 × 0.97 (lower band) **AND** RSI(14) ≥ 20.
- **Stay 2×** when the band says cash but **RSI(14) < 20** (don't sell into an oversold panic — `rsi_exit_filter_on_series` blocks the exit, never enters on RSI).
- Hysteresis between the bands (hold prior state).

## Key implementation points (where things live, if revisiting)
- **`backtest_spx_distance_scale.py`** (UNTRACKED local build tool) regenerates `spx_distance_scale_site_data.json` + `spx_distance_scale_etp_returns.json`. `DEFAULT_SPEC` = the band+RSI 2x strategy; downloads `^GSPC` alone from 1950-01-03 then reindexes `^IRX`/`^VIX` (ffill + defaults) so history starts 1950 not 1960; passes `risk_free=avg_tbill` to all 4 `comprehensive_stats` calls; has `_json_safe()` sanitizing NaN/Inf→null before `json.dumps(..., allow_nan=False)`.
- **`index.html`**: `bandRsiLeverageSeries(rows, params)` helper drives both the live signal (`computeSignal`) and charts (`distanceScaleLeverageForParams`); `DEFAULT_DISTANCE_SCALE` = `{smaWindow:200, bandPct:0.03, rsiWindow:14, rsiExit:20, leverage:2, tradingCost:0.001, cashRate:0.04}`. Back-test equity chart + top-drawdowns read `staticSiteData.equity_curve` via `backtestEquityFullData()`/`sliceEquityByRange()` so they span 1950+. (The S&P **3x** tab was left untouched.)
- **`summary.html`**: fetches `summary_excel.json`; sortable overview table (`OVERVIEW_COLS`) + collapsible per-asset cards with Water/Octane tables (`DETAIL_COLS`) + Nasdaq Stillwater + Definitions card. Reuses the site CSS shell and `site-nav.js`.
- **`build_summary_excel_json.py`** (NEW, untracked) generates `summary_excel.json` from `output/strategy_results/all_assets_combined.csv`, importing `classify_all`/`classify_stillwater`/`is_bh_row`/`load_all_data` from `build_strategy_results_excel.py`.

## Failed approaches / gotchas (don't repeat)
- **Blank S&P page** earlier was a JS syntax error (orphaned `resetCalculator` body left a stray `}`), already fixed — NOT a missing addEventListener.
- **Backtest started at 1960** when downloading `[^GSPC,^IRX,^VIX]` together + `dropna(subset=["tbill_rate"])` — fixed by downloading `^GSPC` alone and reindexing the aux series.
- **Sharpe was wrong** (0.65 vs 0.48) until `risk_free=` was passed to `comprehensive_stats`.
- **Page showed stale hardcoded KPIs** because `json.dumps` wrote `NaN` (invalid JSON) → browser `JSON.parse` threw → `staticSiteData=null`. Sanitize NaN→null.
- **Over-push (21 files)** happened once because `git checkout <ref> -- ...` left files STAGED and `git commit` swept them. **Always `git add` the explicit file list**, never `git add .`, and check `git diff --cached --name-only` is empty/correct before committing.

## Deploy procedure (the working method)
```
# in C:/Users/Reza Karim/OneDrive/Systematic_Backstester (Git Bash)
git add <explicit files>; git commit -m "..."          # commit ONLY intended files
MYSHA=$(git rev-parse HEAD); git fetch origin -q
WT="C:/Users/Reza Karim/_dwtN"; git worktree add --detach "$WT" origin/main
git -C "$WT" cherry-pick "$MYSHA"
git -C "$WT" push origin HEAD:main
gh workflow run deploy-pages.yml --ref main            # then verify live with curl
git reset --mixed origin/main                          # resync local, keep uncommitted work
```
(The `.git/worktrees/_strat_deploy_wt*` "Permission denied" prune errors are harmless OneDrive locks. Use a fresh worktree name each time.)

## Uncommitted changes (LOCAL ONLY — intentionally NOT in the deploy)
The 6 served files are committed. Still local in the working tree:
- **`build_strategy_results_excel.py`** (M) — Stillwater additions (`classify_stillwater`, `build_stillwater_sheet`, `STILLWATER_CAGR_TOL=2.0`, removed default `Sheet` tab).
- **`Results/strategy_results.xlsx`** (M) — the workbook with the expanded S&P Water/Octane + the Nasdaq **Stillwater** sheet.
- **`output/strategy_results/all_assets_combined.csv`** (M) + per-asset `*_results.csv` — the expanded sweep data feeding both the Excel and `summary_excel.json`.
- **`backtest_spx_distance_scale.py`**, **`build_summary_excel_json.py`** (??) — the two build/generator scripts above.
- **`sweep_comprehensive_spx_ndx.py`** (??) — adds the C21 "lever-up" families to `build_strategies()`.
- Plenty of other noise in `git status` (refreshed `*_daily.csv`, `latest_*_signal.json`, `scratch/`, `debug_*.py`) is the **concurrent Cursor agent / cron refresh**, not this task's work — leave it alone.

## Next steps — OPTIONAL (task is functionally done; do only if the user asks)
1. **Commit the build scripts + Stillwater Excel work** as a separate commit if the user wants reproducibility on origin: `build_strategy_results_excel.py`, `build_summary_excel_json.py`, `backtest_spx_distance_scale.py`, `sweep_comprehensive_spx_ndx.py`, `Results/strategy_results.xlsx`, `output/strategy_results/all_assets_combined.csv` (+ the per-asset CSVs). Use the explicit-add + worktree deploy above. (User was asked; awaiting a yes.)
2. **Trim the 5 MB `spx_distance_scale_site_data.json`** (it carries the full 1950+ daily `signal_history`) to ~2 MB if first-load speed matters — drop/sparsify `signal_history`, regenerate via `backtest_spx_distance_scale.py`, redeploy. (User was offered this.)
3. The live site's nav label / JSON need a **hard refresh** (Ctrl+Shift+R) to show on a browser that cached the old version.

## Verify on resume
```
git -C "C:/Users/Reza Karim/OneDrive/Systematic_Backstester" log --oneline -1   # expect 9ce833c
curl -s "https://rkarim25.github.io/Strategy/spx_distance_scale_site_data.json" | python -c "import sys,json;d=json.load(sys.stdin);b=d['default_backtest'];print(b['strategy'],b['cagr_pct'],b['max_drawdown_pct'])"
# expect: SMA200 ±3% Band + RSI>20 Exit 2x  13.59%  -41.53%
```
