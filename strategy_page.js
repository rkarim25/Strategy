/**
 * Shared full-parity strategy page renderer.
 *
 * A thin host page sets `window.STRATEGY_DATA_URL` (a *_site_data.json) and
 * `window.STRATEGY_PAGE_TITLE`, includes site-nav.js then this file. This builds the
 * full Signal / Back-test / Monte-Carlo experience (current signal, KPI cards,
 * interactive equity + price/SMA charts with on-chart signal markers, a rebased
 * %-return window chart, a manual-price check, comparison table, Monte-Carlo) from the
 * precomputed payload — works for both band (S&P Water) and golden-cross (Nasdaq) data.
 */
(function () {
  "use strict";
  const DATA_URL = window.STRATEGY_DATA_URL;
  const ACCENT = "#0071e3";
  const WORKER_QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=quote&symbol=";

  // Fetch a live intraday quote with a TICKER-MATCH SAFEGUARD: if the worker returns a
  // different ticker than expected (e.g. a stale worker serving ^GSPC for everything),
  // reject it so the page falls back to the last completed close instead of a wrong price.
  async function fetchLiveQuote(symbol, expectedTicker) {
    try {
      const r = await fetch(WORKER_QUOTE + encodeURIComponent(symbol) + "&_=" + Date.now(), { cache: "no-store" });
      if (!r.ok) return null;
      const j = await r.json();
      const price = Number(j.price ?? j.close ?? j.last);
      if (!Number.isFinite(price) || price <= 0) return null;
      if (expectedTicker && j.ticker && String(j.ticker) !== expectedTicker) return null;
      return { price, ts: j.timestamp || null };
    } catch (_) { return null; }
  }

  function smaLast(arr, n) {
    const v = arr.filter((x) => x != null && isFinite(x));
    if (v.length < n) return NaN;
    let s = 0; for (let i = v.length - n; i < v.length; i++) s += v[i];
    return s / n;
  }

  // RSI of the last `period` deltas (simple averaging) — used by the S&P Octane RSI-exit rule.
  function rsiLast(arr, period) {
    const v = arr.filter((x) => x != null && isFinite(x));
    if (v.length < period + 1) return NaN;
    let gain = 0, loss = 0;
    for (let i = v.length - period; i < v.length; i++) {
      const d = v[i] - v[i - 1];
      if (d >= 0) gain += d; else loss -= d;
    }
    if (loss === 0) return 100;
    return 100 - 100 / (1 + (gain / period) / (loss / period));
  }

  // Recompute current leverage from a live/manual close, per strategy family.
  function liveLeverage(d, livePrice, liveVix, priorLev) {
    const p = d.price_sma_data || {}, sp = d.strategy_params || {};
    const closes = (p.spx_close || []).concat([livePrice]);
    if (p.sma200_upper_band) {                       // band strategy (S&P Water/Octane)
      const w = sp.sma_window || 200, band = sp.band_pct || 0.03, lev = sp.leverage || 1;
      const sma = smaLast(closes, w);
      if (!isFinite(sma)) return priorLev;
      if (livePrice > sma * (1 + band)) return lev;
      if (livePrice < sma * (1 - band)) {
        // Octane RSI exit-block: stay invested while the recent regime is oversold (RSI < threshold)
        // rather than going to cash. RSI is taken from the real close history (not the hypothetical
        // manual/live point) so a far-off manual price doesn't distort it into a fake oversold reading.
        if (sp.rsi_threshold && rsiLast(p.spx_close || [], sp.rsi_period || 14) < sp.rsi_threshold) return priorLev;
        return 0;
      }
      return priorLev;                               // hysteresis: hold prior state in-band
    }
    if (p.sma50 && p.sma200) {                        // golden cross (Nasdaq Water*/Octane*)
      if (smaLast(closes, 50) <= smaLast(closes, 200)) return 0;
      if (!sp.octane) return 1;
      const peak = Math.max(...closes.filter((x) => x != null && isFinite(x)));
      const dd = livePrice / peak - 1;
      if (liveVix == null) return priorLev >= 2 ? 2 : 1;   // no live VIX yet: keep prior bump
      return (liveVix < 20 && dd > -0.12) ? 2 : 1;
    }
    if (p.sma_main) {                                 // generic SMA cross 1x/cash (Water sma-cash family)
      const w = sp.sma_window || 20;
      const sma = smaLast(closes, w);
      if (!isFinite(sma)) return priorLev;
      return livePrice > sma ? (sp.leverage || 1) : 0;
    }
    if (p.sma20) {                                    // Guarded SMA20-lead family (max 1x)
      const w = sp.sma_window || 20;
      const sma = smaLast(closes, w);
      if (!isFinite(sma)) return priorLev;
      const lead = sp.lead_pct_below_sma20 != null ? sp.lead_pct_below_sma20 : 0.0075;
      const cap = sp.max_leverage || 1;
      if (livePrice >= sma) return Math.min(1, cap);
      if (livePrice >= sma * (1 - lead)) return priorLev;   // within lead guard: hold prior state
      return 0;
    }
    return priorLev;
  }

  const fmt = (v) => (v == null || v === "" ? "—" : v);
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const fmtLev = (x) => (Number(x) > 0 ? `${Number(x).toFixed(0)}x` : "0x");
  const fmtNum = (v) => (v == null || !isFinite(v) ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

  // Colour for a leverage transition marker. Up moves (enter/add) green→blue by size; down moves
  // (reduce/exit) orange→red (red when going fully to cash).
  function markerColor(prevLev, nextLev) {
    const up = nextLev > prevLev;
    if (up) return nextLev >= 2 ? "#2563eb" : "#15803d";
    return nextLev === 0 ? "#b42318" : "#b45309";
  }

  // Build on-chart markers from signal_history: one per leverage transition. Each carries the
  // date (used to locate it on whichever chart), direction, colour, short label and a tooltip.
  function buildMarkers(d) {
    const sh = d.signal_history || [];
    const out = [];
    let prev = null;
    for (let i = 0; i < sh.length; i++) {
      const lev = Number(sh[i].leverage) || 0;
      if (prev === null) { prev = lev; continue; }
      if (lev !== prev) {
        const up = lev > prev;
        const close = sh[i].spx_close;
        // P&L to the next reduce (for an entry/add), measured on the index close.
        let pnl = null;
        if (up && close) {
          for (let j = i + 1; j < sh.length; j++) {
            if ((Number(sh[j].leverage) || 0) < lev) { if (sh[j].spx_close) pnl = sh[j].spx_close / close - 1; break; }
          }
        }
        out.push({
          date: sh[i].date,
          dir: up ? "up" : "down",
          color: markerColor(prev, lev),
          label: fmtLev(lev),
          tip: `<b>${fmtLev(prev)} → ${fmtLev(lev)}</b><br>${esc(sh[i].date)}<br>${up ? "Enter / add" : "Reduce / exit"}`
            + (close ? `<br>close ${fmtNum(close)}` : "")
            + (pnl != null ? `<br>P&amp;L to next reduce ${(pnl >= 0 ? "+" : "") + (pnl * 100).toFixed(1)}%` : ""),
        });
        prev = lev;
      }
    }
    return out;
  }

  // ---- shared hover tooltip ----
  let tipEl = null;
  function tooltip() {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "sp-tip"; tipEl.style.display = "none"; document.body.appendChild(tipEl); }
    return tipEl;
  }

  function setBanner(lev, asOf, live) {
    const el = document.getElementById("signalBanner"); if (!el) return;
    const isLong = lev > 0;
    el.innerHTML = `<div class="signal-banner ${isLong ? "long" : "cash"}">
      <div><div class="big">${isLong ? `IN — ${lev.toFixed(0)}× exposure` : "CASH"}</div>
      <div class="sub">${live ? "● LIVE" : "Last close"} · ${esc(asOf)}</div></div></div>`;
  }

  // Recompute + display the signal at a given price (shared by live auto-refresh and the manual box).
  async function showSignalAtPrice(d, sig, price, { live = false, ts = null } = {}) {
    const q = window.STRATEGY_QUOTE;
    const priorLev = sig ? Number(sig.leverage) : 0;
    let liveVix = null;
    if ((d.strategy_params || {}).octane) { const v = await fetchLiveQuote("vix", "^VIX"); liveVix = v ? v.price : null; }
    const lev = liveLeverage(d, price, liveVix, priorLev);
    const when = ts ? new Date(ts).toLocaleString() : new Date().toLocaleString();
    const tickerLbl = q && q.ticker ? q.ticker + " " : "";
    setBanner(lev, `${live ? "live" : "manual"} ${tickerLbl}${fmtNum(price)} · ${when}`, live);
    return lev;
  }

  async function maybeGoLive(d, sig) {
    const q = window.STRATEGY_QUOTE, note = document.getElementById("signalNote");
    if (!q) { if (note) note.textContent = "Static signal."; return; }
    const run = async () => {
      const quote = await fetchLiveQuote(q.symbol, q.ticker);
      if (!quote) {
        if (note) note.textContent = "Live quote not available for this asset yet — showing the last completed close. It will go live automatically once the quote worker is deployed for it.";
        return;
      }
      await showSignalAtPrice(d, sig, quote.price, { live: true, ts: quote.ts });
      if (note) note.textContent = "Live intraday quote via the Cloudflare proxy; auto-refreshes every 30 min during UK LSE hours. Falls back to last close if unavailable.";
    };
    await run();
    window.SiteNav?.registerAutoRefresh?.(run, 30 * 60 * 1000);
  }

  function injectStyles() {
    if (document.getElementById("strategy-page-styles")) return;
    const s = document.createElement("style");
    s.id = "strategy-page-styles";
    s.textContent = `
      :root{color-scheme:light;--bg:#f5f5f7;--panel:rgba(255,255,255,.8);--text:#1d1d1f;--muted:#6e6e73;
        --line:rgba(0,0,0,.10);--accent:#0071e3;--good:#248a3d;--bad:#d70015;--shadow:0 18px 45px rgba(0,0,0,.08);}
      *{box-sizing:border-box;} html{scroll-behavior:smooth;}
      body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
        background:radial-gradient(circle at top left,rgba(0,113,227,.12),transparent 32rem),linear-gradient(180deg,#fbfbfd,var(--bg) 42%,#fff);
        color:var(--text);-webkit-font-smoothing:antialiased;}
      main{margin:40px auto 72px;}
      h1{margin:0 0 6px;font-size:clamp(28px,4.4vw,46px);letter-spacing:-.04em;font-weight:800;line-height:1.04;}
      h2{margin:0 0 8px;font-size:19px;letter-spacing:-.02em;}
      p{color:var(--muted);line-height:1.55;}
      .lede{font-size:16px;max-width:74ch;}
      .card{border:1px solid var(--line);border-radius:22px;background:var(--panel);padding:20px 22px;
        box-shadow:var(--shadow);backdrop-filter:blur(20px);margin:18px 0;}
      .tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 6px;}
      .tabs button{font:inherit;font-size:14px;font-weight:600;padding:9px 18px;border-radius:999px;border:1px solid var(--line);
        background:#fff;color:var(--text);cursor:pointer;transition:.15s;}
      .tabs button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .view{display:none;} .view.active{display:block;}
      .signal-banner{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:18px 22px;border-radius:18px;color:#fff;}
      .signal-banner.long{background:linear-gradient(120deg,#248a3d,#1c6e31);}
      .signal-banner.cash{background:linear-gradient(120deg,#6e6e73,#4b4b50);}
      .signal-banner .big{font-size:30px;font-weight:800;letter-spacing:-.02em;}
      .signal-banner .sub{font-size:13px;opacity:.92;}
      .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:6px;}
      .kpi{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:#fff;}
      .kpi .k{font-size:12px;color:var(--muted);font-weight:600;} .kpi .v{font-size:22px;font-weight:800;letter-spacing:-.02em;margin-top:2px;}
      .kpi .vs{font-size:11.5px;color:var(--muted);margin-top:2px;}
      table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;margin-top:6px;}
      th,td{padding:8px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;}
      th{color:var(--muted);font-weight:600;font-size:12px;} th.l,td.l{text-align:left;}
      td.num{font-variant-numeric:tabular-nums;} .neg{color:var(--bad);} .pos{color:var(--good);}
      tr.me td{background:rgba(0,113,227,.06);font-weight:600;}
      .tbl-wrap{overflow-x:auto;}
      .chartwrap{position:relative;width:100%;margin-top:8px;} canvas{width:100%;height:auto;display:block;}
      .ranges{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0;align-items:center;}
      .ranges button{font:inherit;font-size:12px;padding:5px 12px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .ranges button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .ranges input[type=date]{font:inherit;font-size:12px;padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:#fff;}
      .ranges .sep{width:1px;height:18px;background:var(--line);margin:0 2px;}
      .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px;}
      .legend span{display:inline-flex;align-items:center;gap:6px;} .legend i{width:14px;height:3px;border-radius:2px;display:inline-block;}
      .meta{font-size:12.5px;color:var(--muted);line-height:1.5;}
      .err{color:var(--bad);font-weight:600;}
      .manual{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:4px;}
      .manual input{font:inherit;font-size:14px;padding:8px 12px;border-radius:10px;border:1px solid var(--line);background:#fff;width:160px;}
      .manual button{font:inherit;font-size:13px;font-weight:600;padding:8px 16px;border-radius:10px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;}
      .manual button.ghost{background:#fff;color:var(--text);border-color:var(--line);}
      .sp-tip{position:fixed;z-index:9999;pointer-events:none;background:#1d1d1f;color:#fff;font-size:12px;line-height:1.4;
        padding:7px 10px;border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.22);max-width:240px;}
    `;
    document.head.appendChild(s);
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  // ---- canvas line chart ----
  // series: [{label,color,width,values}]  markers: [{i,value,dir,color,label,tip}] (already sliced to local i)
  function lineChart(canvas, dates, series, { log = false, pct = false, markers = [] } = {}) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth || 900, H = 320;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const padL = 56, padR = 12, padT = 16, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (const v of s.values) if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (!isFinite(lo) || !isFinite(hi)) { canvas.__hits = []; return; }
    if (pct) { const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad; }       // breathing room for % charts
    const tf = (v) => (log ? Math.log10(Math.max(v, 1e-9)) : v);
    let tlo = tf(lo), thi = tf(hi); if (tlo === thi) thi = tlo + 1;
    const n = dates.length;
    const xAt = (i) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const yAt = (v) => padT + plotH - ((tf(v) - tlo) / (thi - tlo)) * plotH;
    const fmtY = (val) => pct ? `${val >= 0 ? "+" : ""}${val.toFixed(Math.abs(val) < 10 ? 1 : 0)}%`
      : (val >= 1000 ? Math.round(val).toLocaleString() : val.toFixed(val < 10 ? 1 : 0));
    // gridlines + y labels
    ctx.strokeStyle = "rgba(0,0,0,.07)"; ctx.fillStyle = "#6e6e73"; ctx.font = "11px system-ui"; ctx.textAlign = "right";
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * plotH;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      const tv = thi - (g / 4) * (thi - tlo); const val = log ? Math.pow(10, tv) : tv;
      ctx.fillText(fmtY(val), padL - 6, y + 3);
    }
    // zero baseline for % charts
    if (pct && lo < 0 && hi > 0) {
      const yz = yAt(0); ctx.strokeStyle = "rgba(0,0,0,.28)"; ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(padL, yz); ctx.lineTo(W - padR, yz); ctx.stroke(); ctx.setLineDash([]);
    }
    // x ticks + labels (adaptive count ~1 per 90px; MM-DD for short spans, else YYYY-MM)
    ctx.textAlign = "center";
    const nT = Math.max(2, Math.min(9, Math.floor(plotW / 90)));
    const shortSpan = n <= 95;
    for (let t = 0; t <= nT; t++) {
      const i = n <= 1 ? 0 : Math.round((t / nT) * (n - 1));
      if (i < 0 || i >= n || !dates[i]) continue;
      const x = xAt(i);
      ctx.strokeStyle = "rgba(0,0,0,.14)"; ctx.beginPath(); ctx.moveTo(x, padT + plotH); ctx.lineTo(x, padT + plotH + 4); ctx.stroke();
      ctx.fillStyle = "#6e6e73"; ctx.fillText(String(dates[i]).slice(shortSpan ? 5 : 0, shortSpan ? 10 : 7), x, H - 6);
    }
    for (const s of series) {
      ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 1.6; ctx.beginPath();
      let started = false;
      for (let i = 0; i < n; i++) {
        const v = s.values[i];
        if (v == null || !isFinite(v)) { started = false; continue; }
        const x = xAt(i), y = yAt(v);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    // markers
    const hits = [];
    for (const m of markers) {
      if (m.value == null || !isFinite(m.value) || m.i < 0 || m.i >= n) continue;
      const x = xAt(m.i), y = yAt(m.value), up = m.dir === "up";
      ctx.fillStyle = m.color;
      ctx.beginPath();
      if (up) { ctx.moveTo(x, y - 1); ctx.lineTo(x - 4, y - 7); ctx.lineTo(x + 4, y - 7); }
      else { ctx.moveTo(x, y + 1); ctx.lineTo(x - 4, y + 7); ctx.lineTo(x + 4, y + 7); }
      ctx.closePath(); ctx.fill();
      ctx.font = "700 10px system-ui";
      const tw = ctx.measureText(m.label).width, pw = tw + 10, ph = 15;
      const px = Math.min(Math.max(x - pw / 2, padL), W - padR - pw);
      const py = up ? y - 7 - ph : y + 7;
      roundRect(ctx, px, py, pw, ph, 4); ctx.fillStyle = "#fff"; ctx.fill();
      ctx.strokeStyle = m.color; ctx.lineWidth = 1; ctx.stroke();
      ctx.fillStyle = m.color; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(m.label, px + pw / 2, py + ph / 2 + 0.5);
      ctx.textBaseline = "alphabetic";
      hits.push({ x: px + pw / 2, y: py + ph / 2, r: Math.max(11, pw / 2 + 2), html: m.tip });
    }
    canvas.__hits = hits;
    canvas.__geo = { padL, padR, plotW, n };   // so the hover handler maps mouse-x → bar index exactly as xAt does
    // crosshair + value readout (set canvas.__hoverI / __hoverY on mousemove, then redraw)
    const hvI = canvas.__hoverI, hvY = canvas.__hoverY;
    if (hvI != null && hvI >= 0 && hvI < n) {
      const cx = xAt(hvI);
      ctx.save();
      ctx.strokeStyle = "rgba(0,0,0,.34)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(cx, padT); ctx.lineTo(cx, padT + plotH); ctx.stroke();
      if (hvY != null && hvY >= padT && hvY <= padT + plotH) {
        ctx.beginPath(); ctx.moveTo(padL, hvY); ctx.lineTo(W - padR, hvY); ctx.stroke(); ctx.setLineDash([]);
        const tv = thi - ((hvY - padT) / plotH) * (thi - tlo), yval = log ? Math.pow(10, tv) : tv;
        ctx.fillStyle = "#1d1d1f"; roundRect(ctx, 1, hvY - 8, padL - 5, 16, 3); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.font = "10px system-ui"; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(fmtY(yval), padL - 6, hvY);
      }
      ctx.setLineDash([]);
      const rows = [];
      for (const s of series) { const v = s.values[hvI]; if (v == null || !isFinite(v)) continue; ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(cx, yAt(v), 3.2, 0, 2 * Math.PI); ctx.fill(); rows.push({ c: s.color, t: fmtY(v) }); }
      ctx.font = "11px system-ui"; ctx.textBaseline = "middle";
      const dlab = String(dates[hvI] || "");
      let bw = ctx.measureText(dlab).width + 14; rows.forEach((r) => (bw += ctx.measureText(r.t).width + 18));
      const bx = Math.min(Math.max(cx - bw / 2, padL), W - padR - bw), by = padT + 2, bh = 19;
      ctx.fillStyle = "rgba(255,255,255,.96)"; ctx.strokeStyle = "rgba(0,0,0,.14)"; ctx.lineWidth = 1; roundRect(ctx, bx, by, bw, bh, 5); ctx.fill(); ctx.stroke();
      ctx.textAlign = "left"; ctx.fillStyle = "#1d1d1f"; let tx = bx + 7; ctx.fillText(dlab, tx, by + bh / 2 + 0.5); tx += ctx.measureText(dlab).width + 11;
      rows.forEach((r) => { ctx.fillStyle = r.c; ctx.beginPath(); ctx.arc(tx + 3, by + bh / 2, 3, 0, 2 * Math.PI); ctx.fill(); ctx.fillStyle = "#1d1d1f"; ctx.fillText(r.t, tx + 9, by + bh / 2 + 0.5); tx += ctx.measureText(r.t).width + 18; });
      ctx.restore(); ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    }
  }

  // A chart card with range buttons, optional custom date pickers, optional %-rebasing and markers.
  // seriesDefs values are full-length, aligned to `dates`. markerDefs: [{date,dir,color,label,tip}].
  function chartBlock(title, dates, seriesDefs, opts = {}) {
    const { log = false, rebasePct = false, markerDefs = [], customDates = false, defaultRange = "Full",
      onWindow = null,
      ranges = [["1M", 21], ["3M", 63], ["1Y", 252], ["5Y", 1260], ["10Y", 2520], ["Full", dates.length]] } = opts;
    const dateIdx = new Map(); dates.forEach((dt, i) => dateIdx.set(dt, i));
    // Open at defaultRange (e.g. "1Y") so a rebased %-chart isn't a useless multi-decade scale;
    // fall back to Full if the data is shorter than that window.
    const _defDays = (ranges.find(([l]) => l === defaultRange) || ["Full", dates.length])[1];
    const _useDefault = defaultRange !== "Full" && _defDays <= dates.length;
    const _activeLbl = _useDefault ? defaultRange : "Full";
    const wrap = document.createElement("div"); wrap.className = "card";
    wrap.innerHTML = `<h2>${esc(title)}</h2>`;
    const cw = document.createElement("div"); cw.className = "chartwrap";
    const canvas = document.createElement("canvas"); cw.appendChild(canvas); wrap.appendChild(cw);
    const legend = document.createElement("div"); legend.className = "legend";
    let _series = seriesDefs, _mdefs = markerDefs;   // mutable so wrap.update() can swap data in place
    const renderLegend = () => { legend.innerHTML = _series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join(""); };
    renderLegend();
    wrap.appendChild(legend);

    let winHi = dates.length, winLo = _useDefault ? Math.max(0, dates.length - _defDays) : 0;
    let _suppressOW = false;   // suppress the onWindow callback while a sync sets the window externally
    const draw = () => {
      const lo = Math.max(0, winLo), hi = Math.min(dates.length, winHi);
      const dslice = dates.slice(lo, hi);
      const ser = _series.map((s) => {
        let vals = s.values.slice(lo, hi);
        if (rebasePct) {
          const base = vals.find((v) => v != null && isFinite(v));
          vals = base ? vals.map((v) => (v != null && isFinite(v) ? (v / base - 1) * 100 : null)) : vals;
        }
        return { color: s.color, width: s.width, values: vals };
      });
      const anchor = ser[0] ? ser[0].values : [];
      const markers = _mdefs.map((m) => {
        const gi = dateIdx.get(m.date); if (gi == null || gi < lo || gi >= hi) return null;
        const li = gi - lo; return { ...m, i: li, value: anchor[li] };
      }).filter(Boolean);
      lineChart(canvas, dslice, ser, { log, pct: rebasePct, markers });
      canvas.style.cursor = (winHi - winLo) < dates.length ? "grab" : "default";
      if (onWindow && !_suppressOW) onWindow(lo, hi);
    };
    // Pan the visible window left/right, keeping its width (time scroll). frac<0 = back, >0 = forward.
    const panBy = (frac) => {
      const w = winHi - winLo; if (w >= dates.length) return;
      let lo = winLo + Math.max(1, Math.round(Math.abs(w * frac))) * Math.sign(frac);
      lo = Math.max(0, Math.min(lo, dates.length - w));
      winLo = lo; winHi = lo + w; draw();
    };

    const rdiv = document.createElement("div"); rdiv.className = "ranges";
    const setActive = (btn) => rdiv.querySelectorAll("button[data-range]").forEach((x) => x.classList.toggle("active", x === btn));
    const mkPan = (txt, frac, ttl) => { const b = document.createElement("button"); b.className = "pan"; b.textContent = txt; b.title = ttl; b.onclick = () => panBy(frac); return b; };
    rdiv.appendChild(mkPan("‹", -0.5, "Scroll back in time"));
    rdiv.appendChild(mkPan("›", 0.5, "Scroll forward in time"));
    rdiv.appendChild(Object.assign(document.createElement("span"), { className: "sep" }));
    for (const [lbl, days] of ranges) {
      if (days > dates.length && lbl !== "Full") continue;
      const b = document.createElement("button"); b.dataset.range = lbl; b.textContent = lbl;
      if (lbl === _activeLbl) b.classList.add("active");
      b.onclick = () => { winHi = dates.length; winLo = Math.max(0, dates.length - days); if (customStart) { customStart.value = ""; customEnd.value = ""; } setActive(b); draw(); };
      rdiv.appendChild(b);
    }
    let customStart = null, customEnd = null;
    if (customDates) {
      const sep = document.createElement("span"); sep.className = "sep"; rdiv.appendChild(sep);
      customStart = document.createElement("input"); customStart.type = "date"; customStart.title = "Custom start date";
      customEnd = document.createElement("input"); customEnd.type = "date"; customEnd.title = "Custom end date";
      if (dates.length) { customStart.min = customEnd.min = dates[0]; customStart.max = customEnd.max = dates[dates.length - 1]; }
      const apply = document.createElement("button"); apply.textContent = "Apply dates";
      apply.onclick = () => {
        const s = customStart.value, e = customEnd.value; if (!s && !e) return;
        let lo = 0, hi = dates.length;
        if (s) { lo = dates.findIndex((dt) => dt >= s); if (lo < 0) lo = dates.length - 1; }
        if (e) { for (let i = dates.length - 1; i >= 0; i--) { if (dates[i] <= e) { hi = i + 1; break; } } }
        if (hi <= lo) hi = lo + 1;
        winLo = lo; winHi = hi; setActive(null); draw();
      };
      rdiv.appendChild(customStart); rdiv.appendChild(customEnd); rdiv.appendChild(apply);
    }
    wrap.appendChild(rdiv);

    // hover tooltip on markers + drag-to-pan (scroll time)
    let dragX = null, dragLo = 0;
    canvas.addEventListener("mousedown", (e) => {
      if ((winHi - winLo) >= dates.length) return;   // full view: nothing to scroll
      dragX = e.clientX; dragLo = winLo; canvas.style.cursor = "grabbing"; e.preventDefault();
    });
    window.addEventListener("mouseup", () => { if (dragX != null) { dragX = null; draw(); } });
    canvas.addEventListener("mousemove", (e) => {
      if (dragX != null && (e.buttons & 1)) {
        tooltip().style.display = "none"; canvas.__hoverI = null;
        const w = winHi - winLo, plotPx = (canvas.clientWidth - 68) || 1;   // padL+padR = 68
        let lo = dragLo - Math.round(((e.clientX - dragX) / plotPx) * w);
        lo = Math.max(0, Math.min(lo, dates.length - w));
        winLo = lo; winHi = lo + w; draw();
        return;
      }
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const geo = canvas.__geo;   // crosshair: snap to the nearest bar exactly as the renderer placed it
      if (geo && geo.n > 0 && mx >= geo.padL - 4 && mx <= geo.padL + geo.plotW + 4) { canvas.__hoverI = Math.max(0, Math.min(geo.n - 1, Math.round(((mx - geo.padL) / (geo.plotW || 1)) * (geo.n - 1)))); canvas.__hoverY = my; }
      else { canvas.__hoverI = null; canvas.__hoverY = null; }
      draw();
      const hit = (canvas.__hits || []).find((h) => Math.abs(mx - h.x) <= h.r && Math.abs(my - h.y) <= 11);
      const t = tooltip();
      if (hit) { t.innerHTML = hit.html; t.style.display = "block"; t.style.left = (e.clientX + 13) + "px"; t.style.top = (e.clientY + 13) + "px"; }
      else t.style.display = "none";
    });
    canvas.addEventListener("mouseleave", () => { tooltip().style.display = "none"; canvas.__hoverI = null; canvas.__hoverY = null; draw(); });

    setTimeout(draw, 0);
    window.addEventListener("resize", draw);
    // Live update: swap series/markers in place (same date axis) without losing the current window.
    wrap.update = (series, mdefs) => { if (series) _series = series; if (mdefs) _mdefs = mdefs; renderLegend(); draw(); };
    // Window get/set for cross-chart linking (setWindow won't re-fire onWindow, so syncs don't loop).
    wrap.getWindow = () => [winLo, winHi];
    wrap.setWindow = (lo, hi) => { _suppressOW = true; winLo = Math.max(0, lo); winHi = Math.min(dates.length, hi); setActive(null); draw(); _suppressOW = false; };
    return wrap;
  }

  function kpi(k, v, vs) {
    return `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${esc(fmt(v))}</div>${vs ? `<div class="vs">${esc(vs)}</div>` : ""}</div>`;
  }

  function render(d) {
    const app = document.getElementById("app");
    const sp = d.strategy_params || {};
    const name = sp.strategy || d.default_backtest?.strategy || "Strategy";
    const asset = d.asset_label || "";
    const db = d.default_backtest || {}, bh = d.buy_and_hold_1x || {};
    const sig = (d.signal_history && d.signal_history.length) ? d.signal_history[d.signal_history.length - 1] : null;
    const markerDefs = buildMarkers(d);

    app.innerHTML = `
      <h1>${esc(asset)} — ${esc(name)}</h1>
      <p class="lede">Backtest over ${esc(d.sample?.start_date || "")} → ${esc(d.sample?.end_date || "")}
        (${(d.sample?.trading_days || 0).toLocaleString()} sessions). 1-day signal lag, 0.10% trading cost,
        $100 + $10/yr. Default site pick for this asset.</p>
      <div class="tabs" id="secTabs">
        <button data-view="signal" class="active">Signal</button>
        <button data-view="backtest">Back-test</button>
        <button data-view="mc">Monte Carlo</button>
      </div>
      <div class="view active" id="view-signal"></div>
      <div class="view" id="view-backtest"></div>
      <div class="view" id="view-mc"></div>`;

    // --- Signal view ---
    const vs = document.getElementById("view-signal");
    const bann = document.createElement("div"); bann.className = "card";
    bann.innerHTML = `<div id="signalBanner"></div><p class="meta" id="signalNote" style="margin-top:10px"></p>`;
    vs.appendChild(bann);
    setBanner(sig ? Number(sig.leverage) : 0, sig ? `${esc(sig.date)} close ${sig.spx_close != null ? sig.spx_close.toLocaleString() : "—"}` : "—", false);
    maybeGoLive(d, sig);

    // manual price check
    const man = document.createElement("div"); man.className = "card";
    man.innerHTML = `<h2>Manual price check</h2>
      <div class="manual">
        <input id="manualPrice" type="number" step="any" inputmode="decimal" placeholder="Enter ${esc(asset)} level" />
        <button id="applyManual">Apply</button>
        <button id="clearManual" class="ghost">Reset to last close</button>
      </div>
      <p class="meta" id="manualNote">Type a current ${esc(asset)} level and click Apply to see the signal at that price (recomputes the current leverage only — not the historical backtest).</p>`;
    vs.appendChild(man);
    const applyManual = () => {
      const raw = parseFloat(document.getElementById("manualPrice").value);
      const note = document.getElementById("manualNote");
      if (!isFinite(raw) || raw <= 0) { if (note) note.textContent = "Enter a positive price level."; return; }
      showSignalAtPrice(d, sig, raw, { live: false }).then((lev) => {
        if (note) note.innerHTML = `At <b>${fmtNum(raw)}</b> the signal is <b>${lev > 0 ? "IN — " + lev.toFixed(0) + "× exposure" : "CASH"}</b>. Recomputes the current leverage only.`;
      });
    };
    man.querySelector("#applyManual").addEventListener("click", applyManual);
    man.querySelector("#manualPrice").addEventListener("keydown", (e) => { if (e.key === "Enter") applyManual(); });
    man.querySelector("#clearManual").addEventListener("click", () => {
      document.getElementById("manualPrice").value = "";
      setBanner(sig ? Number(sig.leverage) : 0, sig ? `${esc(sig.date)} close ${sig.spx_close != null ? sig.spx_close.toLocaleString() : "—"}` : "—", false);
      maybeGoLive(d, sig);
      const note = document.getElementById("manualNote");
      if (note) note.textContent = `Type a current ${asset} level and click Apply to see the signal at that price.`;
    });

    // --- Signal-change history, dynamically linked to the price chart's visible window ---
    const _sh = d.signal_history || [];
    const transitions = [];
    for (let i = 1; i < _sh.length; i++) {
      const lev = Number(_sh[i].leverage) || 0, prev = Number(_sh[i - 1].leverage) || 0;
      if (lev !== prev) transitions.push({ gi: i, date: _sh[i].date, prev, lev, close: _sh[i].spx_close });
    }
    function renderSignalHistory(lo, hi) {
      const cont = document.getElementById("sigHistBody"); if (!cont) return;
      const inWin = transitions.filter((t) => t.gi >= lo && t.gi < hi);
      const a = _sh[Math.max(0, lo)], b = _sh[Math.min(hi, _sh.length) - 1];
      const period = a && b ? `${a.date} → ${b.date}` : "";
      if (!inWin.length) {
        const lev = b ? Number(b.leverage) || 0 : 0;
        cont.innerHTML = `<p class="meta">No signal changes in the charted period (${esc(period)}) — ${lev > 0 ? "held " + lev.toFixed(0) + "× throughout" : "in cash throughout"}.</p>`;
        return;
      }
      const shown = inWin.slice(-30).reverse();
      const rows = shown.map((t) => `<tr><td class="l">${esc(t.date)}</td><td class="l">${t.lev > 0 ? "Long " + t.lev.toFixed(0) + "×" : "Cash"}</td><td class="num">${t.close != null ? t.close.toLocaleString() : "—"}</td><td class="l">${fmtLev(t.prev)} → ${fmtLev(t.lev)}</td></tr>`).join("");
      cont.innerHTML = `<div class="meta" style="margin-bottom:6px">${inWin.length} signal change${inWin.length !== 1 ? "s" : ""} in the charted period (${esc(period)})${inWin.length > shown.length ? ` · latest ${shown.length} shown` : ""}.</div><div class="tbl-wrap"><table><thead><tr><th class="l">Date</th><th class="l">New signal</th><th>Close</th><th class="l">Change</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }
    let _lastLo = -1, _lastHi = -1;
    function scheduleSignalHistory(lo, hi) {
      if (lo === _lastLo && hi === _lastHi) return;   // skip redundant redraws (e.g. unchanged drag frame)
      _lastLo = lo; _lastHi = hi;
      renderSignalHistory(lo, hi);
    }

    if (d.price_sma_data) {
      const p = d.price_sma_data, defs = [{ label: asset + " close", color: "#1d1d1f", values: p.spx_close }];
      if (p.sma200) defs.push({ label: "SMA200", color: ACCENT, values: p.sma200 });
      if (p.sma50) defs.push({ label: "SMA50", color: "#b26a00", values: p.sma50 });
      if (p.sma20) defs.push({ label: "SMA20", color: "#b26a00", values: p.sma20 });
      if (p.sma_main) defs.push({ label: "SMA" + (sp.sma_window || ""), color: "#b26a00", values: p.sma_main });
      if (p.sma200_upper_band) defs.push({ label: "Upper band", color: "rgba(36,138,61,.5)", values: p.sma200_upper_band });
      if (p.sma200_lower_band) defs.push({ label: "Lower band", color: "rgba(215,0,21,.5)", values: p.sma200_lower_band });
      vs.appendChild(chartBlock("Price & moving averages — with signal markers", p.dates, defs, { log: false, markerDefs, customDates: true, onWindow: scheduleSignalHistory }));
    }
    // Rebased %-equity P&L chart on the Signal view (price + equity together, with markers).
    if (d.equity_curve) {
      const e = d.equity_curve;
      vs.appendChild(chartBlock("Equity P&L vs buy & hold (% return, rebased to 0%)", e.dates, [
        { label: name, color: ACCENT, width: 2, values: e.strategy_equity },
        { label: "Buy & hold 1×", color: "#6e6e73", values: e.buy_hold_1x_equity },
      ], { rebasePct: true, customDates: true, markerDefs, defaultRange: "1Y" }));
    }
    // Signal-change table — filled (and updated) by the price chart's onWindow callback.
    if (_sh.length) {
      const c = document.createElement("div"); c.className = "card";
      c.innerHTML = `<h2>Signal changes — charted period</h2>
        <p class="meta" style="margin:0 0 8px">Follows the price chart above: change its range / scroll / dates to update.</p>
        <div id="sigHistBody"></div>`;
      vs.appendChild(c);
      renderSignalHistory(0, _sh.length);   // initial fill (price chart opens Full); refined once it draws
    }

    // --- Backtest view ---
    const vb = document.getElementById("view-backtest");
    const kc = document.createElement("div"); kc.className = "card";
    kc.innerHTML = `<h2>Back-test — full history</h2><div class="kpis">
      ${kpi("CAGR", db.cagr_pct, "B&H 1× " + fmt(bh.cagr_pct))}
      ${kpi("Max drawdown", db.max_drawdown_pct, "B&H 1× " + fmt(bh.max_drawdown_pct))}
      ${kpi("Sharpe", db.sharpe_fmt, "B&H 1× " + fmt(bh.sharpe_fmt))}
      ${kpi("Calmar", db.calmar_fmt)}
      ${kpi("Sortino", db.sortino_fmt)}
      ${kpi("Volatility", db.ann_volatility_pct)}
      ${kpi("End $ ($100→)", db.end_value_fmt, "B&H 1× " + fmt(bh.end_value_fmt))}
    </div>`;
    vb.appendChild(kc);
    if (d.equity_curve) {
      const e = d.equity_curve;
      // Absolute growth-of-$100 (log) for the long view (the rebased %-equity chart is on the Signal view).
      vb.appendChild(chartBlock("Growth of $100 (log scale)", e.dates, [
        { label: name, color: ACCENT, width: 2, values: e.strategy_equity },
        { label: "Buy & hold 1×", color: "#6e6e73", values: e.buy_hold_1x_equity },
      ], { log: true, customDates: true }));
    }
    if (d.comparison_table) {
      const rows = d.comparison_table.map((r) => {
        const me = r.strategy === name;
        return `<tr class="${me ? "me" : ""}"><td class="l">${esc(r.strategy)}</td><td class="num">${fmt(r.cagr_pct)}</td>
          <td class="num">${fmt(r.ann_volatility_pct)}</td><td class="num">${fmt(r.sharpe_fmt)}</td>
          <td class="num neg">${fmt(r.max_drawdown_pct)}</td><td class="num">${fmt(r.calmar_fmt)}</td><td class="num">${fmt(r.end_value_fmt)}</td></tr>`;
      }).join("");
      const c = document.createElement("div"); c.className = "card";
      c.innerHTML = `<h2>Comparison</h2><div class="tbl-wrap"><table><thead><tr><th class="l">Strategy</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>MaxDD</th><th>Calmar</th><th>End $</th></tr></thead><tbody>${rows}</tbody></table></div>`;
      vb.appendChild(c);
    }

    // --- Monte Carlo view ---
    const vm = document.getElementById("view-mc");
    const mc = d.monte_carlo || {};
    const mcc = document.createElement("div"); mcc.className = "card";
    mcc.innerHTML = `<h2>Monte Carlo — ${mc.n_sims || 0} paths × ${(mc.horizon_years || 0).toFixed(0)}yr block bootstrap</h2>
      <div class="kpis">
        ${kpi("Median CAGR", mc.median_cagr_pct, "10–90%: " + fmt(mc.p10_cagr_pct) + " … " + fmt(mc.p90_cagr_pct))}
        ${kpi("Median max DD", mc.median_max_drawdown_pct, "10–90%: " + fmt(mc.p10_max_drawdown_pct) + " … " + fmt(mc.p90_max_drawdown_pct))}
        ${kpi("P(DD worse −35%)", mc.prob_max_dd_worse_35pct_fmt)}
        ${kpi("P(DD worse −50%)", mc.prob_max_dd_worse_50pct_fmt)}
        ${kpi("P(end below start)", mc.prob_end_below_start_fmt)}
      </div>
      <p class="meta">Block-bootstrap resampling of historical daily returns (${esc(mc.method || "")}). Illustrative distribution, not a forecast.</p>`;
    vm.appendChild(mcc);

    // tab switching
    document.getElementById("secTabs").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-view]"); if (!b) return;
      document.querySelectorAll("#secTabs button").forEach((x) => x.classList.toggle("active", x === b));
      document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
      window.dispatchEvent(new Event("resize"));
    });
  }

  function boot() {
    injectStyles();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const app = document.getElementById("app");
    if (!DATA_URL) { app.innerHTML = '<p class="err">No STRATEGY_DATA_URL set.</p>'; return; }
    fetch(DATA_URL + "?v=" + Date.now(), { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(render)
      .catch((e) => { app.innerHTML = `<p class="err">Could not load ${esc(DATA_URL)} — ${esc(e.message)}</p>`; });
  }

  // Expose the chart engine + format helpers so other pages (e.g. the interactive Band Lab) can reuse
  // the exact same charts. `chartBlock(...)` returns a card element with a `.update(series, markers)` method.
  window.SP = { chartBlock, lineChart, kpi, esc, fmt, fmtLev, fmtNum, injectStyles };

  // Only auto-boot a strategy page when a data URL is set; otherwise we were loaded purely for window.SP.
  function start() { if (window.STRATEGY_DATA_URL) boot(); else injectStyles(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
