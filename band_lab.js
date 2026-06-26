/**
 * Interactive SMA-band strategy lab (client-side backtest).
 *
 * Rule (same as sma_band_sweep.py): ENTER when price crosses the LOWER band (SMA*(1-lower%)) from
 * below; EXIT to cash when price crosses the UPPER band (SMA*(1+upper%)) from the top. In-position
 * leverage = 1x/2x/3x. Drag the band sliders / pick the SMA / leverage and the KPIs + price and
 * equity charts recompute live. Reuses the shared chart engine (window.SP) from strategy_page.js.
 */
(function () {
  "use strict";
  const DATA_URL = "band_lab_spx.json";
  const ACCENT = "#0071e3";
  const TD = 252;
  const COST = 0.001;          // 0.10% turnover cost on leverage changes
  const fmtLev = (x) => (x > 0 ? x.toFixed(0) + "x" : "0x");
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x * 100).toFixed(2) + "%");
  const f3 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(3));
  const f2 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(2));
  const money = (x) => (x == null || !isFinite(x) ? "—" : "$" + Math.round(x).toLocaleString());

  // ---------------- engine ----------------
  function sma(close, n) {
    const out = new Array(close.length).fill(null);
    let s = 0;
    for (let i = 0; i < close.length; i++) {
      s += close[i];
      if (i >= n) s -= close[i - n];
      if (i >= n - 1) out[i] = s / n;
    }
    return out;
  }

  // ENTER on upward cross of lower band; EXIT (to cash) on downward cross of upper band.
  function bandReversionLev(close, smaArr, upperPct, lowerPct, leverage) {
    const n = close.length, lev = new Array(n).fill(0);
    let state = 0;
    for (let i = 0; i < n; i++) {
      const s = smaArr[i], sp = smaArr[i - 1];
      if (s == null || sp == null) { lev[i] = state; continue; }
      const lowerNow = s * (1 - lowerPct), lowerPrev = sp * (1 - lowerPct);
      const upperNow = s * (1 + upperPct), upperPrev = sp * (1 + upperPct);
      if (close[i - 1] < lowerPrev && close[i] >= lowerNow) state = leverage;       // up through lower band
      else if (close[i - 1] > upperPrev && close[i] <= upperNow) state = 0;          // down through upper band
      lev[i] = state;
    }
    return lev;
  }

  // Equity from a daily leverage series: ret = lev*asset + (1-lev)*cash (1-day lag, turnover cost).
  function backtest(close, tbill, leverage, init) {
    const n = close.length, eq = new Array(n), ret = new Array(n);
    let prevLevLag = 0, e = init == null ? 100 : init;
    for (let i = 0; i < n; i++) {
      const aret = i === 0 ? 0 : close[i] / close[i - 1] - 1;
      const cash = (tbill[i] || 0) / TD;
      const levLag = i === 0 ? 0 : leverage[i - 1];           // act on yesterday's signal
      let r = levLag * aret + (1 - levLag) * cash;
      r -= Math.abs(levLag - prevLevLag) * COST;
      prevLevLag = levLag;
      e *= 1 + r;
      eq[i] = e; ret[i] = r;
    }
    return { equity: eq, ret };
  }

  function stats(equity, ret, tbill) {
    const n = equity.length;
    const years = n / TD;
    const end = equity[n - 1];
    const cagr = Math.pow(end / equity[0], 1 / years) - 1;
    let mean = 0; for (const r of ret) mean += r; mean /= n;
    let v = 0, dn = 0; for (const r of ret) { v += (r - mean) ** 2; if (r < 0) dn += r * r; }
    const vol = Math.sqrt(v / (n - 1)) * Math.sqrt(TD);
    const downside = Math.sqrt(dn / n) * Math.sqrt(TD);
    let rf = 0; for (const t of tbill) rf += t; rf /= n;
    const annRet = mean * TD;
    const sharpe = vol ? (annRet - rf) / vol : NaN;
    const sortino = downside ? (annRet - rf) / downside : NaN;
    let peak = -Infinity, mdd = 0;
    for (const e of equity) { if (e > peak) peak = e; const dd = e / peak - 1; if (dd < mdd) mdd = dd; }
    const calmar = mdd < 0 ? cagr / Math.abs(mdd) : NaN;
    return { cagr, vol, sharpe, sortino, calmar, maxdd: mdd, end };
  }

  function buildMarkers(lev, dates, close) {
    const out = [];
    for (let i = 1; i < lev.length; i++) {
      if (lev[i] === lev[i - 1]) continue;
      const up = lev[i] > lev[i - 1];
      out.push({
        date: dates[i], dir: up ? "up" : "down",
        color: up ? (lev[i] >= 2 ? "#2563eb" : "#15803d") : (lev[i] === 0 ? "#b42318" : "#b45309"),
        label: fmtLev(lev[i]),
        tip: `<b>${fmtLev(lev[i - 1])} → ${fmtLev(lev[i])}</b><br>${dates[i]}<br>${up ? "Entry" : "Exit"}`
          + (close[i] != null ? `<br>close ${close[i].toLocaleString()}` : ""),
      });
    }
    return out;
  }

  // ---------------- styles ----------------
  function injectLabStyles() {
    if (document.getElementById("band-lab-styles")) return;
    const s = document.createElement("style"); s.id = "band-lab-styles";
    s.textContent = `
      .lab-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px 26px;align-items:start;}
      .ctl label{display:block;font-size:13px;font-weight:600;color:#1d1d1f;margin-bottom:8px;}
      .ctl .seg{display:flex;gap:6px;flex-wrap:wrap;}
      .ctl .seg button{font:inherit;font-size:13px;font-weight:600;padding:7px 14px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .ctl .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .ctl input[type=range]{width:100%;accent-color:var(--accent);height:24px;cursor:grab;}
      .ctl input[type=number]{font:inherit;font-size:14px;padding:6px 10px;border-radius:10px;border:1px solid var(--line);width:90px;margin-top:8px;}
      .ctl .val{color:var(--accent);font-variant-numeric:tabular-nums;}
    `;
    document.head.appendChild(s);
  }

  // ---------------- UI ----------------
  function run(data) {
    const dates = data.dates, close = data.close, tbill = data.tbill, label = data.asset_label || "S&P 500";
    const app = document.getElementById("app");
    app.innerHTML = `
      <h1>${label} — Band Lab</h1>
      <p class="lede">Drag the band sliders, pick a moving average and leverage; the metrics and both charts
        recompute live. <b>Rule:</b> enter (go long) when price crosses up through the lower band, exit to cash
        when it crosses down through the upper band. Full S&P 500 history, 1-day signal lag, 0.10% turnover cost,
        synthetic daily-rebalanced leverage (cash/funding at T-bills).</p>
      <div class="card lab-controls">
        <div class="ctl"><label>Moving average (SMA days)</label>
          <div class="seg" id="smaSeg"></div>
          <input id="smaNum" type="number" min="2" max="400" step="1" value="100" />
        </div>
        <div class="ctl"><label>Upper band (exit): <span class="val" id="upVal"></span></label>
          <input id="upper" type="range" min="-15" max="15" step="0.5" value="2" /></div>
        <div class="ctl"><label>Lower band (entry): <span class="val" id="loVal"></span></label>
          <input id="lower" type="range" min="-15" max="15" step="0.5" value="2" /></div>
        <div class="ctl"><label>Leverage when invested</label>
          <div class="seg" id="levSeg"></div></div>
      </div>
      <div class="card"><div class="kpis" id="kpis"></div>
        <p class="meta" id="bhNote" style="margin-top:10px"></p></div>
      <div id="charts"></div>`;

    // controls state (default: a sensible non-levered combo with visible bands)
    let smaWin = 100, upperPct = 0.02, lowerPct = 0.02, lev = 1;

    const smaSeg = document.getElementById("smaSeg");
    [20, 50, 100, 200].forEach((w) => {
      const b = document.createElement("button"); b.textContent = w + "d"; b.dataset.w = w;
      b.onclick = () => { smaWin = w; document.getElementById("smaNum").value = w; syncSeg(smaSeg, w + "d", "textContent"); schedule(); };
      smaSeg.appendChild(b);
    });
    const levSeg = document.getElementById("levSeg");
    [1, 2, 3].forEach((L) => {
      const b = document.createElement("button"); b.textContent = L + "x"; b.dataset.l = L;
      b.onclick = () => { lev = L; syncSeg(levSeg, L + "x", "textContent"); schedule(); };
      levSeg.appendChild(b);
    });
    const upper = document.getElementById("upper"), lower = document.getElementById("lower"), smaNum = document.getElementById("smaNum");
    upper.value = upperPct * 100; lower.value = lowerPct * 100; smaNum.value = smaWin;
    upper.addEventListener("input", () => { upperPct = +upper.value / 100; schedule(); });
    lower.addEventListener("input", () => { lowerPct = +lower.value / 100; schedule(); });
    smaNum.addEventListener("input", () => { const w = Math.max(2, Math.min(400, +smaNum.value || 200)); smaWin = w; syncSeg(smaSeg, w + "d", "textContent"); schedule(); });

    function syncSeg(seg, active, prop) { seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b[prop] === active)); }
    syncSeg(smaSeg, smaWin + "d", "textContent"); syncSeg(levSeg, lev + "x", "textContent");

    // KPIs scaffold
    const KPI = [["CAGR", "cagr"], ["Max drawdown", "maxdd"], ["Calmar", "calmar"], ["Sortino", "sortino"],
                 ["Sharpe", "sharpe"], ["Volatility", "vol"], ["End $ ($100→)", "end"], ["% time invested", "pctIn"]];
    document.getElementById("kpis").innerHTML = KPI.map(([k]) =>
      `<div class="kpi"><div class="k">${k}</div><div class="v" data-kpi="${k}">—</div></div>`).join("");

    // buy & hold reference (always 1x) — computed once
    const bhEq = backtest(close, tbill, new Array(close.length).fill(1)).equity;
    const bhSt = stats(bhEq, backtest(close, tbill, new Array(close.length).fill(1)).ret, tbill);
    document.getElementById("bhNote").innerHTML =
      `Buy &amp; hold 1× reference: CAGR <b>${pct(bhSt.cagr)}</b> · Max DD <b>${pct(bhSt.maxdd)}</b> · Sharpe <b>${f3(bhSt.sharpe)}</b> · End <b>${money(bhSt.end)}</b>.`;

    // initial compute + charts
    const first = compute();
    const charts = document.getElementById("charts");
    const priceChart = SP.chartBlock("Price, SMA & bands — entry/exit markers", dates, first.priceSeries,
      { log: false, markerDefs: first.markers, customDates: true });
    const eqChart = SP.chartBlock("Equity P&L vs buy & hold (% return, rebased to 0%)", dates, first.eqSeries,
      { rebasePct: true, customDates: true, markerDefs: first.markers });
    charts.appendChild(priceChart); charts.appendChild(eqChart);
    setKPIs(first.st);

    function compute() {
      const smaArr = sma(close, smaWin);
      const leverage = bandReversionLev(close, smaArr, upperPct, lowerPct, lev);
      const bt = backtest(close, tbill, leverage);
      const st = stats(bt.equity, bt.ret, tbill);
      st.pctIn = leverage.reduce((a, v) => a + (v > 0 ? 1 : 0), 0) / leverage.length;
      const upperB = smaArr.map((s) => (s == null ? null : s * (1 + upperPct)));
      const lowerB = smaArr.map((s) => (s == null ? null : s * (1 - lowerPct)));
      const markers = buildMarkers(leverage, dates, close);
      return {
        st, markers,
        priceSeries: [
          { label: label + " close", color: "#1d1d1f", values: close },
          { label: "SMA" + smaWin, color: "#b26a00", values: smaArr },
          { label: "Upper band", color: "rgba(36,138,61,.55)", values: upperB },
          { label: "Lower band", color: "rgba(215,0,21,.55)", values: lowerB },
        ],
        eqSeries: [
          { label: `Band ${fmtLev(lev)}`, color: ACCENT, width: 2, values: bt.equity },
          { label: "Buy & hold 1×", color: "#6e6e73", values: bhEq },
        ],
      };
    }

    function setKPIs(st) {
      const v = { cagr: pct(st.cagr), maxdd: pct(st.maxdd), calmar: f2(st.calmar), sortino: f3(st.sortino),
                  sharpe: f3(st.sharpe), vol: pct(st.vol), end: money(st.end), "pctIn": (st.pctIn * 100).toFixed(1) + "%" };
      KPI.forEach(([k, key]) => { const el = document.querySelector(`[data-kpi="${k}"]`); if (el) el.textContent = v[key]; });
    }

    let t = null;
    function schedule() {
      document.getElementById("upVal").textContent = (+upper.value).toFixed(1) + "%";
      document.getElementById("loVal").textContent = (+lower.value).toFixed(1) + "%";
      if (t) clearTimeout(t);
      t = setTimeout(() => {
        t = null;
        const c = compute();
        setKPIs(c.st);
        priceChart.update(c.priceSeries, c.markers);
        eqChart.update(c.eqSeries, c.markers);
      }, 90);
    }
    document.getElementById("upVal").textContent = (upperPct * 100).toFixed(1) + "%";
    document.getElementById("loVal").textContent = (lowerPct * 100).toFixed(1) + "%";
  }

  function boot() {
    if (!window.SP || !SP.chartBlock) { setTimeout(boot, 30); return; }   // wait for the chart engine
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
