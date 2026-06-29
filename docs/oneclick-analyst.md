# One-click Analyst — architecture & replication

A single click (a Claude Code command, or a website button) that does what hours of chart-reading
would: pull and validate all the signal data for the S&P 500 and Nasdaq 100, read every graded
indicator, and produce a quantitative + qualitative assessment with an action plan and suggested
leverage. Built as a portable kit so it drops into other projects.

## The design: one brain, one data step, three surfaces

```
                         analyst_prompt.md          <- THE BRAIN (shared reasoning instructions)
                                |
   research/build_analyst_bundle.py  ->  analyst_bundle.json   <- THE DATA (gather + validate + live)
                                |
        +-----------------------+------------------------+
        |                       |                        |
  Claude Code            Website button            Cloudflare worker (optional)
  /analyst command       (price.js)                cloudflare_market_analyst_worker.js
  reads bundle +         quant report + copy-       reads bundle + same prompt,
  applies prompt         prompt (+ worker if set)   calls Claude API -> inline narrative
```

- **The brain** — [`analyst_prompt.md`](../analyst_prompt.md): the analyst's reasoning steps and
  output format. Edited once, used by all three surfaces. This is what makes the quality identical
  whether the analysis runs via the API or via a pasted prompt.
- **The data** — [`research/build_analyst_bundle.py`](../research/build_analyst_bundle.py): refreshes
  the graded signals, fetches **live** quotes + VIX (recomputing the composite live), runs
  **data-health checks** (freshness, NaN, fetch success), and writes one `analyst_bundle.json`.
  Degrades gracefully to the last-close snapshot when offline (WARNs, never hard-fails).

## The three surfaces
1. **Claude Code** — `/analyst` (the `oneclick-analyst` skill): runs the bundle, reads it, applies
   `analyst_prompt.md`, delivers the brief. No key, no cost.
2. **Website** — the "🧠 Run one-click Analyst" button on the Charts page (`price.js`): builds the
   live bundle client-side for both assets, renders a deterministic quant report + data-health, and
   offers **Copy analyst prompt** (paste into any Claude window — identical quality). Works today,
   no key.
3. **Website + API (optional upgrade)** — deploy `cloudflare_market_analyst_worker.js` and set
   `ANALYST_WORKER` in `price.js`; the button then also shows **Generate AI assessment**, rendering
   the Claude-written narrative inline. ~1-3¢/click. Quality is the same as the copy-prompt route —
   the API only removes the paste step.

### Enabling the worker (only if you want paste-free inline AI)
1. Get an Anthropic API key at console.anthropic.com (set a spend limit).
2. `wrangler deploy` the worker, then `wrangler secret put ANTHROPIC_API_KEY`.
3. Set `const ANALYST_WORKER = "https://<worker>.workers.dev"` in `price.js`, bump `price.js?v=`, deploy.
Model is `claude-sonnet-4-6` by default (good value); set the `MODEL` worker var to `claude-opus-4-8`
for maximum quality.

## Replicating in another project
Copy the kit and repoint three things:
1. `research/build_signal_dashboard.py` + `research/signal_state.py` — the grader + live evaluators
   (point at the project's backtest sweep + price series).
2. `research/build_analyst_bundle.py` — asset list, data files, quote source.
3. `analyst_prompt.md` — rewrite the analyst brain for the new domain.
The `oneclick-analyst` skill, the website button (`price.js`), and the worker carry over with only
those data sources changed.

## Files
| File | Role |
|------|------|
| `analyst_prompt.md` | Shared analyst brain (system prompt) |
| `research/build_analyst_bundle.py` | Gather + validate + live-recompute → `analyst_bundle.json` |
| `research/build_signal_dashboard.py`, `research/signal_state.py` | Grader + live evaluators |
| `.claude/skills/oneclick-analyst/SKILL.md` | Claude Code `/analyst` wiring |
| `price.js` (Analyst button + `buildClientBundle`/`openAnalyst`) | Website one-click |
| `cloudflare_market_analyst_worker.js` | Optional API worker for inline narrative |
