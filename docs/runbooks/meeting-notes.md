# Runbook: Investor-Meeting Audio Summarization

Owner: rkarim88@gmail.com (EM corporate bond / Eurobond fund manager).
Purpose: turn (audio + Otter transcript + the user's own notes) for each investor
meeting into a concise credit-focused summary. This runs **per meeting folder in
Google Drive** — it is unrelated to the backtesting factory in the rest of this repo.

## Inputs (Google Drive, via the Google Drive connector)

- Trip folder: `Turkey investor trip 2026`, folder ID `1ZCmOltWADWV7jfRj37Fe7CU05Q3eAGN1`.
- Per meeting: an audio file (`.mp3`), an Otter transcript export (`.txt`),
  and the user's own notes (PDF covering the whole trip: `Turkey invest trip 2026.pdf`,
  file ID `1B2GCCboyyyxXQfOFHonucdpZd29R63TQ`).
- Connector quirks: `download_file_content` returns **base64** and refuses files
  **> 10 MB** — transcripts fit, audio does not. Large tool results are auto-saved
  to a file under the session's `tool-results/` dir; `jq -r '.content' | base64 -d` to extract.

## Getting the audio (> 10 MB)

Requires the environment network policy to allow `drive.google.com` +
`*.googleusercontent.com` (user has enabled all domains — policy applies to
**freshly started containers only**). Then either:

1. Ask the user to set the audio file to "anyone with link", then
   `pip install gdown && gdown <FILE_ID>` (handles the large-file confirm token), or
2. Use the Drive API host `www.googleapis.com` if an OAuth token is available.

Revoke link-sharing after download if it was enabled.

## Transcription (own transcript from audio — do NOT summarise from Otter alone)

- `pip install faster-whisper` (bundles ffmpeg via PyAV; no system ffmpeg needed).
  Model weights come from `huggingface.co` / `cdn-lfs.huggingface.co`.
- CPU-only box (4 cores): use `small` or `medium` model, `compute_type="int8"`,
  `beam_size=5`, `word_timestamps=False`, language auto (meetings are English with
  Turkish accents — Whisper handles this much better than Otter).
- ~1h35m audio ≈ 30–60 min on `small`. Run in background (`run_in_background`).
- Keep the audio and transcripts in the session scratchpad, NOT in this git repo.

## Reconciliation & summary rules (FINAL SPEC — user-approved 2026-07-09, v3 format)

1. The user's own notes have **priority** — they mark what mattered in the room.
2. Cross-check every **number** across all sources (own Whisper transcript, Otter,
   user notes, public disclosures) and by arithmetic (cash walks etc.) — then
   **print only the single most reliable value. Never show the conflict, the
   correction trail, or "X said / notes said" annotations.** Mis-heard names are
   silently replaced with the verified real name (e.g. Otter's "Engin" → İncir HPP).
3. **Per issuer, run a deep research pass before writing** (parallel web-research
   agents): company background, industry, and macro. Weave in only context that
   changes the credit read — one clause, stated as fact, no "Context:" labels,
   no source lists, no verification notes in the output.
4. Audience: EM Eurobond credit investor. Only forward-useful content. Template
   (copy-paste ready, no meta, no second-person references):
   - `# <Issuer> — Management Meeting, <Trip> (<Mon-Year>)`
   - **Takeaways** — 4–6 bullets, credit-relevant, key figures bolded
   - **Guidance** table — Metric | Guidance | Period. Metrics: revenue, EBITDA,
     interest expense, working capital, capex, FCF, dividend, net leverage,
     plus volumes/pricing where relevant.
   - **Funding & issuance** table — instrument, size, timing, terms, use of proceeds
   - **Watch items** — ≤3 bullets: swing factors, catalysts, what to track
   - Reference example: `Limak_Renewables_note_v3.md` in the trip folder.
5. Output: markdown, uploaded to the same Drive trip folder
   (`create_file`, `disableConversionToGoogleType: true`) and sent to the user
   via SendUserFile. Meeting recordings may contain sensitive information — do
   not commit transcripts, audio, or summaries to this repo.
6. Maintain the **MASTER file** in the trip folder: title
   `_MASTER <trip> [updated YYYY-MM-DD].md`. Contents: (a) progress tracker
   table — one row per meeting: audio / Otter / note status — then (b) every
   completed note concatenated in full (v3 format), so one copy grabs everything.
   The Drive connector cannot update or delete files, so each refresh CREATES a
   new file with the current date in the title — **the newest-dated `_MASTER` is
   canonical**; the master's copy of a note supersedes the individual file.
   Individual per-issuer note files are still uploaded alongside it.
   The user checks progress from any chat by asking Claude (with the Drive
   connector) to read the latest `_MASTER` file. Refresh the master after every
   completed note, and suggest the user occasionally deletes stale `_MASTER`
   versions and superseded drafts (connector can't).

## Status (2026-07-09)

- Pilot done: `Limak_meeting_summary_DRAFT.md` in the trip folder — covers
  Limak Port İskenderun / Limak Cement / Limak Renewables from
  `Limak_otter.ai.txt` + user notes. Audio `Limak_2.mp3`
  (ID `1gfOunnz7oiXGpNbs-mCYSQO_4A3rK8Xr`, 17 MB) **not yet transcribed** —
  blocked on network policy in the old container; user has since allowed all domains.
- Next session: download audio, Whisper-transcribe, resolve the 9 numbered flags
  at the bottom of the draft (biggest: Limak Port EBITDA/net debt — notes say
  $50m/$300m, Otter says $60m/$200m), reissue the summary as FINAL.
- Also delete/ignore the stray 22-byte `Limak_meeting_summary_DRAFT.md` stub in
  the folder (bad first upload; connector cannot delete).
- Awaiting user feedback on template (length/altitude) before batch-processing
  further meetings; then add a running cross-issuer guidance master file.
