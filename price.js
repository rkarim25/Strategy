/**
 * Charts — a TradingView/Bloomberg-style charting workstation built on KLineChart (vendored v9.8.12).
 * Asset registry grouped by class (price_assets.json) · candle/bar/area · linear/log/% axis · range presets ·
 * timeframes 1m/5m/15m/30m/1h/4h/1D (intraday from the quote proxy, 4h aggregated client-side, 60s auto-refresh) ·
 * comprehensive indicators (overlays + ~20 studies) · drawing palette + custom "Measure %" overlay (retained
 * across timeframe/zoom) · live last price · private per-asset notes + drawings (passphrase-gated, localStorage
 * fallback) · a Signal Playbook backtesting common indicator buy/sell rules on the current asset.
 */
(function () {
  "use strict";
  const QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev";
  const STORE = "https://lab-strategy-store.rkarim88.workers.dev";
  const CLOUD_KEY = "lab_cloud_key"; // shared passphrase login with the Lab
  const UP = "#15803d", DN = "#b42318";
  const RANGES = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["2Y", 504], ["5Y", 1260], ["Max", null]];
  const TFS = [
    { id: "1m", label: "1m", interval: "1m", range: "7d", show: 180 },
    { id: "5m", label: "5m", interval: "5m", range: "60d", show: 160 },
    { id: "15m", label: "15m", interval: "15m", range: "60d", show: 170 },
    { id: "30m", label: "30m", interval: "30m", range: "60d", show: 170 },
    { id: "1h", label: "1h", interval: "60m", range: "730d", show: 200 },
    { id: "4h", label: "4h", interval: "60m", range: "730d", show: 200, aggMs: 4 * 3600 * 1000 },
    { id: "D", label: "1D", interval: null },
  ];
  const POLL_MS = 60000;
  const TYPES = [["candle_solid", "Candles"], ["ohlc", "Bars"], ["area", "Area"]];
  const AXES = [["normal", "Linear"], ["log", "Log"], ["percentage", "%"]];
  const MAIN_INDS = [["MA", "MA"], ["EMA", "EMA"], ["SMA", "SMA"], ["BOLL", "Bollinger"], ["BBI", "BBI"], ["SAR", "SAR"]];
  const SUB_INDS = [["VOL", "Volume"], ["MACD", "MACD"], ["RSI", "RSI"], ["KDJ", "KDJ"], ["CCI", "CCI"], ["WR", "Williams %R"],
    ["DMI", "DMI/ADX"], ["OBV", "OBV"], ["ROC", "ROC"], ["TRIX", "TRIX"], ["BIAS", "BIAS"], ["MTM", "Momentum"],
    ["PSY", "PSY"], ["BRAR", "BRAR"], ["CR", "CR"], ["VR", "VR"], ["EMV", "EMV"], ["DMA", "DMA"], ["AO", "AO"], ["PVT", "PVT"]];
  const MAIN_SET = new Set(MAIN_INDS.map(([v]) => v));
  const TOOLS = [
    ["cursor", "Cursor"], ["segment", "Trend line"], ["rayLine", "Ray"], ["horizontalStraightLine", "Horizontal"],
    ["verticalStraightLine", "Vertical"], ["priceLine", "Price line"], ["parallelStraightLine", "Parallel"],
    ["fibonacciLine", "Fibonacci"], ["simpleAnnotation", "Text"], ["measurePct", "Measure %"],
  ];
  const nfmt = (x) => (x == null || !isFinite(x) ? "—" : Math.abs(x) < 10 ? x.toLocaleString(undefined, { maximumFractionDigits: 4 }) : x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x * 100).toFixed(1) + "%");
  const f2 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(2));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- indicator math (for the Signal Playbook backtests) ----------
  function sma(a, n) { const o = Array(a.length).fill(null); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
  function ema(a, n) { const o = Array(a.length).fill(null); const k = 2 / (n + 1); let e = null; for (let i = 0; i < a.length; i++) { e = e == null ? a[i] : a[i] * k + e * (1 - k); if (i >= n - 1) o[i] = e; } return o; }
  function rstd(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let m = 0; for (let j = i - n + 1; j <= i; j++) m += a[j]; m /= n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (a[j] - m) ** 2; o[i] = Math.sqrt(v / n); } return o; }
  function rsiArr(a, n) { const o = Array(a.length).fill(null); let g = 0, l = 0; for (let i = 1; i < a.length; i++) { const ch = a[i] - a[i - 1], gg = Math.max(ch, 0), ll = Math.max(-ch, 0); if (i <= n) { g += gg; l += ll; if (i === n) { g /= n; l /= n; o[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)); } } else { g = (g * (n - 1) + gg) / n; l = (l * (n - 1) + ll) / n; o[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)); } } return o; }
  function macdArr(a) { const ef = ema(a, 12), es = ema(a, 26); const m = a.map((_, i) => (ef[i] == null || es[i] == null ? null : ef[i] - es[i])); const sig = ema(m.map((v) => v == null ? 0 : v), 9).map((v, i) => (m[i] == null ? null : v)); return { macd: m, signal: sig }; }
  function rollMax(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let x = -Infinity; for (let j = i - n + 1; j <= i; j++) if (a[j] > x) x = a[j]; o[i] = x; } return o; }
  function rollMin(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let x = Infinity; for (let j = i - n + 1; j <= i; j++) if (a[j] < x) x = a[j]; o[i] = x; } return o; }
  function backtest(c, posArr) { const n = c.length, eq = Array(n), ret = Array(n); let e = 100; for (let i = 0; i < n; i++) { const r = i ? (posArr[i - 1] || 0) * (c[i] / c[i - 1] - 1) : 0; e *= 1 + r; eq[i] = e; ret[i] = r; } return { eq, ret }; }
  function stats(eq, ret, posArr) { const n = eq.length; if (n < 30) return { cagr: NaN, vol: NaN, sharpe: NaN, maxdd: NaN, end: eq[n - 1], pin: NaN }; const yrs = n / 252, cagr = Math.pow(eq[n - 1] / 100, 1 / yrs) - 1; let m = 0; for (const r of ret) m += r; m /= n; let v = 0; for (const r of ret) v += (r - m) ** 2; const vol = Math.sqrt(v / (n - 1)) * Math.sqrt(252); let pk = -1e9, mdd = 0; for (const x of eq) { if (x > pk) pk = x; const dd = x / pk - 1; if (dd < mdd) mdd = dd; } let inn = 0; for (const p of posArr) inn += p > 0 ? 1 : 0; return { cagr, vol, sharpe: vol ? (m * 252) / vol : NaN, maxdd: mdd, end: eq[n - 1], pin: inn / n }; }
  const STRATS = [
    { name: "Golden Cross 50/200", buy: "SMA50 crosses above SMA200", sell: "SMA50 crosses below SMA200", pos: (c) => { const a = sma(c, 50), b = sma(c, 200); return c.map((_, i) => (a[i] != null && b[i] != null && a[i] >= b[i]) ? 1 : 0); } },
    { name: "Trend filter (Close > SMA200)", buy: "Close rises above its 200-day average", sell: "Close falls below SMA200", pos: (c) => { const b = sma(c, 200); return c.map((x, i) => (b[i] != null && x >= b[i]) ? 1 : 0); } },
    { name: "MACD 12/26/9", buy: "MACD line crosses above signal", sell: "MACD line crosses below signal", pos: (c) => { const m = macdArr(c); return c.map((_, i) => (m.macd[i] != null && m.signal[i] != null && m.macd[i] >= m.signal[i]) ? 1 : 0); } },
    { name: "RSI(14) momentum", buy: "RSI rises above 50", sell: "RSI falls below 50", pos: (c) => { const r = rsiArr(c, 14); return c.map((_, i) => (r[i] != null && r[i] >= 50) ? 1 : 0); } },
    { name: "Bollinger(20,2) reversion", buy: "Close dips below the lower band", sell: "Close returns above the mid (SMA20)", pos: (c) => { const mid = sma(c, 20), sd = rstd(c, 20); let p = 0; return c.map((x, i) => { if (mid[i] == null) return 0; if (p === 0 && x < mid[i] - 2 * sd[i]) p = 1; else if (p === 1 && x > mid[i]) p = 0; return p; }); } },
    { name: "Donchian 20 breakout", buy: "Close makes a new 20-day high", sell: "Close makes a new 20-day low", pos: (c) => { const hi = rollMax(c, 20), lo = rollMin(c, 20); let p = 0; return c.map((x, i) => { if (i < 20) return 0; if (x >= hi[i - 1]) p = 1; else if (x <= lo[i - 1]) p = 0; return p; }); } },
  ];

  // ---------- custom "Measure %" overlay ----------
  function registerMeasure() {
    if (!window.klinecharts || !klinecharts.registerOverlay) return;
    try {
      klinecharts.registerOverlay({
        name: "measurePct", totalStep: 3, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
        createPointFigures: ({ overlay, coordinates }) => {
          if (coordinates.length < 2) return [];
          const p = overlay.points; const v0 = p[0].value, v1 = p[1].value;
          if (v0 == null || v1 == null) return [];
          const diff = v1 - v0, pc = v0 ? (diff / v0) * 100 : 0, up = diff >= 0;
          const days = (p[0].timestamp != null && p[1].timestamp != null) ? Math.round(Math.abs(p[1].timestamp - p[0].timestamp) / 864e5) : null;
          const bars = (p[0].dataIndex != null && p[1].dataIndex != null) ? Math.abs(p[1].dataIndex - p[0].dataIndex) : null;
          const c0 = coordinates[0], c1 = coordinates[1];
          const x = Math.min(c0.x, c1.x), w = Math.max(1, Math.abs(c1.x - c0.x)), y = Math.min(c0.y, c1.y), h = Math.max(1, Math.abs(c1.y - c0.y));
          const col = up ? UP : DN, s = up ? "+" : "";
          const label = `${s}${pc.toFixed(2)}%   ${s}${nfmt(diff)}` + (bars != null ? `   ${bars} bars` : "") + (days != null ? ` · ${days}d` : "");
          return [
            { type: "rect", attrs: { x, y, width: w, height: h }, styles: { style: "stroke_fill", color: up ? "rgba(21,128,61,.10)" : "rgba(180,35,24,.10)", borderColor: col, borderSize: 1, borderStyle: "dashed" }, ignoreEvent: true },
            { type: "text", attrs: { x: (c0.x + c1.x) / 2, y: y - 4, text: label, align: "center", baseline: "bottom" }, styles: { color: "#fff", backgroundColor: col, size: 12, weight: "bold", paddingLeft: 7, paddingRight: 7, paddingTop: 3, paddingBottom: 3, borderRadius: 4 } },
          ];
        },
      });
    } catch (_) {}
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
      details.ind-panel{margin:4px 0;border:1px solid var(--line);border-radius:12px;padding:4px 12px;background:rgba(255,255,255,.5);}
      details.ind-panel summary{font-size:13px;font-weight:700;cursor:pointer;padding:5px 0;color:#1d1d1f;}
      .ind-grp{display:flex;gap:8px;align-items:flex-start;margin:6px 0;flex-wrap:wrap;}
      .notes-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}
      .notes-row button{font:inherit;font-size:13px;font-weight:600;padding:8px 13px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .notes-row button.apply{background:var(--accent);color:#fff;border-color:var(--accent);}
      #notes{width:100%;box-sizing:border-box;font:inherit;font-size:13px;padding:10px 12px;border-radius:10px;border:1px solid var(--line);resize:vertical;}
      table.pb{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px;}
      table.pb th,table.pb td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap;}
      table.pb th:first-child,table.pb td:first-child{text-align:left;white-space:normal;}
      table.pb th{font-size:11.5px;color:#6e6e73;text-transform:uppercase;letter-spacing:.03em;}
      table.pb tr.bh{background:rgba(0,0,0,.03);font-weight:600;}
      table.pb .sig{font-size:11.5px;color:#6e6e73;}
      table.pb .win{color:${UP};font-weight:700;}
    `;
    document.head.appendChild(s);
  }

  function run() {
    injectStyles(); registerMeasure();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const state = { asset: "spx", tf: "D", type: "candle_solid", yAxis: "normal", tool: "cursor", tfLastTs: 0,
      indicators: Object.fromEntries(MAIN_INDS.concat(SUB_INDS).map(([v]) => [v, false])) };
    const D = { id: "", ticker: "", label: "", n: 0, dates: [], close: [], daily: [] };
    let chart = null, ASSETS = [], drawings = [], saveTimer = null, restoring = false, pollTimer = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1 id="cTitle">Charts</h1>
      <p class="lede">Candles with indicators and drawing tools across timeframes. Pick an asset, draw trend lines and levels,
        use <b>Measure %</b> for the change between two points, layer studies, and save private notes (passphrase).</p>
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
        <details class="ind-panel">
          <summary>Indicators — overlays &amp; studies</summary>
          <div class="ind-grp"><span class="lbl">On price</span><span class="seg" id="indMain"></span></div>
          <div class="ind-grp"><span class="lbl">Studies</span><span class="seg" id="indSub"></span></div>
        </details>
        <div class="cbar">
          <div><span class="lbl">Draw</span><span class="seg" id="toolSeg"></span></div>
          <div class="seg"><button id="undoBtn">Undo</button><button id="clearBtn">Clear all</button></div>
        </div>
        <div id="chart"></div>
        <p class="meta" id="hint" style="margin-top:8px">Scroll to zoom · drag to pan · pick a draw tool then click points on the chart.</p>
      </div>
      <div class="card">
        <h2>Signal playbook <span class="meta" id="pbAsset" style="font-weight:400"></span></h2>
        <p class="meta">Common indicator buy/sell rules and how each would have <b>backtested on this asset's full daily history</b>
          (long-or-cash, next-day execution, cash earns 0%, no costs). Educational only — not investment advice.</p>
        <div id="playbook"><p class="meta">Loading…</p></div>
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
    const findBtn = (c, v) => [...c.querySelectorAll("button")].find((b) => b.dataset.v === v);
    function makeSeg(host, items, isActive, onPick, cls) {
      host.innerHTML = "";
      items.forEach(([val, label]) => { const b = document.createElement("button"); if (cls) b.className = cls; b.textContent = label; b.dataset.v = val; if (isActive(val)) b.classList.add("active"); b.onclick = () => onPick(val, b); host.appendChild(b); });
    }

    // ---- chart ----
    chart = klinecharts.init($("chart"));
    chart.setStyles({
      grid: { horizontal: { color: "#eee" }, vertical: { color: "#f4f4f4" } },
      candle: { type: state.type, bar: { upColor: UP, downColor: DN, noChangeColor: "#888", upBorderColor: UP, downBorderColor: DN, upWickColor: UP, downWickColor: DN }, priceMark: { last: { show: true }, high: { show: true }, low: { show: true } }, tooltip: { showRule: "always", showType: "rect" } },
      indicator: { lastValueMark: { show: false } },
      yAxis: { type: state.yAxis }, xAxis: { tickText: { color: "#8a8a8e" } },
    });
    window.addEventListener("resize", () => chart && chart.resize());
    setTimeout(() => chart && chart.resize(), 60);

    // ---- controls ----
    makeSeg($("tfSeg"), TFS.map((t) => [t.id, t.label]), (v) => v === state.tf, (v, b) => { state.tf = v; segActive($("tfSeg"), b); applyTF(); });
    makeSeg($("typeSeg"), TYPES, (v) => v === state.type, (v, b) => { state.type = v; safe(() => chart.setStyles({ candle: { type: v } })); segActive($("typeSeg"), b); scheduleSave(); });
    makeSeg($("axisSeg"), AXES, (v) => v === state.yAxis, (v, b) => { state.yAxis = v; safe(() => chart.setStyles({ yAxis: { type: v } })); segActive($("axisSeg"), b); scheduleSave(); });
    makeSeg($("rangeSeg"), RANGES, () => false, (days, b) => { setRange(days); segActive($("rangeSeg"), b); });
    makeSeg($("indMain"), MAIN_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("indSub"), SUB_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("toolSeg"), TOOLS, (v) => v === state.tool, (v, b) => { pickTool(v); segActive($("toolSeg"), b); }, "tool");
    $("undoBtn").onclick = undoDrawing;
    $("clearBtn").onclick = clearDrawings;

    function safe(fn) { try { return fn(); } catch (e) { status("error: " + (e.message || e)); } }
    function setRange(days) {
      if (!D.n && !chart) return;
      const w = Math.max(200, $("chart").clientWidth - 70);
      const n = days ? Math.min(days, D.n || days) : (D.n || days || 250);
      safe(() => { chart.setBarSpace(Math.max(0.5, Math.min(40, w / n))); chart.scrollToRealTime(0); });
    }

    // ---- timeframe / intraday ----
    function aggregate(bars, ms) {
      if (!ms) return bars; const out = []; let cur = null, key = null;
      for (const b of bars) { const k = Math.floor(b.timestamp / ms); if (k !== key) { if (cur) out.push(cur); cur = { timestamp: k * ms, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0 }; key = k; } else { cur.high = Math.max(cur.high, b.high); cur.low = Math.min(cur.low, b.low); cur.close = b.close; cur.volume += b.volume || 0; } }
      if (cur) out.push(cur); return out;
    }
    function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
    function applyTF() {
      stopPoll();
      const tf = TFS.find((t) => t.id === state.tf) || TFS[TFS.length - 1];
      if (!tf.interval) {
        safe(() => { chart.applyNewData(D.daily || []); chart.resize(); }); setRange(126); reapplyDrawings(); state.tfLastTs = 0;
        $("hint").textContent = "Daily bars · scroll to zoom · drag to pan · pick a draw tool then click points.";
        return;
      }
      status("loading " + tf.label + "…");
      fetch(QUOTE + "/?mode=intraday&symbol=" + encodeURIComponent(D.ticker) + "&interval=" + tf.interval + "&range=" + tf.range + "&_=" + Date.now())
        .then((r) => r.json())
        .then((j) => {
          let bars = j.bars || []; if (!bars.length) throw new Error("no intraday data");
          if (tf.aggMs) bars = aggregate(bars, tf.aggMs);
          safe(() => { chart.applyNewData(bars); chart.resize(); });
          const w = Math.max(200, $("chart").clientWidth - 70), show = Math.min(bars.length, tf.show || 180);
          safe(() => { chart.setBarSpace(Math.max(1, Math.min(14, w / show))); chart.scrollToRealTime(0); });
          reapplyDrawings();
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
          let bars = j.bars || []; if (tf.aggMs) bars = aggregate(bars, tf.aggMs);
          let n = 0; for (const b of bars) { if (b.timestamp >= state.tfLastTs) { safe(() => chart.updateData(b)); state.tfLastTs = Math.max(state.tfLastTs, b.timestamp); n++; } }
          if (n) fetchLive();
        }).catch(() => {});
    }

    // ---- indicators ----
    const paneId = (name) => "pane_" + name.toLowerCase();
    function toggleIndicator(name) {
      const on = !state.indicators[name]; state.indicators[name] = on;
      safe(() => {
        if (MAIN_SET.has(name)) { if (on) chart.createIndicator(name, true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", name); }
        else { if (on) chart.createIndicator(name, false, { id: paneId(name) }); else chart.removeIndicator(paneId(name), name); }
      });
    }
    function syncIndicators(target) {
      Object.keys(state.indicators).forEach((name) => { const want = !!(target && target[name]); if (state.indicators[name] !== want) toggleIndicator(name); });
      [...$("indMain").querySelectorAll("button"), ...$("indSub").querySelectorAll("button")].forEach((b) => b.classList.toggle("active", !!state.indicators[b.dataset.v]));
    }

    // ---- drawing (retained across timeframe/zoom via reapplyDrawings) ----
    function pickTool(name) {
      state.tool = name; if (name === "cursor") return;
      let extend; if (name === "simpleAnnotation") extend = (window.prompt("Annotation text:") || "").trim() || "note";
      safe(() => chart.createOverlay({
        name, extendData: extend,
        onDrawEnd: (e) => { recordDrawing(e.overlay); pickTool("cursor"); segActive($("toolSeg"), findBtn($("toolSeg"), "cursor")); return false; },
      }));
    }
    function recordDrawing(o) {
      if (restoring || !o) return;
      const pts = (o.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value }));
      const i = drawings.findIndex((d) => d.id === o.id), rec = { id: o.id, name: o.name, points: pts, extendData: o.extendData };
      if (i >= 0) drawings[i] = rec; else drawings.push(rec); scheduleSave();
    }
    function reapplyDrawings() {
      restoring = true;
      safe(() => chart.removeOverlay());
      const keep = drawings.slice(); drawings = [];
      keep.forEach((d) => { const id = safe(() => chart.createOverlay({ name: d.name, points: d.points, extendData: d.extendData })); drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); });
      restoring = false;
    }
    function undoDrawing() { const last = drawings.pop(); if (last) safe(() => chart.removeOverlay(last.id)); scheduleSave(); }
    function clearDrawings() { safe(() => chart.removeOverlay()); drawings = []; scheduleSave(); }

    // ---- persistence ----
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
      const entry = (window.prompt("Passphrase to save/view private notes:") || "").trim(); if (!entry) return Promise.resolve("");
      return fetch(STORE + "/api/auth", { method: "POST", headers: { "X-Lab-Key": entry } }).then((r) => { if (!r.ok) { status("wrong passphrase"); return ""; } setKey(entry); return entry; }).catch(() => { status("login failed"); return ""; });
    }
    function snapshot() { return { notes: $("notes").value || "", drawings: drawings.map(({ id, ...d }) => d), settings: { type: state.type, yAxis: state.yAxis, indicators: state.indicators } }; }
    function saveLocal() { try { localStorage.setItem(lsKey(D.id), JSON.stringify(snapshot())); } catch (_) {} }
    function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => { saveTimer = null; saveLocal(); status("saved locally"); }, 600); }
    $("cloudBtn").onclick = () => { ensureKey().then((key) => { if (!key) return; updateAuth(); status("saving…"); fetch(STORE + "/api/chart/" + D.id, { method: "POST", headers: { "Content-Type": "application/json", "X-Lab-Key": key }, body: JSON.stringify(snapshot()) }).then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(() => status("saved to cloud ✓")).catch((e) => status("cloud save failed: " + e.message)); }); };
    $("notes").addEventListener("input", scheduleSave);

    function applySnapshot(snap) {
      restoring = true;
      $("notes").value = snap.notes || "";
      const st = snap.settings || {};
      if (st.type) { state.type = st.type; safe(() => chart.setStyles({ candle: { type: st.type } })); segActive($("typeSeg"), findBtn($("typeSeg"), st.type)); }
      if (st.yAxis) { state.yAxis = st.yAxis; safe(() => chart.setStyles({ yAxis: { type: st.yAxis } })); segActive($("axisSeg"), findBtn($("axisSeg"), st.yAxis)); }
      syncIndicators(st.indicators);
      drawings = [];
      (snap.drawings || []).forEach((d) => { const id = safe(() => chart.createOverlay({ name: d.name, points: d.points, extendData: d.extendData })); drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); });
      restoring = false;
    }
    function loadNotes() {
      safe(() => chart.removeOverlay()); drawings = [];
      const local = (() => { try { return JSON.parse(localStorage.getItem(lsKey(D.id))) || null; } catch (_) { return null; } })();
      const key = getKey();
      if (key) {
        status("loading…");
        fetch(STORE + "/api/chart/" + D.id, { headers: { "X-Lab-Key": key } })
          .then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } return r.json(); })
          .then((snap) => { const has = snap && (snap.notes || (snap.drawings && snap.drawings.length) || snap.settings); applySnapshot(has ? snap : (local || {})); status(has && snap.savedAt ? "from cloud" : ""); })
          .catch(() => { applySnapshot(local || {}); status("offline — local"); });
      } else applySnapshot(local || {});
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

    // ---- signal playbook ----
    function renderPlaybook() {
      const c = D.close; const host = $("playbook"); $("pbAsset").textContent = D.dates.length ? "· " + D.label + " · " + D.dates[0] + " → " + D.dates[D.n - 1] : "";
      if (!c || c.length < 250) { host.innerHTML = `<p class="meta">Not enough history for a meaningful backtest.</p>`; return; }
      const bh = stats(backtest(c, c.map(() => 1)).eq, backtest(c, c.map(() => 1)).ret, c.map(() => 1));
      const rows = STRATS.map((st) => { const p = st.pos(c); const r = backtest(c, p); const s = stats(r.eq, r.ret, p); return { st, s }; });
      const cell = (s, key, fmt) => fmt(s[key]);
      const head = `<tr><th>Strategy &amp; signal</th><th>CAGR</th><th>Max DD</th><th>Sharpe</th><th>% in</th><th>$100→</th></tr>`;
      const bhRow = `<tr class="bh"><td>Buy &amp; hold<div class="sig">always invested</div></td><td>${pct(bh.cagr)}</td><td>${pct(bh.maxdd)}</td><td>${f2(bh.sharpe)}</td><td>100%</td><td>$${Math.round(bh.end).toLocaleString()}</td></tr>`;
      const body = rows.map(({ st, s }) => `<tr><td><b>${esc(st.name)}</b><div class="sig">▲ ${esc(st.buy)} · ▼ ${esc(st.sell)}</div></td>
        <td class="${s.cagr > bh.cagr ? "win" : ""}">${pct(s.cagr)}</td><td>${pct(s.maxdd)}</td><td>${f2(s.sharpe)}</td><td>${pct(s.pin)}</td><td>$${Math.round(s.end).toLocaleString()}</td></tr>`).join("");
      host.innerHTML = `<table class="pb"><thead>${head}</thead><tbody>${bhRow}${body}</tbody></table>`;
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
          safe(() => chart.removeOverlay()); drawings = [];
          applyTF();
          loadNotes();
          fetchLive();
          renderPlaybook();
        })
        .catch((e) => { status("could not load " + id + " — " + e.message); });
    }

    // ---- asset registry ----
    updateAuth();
    fetch("price_assets.json?v=" + Date.now()).then((r) => r.json())
      .then((list) => { ASSETS = list; })
      .catch(() => { ASSETS = [{ id: "spx", label: "S&P 500", klass: "Indices", ticker: "^GSPC" }, { id: "ndx", label: "Nasdaq 100", klass: "Indices", ticker: "^NDX" }]; })
      .then(() => {
        const sel = $("assetSel"), groups = {};
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
