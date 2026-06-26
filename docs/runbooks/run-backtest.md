# Runbook: run a backtest (without duplicating work)

## STOP — check first
1. Open [`../../catalog/experiments.md`](../../catalog/experiments.md), `Results/strategy_results.xlsx`,
   and `output/strategy_results/all_assets_combined.csv`. **Has this strategy × asset already been tested?**
   → reuse / re-check the existing result; don't re-run from scratch.
2. Need data? → [`../../catalog/data.md`](../../catalog/data.md) first (don't re-download).

## Run it
3. **Reuse the engine** — import `engine.py` (`PortfolioEngine`), `strategies.py`, `metrics.py`,
   `etp_leverage.py`. **Never write a new backtest engine or re-implement metrics.** Add a new strategy by
   extending `strategies.py`.
4. Obey [`../coding-standards.md`](../coding-standards.md): 1-day signal lag, ≥10 bps cost, VIX borrow, vectorized.
5. Write **all** outputs to `output/<your-experiment-id>/` — one directory per experiment, so parallel agents
   never collide.
6. To extend the **master grid**, add to the sweep (`sweep_all_assets_strategies.py` /
   `sweep_comprehensive_spx_ndx.py`), then:
   ```bash
   python sweep_all_assets_strategies.py       # -> output/strategy_results/*.csv
   python build_strategy_results_excel.py      # -> Results/strategy_results.xlsx
   ```
7. **Register it:** `python tools/build_catalog.py` (adds your output dir to `catalog/experiments.md`).
8. Commit **explicit** files. Deploy only if it changes data the site serves ([`../deploy.md`](../deploy.md)).

## Don't
- Don't rebuild the engine or re-implement `metrics` / `etp_leverage`.
- Don't dump outputs at repo root or inside another experiment's directory.
- Put exploratory scripts in `research/` (run from repo root); only pipeline generators that write site data stay at root.
- Don't blindly re-run a page builder and commit it (it can regress hand-hydrated tables — see
  [`add-website-feature.md`](add-website-feature.md)).
