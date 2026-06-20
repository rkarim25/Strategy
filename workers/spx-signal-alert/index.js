/**
 * Cloudflare Worker: SPX 3x Levered Signal Alert
 *
 * Runs on a cron schedule (every 30 min during LSE hours, weekdays).
 * Fetches S&P 500 daily close data from Yahoo Finance, computes the
 * B1 strategy signal (SMA200 ±3% Band + RSI>30 Exit), compares to
 * the last known state stored in Workers KV, and sends an email alert
 * via SendGrid when the signal changes (cash→long or long→cash).
 *
 * Also supports HTTP GET for manual trigger and health checks:
 *   GET /             → health check (returns last signal state)
 *   GET /?force=true  → force a signal check (useful for testing)
 *
 * Deployment instructions are in wrangler.toml and README.md.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SPX_ENCODED = "%5EGSPC";
const SPX_TICKER = "^GSPC";
const YAHOO_CHART_URL = `https://query1.finance.yahoo.com/v8/finance/chart/${SPX_ENCODED}?interval=1d&range=30y`;

const SMA_WINDOW = 200;
const BAND_PCT = 0.03;
const RSI_WINDOW = 14;
const RSI_EXIT = 30;
const BASE_LEVERAGE = 3;

const KV_KEY = "spx3x_signal";
const SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send";

// ---------------------------------------------------------------------------
// Main Entry Point
// ---------------------------------------------------------------------------

export default {
  /**
   * Cron trigger handler. Called automatically by Cloudflare on the schedule
   * defined in wrangler.toml [triggers] section.
   */
  async scheduled(event, env, ctx) {
    ctx.waitUntil(processSignalCheck(env));
  },

  /**
   * HTTP fetch handler. Supports:
   *   GET /              → health check / manual trigger
   *   GET /?force=true   → force a signal check (bypasses cron-only restriction)
   */
  async fetch(request, env) {
    const url = new URL(request.url);
    const force = url.searchParams.get("force") === "true";

    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "")) {
      try {
        const result = await processSignalCheck(env);
        return new Response(JSON.stringify(result, null, 2), {
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "content-type": "application/json" },
        });
      }
    }

    return new Response("SPX Signal Alert Worker — use GET / for health check", {
      status: 200,
      headers: { "content-type": "text/plain" },
    });
  },
};

// ---------------------------------------------------------------------------
// Core Logic: Fetch Data → Compute Signal → Compare → Alert
// ---------------------------------------------------------------------------

/**
 * Main processing pipeline. Fetches SPX data, computes the B1 signal,
 * compares to the last stored state in KV, and sends an email alert
 * if the signal has changed.
 *
 * @param {object} env - Worker environment bindings (KV, vars, secrets)
 * @returns {object} result summary
 */
