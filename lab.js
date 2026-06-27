/**
 * Strategy Lab — compose a strategy from an ENTRY condition and an EXIT condition, each built from a
 * library of indicators (SMA / EMA / SMA-cross / RSI / MACD / Bollinger / Donchian / price level).
 * Entry fires -> go long (1x/2x/3x); exit fires -> cash. Everything renders on time-linked charts
 * (indicator panels + equity-P&L-vs-buy&hold), with a Combined/Separate layout toggle. Fully
 * client-side; reuses the shared chart engine (window.SP) from strategy_page.js.
 *
 * Extend it by adding an entry to the IND registry: { id,label,panel, params, triggers, compute }.
 */
(function () {
  "use strict";
  const DATA_URL = "band_lab_spx.json";
  const TD = 252, COST = 0.001;
  const fmtLev = (x) => (x > 0 ? x.toFixed(0) + "x" : "0x");
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x * 100).toFixed(2) + "%");
  const f3 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(3));
  const f2 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(2));
  const money = (x) => (x == null || !isFinite(x) ? "—" : "$" + Math.round(x).toLocaleString());

  // ---------------- indicator math ----------------
  function sma(c, n) { const o = Array(c.length).fill(null); let s = 0; for (let i = 0; i < c.length; i++) { s += c[i]; if (i >= n) s -= c[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
  function emaSeries(c, n) { const o = Array(c.length).fill(null); const k = 2 / (n + 1); let e = null, started = false; for (let i = 0; i < c.length; i++) { const v = c[i]; if (v == null) { o[i] = e; continue; } e = e == null ? v : v * k + e * (1 - k); if (i >= n - 1) { started = true; } if (started) o[i] = e; } return o; }
  function rsi(c, n) { const o = Array(c.length).fill(null); let ag = 0, al = 0; for (let i = 1; i < c.length; i++) { const ch = c[i] - c[i - 1], g = Math.max(ch, 0), l = Math.max(-ch, 0); if (i <= n) { ag += g; al += l; if (i === n) { ag /= n; al /= n; o[i] = 100 - 100 / (1 + (al === 0 ? 1e9 : ag / al)); } } else { ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n; o[i] = 100 - 100 / (1 + (al === 0 ? 1e9 : ag / al)); } } return o; }
  function macd(c, f, s, sig) { const ef = emaSeries(c, f), es = emaSeries(c, s); const m = c.map((_, i) => (ef[i] == null || es[i] == null ? null : ef[i] - es[i])); const sg = emaSeries(m.map((v) => (v == null ? 0 : v)), sig).map((v, i) => (m[i] == null ? null : v)); const h = m.map((v, i) => (v == null || sg[i] == null ? null : v - sg[i])); return { macd: m, signal: sg, hist: h }; }
  function rollStd(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let m = 0; for (let j = i - n + 1; j <= i; j++) m += c[j]; m /= n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (c[j] - m) ** 2; o[i] = Math.sqrt(v / n); } return o; }
  function rollMax(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let x = -Infinity; for (let j = i - n + 1; j <= i; j++) if (c[j] > x) x = c[j]; o[i] = x; } return o; }
  function rollMin(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let x = Infinity; for (let j = i - n + 1; j <= i; j++) if (c[j] < x) x = c[j]; o[i] = x; } return o; }
  const tref = (r, i) => (typeof r === "number" ? r : r[i]);
  function crossUp(a, ref) { const n = a.length, o = Array(n).fill(false); for (let i = 1; i < n; i++) { const r = tref(ref, i), rp = tref(ref, i - 1); if (a[i - 1] != null && a[i] != null && r != null && rp != null && a[i - 1] < rp && a[i] >= r) o[i] = true; } return o; }
  function crossDn(a, ref) { const n = a.length, o = Array(n).fill(false); for (let i = 1; i < n; i++) { const r = tref(ref, i), rp = tref(ref, i - 1); if (a[i - 1] != null && a[i] != null && r != null && rp != null && a[i - 1] > rp && a[i] <= r) o[i] = true; } return o; }
  const shift1 = (a) => a.map((_, i) => (i ? a[i - 1] : null));
  const CLOSE_C = "#1d1d1f";

  // ---------------- indicator registry ----------------
  // compute(close, p) -> { lines:[{label,color,values}], sig:{ triggerId: bool[] } }
  const IND = {
    sma: {
      label: "Price vs SMA", panel: "price",
      params: [{ k: "window", label: "SMA days", d: 100, min: 2, max: 400, step: 1 }, { k: "offset", label: "Offset %", d: 0, min: -15, max: 15, step: 0.5 }],
      triggers: [{ id: "cu", label: "price crosses ABOVE the line" }, { id: "cd", label: "price crosses BELOW the line" }],
      compute(c, p) { const s = sma(c, p.window); const off = p.offset / 100; const line = off ? s.map((x) => (x == null ? null : x * (1 + off))) : s; const lines = [{ label: "SMA" + p.window, color: "#b26a00", values: s }]; if (off) lines.push({ label: `SMA${p.window} ${p.offset > 0 ? "+" : ""}${p.offset}%`, color: "#15803d", values: line }); return { lines, sig: { cu: crossUp(c, line), cd: crossDn(c, line) } }; },
    },
    ema: {
      label: "Price vs EMA", panel: "price",
      params: [{ k: "window", label: "EMA days", d: 100, min: 2, max: 400, step: 1 }, { k: "offset", label: "Offset %", d: 0, min: -15, max: 15, step: 0.5 }],
      triggers: [{ id: "cu", label: "price crosses ABOVE the line" }, { id: "cd", label: "price crosses BELOW the line" }],
      compute(c, p) { const s = emaSeries(c, p.window); const off = p.offset / 100; const line = off ? s.map((x) => (x == null ? null : x * (1 + off))) : s; const lines = [{ label: "EMA" + p.window, color: "#b26a00", values: s }]; if (off) lines.push({ label: `EMA${p.window} ${p.offset > 0 ? "+" : ""}${p.offset}%`, color: "#15803d", values: line }); return { lines, sig: { cu: crossUp(c, line), cd: crossDn(c, line) } }; },
    },
    sma_cross: {
      label: "SMA cross (fast/slow)", panel: "price",
      params: [{ k: "fast", label: "Fast SMA", d: 50, min: 2, max: 200, step: 1 }, { k: "slow", label: "Slow SMA", d: 200, min: 5, max: 400, step: 1 }],
      triggers: [{ id: "gc", label: "fast crosses ABOVE slow (golden)" }, { id: "dc", label: "fast crosses BELOW slow (death)" }],
      compute(c, p) { const f = sma(c, p.fast), s = sma(c, p.slow); return { lines: [{ label: "SMA" + p.fast, color: "#2563eb", values: f }, { label: "SMA" + p.slow, color: "#b26a00", values: s }], sig: { gc: crossUp(f, s), dc: crossDn(f, s) } }; },
    },
    rsi: {
      label: "RSI", panel: "osc",
      params: [{ k: "period", label: "RSI period", d: 14, min: 2, max: 50, step: 1 }, { k: "level", label: "Level", d: 30, min: 1, max: 99, step: 1 }],
      triggers: [{ id: "cu", label: "RSI crosses ABOVE level" }, { id: "cd", label: "RSI crosses BELOW level" }],
      compute(c, p) { const r = rsi(c, p.period); return { lines: [{ label: "RSI" + p.period, color: "#7c3aed", values: r }, { label: "Level " + p.level, color: "rgba(0,0,0,.45)", values: c.map(() => p.level) }], sig: { cu: crossUp(r, p.level), cd: crossDn(r, p.level) } }; },
    },
    macd: {
      label: "MACD", panel: "osc",
      params: [{ k: "fast", label: "Fast EMA", d: 12, min: 2, max: 50, step: 1 }, { k: "slow", label: "Slow EMA", d: 26, min: 3, max: 100, step: 1 }, { k: "signal", label: "Signal EMA", d: 9, min: 2, max: 50, step: 1 }],
      triggers: [{ id: "csu", label: "MACD crosses ABOVE signal" }, { id: "csd", label: "MACD crosses BELOW signal" }, { id: "zu", label: "MACD crosses ABOVE zero" }, { id: "zd", label: "MACD crosses BELOW zero" }],
      compute(c, p) { const m = macd(c, p.fast, p.slow, p.signal); return { lines: [{ label: "MACD", color: "#2563eb", values: m.macd }, { label: "Signal", color: "#b26a00", values: m.signal }, { label: "0", color: "rgba(0,0,0,.45)", values: c.map(() => 0) }], sig: { csu: crossUp(m.macd, m.signal), csd: crossDn(m.macd, m.signal), zu: crossUp(m.macd, 0), zd: crossDn(m.macd, 0) } }; },
    },
    boll: {
      label: "Bollinger Bands", panel: "price",
      params: [{ k: "window", label: "Window", d: 20, min: 5, max: 100, step: 1 }, { k: "k", label: "Std devs", d: 2, min: 0.5, max: 4, step: 0.1 }],
      triggers: [{ id: "cuu", label: "price crosses ABOVE upper" }, { id: "cdu", label: "price crosses BELOW upper" }, { id: "cul", label: "price crosses ABOVE lower" }, { id: "cdl", label: "price crosses BELOW lower" }],
      compute(c, p) { const mid = sma(c, p.window), sd = rollStd(c, p.window); const up = mid.map((m, i) => (m == null ? null : m + p.k * sd[i])), lo = mid.map((m, i) => (m == null ? null : m - p.k * sd[i])); return { lines: [{ label: "SMA" + p.window, color: "#b26a00", values: mid }, { label: "Upper", color: "#15803d", values: up }, { label: "Lower", color: "#b42318", values: lo }], sig: { cuu: crossUp(c, up), cdu: crossDn(c, up), cul: crossUp(c, lo), cdl: crossDn(c, lo) } }; },
    },
    donchian: {
      label: "Donchian channel", panel: "price",
      params: [{ k: "window", label: "Window", d: 20, min: 3, max: 200, step: 1 }],
      triggers: [{ id: "bu", label: "price breaks ABOVE N-high" }, { id: "bd", label: "price breaks BELOW N-low" }],
      compute(c, p) { const up = rollMax(c, p.window), lo = rollMin(c, p.window); return { lines: [{ label: "High" + p.window, color: "#15803d", values: up }, { label: "Low" + p.window, color: "#b42318", values: lo }], sig: { bu: crossUp(c, shift1(up)), bd: crossDn(c, shift1(lo)) } }; },
    },
    price: {
      label: "Price level", panel: "price",
      params: [{ k: "level", label: "Price level", d: 3000, min: 1, max: 10000, step: 10 }],
      triggers: [{ id: "cu", label: "price crosses ABOVE level" }, { id: "cd", label: "price crosses BELOW level" }],
      compute(c, p) { return { lines: [{ label: "Level " + p.level, color: "rgba(0,0,0,.5)", values: c.map(() => p.level) }], sig: { cu: crossUp(c, p.level), cd: crossDn(c, p.level) } }; },
    },
  };
  const defaultsFor = (id) => { const o = {}; IND[id].params.forEach((q) => (o[q.k] = q.d)); return o; };

  // ---------------- backtest / stats ----------------
  function backtest(close, tbill, lev) { const n = close.length, eq = Array(n), ret = Array(n); let prev = 0, e = 100; for (let i = 0; i < n; i++) { const ar = i === 0 ? 0 : close[i] / close[i - 1] - 1, cash = (tbill[i] || 0) / TD, ll = i === 0 ? 0 : lev[i - 1]; let r = ll * ar + (1 - ll) * cash - Math.abs(ll - prev) * COST; prev = ll; e *= 1 + r; eq[i] = e; ret[i] = r; } return { equity: eq, ret }; }
  function stats(eq, ret, tbill) { const n = eq.length, years = n / TD, end = eq[n - 1]; const cagr = Math.pow(end / eq[0], 1 / years) - 1; let mean = 0; for (const r of ret) mean += r; mean /= n; let v = 0, dn = 0; for (const r of ret) { v += (r - mean) ** 2; if (r < 0) dn += r * r; } const vol = Math.sqrt(v / (n - 1)) * Math.sqrt(TD), down = Math.sqrt(dn / n) * Math.sqrt(TD); let rf = 0; for (const t of tbill) rf += t; rf /= n; const ann = mean * TD; const sharpe = vol ? (ann - rf) / vol : NaN, sortino = down ? (ann - rf) / down : NaN; let peak = -Infinity, mdd = 0; for (const x of eq) { if (x > peak) peak = x; const dd = x / peak - 1; if (dd < mdd) mdd = dd; } return { cagr, vol, sharpe, sortino, calmar: mdd < 0 ? cagr / Math.abs(mdd) : NaN, maxdd: mdd, end }; }
  function transitions(lev, dates, close) { const entry = [], exit = []; for (let i = 1; i < lev.length; i++) { if (lev[i] === lev[i - 1]) continue; const up = lev[i] > lev[i - 1]; const m = { date: dates[i], dir: up ? "up" : "down", color: up ? "#15803d" : "#b42318", label: up ? fmtLev(lev[i]) : "out", tip: `<b>${up ? "Entry" : "Exit"}</b><br>${dates[i]}<br>${fmtLev(lev[i - 1])} → ${fmtLev(lev[i])}` + (close[i] != null ? `<br>close ${close[i].toLocaleString()}` : "") }; (up ? entry : exit).push(m); } return { entry, exit, all: entry.concat(exit) }; }

  // ---------------- styles ----------------
  function injectLabStyles() {
    if (document.getElementById("lab-styles")) return;
    const s = document.createElement("style"); s.id = "lab-styles";
    s.textContent = `
      .lab-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;}
      @media(max-width:760px){.lab-grid{grid-template-columns:1fr;}}
      .cond h3{margin:0 0 10px;font-size:15px;}
      .cond.entry h3{color:#15803d;} .cond.exit h3{color:#b42318;}
      .cond .row{margin:8px 0;}
      .cond label{display:block;font-size:12px;font-weight:600;color:#6e6e73;margin-bottom:3px;}
      .cond select,.cond input[type=number]{font:inherit;font-size:13px;padding:6px 9px;border-radius:9px;border:1px solid var(--line);background:#fff;width:100%;}
      .cond .params{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
      .lab-bar{display:flex;gap:22px;flex-wrap:wrap;align-items:center;margin-top:4px;}
      .lab-bar .seg{display:flex;gap:6px;}
      .lab-bar .seg button{font:inherit;font-size:13px;font-weight:600;padding:7px 14px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .lab-bar .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .lab-bar .lbl{font-size:12px;font-weight:600;color:#6e6e73;margin-right:6px;}
    `;
    document.head.appendChild(s);
  }

  // ---------------- app ----------------
  function run(data) {
    const dates = data.dates, close = data.close, tbill = data.tbill, label = data.asset_label || "S&P 500";
    const n = close.length;
    const bh = backtest(close, tbill, Array(n).fill(1));
    const bhSt = stats(bh.equity, bh.ret, tbill);
    let savedWin = [Math.max(0, n - 2520), n];   // shared time window (default last ~10y)

    const state = {
      entry: { ind: "sma", params: { window: 100, offset: -2 }, trig: "cu" },
      exit: { ind: "sma", params: { window: 100, offset: 2 }, trig: "cd" },
      lev: 1, layout: "combined",
    };

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1>${label} — Lab</h1>
      <p class="lede">Build a strategy: pick an <b style="color:#15803d">entry</b> condition and an
        <b style="color:#b42318">exit</b> condition from the indicator library, choose leverage, and the
        metrics + linked charts recompute live. Entry → go long; exit → cash. Full S&P 500 history,
        1-day signal lag, 0.10% turnover cost, synthetic daily-rebalanced leverage (cash/funding at T-bills).</p>
      <div class="card"><div class="lab-grid">
        <div class="cond entry" id="condEntry"><h3>▲ Entry condition</h3></div>
        <div class="cond exit" id="condExit"><h3>▼ Exit condition</h3></div>
      </div>
      <div class="lab-bar">
        <div><span class="lbl">Leverage</span><span class="seg" id="levSeg"></span></div>
        <div><span class="lbl">Charts</span><span class="seg" id="layoutSeg"></span></div>
      </div></div>
      <div class="card"><div class="kpis" id="kpis"></div>
        <p class="meta" id="bhNote" style="margin-top:10px"></p></div>
      <div id="charts"></div>`;

    document.getElementById("bhNote").innerHTML =
      `Buy &amp; hold 1× reference: CAGR <b>${pct(bhSt.cagr)}</b> · Max DD <b>${pct(bhSt.maxdd)}</b> · Sharpe <b>${f3(bhSt.sharpe)}</b> · End <b>${money(bhSt.end)}</b>.`;

    const KPI = [["CAGR", "cagr"], ["Max drawdown", "maxdd"], ["Calmar", "calmar"], ["Sortino", "sortino"],
                 ["Sharpe", "sharpe"], ["Volatility", "vol"], ["End $ ($100→)", "end"], ["% time invested", "pctIn"]];
    document.getElementById("kpis").innerHTML = KPI.map(([k]) => `<div class="kpi"><div class="k">${k}</div><div class="v" data-kpi="${k}">—</div></div>`).join("");

    // leverage + layout toggles
    const levSeg = document.getElementById("levSeg");
    [1, 2, 3].forEach((L) => { const b = document.createElement("button"); b.textContent = L + "x"; if (L === state.lev) b.classList.add("active"); b.onclick = () => { state.lev = L; seg(levSeg, b); schedule(); }; levSeg.appendChild(b); });
    const layoutSeg = document.getElementById("layoutSeg");
    [["combined", "Combined"], ["separate", "Separate entry/exit"]].forEach(([id, t]) => { const b = document.createElement("button"); b.textContent = t; if (id === state.layout) b.classList.add("active"); b.onclick = () => { state.layout = id; seg(layoutSeg, b); rebuild(); }; layoutSeg.appendChild(b); });
    function seg(container, btn) { container.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === btn)); }

    // condition builders
    buildCond("entry", document.getElementById("condEntry"));
    buildCond("exit", document.getElementById("condExit"));
    function buildCond(role, host) {
      const cur = state[role];
      const indSel = document.createElement("select");
      Object.keys(IND).forEach((id) => { const o = document.createElement("option"); o.value = id; o.textContent = IND[id].label; if (id === cur.ind) o.selected = true; indSel.appendChild(o); });
      const paramsBox = document.createElement("div"); paramsBox.className = "params";
      const trigSel = document.createElement("select");
      const renderParams = () => {
        paramsBox.innerHTML = "";
        IND[cur.ind].params.forEach((q) => {
          const wrap = document.createElement("div");
          wrap.innerHTML = `<label>${q.label}</label>`;
          const inp = document.createElement("input"); inp.type = "number"; inp.min = q.min; inp.max = q.max; inp.step = q.step; inp.value = cur.params[q.k];
          inp.addEventListener("input", () => { const v = +inp.value; if (isFinite(v)) { cur.params[q.k] = v; schedule(); } });
          wrap.appendChild(inp); paramsBox.appendChild(wrap);
        });
      };
      const renderTriggers = () => { trigSel.innerHTML = ""; IND[cur.ind].triggers.forEach((t) => { const o = document.createElement("option"); o.value = t.id; o.textContent = t.label; if (t.id === cur.trig) o.selected = true; trigSel.appendChild(o); }); };
      indSel.addEventListener("change", () => { cur.ind = indSel.value; cur.params = defaultsFor(cur.ind); cur.trig = IND[cur.ind].triggers[0].id; renderParams(); renderTriggers(); rebuild(); });
      trigSel.addEventListener("change", () => { cur.trig = trigSel.value; schedule(); });
      const r1 = document.createElement("div"); r1.className = "row"; r1.innerHTML = "<label>Indicator</label>"; r1.appendChild(indSel);
      const r2 = document.createElement("div"); r2.className = "row"; r2.appendChild(paramsBox);
      const r3 = document.createElement("div"); r3.className = "row"; r3.innerHTML = "<label>Trigger</label>"; r3.appendChild(trigSel);
      host.appendChild(r1); host.appendChild(r2); host.appendChild(r3);
      renderParams(); renderTriggers();
    }

    // ---- compute + charts ----
    function computeCtx() {
      const eComp = IND[state.entry.ind].compute(close, state.entry.params);
      const xComp = IND[state.exit.ind].compute(close, state.exit.params);
      const eFire = eComp.sig[state.entry.trig] || [], xFire = xComp.sig[state.exit.trig] || [];
      const lev = Array(n).fill(0); let st = 0;
      for (let i = 0; i < n; i++) { if (st === 0 && eFire[i]) st = state.lev; else if (st > 0 && xFire[i]) st = 0; lev[i] = st; }
      const bt = backtest(close, tbill, lev); const stt = stats(bt.equity, bt.ret, tbill); stt.pctIn = lev.reduce((a, v) => a + (v > 0 ? 1 : 0), 0) / n;
      return { eInd: IND[state.entry.ind], xInd: IND[state.exit.ind], eComp, xComp, equity: bt.equity, mk: transitions(lev, dates, close), stt };
    }

    function setKPIs(s) { const v = { cagr: pct(s.cagr), maxdd: pct(s.maxdd), calmar: f2(s.calmar), sortino: f3(s.sortino), sharpe: f3(s.sharpe), vol: pct(s.vol), end: money(s.end), pctIn: (s.pctIn * 100).toFixed(1) + "%" }; KPI.forEach(([k, key]) => { const el = document.querySelector(`[data-kpi="${k}"]`); if (el) el.textContent = v[key]; }); }

    // chart descriptors: each {card, build(ctx)->{series,markers}}
    let descs = [];
    function sync(lo, hi) { savedWin = [lo, hi]; descs.forEach((d) => { const w = d.card.getWindow(); if (w[0] !== lo || w[1] !== hi) d.card.setWindow(lo, hi); }); }
    const SERIES = (lines) => lines.map((l) => ({ label: l.label, color: l.color, width: l.width, values: l.values }));

    function makeDescriptors(ctx) {
      const list = [];
      const priceLines = (c) => { const a = [{ label: label + " close", color: CLOSE_C, values: close }]; if (c.eInd.panel === "price") a.push(...c.eComp.lines); if (c.xInd.panel === "price") a.push(...c.xComp.lines); return a; };
      if (state.layout === "combined") {
        list.push({ title: "Price & indicators — entry/exit markers", build: (c) => ({ series: SERIES(priceLines(c)), markers: c.mk.all }) });
        if (ctx.eInd.panel === "osc") list.push({ title: "Entry: " + ctx.eInd.label, build: (c) => ({ series: SERIES(c.eComp.lines), markers: c.mk.entry }) });
        if (ctx.xInd.panel === "osc") list.push({ title: "Exit: " + ctx.xInd.label, build: (c) => ({ series: SERIES(c.xComp.lines), markers: c.mk.exit }) });
      } else {
        list.push({ title: "Entry: " + ctx.eInd.label, build: (c) => ({ series: SERIES(c.eInd.panel === "price" ? [{ label: label + " close", color: CLOSE_C, values: close }, ...c.eComp.lines] : c.eComp.lines), markers: c.mk.entry }) });
        list.push({ title: "Exit: " + ctx.xInd.label, build: (c) => ({ series: SERIES(c.xInd.panel === "price" ? [{ label: label + " close", color: CLOSE_C, values: close }, ...c.xComp.lines] : c.xComp.lines), markers: c.mk.exit }) });
      }
      list.push({ title: "Equity P&L vs buy & hold (% return, rebased to 0%)", rebase: true, build: (c) => ({ series: [{ label: "Strategy", color: "#0071e3", width: 2, values: c.equity }, { label: "Buy & hold 1×", color: "#6e6e73", values: bh.equity }], markers: c.mk.all }) });
      return list;
    }

    function rebuild() {
      const ctx = computeCtx(); setKPIs(ctx.stt);
      const host = document.getElementById("charts"); host.innerHTML = "";
      const specs = makeDescriptors(ctx);
      descs = specs.map((sp) => { const { series, markers } = sp.build(ctx); const card = SP.chartBlock(sp.title, dates, series, { rebasePct: !!sp.rebase, customDates: true, markerDefs: markers, onWindow: sync }); host.appendChild(card); return { card, build: sp.build, sig: specs.length + "|" + sp.title }; });
      descs.forEach((d) => d.card.setWindow(savedWin[0], savedWin[1]));
      lastSig = sigOf();
    }
    const sigOf = () => state.layout + "|" + state.entry.ind + "|" + state.exit.ind;
    let lastSig = null, t = null;
    function schedule() {
      if (t) clearTimeout(t);
      t = setTimeout(() => {
        t = null;
        if (sigOf() !== lastSig || !descs.length) { rebuild(); return; }   // chart set changed -> rebuild
        const ctx = computeCtx(); setKPIs(ctx.stt);
        descs.forEach((d) => { const { series, markers } = d.build(ctx); d.card.update(series, markers); });
      }, 90);
    }

    rebuild();   // initial
  }

  function boot() {
    if (!window.SP || !SP.chartBlock) { setTimeout(boot, 30); return; }
    SP.injectStyles && SP.injectStyles();
    injectLabStyles();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    fetch(DATA_URL + "?v=" + Date.now(), { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(run)
      .catch((e) => { document.getElementById("app").innerHTML = `<p class="err">Could not load ${DATA_URL} — ${e.message}</p>`; });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
