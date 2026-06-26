/**
 * Shared full-parity strategy page renderer.
 *
 * A thin host page sets `window.STRATEGY_DATA_URL` (a *_site_data.json) and
 * `window.STRATEGY_PAGE_TITLE`, includes site-nav.js then this file. This builds the
 * full Signal / Back-test / Monte-Carlo experience (current signal, KPI cards,
 * interactive equity + price/SMA charts, comparison table, Monte-Carlo) from the
 * precomputed payload — works for both band (S&P Water) and golden-cross (Nasdaq) data.
 */
(function () {
  "use strict";
  const DATA_URL = window.STRATEGY_DATA_URL;
  const ACCENT = "#0071e3";

  const fmt = (v) => (v == null || v === "" ? "—" : v);
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

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
      .ranges{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0;}
      .ranges button{font:inherit;font-size:12px;padding:5px 12px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .ranges button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px;}
      .legend span{display:inline-flex;align-items:center;gap:6px;} .legend i{width:14px;height:3px;border-radius:2px;display:inline-block;}
      .meta{font-size:12.5px;color:var(--muted);line-height:1.5;}
      .err{color:var(--bad);font-weight:600;}
    `;
    document.head.appendChild(s);
  }

  // ---- canvas line chart ----
  function lineChart(canvas, dates, series, { log = false } = {}) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth || 900, H = 320;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const padL = 56, padR = 12, padT = 12, padB = 24;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (const v of s.values) if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (!isFinite(lo) || !isFinite(hi)) return;
    const tf = (v) => (log ? Math.log10(Math.max(v, 1e-9)) : v);
    let tlo = tf(lo), thi = tf(hi); if (tlo === thi) thi = tlo + 1;
    const n = dates.length;
    const xAt = (i) => padL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
    const yAt = (v) => padT + plotH - ((tf(v) - tlo) / (thi - tlo)) * plotH;
    // gridlines + y labels
    ctx.strokeStyle = "rgba(0,0,0,.07)"; ctx.fillStyle = "#6e6e73"; ctx.font = "11px system-ui"; ctx.textAlign = "right";
    for (let g = 0; g <= 4; g++) {
      const y = padT + (g / 4) * plotH;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      const tv = thi - (g / 4) * (thi - tlo); const val = log ? Math.pow(10, tv) : tv;
      ctx.fillText(val >= 1000 ? Math.round(val).toLocaleString() : val.toFixed(val < 10 ? 1 : 0), padL - 6, y + 3);
    }
    // x labels (first / mid / last)
    ctx.textAlign = "center";
    for (const i of [0, Math.floor((n - 1) / 2), n - 1]) {
      if (i >= 0 && i < n && dates[i]) ctx.fillText(String(dates[i]).slice(0, 7), xAt(i), H - 7);
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
  }

  function chartBlock(title, dates, seriesDefs, { log = false, ranges = true } = {}) {
    const wrap = document.createElement("div"); wrap.className = "card";
    wrap.innerHTML = `<h2>${esc(title)}</h2>`;
    const cw = document.createElement("div"); cw.className = "chartwrap";
    const canvas = document.createElement("canvas"); cw.appendChild(canvas); wrap.appendChild(cw);
    const legend = document.createElement("div"); legend.className = "legend";
    legend.innerHTML = seriesDefs.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join("");
    wrap.appendChild(legend);
    let curN = dates.length;
    const draw = () => {
      const start = Math.max(0, dates.length - curN);
      const d = dates.slice(start);
      const ser = seriesDefs.map((s) => ({ color: s.color, width: s.width, values: s.values.slice(start) }));
      lineChart(canvas, d, ser, { log });
    };
    if (ranges) {
      const rdiv = document.createElement("div"); rdiv.className = "ranges";
      const opts = [["1Y", 252], ["5Y", 1260], ["10Y", 2520], ["Full", dates.length]];
      for (const [lbl, days] of opts) {
        if (days > dates.length && lbl !== "Full") continue;
        const b = document.createElement("button"); b.textContent = lbl; if (lbl === "Full") b.classList.add("active");
        b.onclick = () => { curN = Math.min(days, dates.length); rdiv.querySelectorAll("button").forEach((x) => x.classList.remove("active")); b.classList.add("active"); draw(); };
        rdiv.appendChild(b);
      }
      wrap.appendChild(rdiv);
    }
    setTimeout(draw, 0);
    window.addEventListener("resize", draw);
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
    const isLong = sig && Number(sig.leverage) > 0;

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
    bann.innerHTML = `<div class="signal-banner ${isLong ? "long" : "cash"}">
      <div><div class="big">${isLong ? `IN — ${Number(sig.leverage).toFixed(0)}× exposure` : "CASH"}</div>
      <div class="sub">As of ${esc(sig ? sig.date : "—")} · last close ${esc(sig && sig.spx_close != null ? sig.spx_close.toLocaleString() : "—")}</div></div>
    </div>
    <p class="meta">Signal recomputed daily from the precomputed history; for an intraday what-if, the page can be regenerated. This page does not auto-poll a live quote (only the Gold page does).</p>`;
    vs.appendChild(bann);
    if (d.price_sma_data) {
      const p = d.price_sma_data, defs = [{ label: asset + " close", color: "#1d1d1f", values: p.spx_close }];
      if (p.sma200) defs.push({ label: "SMA200", color: ACCENT, values: p.sma200 });
      if (p.sma50) defs.push({ label: "SMA50", color: "#b26a00", values: p.sma50 });
      if (p.sma200_upper_band) defs.push({ label: "Upper band", color: "rgba(36,138,61,.5)", values: p.sma200_upper_band });
      if (p.sma200_lower_band) defs.push({ label: "Lower band", color: "rgba(215,0,21,.5)", values: p.sma200_lower_band });
      vs.appendChild(chartBlock("Price & moving averages", p.dates, defs, { log: false }));
    }
    // recent signal history
    const sh = (d.signal_history || []).slice(-14).reverse();
    if (sh.length) {
      const rows = sh.map((r) => `<tr><td class="l">${esc(r.date)}</td><td class="l">${r.leverage > 0 ? "Long " + Number(r.leverage).toFixed(0) + "×" : "Cash"}</td>
        <td class="num">${r.spx_close != null ? r.spx_close.toLocaleString() : "—"}</td><td class="l">${esc(r.action || "")}</td></tr>`).join("");
      const c = document.createElement("div"); c.className = "card";
      c.innerHTML = `<h2>Recent signal history</h2><div class="tbl-wrap"><table><thead><tr><th class="l">Date</th><th class="l">Signal</th><th>Close</th><th class="l">Action</th></tr></thead><tbody>${rows}</tbody></table></div>`;
      vs.appendChild(c);
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
      vb.appendChild(chartBlock("Growth of $100 (log scale)", e.dates, [
        { label: name, color: ACCENT, width: 2, values: e.strategy_equity },
        { label: "Buy & hold 1×", color: "#6e6e73", values: e.buy_hold_1x_equity },
      ], { log: true }));
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

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
