/**
 * gbi-em-page.js - Interactive GBI-EM Sovereign Debt & FX Strategy Desk
 * Strategy Dashboard (rkarim25.github.io/Strategy)
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
    const pad = { top: 25, right: 30, bottom: 45, left: 110 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    const countries = Object.values(gbiData.countries).filter(c => c.rates.real_yield_10y > -10);
    countries.sort((a, b) => b.rates.real_yield_10y - a.rates.real_yield_10y);

    const maxVal = 9.0;
    const barHeight = chartH / countries.length;

    // Draw vertical grid lines
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

    // Draw bars
    countries.forEach((c, i) => {
      const py = pad.top + i * barHeight;
      const val = c.rates.real_yield_10y;
      const barW = Math.max(0, (chartW * val) / maxVal);

      // Country label
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "600 12px -apple-system, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(`${c.flag} ${c.name}`, pad.left - 10, py + barHeight / 2);

      // Bar
      const isHigh = val >= 5.0;
      ctx.fillStyle = isHigh ? "#248a3d" : val >= 3.0 ? "#0071e3" : "#ff9500";
      ctx.beginPath();
      ctx.roundRect(pad.left, py + 4, barW, barHeight - 8, 4);
      ctx.fill();

      // Value label
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "700 11px -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(`+${val.toFixed(2)}%`, pad.left + barW + 8, py + barHeight / 2);
    });
  }

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
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
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

        <!-- Two Columns: Rates vs FX -->
        <div class="two-col" style="margin: 14px 0 18px;">
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
                <span style="font-size: 11px; color: var(--muted); display: block;">5Y Yield</span>
                <strong style="font-size: 15px;">${c.rates.yield_5y ? c.rates.yield_5y.toFixed(2) + '%' : 'N/A'}</strong>
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

        <!-- Executive Narrative & Trade Expression -->
        <p style="font-size: 14.5px; line-height: 1.6; color: var(--text); margin-bottom: 16px;">${c.executive_summary}</p>

        <!-- Execution & Hedging Callout -->
        <div style="background: rgba(0, 113, 227, .06); border: 1px solid rgba(0, 113, 227, .2); border-radius: 16px; padding: 16px; margin-bottom: 14px;">
          <h4 style="margin: 0 0 6px; font-size: 14px; color: var(--accent);">Hedging & Execution Instruction</h4>
          <p style="margin: 0; font-size: 13.5px;"><strong>FX Recommendation:</strong> ${c.rates.hedging_recommendation}</p>
          ${c.sideways_condition ? `<p style="margin: 6px 0 0; font-size: 13px; color: var(--warn);"><strong>Sideways Rule:</strong> ${c.sideways_condition}</p>` : ''}
        </div>

        <!-- Catalysts -->
        <div>
          <span style="font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase;">Upcoming Catalysts:</span>
          <ul style="margin: 6px 0 0; padding-left: 20px; font-size: 13px; color: var(--muted);">
            ${c.catalysts.map(cat => `<li>${cat}</li>`).join('')}
          </ul>
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
