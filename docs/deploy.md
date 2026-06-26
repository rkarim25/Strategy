# Deploy & git workflow

**Read this before you commit or push anything.** This repo lives in OneDrive and is shared with a concurrent
agent + cron jobs, so the safe procedure is non-obvious.

## Why it's special

- **OneDrive locks `.git` and any open Excel** → a plain `git push` from the repo dir can fail or race.
- **A second Cursor agent + GitHub Actions cron also push to `main`** → `origin/main` moves under you.
- The fix: commit locally, then **deploy through a throwaway detached worktree** built from fresh `origin/main`.

## The deploy procedure (the working method)

```bash
cd "C:/Users/Reza Karim/OneDrive/Systematic_Backstester"     # Git Bash

# 1) Commit ONLY the intended files (NEVER `git add .`)
git add <explicit file list>
git diff --cached --name-only          # confirm this is exactly what you mean to ship
git commit -m "..."

# 2) Cherry-pick onto fresh origin/main in an isolated worktree
MYSHA=$(git rev-parse HEAD)
git fetch origin -q
WT="C:/Users/Reza Karim/_dwtN"         # use a FRESH name each time (_dwt1, _dwt2, …)
git worktree add --detach "$WT" origin/main
git -C "$WT" cherry-pick "$MYSHA"
git -C "$WT" push origin HEAD:main

# 3) Trigger the Pages build, then verify live (see below)
gh workflow run deploy-pages.yml --ref main

# 4) Resync local to the new origin/main, keeping your uncommitted work
git reset --mixed origin/main
```

- The `.git/worktrees/_strat_deploy_wt*` **"Permission denied" prune errors are harmless** OneDrive locks.
- Always use a fresh worktree name to dodge stale locked dirs.

## Verify live (don't trust the push — check the deployed site)

```bash
git log --oneline -1                     # your feature commit is the latest local
curl -s "https://rkarim25.github.io/Strategy/spx_distance_scale_site_data.json" \
  | python -c "import sys,json;d=json.load(sys.stdin);b=d['default_backtest'];print(b['strategy'],b['cagr_pct'],b['max_drawdown_pct'])"
gh run list --workflow deploy-pages.yml -L 1     # confirm the deploy run succeeded
```

## ⚠️ Hard-won gotchas

- **Never `git add .` / `-A`.** A `git checkout <ref> -- …` can leave files STAGED that a later `git commit`
  then sweeps in — once shipped 21 files by accident. Stage explicitly; check `git diff --cached`.
- **Don't bundle the cron refresh.** `*_daily.csv`, `latest_*_signal.json`, `holdings_*.json`, `news_score.json`
  churn constantly from the concurrent agent/cron — keep them out of your commits.
- **Committed website pages are hand-hydrated snapshots.** Re-running a page builder can regress static
  Legacy/OOS tables. `build_ndx` fails *silently* and is currently drifted; `build_gold` fails *loud*. Diff first.
- **Invalid JSON breaks pages silently** (NaN/Inf → `JSON.parse` throws → blank/stale page). Dump with
  `allow_nan=False` and sanitize NaN/Inf → null.

## GitHub Actions (`.github/workflows/`)

| Workflow | What it does |
|----------|--------------|
| `deploy-pages.yml` | Builds & deploys the GitHub Pages site from `main` |
| `update-market-data.yml` | Cron: runs `update_static_market_data.py` + `refresh_holdings_prices.py`, rewrites `*_daily.csv` / `latest_*_signal.json` / `holdings_*.json` and pushes |

`refresh_holdings_prices.py` is **also consumed cross-repo** by the holdings repo's `update-prices.yml` — don't delete or relocate it.