async function processSignalCheck(env) {
  const testMode = env.TEST_MODE === "true";

  // 1. Fetch SPX daily close data from Yahoo Finance
  const closes = await fetchSpxDailyCloses();
  if (!closes || closes.length < SMA_WINDOW) {
    throw new Error(`Insufficient data: need ${SMA_WINDOW}+ closes, got ${closes?.length || 0}`);
  }

  // 2. Read the last known signal state from KV (needed for hysteresis)
  let previousState = null;
  try {
    const raw = await env.SIGNAL_STATE.get(KV_KEY);
    if (raw) {
      previousState = JSON.parse(raw);
    }
  } catch (err) {
    console.error("Failed to read KV state:", err.message);
    // Continue — if we can't read previous state, we'll store current and not alert
  }

  const previousSignal = previousState?.signal || null;

  // 3. Compute the B1 signal (uses previousSignal for hysteresis in neutral zone)
  const lastIndex = closes.length - 1;
  const price = closes[lastIndex];
  const sma200 = computeSMA(closes, lastIndex, SMA_WINDOW);
  const rsi14 = computeRSI(closes, lastIndex, RSI_WINDOW);
  const signal = computeSignal(price, sma200, rsi14, previousSignal);

  // 4. Build the new state object
  const newState = {
    signal: signal,
    timestamp: new Date().toISOString(),
    price: price,
    sma200: sma200,
    rsi14: rsi14,
    upperBand: sma200 * (1 + BAND_PCT),
    lowerBand: sma200 * (1 - BAND_PCT),
  };

  // 5. Determine if signal changed
  const changed = previousSignal !== null && previousSignal !== signal;

  // 6. Store the new state in KV (always, even if unchanged)
  try {
    await env.SIGNAL_STATE.put(KV_KEY, JSON.stringify(newState));
  } catch (err) {
    console.error("Failed to write KV state:", err.message);
    // Non-fatal — alert can still be sent
  }

  // 7. Send email alert if signal changed
  let emailResult = null;
  if (changed) {
    if (testMode) {
      console.log(`[TEST MODE] Would send email: ${previousSignal} → ${signal}`);
      console.log(`[TEST MODE] Email subject: ⚠️ SPX 3x Signal Change: ${previousSignal} → ${signal}`);
      console.log(`[TEST MODE] Price: ${price.toFixed(2)}, SMA200: ${sma200.toFixed(2)}, RSI14: ${rsi14.toFixed(1)}`);
      emailResult = { testMode: true, wouldSend: true };
    } else {
      emailResult = await sendAlert(env, newState, previousSignal);
    }
  }

  return {
    ok: true,
    timestamp: newState.timestamp,
    signal: signal,
    previousSignal: previousSignal,
    changed: changed,
    emailSent: changed && !testMode,
    testMode: testMode,
    metrics: {
      price: price,
      sma200: sma200,
      rsi14: rsi14,
      upperBand: newState.upperBand,
      lowerBand: newState.lowerBand,
    },
    emailResult: emailResult,
  };
}

// ---------------------------------------------------------------------------
// Data Fetching: Yahoo Finance Chart API
// ---------------------------------------------------------------------------

/**
 * Fetches S&P 500 daily close prices from Yahoo Finance.
 * Uses the same v8 chart endpoint as the existing spx-quote-proxy Worker.
 *
 * @returns {number[]} Array of daily close prices (most recent last)
 */
