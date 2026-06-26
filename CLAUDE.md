# CLAUDE.md

This repo is an **AI-run factory** (edited entirely by AI agents in fresh sessions).

**Read [AGENTS.md](AGENTS.md) first, then [docs/runbooks/START-HERE.md](docs/runbooks/START-HERE.md).**

- Coding standards: [docs/coding-standards.md](docs/coding-standards.md) (anti-look-ahead, ≥10 bps friction, VIX borrow, vectorized).
- Before downloading data or running a backtest, check [catalog/data.md](catalog/data.md) /
  [catalog/experiments.md](catalog/experiments.md) — **don't duplicate work**.
- Multiple agents + a cron write here; don't clash — see [docs/runbooks/coordination.md](docs/runbooks/coordination.md).
- `HANDOVER.md`, if present, is a **transient** per-session note — not the guide.
- Don't read `archive/roohistory.md` (~18k lines) unless you genuinely need deep history.
