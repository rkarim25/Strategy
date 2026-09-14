/**
 * credit-page.js - Interactive Credit Derivatives Desk (CDX EM, iTraxx Xover, US HY CDX)
 * Strategy Dashboard (rkarim25.github.io/Strategy)
 */

(function () {
  "use strict";

  let creditData = null;
  let activeChartMode = "all"; // "all" or "basis"

  const INDEX_COLORS = {
    cdx_na_hy: "#ff9500",
    itraxx_xover: "#0071e3",
    cdx_em: "#34c759",
  };

  async function loadData() {
    try {
      const resp = await fetch("credit_data.json?v=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      creditData = await resp.json();
      initUI();
    } catch (e) {
      console.warn("Using fallback credit data", e);
      const fallbackEl = document.getElementById("creditFallbackData");
      if (fallbackEl) {
        try {
          creditData = JSON.parse(fallbackEl.textContent);
          initUI();
        } catch (err) {
          console.error("Fallback failed", err);
        }
      }
    }
  }

  function initUI() {
    if (!creditData) return;
    renderTopCards();
    renderExecutiveRecommendation();
    renderCreditChart();
    renderTriggers();
    renderDetailedCards();
    setupEventListeners();
  }

  function renderTopCards() {
    const indices = creditData.indices || {};
    Object.keys(indices).forEach((k) => {
      const idx = indices[k];
      const elSpread = document.getElementById(`spread_${k}`);
      const elChg = document.getElementById(`chg_${k}`);
      const elSma = document.getElementById(`sma_${k}`);
      const elPct = document.getElementById(`pct_${k}`);
      const elBar = document.getElementById(`bar_${k}`);

      if (elSpread) elSpread.textContent = `${idx.spread_bps.toFixed(1)} bps`;
      if (elChg) {
        const sign = idx.change_bps > 0 ? "+" : "";
        elChg.textContent = `1D: ${sign}${idx.change_bps.toFixed(1)} bps`;
        elChg.className = "stat-change " + (idx.change_bps > 0 ? "bad" : "good");
      }
      if (elSma) {
        elSma.textContent = `50d SMA: ${idx.sma50} · 200d: ${idx.sma200} · RSI: ${idx.rsi14}`;
      }
      if (elPct && idx.range_1y) {
        elPct.textContent = `1Y: ${idx.range_1y.percentile}th %ile (${idx.range_1y.min}-${idx.range_1y.max} bps)`;
      }
      if (elBar && idx.range_1y) {
        elBar.style.width = `${idx.range_1y.percentile}%`;
      }
    });

    const asOf = document.getElementById("creditAsOf");
    if (asOf && creditData.latest_date) {
      asOf.textContent = `As of ${creditData.latest_date} · 5-Year On-The-Run Credit Default Swap Indices`;
    }
  }

  function renderExecutiveRecommendation() {
    const execEl = document.getElementById("creditExecutiveSummary");
    if (execEl && creditData.executive_paragraph) {
      execEl.textContent = creditData.executive_paragraph;
    }
  }

  function renderTriggers() {
    const triggersContainer = document.getElementById("creditTriggersContainer");
    if (!triggersContainer || !creditData.technicals || !creditData.technicals.triggers) return;
    triggersContainer.replaceChildren();

    creditData.technicals.triggers.forEach((trg) => {
      const div = document.createElement("div");
      div.className = "trigger-card " + (trg.threshold_met ? "active-alert" : "");
      div.innerHTML = `
        <div class="trigger-header">
          <h4 class="trigger-title">${trg.title}</h4>
          <span class="trigger-status-badge ${trg.threshold_met ? 'badge-alert' : 'badge-inactive'}">${trg.status}</span>
        </div>
        <p class="trigger-condition"><strong>Trigger Condition:</strong> ${trg.condition}</p>
        <div class="trigger-action-pill"><strong>Tactical Action:</strong> ${trg.action}</div>
        <div class="trigger-metric-dist">${trg.active_metric}</div>
      `;
      triggersContainer.appendChild(div);
    });
  }

  function renderDetailedCards() {
    const container = document.getElementById("creditDetailsContainer");
    if (!container || !creditData.indices) return;
    container.replaceChildren();

    const order = ["cdx_na_hy", "itraxx_xover", "cdx_em"];
    order.forEach((k) => {
      const idx = creditData.indices[k];
      if (!idx) return;

      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "20px";
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
          <div>
            <h3 style="margin: 0; font-size: 20px;">${idx.name}</h3>
            <span style="font-size: 13px; color: var(--muted);">${idx.asset_class} · ${idx.tenor}</span>
          </div>
          <div style="display: flex; gap: 10px; align-items: center;">
            <span style="font-size: 24px; font-weight: 800;">${idx.spread_bps} bps</span>
            <span class="trade-badge" style="background: ${idx.rating.includes('Overweight') ? 'var(--good)' : 'var(--accent)'};">${idx.rating}</span>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 16px;">
          <div class="card" style="padding: 12px; background: rgba(255,255,255,.6); border-radius: 14px;">
            <div style="font-size: 11px; color: var(--muted); font-weight: 700;">DEFAULT FORECAST</div>
            <div style="font-size: 16px; font-weight: 800; margin-top: 2px;">${idx.default_rate_forecast}</div>
          </div>
          <div class="card" style="padding: 12px; background: rgba(255,255,255,.6); border-radius: 14px;">
            <div style="font-size: 11px; color: var(--muted); font-weight: 700;">DISTRESS RATIO</div>
            <div style="font-size: 16px; font-weight: 800; margin-top: 2px;">${idx.distress_ratio}</div>
          </div>
          <div class="card" style="padding: 12px; background: rgba(255,255,255,.6); border-radius: 14px;">
            <div style="font-size: 11px; color: var(--muted); font-weight: 700;">TECHNICAL STANCE</div>
            <div style="font-size: 14px; font-weight: 700; margin-top: 2px; color: var(--accent);">${idx.recommendation_stance}</div>
          </div>
        </div>

        <p style="font-size: 14.5px; line-height: 1.6; color: var(--text); margin-bottom: 16px;">${idx.rationale}</p>

        <div style="background: rgba(0, 113, 227, .06); border: 1px solid rgba(0, 113, 227, .18); border-radius: 16px; padding: 16px;">
          <h4 style="margin: 0 0 6px; font-size: 14px; color: var(--accent);">Trade Expression & Execution</h4>
          <p style="margin: 0 0 6px; font-size: 13.5px;"><strong>Expression:</strong> ${idx.trade_expression.primary_trade}</p>
          <p style="margin: 0 0 6px; font-size: 13px; color: var(--muted);"><strong>Target & Stop:</strong> ${idx.trade_expression.spread_target}</p>
          <p style="margin: 0 0 6px; font-size: 13px; color: var(--muted);"><strong>Instrument:</strong> <code>${idx.trade_expression.instrument}</code></p>
          <p style="margin: 0; font-size: 12.5px; color: var(--muted);"><strong>Catalysts:</strong> ${idx.trade_expression.catalysts}</p>
        </div>
      `;
      container.appendChild(card);
    });
  }

  function renderCreditChart() {
    const canvas = document.getElementById("creditChartCanvas");
    if (!canvas || !creditData || !creditData.history) return;
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

    const rows = creditData.history;
    let minY = Infinity;
    let maxY = -Infinity;

    if (activeChartMode === "all") {
      rows.forEach((r) => {
        minY = Math.min(minY, r.cdx_em, r.itraxx_xover, r.cdx_na_hy);
        maxY = Math.max(maxY, r.cdx_em, r.itraxx_xover, r.cdx_na_hy);
      });
      minY = Math.floor(minY / 25) * 25 - 10;
      maxY = Math.ceil(maxY / 25) * 25 + 10;
    } else {
      // Basis mode: cdx_na_hy - itraxx_xover
      rows.forEach((r) => {
        minY = Math.min(minY, r.basis_hy_xover);
        maxY = Math.max(maxY, r.basis_hy_xover);
      });
      minY = Math.floor(minY / 5) * 5 - 5;
      maxY = Math.ceil(maxY / 5) * 5 + 5;
    }

    function yToPx(val) {
      return pad.top + chartH * (1 - (val - minY) / (maxY - minY));
    }
    function xToPx(idx) {
      return pad.left + (chartW * idx) / (rows.length - 1);
    }

    // Grid lines
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
      ctx.fillText(v.toFixed(0) + " bps", pad.left - 8, py);
    }

    if (activeChartMode === "all") {
      // Draw 3 series
      const series = [
        { key: "cdx_na_hy", color: INDEX_COLORS.cdx_na_hy, label: "US HY CDX" },
        { key: "itraxx_xover", color: INDEX_COLORS.itraxx_xover, label: "iTraxx Xover" },
        { key: "cdx_em", color: INDEX_COLORS.cdx_em, label: "CDX EM" },
      ];

      series.forEach((s) => {
        ctx.beginPath();
        rows.forEach((r, i) => {
          const px = xToPx(i);
          const py = yToPx(r[s.key]);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2.5;
        ctx.stroke();
      });
    } else {
      // Basis line
      ctx.beginPath();
      rows.forEach((r, i) => {
        const px = xToPx(i);
        const py = yToPx(r.basis_hy_xover);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = "#af52de";
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }

    // Dates on X
    ctx.fillStyle = "#86868b";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const xCount = Math.min(5, rows.length);
    for (let i = 0; i < xCount; i++) {
      const idx = Math.round((i * (rows.length - 1)) / (xCount - 1));
      ctx.fillText(rows[idx].date, xToPx(idx), H - pad.bottom + 10);
    }
  }

  function setupEventListeners() {
    document.querySelectorAll(".credit-chart-mode-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".credit-chart-mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        activeChartMode = btn.dataset.mode;
        renderCreditChart();
      });
    });

    window.addEventListener("resize", renderCreditChart);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadData);
  } else {
    loadData();
  }
})();