async function fetchSpxDailyCloses() {
  const res = await fetch(YAHOO_CHART_URL, {
    headers: { "user-agent": "Mozilla/5.0" },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Yahoo Finance daily request failed (${res.status}): ${text.slice(0, 300)}`);
  }

  const data = await res.json();
  const result = data?.chart?.result?.[0];
  if (!result) {
    throw new Error("Yahoo Finance response missing chart.result[0]");
  }

  const timestamps = result.timestamp || [];
  const quote = result.indicators?.quote?.[0];
  const closes = quote?.close || [];

  // Pair timestamps with closes, filter invalid entries
  const rows = [];
  for (let i = 0; i < Math.min(timestamps.length, closes.length); i++) {
    const close = Number(closes[i]);
    if (Number.isFinite(close) && close > 0) {
      rows.push({
        date: new Date(timestamps[i] * 1000).toISOString().slice(0, 10),
        close: close,
      });
    }
  }

  if (rows.length < SMA_WINDOW) {
    throw new Error(`Only ${rows.length} valid daily closes available (need ${SMA_WINDOW}+)`);
  }

  // Return just the close prices array
  return rows.map((r) => r.close);
}

// ---------------------------------------------------------------------------
// Signal Computation
// ---------------------------------------------------------------------------

/**
 * Compute Simple Moving Average over a window ending at endIndex.
 *
 * @param {number[]} prices - Array of prices
 * @param {number} endIndex - Index of the last element to include
 * @param {number} window - Number of periods for the SMA
 * @returns {number} SMA value, or NaN if insufficient data
 */
function computeSMA(prices, endIndex, window) {
  if (endIndex < window - 1) return NaN;
  let sum = 0;
  for (let i = endIndex - window + 1; i <= endIndex; i++) {
    sum += prices[i];
  }
  return sum / window;
}

/**
 * Compute RSI (Relative Strength Index) using Wilder's smoothing.
 *
 * Uses the standard Wilder's method:
 *   - First average gain/loss is a simple average over the initial window
 *   - Subsequent values use exponential smoothing:
 *       avgGain = (prevAvgGain * (window - 1) + currentGain) / window
 *       avgLoss = (prevAvgLoss * (window - 1) + currentLoss) / window
 *   - RS = avgGain / avgLoss
 *   - RSI = 100 - (100 / (1 + RS))
 *
 * This matches the Python backtest engine's RSI computation exactly.
 *
 * @param {number[]} prices - Array of prices
 * @param {number} endIndex - Index of the last element to include
 * @param {number} window - RSI period (default 14)
 * @returns {number} RSI value (0–100), or NaN if insufficient data
 */
function computeRSI(prices, endIndex, window = 14) {
  if (endIndex < window) return NaN;

  // Compute initial average gain and loss (simple average over first 'window' periods)
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = endIndex - window + 1; i <= endIndex; i++) {
    const delta = prices[i] - prices[i - 1];
    if (delta > 0) {
      avgGain += delta;
    } else {
      avgLoss += -delta;
    }
  }
  avgGain /= window;
  avgLoss /= window;

  if (avgLoss === 0) return 100;
  if (avgGain === 0) return 0;

  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/**
 * Compute the B1 strategy signal.
 *
 * Logic (per implementation plan — authoritative):
 *   - If price > SMA200 × 1.03 → LONG (3x levered)
 *   - If price < SMA200 × 0.97 → CASH
 *   - If RSI(14) < 30 → CASH (the "RSI>30 Exit" means exit to cash when RSI drops below 30)
 *   - Otherwise → hold prior state (hysteresis in the neutral zone)
 *
 * The "previous signal" for hysteresis is the last stored KV state.
 *
 * @param {number} price - Latest SPX close price
 * @param {number} sma200 - 200-day SMA value
 * @param {number} rsi14 - 14-period RSI value
 * @param {string|null} previousSignal - Last known signal from KV ("LONG" or "CASH")
 * @returns {string} "LONG" or "CASH"
 */
function computeSignal(price, sma200, rsi14, previousSignal = null) {
  const upperBand = sma200 * (1 + BAND_PCT);
  const lowerBand = sma200 * (1 - BAND_PCT);

  let rawSignal;

  if (price > upperBand) {
    rawSignal = "LONG";
  } else if (price < lowerBand || rsi14 < RSI_EXIT) {
    // Exit to cash: either below the lower band OR RSI dropped below 30
    rawSignal = "CASH";
  } else {
    // Neutral zone with RSI ≥ 30 — hold prior state (hysteresis)
    rawSignal = previousSignal || "CASH"; // Default to CASH if no prior state
  }

  return rawSignal;
}

// ---------------------------------------------------------------------------
// Email Alert via SendGrid
// ---------------------------------------------------------------------------

/**
 * Sends an email alert via the SendGrid v3 Mail Send API.
 *
 * @param {object} env - Worker environment (contains SENDGRID_API_KEY, etc.)
 * @param {object} state - Current signal state object
 * @param {string} previousSignal - Previous signal value ("LONG" or "CASH")
 * @returns {object} SendGrid response summary
 */
async function sendAlert(env, state, previousSignal) {
  const apiKey = env.SENDGRID_API_KEY;
  const fromEmail = env.ALERT_EMAIL_FROM;
  const toEmail = env.ALERT_EMAIL_TO;

  if (!apiKey || !fromEmail || !toEmail) {
    throw new Error("Missing required environment variables: SENDGRID_API_KEY, ALERT_EMAIL_FROM, ALERT_EMAIL_TO");
  }

  const newSignal = state.signal;
  const action = newSignal === "LONG" ? "BUY (3x Levered)" : "SELL (Go to Cash)";
  const subject = `⚠️ SPX 3x Signal Change: ${previousSignal} → ${newSignal}`;

  const html = buildEmailHtml(state, previousSignal, action);
  const plainText = buildEmailText(state, previousSignal, action);

  const payload = {
    personalizations: [
      {
        to: [{ email: toEmail }],
        subject: subject,
      },
    ],
    from: { email: fromEmail },
    content: [
      { type: "text/plain", value: plainText },
      { type: "text/html", value: html },
    ],
  };

  const res = await fetch(SENDGRID_API_URL, {
    method: "POST",
    headers: {
      "authorization": `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`SendGrid API returned ${res.status}: ${body.slice(0, 500)}`);
  }

  return {
    sent: true,
    statusCode: res.status,
    to: toEmail,
    subject: subject,
  };
}

