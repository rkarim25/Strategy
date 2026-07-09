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

## Reconciliation & summary rules

1. The user's own notes have **priority** — they mark what mattered in the room.
2. Use Otter mainly for speaker labels/timestamps; trust the fresh Whisper
   transcript for content. Every **number** must be cross-checked across all
   three sources; unresolved conflicts go in a "Flags for verification" list with
   timestamps. Sanity-check numbers by arithmetic where possible (cash walks etc.).
3. Audience: EM Eurobond credit investor. Include only forward-useful content.
   Fixed template per issuer:
   - Header (issuer, date, meeting type)
   - Top takeaways (3–6 bullets, credit-relevant)
   - **Guidance table**: revenue, EBITDA, interest expense, working capital,
     capex, FCF, dividend, net leverage — plus volumes/pricing where relevant.
     Columns: Metric | Guidance | Period | Confidence | Timestamp.
     Confidence key: ✓ notes+transcript agree · N notes only · T transcript only · ⚠ conflict.
   - **Issuance / liability-management table**: instrument, size, timing, use of proceeds.
   - Other points for the file (competitive/regulatory/watch items)
   - Flags for audio verification
4. Output: markdown, uploaded back into the same Drive trip folder
   (`create_file`, `disableConversionToGoogleType: true`) and sent to the user
   via SendUserFile. Meeting recordings may contain sensitive information — do
   not commit transcripts, audio, or summaries to this repo.

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
