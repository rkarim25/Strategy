# Coordination — how multiple agents avoid clashing

Writers to this repo at any moment: **(a)** you, **(b)** other AI sessions, **(c)** the GitHub Actions cron
(`update-market-data.yml`, which rewrites `*_daily.csv` + `latest_*_signal.json`). Assume concurrency always.

## The 6 rules

1. **Sync first.** `git fetch origin` before you start and again before you push — `origin/main` moves under you.
2. **Ownership zones — who edits what:**
   | Zone | Owner | Rule |
   |------|-------|------|
   | Data refresh (`*_daily.csv`, `latest_*_signal.json`, `holdings_*.json`) | the cron | **never hand-edit**; never commit its churn |
   | Website files (root `*.html` / `*.js`) | one agent at a time | claim before editing |
   | Core engine (`engine`/`metrics`/`etp_leverage`/`strategies`/`indicators`) | careful — wide blast radius | claim before editing |
   | Experiments (`output/<id>/`) | whoever runs it | isolated — one dir each, never collide |
3. **Never `git add .`** — stage explicit files, check `git diff --cached --name-only`.
4. **Never commit cron churn** inside a feature commit (see zones).
5. **Deploy via the worktree procedure** ([`../deploy.md`](../deploy.md)) — it isolates the push.
6. **Claim big / long / shared work:**
   - Create `.claims/<YYYYMMDD-HHMM>-<short-task>.md` — one line: who you are, what you're doing, which files.
   - **Delete it when done.** Treat claims older than ~24h as stale.
   - `.claims/` is gitignored (local coordination for agents sharing this working copy).
   - Before editing a shared file, check `.claims/` for an active claim on it.

## If two agents clash anyway
The push is rejected (non-fast-forward). Re-`fetch`, re-cherry-pick your commit onto the new `origin/main`,
re-verify, push again. **Never force-push `main`.**

## Why this is enough
Most clashes are prevented structurally: the cron owns data, experiments are isolated per-directory, and the
worktree deploy + explicit commits keep pushes clean. Claims cover the rest (shared website/engine edits).
