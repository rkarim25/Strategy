# .claims/ — multi-agent work claims

Before starting **substantial / long / shared** work (editing website or core-engine files), drop a claim
here so other agents don't collide with you. Full protocol: `docs/runbooks/coordination.md`.

## How (idiot-proof)
1. Create a file named `YYYYMMDD-HHMM-<short-task>.md` in this folder.
2. Put one or two lines inside: who you are (model/session), what you're doing, which files/areas you'll touch.
3. **Delete your file when you're done.**

Before editing a shared file, check the other files here for an active claim on it. Treat any claim older
than ~24h as stale and ignore it.

Claim files are gitignored — this README is the only committed file. They coordinate agents sharing this
local working copy (the realistic case: several AI sessions on the same machine).

## Example
`20260626-1530-spx-rsi-tweak.md`:
> Claude session — editing `index.html` RSI tab + `spx_distance_scale_site_data.json`. ~30 min.
