# SPX Signal Alert Worker

Cloudflare Worker that monitors the **S&P500 3x Levered (B1) strategy signal** and sends email alerts via SendGrid when the signal changes.

**Strategy:** SMA200 ±3% Band + RSI>30 Exit, 3x leverage  
**Execution vehicle:** 3USL.L (UCITS 3x S&P 500, London) / UPRO (US)

---

## How It Works

1. **Cron trigger** fires every 30 minutes during LSE hours (Mon–Fri, 08:00–16:30 UK time)
2. Fetches ~30 years of S&P 500 daily close data from Yahoo Finance
3. Computes SMA(200), RSI(14), and the B1 signal:
   - **LONG** (3x): Close > SMA200 × 1.03
   - **CASH**: Close < SMA200 × 0.97 **or** RSI(14) < 30
   - **Hold prior state**: In the neutral zone between bands with RSI ≥ 30
4. Compares to the last known signal stored in **Workers KV**
5. If the signal changed (CASH→LONG or LONG→CASH), sends an email via **SendGrid**
6. Stores the new signal state in KV for the next check

---

## Prerequisites

1. **Cloudflare Workers** account (free tier: 100k requests/day, sufficient)
2. **SendGrid** account (free tier: 100 emails/day — more than enough for signal alerts)
3. **Node.js** and **npm** installed locally (for `wrangler` CLI)

---

## Setup & Deployment

### Step 1: Install Wrangler CLI

```bash
npm install -g wrangler
```

### Step 2: Create a KV Namespace

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **KV**
2. Click **Create namespace**
3. Name it `SIGNAL_STATE` (or any name — just match the binding in `wrangler.toml`)
4. Copy the **Namespace ID** (looks like `abc123...`)
5. Paste it into [`wrangler.toml`](wrangler.toml:18) replacing `YOUR_KV_NAMESPACE_ID`:
   ```toml
   id = "abc123..."  # Your actual namespace ID
   ```

### Step 3: Get a SendGrid API Key

1. Sign up at [sendgrid.com](https://sendgrid.com) (free tier: 100 emails/day)
2. Go to **Settings** → **API Keys** → **Create API Key**
3. Choose "Full Access" or "Restricted Access" with at least **Mail Send** permission
4. Copy the API key (starts with `SG.`)

### Step 4: Verify a Sender Email in SendGrid

1. Go to **Settings** → **Sender Authentication**
2. Either verify a single sender email, or authenticate a domain
3. The sender email must be verified before SendGrid will send

### Step 5: Configure Environment Variables

Set these in Cloudflare Dashboard (**Workers & Pages** → `spx-signal-alert` → **Settings** → **Variables**) or via `wrangler secret put`:

| Variable | Description | Example |
|----------|-------------|---------|
| `SENDGRID_API_KEY` | Your SendGrid API key | `SG.xxxxxxxxxxxxxxxx` |
| `ALERT_EMAIL_FROM` | Verified sender email | `alerts@yourdomain.com` |
| `ALERT_EMAIL_TO` | Recipient email for alerts | `you@example.com` |
| `TEST_MODE` | Set to `"true"` to log instead of sending | `"false"` |

Using `wrangler secret put` (recommended for secrets):
```bash
npx wrangler secret put SENDGRID_API_KEY
# Paste your key when prompted

npx wrangler secret put ALERT_EMAIL_FROM
npx wrangler secret put ALERT_EMAIL_TO
```

For non-secret vars, set them in `wrangler.toml` or Cloudflare Dashboard.

### Step 6: Adjust Cron Schedule for UK Time

Cloudflare Workers cron uses **UTC**. Adjust the hours in [`wrangler.toml`](wrangler.toml:30) based on the season:

| Season | UK Time (LSE) | UTC Equivalent | Cron Expression |
|--------|---------------|----------------|-----------------|
| **Summer** (BST, UTC+1) | 08:00–16:30 | 07:00–15:30 | `*/30 7-15 * * 1-5` |
| **Winter** (GMT, UTC+0) | 08:00–16:30 | 08:00–16:30 | `*/30 8-16 * * 1-5` |

The cron expression `*/30 8-16 * * 1-5` means:
- `*/30` = every 30 minutes
- `8-16` = hours 8 through 16 (inclusive)
- `*` = every day of month
- `*` = every month
- `1-5` = Monday through Friday

### Step 7: Deploy

```bash
cd workers/spx-signal-alert
npx wrangler deploy
```

After deployment, the Worker will start running on the cron schedule automatically.

---

## Testing

### Local Testing (without sending real emails)

1. Create a `.dev.vars` file in the worker directory:
   ```
   SENDGRID_API_KEY = "SG.test"
   ALERT_EMAIL_FROM = "test@example.com"
   ALERT_EMAIL_TO = "test@example.com"
   TEST_MODE = "true"
   ```

2. Run the worker locally with cron simulation:
   ```bash
   npx wrangler dev --test-scheduled
   ```

3. In another terminal, trigger a scheduled event:
   ```bash
   curl http://localhost:8787/__scheduled?force=true
   ```

4. Or trigger via HTTP:
   ```bash
   curl http://localhost:8787/
   ```

With `TEST_MODE=true`, the worker will log what it *would* send instead of actually calling SendGrid.

### Manual Trigger (Production)

Visit the Worker URL directly to force a signal check and see the result:
```
https://spx-signal-alert.YOUR_SUBDOMAIN.workers.dev/
```

Or with `?force=true`:
```
https://spx-signal-alert.YOUR_SUBDOMAIN.workers.dev/?force=true
```

The response is a JSON object with the signal check result:
```json
{
  "ok": true,
  "timestamp": "2026-06-19T14:30:00.000Z",
  "signal": "LONG",
  "previousSignal": "CASH",
  "changed": true,
  "emailSent": true,
  "testMode": false,
  "metrics": {
    "price": 6048.32,
    "sma200": 5872.15,
    "rsi14": 52.3,
    "upperBand": 6048.31,
    "lowerBand": 5695.99
  },
  "emailResult": {
    "sent": true,
    "statusCode": 202,
    "to": "you@example.com",
    "subject": "⚠️ SPX 3x Signal Change: CASH → LONG"
  }
}
```

---

## Monitoring

- **Cloudflare Dashboard** → Workers & Pages → `spx-signal-alert` → **Logs** — view cron execution logs
- **SendGrid Dashboard** → **Activity** — view email delivery status
- **Workers KV** → `SIGNAL_STATE` namespace — inspect the stored signal state

---

## Files

| File | Purpose |
|------|---------|
| [`wrangler.toml`](wrangler.toml) | Worker configuration: KV binding, cron schedule, env vars |
| [`index.js`](index.js) | Worker code: data fetch, signal computation, KV state, SendGrid email |
| [`package.json`](package.json) | Node.js package metadata |
| [`README.md`](README.md) | This file — deployment and testing instructions |

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Worker deploys but cron doesn't run | Wrong cron expression or timezone mismatch | Check UTC vs UK time; verify in Cloudflare Dashboard → Workers → Triggers |
| Emails not sending | SendGrid API key invalid or sender not verified | Check SendGrid Dashboard → Activity for errors; verify sender email |
| "Insufficient data" error | Yahoo Finance API returned fewer than 200 closes | Rare — Yahoo's 30y range always has 200+ days. Check network/fetch errors in logs |
| Signal not changing when expected | RSI computation mismatch with Python backtest | The Worker uses Wilder's smoothing (same as Python). Verify with manual trigger |
| KV read/write failures | KV namespace not created or binding ID wrong | Check `wrangler.toml` has correct namespace ID; verify namespace exists in Dashboard |
