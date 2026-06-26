# Coding standards

Mandatory for **all** code in this repo, written by **any** AI agent. (Migrated from the old
Cursor-specific `.cursorrules`; this repo is now edited by many different AIs.)

## Mindset
Write like a disciplined institutional quantitative developer: every backtest must reflect real-world
market friction and eliminate statistical biases. No shortcuts that would flatter a result.

## Hard rules (quant correctness)
- **Anti-look-ahead:** signals/indicators are strictly out-of-sample and lagged. A signal computed from data
  up to bar T may only execute/fill at bar T+1. Apply `.shift(1)` when computing entry/exit vectors.
- **Market friction:** every backtest models transaction costs — minimum **10 bps (0.0010) per trade** from
  the mid-price on each leverage change. Per-asset costs are in `docs/backtesting.md`.
- **Borrow & financing:** leveraged/short exposure incorporates the VIX-linked annual borrow cost into the
  daily returns accounting (see `engine.py`).
- **Vectorization:** never iterate a time series with Python `for` loops or `.iterrows()`. Use vectorized
  NumPy/Pandas (rolling windows, `.shift`, boolean masks).
- **Completion & hygiene:** no placeholder functions, truncated blocks, or `# TODO`s. Every script is fully
  implemented, syntactically complete, with explicit type hints.

## Repo rules (don't fight the factory)
- **Don't move** website / data / core-engine files — see the golden rules in [`../AGENTS.md`](../AGENTS.md).
- **Reuse, don't rebuild:** import from the `core/` package — `from core import engine, metrics, etp_leverage, indicators, strategies`. Never
  re-implement the backtest engine or the metrics — extend them.
- **Don't re-download or re-run:** check `catalog/data.md` before pulling data and `catalog/experiments.md`
  before running a backtest. Register new work afterwards (`python tools/build_catalog.py`).
- **One experiment → one `output/<id>/` directory**, so parallel agents never collide.
- **Git discipline:** explicit `git add` (never `git add .`), deploy via the worktree procedure
  (`docs/deploy.md`), and never commit the cron data churn. Full protocol: `docs/runbooks/coordination.md`.
