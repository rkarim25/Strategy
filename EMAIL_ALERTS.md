# Trade alert email setup

The GitHub Pages site is **static** — it cannot send email from the browser. Trade alerts are sent by the **scheduled GitHub Action** when `update_static_market_data.py` refreshes market data and detects a **change in official target leverage** (cash ↔ 1x ↔ 2x ↔ 3x).

**Recipient (default):** `rkarim88@gmail.com` (override with `ALERT_EMAIL_TO` secret).

## Which strategies send email?

All sleeves processed by the updater send email on official leverage change:

| Asset | Signal file | Email alerts | II instruments in email |
|-------|-------------|--------------|-------------------------|
| **S&P 500** | `latest_signal.json` | Yes | SPYL / XS2D / 3USL (cash when 0x) |
| **Nasdaq 100** | `latest_ndx_signal.json` | Yes | EQQQ / LQQ / LQQ3 (cash when 0x) |
| **Gold** | `latest_gold_signal.json` | Yes | SGLN / PHGP (max 1x; cash when 0x) |
| **FTSE 250** | `latest_ftse250_signal.json` | Yes | MIDD / VMID (max 1x; cash when 0x) |
| **MSCI EM** | `latest_msci_em_signal.json` | Yes | EIMI / VFEM (max 1x; cash when 0x) |
| **DAX** | `latest_dax_signal.json` | Yes | EXS1 / XDAX (max 1x; cash when 0x) |
| **MSCI World** | `latest_msci_world_signal.json` | Yes | IWDA / SWDA (max 1x; cash when 0x) |
| **LQQ3 3x Nasdaq** | `latest_lqq3_signal.json` | Yes | LQQ3 (max 1x tab = cash vs fully in 3x ETP) |
| **3BAL EU Banks** | `latest_3bal_signal.json` | Yes | 3BAL (max 1x tab = cash vs fully in 3x ETP) |

Max 1x sleeves only email **cash ↔ 1x** transitions (tiers 2x/3x are capped in the signal). US sleeves (SPX, NDX) can email all four tiers.

## When is email sent?

1. **Official** end-of-day signal leverage **changes** vs the previous run (e.g. 1x → 2x, or cash → 1x).
2. **At most one email per asset per UK calendar day** (`Europe/London`, GMT/BST). If leverage changes again later the same UK day (e.g. 2x → 3x), no second email is sent for that asset.
3. Unchanged signals never email (state is stored in `trade_alert_state` inside each `latest_*.json`).

The Action runs **every 30 minutes** on **weekdays** (see `.github/workflows/update-market-data.yml`), aligned with the site’s data refresh — not on every browser refresh.

## GitHub secrets required

In the repo: **Settings → Secrets and variables → Actions**, add:

| Secret | Example |
|--------|---------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | your Gmail address |
| `SMTP_PASSWORD` | [Gmail App Password](https://myaccount.google.com/apppasswords) (not your normal password) |
| `ALERT_EMAIL_TO` | `rkarim88@gmail.com` |
| `ALERT_EMAIL_FROM` | same as `SMTP_USERNAME` (optional) |

If SMTP secrets are missing, data still refreshes; the log will say the alert was skipped.

## Email contents

Each alert includes:

- **Buy/sell direction** (increase or reduce leverage vs prior target)
- **Target tier** (cash, 1x, 2x, or 3x)
- **Specific LSE tickers** to use on Interactive Investor for that tier (from `ALERT_PROFILES` in `update_static_market_data.py`)
- Index level, SMA20, drawdown, regime, trigger levels, and the rule explanation

Subject line format: `[Asset] old -> new (signal date)` — e.g. `[FTSE 250] cash -> 1x (2026-06-06)`.

## Manual test

SMTP connectivity (no market refresh):

```powershell
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USERNAME="you@gmail.com"
$env:SMTP_PASSWORD="your-app-password"
$env:ALERT_EMAIL_TO="rkarim88@gmail.com"
python update_static_market_data.py --test-email
```

Preview alert body templates (no SMTP, no network):

```powershell
python update_static_market_data.py --preview-alerts
```

Full refresh (sends real alerts only when official leverage changes):

```powershell
python update_static_market_data.py
```

Or trigger **Actions → Update static market data → Run workflow** after secrets are set.
