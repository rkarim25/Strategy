/**
 * Strategy Lab — compose a strategy from an ENTRY group and an EXIT group, each a STACK of conditions
 * combined with AND/OR. A condition = indicator (SMA/EMA/SMA-cross/RSI/MACD/Bollinger/Donchian/price)
 * + a state predicate (e.g. "price above the line", "RSI below level"). The group's combined state is
 * AND/OR of its conditions; the group "fires" on the rising edge of that combined state. Entry fires
 * (while flat) -> go long (1x/2x/3x); exit fires (while long) -> cash. Pick the asset (S&P 500 / Nasdaq)
 * and back-test period/decade; KPIs track the charted window. Time-linked charts + Combined/Separate
 * layout toggle + equity-P&L-vs-buy&hold. Client-side; reuses window.SP.
 *
 * Extend: add an entry to IND { id,label,panel, params, states, compute(close,p)->{lines,state} }.
 * A single condition with a state + rising-edge == the usual "cross" trigger.
 */
(function () {
  "use strict";
  const TD = 252, COST = 0.001, CLOSE_C = "#1d1d1f";
  const ASSETS = { spx: { label: "S&P 500", url: "band_lab_spx.json" }, ndx: { label: "Nasdaq", url: "lab_ndx.json" } };
  const STORE = "https://lab-strategy-store.rkarim88.workers.dev"; // Cloudflare Worker + KV ("Save to cloud")
  const fmtLev = (x) => (x > 0 ? x.toFixed(0) + "x" : "0x");
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x * 100).toFixed(2) + "%");
  const f3 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(3));
  const f2 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(2));
  const money = (x) => (x == null || !isFinite(x) ? "—" : "$" + Math.round(x).toLocaleString());
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------------- indicator math ----------------
  function sma(c, n) { const o = Array(c.length).fill(null); let s = 0; for (let i = 0; i < c.length; i++) { s += c[i]; if (i >= n) s -= c[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
  function emaSeries(c, n) { const o = Array(c.length).fill(null); const k = 2 / (n + 1); let e = null; for (let i = 0; i < c.length; i++) { const v = c[i]; if (v == null) { o[i] = e; continue; } e = e == null ? v : v * k + e * (1 - k); if (i >= n - 1) o[i] = e; } return o; }
  function rsi(c, n) { const o = Array(c.length).fill(null); let ag = 0, al = 0; for (let i = 1; i < c.length; i++) { const ch = c[i] - c[i - 1], g = Math.max(ch, 0), l = Math.max(-ch, 0); if (i <= n) { ag += g; al += l; if (i === n) { ag /= n; al /= n; o[i] = 100 - 100 / (1 + (al === 0 ? 1e9 : ag / al)); } } else { ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n; o[i] = 100 - 100 / (1 + (al === 0 ? 1e9 : ag / al)); } } return o; }
  function macd(c, f, s, sig) { const ef = emaSeries(c, f), es = emaSeries(c, s); const m = c.map((_, i) => (ef[i] == null || es[i] == null ? null : ef[i] - es[i])); const sg = emaSeries(m.map((v) => (v == null ? 0 : v)), sig).map((v, i) => (m[i] == null ? null : v)); return { macd: m, signal: sg }; }
  function rollStd(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let m = 0; for (let j = i - n + 1; j <= i; j++) m += c[j]; m /= n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (c[j] - m) ** 2; o[i] = Math.sqrt(v / n); } return o; }
  function rollMax(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let x = -Infinity; for (let j = i - n + 1; j <= i; j++) if (c[j] > x) x = c[j]; o[i] = x; } return o; }
  function rollMin(c, n) { const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let x = Infinity; for (let j = i - n + 1; j <= i; j++) if (c[j] < x) x = c[j]; o[i] = x; } return o; }
  const tref = (r, i) => (typeof r === "number" ? r : r[i]);
  function above(a, ref) { const n = a.length, o = Array(n).fill(false); for (let i = 0; i < n; i++) { const r = tref(ref, i); if (a[i] != null && r != null && a[i] >= r) o[i] = true; } return o; }
  function below(a, ref) { const n = a.length, o = Array(n).fill(false); for (let i = 0; i < n; i++) { const r = tref(ref, i); if (a[i] != null && r != null && a[i] <= r) o[i] = true; } return o; }
  const shift1 = (a) => a.map((_, i) => (i ? a[i - 1] : null));
  const risingEdge = (s) => s.map((v, i) => (i > 0 && v && !s[i - 1]));   // true only on the bar a state turns on
  const crossUp = (a, ref) => risingEdge(above(a, ref));   // a crosses UP through ref (was below, now at/above) — momentary
  const crossDn = (a, ref) => risingEdge(below(a, ref));   // a crosses DOWN through ref (was above, now at/below) — momentary

  // ---------------- indicator registry ----------------
  // compute(close,p) -> { lines:[{label,color,values}], state:{ stateId: bool[] (currently-true) } }
  const IND = {
    sma: {
      label: "Price vs SMA", panel: "price",
      params: [{ k: "window", label: "SMA days", d: 100, min: 2, max: 400, step: 1 }, { k: "offset", label: "Offset %", d: 0, min: -15, max: 15, step: 0.5 }],
      states: [{ id: "above", label: "price ABOVE the line" }, { id: "below", label: "price BELOW the line" }, { id: "xu", label: "price CROSSES UP through the line (from below)" }, { id: "xd", label: "price CROSSES DOWN through the line (from above)" }],
      compute(c, p) { const s = sma(c, p.window); const off = p.offset / 100; const line = off ? s.map((x) => (x == null ? null : x * (1 + off))) : s; const lines = [{ label: "SMA" + p.window, color: "#b26a00", values: s }]; if (off) lines.push({ label: `SMA${p.window} ${p.offset > 0 ? "+" : ""}${p.offset}%`, color: "#15803d", values: line }); return { lines, state: { above: above(c, line), below: below(c, line), xu: crossUp(c, line), xd: crossDn(c, line) } }; },
    },
    ema: {
      label: "Price vs EMA", panel: "price",
      params: [{ k: "window", label: "EMA days", d: 100, min: 2, max: 400, step: 1 }, { k: "offset", label: "Offset %", d: 0, min: -15, max: 15, step: 0.5 }],
      states: [{ id: "above", label: "price ABOVE the line" }, { id: "below", label: "price BELOW the line" }, { id: "xu", label: "price CROSSES UP through the line (from below)" }, { id: "xd", label: "price CROSSES DOWN through the line (from above)" }],
      compute(c, p) { const s = emaSeries(c, p.window); const off = p.offset / 100; const line = off ? s.map((x) => (x == null ? null : x * (1 + off))) : s; const lines = [{ label: "EMA" + p.window, color: "#b26a00", values: s }]; if (off) lines.push({ label: `EMA${p.window} ${p.offset > 0 ? "+" : ""}${p.offset}%`, color: "#15803d", values: line }); return { lines, state: { above: above(c, line), below: below(c, line), xu: crossUp(c, line), xd: crossDn(c, line) } }; },
    },
    sma_cross: {
      label: "SMA cross (fast/slow)", panel: "price",
      params: [{ k: "fast", label: "Fast SMA", d: 50, min: 2, max: 200, step: 1 }, { k: "slow", label: "Slow SMA", d: 200, min: 5, max: 400, step: 1 }],
      states: [{ id: "fa", label: "fast ABOVE slow (bullish)" }, { id: "fb", label: "fast BELOW slow (bearish)" }, { id: "gx", label: "GOLDEN cross — fast crosses ABOVE slow" }, { id: "dx", label: "DEATH cross — fast crosses BELOW slow" }],
      compute(c, p) { const f = sma(c, p.fast), s = sma(c, p.slow); return { lines: [{ label: "SMA" + p.fast, color: "#2563eb", values: f }, { label: "SMA" + p.slow, color: "#b26a00", values: s }], state: { fa: above(f, s), fb: below(f, s), gx: crossUp(f, s), dx: crossDn(f, s) } }; },
    },
    rsi: {
      label: "RSI", panel: "osc",
      params: [{ k: "period", label: "RSI period", d: 14, min: 2, max: 50, step: 1 }, { k: "level", label: "Level", d: 30, min: 1, max: 99, step: 1 }],
      states: [{ id: "above", label: "RSI ABOVE level" }, { id: "below", label: "RSI BELOW level" }, { id: "xu", label: "RSI CROSSES UP through level (from below)" }, { id: "xd", label: "RSI CROSSES DOWN through level (from above)" }],
      compute(c, p) { const r = rsi(c, p.period); return { lines: [{ label: "RSI" + p.period, color: "#7c3aed", values: r }, { label: "Level " + p.level, color: "rgba(0,0,0,.45)", values: c.map(() => p.level) }], state: { above: above(r, p.level), below: below(r, p.level), xu: crossUp(r, p.level), xd: crossDn(r, p.level) } }; },
    },
    macd: {
      label: "MACD", panel: "osc",
      params: [{ k: "fast", label: "Fast EMA", d: 12, min: 2, max: 50, step: 1 }, { k: "slow", label: "Slow EMA", d: 26, min: 3, max: 100, step: 1 }, { k: "signal", label: "Signal EMA", d: 9, min: 2, max: 50, step: 1 }],
      states: [{ id: "as", label: "MACD ABOVE signal" }, { id: "bs", label: "MACD BELOW signal" }, { id: "az", label: "MACD ABOVE zero" }, { id: "bz", label: "MACD BELOW zero" }, { id: "xsu", label: "MACD CROSSES ABOVE signal (bullish)" }, { id: "xsd", label: "MACD CROSSES BELOW signal (bearish)" }, { id: "xzu", label: "MACD CROSSES ABOVE zero" }, { id: "xzd", label: "MACD CROSSES BELOW zero" }],
      compute(c, p) { const m = macd(c, p.fast, p.slow, p.signal); return { lines: [{ label: "MACD", color: "#2563eb", values: m.macd }, { label: "Signal", color: "#b26a00", values: m.signal }, { label: "0", color: "rgba(0,0,0,.45)", values: c.map(() => 0) }], state: { as: above(m.macd, m.signal), bs: below(m.macd, m.signal), az: above(m.macd, 0), bz: below(m.macd, 0), xsu: crossUp(m.macd, m.signal), xsd: crossDn(m.macd, m.signal), xzu: crossUp(m.macd, 0), xzd: crossDn(m.macd, 0) } }; },
    },
    boll: {
      label: "Bollinger Bands", panel: "price",
      params: [{ k: "window", label: "Window", d: 20, min: 5, max: 100, step: 1 }, { k: "k", label: "Std devs", d: 2, min: 0.5, max: 4, step: 0.1 }],
      states: [{ id: "au", label: "price ABOVE upper" }, { id: "bu", label: "price BELOW upper" }, { id: "al", label: "price ABOVE lower" }, { id: "bl", label: "price BELOW lower" }, { id: "xau", label: "price CROSSES ABOVE upper (breakout)" }, { id: "xbu", label: "price CROSSES BACK BELOW upper" }, { id: "xal", label: "price CROSSES BACK ABOVE lower (reversion)" }, { id: "xbl", label: "price CROSSES BELOW lower (breakdown)" }],
      compute(c, p) { const mid = sma(c, p.window), sd = rollStd(c, p.window); const up = mid.map((m, i) => (m == null ? null : m + p.k * sd[i])), lo = mid.map((m, i) => (m == null ? null : m - p.k * sd[i])); return { lines: [{ label: "SMA" + p.window, color: "#b26a00", values: mid }, { label: "Upper", color: "#15803d", values: up }, { label: "Lower", color: "#b42318", values: lo }], state: { au: above(c, up), bu: below(c, up), al: above(c, lo), bl: below(c, lo), xau: crossUp(c, up), xbu: crossDn(c, up), xal: crossUp(c, lo), xbl: crossDn(c, lo) } }; },
    },
    donchian: {
      label: "Donchian channel", panel: "price",
      params: [{ k: "window", label: "Window", d: 20, min: 3, max: 200, step: 1 }],
      states: [{ id: "ah", label: "price at/above N-high" }, { id: "al", label: "price at/below N-low" }, { id: "xbo", label: "NEW N-high breakout (crosses up)" }, { id: "xbd", label: "NEW N-low breakdown (crosses down)" }],
      compute(c, p) { const up = rollMax(c, p.window), lo = rollMin(c, p.window); return { lines: [{ label: "High" + p.window, color: "#15803d", values: up }, { label: "Low" + p.window, color: "#b42318", values: lo }], state: { ah: above(c, shift1(up)), al: below(c, shift1(lo)), xbo: crossUp(c, shift1(up)), xbd: crossDn(c, shift1(lo)) } }; },
    },
    price: {
      label: "Price level", panel: "price",
      params: [{ k: "level", label: "Price level", d: 3000, min: 1, max: 100000, step: 10 }],
      states: [{ id: "above", label: "price ABOVE level" }, { id: "below", label: "price BELOW level" }, { id: "xu", label: "price CROSSES UP through level (from below)" }, { id: "xd", label: "price CROSSES DOWN through level (from above)" }],
      compute(c, p) { return { lines: [{ label: "Level " + p.level, color: "rgba(0,0,0,.5)", values: c.map(() => p.level) }], state: { above: above(c, p.level), below: below(c, p.level), xu: crossUp(c, p.level), xd: crossDn(c, p.level) } }; },
    },
  };
  const defaultsFor = (id) => { const o = {}; IND[id].params.forEach((q) => (o[q.k] = q.d)); return o; };
  const newCond = (id) => ({ ind: id, params: defaultsFor(id), st: IND[id].states[0].id });

  // ---------------- backtest / stats ----------------
  function backtest(close, tbill, lev) { const n = close.length, eq = Array(n), ret = Array(n); let prev = 0, e = 100; for (let i = 0; i < n; i++) { const ar = i === 0 ? 0 : close[i] / close[i - 1] - 1, cash = (tbill[i] || 0) / TD, ll = i === 0 ? 0 : lev[i - 1]; let r = ll * ar + (1 - ll) * cash - Math.abs(ll - prev) * COST; prev = ll; e *= 1 + r; eq[i] = e; ret[i] = r; } return { equity: eq, ret }; }
  function stats(eq, ret, tbill) { const n = eq.length; if (n < 2) return { cagr: NaN, vol: NaN, sharpe: NaN, sortino: NaN, calmar: NaN, maxdd: NaN, end: eq[n - 1] }; const years = n / TD, end = eq[n - 1]; const cagr = Math.pow(end / eq[0], 1 / years) - 1; let mean = 0; for (const r of ret) mean += r; mean /= n; let v = 0, dn = 0; for (const r of ret) { v += (r - mean) ** 2; if (r < 0) dn += r * r; } const vol = Math.sqrt(v / (n - 1)) * Math.sqrt(TD), down = Math.sqrt(dn / n) * Math.sqrt(TD); let rf = 0; for (const t of tbill) rf += t; rf /= n; const ann = mean * TD; let peak = -Infinity, mdd = 0; for (const x of eq) { if (x > peak) peak = x; const dd = x / peak - 1; if (dd < mdd) mdd = dd; } return { cagr, vol, sharpe: vol ? (ann - rf) / vol : NaN, sortino: down ? (ann - rf) / down : NaN, calmar: mdd < 0 ? cagr / Math.abs(mdd) : NaN, maxdd: mdd, end }; }
  function transitions(lev, dates, close) { const entry = [], exit = []; for (let i = 1; i < lev.length; i++) { if (lev[i] === lev[i - 1]) continue; const up = lev[i] > lev[i - 1]; const m = { date: dates[i], dir: up ? "up" : "down", color: up ? "#15803d" : "#b42318", label: up ? fmtLev(lev[i]) : "out", tip: `<b>${up ? "Entry" : "Exit"}</b><br>${dates[i]}<br>${fmtLev(lev[i - 1])} → ${fmtLev(lev[i])}` + (close[i] != null ? `<br>close ${close[i].toLocaleString()}` : "") }; (up ? entry : exit).push(m); } return { entry, exit, all: entry.concat(exit) }; }

  function groupSignal(close, group) {
    const comps = group.conds.map((cond) => ({ ind: IND[cond.ind], comp: IND[cond.ind].compute(close, cond.params), st: cond.st }));
    const n = close.length, comb = Array(n).fill(false);
    for (let i = 0; i < n; i++) { if (!comps.length) { comb[i] = false; continue; } const vals = comps.map((c) => !!(c.comp.state[c.st] || [])[i]); comb[i] = group.op === "or" ? vals.some(Boolean) : vals.every(Boolean); }
    const fires = Array(n).fill(false);
    for (let i = 1; i < n; i++) fires[i] = comb[i] && !comb[i - 1];
    return { fires, comps };
  }

  // ---------------- styles ----------------
  function injectLabStyles() {
    if (document.getElementById("lab-styles")) return;
    const s = document.createElement("style"); s.id = "lab-styles";
    s.textContent = `
      .lab-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;}
      @media(max-width:780px){.lab-grid{grid-template-columns:1fr;}}
      .grp h3{margin:0 0 6px;font-size:15px;}
      .grp.entry h3{color:#15803d;} .grp.exit h3{color:#b42318;}
      .grp .opbar{display:flex;align-items:center;gap:8px;margin:4px 0 10px;}
      .grp .opbar .seg button{font:inherit;font-size:12px;font-weight:600;padding:4px 12px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .grp .opbar .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .grp .opbar .joiner{font-size:12px;color:var(--muted);}
      .condrow{border:1px solid var(--line);border-radius:14px;padding:10px 12px;margin:8px 0;background:rgba(255,255,255,.5);position:relative;}
      .condrow label{display:block;font-size:11.5px;font-weight:600;color:#6e6e73;margin-bottom:3px;}
      .condrow select,.condrow input[type=number]{font:inherit;font-size:13px;padding:6px 9px;border-radius:9px;border:1px solid var(--line);background:#fff;width:100%;}
      .condrow .params{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0;}
      .condrow .rm{position:absolute;top:8px;right:10px;border:none;background:none;color:var(--muted);cursor:pointer;font-size:16px;line-height:1;}
      .condrow .rm:hover{color:var(--bad);}
      .addcond{font:inherit;font-size:13px;font-weight:600;color:var(--accent);background:none;border:1px dashed var(--line);border-radius:10px;padding:8px 12px;cursor:pointer;width:100%;}
      .lab-bar{display:flex;gap:22px;flex-wrap:wrap;align-items:center;margin-top:6px;}
      .lab-bar .seg{display:flex;gap:6px;}
      .lab-bar .seg button{font:inherit;font-size:13px;font-weight:600;padding:7px 14px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .lab-bar .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .lab-bar .lbl{font-size:12px;font-weight:600;color:#6e6e73;margin-right:6px;}
      .lab-bar select,.lab-bar input[type=date]{font:inherit;font-size:13px;padding:6px 9px;border-radius:9px;border:1px solid var(--line);background:#fff;}
      .lab-bar .apply{font:inherit;font-size:12px;font-weight:600;padding:6px 12px;border-radius:9px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer;}
      .save-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;}
      .save-row input{font:inherit;font-size:13px;padding:8px 12px;border-radius:10px;border:1px solid var(--line);min-width:200px;flex:1;}
      .save-row button{font:inherit;font-size:13px;font-weight:600;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .save-row button.apply{background:var(--accent);color:#fff;border-color:var(--accent);}
      #stratNotes{font:inherit;font-size:13px;padding:10px 12px;border-radius:10px;border:1px solid var(--line);width:100%;resize:vertical;box-sizing:border-box;}
      .saved-item{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:8px;}
      .saved-item .sh{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
      .saved-item .nm{font-weight:700;}
      .saved-item .meta2{font-size:12px;color:var(--muted);flex:1;}
      .saved-item .notes{font-size:12.5px;color:var(--muted);margin-top:5px;white-space:pre-wrap;}
      .saved-item button{font:inherit;font-size:12px;font-weight:600;padding:4px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
    `;
    document.head.appendChild(s);
  }

  // ---------------- app ----------------
  function run() {
    injectLabStyles();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const D = { dates: [], close: [], tbill: [], label: "", n: 0, bh: null };
    const state = {
      asset: "spx", period: "full", cs: "", ce: "",
      entry: { op: "and", conds: [{ ind: "sma", params: { window: 100, offset: -2 }, st: "above" }] },
      exit: { op: "and", conds: [{ ind: "sma", params: { window: 100, offset: 2 }, st: "below" }] },
      lev: 1, layout: "combined",
    };
    let savedWin = [0, 0], lastBt = null, descs = [], lastSig = null, tmr = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1 id="labTitle">Lab</h1>
      <p class="lede">Build a strategy by stacking conditions (combined with <b>AND</b>/<b>OR</b>); a group fires when
        its combined state turns on. Entry → go long (1×/2×/3×); exit → cash. The metrics track the charted
        window — set a back-test period or zoom any chart. 1-day lag, 0.10% turnover cost, synthetic daily-rebalanced leverage.</p>
      <div class="card">
        <div class="lab-bar" style="margin-bottom:16px">
          <div><span class="lbl">Asset</span><span class="seg" id="assetSeg"></span></div>
          <div><span class="lbl">Back-test period</span>
            <select id="periodSel"></select>
            <span id="customWrap" style="display:none">
              <input type="date" id="pStart" /> <input type="date" id="pEnd" />
              <button id="pApply" class="apply">Apply</button></span></div>
        </div>
        <div class="lab-grid">
          <div class="grp entry" id="grpEntry"></div>
          <div class="grp exit" id="grpExit"></div>
        </div>
        <div class="lab-bar">
          <div><span class="lbl">Leverage</span><span class="seg" id="levSeg"></span></div>
          <div><span class="lbl">Charts</span><span class="seg" id="layoutSeg"></span></div>
        </div>
      </div>
      <div class="card"><div class="kpis" id="kpis"></div>
        <p class="meta" id="bhNote" style="margin-top:10px"></p></div>
      <div class="card">
        <h2>Save &amp; notes</h2>
        <div class="save-row">
          <input id="stratName" placeholder="Strategy name…" />
          <button id="saveBtn" class="apply">Save here</button>
          <button id="cloudBtn">☁ Save to cloud &amp; copy link</button>
          <button id="shareBtn">Copy offline link</button>
          <span class="meta" id="cloudAuth"></span>
          <span class="meta" id="saveFlash" style="color:var(--good)"></span>
        </div>
        <textarea id="stratNotes" rows="3" placeholder="Notes about this strategy…"></textarea>
        <p class="meta" style="margin-top:8px"><b>Save here</b> = this browser (localStorage). <b>☁ Save to cloud</b> = saved on the site (Cloudflare), giving a short <code>?id=</code> link that opens the strategy + notes on any device. Saving needs your <b>passphrase</b> (one-time login per browser); anyone can <i>open</i> a shared link, only you can save. <b>Offline link</b> packs everything into a <code>#s=</code> URL with no server.</p>
        <div id="savedList"></div>
      </div>
      <div id="charts"></div>`;

    const KPI = [["CAGR", "cagr"], ["Max drawdown", "maxdd"], ["Calmar", "calmar"], ["Sortino", "sortino"],
                 ["Sharpe", "sharpe"], ["Volatility", "vol"], ["End $ ($100→)", "end"], ["% time invested", "pctIn"]];
    document.getElementById("kpis").innerHTML = KPI.map(([k]) => `<div class="kpi"><div class="k">${k}</div><div class="v" data-kpi="${k}">—</div></div>`).join("");
    function seg(c, btn) { c.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === btn)); }

    const assetSeg = document.getElementById("assetSeg");
    Object.keys(ASSETS).forEach((id) => { const b = document.createElement("button"); b.textContent = ASSETS[id].label; if (id === state.asset) b.classList.add("active"); b.onclick = () => { seg(assetSeg, b); loadAsset(id); }; assetSeg.appendChild(b); });
    const levSeg = document.getElementById("levSeg");
    [1, 2, 3].forEach((L) => { const b = document.createElement("button"); b.textContent = L + "x"; if (L === state.lev) b.classList.add("active"); b.onclick = () => { state.lev = L; seg(levSeg, b); schedule(); }; levSeg.appendChild(b); });
    const layoutSeg = document.getElementById("layoutSeg");
    [["combined", "Combined"], ["separate", "Separate entry/exit"]].forEach(([id, t]) => { const b = document.createElement("button"); b.textContent = t; if (id === state.layout) b.classList.add("active"); b.onclick = () => { state.layout = id; seg(layoutSeg, b); rebuild(); }; layoutSeg.appendChild(b); });

    const periodSel = document.getElementById("periodSel"), customWrap = document.getElementById("customWrap");
    periodSel.addEventListener("change", () => { state.period = periodSel.value; customWrap.style.display = state.period === "custom" ? "" : "none"; if (state.period !== "custom") applyPeriod(); });
    document.getElementById("pApply").addEventListener("click", () => { state.cs = document.getElementById("pStart").value; state.ce = document.getElementById("pEnd").value; applyPeriod(); });

    // ---- condition group UI ----
    function renderGroup(role) {
      const host = document.getElementById(role === "entry" ? "grpEntry" : "grpExit");
      const grp = state[role];
      host.innerHTML = `<h3>${role === "entry" ? "▲ Entry" : "▼ Exit"} conditions</h3>`;
      if (grp.conds.length > 1) {
        const bar = document.createElement("div"); bar.className = "opbar";
        bar.innerHTML = `<span class="joiner">combine with</span>`;
        const segEl = document.createElement("span"); segEl.className = "seg";
        ["and", "or"].forEach((op) => { const b = document.createElement("button"); b.textContent = op.toUpperCase(); if (grp.op === op) b.classList.add("active"); b.onclick = () => { grp.op = op; seg(segEl, b); schedule(); }; segEl.appendChild(b); });
        bar.appendChild(segEl); host.appendChild(bar);
      }
      grp.conds.forEach((cond, idx) => host.appendChild(condRow(role, grp, cond, idx)));
      const add = document.createElement("button"); add.className = "addcond"; add.textContent = "+ Add condition";
      add.onclick = () => { grp.conds.push(newCond("rsi")); renderGroup(role); rebuild(); };
      host.appendChild(add);
    }
    function condRow(role, grp, cond, idx) {
      const row = document.createElement("div"); row.className = "condrow";
      const indSel = document.createElement("select");
      Object.keys(IND).forEach((id) => { const o = document.createElement("option"); o.value = id; o.textContent = IND[id].label; if (id === cond.ind) o.selected = true; indSel.appendChild(o); });
      const paramsBox = document.createElement("div"); paramsBox.className = "params";
      const stSel = document.createElement("select");
      const renderParams = () => { paramsBox.innerHTML = ""; IND[cond.ind].params.forEach((q) => { const w = document.createElement("div"); w.innerHTML = `<label>${q.label}</label>`; const inp = document.createElement("input"); inp.type = "number"; inp.min = q.min; inp.max = q.max; inp.step = q.step; inp.value = cond.params[q.k]; inp.addEventListener("input", () => { const v = +inp.value; if (isFinite(v)) { cond.params[q.k] = v; schedule(); } }); w.appendChild(inp); paramsBox.appendChild(w); }); };
      const renderStates = () => { stSel.innerHTML = ""; IND[cond.ind].states.forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.label; if (s.id === cond.st) o.selected = true; stSel.appendChild(o); }); };
      indSel.addEventListener("change", () => { cond.ind = indSel.value; cond.params = defaultsFor(cond.ind); cond.st = IND[cond.ind].states[0].id; renderParams(); renderStates(); rebuild(); });
      stSel.addEventListener("change", () => { cond.st = stSel.value; schedule(); });
      const r1 = document.createElement("div"); r1.innerHTML = "<label>Indicator</label>"; r1.appendChild(indSel);
      const r3 = document.createElement("div"); r3.innerHTML = "<label>Condition (true when)</label>"; r3.appendChild(stSel);
      row.appendChild(r1); row.appendChild(paramsBox); row.appendChild(r3);
      if (grp.conds.length > 1) { const rm = document.createElement("button"); rm.className = "rm"; rm.textContent = "✕"; rm.title = "Remove condition"; rm.onclick = () => { grp.conds.splice(idx, 1); renderGroup(role); rebuild(); }; row.appendChild(rm); }
      renderParams(); renderStates();
      return row;
    }
    renderGroup("entry"); renderGroup("exit");

    // ---- period ----
    const idxGE = (d) => { for (let i = 0; i < D.n; i++) if (D.dates[i] >= d) return i; return D.n; };
    const idxGT = (d) => { for (let i = D.n - 1; i >= 0; i--) if (D.dates[i] <= d) return i + 1; return 0; };
    function periodRange() {
      const v = state.period, n = D.n;
      if (v === "full") return [0, n];
      if (v[0] === "L") return [Math.max(0, n - (+v.slice(1)) * TD), n];
      if (v[0] === "S") return [idxGE(v.slice(1) + "-01-01"), n];
      if (v[0] === "D") { const y = +v.slice(1); return [idxGE(y + "-01-01"), idxGE((y + 10) + "-01-01")]; }
      if (v === "custom") { const a = state.cs ? idxGE(state.cs) : 0, b = state.ce ? idxGT(state.ce) : n; return [a, Math.max(a + 1, b)]; }
      return [0, n];
    }
    function buildPeriodOptions() {
      const n = D.n, sy = +D.dates[0].slice(0, 4), ey = +D.dates[n - 1].slice(0, 4);
      const opts = [["full", "Full history"]];
      if (n >= 10 * TD) opts.push(["L10", "Last 10 years"]);
      if (n >= 20 * TD) opts.push(["L20", "Last 20 years"]);
      [2020, 2010, 2000, 1990, 1980].forEach((y) => { if (y > sy) opts.push(["S" + y, "Since " + y]); });
      for (let d = Math.floor(sy / 10) * 10; d <= Math.floor(ey / 10) * 10; d += 10) opts.push(["D" + d, d + "s"]);
      opts.push(["custom", "Custom dates…"]);
      periodSel.innerHTML = opts.map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
      periodSel.value = "full"; state.period = "full"; customWrap.style.display = "none";
    }
    function applyPeriod() { savedWin = periodRange(); descs.forEach((d) => d.card.setWindow(savedWin[0], savedWin[1])); setKPIsForWindow(); }

    // ---- compute / kpis ----
    function computeStrategy() {
      const e = groupSignal(D.close, state.entry), x = groupSignal(D.close, state.exit);
      const lev = Array(D.n).fill(0); let st = 0;
      for (let i = 0; i < D.n; i++) { if (st === 0 && e.fires[i]) st = state.lev; else if (st > 0 && x.fires[i]) st = 0; lev[i] = st; }
      const bt = backtest(D.close, D.tbill, lev); lastBt = { equity: bt.equity, ret: bt.ret, lev };
      return { entryComps: e.comps, exitComps: x.comps, mk: transitions(lev, D.dates, D.close) };
    }
    function setKPIs(s) { const v = { cagr: pct(s.cagr), maxdd: pct(s.maxdd), calmar: f2(s.calmar), sortino: f3(s.sortino), sharpe: f3(s.sharpe), vol: pct(s.vol), end: money(s.end), pctIn: (s.pctIn * 100).toFixed(1) + "%" }; KPI.forEach(([k, key]) => { const el = document.querySelector(`[data-kpi="${k}"]`); if (el) el.textContent = v[key]; }); }
    function setKPIsForWindow() {
      if (!lastBt) return;
      const a = Math.max(0, savedWin[0]), b = Math.min(D.n, savedWin[1]), hi = Math.max(a + 2, b);
      const reb = (arr) => { const sl = arr.slice(a, hi), base = sl[0]; return sl.map((x) => 100 * x / base); };   // $100 at window start
      const s = stats(reb(lastBt.equity), lastBt.ret.slice(a, hi), D.tbill.slice(a, hi));
      s.pctIn = lastBt.lev.slice(a, hi).reduce((acc, v) => acc + (v > 0 ? 1 : 0), 0) / (hi - a);
      setKPIs(s);
      const bs = stats(reb(D.bh.equity), D.bh.ret.slice(a, hi), D.tbill.slice(a, hi));
      document.getElementById("bhNote").innerHTML = `Buy &amp; hold 1× over the charted window (${D.dates[a]} → ${D.dates[hi - 1]}): CAGR <b>${pct(bs.cagr)}</b> · Max DD <b>${pct(bs.maxdd)}</b> · Sharpe <b>${f3(bs.sharpe)}</b> · End <b>${money(bs.end)}</b>.`;
    }

    // ---- charts ----
    function sync(lo, hi) { savedWin = [lo, hi]; descs.forEach((d) => { const w = d.card.getWindow(); if (w[0] !== lo || w[1] !== hi) d.card.setWindow(lo, hi); }); setKPIsForWindow(); }
    const SER = (lines) => lines.map((l) => ({ label: l.label, color: l.color, width: l.width, values: l.values }));
    const priceOverlays = (comps) => comps.filter((c) => c.ind.panel === "price").flatMap((c) => c.comp.lines);
    const oscComps = (comps) => comps.map((c, i) => ({ c, i })).filter((o) => o.c.ind.panel === "osc");
    function makeDescriptors(ctx) {
      const list = [], closeLine = () => ({ label: D.label + " close", color: CLOSE_C, values: D.close });
      if (state.layout === "combined") {
        list.push({ title: "Price & indicators — entry/exit markers", mk: "all", series: (c) => SER([closeLine(), ...priceOverlays(c.entryComps), ...priceOverlays(c.exitComps)]) });
        oscComps(ctx.entryComps).forEach(({ i }) => list.push({ title: "Entry: " + ctx.entryComps[i].ind.label, mk: "entry", series: (c) => SER(c.entryComps[i].comp.lines) }));
        oscComps(ctx.exitComps).forEach(({ i }) => list.push({ title: "Exit: " + ctx.exitComps[i].ind.label, mk: "exit", series: (c) => SER(c.exitComps[i].comp.lines) }));
      } else {
        if (ctx.entryComps.some((c) => c.ind.panel === "price")) list.push({ title: "Entry — price & indicators", mk: "entry", series: (c) => SER([closeLine(), ...priceOverlays(c.entryComps)]) });
        oscComps(ctx.entryComps).forEach(({ i }) => list.push({ title: "Entry: " + ctx.entryComps[i].ind.label, mk: "entry", series: (c) => SER(c.entryComps[i].comp.lines) }));
        if (ctx.exitComps.some((c) => c.ind.panel === "price")) list.push({ title: "Exit — price & indicators", mk: "exit", series: (c) => SER([closeLine(), ...priceOverlays(c.exitComps)]) });
        oscComps(ctx.exitComps).forEach(({ i }) => list.push({ title: "Exit: " + ctx.exitComps[i].ind.label, mk: "exit", series: (c) => SER(c.exitComps[i].comp.lines) }));
      }
      list.push({ title: "Equity P&L vs buy & hold (% return, rebased to 0%)", rebase: true, mk: "all", series: () => [{ label: "Strategy", color: "#0071e3", width: 2, values: lastBt.equity }, { label: "Buy & hold 1×", color: "#6e6e73", values: D.bh.equity }] });
      return list;
    }
    const sigOf = (ctx) => state.layout + "|E:" + ctx.entryComps.map((c) => c.ind.label).join(",") + "|X:" + ctx.exitComps.map((c) => c.ind.label).join(",");
    function rebuild() {
      const ctx = computeStrategy();
      const host = document.getElementById("charts"); host.innerHTML = "";
      const specs = makeDescriptors(ctx);
      descs = specs.map((sp) => { const card = SP.chartBlock(sp.title, D.dates, sp.series(ctx), { rebasePct: !!sp.rebase, customDates: true, markerDefs: ctx.mk[sp.mk], onWindow: sync, defaultRange: "Full" }); host.appendChild(card); return { card, spec: sp }; });   // Lab is a backtester → full history; its period dropdown controls the window
      descs.forEach((d) => d.card.setWindow(savedWin[0], savedWin[1]));
      lastSig = sigOf(ctx); setKPIsForWindow();
    }
    function schedule() {
      if (tmr) clearTimeout(tmr);
      tmr = setTimeout(() => {
        tmr = null;
        const ctx = computeStrategy();
        if (sigOf(ctx) !== lastSig || !descs.length) { rebuild(); return; }
        descs.forEach((d) => d.card.update(d.spec.series(ctx), ctx.mk[d.spec.mk]));
        setKPIsForWindow();
      }, 90);
    }

    // ---- asset load ----
    function loadAsset(id) {
      state.asset = id;
      document.getElementById("charts").innerHTML = '<p class="meta">Loading…</p>';
      fetch(ASSETS[id].url)   // cache via ETag/max-age (was no-store → full re-download on every asset switch)
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then((data) => {
          D.dates = data.dates; D.close = data.close; D.tbill = data.tbill; D.label = data.asset_label || ASSETS[id].label; D.n = data.close.length;
          D.bh = backtest(D.close, D.tbill, Array(D.n).fill(1));
          document.getElementById("labTitle").textContent = D.label + " — Lab";
          buildPeriodOptions();
          savedWin = periodRange();
          rebuild();
        })
        .catch((e) => { document.getElementById("charts").innerHTML = `<p class="err">Could not load ${ASSETS[id].url} — ${e.message}</p>`; });
    }
    // ---- save / notes / share (browser localStorage + portable links) ----
    const LS_KEY = "lab_saved_v1";
    const enc = (rec) => btoa(encodeURIComponent(JSON.stringify(rec)));
    const dec = (str) => JSON.parse(decodeURIComponent(atob(str)));
    const loadSaved = () => { try { return JSON.parse(localStorage.getItem(LS_KEY)) || []; } catch (_) { return []; } };
    const writeSaved = (arr) => { try { localStorage.setItem(LS_KEY, JSON.stringify(arr)); } catch (_) {} };
    const currentConfig = () => ({ asset: state.asset, period: state.period, cs: state.cs, ce: state.ce, lev: state.lev, layout: state.layout, entry: state.entry, exit: state.exit });
    const findBtn = (c, t) => [...c.querySelectorAll("button")].find((b) => b.textContent === t);
    function applyConfig(cfg) {
      if (!cfg || !cfg.entry || !cfg.exit) return;
      state.entry = cfg.entry; state.exit = cfg.exit; state.lev = +cfg.lev || 1; state.layout = cfg.layout === "separate" ? "separate" : "combined";
      state.period = cfg.period || "full"; state.cs = cfg.cs || ""; state.ce = cfg.ce || "";
      renderGroup("entry"); renderGroup("exit");
      const lb = findBtn(levSeg, state.lev + "x"); if (lb) seg(levSeg, lb);
      const yb = findBtn(layoutSeg, state.layout === "separate" ? "Separate entry/exit" : "Combined"); if (yb) seg(layoutSeg, yb);
      const id = ASSETS[cfg.asset] ? cfg.asset : "spx"; const ab = findBtn(assetSeg, ASSETS[id].label); if (ab) seg(assetSeg, ab);
      loadAsset(id);
    }
    function flash(msg) { const el = document.getElementById("saveFlash"); if (el) { el.textContent = msg; setTimeout(() => { el.textContent = ""; }, 2600); } }
    function copyShare(rec) { const url = location.origin + location.pathname + "#s=" + enc(rec); if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => flash("Share link copied")).catch(() => flash("Could not copy")); else flash("Copy from address bar"); }
    function renderSavedList() {
      const host = document.getElementById("savedList"), arr = loadSaved();
      if (!arr.length) { host.innerHTML = `<p class="meta">No saved strategies yet.</p>`; return; }
      host.innerHTML = arr.map((s, i) => `<div class="saved-item"><div class="sh">
        <span class="nm">${esc(s.name)}</span>
        <span class="meta2">${(s.config.entry.conds || []).length} entry · ${(s.config.exit.conds || []).length} exit · ${esc((ASSETS[s.config.asset] || {}).label || "")} · ${s.config.lev}× · ${esc(s.savedAt || "")}</span>
        <button data-load="${i}">Load</button><button data-share="${i}">Share</button><button data-del="${i}">Delete</button></div>
        ${s.notes ? `<div class="notes">${esc(s.notes)}</div>` : ""}</div>`).join("");
      host.querySelectorAll("[data-load]").forEach((b) => (b.onclick = () => { const s = loadSaved()[+b.dataset.load]; document.getElementById("stratName").value = s.name || ""; document.getElementById("stratNotes").value = s.notes || ""; applyConfig(s.config); flash("Loaded “" + (s.name || "") + "”"); }));
      host.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { const a = loadSaved(); a.splice(+b.dataset.del, 1); writeSaved(a); renderSavedList(); }));
      host.querySelectorAll("[data-share]").forEach((b) => (b.onclick = () => { const s = loadSaved()[+b.dataset.share]; copyShare({ name: s.name, notes: s.notes, config: s.config }); }));
    }
    document.getElementById("saveBtn").onclick = () => { const name = (document.getElementById("stratName").value || "").trim() || ("Strategy " + (loadSaved().length + 1)); const notes = document.getElementById("stratNotes").value || ""; const arr = loadSaved(); arr.unshift({ name, notes, config: currentConfig(), savedAt: new Date().toISOString().slice(0, 10) }); writeSaved(arr); renderSavedList(); flash("Saved “" + name + "”"); };
    document.getElementById("shareBtn").onclick = () => copyShare({ name: (document.getElementById("stratName").value || "").trim(), notes: document.getElementById("stratNotes").value || "", config: currentConfig() });

    // ---- cloud save (server-side, persists & cross-device; passphrase-gated writes) ----
    const cloudBtn = document.getElementById("cloudBtn"), CLOUD_KEY = "lab_cloud_key";
    const getKey = () => { try { return localStorage.getItem(CLOUD_KEY) || ""; } catch (_) { return ""; } };
    function setKey(k) { try { k ? localStorage.setItem(CLOUD_KEY, k) : localStorage.removeItem(CLOUD_KEY); } catch (_) {} updateCloudAuth(); }
    function updateCloudAuth() {
      const el = document.getElementById("cloudAuth");
      if (getKey()) { el.innerHTML = `signed in · <a href="#" id="cloudLogout">log out</a>`; el.querySelector("#cloudLogout").onclick = (e) => { e.preventDefault(); setKey(""); flash("Logged out"); }; }
      else el.textContent = "";
    }
    function ensureKey() {
      const k = getKey();
      if (k) return Promise.resolve(k);
      const entry = (window.prompt("Cloud-save passphrase (one-time login for this browser):") || "").trim();
      if (!entry) return Promise.resolve("");
      return fetch(STORE + "/api/auth", { method: "POST", headers: { "X-Lab-Key": entry } })
        .then((r) => { if (!r.ok) { flash("Wrong passphrase"); return ""; } setKey(entry); flash("Signed in"); return entry; })
        .catch(() => { flash("Login failed — network?"); return ""; });
    }
    cloudBtn.onclick = () => {
      ensureKey().then((key) => {
        if (!key) return;
        const name = (document.getElementById("stratName").value || "").trim(), notes = document.getElementById("stratNotes").value || "";
        cloudBtn.disabled = true; flash("Saving to cloud…");
        fetch(STORE + "/api/strategy", { method: "POST", headers: { "Content-Type": "application/json", "X-Lab-Key": key }, body: JSON.stringify({ name, notes, config: currentConfig() }) })
          .then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired — click again"); } return r.json().then((j) => { if (!r.ok || !j.id) throw new Error(j.error || ("HTTP " + r.status)); return j.id; }); })
          .then((cid) => { const url = location.origin + location.pathname + "?id=" + cid; const done = () => flash("Cloud link copied  ·  /?id=" + cid); navigator.clipboard ? navigator.clipboard.writeText(url).then(done).catch(done) : done(); })
          .catch((e) => flash("Cloud save failed: " + e.message))
          .finally(() => { cloudBtn.disabled = false; });
      });
    };
    updateCloudAuth();
    function loadCloud(cid) {
      flash("Loading shared strategy…");
      fetch(STORE + "/api/strategy/" + encodeURIComponent(cid))
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 404 ? "not found" : "HTTP " + r.status))))
        .then((rec) => { if (!rec || !rec.config) throw new Error("bad record"); document.getElementById("stratName").value = rec.name || ""; document.getElementById("stratNotes").value = rec.notes || ""; applyConfig(rec.config); flash("Loaded shared strategy “" + (rec.name || cid) + "”"); })
        .catch((e) => { loadAsset(state.asset); flash("Could not load /?id=" + cid + " — " + e.message); });
    }
    renderSavedList();

    // initial: cloud ?id= link → offline #s= link → default asset
    const cloudId = new URLSearchParams(location.search).get("id");
    let bootRec = null;
    try { if (location.hash.indexOf("#s=") === 0) bootRec = dec(location.hash.slice(3)); } catch (_) {}
    if (cloudId) loadCloud(cloudId);
    else if (bootRec && bootRec.config) { document.getElementById("stratName").value = bootRec.name || ""; document.getElementById("stratNotes").value = bootRec.notes || ""; applyConfig(bootRec.config); }
    else loadAsset(state.asset);
  }

  function boot() {
    if (!window.SP || !SP.chartBlock) { setTimeout(boot, 30); return; }
    SP.injectStyles && SP.injectStyles();
    run();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
