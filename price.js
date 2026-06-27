/**
 * Price page — daily high/low/close (HLC) bar charts for S&P 500 (^GSPC) and Nasdaq 100 (^NDX).
 * Self-contained canvas chart (does not touch strategy_page.js beyond reusing window.SP styles):
 * asset toggle, range buttons + custom dates, crosshair O/H/L/C readout, live last price via the
 * quote-proxy worker. Bars auto-aggregate to weekly/monthly buckets when zoomed out so the
 * high–low ranges stay legible at every zoom level (daily when zoomed in).
 */
(function () {
  "use strict";
  const QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev";
  const ASSETS = {
    spx: { label: "S&P 500", ticker: "^GSPC", url: "price_spx.json" },
    ndx: { label: "Nasdaq 100", ticker: "^NDX", url: "price_ndx.json" },
  };
  const RANGES = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["2Y", 504], ["5Y", 1260], ["Max", null]];
  const fmt = (x) => (x == null || !isFinite(x) ? "—" : x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const UP = "#15803d", DN = "#b42318";

  function injectStyles() {
    if (document.getElementById("price-styles")) return;
    const s = document.createElement("style"); s.id = "price-styles";
    s.textContent = `
      .pbar{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:4px 0 2px;}
      .pbar .lbl{font-size:12px;font-weight:600;color:#6e6e73;margin-right:6px;}
      .pbar .seg{display:inline-flex;gap:6px;flex-wrap:wrap;}
      .pbar .seg button{font:inherit;font-size:13px;font-weight:600;padding:6px 13px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .pbar .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .pbar input[type=date]{font:inherit;font-size:12px;padding:5px 8px;border-radius:8px;border:1px solid var(--line);}
      .pbar .apply{font:inherit;font-size:12px;font-weight:600;padding:6px 12px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;}
      .live{display:inline-flex;align-items:center;gap:7px;font-size:13px;}
      .live .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);}
      .live.on .dot{background:var(--good);box-shadow:0 0 0 3px rgba(48,209,88,.18);}
      .readout{font-size:12.5px;color:#6e6e73;min-height:18px;margin-top:8px;}
      .readout b{color:var(--ink,#1d1d1f);}
      .readout .o{color:#6e6e73;} .readout .up{color:${UP};} .readout .dn{color:${DN};}
      .pchart{position:relative;width:100%;}
      .pchart canvas{display:block;width:100%;cursor:crosshair;}
    `;
    document.head.appendChild(s);
  }

  function run() {
    injectStyles();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const state = { asset: "spx", win: [0, 0], rangeDays: 126, hover: -1 };
    const D = { ticker: "", label: "", dates: [], open: [], high: [], low: [], close: [], n: 0 };
    let view = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1 id="pTitle">Prices — high / low / close</h1>
      <p class="lede">Daily high–low–close bars. Each vertical bar spans the day's <b>high</b> to <b>low</b>; the right tick is the
        <b>close</b>, the left tick the open. Green = close above the prior bar, red = below. Zoomed out, bars aggregate to
        weekly/monthly so the ranges stay readable. Live last price via the quote proxy.</p>
      <div class="card">
        <div class="pbar" style="margin-bottom:10px">
          <div><span class="lbl">Index</span><span class="seg" id="assetSeg"></span></div>
          <div class="live" id="live"><span class="dot"></span><span id="liveTxt">live —</span></div>
        </div>
        <div class="pbar">
          <div><span class="lbl">Range</span><span class="seg" id="rangeSeg"></span></div>
          <div><span class="lbl">Custom</span><input type="date" id="d0"/> <input type="date" id="d1"/> <button class="apply" id="dApply">Apply</button></div>
        </div>
        <div class="readout" id="readout"></div>
        <div class="pchart"><canvas id="cv"></canvas></div>
        <p class="meta" id="agg" style="margin-top:6px"></p>
      </div>`;

    const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
    const seg = (c, b) => c.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));

    const assetSeg = document.getElementById("assetSeg");
    Object.keys(ASSETS).forEach((id) => { const b = document.createElement("button"); b.textContent = ASSETS[id].label; if (id === state.asset) b.classList.add("active"); b.onclick = () => { seg(assetSeg, b); loadAsset(id); }; assetSeg.appendChild(b); });
    const rangeSeg = document.getElementById("rangeSeg");
    RANGES.forEach(([t, days]) => { const b = document.createElement("button"); b.textContent = t; if (days === state.rangeDays) b.classList.add("active"); b.onclick = () => { seg(rangeSeg, b); setRange(days); }; rangeSeg.appendChild(b); });
    document.getElementById("dApply").onclick = () => {
      const a = document.getElementById("d0").value, z = document.getElementById("d1").value;
      const lo = a ? idxGE(a) : 0, hi = z ? idxGT(z) : D.n;
      state.win = [lo, Math.max(lo + 2, hi)]; seg(rangeSeg, null); draw();
    };

    const idxGE = (d) => { for (let i = 0; i < D.n; i++) if (D.dates[i] >= d) return i; return D.n; };
    const idxGT = (d) => { for (let i = D.n - 1; i >= 0; i--) if (D.dates[i] <= d) return i + 1; return 0; };
    function setRange(days) { state.rangeDays = days; const n = D.n; state.win = days ? [Math.max(0, n - days), n] : [0, n]; draw(); }

    function buildBars() {
      const [lo, hi] = state.win, raw = hi - lo;
      const plotW = Math.max(200, cv.clientWidth - 72);
      const target = Math.max(24, Math.min(280, Math.floor(plotW / 6)));
      const bucket = Math.max(1, Math.ceil(raw / target));
      const bars = [];
      for (let i = lo; i < hi; i += bucket) {
        const j = Math.min(hi, i + bucket);
        let h = -Infinity, l = Infinity;
        for (let k = i; k < j; k++) { if (D.high[k] > h) h = D.high[k]; if (D.low[k] < l) l = D.low[k]; }
        bars.push({ o: D.open[i], h, l, c: D.close[j - 1], i0: i, i1: j - 1, d0: D.dates[i], d1: D.dates[j - 1] });
      }
      return { bars, bucket };
    }

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      const W = cv.clientWidth || cv.parentNode.clientWidth || 700, H = 440;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
      const padL = 62, padR = 14, padT = 14, padB = 30, plotW = W - padL - padR, plotH = H - padT - padB;

      const { bars, bucket } = buildBars();
      if (!bars.length) return;
      let yMin = Infinity, yMax = -Infinity;
      for (const b of bars) { if (b.l < yMin) yMin = b.l; if (b.h > yMax) yMax = b.h; }
      const pad = (yMax - yMin) * 0.05 || 1; yMin -= pad; yMax += pad;
      const Y = (v) => padT + plotH * (1 - (v - yMin) / (yMax - yMin));
      const barW = plotW / bars.length, X = (k) => padL + (k + 0.5) * barW;

      // gridlines + y labels
      ctx.font = "11px -apple-system,system-ui,sans-serif"; ctx.textBaseline = "middle";
      const ticks = 5;
      for (let t = 0; t <= ticks; t++) {
        const v = yMin + (yMax - yMin) * (t / ticks), y = Y(v);
        ctx.strokeStyle = "rgba(0,0,0,.07)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
        ctx.fillStyle = "#8a8a8e"; ctx.textAlign = "right"; ctx.fillText(fmt(v), padL - 8, y);
      }
      // x date labels
      ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = "#8a8a8e";
      const xlab = Math.max(1, Math.floor(bars.length / 6));
      for (let k = 0; k < bars.length; k += xlab) ctx.fillText(bars[k].d1, X(k), H - padB + 8);

      // HLC bars
      const tick = Math.min(barW * 0.34, 5), lw = Math.max(1, Math.min(barW * 0.5, 3));
      ctx.lineWidth = lw; ctx.lineCap = "butt";
      for (let k = 0; k < bars.length; k++) {
        const b = bars[k], x = X(k), up = k > 0 ? b.c >= bars[k - 1].c : b.c >= b.o;
        ctx.strokeStyle = up ? UP : DN;
        ctx.beginPath(); ctx.moveTo(x, Y(b.h)); ctx.lineTo(x, Y(b.l)); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x, Y(b.c)); ctx.lineTo(x + tick, Y(b.c)); ctx.stroke();
        if (tick >= 2) { ctx.beginPath(); ctx.moveTo(x - tick, Y(b.o)); ctx.lineTo(x, Y(b.o)); ctx.stroke(); }
      }
      // crosshair
      if (state.hover >= 0 && state.hover < bars.length) {
        const x = X(state.hover); ctx.strokeStyle = "rgba(0,0,0,.25)"; ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, H - padB); ctx.stroke(); ctx.setLineDash([]);
      }
      view = { bars, barW, padL, plotW, bucket };
      const b = bars[state.hover >= 0 && state.hover < bars.length ? state.hover : bars.length - 1];
      showReadout(b, bars[bars.indexOf(b) - 1]);
      document.getElementById("agg").textContent = bucket === 1
        ? `Daily bars — ${bars.length} trading days (${bars[0].d1} → ${bars[bars.length - 1].d1}).`
        : `Each bar = ${bucket} trading days (high–low range, tick = close) — ${bars.length} bars over ${bars[0].d0} → ${bars[bars.length - 1].d1}.`;
    }

    function showReadout(b, prev) {
      if (!b) { document.getElementById("readout").innerHTML = ""; return; }
      const chg = prev ? (b.c / prev.c - 1) * 100 : 0;
      const cls = chg >= 0 ? "up" : "dn", sign = chg >= 0 ? "+" : "";
      const label = b.i0 === b.i1 ? b.d1 : `${b.d0} → ${b.d1}`;
      document.getElementById("readout").innerHTML =
        `<b>${label}</b> &nbsp; <span class="o">O</span> ${fmt(b.o)} &nbsp; <span class="o">H</span> ${fmt(b.h)} &nbsp; <span class="o">L</span> ${fmt(b.l)} &nbsp; <span class="o">C</span> <b>${fmt(b.c)}</b> &nbsp; <span class="${cls}">${sign}${chg.toFixed(2)}%</span>`;
    }

    cv.addEventListener("mousemove", (e) => {
      if (!view) return;
      const r = cv.getBoundingClientRect(), mx = e.clientX - r.left;
      const k = Math.round((mx - view.padL) / view.barW - 0.5);
      const nk = Math.max(0, Math.min(view.bars.length - 1, k));
      if (nk !== state.hover) { state.hover = nk; draw(); }
    });
    cv.addEventListener("mouseleave", () => { state.hover = -1; draw(); });
    let rT; window.addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(draw, 120); });

    function fetchLive() {
      const a = ASSETS[state.asset], live = document.getElementById("live"), txt = document.getElementById("liveTxt");
      txt.textContent = "live —"; live.classList.remove("on");
      fetch(QUOTE + "/?mode=quote&symbol=" + state.asset + "&_=" + Date.now())
        .then((r) => r.json())
        .then((q) => {
          if (!q || q.ticker !== a.ticker || !(q.price > 0)) { txt.textContent = "live unavailable"; return; }
          const prev = D.close[D.n - 1], chg = ((q.price / prev) - 1) * 100, sign = chg >= 0 ? "+" : "";
          live.classList.add("on");
          txt.innerHTML = `<b>${a.ticker} ${fmt(q.price)}</b> &nbsp;<span style="color:${chg >= 0 ? UP : DN}">${sign}${chg.toFixed(2)}%</span> &nbsp;<span style="color:#8a8a8e">since prev close · ${q.timestamp || ""}</span>`;
        })
        .catch(() => { txt.textContent = "live unavailable"; });
    }

    function loadAsset(id) {
      state.asset = id;
      document.getElementById("readout").textContent = "Loading…";
      fetch(ASSETS[id].url + "?v=" + Date.now())
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then((d) => {
          D.ticker = d.ticker; D.label = d.asset_label || ASSETS[id].label;
          D.dates = d.dates; D.open = d.open; D.high = d.high; D.low = d.low; D.close = d.close; D.n = d.close.length;
          document.getElementById("pTitle").textContent = `${D.label} — high / low / close`;
          state.hover = -1; setRange(state.rangeDays); fetchLive();
        })
        .catch((e) => { document.getElementById("readout").innerHTML = `<span class="dn">Could not load ${ASSETS[id].url} — ${e.message}</span>`; });
    }

    loadAsset(state.asset);
  }

  function boot() {
    if (window.SP && SP.injectStyles) SP.injectStyles();
    if (!document.getElementById("app")) { setTimeout(boot, 30); return; }
    run();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
