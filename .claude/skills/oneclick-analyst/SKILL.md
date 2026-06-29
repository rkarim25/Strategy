---
name: oneclick-analyst
description: >-
  One-click market Analyst for the S&P 500 and Nasdaq 100. Use whenever the user wants a full
  read of the current market — "/analyst", "run the analyst", "what should I do in the market",
  "read the signals", "what's the suggested action / leverage", "is it risk-on or risk-off",
  "check the data and signals". Downloads + validates all the signal data, then produces a
  quantitative + qualitative assessment and a concrete action plan with a suggested leverage —
  the hours-of-chart-reading job, done in one step.
---

# One-click Analyst

Turn one command into the assessment a human would spend hours reaching: pull and validate all the
data, read every graded signal for both indices, and deliver a quant + qualitative call with an
action plan and suggested leverage. The reasoning lives in `analyst_prompt.md` (the shared brain,
also used by the website button and the optional API worker) — this skill is the Claude Code wiring.

## Run it (one click)
1. **Build the bundle** (downloads live data + validates it; no backtests re-run):
   `python research/build_analyst_bundle.py`
   - It fetches live quotes + VIX from the quote worker and recomputes the composite live.
   - The worker rejects non-browser user-agents, and some sandboxes block outbound HTTP — if you
     see `live ... fetch: worker unreachable`, re-run with the network sandbox disabled. The script
     degrades gracefully to the last-close snapshot and WARNs, so it never hard-fails.
   - Output: `analyst_bundle.json` (the single source of truth) + a console health summary.
2. **Read** `analyst_bundle.json` and `analyst_prompt.md`.
3. **Apply `analyst_prompt.md` to the bundle** — follow it exactly (data-health first, lead with the
   composite, weight by grade, name composite-vs-official divergences, explain the leverage cap,
   quantify with Sharpe/Calmar/MaxDD, then the action plan). Deliver the markdown brief to the user.

That's it — steps 1-3 are the whole "click". Everything the analysis needs is in the bundle.

## What makes it robust
- **Data health is enforced**, not assumed: freshness (daily CSV + official signal age), NaN/Infinity
  integrity, live-fetch success, and per-signal evaluation coverage. Lead the brief with any
  `FAIL`/`WARN` — never present a confident read on data flagged broken.
- **Live, not stale**: the bundle overrides the last close with the live quote and pulls live VIX, so
  the composite matches the website dashboard. If offline, it says `asof:"snapshot"` — surface that.
- **One brain, three surfaces**: `analyst_prompt.md` is shared by this skill, the website
  "Copy analyst prompt" button, and `cloudflare_market_analyst_worker.js`. Edit the prompt once.

## Scope & data
- Assets: S&P 500 (`spx`) + Nasdaq 100 (`ndx`) — the dashboard's scope.
- Inputs the bundle gathers: `signals_{spx,ndx}.json` (graded signals + live state), the official
  mechanical signals (`latest_signal.json`, `latest_ndx_signal.json`), `news_score.json`, benchmarks.
- This is a read/report task — **no deploy needed**. Only deploy if you regenerated `signals_*.json`
  and the user wants the refreshed snapshot live (then use the worktree deploy in `strategy-factory`).

## Replicating this in another project (the portable kit)
Copy these and repoint three things:
1. `research/build_signal_dashboard.py` + `research/signal_state.py` — the grader + live evaluators
   (point at that project's backtest sweep CSV and price series).
2. `research/build_analyst_bundle.py` — the gather+validate+bundle step (set its asset list, data
   files, and quote source).
3. `analyst_prompt.md` — the analyst brain (rewrite for the new domain's signals).
Then this SKILL.md + the website button + `cloudflare_market_analyst_worker.js` carry over unchanged
except for those data sources. See `docs/oneclick-analyst.md` for the full architecture.
