# archive/

Research and one-off analysis files that are **not used by the live website**.
Moved here to keep the repo root focused on the files that actually build and
serve the site. Nothing in this folder is imported, run, or fetched by:

- the deployed pages (`index.html`, `summary.html`, the `*_guarded.html` asset
  pages, `instruments.html`, `live_guarded_sma20_leverage.html`) or their JS/JSON/CSV;
- the GitHub Actions pipeline (`update_static_market_data.py`,
  `refresh_holdings_prices.py`);
- the site-data regenerators kept at the repo root
  (`regenerate_website_leveraged_backtests.py` and the backtest / build /
  Monte-Carlo / patch scripts it drives).

This was verified mechanically: every file moved here is **tracked in git**, has
**zero importers** anywhere in the repo (so moving it can't break tracked or
in-flight scripts), and its name is **not referenced by any website-maintenance
script**.

## Contents

- `research_scripts/` — exploratory `analyze_* / optimize_* / sweep_* /
  forward_test_* / test_*` scripts and the old `main.py` CLI. Standalone
  experiments; none feed the site.
- `output/` — result CSVs / JSON / PDFs from those experiments (parameter
  sweeps, fundamental-overlay tests, drawdown studies, strategy tear-sheets,
  etc.). The `output/` dirs the live pipeline still reads/writes were **left in
  place** at the repo root `output/`.
- `equity_comparison.pdf` — a one-off comparison chart.

## Re-running an archived script

These scripts `import engine`, `metrics`, etc. from the repo root. To run one
again, invoke it from the repo root with the root on the path, e.g.:

```
python -m archive.research_scripts.optimize_macd      # or
PYTHONPATH=. python archive/research_scripts/optimize_macd.py
```

## Deliberately left at the root (not archived)

- Shared research libraries still imported by other scripts: `indicators.py`,
  `strategies.py`, `reporting.py`, `data_three_asset.py`, `sweep_sma_periods.py`,
  and several `analyze_*` modules imported by others.
- **Untracked / in-flight** research files (a concurrent editor is actively
  creating these) — left untouched so as not to disrupt that work.
- `scratch/` — kept as-is; it also holds `build_summary_data.py`, which
  generates the served `summary_data.json`.
