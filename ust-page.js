
  /* -------------------------------------------------------------
     DUAL-BAND STRATEGY & DURATION SIZING MATRIX RENDERER
     ------------------------------------------------------------- */
  function renderDualBandMatrix() {
    const tbody = document.getElementById("dualBandTableBody");
    if (!tbody || !curveData || !curveData.dual_band_framework) return;

    const dbf = curveData.dual_band_framework;
    const tenors = dbf.tenors || {};
    const spreads = dbf.spreads || {};
    tbody.replaceChildren();

    // 1. Tenors (2Y, 5Y, 10Y, 30Y)
    const tenorList = ["2y", "5y", "10y", "30y"];
    tenorList.forEach((k) => {
      const t = tenors[k];
      if (!t) return;
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      const isConfluence = t.signal === "SHORT_DUAL_CONFLUENCE" || t.signal === "LONG_DUAL_CONFLUENCE";
      const sigColor = t.recommended_duration < 0 ? "var(--bad)" : t.recommended_duration > 0 ? "var(--good)" : "var(--muted)";
      const durText = t.recommended_duration !== 0 ? `${t.recommended_duration > 0 ? "+" : ""}${t.recommended_duration.toFixed(2)}y Duration` : "0.00y (Neutral)";

      tr.innerHTML = `
        <td style="padding: 10px 12px; font-weight: 700;">
          <div style="font-size: 13.5px; color: var(--text);">${t.name}</div>
          <div style="font-size: 11px; color: var(--muted);">${t.contract}</div>
        </td>
        <td style="padding: 10px 12px; font-weight: 800; font-size: 14px; color: var(--accent);">${t.current.toFixed(3)}%</td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 600; color: var(--text);">${t.fund_band.lower.toFixed(2)}% – ${t.fund_band.upper.toFixed(2)}%</div>
          <div style="font-size: 11px; color: var(--muted);">Mid: ${t.fund_band.mid.toFixed(2)}% · ${t.fund_driver}</div>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 600; color: var(--orange);">${t.tech_band.lower.toFixed(2)}% – ${t.tech_band.upper.toFixed(2)}%</div>
          <div style="font-size: 11px; color: var(--muted);">SMA: ${t.tech_band.mid.toFixed(2)}%</div>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 700; color: ${t.rsi14 > 68 ? 'var(--bad)' : t.rsi14 < 32 ? 'var(--good)' : 'var(--text)'};">${t.rsi14.toFixed(1)}</div>
          <div style="font-size: 11px; color: var(--muted);">${t.rsi_state}</div>
        </td>
        <td style="padding: 10px 12px;">
          <span style="font-size: 11.5px; font-weight: 600; padding: 3px 8px; border-radius: 6px; background: ${isConfluence ? 'rgba(215, 0, 21, 0.12)' : 'rgba(0, 0, 0, 0.05)'}; color: ${isConfluence ? 'var(--bad)' : 'var(--muted)'};">
            ${t.sizing_type}
          </span>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 700; color: ${sigColor};">${t.signal_badge}</div>
          <div style="font-size: 11.5px; font-weight: 700; color: ${sigColor};">${durText}</div>
        </td>
        <td style="padding: 10px 12px; font-weight: 600; color: var(--muted);">
          ${k === '30y' ? '5.180%' : k === '2y' ? '4.250%' : k === '5y' ? '4.880%' : 'N/A'}
        </td>
      `;
      tbody.appendChild(tr);
    });

    // 2. Spreads (2s10s, 10s30s, 2s30s)
    const spreadList = ["2s10s", "10s30s", "2s30s"];
    spreadList.forEach((sk) => {
      const sp = spreads[sk];
      if (!sp) return;
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";
      tr.style.background = "rgba(0, 113, 227, 0.02)";

      const isSteepener = sp.signal.includes("STEEPENER");
      const sigColor = isSteepener ? "var(--bad)" : "var(--muted)";

      tr.innerHTML = `
        <td style="padding: 10px 12px; font-weight: 700;">
          <div style="font-size: 13.5px; color: var(--text);">${sp.name}</div>
          <div style="font-size: 11px; color: var(--muted);">${sk} Curve Slope</div>
        </td>
        <td style="padding: 10px 12px; font-weight: 800; font-size: 14px; color: var(--accent);">+${sp.current_bps.toFixed(1)} bps</td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 600; color: var(--text);">+${sp.fund_band.lower_bps.toFixed(0)} to +${sp.fund_band.upper_bps.toFixed(0)} bps</div>
          <div style="font-size: 11px; color: var(--muted);">Mid: +${sp.fund_band.mid_bps.toFixed(0)} bps · ${sp.fund_driver}</div>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 600; color: var(--orange);">+${sp.tech_band.lower_bps.toFixed(0)} to +${sp.tech_band.upper_bps.toFixed(0)} bps</div>
          <div style="font-size: 11px; color: var(--muted);">Technical Channel</div>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 700;">${sp.rsi14.toFixed(1)}</div>
          <div style="font-size: 11px; color: var(--muted);">Curve Momentum</div>
        </td>
        <td style="padding: 10px 12px;">
          <span style="font-size: 11.5px; font-weight: 600; padding: 3px 8px; border-radius: 6px; background: rgba(0, 0, 0, 0.05); color: var(--muted);">
            ${isSteepener ? 'Structural Curve Play' : 'Balanced Fair Value'}
          </span>
        </td>
        <td style="padding: 10px 12px;">
          <div style="font-weight: 700; color: ${sigColor};">${sp.signal_badge}</div>
          <div style="font-size: 11.5px; color: var(--muted);">Tgt: +${sp.target_bps.toFixed(0)} bps</div>
        </td>
        <td style="padding: 10px 12px; font-weight: 700; color: var(--bad);">
          +${sp.stop_loss_bps.toFixed(0)} bps
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

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
  let activeSpreadKey = "2s10s"; // "2s10s", "2s30s", "5s10s", "all"
  let activeSpreadRange = "1y"; // "1m", "3m", "6m", "1y"
  let activeTrackerFilter = "all"; // "all", "US Treasuries", "Local EM", "Credit Derivatives"

  // Interactive curve tenor & spread toggles
  let activeHistoryTenors = {
    "30y": true,
    "10y": true,
    "5y": true,
    "2y": true,
  };
  let activeHistorySpreads = {
    spread_2s10s: true,
    spread_2s30s: true,
    spread_5s10s: true,
  };

  // Hover indices
  let hoverHistoryIdx = null;
  let hoverSpreadIdx = null;
  let hoverYieldTenor = null;

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
    renderDualBandMatrix();
    renderMacroRadar();
    renderRegimeModelTable();
    renderSpreadChart();
    renderTradeTracker();
    setupEventListeners();
    setupSteepenerCalculator();
    setupChartHoverEngines();
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
        elDur.textContent = `Mod Dur: ${item.duration.toFixed(1)}y • DV01: $${item.dv01.toFixed(1)}`;
      }
    });

    const elAsOf = document.getElementById("dataAsOfTime");
    if (elAsOf && curveData.as_of) {
      elAsOf.textContent = "Data as of: " + curveData.as_of;
    }
  }

  function renderSpreads() {
    const sp = curveData.spreads || {};
    const map = {
      "2s10s": { val: "spread_2s10s_val", chg: "spread_2s10s_chg", st: "spread_2s10s_st" },
      "2s30s": { val: "spread_2s30s_val", chg: "spread_2s30s_chg", st: "spread_2s30s_st" },
      "5s30s": { val: "spread_5s30s_val", chg: "spread_5s30s_chg", st: "spread_5s30s_st" },
      "10s30s": { val: "spread_10s30s_val", chg: "spread_10s30s_chg", st: "spread_10s30s_st" },
    };

    Object.keys(map).forEach((k) => {
      const item = sp[k];
      if (!item) return;
      const ids = map[k];
      const elV = document.getElementById(ids.val);
      const elC = document.getElementById(ids.chg);
      const elS = document.getElementById(ids.st);

      if (elV) {
        const sign = item.bps > 0 ? "+" : "";
        elV.textContent = `${sign}${item.bps.toFixed(1)} bps`;
        elV.className = "spread-val " + (item.bps > 0 ? "good" : item.bps < 0 ? "bad" : "muted");
      }
      if (elC) {
        const sign = item.change_bps > 0 ? "+" : "";
        elC.textContent = `${sign}${item.change_bps.toFixed(1)} bps 1D`;
      }
      if (elS) {
        elS.textContent = item.status || (item.bps >= 0 ? "Normal" : "Inverted");
      }
    });
  }

  /* -------------------------------------------------------------
     EXECUTIVE RECOMMENDATION & RATIONALE
     ------------------------------------------------------------- */
  function renderExecutiveRecommendation() {
    const rec = curveData.executive_recommendation;
    if (!rec) return;

    const banner = document.getElementById("recommendationBanner");
    const titleEl = document.getElementById("recTitle");
    const badgeEl = document.getElementById("recBadge");
    const pointEl = document.getElementById("recPoint");
    const typeEl = document.getElementById("recType");
    const horizonEl = document.getElementById("recHorizon");
    const summaryEl = document.getElementById("recSummary");
    const bulletsEl = document.getElementById("recBullets");
    const vehicleEl = document.getElementById("recVehicle");

    if (titleEl) titleEl.textContent = rec.headline || "Yield Curve Stance";
    if (badgeEl) {
      badgeEl.textContent = (rec.curve_structure || "STANCE").toUpperCase();
      badgeEl.className = "rec-badge " + (rec.direction === "STEEPENER" ? "steepener" : "flattener");
    }
    if (pointEl) pointEl.textContent = rec.curve_point || "2s10s";
    if (typeEl) typeEl.textContent = rec.curve_structure || "Bear Steepener";
    if (horizonEl) horizonEl.textContent = rec.target_horizon || "3 - 6 Months";
    if (summaryEl) summaryEl.textContent = rec.concise_summary || "";

    if (bulletsEl && Array.isArray(rec.key_drivers)) {
      bulletsEl.replaceChildren();
      rec.key_drivers.forEach((d) => {
        const li = document.createElement("li");
        li.textContent = d;
        bulletsEl.appendChild(li);
      });
    }

    if (vehicleEl) {
      vehicleEl.innerHTML = `<strong>Expression Vehicle:</strong> ${rec.recommended_vehicle || "Treasury Futures / Swaps"}`;
    }
  }

  /* -------------------------------------------------------------
     TECHNICAL INDICATORS & PIVOT TRIGGERS
     ------------------------------------------------------------- */
  function renderTechnicalsAndTriggers() {
    const tech = curveData.technicals;
    const trig = curveData.change_triggers;

    // Technical Metrics Grid
    const techGrid = document.getElementById("technicalsGrid");
    if (techGrid && tech) {
      techGrid.replaceChildren();
      const items = [
        { label: "2s10s Spread Level", val: `+${tech["2s10s_spread"] ? tech["2s10s_spread"].toFixed(1) : 0} bps`, sub: "Current Benchmark Slope" },
        { label: "50-Day Moving Avg", val: `+${tech["2s10s_sma50"] ? tech["2s10s_sma50"].toFixed(1) : 0} bps`, sub: tech["2s10s_spread"] > tech["2s10s_sma50"] ? "Above SMA50 (Bullish Slope)" : "Below SMA50" },
        { label: "200-Day Moving Avg", val: `${tech["2s10s_sma200"] >= 0 ? "+" : ""}${tech["2s10s_sma200"] ? tech["2s10s_sma200"].toFixed(1) : 0} bps`, sub: "Structural Trend Baseline" },
        { label: "14-Day RSI (Spread)", val: tech.rsi14 ? tech.rsi14.toFixed(1) : "50.0", sub: tech.rsi14 > 70 ? "Overbought Slope" : tech.rsi14 < 30 ? "Oversold Slope" : "Neutral Momentum" },
        { label: "10Y Term Premium", val: `+${tech.term_premium_10y ? tech.term_premium_10y.toFixed(2) : 0}%`, sub: "ACM Model Estimate" },
        { label: "Market Momentum", val: tech.momentum_regime || "Steepening Trend", sub: "Trend Classification" },
      ];

      items.forEach((it) => {
        const div = document.createElement("div");
        div.className = "tech-stat-card";
        div.innerHTML = `
          <span class="tech-label">${it.label}</span>
          <span class="tech-val">${it.val}</span>
          <span class="tech-sub">${it.sub}</span>
        `;
        techGrid.appendChild(div);
      });
    }

    // Pivot Triggers Lists
    const flattenerList = document.getElementById("flattenerTriggersList");
    if (flattenerList && trig && trig.pivot_to_flattener) {
      flattenerList.replaceChildren();
      trig.pivot_to_flattener.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        flattenerList.appendChild(li);
      });
    }

    const bullSteepList = document.getElementById("bullSteepTriggersList");
    if (bullSteepList && trig && trig.pivot_to_bull_steepener) {
      bullSteepList.replaceChildren();
      trig.pivot_to_bull_steepener.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        bullSteepList.appendChild(li);
      });
    }
  }

  /* -------------------------------------------------------------
     INTERACTIVE STEEPENER / FLATTENER TRADE CALCULATOR
     ------------------------------------------------------------- */
  function setupSteepenerCalculator() {
    const selectSpread = document.getElementById("calcSpreadSelect");
    const selectTrade = document.getElementById("calcTradeType");
    const inputNotional = document.getElementById("calcNotional");
    const inputExpectedShift = document.getElementById("calcExpectedShift");
    const btnCalc = document.getElementById("calcRunBtn");

    if (!btnCalc || !curveData) return;

    function runCalc() {
      const spreadKey = selectSpread ? selectSpread.value : "2s10s";
      const tradeType = selectTrade ? selectTrade.value : "steepener";
      const notional = parseFloat(inputNotional ? inputNotional.value : 1000000) || 1000000;
      const expectedShiftBps = parseFloat(inputExpectedShift ? inputExpectedShift.value : 25) || 25;

      const y = curveData.yields || {};
      const sp = curveData.spreads || {};

      let legShort = "2y";
      let legLong = "10y";
      if (spreadKey === "2s30s") { legShort = "2y"; legLong = "30y"; }
      else if (spreadKey === "5s30s") { legShort = "5y"; legLong = "30y"; }
      else if (spreadKey === "10s30s") { legShort = "10y"; legLong = "30y"; }

      const shortMeta = y[legShort] || { yield: 4.38, duration: 1.85, dv01: 18.5 };
      const longMeta = y[legLong] || { yield: 4.96, duration: 8.2, dv01: 82.0 };

      const hedgeRatio = longMeta.dv01 / shortMeta.dv01;
      const shortNotional = notional * hedgeRatio;
      const dv01PerLeg = (notional / 100000) * longMeta.dv01;

      const multiplier = tradeType === "steepener" ? 1 : -1;
      const estPnl = dv01PerLeg * expectedShiftBps * multiplier;

      const elCurrSpread = document.getElementById("calcCurrSpread");
      const elRatio = document.getElementById("calcHedgeRatio");
      const elLegShort = document.getElementById("calcLegShortDesc");
      const elLegLong = document.getElementById("calcLegLongDesc");
      const elDv01 = document.getElementById("calcTotalDv01");
      const elPnl = document.getElementById("calcEstPnl");

      if (elCurrSpread) {
        const curSp = sp[spreadKey] ? sp[spreadKey].bps : (longMeta.yield - shortMeta.yield) * 100;
        elCurrSpread.textContent = `+${curSp.toFixed(1)} bps`;
      }
      if (elRatio) {
        elRatio.textContent = `${hedgeRatio.toFixed(2)}x (DV01 Neutral)`;
      }
      if (elLegShort) {
        const action = tradeType === "steepener" ? "Pay (Short)" : "Receive (Long)";
        elLegShort.textContent = `${action} $${(shortNotional / 1000000).toFixed(2)}M of ${TENOR_LABELS[legShort]}`;
      }
      if (elLegLong) {
        const action = tradeType === "steepener" ? "Receive (Long)" : "Pay (Short)";
        elLegLong.textContent = `${action} $${(notional / 1000000).toFixed(2)}M of ${TENOR_LABELS[legLong]}`;
      }
      if (elDv01) {
        elDv01.textContent = `$${dv01PerLeg.toFixed(0)} / bp`;
      }
      if (elPnl) {
        const sign = estPnl >= 0 ? "+" : "-";
        elPnl.textContent = `${sign}$${Math.abs(estPnl).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
        elPnl.className = "calc-pnl-val " + (estPnl >= 0 ? "good" : "bad");
      }
    }

    btnCalc.addEventListener("click", runCalc);
    if (selectSpread) selectSpread.addEventListener("change", runCalc);
    if (selectTrade) selectTrade.addEventListener("change", runCalc);
    runCalc();
  }

  /* -------------------------------------------------------------
     MACRO RADAR & NEWS HEADLINES
     ------------------------------------------------------------- */
  function renderMacroRadar() {
    const macro = curveData.macro_assessment;
    if (!macro) return;

    const elTitle = document.getElementById("macroRegimeTitle");
    const elBadge = document.getElementById("macroRegimeBadge");
    const elSumm = document.getElementById("macroRegimeSummary");
    const elAction = document.getElementById("curveActionBanner");

    if (elTitle) elTitle.textContent = macro.regime_name || "Active Macro Regime";
    if (elBadge) elBadge.textContent = macro.regime_id ? macro.regime_id.toUpperCase().replace(/_/g, " ") : "REGIME";
    if (elSumm) elSumm.textContent = macro.summary || "";
    if (elAction) elAction.textContent = macro.tactical_bias || "Maintain neutral duration posture.";

    const headlineList = document.getElementById("macroHeadlineList");
    if (headlineList && macro.news_drivers) {
      headlineList.replaceChildren();
      macro.news_drivers.forEach((item) => {
        const card = document.createElement("div");
        card.className = "headline-card";
        const impactCls = (item.impact || "neutral").toLowerCase().replace(/\s+/g, '-');
        card.innerHTML = `
          <div class="headline-header">
            <span>${item.source} • ${item.date}</span>
            <span class="headline-tag ${impactCls}">${item.impact}</span>
          </div>
          <h4 class="headline-title">${item.headline}</h4>
          <p class="headline-summary">${item.summary}</p>
        `;
        headlineList.appendChild(card);
      });
    }

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

    // Tenor Columns
    TENOR_KEYS.forEach((k) => {
      const px = tenorXMap[k];
      const isHovered = hoverYieldTenor === k;

      // Soft vertical highlight band if hovered
      if (isHovered) {
        ctx.fillStyle = "rgba(0, 113, 227, 0.07)";
        ctx.fillRect(px - 30, pad.top - 10, 60, chartH + 20);
      }

      ctx.strokeStyle = isHovered ? "rgba(0, 113, 227, 0.35)" : "rgba(0, 0, 0, 0.05)";
      ctx.lineWidth = isHovered ? 1.5 : 1;
      ctx.beginPath();
      ctx.moveTo(px, pad.top);
      ctx.lineTo(px, H - pad.bottom);
      ctx.stroke();

      ctx.fillStyle = isHovered ? "#0071e3" : "#1d1d1f";
      ctx.font = isHovered ? "bold 13px sans-serif" : "600 13px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(TENOR_LABELS[k], px, H - pad.bottom + 10);
    });


    // Dual-Band Visual Overlay: Fundamental Fair Value Shaded Corridors & Technical Bands
    const dbf = curveData.dual_band_framework;
    if (dbf && dbf.tenors) {
      TENOR_KEYS.forEach((k) => {
        const tData = dbf.tenors[k];
        if (!tData) return;
        const px = tenorXMap[k];
        const bandW = chartW * 0.16;

        // Fundamental Fair Value Corridor (Shaded Blue)
        const fundTopY = yToPx(tData.fund_band.upper);
        const fundBotY = yToPx(tData.fund_band.lower);
        ctx.fillStyle = "rgba(0, 113, 227, 0.08)";
        ctx.fillRect(px - bandW / 2, fundTopY, bandW, fundBotY - fundTopY);

        ctx.strokeStyle = "rgba(0, 113, 227, 0.40)";
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(px - bandW / 2, fundTopY);
        ctx.lineTo(px + bandW / 2, fundTopY);
        ctx.moveTo(px - bandW / 2, fundBotY);
        ctx.lineTo(px + bandW / 2, fundBotY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Technical Trading Band (Orange Dashed Lines)
        if (tData.tech_band) {
          const techTopY = yToPx(tData.tech_band.upper);
          const techBotY = yToPx(tData.tech_band.lower);
          ctx.strokeStyle = "rgba(255, 149, 0, 0.75)";
          ctx.lineWidth = 1.2;
          ctx.setLineDash([4, 3]);
          ctx.beginPath();
          ctx.moveTo(px - bandW / 2 - 4, techTopY);
          ctx.lineTo(px + bandW / 2 + 4, techTopY);
          ctx.moveTo(px - bandW / 2 - 4, techBotY);
          ctx.lineTo(px + bandW / 2 + 4, techBotY);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      });
    }

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
        const isHovered = hoverYieldTenor === t;

        ctx.beginPath();
        ctx.arc(px, py, isCurrent ? 5.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = isCurrent ? 2 : 1.5;
        ctx.stroke();

        if (isCurrent || isHovered) {
          ctx.fillStyle = "#1d1d1f";
          ctx.font = "bold 12px -apple-system, BlinkMacSystemFont, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(snap[t].toFixed(2) + "%", px, py - 8);

          // Render Signal Pill Badge above current yield
          if (isCurrent && dbf && dbf.tenors && dbf.tenors[t]) {
            const tData = dbf.tenors[t];
            const badgeText = t === "30y" ? "🔴 DUAL CONFLUENCE (-0.20y)" :
                              t === "2y"  ? "🔴 SHORT STRATEGIC (-0.15y)" :
                              t === "5y"  ? "🟢 LONG TACTICAL (+0.10y)" :
                                            "⚪ NEUTRAL (0.00y)";

            const isShort = tData.recommended_duration < 0;
            const isLong = tData.recommended_duration > 0;
            const bgColor = isShort ? "rgba(215, 0, 21, 0.90)" : isLong ? "rgba(36, 138, 61, 0.90)" : "rgba(110, 110, 115, 0.85)";

            ctx.save();
            ctx.font = "bold 10px -apple-system, BlinkMacSystemFont, sans-serif";
            const textMetrics = ctx.measureText(badgeText);
            const bw = textMetrics.width + 12;
            const bh = 18;
            const by = py - 32;

            ctx.fillStyle = bgColor;
            ctx.beginPath();
            ctx.roundRect(px - bw / 2, by, bw, bh, 5);
            ctx.fill();

            ctx.fillStyle = "#ffffff";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(badgeText, px, by + bh / 2);
            ctx.restore();
          }
        }
      });
    });
  }

  /* -------------------------------------------------------------
     INTERACTIVE HISTORICAL SERIES CHART
     ------------------------------------------------------------- */
  function renderHistoryLegendBar(rows) {
    const bar = document.getElementById("historyLegendBar");
    if (!bar || !rows || !rows.length) return;
    bar.replaceChildren();

    const lastRow = rows[rows.length - 1];

    if (activeHistoryMode === "yields") {
      const tenors = [
        { key: "30y", label: "30Y Long Bond", color: "#34c759" },
        { key: "10y", label: "10Y Benchmark", color: "#0071e3" },
        { key: "5y", label: "5Y Belly", color: "#af52de" },
        { key: "2y", label: "2Y Front-End", color: "#ff9500" },
      ];

      tenors.forEach((t) => {
        const btn = document.createElement("button");
        btn.type = "button";
        const isActive = activeHistoryTenors[t.key] !== false;
        btn.className = `legend-pill ${isActive ? "active" : "muted"}`;
        btn.title = `Click to toggle ${t.label} curve on/off`;
        const val = lastRow[t.key] != null ? lastRow[t.key].toFixed(2) + "%" : "—";
        btn.innerHTML = `
          <span class="pill-dot" style="background: ${t.color};"></span>
          <span>${t.label}</span>
          <span class="pill-val" style="color: ${isActive ? t.color : 'inherit'};">${val}</span>
        `;
        btn.addEventListener("click", () => {
          activeHistoryTenors[t.key] = !activeHistoryTenors[t.key];
          // Ensure at least one tenor stays active
          const anyActive = Object.values(activeHistoryTenors).some(Boolean);
          if (!anyActive) activeHistoryTenors[t.key] = true;
          renderHistoryChart();
        });
        bar.appendChild(btn);
      });

      const tip = document.createElement("span");
      tip.style.fontSize = "11px";
      tip.style.color = "var(--muted)";
      tip.style.marginLeft = "auto";
      tip.textContent = "💡 Click curves to toggle • Hover to inspect";
      bar.appendChild(tip);

    } else {
      const spreads = [
        { key: "spread_2s10s", label: "2s10s Benchmark (10Y − 2Y)", color: "#0071e3" },
        { key: "spread_2s30s", label: "2s30s Total Slope (30Y − 2Y)", color: "#af52de" },
        { key: "spread_5s10s", label: "5s10s Belly Slope (10Y − 5Y)", color: "#248a3d" },
      ];

      spreads.forEach((s) => {
        const btn = document.createElement("button");
        btn.type = "button";
        const isActive = activeHistorySpreads[s.key] !== false;
        btn.className = `legend-pill ${isActive ? "active" : "muted"}`;
        btn.title = `Click to toggle ${s.label} on/off`;
        const val = lastRow[s.key] != null ? (lastRow[s.key] >= 0 ? "+" : "") + lastRow[s.key].toFixed(1) + " bps" : "—";
        btn.innerHTML = `
          <span class="pill-dot" style="background: ${s.color};"></span>
          <span>${s.label}</span>
          <span class="pill-val" style="color: ${isActive ? s.color : 'inherit'};">${val}</span>
        `;
        btn.addEventListener("click", () => {
          activeHistorySpreads[s.key] = !activeHistorySpreads[s.key];
          const anyActive = Object.values(activeHistorySpreads).some(Boolean);
          if (!anyActive) activeHistorySpreads[s.key] = true;
          renderHistoryChart();
        });
        bar.appendChild(btn);
      });

      const invBadge = document.createElement("div");
      invBadge.className = "legend-pill";
      invBadge.style.cursor = "default";
      invBadge.style.borderColor = "rgba(215, 0, 21, 0.4)";
      invBadge.innerHTML = `
        <span class="pill-dot" style="background: #d70015;"></span>
        <span style="color: #d70015; font-weight: 700;">Inversion Barrier</span>
        <span class="pill-val" style="color: #d70015;">0.0 bps</span>
      `;
      bar.appendChild(invBadge);
    }
  }

  function renderHistoryChart() {
    const canvas = document.getElementById("historyChartCanvas");
    if (!canvas || !curveData || !curveData.history) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 340 * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 340;
    const pad = { top: 28, right: 88, bottom: 42, left: 58 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const allRows = curveData.history;
    const countMap = { "1m": 22, "3m": 66, "6m": 126, "1y": 252 };
    const maxPts = countMap[activeHistoryRange] || allRows.length;
    const rows = allRows.slice(-maxPts);
    if (!rows.length) return;

    renderHistoryLegendBar(rows);

    let minY = Infinity;
    let maxY = -Infinity;

    if (activeHistoryMode === "yields") {
      rows.forEach((r) => {
        TENOR_KEYS.forEach((k) => {
          if (activeHistoryTenors[k] && r[k] != null) {
            minY = Math.min(minY, r[k]);
            maxY = Math.max(maxY, r[k]);
          }
        });
      });
      if (minY === Infinity) { minY = 3.5; maxY = 5.5; }
      minY = Math.floor(minY * 2) / 2 - 0.2;
      maxY = Math.ceil(maxY * 2) / 2 + 0.2;
    } else {
      rows.forEach((r) => {
        ["spread_2s10s", "spread_2s30s", "spread_5s10s"].forEach((sk) => {
          if (activeHistorySpreads[sk] && typeof r[sk] === "number") {
            minY = Math.min(minY, r[sk]);
            maxY = Math.max(maxY, r[sk]);
          }
        });
      });
      if (minY === Infinity) { minY = -20; maxY = 100; }
      minY = Math.min(minY, -10);
      maxY = Math.max(maxY, 20);
      const padY = (maxY - minY) * 0.12;
      minY = Math.floor((minY - padY) / 10) * 10;
      maxY = Math.ceil((maxY + padY) / 10) * 10;
    }

    function yToPx(val) {
      return pad.top + chartH * (1 - (val - minY) / (maxY - minY));
    }
    function xToPx(idx) {
      return pad.left + (chartW * idx) / (rows.length - 1);
    }

    // Grid lines
    ctx.strokeStyle = "rgba(0, 0, 0, 0.06)";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#86868b";
    ctx.font = "11.5px -apple-system, BlinkMacSystemFont, sans-serif";
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
      const label = activeHistoryMode === "yields" ? v.toFixed(2) + "%" : (v >= 0 ? "+" : "") + v.toFixed(0) + " bps";
      ctx.fillText(label, pad.left - 8, py);
    }

    // Zero line (Spreads mode)
    if (activeHistoryMode === "spreads" && minY <= 0 && maxY >= 0) {
      const zPy = yToPx(0);
      ctx.save();
      ctx.strokeStyle = "rgba(215, 0, 21, 0.75)";
      ctx.lineWidth = 1.6;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.left, zPy);
      ctx.lineTo(W - pad.right, zPy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#d70015";
      ctx.font = "bold 10px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("0 bps — Inversion Barrier (Recession Threshold)", pad.left + 8, zPy - 5);
      ctx.restore();
    }

    // Render Series Lines & End Badges
    if (activeHistoryMode === "yields") {
      const seriesColors = {
        "30y": "#34c759",
        "10y": "#0071e3",
        "5y": "#af52de",
        "2y": "#ff9500",
      };

      ["2y", "5y", "10y", "30y"].forEach((k) => {
        if (!activeHistoryTenors[k]) return;
        const color = seriesColors[k];

        ctx.beginPath();
        rows.forEach((r, i) => {
          const px = xToPx(i);
          const py = yToPx(r[k]);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.2;
        ctx.stroke();

        // End-of-line marker & badge
        const lastVal = rows[rows.length - 1][k];
        if (lastVal != null) {
          const lastX = xToPx(rows.length - 1);
          const lastY = yToPx(lastVal);

          ctx.beginPath();
          ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;
          ctx.stroke();

          // Pill Badge
          const badgeX = lastX + 7;
          const badgeY = lastY - 9.5;
          const badgeW = 75;
          const badgeH = 19;

          ctx.save();
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 5);
          else ctx.rect(badgeX, badgeY, badgeW, badgeH);
          ctx.fillStyle = color;
          ctx.fill();

          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 10px -apple-system, BlinkMacSystemFont, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(`${k.toUpperCase()} ${lastVal.toFixed(2)}%`, badgeX + badgeW / 2, badgeY + badgeH / 2);
          ctx.restore();
        }
      });
    } else {
      const spreadConfigs = [
        { key: "spread_2s10s", label: "2s10s", color: "#0071e3", width: 2.5 },
        { key: "spread_2s30s", label: "2s30s", color: "#af52de", width: 2.2 },
        { key: "spread_5s10s", label: "5s10s", color: "#248a3d", width: 2.2 },
      ];

      spreadConfigs.forEach((cfg) => {
        if (!activeHistorySpreads[cfg.key]) return;
        ctx.beginPath();
        rows.forEach((r, i) => {
          const px = xToPx(i);
          const py = yToPx(r[cfg.key]);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = cfg.color;
        ctx.lineWidth = cfg.width;
        ctx.stroke();

        const lastVal = rows[rows.length - 1][cfg.key];
        if (typeof lastVal === "number") {
          const lastX = xToPx(rows.length - 1);
          const lastY = yToPx(lastVal);

          ctx.beginPath();
          ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
          ctx.fillStyle = cfg.color;
          ctx.fill();
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;
          ctx.stroke();

          // Pill badge
          const badgeX = lastX + 7;
          const badgeY = lastY - 9.5;
          const badgeW = 75;
          const badgeH = 19;

          ctx.save();
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 5);
          else ctx.rect(badgeX, badgeY, badgeW, badgeH);
          ctx.fillStyle = cfg.color;
          ctx.fill();

          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 9.5px -apple-system, BlinkMacSystemFont, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          const sign = lastVal >= 0 ? "+" : "";
          ctx.fillText(`${cfg.label} ${sign}${Math.round(lastVal)}b`, badgeX + badgeW / 2, badgeY + badgeH / 2);
          ctx.restore();
        }
      });
    }

    // X Axis Labels (Dates)
    ctx.fillStyle = "#86868b";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
    const xLabelsCount = Math.min(6, rows.length);
    for (let i = 0; i < xLabelsCount; i++) {
      const rIdx = Math.round((i * (rows.length - 1)) / (xLabelsCount - 1));
      const px = xToPx(rIdx);
      const dt = rows[rIdx].date;
      ctx.fillText(dt, px, H - pad.bottom + 12);
    }

    // HOVER OVER INTERACTIVITY
    if (hoverHistoryIdx !== null && hoverHistoryIdx >= 0 && hoverHistoryIdx < rows.length) {
      const hx = xToPx(hoverHistoryIdx);
      const r = rows[hoverHistoryIdx];

      ctx.save();
      // Vertical crosshair
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = "rgba(0, 113, 227, 0.45)";
      ctx.lineWidth = 1.5;
      ctx.moveTo(hx, pad.top);
      ctx.lineTo(hx, H - pad.bottom);
      ctx.stroke();

      // Bottom date badge
      ctx.setLineDash([]);
      ctx.fillStyle = "#1d1d1f";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(hx - 40, H - pad.bottom + 8, 80, 20, 5);
      else ctx.rect(hx - 40, H - pad.bottom + 8, 80, 20);
      ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10.5px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(r.date, hx, H - pad.bottom + 18);

      // Glowing anchor dots
      if (activeHistoryMode === "yields") {
        const seriesColors = { "30y": "#34c759", "10y": "#0071e3", "5y": "#af52de", "2y": "#ff9500" };
        ["30y", "10y", "5y", "2y"].forEach((k) => {
          if (!activeHistoryTenors[k] || r[k] == null) return;
          const py = yToPx(r[k]);
          const col = seriesColors[k];
          ctx.beginPath();
          ctx.arc(hx, py, 7.5, 0, Math.PI * 2);
          ctx.fillStyle = col + "40";
          ctx.fill();
          ctx.beginPath();
          ctx.arc(hx, py, 4, 0, Math.PI * 2);
          ctx.fillStyle = col;
          ctx.fill();
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        });
      } else {
        const spreadConfigs = [
          { key: "spread_2s10s", color: "#0071e3" },
          { key: "spread_2s30s", color: "#af52de" },
          { key: "spread_5s10s", color: "#248a3d" },
        ];
        spreadConfigs.forEach((cfg) => {
          if (!activeHistorySpreads[cfg.key] || typeof r[cfg.key] !== "number") return;
          const py = yToPx(r[cfg.key]);
          ctx.beginPath();
          ctx.arc(hx, py, 7.5, 0, Math.PI * 2);
          ctx.fillStyle = cfg.color + "40";
          ctx.fill();
          ctx.beginPath();
          ctx.arc(hx, py, 4, 0, Math.PI * 2);
          ctx.fillStyle = cfg.color;
          ctx.fill();
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        });
      }
      ctx.restore();
    }
  }

  /* -------------------------------------------------------------
     DEDICATED CURVE SPREADS CHART (2s10s, 2s30s, 5s10s)
     ------------------------------------------------------------- */
  function renderSpreadChart() {
    const canvas = document.getElementById("spreadChartCanvas");
    if (!canvas || !curveData || !curveData.history) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 340 * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 340;
    const pad = { top: 28, right: 88, bottom: 42, left: 58 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const allRows = curveData.history;
    const countMap = { "1m": 22, "3m": 66, "6m": 126, "1y": 252 };
    const maxPts = countMap[activeSpreadRange] || allRows.length;
    const rows = allRows.slice(-maxPts);
    if (rows.length === 0) return;

    renderSpreadStatsGrid(rows);

    let minVal = Infinity;
    let maxVal = -Infinity;

    const spreadsToPlot = activeSpreadKey === "all" ? ["spread_2s10s", "spread_2s30s", "spread_5s10s"] : [`spread_${activeSpreadKey}`];
    spreadsToPlot.forEach((sKey) => {
      rows.forEach((r) => {
        const val = r[sKey];
        if (typeof val === "number" && !isNaN(val)) {
          if (val < minVal) minVal = val;
          if (val > maxVal) maxVal = val;
        }
      });
    });

    if (minVal === Infinity) { minVal = -20; maxVal = 100; }
    minVal = Math.min(minVal, -10);
    maxVal = Math.max(maxVal, 20);

    const padY = (maxVal - minVal) * 0.12 || 10;
    minVal = Math.floor((minVal - padY) / 10) * 10;
    maxVal = Math.ceil((maxVal + padY) / 10) * 10;

    const toX = (idx) => pad.left + (idx / (rows.length - 1)) * chartW;
    const toY = (val) => pad.top + (1 - (val - minVal) / (maxVal - minVal)) * chartH;

    // Grid lines
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(0,0,0,0.06)";
    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
      const v = minVal + (i / ySteps) * (maxVal - minVal);
      const y = toY(v);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(W - pad.right, y);
      ctx.stroke();

      ctx.fillStyle = "#86868b";
      ctx.font = "11.5px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`${v >= 0 ? "+" : ""}${Math.round(v)} bps`, pad.left - 8, y + 3.5);
    }

    // Fundamental Fair Value Corridor for selected spread
    if (activeSpreadKey !== "all" && curveData.dual_band_framework && curveData.dual_band_framework.spreads) {
      const spData = curveData.dual_band_framework.spreads[activeSpreadKey];
      if (spData && spData.fund_band) {
        const topY = toY(spData.fund_band.upper_bps);
        const botY = toY(spData.fund_band.lower_bps);
        const midY = toY(spData.fund_band.mid_bps);

        // Soft shaded corridor
        ctx.fillStyle = "rgba(0, 113, 227, 0.08)";
        ctx.fillRect(pad.left, topY, chartW, botY - topY);

        // Dashed boundaries
        ctx.strokeStyle = "rgba(0, 113, 227, 0.45)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(pad.left, topY); ctx.lineTo(W - pad.right, topY);
        ctx.moveTo(pad.left, botY); ctx.lineTo(W - pad.right, botY);
        ctx.stroke();

        ctx.strokeStyle = "rgba(0, 113, 227, 0.65)";
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(pad.left, midY); ctx.lineTo(W - pad.right, midY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Top right banner on spread chart
        const isSteep = spData.signal.includes("STEEPENER");
        const bannerTxt = `SIGNAL: ${spData.signal_badge} | Stop: +${spData.stop_loss_bps} bps | Target: +${spData.target_bps} bps`;
        ctx.save();
        ctx.fillStyle = isSteep ? "rgba(215, 0, 21, 0.90)" : "rgba(0, 113, 227, 0.90)";
        ctx.beginPath();
        ctx.roundRect(pad.left + 8, pad.top + 6, 370, 22, 6);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(bannerTxt, pad.left + 16, pad.top + 17);
        ctx.restore();
      }
    }

    // Prominent Red Zero Inversion Barrier Line
    const zeroY = toY(0);
    if (zeroY >= pad.top && zeroY <= pad.top + chartH) {
      ctx.save();
      ctx.lineWidth = 1.8;
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = "rgba(215, 0, 21, 0.85)";
      ctx.beginPath();
      ctx.moveTo(pad.left, zeroY);
      ctx.lineTo(W - pad.right, zeroY);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#d70015";
      ctx.font = "bold 10px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("0.0 bps — INVERSION BARRIER (Recession Threshold)", pad.left + 8, zeroY - 5);
      ctx.restore();
    }

    // X Axis Labels (Dates)
    ctx.fillStyle = "#86868b";
    ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center";
    const xLabelCount = Math.min(6, rows.length);
    for (let i = 0; i < xLabelCount; i++) {
      const idx = Math.round((i / (xLabelCount - 1)) * (rows.length - 1));
      const r = rows[idx];
      if (!r) continue;
      const x = toX(idx);
      ctx.fillText(r.date, x, pad.top + chartH + 15);
    }

    const SPREAD_LINE_CONFIG = {
      spread_2s10s: { label: "2s10s Benchmark (10Y − 2Y)", tag: "2s10s", color: "#0071e3", width: 2.5 },
      spread_2s30s: { label: "2s30s Total Slope (30Y − 2Y)", tag: "2s30s", color: "#af52de", width: 2.2 },
      spread_5s10s: { label: "5s10s Belly Slope (10Y − 5Y)", tag: "5s10s", color: "#248a3d", width: 2.2 },
    };

    spreadsToPlot.forEach((sKey) => {
      const cfg = SPREAD_LINE_CONFIG[sKey] || { label: sKey, tag: sKey, color: "#0071e3", width: 2 };

      // Shaded area for single spread mode
      if (activeSpreadKey !== "all") {
        const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
        grad.addColorStop(0, "rgba(0, 113, 227, 0.16)");
        grad.addColorStop(1, "rgba(0, 113, 227, 0.00)");
        ctx.beginPath();
        ctx.moveTo(toX(0), toY(rows[0][sKey]));
        for (let i = 1; i < rows.length; i++) {
          ctx.lineTo(toX(i), toY(rows[i][sKey]));
        }
        ctx.lineTo(toX(rows.length - 1), pad.top + chartH);
        ctx.lineTo(toX(0), pad.top + chartH);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();

        renderMovingAverageLine(ctx, rows, sKey, 50, "#ff9500", [4, 3], toX, toY);
      }

      // Main line
      ctx.lineWidth = cfg.width;
      ctx.strokeStyle = cfg.color;
      ctx.beginPath();
      for (let i = 0; i < rows.length; i++) {
        const x = toX(i);
        const y = toY(rows[i][sKey]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // End point marker & badge
      const lastX = toX(rows.length - 1);
      const lastVal = rows[rows.length - 1][sKey];
      if (typeof lastVal === "number") {
        const lastY = toY(lastVal);

        ctx.beginPath();
        ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = cfg.color;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Right margin badge
        const badgeX = lastX + 7;
        const badgeY = lastY - 9.5;
        const badgeW = 75;
        const badgeH = 19;

        ctx.save();
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 5);
        else ctx.rect(badgeX, badgeY, badgeW, badgeH);
        ctx.fillStyle = cfg.color;
        ctx.fill();

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 9.5px -apple-system, BlinkMacSystemFont, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const sign = lastVal >= 0 ? "+" : "";
        ctx.fillText(`${cfg.tag} ${sign}${Math.round(lastVal)}b`, badgeX + badgeW / 2, badgeY + badgeH / 2);
        ctx.restore();
      }
    });

    // Top Legend
    let legX = pad.left + 10;
    const legY = pad.top + 14;
    spreadsToPlot.forEach((sKey) => {
      const cfg = SPREAD_LINE_CONFIG[sKey] || { label: sKey, color: "#0071e3" };
      ctx.fillStyle = cfg.color;
      ctx.fillRect(legX, legY - 8, 12, 4);
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "bold 11px -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(cfg.label, legX + 16, legY - 3);
      legX += ctx.measureText(cfg.label).width + 30;
    });

    if (activeSpreadKey !== "all") {
      ctx.fillStyle = "#ff9500";
      ctx.fillRect(legX, legY - 8, 12, 3);
      ctx.fillStyle = "#6e6e73";
      ctx.font = "11px -apple-system, sans-serif";
      ctx.fillText("50d SMA", legX + 16, legY - 3);
    }

    // HOVER OVER INTERACTIVITY
    if (hoverSpreadIdx !== null && hoverSpreadIdx >= 0 && hoverSpreadIdx < rows.length) {
      const hx = toX(hoverSpreadIdx);
      const r = rows[hoverSpreadIdx];

      ctx.save();
      // Vertical crosshair
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = "rgba(0, 113, 227, 0.45)";
      ctx.lineWidth = 1.5;
      ctx.moveTo(hx, pad.top);
      ctx.lineTo(hx, pad.top + chartH);
      ctx.stroke();

      // Bottom date badge
      ctx.setLineDash([]);
      ctx.fillStyle = "#1d1d1f";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(hx - 40, pad.top + chartH + 6, 80, 20, 5);
      else ctx.rect(hx - 40, pad.top + chartH + 6, 80, 20);
      ctx.fill();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10.5px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(r.date, hx, pad.top + chartH + 16);

      // Glowing anchor dots
      spreadsToPlot.forEach((sKey) => {
        const val = r[sKey];
        if (typeof val !== "number") return;
        const cfg = SPREAD_LINE_CONFIG[sKey] || { color: "#0071e3" };
        const py = toY(val);

        ctx.beginPath();
        ctx.arc(hx, py, 7.5, 0, Math.PI * 2);
        ctx.fillStyle = cfg.color + "40";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(hx, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = cfg.color;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
      ctx.restore();
    }
  }

  function renderMovingAverageLine(ctx, rows, key, windowSize, color, dash, toX, toY) {
    if (rows.length < windowSize) return;
    ctx.save();
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = color;
    ctx.setLineDash(dash);
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < rows.length; i++) {
      if (i < windowSize - 1) continue;
      let sum = 0;
      for (let j = 0; j < windowSize; j++) {
        sum += rows[i - j][key];
      }
      const avg = sum / windowSize;
      const x = toX(i);
      const y = toY(avg);
      if (!started) { ctx.moveTo(x, y); started = true; }
      else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
    ctx.restore();
  }

  function renderSpreadStatsGrid(rows) {
    const grid = document.getElementById("spreadStatsGrid");
    if (!grid || !curveData || !curveData.spreads) return;
    grid.replaceChildren();

    const spreads = curveData.spreads;

    if (activeSpreadKey !== "all") {
      const sp = spreads[activeSpreadKey] || {};
      const curr = sp.bps !== undefined ? sp.bps : 0;
      const chg = sp.change_bps !== undefined ? sp.change_bps : 0;
      const sma50 = sp.sma50 !== undefined ? sp.sma50 : 0;
      const sma200 = sp.sma200 !== undefined ? sp.sma200 : 0;
      const min52 = sp.min_52w !== undefined ? sp.min_52w : -100;
      const max52 = sp.max_52w !== undefined ? sp.max_52w : 100;
      const rsi = sp.rsi14 !== undefined ? sp.rsi14 : 50;

      const signChg = chg > 0 ? "+" : "";
      const signCurr = curr > 0 ? "+" : "";

      const cards = [
        { label: "Current Level", val: `${signCurr}${curr.toFixed(1)} bps`, sub: `${signChg}${chg.toFixed(1)} bps 1D` },
        { label: "Curve Status", val: sp.status || (curr > 0 ? "Normal" : "Inverted"), sub: curr > 0 ? `${curr.toFixed(1)} bps above 0` : `${Math.abs(curr).toFixed(1)} bps inverted` },
        { label: "50-Day Moving Avg", val: `+${sma50.toFixed(1)} bps`, sub: `${(curr - sma50) >= 0 ? "+" : ""}${(curr - sma50).toFixed(1)} bps vs SMA50` },
        { label: "200-Day Moving Avg", val: `${sma200 >= 0 ? "+" : ""}${sma200.toFixed(1)} bps`, sub: `${(curr - sma200) >= 0 ? "+" : ""}${(curr - sma200).toFixed(1)} bps vs SMA200` },
        { label: "14-Day RSI", val: rsi.toFixed(1), sub: rsi > 70 ? "Overbought" : rsi < 30 ? "Oversold" : "Neutral Range" },
        { label: "52-Week Range", val: `${min52.toFixed(1)} to +${max52.toFixed(1)}`, sub: "Annual Extremes" },
      ];

      cards.forEach((c) => {
        const el = document.createElement("div");
        el.className = "spread-stat-card";
        el.innerHTML = `
          <span class="spread-stat-label">${c.label}</span>
          <span class="spread-stat-val">${c.val}</span>
          <span class="spread-stat-sub">${c.sub}</span>
        `;
        grid.appendChild(el);
      });
    } else {
      ["2s10s", "2s30s", "5s10s"].forEach((k) => {
        const sp = spreads[k] || {};
        const curr = sp.bps !== undefined ? sp.bps : 0;
        const chg = sp.change_bps !== undefined ? sp.change_bps : 0;
        const signCurr = curr > 0 ? "+" : "";
        const signChg = chg > 0 ? "+" : "";

        const el = document.createElement("div");
        el.className = "spread-stat-card";
        el.innerHTML = `
          <span class="spread-stat-label">${sp.name || k}</span>
          <span class="spread-stat-val" style="color: ${k === '2s10s' ? '#0071e3' : k === '2s30s' ? '#af52de' : '#248a3d'};">${signCurr}${curr.toFixed(1)} bps</span>
          <span class="spread-stat-sub">1D: ${signChg}${chg.toFixed(1)} bps | 50d SMA: +${sp.sma50 ? sp.sma50.toFixed(1) : 0} bps</span>
        `;
        grid.appendChild(el);
      });
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

    const elName = document.getElementById("scenarioName");
    const elDesc = document.getElementById("scenarioDesc");
    const elRegime = document.getElementById("scenarioRegimeTag");

    if (elName) elName.textContent = sc.name;
    if (elDesc) elDesc.textContent = sc.desc;
    if (elRegime) elRegime.textContent = sc.regime;

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

  /* -------------------------------------------------------------
     TRADE RECOMMENDATIONS & LIVE P&L TRACKER
     ------------------------------------------------------------- */
  function renderTradeTracker() {
    const summaryBar = document.getElementById("trackerSummaryBar");
    const tbody = document.getElementById("trackerTableBody");
    if (!summaryBar || !tbody) return;

    const tracker = curveData.trade_tracker || {
      portfolio_summary: { total_trades: 0, open_trades: 0, closed_trades: 0, total_pnl_bps: 0, total_pnl_usd: 0, win_rate_pct: 100 },
      trades: []
    };

    const summary = tracker.portfolio_summary || {};
    const trades = tracker.trades || [];

    // Render Summary Bar
    summaryBar.replaceChildren();

    const signBps = (summary.total_pnl_bps || 0) > 0 ? "+" : "";
    const signUsd = (summary.total_pnl_usd || 0) > 0 ? "+" : "";
    const pnlCls = (summary.total_pnl_usd || 0) >= 0 ? "good" : "bad";

    const stats = [
      { label: "Total Ideas Tracked", val: summary.total_trades || 0, sub: `${summary.open_trades || 0} Open • ${summary.closed_trades || 0} Closed` },
      { label: "Win Rate", val: `${summary.win_rate_pct || 100}%`, sub: "Closed + Open in Profit" },
      { label: "Cumulative MTM (bps)", val: `${signBps}${(summary.total_pnl_bps || 0).toFixed(1)} bps`, sub: "Aggregate Basis Points", cls: pnlCls },
      { label: "Mark-to-Market P&L", val: `${signUsd}$${Math.abs(summary.total_pnl_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, sub: "Live Unrealized + Realized", cls: pnlCls },
    ];

    stats.forEach((st) => {
      const card = document.createElement("div");
      card.className = "tracker-summary-card";
      card.innerHTML = `
        <span class="tracker-summary-label">${st.label}</span>
        <span class="tracker-summary-val ${st.cls || ''}">${st.val}</span>
        <span class="tracker-summary-sub">${st.sub}</span>
      `;
      summaryBar.appendChild(card);
    });

    // Render Trades Table
    tbody.replaceChildren();

    const filteredTrades = activeTrackerFilter === "all" ? trades : trades.filter(t => t.desk === activeTrackerFilter);

    if (filteredTrades.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="10" style="padding: 24px; text-align: center; color: var(--muted);">No recommendations for ${activeTrackerFilter}.</td>`;
      tbody.appendChild(tr);
      return;
    }

    filteredTrades.forEach((t) => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      const pnlBps = t.pnl_bps || 0;
      const pnlUsd = t.pnl_usd || 0;
      const signB = pnlBps > 0 ? "+" : "";
      const signU = pnlUsd > 0 ? "+" : "";
      const pCls = pnlUsd >= 0 ? "good" : "bad";

      const badgeCls = t.status === "OPEN" ? "badge-open" : t.status === "TARGET_HIT" ? "badge-hit" : "badge-stopped";

      tr.innerHTML = `
        <td style="padding: 12px 10px; font-weight: 500; font-size: 12px; color: var(--muted);">${t.date_opened}</td>
        <td style="padding: 12px 10px;">
          <div style="font-weight: 700; color: var(--text);">${t.title}</div>
          <div style="font-size: 12px; color: var(--muted); margin-top: 2px;">${t.rationale}</div>
        </td>
        <td style="padding: 12px 10px;"><span class="desk-tag">${t.desk}</span></td>
        <td style="padding: 12px 10px;">
          <div style="font-weight: 600;">${t.instrument}</div>
          <div style="font-size: 11.5px; color: var(--muted);">${t.sizing}</div>
        </td>
        <td style="padding: 12px 10px; font-weight: 600;">${t.entry_level} ${t.entry_unit || ''}</td>
        <td style="padding: 12px 10px; font-weight: 700; color: var(--accent);">${t.current_level} ${t.entry_unit || ''}</td>
        <td style="padding: 12px 10px; font-size: 12px;">
          <div><span style="color: var(--good); font-weight: 600;">Tgt:</span> ${t.target_level}</div>
          <div><span style="color: var(--bad); font-weight: 600;">Stp:</span> ${t.stop_loss_level}</div>
        </td>
        <td style="padding: 12px 10px; font-weight: 700;" class="${pCls}">${signB}${pnlBps.toFixed(1)}</td>
        <td style="padding: 12px 10px; font-weight: 800;" class="${pCls}">${signU}$${Math.abs(pnlUsd).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td style="padding: 12px 10px;"><span class="${badgeCls}">${t.status}</span></td>
      `;
      tbody.appendChild(tr);
    });
  }

  /* -------------------------------------------------------------
     CHART HOVER ENGINES & TOOLTIP UPDATERS
     ------------------------------------------------------------- */
  function setupChartHoverEngines() {
    // 1. History Chart Hover
    const histCanvas = document.getElementById("historyChartCanvas");
    const histTooltip = document.getElementById("historyChartTooltip");

    if (histCanvas && histTooltip) {
      histCanvas.addEventListener("mousemove", (e) => {
        if (!curveData || !curveData.history) return;
        const countMap = { "1m": 22, "3m": 66, "6m": 126, "1y": 252 };
        const maxPts = countMap[activeHistoryRange] || curveData.history.length;
        const rows = curveData.history.slice(-maxPts);
        if (!rows.length) return;

        const rect = histCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const padLeft = 58;
        const padRight = 88;
        const chartW = rect.width - padLeft - padRight;

        if (mouseX >= padLeft - 10 && mouseX <= rect.width - padRight + 10) {
          const frac = Math.max(0, Math.min(1, (mouseX - padLeft) / chartW));
          hoverHistoryIdx = Math.round(frac * (rows.length - 1));
          renderHistoryChart();
          updateHistoryTooltip(rows[hoverHistoryIdx], padLeft + (chartW * hoverHistoryIdx) / (rows.length - 1), rect.width);
        } else {
          hoverHistoryIdx = null;
          histTooltip.style.display = "none";
          renderHistoryChart();
        }
      });

      histCanvas.addEventListener("mouseleave", () => {
        hoverHistoryIdx = null;
        histTooltip.style.display = "none";
        renderHistoryChart();
      });
    }

    // 2. Dedicated Spreads Chart Hover
    const spCanvas = document.getElementById("spreadChartCanvas");
    const spTooltip = document.getElementById("spreadChartTooltip");

    if (spCanvas && spTooltip) {
      spCanvas.addEventListener("mousemove", (e) => {
        if (!curveData || !curveData.history) return;
        const countMap = { "1m": 22, "3m": 66, "6m": 126, "1y": 252 };
        const maxPts = countMap[activeSpreadRange] || curveData.history.length;
        const rows = curveData.history.slice(-maxPts);
        if (!rows.length) return;

        const rect = spCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const padLeft = 58;
        const padRight = 88;
        const chartW = rect.width - padLeft - padRight;

        if (mouseX >= padLeft - 10 && mouseX <= rect.width - padRight + 10) {
          const frac = Math.max(0, Math.min(1, (mouseX - padLeft) / chartW));
          hoverSpreadIdx = Math.round(frac * (rows.length - 1));
          renderSpreadChart();
          updateSpreadTooltip(rows[hoverSpreadIdx], padLeft + (chartW * hoverSpreadIdx) / (rows.length - 1), rect.width);
        } else {
          hoverSpreadIdx = null;
          spTooltip.style.display = "none";
          renderSpreadChart();
        }
      });

      spCanvas.addEventListener("mouseleave", () => {
        hoverSpreadIdx = null;
        spTooltip.style.display = "none";
        renderSpreadChart();
      });
    }

    // 3. Yield Curve Shape Hover
    const ycCanvas = document.getElementById("yieldCurveCanvas");
    const ycTooltip = document.getElementById("yieldCurveTooltip");

    if (ycCanvas && ycTooltip) {
      ycCanvas.addEventListener("mousemove", (e) => {
        if (!curveData || !curveData.snapshots) return;
        const rect = ycCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const padLeft = 55;
        const padRight = 40;
        const chartW = rect.width - padLeft - padRight;

        const tenorXMap = {
          "2y": padLeft + chartW * 0.10,
          "5y": padLeft + chartW * 0.38,
          "10y": padLeft + chartW * 0.68,
          "30y": padLeft + chartW * 0.95,
        };

        let closest = null;
        let minDist = 50; // pixel threshold
        Object.keys(tenorXMap).forEach((t) => {
          const dist = Math.abs(mouseX - tenorXMap[t]);
          if (dist < minDist) {
            minDist = dist;
            closest = t;
          }
        });

        if (closest) {
          hoverYieldTenor = closest;
          renderYieldCurveChart();
          updateYieldCurveTooltip(closest, tenorXMap[closest], rect.width);
        } else {
          hoverYieldTenor = null;
          ycTooltip.style.display = "none";
          renderYieldCurveChart();
        }
      });

      ycCanvas.addEventListener("mouseleave", () => {
        hoverYieldTenor = null;
        ycTooltip.style.display = "none";
        renderYieldCurveChart();
      });
    }
  }

  function updateHistoryTooltip(row, xPx, totalW) {
    const tip = document.getElementById("historyChartTooltip");
    if (!tip || !row) return;

    tip.style.display = "block";
    tip.style.left = `${xPx}px`;
    tip.style.top = `38px`;
    const isRight = xPx > totalW * 0.62;
    tip.style.transform = isRight ? "translate(calc(-100% - 14px), 0)" : "translate(14px, 0)";

    if (activeHistoryMode === "yields") {
      const s2s10 = row.spread_2s10s !== undefined ? row.spread_2s10s : ((row["10y"] - row["2y"]) * 100);
      const isNormal = s2s10 >= 0;
      tip.innerHTML = `
        <div class="tooltip-date">
          <span>📅 ${row.date}</span>
          <span class="${isNormal ? 'status-pill-normal' : 'status-pill-inverted'}">${isNormal ? 'Normal Slope' : 'Inverted'}</span>
        </div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #34c759;"></span>30Y Long Bond</span><span class="tooltip-val">${row["30y"] != null ? row["30y"].toFixed(2) + "%" : "—"}</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #0071e3;"></span>10Y Benchmark</span><span class="tooltip-val">${row["10y"] != null ? row["10y"].toFixed(2) + "%" : "—"}</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #af52de;"></span>5Y Belly</span><span class="tooltip-val">${row["5y"] != null ? row["5y"].toFixed(2) + "%" : "—"}</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #ff9500;"></span>2Y Front-End</span><span class="tooltip-val">${row["2y"] != null ? row["2y"].toFixed(2) + "%" : "—"}</span></div>
        <div class="tooltip-footer">
          <div style="display: flex; justify-content: space-between; font-weight: 700;">
            <span>2s10s Spread:</span>
            <span style="color: ${isNormal ? '#248a3d' : '#d70015'};">${isNormal ? '+' : ''}${s2s10.toFixed(1)} bps</span>
          </div>
          <div style="font-size: 10px; color: #86868b; margin-top: 3px;">Math: 10Y (${row["10y"] ? row["10y"].toFixed(2) : 0}%) − 2Y (${row["2y"] ? row["2y"].toFixed(2) : 0}%)</div>
        </div>
      `;
    } else {
      const s2s10 = row.spread_2s10s || 0;
      const s2s30 = row.spread_2s30s || 0;
      const s5s10 = row.spread_5s10s || 0;
      const isNormal = s2s10 >= 0;

      tip.innerHTML = `
        <div class="tooltip-date">
          <span>📅 ${row.date}</span>
          <span class="${isNormal ? 'status-pill-normal' : 'status-pill-inverted'}">${isNormal ? 'Normal Slope' : 'Inverted'}</span>
        </div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #0071e3;"></span>2s10s (10Y − 2Y)</span><span class="tooltip-val" style="color: #0071e3;">${s2s10 >= 0 ? '+' : ''}${s2s10.toFixed(1)} bps</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #af52de;"></span>2s30s (30Y − 2Y)</span><span class="tooltip-val" style="color: #af52de;">${s2s30 >= 0 ? '+' : ''}${s2s30.toFixed(1)} bps</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #248a3d;"></span>5s10s (10Y − 5Y)</span><span class="tooltip-val" style="color: #248a3d;">${s5s10 >= 0 ? '+' : ''}${s5s10.toFixed(1)} bps</span></div>
        <div class="tooltip-footer">
          <div style="font-weight: 600; color: #1d1d1f;">Spread = Longer Tenor − Shorter Tenor</div>
          <div style="font-size: 10px; color: #86868b; margin-top: 2px;">${isNormal ? '✅ Positive Slope: Healthy economic expansion' : '⚠️ Negative (< 0 bps): Recession warning signal'}</div>
        </div>
      `;
    }
  }

  function updateSpreadTooltip(row, xPx, totalW) {
    const tip = document.getElementById("spreadChartTooltip");
    if (!tip || !row) return;

    tip.style.display = "block";
    tip.style.left = `${xPx}px`;
    tip.style.top = `38px`;
    const isRight = xPx > totalW * 0.62;
    tip.style.transform = isRight ? "translate(calc(-100% - 14px), 0)" : "translate(14px, 0)";

    const SPREAD_INFO = {
      "2s10s": { name: "2s10s Benchmark", formula: "10Y Yield − 2Y Yield", key: "spread_2s10s", color: "#0071e3" },
      "2s30s": { name: "2s30s Total Slope", formula: "30Y Yield − 2Y Yield", key: "spread_2s30s", color: "#af52de" },
      "5s10s": { name: "5s10s Belly Slope", formula: "10Y Yield − 5Y Yield", key: "spread_5s10s", color: "#248a3d" },
    };

    if (activeSpreadKey !== "all") {
      const info = SPREAD_INFO[activeSpreadKey] || SPREAD_INFO["2s10s"];
      const val = row[info.key] || 0;
      const isNormal = val >= 0;

      let formulaMath = "";
      if (activeSpreadKey === "2s10s") {
        formulaMath = `10Y (${row["10y"] ? row["10y"].toFixed(2) : 0}%) − 2Y (${row["2y"] ? row["2y"].toFixed(2) : 0}%)`;
      } else if (activeSpreadKey === "2s30s") {
        formulaMath = `30Y (${row["30y"] ? row["30y"].toFixed(2) : 0}%) − 2Y (${row["2y"] ? row["2y"].toFixed(2) : 0}%)`;
      } else if (activeSpreadKey === "5s10s") {
        formulaMath = `10Y (${row["10y"] ? row["10y"].toFixed(2) : 0}%) − 5Y (${row["5y"] ? row["5y"].toFixed(2) : 0}%)`;
      }

      tip.innerHTML = `
        <div class="tooltip-date">
          <span>📅 ${row.date}</span>
          <span class="${isNormal ? 'status-pill-normal' : 'status-pill-inverted'}">${isNormal ? 'Normal Slope' : 'Inverted'}</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-label"><span class="tooltip-dot" style="background: ${info.color};"></span>${info.name}</span>
          <span class="tooltip-val" style="color: ${info.color}; font-size: 13.5px;">${val >= 0 ? '+' : ''}${val.toFixed(1)} bps</span>
        </div>
        <div class="tooltip-footer">
          <div style="font-weight: 700; color: #1d1d1f; margin-bottom: 2px;">Formula: ${info.formula}</div>
          <div style="font-size: 10px; color: #555;">Math: ${formulaMath} = ${val >= 0 ? '+' : ''}${val.toFixed(1)} bps</div>
          <div style="font-size: 10px; color: ${isNormal ? '#248a3d' : '#d70015'}; margin-top: 4px; font-weight: 600;">
            ${isNormal ? '✅ Normal: Long rates pay more than short rates' : '⚠️ Inverted: Short rates higher than long rates'}
          </div>
        </div>
      `;
    } else {
      const s2s10 = row.spread_2s10s || 0;
      const s2s30 = row.spread_2s30s || 0;
      const s5s10 = row.spread_5s10s || 0;

      tip.innerHTML = `
        <div class="tooltip-date">
          <span>📅 ${row.date}</span>
          <span class="${s2s10 >= 0 ? 'status-pill-normal' : 'status-pill-inverted'}">${s2s10 >= 0 ? 'Normal' : 'Inverted'}</span>
        </div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #0071e3;"></span>2s10s Benchmark</span><span class="tooltip-val" style="color: #0071e3;">${s2s10 >= 0 ? '+' : ''}${s2s10.toFixed(1)} bps</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #af52de;"></span>2s30s Total Slope</span><span class="tooltip-val" style="color: #af52de;">${s2s30 >= 0 ? '+' : ''}${s2s30.toFixed(1)} bps</span></div>
        <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #248a3d;"></span>5s10s Belly Slope</span><span class="tooltip-val" style="color: #248a3d;">${s5s10 >= 0 ? '+' : ''}${s5s10.toFixed(1)} bps</span></div>
        <div class="tooltip-footer">
          <div style="font-size: 10.5px; color: #555;">Inversion Barrier: <strong>0.0 bps</strong></div>
        </div>
      `;
    }
  }

  function updateYieldCurveTooltip(tenorKey, xPx, totalW) {
    const tip = document.getElementById("yieldCurveTooltip");
    if (!tip || !curveData || !curveData.snapshots) return;

    const snaps = curveData.snapshots;
    const meta = (curveData.yields && curveData.yields[tenorKey]) || {};

    tip.style.display = "block";
    tip.style.left = `${xPx}px`;
    tip.style.top = `40px`;
    const isRight = xPx > totalW * 0.65;
    tip.style.transform = isRight ? "translate(calc(-100% - 14px), 0)" : "translate(14px, 0)";

    tip.innerHTML = `
      <div class="tooltip-date">
        <span>📍 ${TENOR_LABELS[tenorKey]} (${tenorKey.toUpperCase()})</span>
        <span class="status-pill-normal">Current: ${meta.yield ? meta.yield.toFixed(2) + "%" : "—"}</span>
      </div>
      <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #0071e3;"></span>Current</span><span class="tooltip-val">${snaps.current && snaps.current[tenorKey] != null ? snaps.current[tenorKey].toFixed(2) + "%" : "—"}</span></div>
      <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #8e8e93;"></span>1M Ago</span><span class="tooltip-val">${snaps["1m_ago"] && snaps["1m_ago"][tenorKey] != null ? snaps["1m_ago"][tenorKey].toFixed(2) + "%" : "—"}</span></div>
      <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #af52de;"></span>6M Ago</span><span class="tooltip-val">${snaps["6m_ago"] && snaps["6m_ago"][tenorKey] != null ? snaps["6m_ago"][tenorKey].toFixed(2) + "%" : "—"}</span></div>
      <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #34c759;"></span>1Y Ago</span><span class="tooltip-val">${snaps["1y_ago"] && snaps["1y_ago"][tenorKey] != null ? snaps["1y_ago"][tenorKey].toFixed(2) + "%" : "—"}</span></div>
      <div class="tooltip-row"><span class="tooltip-label"><span class="tooltip-dot" style="background: #ff3b30;"></span>Inverted Peak</span><span class="tooltip-val">${snaps.peak_inversion && snaps.peak_inversion[tenorKey] != null ? snaps.peak_inversion[tenorKey].toFixed(2) + "%" : "—"}</span></div>
      <div class="tooltip-footer">
        <div><strong>Mod Duration:</strong> ${meta.duration ? meta.duration.toFixed(1) + "y" : "—"}</div>
        <div><strong>DV01:</strong> ${meta.dv01 ? "$" + meta.dv01.toFixed(1) + " / bp ($100k)" : "—"}</div>
      </div>
    `;
  }

  /* -------------------------------------------------------------
     EVENT LISTENERS INITIALIZATION
     ------------------------------------------------------------- */
  function setupEventListeners() {
    // Yield Curve series toggles
    document.querySelectorAll(".curve-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.curveKey;
        activeCurveSeries[key] = !activeCurveSeries[key];
        btn.classList.toggle("active", activeCurveSeries[key]);
        renderYieldCurveChart();
      });
    });

    // History mode toggles (Yields % vs Spreads bps)
    document.querySelectorAll(".history-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".history-mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeHistoryMode = btn.dataset.mode;
        renderHistoryChart();
      });
    });

    // History range buttons (1M, 3M, 6M, 1Y)
    document.querySelectorAll(".history-range-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".history-range-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeHistoryRange = btn.dataset.range;
        renderHistoryChart();
      });
    });

    // Spread selection buttons (2s10s, 2s30s, 5s10s, all)
    document.querySelectorAll(".spread-select-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".spread-select-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeSpreadKey = btn.dataset.spread;
        renderSpreadChart();
      });
    });

    // Spread range buttons (1M, 3M, 6M, 1Y)
    document.querySelectorAll(".spread-range-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".spread-range-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeSpreadRange = btn.dataset.range;
        renderSpreadChart();
      });
    });

    // Trade tracker desk filter buttons
    document.querySelectorAll(".tracker-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tracker-filter-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeTrackerFilter = btn.dataset.filter;
        renderTradeTracker();
      });
    });

    // Scenario buttons
    document.querySelectorAll(".scenario-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        runScenarioSimulation(btn.dataset.scenario);
      });
    });

    // Resize event
    window.addEventListener("resize", () => {
      renderYieldCurveChart();
      renderHistoryChart();
      renderSpreadChart();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadData);
  } else {
    loadData();
  }
})();
