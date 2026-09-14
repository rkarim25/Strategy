/**
 * ust-page.js - Interactive US Treasury Curve & Macro Regime Visualizer
 * Strategy Dashboard (rkarim25.github.io/Strategy)
 * Includes Technical Analysis, Steepener/Flattener Recommendations, and Pivot Triggers.
 */

(function () {
  "use strict";

  let curveData = null;
  let activeCurveSeries = {
    current: true,
    "1m_ago": true,
    "6m_ago": false,
    "1y_ago": false,
    peak_inversion: true,
  };
  let activeHistoryMode = "yields"; // "yields" or "spreads"
  let activeHistoryRange = "1y"; // "1m", "3m", "6m", "1y"

  const CURVE_COLORS = {
    current: "#0071e3",
    "1m_ago": "#8e8e93",
    "6m_ago": "#af52de",
    "1y_ago": "#34c759",
    peak_inversion: "#ff3b30",
  };

  const TENOR_KEYS = ["2y", "5y", "10y", "30y"];
  const TENOR_LABELS = { "2y": "2-Year", "5y": "5-Year", "10y": "10-Year", "30y": "30-Year" };
  const TENOR_YEARS = { "2y": 2, "5y": 5, "10y": 10, "30y": 30 };

  const PRESET_SCENARIOS = {
    recession_cut: {
      name: "Emergency Easing (Hard Landing)",
      desc: "Fed aggressively cuts policy rate as growth plunges. Massive bull steepening.",
      shifts: { "2y": -1.25, "5y": -0.85, "10y": -0.45, "30y": -0.15 },
      regime: "Bull Steepening",
    },
    soft_landing: {
      name: "Disinflationary Soft Landing",
      desc: "Orderly Fed rate cuts as inflation hits 2%. Balanced curve rally with moderate bull flattening.",
      shifts: { "2y": -0.60, "5y": -0.55, "10y": -0.50, "30y": -0.40 },
      regime: "Bull Flattening",
    },
    stagflation: {
      name: "Stagflation / Energy Shock",
      desc: "Sticky commodity surge keeps inflation elevated; long yields spike on term premium.",
      shifts: { "2y": +0.35, "5y": +0.55, "10y": +0.75, "30y": +0.95 },
      regime: "Bear Steepening",
    },
    fiscal_supply: {
      name: "Fiscal Dominance & Supply Shock",
      desc: "$2T deficit auction supply overwhelms long-end demand. Bond vigilantes demand higher term premium.",
      shifts: { "2y": +0.10, "5y": +0.35, "10y": +0.65, "30y": +0.95 },
      regime: "Bear Steepening (Current Risk)",
    },
    hawkish_hike: {
      name: "Hawkish Tightening (Inflation Surprise)",
      desc: "Fed resumes rate hikes to squash persistent wage-price inflation. Sharp bear flattening.",
      shifts: { "2y": +0.80, "5y": +0.45, "10y": +0.20, "30y": +0.05 },
      regime: "Bear Flattening",
    },
  };

  async function loadData() {
    try {
      const resp = await fetch("ust_curve_data.json?v=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      curveData = await resp.json();
      initUI();
    } catch (e) {
      console.warn("Could not fetch ust_curve_data.json, using fallback", e);
      const fallbackEl = document.getElementById("ustFallbackData");
      if (fallbackEl) {
        try {
          curveData = JSON.parse(fallbackEl.textContent);
          initUI();
        } catch (parseErr) {
          console.error("Fallback parse failed", parseErr);
        }
      }
    }
  }

  function initUI() {
    if (!curveData) return;
    renderTopStats();
    renderSpreads();
    renderYieldCurveChart();
    renderHistoryChart();
    renderExecutiveRecommendation();
    renderTechnicalsAndTriggers();
    renderMacroRadar();
    renderRegimeModelTable();
    setupEventListeners();
    setupSteepenerCalculator();
    runScenarioSimulation("fiscal_supply");
  }

  function renderTopStats() {
    const y = curveData.yields || {};
    TENOR_KEYS.forEach((k) => {
      const item = y[k];
      if (!item) return;
      const elVal = document.getElementById(`val_${k}`);
      const elChg = document.getElementById(`chg_${k}`);
      const elDur = document.getElementById(`dur_${k}`);
      if (elVal) elVal.textContent = item.yield.toFixed(2) + "%";
      if (elChg) {
        const chg = item.change_bps;
        const sign = chg > 0 ? "+" : "";
        elChg.textContent = `${sign}${chg.toFixed(1)} bps`;
        elChg.className = "stat-change " + (chg > 0 ? "bad" : chg < 0 ? "good" : "muted");
      }
      if (elDur) {
        elDur.textContent = `Mod Dur: ${item.duration.toFixed(1)}y · DV01: $${item.dv01.toFixed(1)}`;
      }
    });

    const asOfEl = document.getElementById("curveAsOfDate");
    if (asOfEl && curveData.latest_date) {
      asOfEl.textContent = `As of ${curveData.latest_date} · Live Generic Treasury Par Rates`;
    }
  }

  function renderSpreads() {
    const s = curveData.spreads || {};
    const keys = ["2s10s", "5s30s", "2s30s", "10s30s"];
    keys.forEach((k) => {
      const item = s[k];
      if (!item) return;
      const elVal = document.getElementById(`spread_${k}_val`);
      const elChg = document.getElementById(`spread_${k}_chg`);
      const elStatus = document.getElementById(`spread_${k}_status`);
      if (elVal) {
        const sign = item.bps > 0 ? "+" : "";
        elVal.textContent = `${sign}${item.bps.toFixed(1)} bps`;
      }
      if (elChg) {
        const sign = item.change_bps > 0 ? "+" : "";
        elChg.textContent = `1D: ${sign}${item.change_bps.toFixed(1)} bps`;
      }
      if (elStatus) elStatus.textContent = item.status;
    });
  }

  function renderExecutiveRecommendation() {
    const macro = curveData.macro_assessment;
    if (!macro) return;

    const execP = document.getElementById("executiveParagraph");
    if (execP && macro.executive_paragraph) {
      execP.textContent = macro.executive_paragraph;
    }

    const tradeRec = document.getElementById("curveTradeBadge");
    if (tradeRec && macro.curve_trade_recommendation) {
      tradeRec.textContent = macro.curve_trade_recommendation.primary_trade;
    }

    const sizingEl = document.getElementById("curveTradeSizing");
    if (sizingEl && macro.curve_trade_recommendation) {
      sizingEl.textContent = `Execution Rule: ${macro.curve_trade_recommendation.sizing_rule}`;
    }
  }

  function renderTechnicalsAndTriggers() {
    const macro = curveData.macro_assessment;
    if (!macro || !macro.technicals) return;
    const tech = macro.technicals;

    // Technical gauges
    const t10 = tech["10y"] || {};
    const t2s10s = tech["2s10s"] || {};

    const el10ySma = document.getElementById("tech10ySma");
    if (el10ySma) {
      el10ySma.innerHTML = `<strong>10Y: ${t10.current}%</strong> · 50d SMA: ${t10.sma50}% · 200d SMA: ${t10.sma200}% · RSI(14): <strong>${t10.rsi14}</strong> (${t10.rsi_status})`;
    }

    const el2s10sSma = document.getElementById("tech2s10sSma");
    if (el2s10sSma) {
      el2s10sSma.innerHTML = `<strong>2s10s: +${t2s10s.current} bps</strong> · 50d SMA: +${t2s10s.sma50} bps · 200d SMA: +${t2s10s.sma200} bps · RSI(14): <strong>${t2s10s.rsi14}</strong> (${t2s10s.trend})`;
    }

    // Triggers List
    const triggersList = document.getElementById("triggersContainer");
    if (triggersList && tech.triggers) {
      triggersList.replaceChildren();
      tech.triggers.forEach((trg) => {
        const item = document.createElement("div");
        item.className = "trigger-card " + (trg.threshold_met ? "active-alert" : "");
        item.innerHTML = `
          <div class="trigger-header">
            <h4 class="trigger-title">${trg.title}</h4>
            <span class="trigger-status-badge ${trg.threshold_met ? 'badge-alert' : 'badge-inactive'}">${trg.status}</span>
          </div>
          <p class="trigger-condition"><strong>Condition:</strong> ${trg.condition}</p>
          <div class="trigger-action-pill"><strong>Action:</strong> ${trg.action}</div>
          <div class="trigger-metric-dist">${trg.active_metric}</div>
        `;
        triggersList.appendChild(item);
      });
    }
  }

  function setupSteepenerCalculator() {
    const notionalInput = document.getElementById("steepenerNotional");
    const basisShiftInput = document.getElementById("steepenerBpsShift");
    const out2y = document.getElementById("calcSize2y");
    const out10y = document.getElementById("calcSize10y");
    const outPnl = document.getElementById("calcPnl");

    function recalc() {
      if (!notionalInput || !basisShiftInput || !out2y || !out10y || !outPnl) return;
      const notional = parseFloat(notionalInput.value) || 1000000;
      const bps = parseFloat(basisShiftInput.value) || 10;

      // 10Y DV01 approx $82.0 per $100k = $0.00082 per $1
      // 2Y DV01 approx $19.2 per $100k = $0.000192 per $1
      // For DV01 neutrality: Size_2Y * DV01_2Y = Size_10Y * DV01_10Y
      // Ratio: 82.0 / 19.2 = ~4.27
      const ratio = 82.0 / 19.2;
      const size10y = notional;
      const size2y = notional * ratio;

      // P&L per basis point of steepening (2s10s widens by 1 bp):
      // DV01 = notional * 0.00082
      const dv01Total = (size10y / 100000) * 82.0;
      const pnl = dv01Total * bps;

      out10y.textContent = `$${(size10y / 1e6).toFixed(2)}M Short`;
      out2y.textContent = `$${(size2y / 1e6).toFixed(2)}M Long (Ratio ${ratio.toFixed(2)}x)`;
      const sign = pnl >= 0 ? "+" : "";
      outPnl.textContent = `${sign}$${Math.round(pnl).toLocaleString()}`;
      outPnl.className = "calc-pnl-val " + (pnl >= 0 ? "good" : "bad");
    }

    if (notionalInput && basisShiftInput) {
      notionalInput.addEventListener("input", recalc);
      basisShiftInput.addEventListener("input", recalc);
      recalc();
    }
  }

  function renderMacroRadar() {
    const macro = curveData.macro_assessment;
    if (!macro) return;

    const regimeTitle = document.getElementById("macroRegimeTitle");
    const regimeBadge = document.getElementById("macroRegimeBadge");
    const regimeSummary = document.getElementById("macroRegimeSummary");
    const curveAction = document.getElementById("curveActionBanner");

    if (regimeTitle) regimeTitle.textContent = macro.regime_name;
    if (regimeBadge) {
      regimeBadge.textContent = "CURRENT REGIME";
      regimeBadge.className = "regime-badge bear-steep";
    }
    if (regimeSummary) regimeSummary.textContent = macro.regime_summary;
    if (curveAction) curveAction.textContent = macro.curve_trade_recommendation ? macro.curve_trade_recommendation.curve_action : macro.curve_action;

    // Render Indicator Table
    const tbody = document.getElementById("macroIndicatorsBody");
    if (tbody && macro.indicators) {
      tbody.replaceChildren();
      macro.indicators.forEach((ind) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${ind.name}</strong></td>
          <td class="stat-highlight">${ind.value}</td>
          <td><span class="trend-pill ${ind.trend.toLowerCase().replace(/\s+/g, '-')}">${ind.trend}</span></td>
          <td class="small-muted">${ind.target}</td>
          <td>${ind.impact}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Render Headlines
    const headlineList = document.getElementById("macroHeadlinesList");
    if (headlineList && macro.headlines) {
      headlineList.replaceChildren();
      macro.headlines.forEach((h) => {
        const card = document.createElement("div");
        card.className = "headline-item";
        card.innerHTML = `
          <div class="headline-header">
            <span class="headline-cat">${h.category}</span>
            <span class="headline-source">${h.source}</span>
          </div>
          <h4 class="headline-title">${h.headline}</h4>
          <p class="headline-summary">${h.summary}</p>
          <div class="headline-tag ${h.sentiment.toLowerCase().replace(/\s+/g, '-')}">${h.sentiment}</div>
        `;
        headlineList.appendChild(card);
      });
    }

    // Render Model Stances
    const stanceContainer = document.getElementById("modelStanceContainer");
    if (stanceContainer && macro.model_signals) {
      stanceContainer.replaceChildren();
      TENOR_KEYS.forEach((k) => {
        const sig = macro.model_signals[k];
        const meta = curveData.yields[k] || {};
        if (!sig) return;
        const box = document.createElement("div");
        box.className = `model-point-card ${sig.rating.toLowerCase().replace(/\s+/g, '-')}`;
        box.innerHTML = `
          <div class="point-header">
            <span class="point-tenor">${TENOR_LABELS[k]} (${k.toUpperCase()})</span>
            <span class="point-rating-badge">${sig.rating}</span>
          </div>
          <div class="point-yield">${meta.yield ? meta.yield.toFixed(2) + "%" : ""}</div>
          <div class="point-stance">${sig.stance}</div>
          <div class="point-score-bar">
            <div class="score-fill" style="width: ${sig.score * 10}%;"></div>
          </div>
          <p class="point-rationale">${sig.rationale}</p>
        `;
        stanceContainer.appendChild(box);
      });
    }
  }

  function renderRegimeModelTable() {
    const fw = curveData.curve_model_framework;
    if (!fw) return;

    const tbody = document.getElementById("regimeFrameworkBody");
    if (tbody && fw.regimes) {
      tbody.replaceChildren();
      fw.regimes.forEach((r) => {
        const isCurrent = r.id === (curveData.macro_assessment ? curveData.macro_assessment.regime_id : "");
        const tr = document.createElement("tr");
        if (isCurrent) tr.className = "current-regime-row";
        tr.innerHTML = `
          <td>
            <strong>${r.name}</strong>
            ${isCurrent ? '<span class="current-tag">ACTIVE</span>' : ''}
          </td>
          <td>${r.macro_driver}</td>
          <td>${r.curve_motion}</td>
          <td><span class="best-pill">${r.best_points.join(", ")}</span></td>
          <td><span class="worst-pill">${r.worst_point}</span></td>
          <td class="small">${r.rationale}</td>
        `;
        tbody.appendChild(tr);
      });
    }
  }

  /* -------------------------------------------------------------
     INTERACTIVE CANVAS YIELD CURVE CHART
     ------------------------------------------------------------- */
  function renderYieldCurveChart() {
    const canvas = document.getElementById("yieldCurveCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 360 * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 360;
    const pad = { top: 35, right: 40, bottom: 45, left: 55 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    let minY = 3.5;
    let maxY = 5.8;
    const snaps = curveData.snapshots || {};

    Object.keys(activeCurveSeries).forEach((k) => {
      if (!activeCurveSeries[k] || !snaps[k]) return;
      TENOR_KEYS.forEach((t) => {
        const v = snaps[k][t];
        if (v != null) {
          minY = Math.min(minY, v);
          maxY = Math.max(maxY, v);
        }
      });
    });

    minY = Math.floor(minY * 2) / 2 - 0.2;
    maxY = Math.ceil(maxY * 2) / 2 + 0.2;

    const tenorXMap = {
      "2y": pad.left + chartW * 0.10,
      "5y": pad.left + chartW * 0.38,
      "10y": pad.left + chartW * 0.68,
      "30y": pad.left + chartW * 0.95,
    };

    function yToPx(val) {
      return pad.top + chartH * (1 - (val - minY) / (maxY - minY));
    }

    ctx.strokeStyle = "rgba(0, 0, 0, 0.07)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#86868b";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    const step = 0.5;
    for (let yVal = Math.ceil(minY * 2) / 2; yVal <= maxY; yVal += step) {
      const py = yToPx(yVal);
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(W - pad.right, py);
      ctx.stroke();
      ctx.fillText(yVal.toFixed(2) + "%", pad.left - 10, py);
    }

    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    TENOR_KEYS.forEach((k) => {
      const px = tenorXMap[k];
      ctx.strokeStyle = "rgba(0, 0, 0, 0.05)";
      ctx.beginPath();
      ctx.moveTo(px, pad.top);
      ctx.lineTo(px, H - pad.bottom);
      ctx.stroke();
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.fillText(TENOR_LABELS[k], px, H - pad.bottom + 10);
    });

    const drawOrder = ["1y_ago", "6m_ago", "1m_ago", "peak_inversion", "current"];
    drawOrder.forEach((k) => {
      if (!activeCurveSeries[k] || !snaps[k]) return;
      const snap = snaps[k];
      const isCurrent = k === "current";
      const color = CURVE_COLORS[k] || "#0071e3";

      ctx.beginPath();
      TENOR_KEYS.forEach((t, i) => {
        const px = tenorXMap[t];
        const py = yToPx(snap[t]);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });

      ctx.strokeStyle = color;
      ctx.lineWidth = isCurrent ? 3.5 : 2;
      if (k === "peak_inversion") {
        ctx.setLineDash([5, 4]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      TENOR_KEYS.forEach((t) => {
        const px = tenorXMap[t];
        const py = yToPx(snap[t]);
        ctx.beginPath();
        ctx.arc(px, py, isCurrent ? 5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        if (isCurrent) {
          ctx.fillStyle = "#1d1d1f";
          ctx.font = "bold 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(snap[t].toFixed(2) + "%", px, py - 8);
        }
      });
    });
  }

  /* -------------------------------------------------------------
     INTERACTIVE HISTORICAL SERIES CHART
     ------------------------------------------------------------- */
  function renderHistoryChart() {
    const canvas = document.getElementById("historyChartCanvas");
    if (!canvas || !curveData || !curveData.history) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 320 * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 320;
    const pad = { top: 30, right: 40, bottom: 40, left: 55 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const allRows = curveData.history;
    const countMap = { "1m": 22, "3m": 66, "6m": 126, "1y": 252 };
    const maxPts = countMap[activeHistoryRange] || allRows.length;
    const rows = allRows.slice(-maxPts);
    if (!rows.length) return;

    let minY = Infinity;
    let maxY = -Infinity;

    if (activeHistoryMode === "yields") {
      rows.forEach((r) => {
        TENOR_KEYS.forEach((k) => {
          if (r[k] != null) {
            minY = Math.min(minY, r[k]);
            maxY = Math.max(maxY, r[k]);
          }
        });
      });
      minY = Math.floor(minY * 2) / 2 - 0.2;
      maxY = Math.ceil(maxY * 2) / 2 + 0.2;
    } else {
      rows.forEach((r) => {
        minY = Math.min(minY, r.spread_2s10s, r.spread_2s30s);
        maxY = Math.max(maxY, r.spread_2s10s, r.spread_2s30s);
      });
      minY = Math.floor(minY / 20) * 20 - 10;
      maxY = Math.ceil(maxY / 20) * 20 + 10;
    }

    function yToPx(val) {
      return pad.top + chartH * (1 - (val - minY) / (maxY - minY));
    }
    function xToPx(idx) {
      return pad.left + (chartW * idx) / (rows.length - 1);
    }

    ctx.strokeStyle = "rgba(0, 0, 0, 0.07)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#86868b";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    const steps = 5;
    for (let i = 0; i <= steps; i++) {
      const v = minY + ((maxY - minY) * i) / steps;
      const py = yToPx(v);
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(W - pad.right, py);
      ctx.stroke();
      const label = activeHistoryMode === "yields" ? v.toFixed(2) + "%" : v.toFixed(0) + " bps";
      ctx.fillText(label, pad.left - 8, py);
    }

    if (activeHistoryMode === "spreads" && minY <= 0 && maxY >= 0) {
      const zPy = yToPx(0);
      ctx.strokeStyle = "rgba(215, 0, 21, 0.35)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, zPy);
      ctx.lineTo(W - pad.right, zPy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#d70015";
      ctx.fillText("0 (Inversion Threshold)", W - pad.right - 10, zPy - 8);
    }

    if (activeHistoryMode === "yields") {
      const seriesColors = {
        "2y": "#ff9500",
        "5y": "#af52de",
        "10y": "#0071e3",
        "30y": "#34c759",
      };
      TENOR_KEYS.forEach((k) => {
        ctx.beginPath();
        rows.forEach((r, i) => {
          const px = xToPx(i);
          const py = yToPx(r[k]);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = seriesColors[k];
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    } else {
      ctx.beginPath();
      rows.forEach((r, i) => {
        const px = xToPx(i);
        const py = yToPx(r.spread_2s10s);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = "#0071e3";
      ctx.lineWidth = 2.5;
      ctx.stroke();

      ctx.beginPath();
      rows.forEach((r, i) => {
        const px = xToPx(i);
        const py = yToPx(r.spread_2s30s);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = "#34c759";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    ctx.fillStyle = "#86868b";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const xLabelsCount = Math.min(5, rows.length);
    for (let i = 0; i < xLabelsCount; i++) {
      const rIdx = Math.round((i * (rows.length - 1)) / (xLabelsCount - 1));
      const px = xToPx(rIdx);
      const dt = rows[rIdx].date;
      ctx.fillText(dt, px, H - pad.bottom + 10);
    }
  }

  /* -------------------------------------------------------------
     SCENARIO SIMULATOR
     ------------------------------------------------------------- */
  function runScenarioSimulation(scenarioKey) {
    const sc = PRESET_SCENARIOS[scenarioKey];
    if (!sc || !curveData || !curveData.yields) return;

    document.querySelectorAll(".scenario-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.scenario === scenarioKey);
    });

    const descEl = document.getElementById("scenarioDesc");
    if (descEl) {
      descEl.innerHTML = `<strong>${sc.name}:</strong> ${sc.desc} <span class="scenario-regime-tag">${sc.regime}</span>`;
    }

    const results = [];
    TENOR_KEYS.forEach((k) => {
      const meta = curveData.yields[k];
      const shiftPct = sc.shifts[k];
      const newYield = meta.yield + shiftPct;

      const priceChgPct = -(meta.duration * shiftPct) + 0.5 * meta.convexity * Math.pow(shiftPct, 2);
      const total1YReturn = priceChgPct + meta.yield;

      results.push({
        tenor: k,
        label: TENOR_LABELS[k],
        initialYield: meta.yield,
        shiftPct: shiftPct,
        newYield: newYield,
        duration: meta.duration,
        priceChgPct: priceChgPct,
        total1YReturn: total1YReturn,
      });
    });

    results.sort((a, b) => b.priceChgPct - a.priceChgPct);

    const tbody = document.getElementById("scenarioResultsBody");
    if (tbody) {
      tbody.replaceChildren();
      results.forEach((res, rank) => {
        const tr = document.createElement("tr");
        const priceCls = res.priceChgPct > 0 ? "good" : res.priceChgPct < 0 ? "bad" : "";
        const totCls = res.total1YReturn > 0 ? "good" : "bad";
        const signShift = res.shiftPct > 0 ? "+" : "";
        const signPrice = res.priceChgPct > 0 ? "+" : "";
        const signTot = res.total1YReturn > 0 ? "+" : "";

        tr.innerHTML = `
          <td><strong>#${rank + 1} ${res.label}</strong></td>
          <td>${res.initialYield.toFixed(2)}%</td>
          <td><span class="${res.shiftPct < 0 ? "good" : "bad"}">${signShift}${res.shiftPct.toFixed(2)}% (${signShift}${(res.shiftPct * 100).toFixed(0)} bps)</span></td>
          <td><strong>${res.newYield.toFixed(2)}%</strong></td>
          <td class="stat-highlight ${priceCls}"><strong>${signPrice}${res.priceChgPct.toFixed(2)}%</strong></td>
          <td class="${totCls}">${signTot}${res.total1YReturn.toFixed(2)}%</td>
          <td>
            <div class="sim-bar-wrap">
              <div class="sim-bar-fill ${res.priceChgPct >= 0 ? 'good-bar' : 'bad-bar'}" style="width: ${Math.min(100, Math.abs(res.priceChgPct) * 6)}%;"></div>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }
  }

  function setupEventListeners() {
    document.querySelectorAll(".curve-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.curveKey;
        activeCurveSeries[key] = !activeCurveSeries[key];
        btn.classList.toggle("active", activeCurveSeries[key]);
        renderYieldCurveChart();
      });
    });

    document.querySelectorAll(".history-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".history-mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeHistoryMode = btn.dataset.mode;
        renderHistoryChart();
      });
    });

    document.querySelectorAll(".history-range-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".history-range-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeHistoryRange = btn.dataset.range;
        renderHistoryChart();
      });
    });

    document.querySelectorAll(".scenario-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        runScenarioSimulation(btn.dataset.scenario);
      });
    });

    window.addEventListener("resize", () => {
      renderYieldCurveChart();
      renderHistoryChart();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadData);
  } else {
    loadData();
  }
})();
