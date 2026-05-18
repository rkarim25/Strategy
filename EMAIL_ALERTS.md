# Trade Alert Email Setup

The GitHub Pages site is static, so it cannot safely send email from browser JavaScript. Trade-alert email is sent by the scheduled GitHub Action when `update_static_market_data.py` refreshes `latest_signal.json`.

Add these repository secrets in GitHub under **Settings -> Secrets and variables -> Actions**:

- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=587`
- `SMTP_USERNAME=<gmail address>`
- `SMTP_PASSWORD=<gmail app password>`
- `ALERT_EMAIL_TO=rkarim88@gmail.com`
- `ALERT_EMAIL_FROM=<gmail address>` (optional; defaults to `SMTP_USERNAME`)

For Gmail, use a Gmail App Password, not the regular account password. If SMTP secrets are missing, the updater still refreshes market data and logs that the email alert was skipped.

Alerts are only sent when the official target leverage changes, such as cash to 1x, 1x to 2x, or 3x to 1x. The last observed signal state is stored in `latest_signal.json` so repeated scheduled runs do not send duplicate emails for an unchanged signal.
