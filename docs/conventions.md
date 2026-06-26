# Conventions & where new things go

This is the **future-proofing** doc: follow it and the repo won't rot back into a flat pile at root.
The single most important rule: **the root is for production (website + data + imported engine modules) and
established research scripts only. Everything new and throwaway goes in a folder.**

## Naming conventions

| Pattern | Meaning |
|---------|---------|
| `{slug}_daily.csv` | Historical daily prices (slugs: `spx`, `ndx`, `gold`, `ftse250`, `dax`, `msci_em`, `msci_world`, `lqq3`, `3bal`) |
| `{slug}_guarded.html` / `.js` | Per-asset website page + client signal |
| `{slug}_guarded_site_data.json` | Pre-computed backtest metrics for charts |
| `latest_{slug}_signal.json` | Current signal metadata |
| `{slug}_etp_returns.json` | ETP daily return series for browser backtests |
| `analyze_*.py` | Research/analysis (output → `output/<name>/`) |
| `backtest_*.py` | Single strategy/asset backtest |
| `sweep_*.py` | Parameter sweep |
| `build_*.py` | Output generator (JSON/HTML/Excel) |
| `verify_*.py` / `validate_*.py` | Consistency/sanity checks |

## Decision table — "I'm adding X, where does it go?"

| You're adding… | Put it in… |
|----------------|-----------|
| **Downloading market data** | **STOP** — check `catalog/data.md` first; then follow `docs/runbooks/add-data-source.md`; register with `python tools/build_catalog.py` |
| **Running a backtest** | **STOP** — check `catalog/experiments.md` first; then `docs/runbooks/run-backtest.md`; outputs → `output/<id>/`; register with `python tools/build_catalog.py` |
| A throwaway / one-off / debug script | `scratch/` (prefix `_` or `debug_`) — **never root** |
| A new reusable strategy | `strategies.py` (extend `LeverageStrategy`) |
| A new asset's guarded page | `guarded_asset_registry.py` + run `build_guarded_asset_pages.py` |
| A committed research/backtest script | root with the right prefix (`analyze_/backtest_/sweep_`) — keep it lean |
| Generated CSV/data from an analysis | `output/<analysis-name>/` |
| A new/updated Excel workbook | `Results/` (backups → `Results/backups/`, suffix `_backup_<YYYYMMDD>`) |
| A design/plan doc | `plans/` |
| Project documentation for AIs | `docs/` (and add it to the index in `AGENTS.md`) |
| A finished session handover worth keeping | `docs/session-notes/<YYYY-MM-DD>-<topic>.md` |
| A new Cloudflare Worker | `workers/<worker-name>/` |
| Anything you'd otherwise `.gitignore` | confirm it matches `.gitignore`; add a pattern if not |

## Reserved expansion areas (use these instead of inventing new top-level folders)

- **`scratch/`** — all experimentation. Logs are gitignored (`*.log`); other files stay untracked.
- **`output/<name>/`** — every analysis gets its own subdir; don't dump results at root.
- **`docs/`** — every new doc; split a big topic into its own page rather than bloating an existing one.
- **`docs/session-notes/`** — historical handovers (the durable guide stays in `AGENTS.md` + `docs/`).
- **`tests/`** *(create when needed)* — if/when formal `pytest` suites arrive, collect them here so the
  `test_*.py` strategy libs at root stay distinguishable from real tests.
- **`research/`** *(optional future migration)* — if root research scripts ever need to leave root, move them
  here **in one coordinated pass** and update imports (`test_tiered_dd_recovery_guarded`,
  `test_guarded_balanced_candidate`, `analyze_cross_asset_guarded_1x`, `analyze_multi_asset_guarded_scan`,
  `backtest_lqq3_guarded`, `backtest_spx_guarded`, `backtest_ndx_guarded` are the imported ones). Not done yet
  because the flat import web + the concurrent agent make a piecemeal move risky.

## Anti-rot rules

1. **Never put a one-off script at root** — it goes in `scratch/`. Root research scripts should be ones you'd
   re-run or import.
2. **Keep `AGENTS.md` current** — when you add a doc, change a golden rule, or fix a known-drift item, update it.
3. **Don't commit cron/agent churn** (`*_daily.csv`, `latest_*_signal.json`, `holdings_*.json`) as part of a
   feature commit.
4. **One source of truth** — project facts live in `docs/`; don't fork them into ad-hoc root markdown.
5. **Two docs that must track code:** the Excel **Definitions** sheet (classification) and the per-asset trading
   costs in both `sweep_all_assets_strategies.py` and `build_strategy_results_excel.py`.
6. **`HANDOVER.md` at root is transient** (the handover skill rewrites it). The durable guide is `AGENTS.md`.