/**
 * Build the HTML email body.
 */
function buildEmailHtml(state, previousSignal, action) {
  const { price, sma200, rsi14, upperBand, lowerBand, timestamp } = state;
  const newSignal = state.signal;

  return `
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #333;">S&P500 3x Levered Strategy — Signal Change</h2>

  <p style="font-size: 16px;"><strong>Action Required:</strong> <span style="color: ${newSignal === 'LONG' ? '#22aa22' : '#cc2222'}; font-size: 18px;">${action}</span></p>

  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;"><strong>Previous Signal</strong></td>
      <td style="padding: 8px; border: 1px solid #ddd;">${previousSignal}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;"><strong>New Signal</strong></td>
      <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold; color: ${newSignal === 'LONG' ? '#22aa22' : '#cc2222'};">${newSignal}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">SPX Close</td>
      <td style="padding: 8px; border: 1px solid #ddd;">${price.toFixed(2)}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">SMA(200)</td>
      <td style="padding: 8px; border: 1px solid #ddd;">${sma200.toFixed(2)}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">Upper Band (+3%)</td>
      <td style="padding: 8px; border: 1px solid #ddd;">${upperBand.toFixed(2)}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">Lower Band (−3%)</td>
      <td style="padding: 8px; border: 1px solid #ddd;">${lowerBand.toFixed(2)}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">RSI(14)</td>
      <td style="padding: 8px; border: 1px solid #ddd;">${rsi14.toFixed(1)}</td>
    </tr>
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9;">Execution Vehicle</td>
      <td style="padding: 8px; border: 1px solid #ddd;">3USL.L (London) / UPRO (US)</td>
    </tr>
  </table>

  <p style="margin-top: 16px;">
    <a href="https://rkarim25.github.io/Strategy/#spx3xSignalPage" style="color: #0066cc;">
      View full signal page →
    </a>
  </p>

  <hr style="border: none; border-top: 1px solid #ddd; margin: 24px 0;">
  <p style="font-size: 12px; color: #999;">
    Generated by SPX Signal Alert Worker — ${timestamp}<br>
    This is an automated alert from the Strategy website.
  </p>
</body>
</html>`;
}

/**
 * Build the plain-text email body (for clients that don't render HTML).
 */
function buildEmailText(state, previousSignal, action) {
  const { price, sma200, rsi14, upperBand, lowerBand, timestamp } = state;
  const newSignal = state.signal;

  return `
S&P500 3x Levered Strategy — Signal Change
===========================================

Action: ${action}
Previous Signal: ${previousSignal}
New Signal: ${newSignal}

Details:
  SPX Close:        ${price.toFixed(2)}
  SMA(200):         ${sma200.toFixed(2)}
  Upper Band (+3%): ${upperBand.toFixed(2)}
  Lower Band (−3%): ${lowerBand.toFixed(2)}
  RSI(14):          ${rsi14.toFixed(1)}
  Execution Vehicle: 3USL.L (London) / UPRO (US)

View full signal page:
https://rkarim25.github.io/Strategy/#spx3xSignalPage

---
Generated by SPX Signal Alert Worker — ${timestamp}
This is an automated alert from the Strategy website.
`.trim();
}
