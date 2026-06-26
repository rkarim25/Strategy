# START HERE — every AI session, every time

You are **one worker in a multi-AI factory**. The human only reads results + the website; everything
underneath is yours (and other agents') to maintain. Follow these steps **in order**. Don't skip.

## 0. Orient (≈2 min — do not read source code yet)
1. Read [`../../AGENTS.md`](../../AGENTS.md) — golden rules + repo map.
2. Read this file.
3. Open **only** the one `docs/` page for your task (the index is in `AGENTS.md`).

## 1. Sync (don't clash with the cron + other agents)
```bash
git fetch origin
git log -1 --oneline origin/main        # someone (or the cron) may have pushed
git reset --mixed origin/main           # if behind: resync, keeps your uncommitted work
```

## 2. Before creating work, CHECK what already exists (don't duplicate)
- **Need market data?** → open [`../../catalog/data.md`](../../catalog/data.md). If your asset + date range
  is there, **DO NOT download** — load the CSV.
- **Running a backtest?** → open [`../../catalog/experiments.md`](../../catalog/experiments.md) and
  `Results/strategy_results.xlsx`. If it exists, build on it / re-check it — don't re-run from scratch.
- Catalogs look stale? → `python tools/build_catalog.py`.

## 3. Claim big work (don't let two agents do the same thing)
For anything substantial, long, or touching shared files, drop a claim file (see
[`coordination.md`](coordination.md)). Skip for tiny edits.

## 4. Do the work — follow the matching runbook
- [`add-data-source.md`](add-data-source.md) · [`run-backtest.md`](run-backtest.md) ·
  [`add-website-feature.md`](add-website-feature.md)
- Obey [`../coding-standards.md`](../coding-standards.md) (anti-look-ahead, ≥10 bps cost, vectorized).
- **One experiment = one `output/<id>/` directory.**

## 5. Register + commit + deploy
- Re-run `python tools/build_catalog.py` so the catalogs include your work.
- Commit **explicit** files (never `git add .`). Deploy via [`../deploy.md`](../deploy.md) (worktree).
- Verify the live site still works (`curl` the URL).

## 6. Leave it clean
- Update the "Current health / known drift" section in `AGENTS.md` if something changed.
- Delete your claim file.

> Golden rule recap: don't move website/data/core-engine files; don't `git add .`; don't commit cron churn;
> don't re-download or re-build what the catalogs already list.
