/**
 * gbi-em-page.js - Interactive GBI-EM Sovereign Debt & FX Strategy Desk
 * Full institutional dashboard: Real rates breakdown, ToT-REER matrix, live trade tracking,
 * geopolitical risk transmission channels, dated central bank catalysts, and interactive canvas charts.
 */

(function () {
  let gbiData = null;
  let activeRegionFilter = "All";
  let activeStanceFilter = "All";
  let activeTrackerFilter = "all";

  async function loadData() {
    try {
      const resp = await fetch("gbi_em_data.json?v=" + Date.now());
      if (!resp.ok) throw new Error("HTTP error " + resp.status);
      gbiData = await resp.json();
    } catch (e) {
      console.warn("Falling back to embedded gbiFallbackData", e);
      const el = document.getElementById("gbiFallbackData");
      if (el) {
        gbiData = JSON.parse(el.textContent);
      }
    }

    if (!gbiData) {
      console.error("No GBI-EM data available.");
      return;
    }

    initUI();
  }

  function initUI() {
    renderTopHeader();
    renderMacroTickers();
    renderCatalystCalendar();
    renderGeopoliticalRadar();
    renderRealYieldChart();
    renderRealRatesTable();
    renderRatesExecutionTable();
    renderTotReerMatrix();
    renderTradeTracker();
    renderCountryCards();
    setupFilters();
    setupTrackerFilters();
  }

  function renderTopHeader() {
    const meta = document.getElementById("gbiAsOf") || document.getElementById("gbiAsOfMeta");
    if (meta && gbiData.as_of_date) {
      meta.textContent = `As of ${gbiData.as_of_date} · Benchmark: ${gbiData.benchmark || 'J.P. Morgan GBI-EM Global Diversified'}`;
    }

    const execEl = document.getElementById("gbiExecutiveParagraph") || document.getElementById("executiveParagraph");
    if (execEl && gbiData.executive_paragraph) {
      execEl.innerHTML = gbiData.executive_paragraph;
    }

    // Top pick badge
    const topPickEl = document.getElementById("topPickHeadline");
    if (topPickEl && gbiData.rankings) {
      const topOvw = (gbiData.rankings.rates_overweight || [])[0];
      if (topOvw) {
        topPickEl.innerHTML = `<strong>Top Conviction:</strong> Overweight <strong>${topOvw}</strong> (High real rate cushion + expanding terms of trade).`;
      }
    }
  }

  function renderMacroTickers() {
    const container = document.getElementById("macroTickerGrid");
    if (!container || !gbiData.macro_anchors) return;

    const anchors = gbiData.macro_anchors;

    function getAnchorVal(item, fallback) {
      if (!item) return fallback;
      if (typeof item === "object") {
        const v = item.value !== undefined ? item.value : '';
        const u = item.unit || '';
        return `${v} ${u}`.trim() || fallback;
      }
      return String(item) || fallback;
    }

    function getAnchorComment(item, fallback) {
      if (item && typeof item === "object" && item.comment) return item.comment;
      return fallback;
    }

    const items = [
      {
        label: "Brent Crude Oil",
        val: getAnchorVal(anchors.brent_crude, "$74.20/bbl"),
        comment: getAnchorComment(anchors.brent_crude, "EM terms of trade driver"),
        icon: "🛢️"
      },
      {
        label: "LME Copper",
        val: getAnchorVal(anchors.copper, "$4.22/lb"),
        comment: getAnchorComment(anchors.copper, "Industrial activity proxy"),
        icon: "⛏️"
      },
      {
        label: "Spot Gold",
        val: getAnchorVal(anchors.gold, "$2,580/oz"),
        comment: getAnchorComment(anchors.gold, "Safe haven & reserve asset"),
        icon: "🥇"
      },
      {
        label: "US Dollar Index (DXY)",
        val: getAnchorVal(anchors.dxy_index, "101.40"),
        comment: getAnchorComment(anchors.dxy_index, "Dollar funding pressure"),
        icon: "💵"
      },
      {
        label: "US 10Y Benchmark",
        val: getAnchorVal(anchors.ust_10y, "4.96%"),
        comment: getAnchorComment(anchors.ust_10y, "Global risk-free hurdle rate"),
        icon: "📈"
      }
    ];

    container.replaceChildren();
    items.forEach(it => {
      const card = document.createElement("div");
      card.className = "macro-ticker-card";
      card.innerHTML = `
        <div class="macro-ticker-label">
          <span>${it.label}</span>
          <span>${it.icon}</span>
        </div>
        <div class="macro-ticker-val">${it.val}</div>
        <div class="macro-ticker-comment">${it.comment}</div>
      `;
      container.appendChild(card);
    });
  }

  function renderCatalystCalendar() {
    const container = document.getElementById("catalystTimeline");
    if (!container || !gbiData.upcoming_catalysts_calendar) return;

    container.replaceChildren();
    gbiData.upcoming_catalysts_calendar.forEach(item => {
      const el = document.createElement("div");
      el.className = "catalyst-item";
      el.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="catalyst-date-badge">${item.date}</span>
          <span style="font-size: 11px; font-weight: 700; color: var(--muted);">${item.country}</span>
        </div>
        <strong style="font-size: 13px; color: var(--text); line-height: 1.35;">${item.event}</strong>
        <div style="font-size: 12px; color: var(--muted);"><strong>Consensus:</strong> ${item.consensus}</div>
        <div style="font-size: 12px; color: var(--accent); font-weight: 600; line-height: 1.35;"><strong>Impact:</strong> ${item.trade_impact}</div>
      `;
      container.appendChild(el);
    });
  }

  function renderGeopoliticalRadar() {
    const container = document.getElementById("geopoliticalGrid");
    if (!container || !gbiData.geopolitical_risk_matrix) return;

    container.replaceChildren();
    const pillars = Array.isArray(gbiData.geopolitical_risk_matrix)
      ? gbiData.geopolitical_risk_matrix
      : Object.values(gbiData.geopolitical_risk_matrix || {});

    pillars.forEach(p => {
      const el = document.createElement("div");
      el.className = "geopolitical-pillar";
      el.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <strong style="font-size: 14px; color: var(--text);">${p.theme || p.title || 'Risk Pillar'}</strong>
          <span style="font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: rgba(215, 0, 21, .12); color: var(--bad);">${p.impact_level || 'High'} Impact</span>
        </div>
        <div style="font-size: 12.5px; color: var(--muted); margin-bottom: 6px;"><strong>Transmission:</strong> ${p.transmission_channel || p.description || ''}</div>
        <div style="font-size: 12.5px; color: var(--accent); font-weight: 600;"><strong>Direct Trade Influence:</strong> ${p.market_implication || p.trade_influence || ''}</div>
      `;
      container.appendChild(el);
    });
  }

  function renderRealYieldChart() {
    const canvas = document.getElementById("realYieldCanvas");
    if (!canvas || !gbiData.countries) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = 240 * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = 240;
    ctx.clearRect(0, 0, width, height);

    const countries = Object.values(gbiData.countries);
    if (!countries.length) return;

    // Filter out extreme outliers like Turkey trailing CPI if negative for chart scaling
    const sorted = [...countries].sort((a, b) => (b.rates.ex_ante_real_rate || b.rates.real_yield_10y) - (a.rates.ex_ante_real_rate || a.rates.real_yield_10y));

    const paddingLeft = 110;
    const paddingRight = 40;
    const paddingTop = 20;
    const paddingBottom = 30;
    const chartWidth = width - paddingLeft - paddingRight;
    const chartHeight = height - paddingTop - paddingBottom;

    const maxVal = 10.0;
    const minVal = -2.0;

    const barHeight = Math.max(16, (chartHeight / sorted.length) - 8);

    sorted.forEach((c, idx) => {
      const y = paddingTop + idx * (chartHeight / sorted.length);
      const val = c.rates.ex_ante_real_rate !== undefined ? c.rates.ex_ante_real_rate : c.rates.real_yield_10y;

      // Label
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "600 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(`${c.flag || ''} ${c.name || c.country || c.id}`, paddingLeft - 10, y + barHeight / 2);

      // Zero line
      const zeroX = paddingLeft + ((0 - minVal) / (maxVal - minVal)) * chartWidth;
      const valX = paddingLeft + ((Math.min(maxVal, Math.max(minVal, val)) - minVal) / (maxVal - minVal)) * chartWidth;

      // Draw zero axis line
      ctx.strokeStyle = "rgba(0,0,0,0.15)";
      ctx.beginPath();
      ctx.moveTo(zeroX, paddingTop);
      ctx.lineTo(zeroX, height - paddingBottom);
      ctx.stroke();

      // Bar
      const isPositive = val >= 0;
      const barX = isPositive ? zeroX : valX;
      const barW = Math.abs(valX - zeroX);

      ctx.fillStyle = isPositive ? "rgba(36, 138, 61, 0.85)" : "rgba(215, 0, 21, 0.85)";
      ctx.beginPath();
      ctx.roundRect(barX, y, Math.max(2, barW), barHeight, 4);
      ctx.fill();

      // Value text
      ctx.fillStyle = "#1d1d1f";
      ctx.font = "700 11.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.textAlign = isPositive ? "left" : "right";
      const textX = isPositive ? valX + 6 : valX - 6;
      ctx.fillText(`${val > 0 ? '+' : ''}${val.toFixed(2)}%`, textX, y + barHeight / 2);
    });

    // Axis label
    ctx.fillStyle = "#86868b";
    ctx.font = "500 10.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Ex-Ante Real Policy Rate (%) = Nominal Policy Rate − 12M Forward Expected CPI", paddingLeft + chartWidth / 2, height - 8);
  }

  function renderRealRatesTable() {
    const tbody = document.getElementById("realRatesTableBody");
    if (!tbody || !gbiData.countries) return;

    tbody.replaceChildren();

    const countries = Object.values(gbiData.countries);
    countries.forEach(c => {
      const rr = c.real_rate_breakdown || {};
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      const exAntePolicy = rr.ex_ante_real_policy_rate !== undefined ? rr.ex_ante_real_policy_rate : (c.rates.policy_rate - 3.5);
      const exAnte10Y = rr.ex_ante_real_yield_10y !== undefined ? rr.ex_ante_real_yield_10y : (c.rates.yield_10y - 3.5);

      let cushionBadge = '<span class="cushion-badge cushion-tight">Tight / Vulnerable</span>';
      if (exAntePolicy >= 6.0) {
        cushionBadge = '<span class="cushion-badge cushion-elite">Elite Cushion (+600bps+)</span>';
      } else if (exAntePolicy >= 3.5) {
        cushionBadge = '<span class="cushion-badge cushion-strong">Strong Cushion (+350bps+)</span>';
      } else if (exAntePolicy >= 2.0) {
        cushionBadge = '<span class="cushion-badge cushion-moderate">Moderate (+200bps+)</span>';
      }

      tr.innerHTML = `
        <td style="padding: 12px 10px; font-weight: 700; white-space: nowrap;">
          <a href="gbi_country.html?c=${c.id}" style="color: inherit; text-decoration: none;" title="Open ${c.name || c.country || c.id} Sovereign One-Pager">
            ${c.flag || ''} ${c.name || c.country || c.id} <span style="font-size: 11px; color: var(--accent);">↗</span>
          </a>
          <div style="font-size: 11px; font-weight: 500; color: var(--muted);">${c.currency}</div>
        </td>
        <td style="padding: 12px 10px;">
          <strong style="font-size: 14px;">${rr.policy_rate ? rr.policy_rate.toFixed(2) : c.rates.policy_rate.toFixed(2)}%</strong>
          <div style="font-size: 11px; color: var(--muted);">${rr.policy_rate_name || 'Central Bank Policy Rate'}</div>
        </td>
        <td style="padding: 12px 10px;">
          <span style="font-size: 13.5px; font-weight: 600;">${rr.trailing_cpi_yoy ? rr.trailing_cpi_yoy.toFixed(2) : c.rates.cpi_yoy.toFixed(2)}%</span>
          <div style="font-size: 10.5px; color: var(--muted);">Trailing 12M YoY</div>
        </td>
        <td style="padding: 12px 10px;">
          <strong style="font-size: 13.5px; color: var(--text);">${rr.forward_inflation_12m ? rr.forward_inflation_12m.toFixed(2) : '3.80'}%</strong>
          <div style="font-size: 11px; color: var(--muted);">${rr.forward_inflation_source || 'Central Bank Survey (12M Ahead)'}</div>
        </td>
        <td style="padding: 12px 10px; background: rgba(0, 113, 227, 0.04);">
          <strong style="font-size: 15px; color: var(--good);">${exAntePolicy > 0 ? '+' : ''}${exAntePolicy.toFixed(2)}%</strong>
          <div style="font-size: 10.5px; color: var(--accent); font-family: monospace; margin-top: 2px;">
            ${rr.ex_ante_math || `${c.rates.policy_rate.toFixed(2)}% − ${(rr.forward_inflation_12m || 3.8).toFixed(2)}%`}
          </div>
        </td>
        <td style="padding: 12px 10px;">
          <strong style="font-size: 14px;">${rr.yield_10y_nominal ? rr.yield_10y_nominal.toFixed(2) : c.rates.yield_10y.toFixed(2)}%</strong>
          <div style="font-size: 11px; color: var(--muted);">10Y Benchmark</div>
        </td>
        <td style="padding: 12px 10px; background: rgba(52, 199, 89, 0.04);">
          <strong style="font-size: 15px; color: ${exAnte10Y > 4 ? 'var(--good)' : 'var(--text)'};">${exAnte10Y > 0 ? '+' : ''}${exAnte10Y.toFixed(2)}%</strong>
          <div style="font-size: 10.5px; color: var(--good); font-family: monospace; margin-top: 2px;">
            ${(rr.yield_10y_nominal || c.rates.yield_10y).toFixed(2)}% − ${(rr.forward_inflation_12m || 3.8).toFixed(2)}%
          </div>
        </td>
        <td style="padding: 12px 10px;">
          ${cushionBadge}
        </td>
      `;
      tbody.appendChild(tr);
    });
  }


  function renderRatesExecutionTable() {
    const tbody = document.getElementById("ratesExecutionTableBody");
    if (!tbody || !gbiData.rates_pay_receive_matrix) return;

    tbody.replaceChildren();

    gbiData.rates_pay_receive_matrix.forEach(r => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      let dirBadgeCls = "directive-receive";
      if (r.directive.toLowerCase().includes("pay fixed") || r.directive.toLowerCase().includes("underweight")) {
        dirBadgeCls = "directive-pay";
      } else if (r.directive.toLowerCase().includes("flattener") || r.directive.toLowerCase().includes("steepener") || r.directive.toLowerCase().includes("curve")) {
        dirBadgeCls = "directive-spread";
      } else if (r.directive.toLowerCase().includes("front-end") || r.directive.toLowerCase().includes("clip")) {
        dirBadgeCls = "directive-cash";
      }

      let tierCls = "tier-1";
      if (r.liquidity_tier.includes("Tier 2")) tierCls = "tier-2";
      if (r.liquidity_tier.includes("Tier 3")) tierCls = "tier-3";

      tr.innerHTML = `
        <td style="padding: 12px 10px; font-weight: 700; white-space: nowrap;">
          <a href="gbi_country.html?c=${r.id}" style="color: inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;" title="Open ${r.country} Sovereign Dossier ↗">
            ${r.flag || ''} ${r.country} <span style="font-size: 10px; color: var(--accent);">↗</span>
          </a>
          <div style="font-size: 11px; font-weight: 500; color: var(--muted);">${r.currency}</div>
        </td>
        <td style="padding: 12px 10px;">
          <span class="directive-badge ${dirBadgeCls}">${r.directive}</span>
        </td>
        <td style="padding: 12px 10px;">
          <strong style="font-size: 13.5px; color: var(--text);">${r.swap_instrument}</strong>
        </td>
        <td style="padding: 12px 10px;">
          <span style="font-size: 12.5px; color: var(--text); font-weight: 600;">${r.cash_instrument}</span>
        </td>
        <td style="padding: 12px 10px;">
          <span class="tier-badge ${tierCls}">${r.liquidity_tier.split('(')[0].trim()}</span>
          <div style="font-size: 11px; color: var(--muted); margin-top: 3px;"><strong>Clip:</strong> ${r.standard_clip}</div>
        </td>
        <td style="padding: 12px 10px;">
          <div style="font-size: 12.5px; font-weight: 600;">${r.bid_ask_spread}</div>
          <div style="font-size: 11px; color: var(--muted);">${r.clearing_venue}</div>
        </td>
        <td style="padding: 12px 10px; font-size: 12.5px; line-height: 1.4;">
          <strong style="color: var(--accent);">${r.dv01_sizing}</strong>
          <div style="font-size: 11.5px; color: var(--muted); margin-top: 2px;">${r.recommended_notional}</div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderTotReerMatrix() {
    const grid = document.getElementById("totQuadrantGrid");
    const tbody = document.getElementById("totReerTableBody");
    if (!grid || !tbody) return;

    // Render 5 Quadrant Boxes
    grid.replaceChildren();
    const quadrants = gbiData.tot_reer_quadrant_matrix || [];
    quadrants.forEach(q => {
      const box = document.createElement("div");
      box.className = "quadrant-box active-q";
      box.innerHTML = `
        <div class="quadrant-title">${q.quadrant}</div>
        <div class="quadrant-theme">${q.theme}</div>
        <div style="font-size: 12px; font-weight: 700; color: var(--text); margin-top: 4px;">
          Countries: <span style="color: var(--accent);">${(q.countries || []).join(', ')}</span>
        </div>
        <div style="font-size: 11.5px; color: var(--muted); line-height: 1.35; margin-top: 2px;">
          <strong>Macro Driver:</strong> ${q.macro_driver}
        </div>
        <div class="quadrant-directive">
          <strong>Strategic Trade Directive:</strong> ${q.trade_directive}
        </div>
      `;
      grid.appendChild(box);
    });

    // Render Country Table Rows
    tbody.replaceChildren();
    const countries = Object.values(gbiData.countries || {});
    countries.forEach(c => {
      const tot = c.tot_reer_framework || {};
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      const dev = tot.reer_deviation_pct !== undefined ? tot.reer_deviation_pct : 0;
      const isUndervalued = dev < -3.0;
      const isOvervalued = dev > 3.0;
      const valColor = isUndervalued ? "var(--good)" : isOvervalued ? "var(--bad)" : "var(--muted)";
      const valTag = isUndervalued ? "Cheap / Undervalued" : isOvervalued ? "Rich / Overvalued" : "Fair Value";

      tr.innerHTML = `
        <td style="padding: 12px 10px; font-weight: 700; white-space: nowrap;">
          <a href="gbi_country.html?c=${c.id}" style="color: inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;" title="Open ${c.name || c.country || c.id} Sovereign Dossier ↗">
            ${c.flag || ''} ${c.name || c.country || c.id} <span style="font-size: 10px; color: var(--accent);">↗</span>
          </a>
          <div style="font-size: 11px; font-weight: 500; color: var(--muted);">${c.fx ? c.fx.pair : c.currency}</div>
        </td>
        <td style="padding: 12px 10px;">
          <strong style="font-size: 14px; color: ${valColor};">${dev > 0 ? '+' : ''}${dev.toFixed(1)}%</strong>
          <div style="font-size: 11px; color: ${valColor}; font-weight: 600;">${valTag}</div>
        </td>
        <td style="padding: 12px 10px;">
          <div style="font-weight: 600; font-size: 13px;">${tot.terms_of_trade_trend || 'Resilient'}</div>
          <div style="font-size: 11px; color: var(--muted);">ToT Index: ${tot.terms_of_trade_index || 100}</div>
        </td>
        <td style="padding: 12px 10px;">
          <span style="font-size: 13px; font-weight: 600;">${tot.current_account_pct_gdp !== undefined ? tot.current_account_pct_gdp.toFixed(1) + '%' : 'N/A'}</span>
          <div style="font-size: 10.5px; color: var(--muted);">Current Account % GDP</div>
        </td>
        <td style="padding: 12px 10px;">
          <span style="font-size: 13px; font-weight: 600;">$${tot.fx_reserves_bn || 0}B</span>
          <div style="font-size: 11px; color: var(--muted);">${tot.import_cover_months || 0} mo import cover</div>
        </td>
        <td style="padding: 12px 10px;">
          <span class="desk-tag">${tot.quadrant_name ? tot.quadrant_name.split(':')[0] : 'Quadrant'}</span>
        </td>
        <td style="padding: 12px 10px; font-size: 12.5px; line-height: 1.4;">
          <strong>${tot.framework_recommendation || c.rates.stance}</strong>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderTradeTracker() {
    const summaryBar = document.getElementById("trackerSummaryBar");
    const tbody = document.getElementById("trackerTableBody");
    if (!summaryBar || !tbody) return;

    const tracker = gbiData.trade_tracker || {
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
      { label: "Cumulative MTM (bps/pips)", val: `${signBps}${(summary.total_pnl_bps || 0).toFixed(1)} pts`, sub: "Aggregate Basis Points", cls: pnlCls },
      { label: "Mark-to-Market P&L", val: `${signUsd}$${Math.abs(summary.total_pnl_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, sub: "Live Unrealized + Realized", cls: pnlCls },
    ];

    stats.forEach(st => {
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

    filteredTrades.forEach(t => {
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid var(--line)";

      const pnlBps = t.pnl_bps !== undefined ? t.pnl_bps : 0;
      const pnlUsd = t.pnl_usd !== undefined ? t.pnl_usd : 0;
      const signB = pnlBps > 0 ? "+" : "";
      const signU = pnlUsd > 0 ? "+" : "";
      const pCls = pnlUsd >= 0 ? "good" : "bad";

      const badgeCls = t.status === "OPEN" ? "badge-open" : t.status === "TARGET_HIT" ? "badge-hit" : "badge-stopped";

      tr.innerHTML = `
        <td style="padding: 12px 10px; font-weight: 500; font-size: 12px; color: var(--muted); white-space: nowrap;">${t.date_opened}</td>
        <td style="padding: 12px 10px;">
          <div style="font-weight: 700; color: var(--text);">${t.title}</div>
          <div style="font-size: 12px; color: var(--muted); margin-top: 2px;">${t.rationale}</div>
        </td>
        <td style="padding: 12px 10px;"><span class="desk-tag">${t.desk}</span></td>
        <td style="padding: 12px 10px;">
          <div style="font-weight: 600;">${t.instrument}</div>
          <div style="font-size: 11.5px; color: var(--muted);">${t.sizing}</div>
        </td>
        <td style="padding: 12px 10px; font-weight: 600;">${t.entry_level}</td>
        <td style="padding: 12px 10px; font-weight: 700; color: var(--text);">${t.current_level}</td>
        <td style="padding: 12px 10px; font-size: 12px;">
          <span style="color: var(--good); font-weight: 600;">T: ${t.target_level !== undefined ? t.target_level : (t.target || 'N/A')}</span><br>
          <span style="color: var(--bad); font-size: 11px;">S: ${t.stop_loss_level !== undefined ? t.stop_loss_level : (t.stop_loss || 'N/A')}</span>
        </td>
        <td style="padding: 12px 10px; font-weight: 700; font-size: 13.5px;" class="${pCls}">
          ${signB}${pnlBps.toFixed(1)}
        </td>
        <td style="padding: 12px 10px; font-weight: 700; font-size: 13.5px;" class="${pCls}">
          ${signU}$${Math.abs(pnlUsd).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
        </td>
        <td style="padding: 12px 10px;">
          <span class="${badgeCls}">${t.status}</span>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  function setupTrackerFilters() {
    document.querySelectorAll(".tracker-filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tracker-filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeTrackerFilter = btn.dataset.filter;
        renderTradeTracker();
      });
    });
  }

  function renderCountryCards() {
    const container = document.getElementById("gbiCountriesContainer");
    if (!container || !gbiData.countries) return;

    container.replaceChildren();

    const countries = Object.values(gbiData.countries);

    const filtered = countries.filter(c => {
      const matchRegion = activeRegionFilter === "All" || c.region === activeRegionFilter;
      let matchStance = true;
      if (activeStanceFilter === "Overweight") matchStance = c.rates.stance.toLowerCase().includes("overweight");
      if (activeStanceFilter === "Underweight") matchStance = c.rates.stance.toLowerCase().includes("underweight");
      if (activeStanceFilter === "Neutral") matchStance = c.rates.stance.toLowerCase().includes("neutral") || c.rates.stance.toLowerCase().includes("sideways");
      return matchRegion && matchStance;
    });

    if (filtered.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--muted);">No countries match the selected filters.</div>`;
      return;
    }

    filtered.forEach(c => {
      const card = document.createElement("div");
      card.className = "country-card card";
      card.style.marginBottom = "24px";

      const ratesBadgeCls = c.rates.stance.toLowerCase().includes("overweight")
        ? "badge-overweight"
        : c.rates.stance.toLowerCase().includes("underweight")
          ? "badge-underweight"
          : "badge-neutral";

      const fxBadgeCls = c.fx.stance.toLowerCase().includes("bullish") || c.fx.stance.toLowerCase().includes("carry") || c.fx.stance.toLowerCase().includes("long")
        ? "badge-overweight"
        : c.fx.stance.toLowerCase().includes("bearish") || c.fx.stance.toLowerCase().includes("depreciation")
          ? "badge-underweight"
          : "badge-neutral";

      const geo = c.geopolitics || {};
      const mac = c.macro_anchors || {};
      const rr = c.real_rate_breakdown || {};
      const tot = c.tot_reer_framework || {};

      card.innerHTML = `
        <!-- Header -->
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 14px;">
          <div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="font-size: 32px;">${c.flag || ''}</span>
              <div>
                <h3 style="margin: 0; font-size: 24px; font-weight: 800;">${c.name || c.country || c.id}</h3>
                <span style="font-size: 13px; color: var(--muted);">${c.currency} · ${c.region} · Credit: <strong>${c.credit_rating}</strong></span>
              </div>
            </div>
          </div>
          <div style="display: flex; gap: 16px;">
            <div style="text-align: right;">
              <div style="font-size: 11px; color: var(--muted); font-weight: 700;">10Y REAL YIELD (EX-POST)</div>
              <div style="font-size: 20px; font-weight: 800; color: ${c.rates.real_yield_10y > 4 ? 'var(--good)' : 'var(--text)'};">${c.rates.real_yield_10y > 0 ? '+' : ''}${c.rates.real_yield_10y.toFixed(2)}%</div>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 11px; color: var(--muted); font-weight: 700;">10Y NOMINAL</div>
              <div style="font-size: 20px; font-weight: 800;">${c.rates.yield_10y.toFixed(2)}%</div>
            </div>
          </div>
        </div>

        <!-- Real Rate Arithmetic Banner -->
        <div style="background: rgba(0, 113, 227, 0.05); border: 1px solid rgba(0, 113, 227, 0.2); border-radius: 12px; padding: 12px 16px; margin: 12px 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
            <span style="font-size: 11.5px; font-weight: 800; color: var(--accent); text-transform: uppercase;">📐 Real Rate Calculation & Forward Inflation:</span>
            <span style="font-size: 11.5px; font-weight: 600; color: var(--muted);">${rr.forward_inflation_source || 'Central Bank 12M Survey'}</span>
          </div>
          <div style="font-size: 13.5px; font-weight: 700; color: var(--text); margin-top: 5px;">
            Policy Rate: <code>${(rr.policy_rate || c.rates.policy_rate).toFixed(2)}%</code> (${rr.policy_rate_name || 'Policy Rate'}) − 12M Forward CPI: <code>${(rr.forward_inflation_12m || 3.8).toFixed(2)}%</code> = <span style="color: var(--good); font-size: 14.5px;">+${(rr.ex_ante_real_policy_rate || c.rates.ex_ante_real_rate).toFixed(2)}% Ex-Ante Real Rate</span>
          </div>
        </div>

        <!-- Terms of Trade & REER Strategic Directive Banner -->
        <div style="background: rgba(36, 138, 61, 0.05); border: 1px solid rgba(36, 138, 61, 0.2); border-radius: 12px; padding: 12px 16px; margin: 12px 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
            <span style="font-size: 11.5px; font-weight: 800; color: var(--good); text-transform: uppercase;">🏛️ Terms of Trade & REER Framework Directive:</span>
            <span style="font-size: 11.5px; font-weight: 700; color: var(--accent);">${tot.quadrant_name || 'BEER/FEER Quadrant'}</span>
          </div>
          <div style="font-size: 13px; color: var(--text); margin-top: 4px; line-height: 1.45;">
            <strong>REER:</strong> ${tot.reer_valuation_tag || c.fx.reer_valuation} · <strong>ToT:</strong> ${tot.terms_of_trade_trend || 'Resilient'} · <strong>Directive:</strong> ${tot.framework_recommendation || c.rates.stance}
          </div>
        </div>

        <!-- Macro Telemetry Chips -->
        <div class="macro-chips-row">
          ${mac.net_oil_exposure ? `<span class="macro-chip">🛢️ ${mac.net_oil_exposure}</span>` : ''}
          ${mac.fx_reserves_bn ? `<span class="macro-chip">🛡️ Reserves: ${mac.fx_reserves_bn}</span>` : ''}
          ${mac.current_account_pct_gdp ? `<span class="macro-chip">⚖️ CA: ${mac.current_account_pct_gdp}</span>` : ''}
          ${mac.fiscal_deficit_pct_gdp ? `<span class="macro-chip">🏛️ Deficit: ${mac.fiscal_deficit_pct_gdp}</span>` : ''}
          ${mac.key_commodity_metric ? `<span class="macro-chip">📦 ${mac.key_commodity_metric}</span>` : ''}
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

        
        <!-- Rates Pay / Receive & Execution Playbook Box -->
        ${c.rates_execution ? `
        <div style="background: linear-gradient(135deg, rgba(0, 113, 227, .06) 0%, rgba(52, 199, 89, .06) 100%); border: 1px solid rgba(0, 113, 227, .25); border-radius: 16px; padding: 16px 18px; margin: 14px 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 16px;">⚡</span>
              <strong style="font-size: 14px; color: var(--text);">Rates Pay / Receive & Instrument Execution Playbook</strong>
            </div>
            <span class="directive-badge ${c.rates_execution.directive.toLowerCase().includes('pay fixed') ? 'directive-pay' : c.rates_execution.directive.toLowerCase().includes('flattener') ? 'directive-spread' : c.rates_execution.directive.toLowerCase().includes('front-end') ? 'directive-cash' : 'directive-receive'}">
              ${c.rates_execution.directive}
            </span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-bottom: 10px;">
            <div style="background: rgba(255,255,255,.8); padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line);">
              <span style="font-size: 11px; color: var(--muted); display: block; text-transform: uppercase; font-weight: 700;">Swap / Futures Instrument:</span>
              <strong style="font-size: 13px; color: var(--text);">${c.rates_execution.swap_instrument}</strong>
            </div>
            <div style="background: rgba(255,255,255,.8); padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line);">
              <span style="font-size: 11px; color: var(--muted); display: block; text-transform: uppercase; font-weight: 700;">Liquidity & Standard Clip:</span>
              <span style="font-size: 12.5px; font-weight: 600;">${c.rates_execution.liquidity_tier}</span>
              <div style="font-size: 11.5px; color: var(--muted);">Clip: ${c.rates_execution.standard_market_clip} · Bid/Ask: ${c.rates_execution.bid_ask_spread}</div>
            </div>
            <div style="background: rgba(255,255,255,.8); padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line);">
              <span style="font-size: 11px; color: var(--muted); display: block; text-transform: uppercase; font-weight: 700;">DV01 Sizing & Risk:</span>
              <strong style="font-size: 13px; color: var(--accent);">${c.rates_execution.recommended_sizing}</strong>
              <div style="font-size: 11.5px; color: var(--muted);">${c.rates_execution.recommended_notional} (${c.rates_execution.dv01_per_unit})</div>
            </div>
          </div>
          <div style="background: rgba(255,255,255,.9); border-left: 3px solid var(--accent); padding: 8px 12px; border-radius: 8px; font-size: 13px; color: var(--text);">
            <strong>Trader Lingo & Execution Rationale:</strong> ${c.rates_execution.trader_lingo_playbook}
          </div>
        </div>
        ` : ''}

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

        <!-- Open Sovereign One-Pager Dossier CTA Button -->
        <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
          <a href="gbi_country.html?c=${c.id}" class="filter-btn" style="background: var(--accent); color: #fff; text-decoration: none; font-weight: 700; font-size: 12.5px; display: inline-flex; align-items: center; gap: 6px; padding: 8px 18px; border-radius: 20px; box-shadow: 0 2px 6px rgba(0, 113, 227, 0.25); transition: all .15s ease;">
            <span>📖</span> Open Full ${c.name || c.country || c.id} One-Pager Dossier ↗
          </a>
          <div style="font-size: 11.5px; color: var(--muted); font-weight: 500;">
            Comprehensive macro balance sheet, GDP structure, positives/negatives & risk triggers
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
