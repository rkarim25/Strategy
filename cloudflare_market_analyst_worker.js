/**
 * Cloudflare Worker — one-click Analyst (optional, for the inline AI narrative on the website).
 *
 * The website Analyst button works WITHOUT this worker (deterministic quant report + copy-prompt).
 * Deploy this only to make the Claude-written narrative render inline with one click.
 *
 * Deploy:
 *   1. wrangler deploy  (needs a wrangler.toml naming this as the worker entry — see docs/oneclick-analyst.md)
 *   2. wrangler secret put ANTHROPIC_API_KEY   (paste your key from console.anthropic.com)
 *   3. In price.js set  const ANALYST_WORKER = "https://<your-worker>.workers.dev";  and bump price.js?v=
 *
 * The system prompt is fetched from the canonical site so the analyst "brain" stays single-sourced
 * (edit analyst_prompt.md once; the skill, the website copy-prompt, and this worker all follow it).
 */

const PROMPT_URL = "https://rkarim25.github.io/Strategy/analyst_prompt.md";
const ALLOW_ORIGINS = ["https://rkarim25.github.io"]; // add custom domains here
const DEFAULT_MODEL = "claude-sonnet-4-6"; // quality/cost balance; "claude-opus-4-8" for max quality

function cors(origin) {
  const ok = ALLOW_ORIGINS.includes(origin) ? origin : ALLOW_ORIGINS[0];
  return { "Access-Control-Allow-Origin": ok, "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type" };
}
function json(o, status, h) { return new Response(JSON.stringify(o), { status: status || 200, headers: Object.assign({ "Content-Type": "application/json" }, h) }); }

export default {
  async fetch(request, env) {
    const h = cors(request.headers.get("Origin") || "");
    if (request.method === "OPTIONS") return new Response(null, { headers: h });
    if (request.method !== "POST") return new Response("POST the analyst_bundle JSON", { status: 405, headers: h });
    if (!env.ANTHROPIC_API_KEY) return json({ error: "ANTHROPIC_API_KEY not set (wrangler secret put ANTHROPIC_API_KEY)" }, 500, h);

    let bundle;
    try { bundle = await request.json(); } catch (_) { return json({ error: "invalid JSON body" }, 400, h); }
    if (!bundle || !bundle.assets) return json({ error: "body is not an analyst_bundle" }, 400, h);

    // Fetch the canonical system prompt (single source of the analyst brain).
    let system = "You are a disciplined systematic-markets analyst. Produce a concise, honest market assessment and action plan from the provided analyst_bundle JSON.";
    try { const pr = await fetch(PROMPT_URL, { cf: { cacheTtl: 600 } }); if (pr.ok) system = await pr.text(); } catch (_) {}

    // Pull the chart screenshot out of the bundle and send it as a vision block (Claude is multimodal).
    const img = typeof bundle.chart_image === "string" ? bundle.chart_image : null;
    const slim = Object.assign({}, bundle); delete slim.chart_image;
    const content = [{ type: "text", text: "Here is the live analyst_bundle:\n\n```json\n" + JSON.stringify(slim) + "\n```\n\nProduce the assessment now, following the system prompt." }];
    const m = img && img.indexOf("base64,") >= 0 ? img.slice(img.indexOf("base64,") + 7) : null;
    if (m) content.push({ type: "image", source: { type: "base64", media_type: "image/png", data: m } });
    const payload = { model: env.MODEL || DEFAULT_MODEL, max_tokens: 1800, system, messages: [{ role: "user", content }] };

    let resp;
    try {
      resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "x-api-key": env.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (e) { return json({ error: "upstream fetch failed: " + (e.message || e) }, 502, h); }

    if (!resp.ok) { const t = await resp.text(); return json({ error: "claude api " + resp.status, detail: t.slice(0, 400) }, 502, h); }
    const data = await resp.json();
    const markdown = (data.content || []).map((b) => b.text || "").join("").trim();
    return json({ markdown, model: payload.model }, 200, h);
  },
};
