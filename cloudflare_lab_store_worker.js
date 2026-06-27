/**
 * lab-strategy-store — tiny KV-backed store for the Strategy Lab's "Save to cloud".
 *
 *   POST /api/strategy   body {name?, notes?, config}  -> { id }    (persists; server-side, cross-device)
 *   GET  /api/strategy/:id                              -> { name, notes, config, savedAt }   (public read)
 *   POST /api/chart/:asset  body {notes?, drawings?, settings?}  -> { ok }   (gated: write)
 *   GET  /api/chart/:asset                              -> {notes,drawings,settings,savedAt}|{}  (gated: PRIVATE read)
 *
 * KV binding: LAB (namespace "lab-strategies"). Strategy shares are public; chart notes are
 * passphrase-gated for BOTH read and write so a visitor never sees the owner's private annotations.
 * Deployed separately from spx-quote-proxy via wrangler.lab-store.toml.
 */
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type,X-Lab-Key",
  "Access-Control-Max-Age": "86400",
};
const authed = (req, env) => !!(env.LAB_SECRET && (req.headers.get("X-Lab-Key") || "").trim() === String(env.LAB_SECRET).trim());
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
    const cm = url.pathname.match(/^\/api\/chart\/([a-z0-9_]{1,32})$/i);
    try {
      if (cm) {                                  // private per-asset chart notes + drawings
        if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
        const k = "chart:" + cm[1].toLowerCase();
        if (req.method === "GET") {
          const v = await env.LAB.get(k);
          return json(v ? JSON.parse(v) : {});
        }
        if (req.method === "POST") {
          let body;
          try { body = await req.json(); } catch (_) { return json({ error: "bad json" }, 400); }
          const rec = {
            notes: String((body && body.notes) || "").slice(0, 20000),
            drawings: Array.isArray(body && body.drawings) ? body.drawings.slice(0, 500) : [],
            settings: (body && body.settings && typeof body.settings === "object") ? body.settings : {},
            savedAt: new Date().toISOString().slice(0, 19) + "Z",
          };
          const payload = JSON.stringify(rec);
          if (payload.length > 300000) return json({ error: "too large" }, 413);
          await env.LAB.put(k, payload);
          return json({ ok: true, savedAt: rec.savedAt });
        }
        return json({ error: "method" }, 405);
      }
      if (req.method === "GET" && m) {
        const v = await env.LAB.get("s:" + m[1].toLowerCase());
        if (!v) return json({ error: "not found" }, 404);
        return json(JSON.parse(v));
      }
      if (req.method === "POST" && url.pathname === "/api/auth") {
        return json({ ok: authed(req, env) }, authed(req, env) ? 200 : 401);
      }
      if (req.method === "POST" && url.pathname === "/api/strategy") {
        if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
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
