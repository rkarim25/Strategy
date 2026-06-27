/**
 * lab-strategy-store — tiny KV-backed store for the Strategy Lab's "Save to cloud".
 *
 *   POST /api/strategy   body {name?, notes?, config}  -> { id }    (persists; server-side, cross-device)
 *   GET  /api/strategy/:id                              -> { name, notes, config, savedAt }
 *
 * KV binding: LAB (namespace "lab-strategies"). CORS open (data is public strategy configs, no PII).
 * Deployed separately from spx-quote-proxy via wrangler.lab-store.toml.
 */
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};
const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...CORS } });
function newId(n = 8) {
  const alpha = "abcdefghijkmnpqrstuvwxyz23456789"; // no l/o/0/1 to avoid confusion
  const r = crypto.getRandomValues(new Uint8Array(n));
  let s = "";
  for (let i = 0; i < n; i++) s += alpha[r[i] % alpha.length];
  return s;
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(req.url);
    const m = url.pathname.match(/^\/api\/strategy\/([a-z2-9]{4,16})$/i);
    try {
      if (req.method === "GET" && m) {
        const v = await env.LAB.get("s:" + m[1].toLowerCase());
        if (!v) return json({ error: "not found" }, 404);
        return json(JSON.parse(v));
      }
      if (req.method === "POST" && url.pathname === "/api/strategy") {
        let body;
        try { body = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
        const cfg = body && body.config;
        if (!cfg || !cfg.entry || !cfg.exit || !Array.isArray(cfg.entry.conds) || !Array.isArray(cfg.exit.conds))
          return json({ error: "bad config" }, 400);
        const rec = {
          name: String(body.name || "").slice(0, 120),
          notes: String(body.notes || "").slice(0, 4000),
          config: cfg,
          savedAt: new Date().toISOString().slice(0, 10),
        };
        const payload = JSON.stringify(rec);
        if (payload.length > 50000) return json({ error: "too large" }, 413);
        let key, tries = 0;
        do { key = newId(8); tries++; } while ((await env.LAB.get("s:" + key)) && tries < 6);
        await env.LAB.put("s:" + key, payload);
        return json({ id: key });
      }
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};
