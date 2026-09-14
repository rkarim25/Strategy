/**
 * gbi-em-page.js - Interactive GBI-EM Sovereign Debt & FX Strategy Desk
 * Strategy Dashboard (rkarim25.github.io/Strategy)
 * Includes Geopolitical Transmission Channels, Dated Catalysts Calendar, and Live Macro Anchors.
 */

(function () {
  "use strict";

  let gbiData = null;
  let activeRegionFilter = "All";
  let activeStanceFilter = "All";

  async function loadData() {
    try {
      const resp = await fetch("gbi_em_data.json?v=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      gbiData = await resp.json();
      initUI();
    } catch (e) {
      console.warn("Using fallback GBI-EM data", e);
      const fallbackEl = document.getElementById("gbiFallbackData");
      if (fallbackEl) {
        try {
          gbiData = JSON.parse(fallbackEl.textContent);
          initUI();
        } catch (err) {
          console.error("GBI fallback failed", err);
        }
      }
    }
  }

  function initUI() {
    if (!gbiData) return;
    renderTopHeader();
    renderMacroTickers();
    renderCatalystCalendar();
    renderGeopoliticalRadar();
    renderRealYieldChart();
    renderCountryCards();
    setupFilters();
  }

  function renderTopHeader() {
    const asOf = document.getElementById("gbiAsOf");
    if (asOf && gbiData.as_of_date) {
      asOf.textContent = `As of ${gbiData.as_of_date} · J.P. Morgan GBI-EM Global Diversified Coverage`;
    }

    const execEl = document.getElementById("gbiExecutiveParagraph");
    if (execEl && gbiData.executive_paragraph) {
      execEl.textContent = gbiData.executive_paragraph;
    }
  }

  /* -------------------------------------------------------------
     GLOBAL MACRO & COMMODITY TICKERS
     ------------------------------------------------------------- */
  function renderMacroTickers() {
    const grid = document.getElementById("macroTickerGrid");
    if (!grid || !gbiData || !gbiData.macro_anchors) return;
    grid.replaceChildren();

    const icons = {
      brent_crude: "🛢️",
      copper: "⛏️",
      gold: "🪙",
      dxy_index: "💵",
      ust_10y: "📈",
    };

    const names = {
      brent_crude: "Brent Crude Oil",
      copper: "LME Copper",
      gold: "Gold Spot",
      dxy_index: "US Dollar (DXY)",
      ust_10y: "US 10Y Yield",
    };

    Object.keys(gbiData.macro_anchors).forEach((k) => {
      const it = gbiData.macro_anchors[k];
      const card = document.createElement("div");
      card.className = "macro-ticker-card";

      const chgText = it.change_1d_pct !== undefined 
        ? `${it.change_1d_pct > 0 ? '+' : ''}${it.change_1d_pct.toFixed(1)}%` 
        : `${it.change_1d_bps > 0 ? '+' : ''}${it.change_1d_bps.toFixed(1)} bps`;
      const chgCls = (it.change_1d_pct || it.change_1d_bps || 0) >= 0 ? "good" : "bad";

      card.innerHTML = `
        <div class="macro-ticker-label">
          <span>${icons[k] || '📊'} ${names[k] || k}</span>
          <span class="${chgCls}" style="font-weight: 700;">${chgText}</span>
        </div>
        <div class="macro-ticker-val">
          ${typeof it.value === "number" && it.unit === "$" ? "$" + it.value.toFixed(2) : it.value} 
          <span style="font-size: 13px; font-weight: 500; color: var(--muted);">${it.unit}</span>
        </div>
        <div class="macro-ticker-comment">${it.comment}</div>
      `;
      grid.appendChild(card);
    });
  }

  /* -------------------------------------------------------------
     UPCOMING DATED CATALYST CALENDAR
     ------------------------------------------------------------- */
  function renderCatalystCalendar() {
    const timeline = document.getElementById("catalystTimeline");
    if (!timeline || !gbiData || !gbiData.upcoming_catalysts_calendar) return;
    timeline.replaceChildren();

    gbiData.upcoming_catalysts_calendar.slice(0, 8).forEach((cat) => {
      const item = document.createElement("div");
      item.className = "catalyst-item";
      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="catalyst-date-badge">📅 ${cat.date}</span>
          <span style="font-size: 16px;">${cat.flag || '🌐'}</span>
        </div>
        <div style="font-weight: 700; font-size: 13px; color: var(--text);">${cat.event}</div>
        <div style="font-size: 11.5px; color: var(--muted);"><strong>Consensus:</strong> ${cat.consensus}</div>
        <div style="font-size: 11.5px; color: var(--accent); font-weight: 600; border-top: 1px dashed rgba(0,0,0,.08); padding-top: 5px;">
          💡 ${cat.trade_implication}
        </div>
      `;
      timeline.appendChild(item);
    });
  }

  /* -------------------------------------------------------------
     GEOPOLITICAL RADAR GRID
     ------------------------------------------------------------- */
  function renderGeopoliticalRadar() {
    const grid = document.getElementById("geopoliticalGrid");
    if (!grid || !gbiData || !gbiData.geopolitical_risk_matrix) return;
    grid.replaceChildren();

    Object.values(gbiData.geopolitical_risk_matrix).forEach((p) => {
      const col = document.createElement("div");
      col.className = "geopolitical-pillar";
      col.innerHTML = `
        <div style="font-weight: 800; font-size: 13.5px; color: var(--text); margin-bottom: 6px;">${p.title}</div>
        <div style="font-size: 11.5px; color: var(--muted); margin-bottom: 8px;">
          <strong>Macro Anchor:</strong> <code>${p.macro_metric}</code>
        </div>
        <div style="margin-bottom: 4px;">
          <span style="font-size: 11px; font-weight: 700; color: var(--good);">WINNERS:</span> 
          <span style="font-size: 12px;">${p.winners.join(", ")}</span>
        </div>
        <div style="margin-bottom: 8px;">
          <span style="font-size: 11px; font-weight: 700; color: var(--bad);">LOSERS / DEFENSE HEADWINDS:</span> 
          <span style="font-size: 12px;">${p.losers.join(", ")}</span>
        </div>
        <div style="background: rgba(0,0,0,.03); border-radius: 8px; padding: 8px 10px; font-size: 11.5px; color: var(--text);">
          <strong>Strategic Action:</strong> ${p.strategic_guidance}
        </div>
      `;
      grid.appendChild(col);
    });
  }

  /* -------------------------------------------------------------
     REAL YIELD CHART
     ------------------------------------------------------------- */
  function renderRealYieldChart() {
    const canvas = document.getElementById("realYieldCanvas");
    if (!canvas || !gbiData || !gbiData.countries) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 240 * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 240;
    const pad = { top: 25, right: 35, bottom: 45, left: 115 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const countries = Object.values(gbiData.countries).filter(c => c.rates.real_yield_10y > -10);
    countries.sort((a, b) => b.rates.real_yield_10y - a.rates.real_yield_10y);

    const maxVal = 9.0;
    const barHeight = chartH / countries.length;

    // Grid lines
    ctx.strokeStyle = "rgba(0,0,0,0.06)";
    ctx.fillStyle = "#86868b";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.textAlign = "center";
    for (let v = 0; v <= 8; v += 2) {
      const px = pad.left + (chartW * v) / maxVal;
      ctx.beginPath();
      ctx.moveTo(px, pad.top);
      ctx.lineTo(px, H - pad.bottom);
      ctx.stroke();
      ctx.fillText(v + "%", px, H - pad.bottom + 14);
    }

    // Bars
    countries.forEach((c, i) => {
      const py = pad.top + i * barHeight;
      const val = c.rates.real_yield_10y;
      const barW = Math.max(0, (chartW * val) / maxVal);

      ctx.fillStyle = "#1d1d1f";
      ctx.font = "600 12px -apple-system, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(`${c.flag} ${c.name}`, pad.left - 10, py + barHeight / 2);

      const isHigh = val >= 5.0;
      ctx.fillStyle = isHigh ? "#248a3d" : val >= 3.0 ? "#0071e3" : "#ff9500";
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(pad.left, py + 4, barW, barHeight - 8, 4);
      else ctx.rect(pad.left, py + 4, barW, barHeight - 8);
      ctx.fill();

      ctx.fillStyle = "#1d1d1f";
      ctx.font = "700 11px -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(`+${val.toFixed(2)}%`, pad.left + barW + 8, py + barHeight / 2);
    });
  }

  /* -------------------------------------------------------------
     COUNTRY CARDS WITH GEOPOLITICS & MACRO ANCHORS
     ------------------------------------------------------------- */
  function renderCountryCards() {
    const container = document.getElementById("gbiCountriesContainer");
    if (!container || !gbiData || !gbiData.countries) return;
    container.replaceChildren();

    const list = Object.values(gbiData.countries);

    const filtered = list.filter((c) => {
      if (activeRegionFilter !== "All" && c.region !== activeRegionFilter) return false;
      if (activeStanceFilter === "Overweight" && !c.rates.stance.includes("Overweight")) return false;
      if (activeStanceFilter === "Neutral" && !c.rates.stance.includes("Neutral") && !c.rates.stance.includes("Sideways")) return false;
      if (activeStanceFilter === "Underweight" && !c.rates.stance.includes("Underweight") && !c.rates.stance.includes("Avoid")) return false;
      return true;
    });

    filtered.forEach((c) => {
      const card = document.createElement("div");
      card.className = "card country-card";
      card.style.marginBottom = "24px";

      const ratesBadgeCls = c.rates.stance.includes("Overweight") ? "badge-overweight" : c.rates.stance.includes("Underweight") ? "badge-underweight" : "badge-neutral";
      const fxBadgeCls = c.fx.stance.includes("Bullish") ? "badge-overweight" : c.fx.stance.includes("Bearish") ? "badge-underweight" : "badge-neutral";

      const geo = c.geopolitics || {};
      const mac = c.macro_anchors || {};

      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; border-bottom: 1px solid var(--line); padding-bottom: 14px;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 26px;">${c.flag}</span>
              <h2 style="margin: 0; font-size: 24px;">${c.name} (${c.currency})</h2>
              <span style="font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 999px; background: rgba(0,0,0,.06);">${c.region}</span>
            </div>
            <div style="font-size: 13px; color: var(--muted); margin-top: 4px;">Rating: <strong>${c.credit_rating}</strong></div>
          </div>
          <div style="display: flex; gap: 12px; flex-wrap: wrap;">
            <div style="text-align: right;">
              <div style="font-size: 11px; color: var(--muted); font-weight: 700;">10Y REAL YIELD</div>
              <div style="font-size: 20px; font-weight: 800; color: ${c.rates.real_yield_10y > 4 ? 'var(--good)' : 'var(--text)'};">${c.rates.real_yield_10y > 0 ? '+' : ''}${c.rates.real_yield_10y.toFixed(2)}%</div>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 11px; color: var(--muted); font-weight: 700;">10Y NOMINAL</div>
              <div style="font-size: 20px; font-weight: 800;">${c.rates.yield_10y.toFixed(2)}%</div>
            </div>
          </div>
        </div>

        <!-- Macro Telemetry Chips -->
        <div class="macro-chips-row">
          ${mac.net_oil_exposure ? `<span class="macro-chip">🛢️ ${mac.net_oil_exposure}</span>` : ''}
          ${mac.fx_reserves_bn ? `<span class="macro-chip">🛡️ Reserves: ${mac.fx_reserves_bn}</span>` : ''}
          ${mac.current_account_pct_gdp ? `<span class="macro-chip">⚖️ CA: ${mac.current_account_pct_gdp}</span>` : ''}
          ${mac.fiscal_deficit_pct_gdp ? `<span class="macro-chip">🏛️ Deficit: ${mac.fiscal_deficit_pct_gdp}</span>` : ''}
        </div>

        <!-- Two Columns: Rates vs FX -->
        <div class="two-col" style="margin: 14px 0 16px;">
          <!-- Rates View -->
          <div style="background: rgba(255,255,255,.65); border: 1px solid var(--line); border-radius: 18px; padding: 18px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <h4 style="margin: 0; font-size: 15px;">Local Rates & Duration</h4>
              <span class="stance-badge ${ratesBadgeCls}">${c.rates.stance}</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">Policy Rate</span>
                <strong style="font-size: 15px;">${c.rates.policy_rate.toFixed(2)}%</strong>
              </div>
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">Headline CPI</span>
                <strong style="font-size: 15px;">${c.rates.cpi_yoy.toFixed(2)}%</strong>
              </div>
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">Ex-Ante Real</span>
                <strong style="font-size: 15px; color: var(--good);">+${c.rates.ex_ante_real_rate.toFixed(2)}%</strong>
              </div>
            </div>
            <div style="font-size: 13px; margin-bottom: 4px;"><strong>Target Point:</strong> ${c.rates.curve_point}</div>
            <div style="font-size: 12.5px; color: var(--muted);"><strong>Instrument:</strong> <code>${c.rates.instrument}</code></div>
          </div>

          <!-- FX View -->
          <div style="background: rgba(255,255,255,.65); border: 1px solid var(--line); border-radius: 18px; padding: 18px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <h4 style="margin: 0; font-size: 15px;">Currency & Carry (${c.fx.pair})</h4>
              <span class="stance-badge ${fxBadgeCls}">${c.fx.stance}</span>
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">Spot Rate</span>
                <strong style="font-size: 15px;">${c.fx.spot.toLocaleString()}</strong>
              </div>
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">3M Carry (ann)</span>
                <strong style="font-size: 15px; color: var(--good);">+${c.fx.carry_3m_ann.toFixed(1)}%</strong>
              </div>
              <div>
                <span style="font-size: 11px; color: var(--muted); display: block;">REER Valuation</span>
                <strong style="font-size: 14px;">${c.fx.reer_valuation}</strong>
              </div>
            </div>
            <div style="font-size: 12.5px; color: var(--muted);">50d SMA: ${c.fx.sma50} · 200d: ${c.fx.sma200} · RSI: ${c.fx.rsi14}</div>
          </div>
        </div>

        <!-- Geopolitical Drivers & Direct Trade Influence Box -->
        ${geo.headline_theme ? `
        <div class="country-geopolitics-box">
          <div class="country-geopolitics-title">
            <span>🌐 Geopolitical Driver & Trade Influence:</span>
            <span>${geo.headline_theme}</span>
          </div>
          <p style="margin: 0 0 8px; font-size: 13px; line-height: 1.5; color: var(--text);">
            <strong>Transmission Channel:</strong> ${geo.transmission_channel}
          </p>
          <div style="background: rgba(255,255,255,.9); border-left: 3px solid #6a1b9a; padding: 8px 12px; border-radius: 8px; font-size: 13px; color: var(--text);">
            <strong>Trade Recommendation Impact:</strong> ${geo.trade_influence}
          </div>
        </div>
        ` : ''}

        <!-- Executive Narrative & Trade Expression -->
        <p style="font-size: 14.5px; line-height: 1.6; color: var(--text); margin-bottom: 14px;">${c.executive_summary}</p>

        <!-- Execution & Hedging Callout -->
        <div style="background: rgba(0, 113, 227, .06); border: 1px solid rgba(0, 113, 227, .2); border-radius: 16px; padding: 16px; margin-bottom: 14px;">
          <h4 style="margin: 0 0 6px; font-size: 14px; color: var(--accent);">Hedging & Execution Directive</h4>
          <p style="margin: 0; font-size: 13.5px;"><strong>Expression Vehicle:</strong> ${c.rates.hedging_recommendation}</p>
          ${c.sideways_condition ? `<p style="margin: 6px 0 0; font-size: 13px; color: var(--warn);"><strong>Sideways Rule:</strong> ${c.sideways_condition}</p>` : ''}
        </div>

        <!-- Dated Upcoming Catalysts -->
        <div>
          <span style="font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase;">Upcoming Dated Catalysts:</span>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-top: 8px;">
            ${(c.catalysts || []).map(cat => `
              <div style="background: rgba(0,0,0,.025); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                  <strong style="font-size: 12.5px; color: var(--text);">${cat.event}</strong>
                  <span class="catalyst-date-badge">${cat.date}</span>
                </div>
                <div style="font-size: 11.5px; color: var(--muted); margin-bottom: 3px;">Consensus: ${cat.consensus}</div>
                <div style="font-size: 11.5px; color: var(--accent); font-weight: 600;">Action: ${cat.trade_implication}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  }

  function setupFilters() {
    document.querySelectorAll(".region-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".region-filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeRegionFilter = btn.dataset.region;
        renderCountryCards();
      });
    });

    document.querySelectorAll(".stance-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".stance-filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeStanceFilter = btn.dataset.stance;
        renderCountryCards();
      });
    });

    window.addEventListener("resize", renderRealYieldChart);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadData);
  } else {
    loadData();
  }
})();
