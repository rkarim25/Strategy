# Strategy Lab

Reusable harness for testing new strategies and adding winners to the workbook on the
**canonical, reproducible basis**. Full guide: [`docs/strategy-lab.md`](../../docs/strategy-lab.md).

| File | What |
|------|------|
| `strategy_lab.py` | the harness: `load(asset[, end_date])`, `quicktest(...)`, `add_strategies(...)`, classification, basis self-check |
| `signals.py` | 0/1 signal builders: conventional & early-in/out bands, fixed/trailing stops, variant-B decay/accelerate exits, variant-C RSI/MACD entries |
| `fast_engine.py` | numpy replica of `core.engine` (validated to the penny for SPX **and** NDX) — for big screens; reported numbers go through `run_one_backtest` |

```bash
# from repo root
PYTHONPATH="$PWD;research/strategy_lab" python research/strategy_lab/strategy_lab.py   # demo: SPX Accel-Exit winner
```

**Golden Rule:** always use the canonical `load_asset_data` loader (this harness does).
Never `download_spx_panel` for anything you'll compare to existing results — different
data vintage, non-comparable. See the doc.
