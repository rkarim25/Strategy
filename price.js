/**
 * Charts — a TradingView/Bloomberg-style charting workstation built on KLineChart (vendored v9.8.12).
 * Asset registry grouped by class (price_assets.json) · candle/bar/area types · linear/log/% axis ·
 * range presets · indicators (MA/EMA/BOLL/VOL/MACD/RSI) · drawing palette (trend/ray/h-line/v-line/
 * price/parallel/fibonacci/text) + a custom "Measure %" overlay · live last price via the quote proxy ·
 * private per-asset notes + drawings saved to the passphrase-gated Cloudflare store (localStorage fallback).
 */
(function () {
  "use strict";
  const QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev";
  const STORE = "https://lab-strategy-store.rkarim88.workers.dev";
  const CLOUD_KEY = "lab_cloud_key"; // shared passphrase login with the Lab
  const UP = "#15803d", DN = "#b42318";
  const RANGES = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["2Y", 504], ["5Y", 1260], ["Max", null]];
  // intraday timeframes (Yahoo via the quote proxy); 1D = the static full-history file
  const TFS = [
    { id: "1m", label: "1m", interval: "1m", range: "7d", show: 180 },
    { id: "5m", label: "5m", interval: "5m", range: "60d", show: 160 },
    { id: "15m", label: "15m", interval: "15m", range: "60d", show: 170 },
    { id: "1h", label: "1h", interval: "60m", range: "730d", show: 200 },
    { id: "D", label: "1D", interval: null },
  ];
  const POLL_MS = 60000;
  const TYPES = [["candle_solid", "Candles"], ["ohlc", "Bars"], ["area", "Area"]];
  const AXES = [["normal", "Linear"], ["log", "Log"], ["percentage", "%"]];
  const MAIN_INDS = [["MA", "MA"], ["EMA", "EMA"], ["BOLL", "Bollinger"]];
  const SUB_INDS = [["VOL", "Volume"], ["MACD", "MACD"], ["RSI", "RSI"]];
  const TOOLS = [
    ["cursor", "Cursor", null], ["segment", "Trend line", "segment"], ["rayLine", "Ray", "rayLine"],
    ["horizontalStraightLine", "Horizontal", "horizontalStraightLine"], ["verticalStraightLine", "Vertical", "verticalStraightLine"],
    ["priceLine", "Price line", "priceLine"], ["parallelStraightLine", "Parallel", "parallelStraightLine"],
    ["fibonacciLine", "Fibonacci", "fibonacciLine"], ["simpleAnnotation", "Text", "simpleAnnotation"],
    ["measurePct", "Measure %", "measurePct"],
  ];
  const nfmt = (x) => (x == null || !isFinite(x) ? "—" : Math.abs(x) < 10 ? x.toLocaleString(undefined, { maximumFractionDigits: 4 }) : x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---- custom "Measure %" overlay: 2 points -> box + Δ% / Δprice / bars / days ----
  function registerMeasure() {
    if (!window.klinecharts || !klinecharts.registerOverlay) return;
    klinecharts.registerOverlay({
      name: "measurePct", totalStep: 3, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
      createPointFigures: ({ overlay, coordinates }) => {
        if (coordinates.length < 2) return [];
        const p = overlay.points; const v0 = p[0].value, v1 = p[1].value;
        if (v0 == null || v1 == null) return [];
        const diff = v1 - v0, pct = v0 ? (diff / v0) * 100 : 0, up = diff >= 0;
        const days = (p[0].timestamp != null && p[1].timestamp != null) ? Math.round(Math.abs(p[1].timestamp - p[0].timestamp) / 864e5) : null;
        const bars = (p[0].dataIndex != null && p[1].dataIndex != null) ? Math.abs(p[1].dataIndex - p[0].dataIndex) : null;
        const c0 = coordinates[0], c1 = coordinates[1];
        const x = Math.min(c0.x, c1.x), w = Math.max(1, Math.abs(c1.x - c0.x)), y = Math.min(c0.y, c1.y), h = Math.max(1, Math.abs(c1.y - c0.y));
        const col = up ? UP : DN, sign = up ? "+" : "";
        const label = `${sign}${pct.toFixed(2)}%   ${sign}${nfmt(diff)}` + (bars != null ? `   ${bars} bars` : "") + (days != null ? ` · ${days}d` : "");
        return [
          { type: "rect", attrs: { x, y, width: w, height: h }, styles: { style: "stroke_fill", color: up ? "rgba(21,128,61,.10)" : "rgba(180,35,24,.10)", borderColor: col, borderSize: 1, borderStyle: "dashed" }, ignoreEvent: true },
          { type: "text", attrs: { x: (c0.x + c1.x) / 2, y: y - 4, text: label, align: "center", baseline: "bottom" }, styles: { color: "#fff", backgroundColor: col, size: 12, weight: "bold", paddingLeft: 7, paddingRight: 7, paddingTop: 3, paddingBottom: 3, borderRadius: 4 } },
        ];
      },
    });
  }

  function injectStyles() {
    if (document.getElementById("charts-styles")) return;
    const s = document.createElement("style"); s.id = "charts-styles";
    s.textContent = `
      .cbar{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:4px 0;}
      .cbar .lbl{font-size:12px;font-weight:600;color:#6e6e73;margin-right:5px;}
      .cbar select{font:inherit;font-size:14px;font-weight:600;padding:7px 10px;border-radius:10px;border:1px solid var(--line);background:#fff;}
      .seg{display:inline-flex;gap:5px;flex-wrap:wrap;}
      .seg button{font:inherit;font-size:12.5px;font-weight:600;padding:6px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .seg button.tool.active{background:#1d1d1f;border-color:#1d1d1f;}
      .live{display:inline-flex;align-items:center;gap:7px;font-size:13px;margin-left:auto;}
      .live .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);}
      .live.on .dot{background:var(--good);box-shadow:0 0 0 3px rgba(48,209,88,.18);}
      #chart{width:100%;height:540px;}
      @media(max-width:680px){#chart{height:60vh;}}
      .notes-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}
      .notes-row button{font:inherit;font-size:13px;font-weight:600;padding:8px 13px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .notes-row button.apply{background:var(--accent);color:#fff;border-color:var(--accent);}
      #notes{width:100%;box-sizing:border-box;font:inherit;font-size:13px;padding:10px 12px;border-radius:10px;border:1px solid var(--line);resize:vertical;}
    `;
    document.head.appendChild(s);
  }

  function run() {
    injectStyles(); registerMeasure();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;

    const state = { asset: "spx", tf: "D", type: "candle_solid", yAxis: "normal", tool: "cursor", tfLastTs: 0,
      indicators: { MA: false, EMA: false, BOLL: false, VOL: false, MACD: false, RSI: false } };
    const D = { id: "", ticker: "", label: "", n: 0, dates: [], close: [], daily: [] };
    let chart = null, ASSETS = [], drawings = [], saveTimer = null, restoring = false, pollTimer = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1 id="cTitle">Charts</h1>
      <p class="lede">Daily candles with indicators and drawing tools. Pick an asset class, draw trend lines and levels,
        use <b>Measure %</b> to read the change between two points, and save private notes + drawings (passphrase).</p>
      <div class="card">
        <div class="cbar">
          <div><span class="lbl">Asset</span><select id="assetSel"></select></div>
          <div class="live" id="live"><span class="dot"></span><span id="liveTxt">live —</span></div>
        </div>
        <div class="cbar">
          <div><span class="lbl">Timeframe</span><span class="seg" id="tfSeg"></span></div>
          <div><span class="lbl">Type</span><span class="seg" id="typeSeg"></span></div>
          <div><span class="lbl">Axis</span><span class="seg" id="axisSeg"></span></div>
          <div><span class="lbl">Range</span><span class="seg" id="rangeSeg"></span></div>
        </div>
        <div class="cbar">
          <div><span class="lbl">Indicators</span><span class="seg" id="indSeg"></span></div>
        </div>
        <div class="cbar">
          <div><span class="lbl">Draw</span><span class="seg" id="toolSeg"></span></div>
          <div class="seg"><button id="undoBtn">Undo</button><button id="clearBtn">Clear all</button></div>
        </div>
        <div id="chart"></div>
        <p class="meta" id="hint" style="margin-top:8px">Scroll to zoom · drag to pan · pick a draw tool then click points on the chart.</p>
      </div>
      <div class="card">
        <h2>Notes <span class="meta" id="notesStatus" style="font-weight:400"></span></h2>
        <div class="notes-row">
          <button id="cloudBtn" class="apply">☁ Save to cloud</button>
          <span class="meta" id="cloudAuth"></span>
        </div>
        <textarea id="notes" rows="5" placeholder="Private notes for this asset (saved locally; ☁ for cross-device)…"></textarea>
        <p class="meta" style="margin-top:8px">Notes &amp; drawings are <b>private</b> — they need your passphrase to view or save, and auto-save in this browser meanwhile.</p>
      </div>`;

    const $ = (id) => document.getElementById(id);
    const segActive = (c, b) => c.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    function makeSeg(host, items, isActive, onPick, cls) {
      host.innerHTML = "";
      items.forEach(([val, label]) => { const b = document.createElement("button"); if (cls) b.className = cls; b.textContent = label; b.dataset.v = val; if (isActive(val)) b.classList.add("active"); b.onclick = () => onPick(val, b); host.appendChild(b); });
    }

    // ---- chart ----
    chart = klinecharts.init($("chart"));
    chart.setStyles({
      grid: { horizontal: { color: "#eee" }, vertical: { color: "#f4f4f4" } },
      candle: {
        type: state.type,
        bar: { upColor: UP, downColor: DN, noChangeColor: "#888", upBorderColor: UP, downBorderColor: DN, upWickColor: UP, downWickColor: DN },
        priceMark: { last: { show: true }, high: { show: true }, low: { show: true } },
        tooltip: { showRule: "always", showType: "rect" },
      },
      indicator: { lastValueMark: { show: false } },
      yAxis: { type: state.yAxis },
      xAxis: { tickText: { color: "#8a8a8e" } },
    });
    window.addEventListener("resize", () => chart && chart.resize());
    setTimeout(() => chart && chart.resize(), 60);  // ensure canvases size to the laid-out container

    // ---- controls ----
    makeSeg($("tfSeg"), TFS.map((t) => [t.id, t.label]), (v) => v === state.tf, (v, b) => { state.tf = v; segActive($("tfSeg"), b); applyTF(); });
    makeSeg($("typeSeg"), TYPES, (v) => v === state.type, (v, b) => { state.type = v; chart.setStyles({ candle: { type: v } }); segActive($("typeSeg"), b); scheduleSave(); });
    makeSeg($("axisSeg"), AXES, (v) => v === state.yAxis, (v, b) => { state.yAxis = v; chart.setStyles({ yAxis: { type: v } }); segActive($("axisSeg"), b); scheduleSave(); });
    makeSeg($("rangeSeg"), RANGES, () => false, (days, b) => { setRange(days); segActive($("rangeSeg"), b); });
    makeSeg($("indSeg"), MAIN_INDS.concat(SUB_INDS), (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("toolSeg"), TOOLS.map(([v, l]) => [v, l]), (v) => v === state.tool, (v, b) => { pickTool(v); segActive($("toolSeg"), b); }, "tool");
    $("undoBtn").onclick = undoDrawing;
    $("clearBtn").onclick = clearDrawings;

    function setRange(days) {
      if (!D.n) return;
      const w = Math.max(200, $("chart").clientWidth - 70);
      const n = days ? Math.min(days, D.n) : D.n;
      chart.setBarSpace(Math.max(0.5, Math.min(40, w / n)));
      chart.scrollToRealTime(0);
    }
    // ---- timeframe: 1D = static full history; intraday = live from the quote proxy ----
    function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
    function applyTF() {
      stopPoll();
      const tf = TFS.find((t) => t.id === state.tf) || TFS[TFS.length - 1];
      if (!tf.interval) {
        chart.applyNewData(D.daily || []); chart.resize(); setRange(126); state.tfLastTs = 0;
        $("hint").textContent = "Daily bars · scroll to zoom · drag to pan · pick a draw tool then click points.";
        return;
      }
      status("loading " + tf.label + "…");
      fetch(QUOTE + "/?mode=intraday&symbol=" + encodeURIComponent(D.ticker) + "&interval=" + tf.interval + "&range=" + tf.range + "&_=" + Date.now())
        .then((r) => r.json())
        .then((j) => {
          const bars = j.bars || []; if (!bars.length) throw new Error("no intraday data");
          chart.applyNewData(bars); chart.resize();
          const w = Math.max(200, $("chart").clientWidth - 70), show = Math.min(bars.length, tf.show || 180);
          chart.setBarSpace(Math.max(1, Math.min(14, w / show))); chart.scrollToRealTime(0);
          state.tfLastTs = bars[bars.length - 1].timestamp;
          status(tf.label + " · " + bars.length + " bars");
          $("hint").textContent = tf.label + " intraday · auto-refreshing every " + (POLL_MS / 1000) + "s · " + (j.ticker || D.ticker);
          pollTimer = setInterval(() => refreshTF(tf), POLL_MS);
        })
        .catch((e) => { status("intraday unavailable: " + e.message); });
    }
    function refreshTF(tf) {
      fetch(QUOTE + "/?mode=intraday&symbol=" + encodeURIComponent(D.ticker) + "&interval=" + tf.interval + "&range=" + tf.range + "&_=" + Date.now())
        .then((r) => r.json())
        .then((j) => {
          const bars = j.bars || []; let n = 0;
          for (const b of bars) { if (b.timestamp >= state.tfLastTs) { chart.updateData(b); state.tfLastTs = Math.max(state.tfLastTs, b.timestamp); n++; } }
          if (n) fetchLive();
        }).catch(() => {});
    }
    const PANE = { VOL: "pane_vol", MACD: "pane_macd", RSI: "pane_rsi" };
    function toggleIndicator(name) {
      const on = !state.indicators[name]; state.indicators[name] = on;
      if (MAIN_INDS.some(([v]) => v === name)) {
        if (on) chart.createIndicator(name, true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", name);
      } else {
        if (on) chart.createIndicator(name, false, { id: PANE[name] }); else chart.removeIndicator(PANE[name], name);
      }
    }

    // ---- drawing ----
    function pickTool(name) {
      state.tool = name;
      if (name === "cursor") return;
      let extend;
      if (name === "simpleAnnotation") { extend = (window.prompt("Annotation text:") || "").trim() || "note"; }
      chart.createOverlay({
        name, extendData: extend,
        onDrawEnd: (e) => { recordDrawing(e.overlay); pickTool("cursor"); segActive($("toolSeg"), [...$("toolSeg").querySelectorAll("button")].find((x) => x.dataset.v === "cursor")); return false; },
      });
    }
    function recordDrawing(o) {
      if (restoring || !o) return;
      const pts = (o.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value }));
      const i = drawings.findIndex((d) => d.id === o.id);
      const rec = { id: o.id, name: o.name, points: pts, extendData: o.extendData };
      if (i >= 0) drawings[i] = rec; else drawings.push(rec);
      scheduleSave();
    }
    function undoDrawing() { const last = drawings.pop(); if (last) chart.removeOverlay(last.id); scheduleSave(); }
    function clearDrawings() { chart.removeOverlay(); drawings = []; scheduleSave(); }

    // ---- persistence (private; passphrase-gated cloud + localStorage fallback) ----
    const lsKey = (id) => "chart_" + id;
    const getKey = () => { try { return localStorage.getItem(CLOUD_KEY) || ""; } catch (_) { return ""; } };
    function setKey(k) { try { k ? localStorage.setItem(CLOUD_KEY, k) : localStorage.removeItem(CLOUD_KEY); } catch (_) {} updateAuth(); }
    function status(msg) { $("notesStatus").textContent = msg ? "· " + msg : ""; }
    function updateAuth() {
      const el = $("cloudAuth");
      if (getKey()) { el.innerHTML = `signed in · <a href="#" id="logout">log out</a>`; el.querySelector("#logout").onclick = (e) => { e.preventDefault(); setKey(""); status("logged out"); }; }
      else el.textContent = "not signed in";
    }
    function ensureKey() {
      const k = getKey(); if (k) return Promise.resolve(k);
      const entry = (window.prompt("Passphrase to save/view private notes:") || "").trim();
      if (!entry) return Promise.resolve("");
      return fetch(STORE + "/api/auth", { method: "POST", headers: { "X-Lab-Key": entry } })
        .then((r) => { if (!r.ok) { status("wrong passphrase"); return ""; } setKey(entry); return entry; })
        .catch(() => { status("login failed"); return ""; });
    }
    function snapshot() { return { notes: $("notes").value || "", drawings: drawings.map(({ id, ...d }) => d), settings: { type: state.type, yAxis: state.yAxis, indicators: state.indicators } }; }
    function saveLocal() { try { localStorage.setItem(lsKey(D.id), JSON.stringify(snapshot())); } catch (_) {} }
    function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => { saveTimer = null; saveLocal(); status("saved locally"); }, 600); }
    $("cloudBtn").onclick = () => {
      ensureKey().then((key) => {
        if (!key) return; updateAuth(); status("saving…");
        fetch(STORE + "/api/chart/" + D.id, { method: "POST", headers: { "Content-Type": "application/json", "X-Lab-Key": key }, body: JSON.stringify(snapshot()) })
          .then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
          .then(() => status("saved to cloud ✓")).catch((e) => status("cloud save failed: " + e.message));
      });
    };
    $("notes").addEventListener("input", scheduleSave);

    function applySnapshot(snap) {
      restoring = true;
      $("notes").value = snap.notes || "";
      const st = snap.settings || {};
      if (st.type) { state.type = st.type; chart.setStyles({ candle: { type: st.type } }); segActive($("typeSeg"), [...$("typeSeg").querySelectorAll("button")].find((b) => b.dataset.v === st.type)); }
      if (st.yAxis) { state.yAxis = st.yAxis; chart.setStyles({ yAxis: { type: st.yAxis } }); segActive($("axisSeg"), [...$("axisSeg").querySelectorAll("button")].find((b) => b.dataset.v === st.yAxis)); }
      if (st.indicators) { Object.keys(state.indicators).forEach((k) => { if (state.indicators[k]) toggleIndicator(k); }); Object.keys(st.indicators).forEach((k) => { if (st.indicators[k]) { state.indicators[k] = false; toggleIndicator(k); } }); [...$("indSeg").querySelectorAll("button")].forEach((b) => b.classList.toggle("active", state.indicators[b.dataset.v])); }
      drawings = [];
      (snap.drawings || []).forEach((d) => { const id = chart.createOverlay({ name: d.name, points: d.points, extendData: d.extendData }); drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); });
      restoring = false;
    }
    function loadNotes() {
      // clear current overlays/state, then load private cloud (if logged in) else localStorage
      chart.removeOverlay(); drawings = [];
      const local = (() => { try { return JSON.parse(localStorage.getItem(lsKey(D.id))) || null; } catch (_) { return null; } })();
      const key = getKey();
      if (key) {
        status("loading…");
        fetch(STORE + "/api/chart/" + D.id, { headers: { "X-Lab-Key": key } })
          .then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } return r.json(); })
          .then((snap) => { applySnapshot(snap && (snap.notes || (snap.drawings && snap.drawings.length) || snap.settings) ? snap : (local || {})); status(snap && snap.savedAt ? "from cloud" : ""); })
          .catch(() => { applySnapshot(local || {}); status("offline — local"); });
      } else { applySnapshot(local || {}); }
    }

    // ---- live ----
    function fetchLive() {
      const live = $("live"), txt = $("liveTxt"); txt.textContent = "live —"; live.classList.remove("on");
      fetch(QUOTE + "/?mode=quote&symbol=" + encodeURIComponent(D.ticker) + "&_=" + Date.now())
        .then((r) => r.json())
        .then((q) => {
          if (!q || !(q.price > 0) || (q.ticker || "").toUpperCase() !== D.ticker.toUpperCase()) { txt.textContent = "live unavailable"; return; }
          const prev = D.close[D.n - 1], chg = (q.price / prev - 1) * 100, s = chg >= 0 ? "+" : "";
          live.classList.add("on");
          txt.innerHTML = `<b>${esc(D.ticker)} ${nfmt(q.price)}</b> <span style="color:${chg >= 0 ? UP : DN}">${s}${chg.toFixed(2)}%</span> <span style="color:#8a8a8e">· ${esc(q.timestamp || "")}</span>`;
        }).catch(() => { txt.textContent = "live unavailable"; });
    }

    // ---- asset load ----
    function loadAsset(id) {
      state.asset = id;
      fetch("price_" + id + ".json?v=" + Date.now())
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then((d) => {
          D.id = id; D.ticker = d.ticker; D.label = d.asset_label || id; D.n = d.close.length; D.dates = d.dates; D.close = d.close;
          $("cTitle").textContent = D.label + " — chart";
          D.daily = d.close.map((c, i) => ({ timestamp: d.timestamp[i], open: d.open[i], high: d.high[i], low: d.low[i], close: c, volume: d.volume ? d.volume[i] : 0 }));
          applyTF();
          loadNotes();
          fetchLive();
        })
        .catch((e) => { status("could not load " + id + " — " + e.message); });
    }

    // ---- asset registry ----
    updateAuth();
    fetch("price_assets.json?v=" + Date.now())
      .then((r) => r.json())
      .then((list) => { ASSETS = list; })
      .catch(() => { ASSETS = [{ id: "spx", label: "S&P 500", klass: "Indices", ticker: "^GSPC" }, { id: "ndx", label: "Nasdaq 100", klass: "Indices", ticker: "^NDX" }]; })
      .then(() => {
        const sel = $("assetSel"); const groups = {};
        ASSETS.forEach((a) => { (groups[a.klass] = groups[a.klass] || []).push(a); });
        sel.innerHTML = Object.keys(groups).map((g) => `<optgroup label="${esc(g)}">` + groups[g].map((a) => `<option value="${esc(a.id)}">${esc(a.label)}</option>`).join("") + `</optgroup>`).join("");
        sel.value = state.asset; sel.onchange = () => loadAsset(sel.value);
        loadAsset(state.asset);
      });
  }

  function boot() {
    if (!window.klinecharts || !document.getElementById("app")) { setTimeout(boot, 30); return; }
    if (window.SP && SP.injectStyles) SP.injectStyles();
    run();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
