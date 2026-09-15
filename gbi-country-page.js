// gbi-country-page.js
// Client logic for GBI-EM Sovereign Country One-Pager Dossiers

(function() {
  "use strict";

  let gbiData = null;
  let activeCountryId = "brazil";

  const COUNTRY_WEIGHTS = {
    "brazil": "10.0% (Capped)",
    "mexico": "10.0% (Capped)",
    "indonesia": "10.0% (Capped)",
    "poland": "10.0% (Capped)",
    "south_africa": "8.8%",
    "india": "10.0% (Phased In)",
    "thailand": "9.5%",
    "malaysia": "10.0% (Capped)",
    "colombia": "4.2%",
    "chile": "3.1%",
    "czech_republic": "3.4%",
    "hungary": "3.2%",
    "romania": "3.5%",
    "peru": "2.4%",
    "turkey": "1.2%",
    "philippines": "1.0%",
    "egypt": "1.1%"
  };

  async function loadData() {
    try {
      const resp = await fetch("gbi_em_data.json?t=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      gbiData = await resp.json();
    } catch (e) {
      console.warn("Falling back to embedded JSON:", e);
      const fallback = document.getElementById("gbiFallbackData");
      if (fallback) {
        try { gbiData = JSON.parse(fallback.textContent); } catch (_) {}
      }
    }

    if (!gbiData || !gbiData.countries) {
      console.error("No GBI-EM data available.");
      return;
    }

    // Determine active country from URL query param
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("c") || params.get("country");
    if (requested && gbiData.countries[requested.toLowerCase()]) {
      activeCountryId = requested.toLowerCase();
    } else {
      activeCountryId = "brazil";
    }

    initCountrySelectors();
    renderDossier(activeCountryId);
  }

  function initCountrySelectors() {
    const dropdown = document.getElementById("countrySelectDropdown");
    const pillsContainer = document.getElementById("countryPillsContainer");
    if (!dropdown || !pillsContainer || !gbiData.countries) return;

    dropdown.replaceChildren();
    pillsContainer.replaceChildren();

    const countries = Object.values(gbiData.countries);

    countries.forEach(c => {
      // Dropdown option
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.flag} ${c.name} (${c.currency})`;
      if (c.id === activeCountryId) opt.selected = true;
      dropdown.appendChild(opt);

      // Pill button
      const pill = document.createElement("a");
      pill.href = `?c=${c.id}`;
      pill.className = `country-pill ${c.id === activeCountryId ? "active" : ""}`;
      pill.id = `pill_${c.id}`;
      pill.innerHTML = `<span>${c.flag}</span> <span>${c.name}</span>`;
      pill.addEventListener("click", (e) => {
        e.preventDefault();
        selectCountry(c.id);
      });
      pillsContainer.appendChild(pill);
    });

    dropdown.addEventListener("change", (e) => {
      selectCountry(e.target.value);
    });
  }

  function selectCountry(cid) {
    if (!gbiData.countries[cid]) return;
    activeCountryId = cid;

    // Update URL query parameter without page reload
    const url = new URL(window.location);
    url.searchParams.set("c", cid);
    window.history.pushState({}, "", url);

    // Update active pill
    document.querySelectorAll(".country-pill").forEach(p => p.classList.remove("active"));
    const activePill = document.getElementById(`pill_${cid}`);
    if (activePill) activePill.classList.add("active");

    // Update dropdown
    const dropdown = document.getElementById("countrySelectDropdown");
    if (dropdown) dropdown.value = cid;

    renderDossier(cid);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderDossier(cid) {
    const c = gbiData.countries[cid];
    if (!c) return;

    document.title = `${c.name} (${c.currency}) — Sovereign One-Pager Dossier | GBI-EM`;

    const rr = c.real_rate_breakdown || {};
    const tot = c.tot_reer_framework || {};
    const rx = c.rates_execution || {};
    const struct = c.economic_structure || {};
    const thesis = c.investment_thesis || {};
    const watch = c.what_to_watch || {};

    // 1. Hero Header
    document.getElementById("heroFlag").textContent = c.flag;
    document.getElementById("heroTitle").textContent = c.name;
    document.getElementById("heroCcy").textContent = c.currency;

    const badgesContainer = document.getElementById("heroBadges");
    badgesContainer.replaceChildren();

    const ratingBadge = document.createElement("span");
    ratingBadge.className = "badge badge-rating";
    ratingBadge.textContent = `Rating: ${c.credit_rating || "Unrated"}`;
    badgesContainer.appendChild(ratingBadge);

    const regionBadge = document.createElement("span");
    regionBadge.className = "badge badge-region";
    regionBadge.textContent = `Region: ${c.region || "EM"}`;
    badgesContainer.appendChild(regionBadge);

    const weightBadge = document.createElement("span");
    weightBadge.className = "badge badge-weight";
    weightBadge.textContent = `GBI-EM Weight: ${COUNTRY_WEIGHTS[c.id] || "Index Constituent"}`;
    badgesContainer.appendChild(weightBadge);

    // Stance Badge
    const stanceContainer = document.getElementById("heroStanceBadgeContainer");
    stanceContainer.replaceChildren();
    const stanceBadge = document.createElement("span");
    let stanceCls = "badge-neutral";
    const dirLower = (rx.directive || c.rates?.stance || "").toLowerCase();
    if (dirLower.includes("receive") || dirLower.includes("overweight")) stanceCls = "badge-overweight";
    else if (dirLower.includes("pay") || dirLower.includes("underweight")) stanceCls = "badge-underweight";
    else if (dirLower.includes("flattener") || dirLower.includes("steepener")) stanceCls = "badge-flattener";
    else if (dirLower.includes("carry") || dirLower.includes("roll")) stanceCls = "badge-carry";

    stanceBadge.className = `badge badge-stance ${stanceCls}`;
    stanceBadge.textContent = rx.directive || c.rates?.stance || "Neutral";
    stanceContainer.appendChild(stanceBadge);

    // Hero KPIs
    const kpiGrid = document.getElementById("heroKpiGrid");
    kpiGrid.replaceChildren();

    const exAnteReal = rr.ex_ante_real_policy_rate !== undefined ? rr.ex_ante_real_policy_rate : (c.rates.policy_rate - 3.5);
    const kpis = [
      { label: "Policy Rate", val: `${c.rates.policy_rate.toFixed(2)}%`, sub: rr.policy_rate_name || "Central Bank Rate" },
      { label: "12M Forward CPI", val: `${(rr.forward_inflation_12m || 3.5).toFixed(2)}%`, sub: "Survey Consensus" },
      { label: "Ex-Ante Real Policy Rate", val: `+${exAnteReal.toFixed(2)}%`, sub: "Policy − 12M Fwd CPI" },
      { label: "10Y Sovereign Yield", val: `${c.rates.yield_10y.toFixed(2)}%`, sub: "Benchmark 10Y" },
      { label: "FX Spot & Carry", val: `${c.fx.spot}`, sub: `+${c.fx.carry_3m_ann.toFixed(1)}% 3M Carry` },
      { label: "10Y REER Valuation", val: `${tot.reer_deviation_pct > 0 ? "+" : ""}${tot.reer_deviation_pct || 0}%`, sub: tot.reer_valuation_tag || "REER" }
    ];

    kpis.forEach(k => {
      const box = document.createElement("div");
      box.className = "kpi-box";
      box.innerHTML = `
        <div class="kpi-label">${k.label}</div>
        <div class="kpi-value">${k.val}</div>
        <div class="kpi-sub">${k.sub}</div>
      `;
      kpiGrid.appendChild(box);
    });

    // 2. Section 1: Executive Thesis
    document.getElementById("thesisExpressionText").textContent = thesis.expression || rx.recommended_notional || "Expression details loading...";
    document.getElementById("thesisNarrativeText").textContent = thesis.core_thesis || c.executive_summary || "Core thesis narrative loading...";

    // 3. Section 2: Positives vs Negatives
    const posList = document.getElementById("positivesList");
    posList.replaceChildren();
    (c.positives || []).forEach(p => {
      const li = document.createElement("li");
      li.className = "point-item bull";
      li.textContent = p;
      posList.appendChild(li);
    });

    const negList = document.getElementById("negativesList");
    negList.replaceChildren();
    (c.negatives || []).forEach(n => {
      const li = document.createElement("li");
      li.className = "point-item bear";
      li.textContent = n;
      negList.appendChild(li);
    });

    // 4. Section 3: Economic Structure
    const gdpMix = struct.gdp_mix || { services: 60, industry: 30, agriculture_mining: 10 };
    document.getElementById("gdpSegServices").style.width = `${gdpMix.services}%`;
    document.getElementById("gdpSegIndustry").style.width = `${gdpMix.industry}%`;
    document.getElementById("gdpSegAgri").style.width = `${gdpMix.agriculture_mining}%`;
    document.getElementById("gdpValServices").textContent = `${gdpMix.services}%`;
    document.getElementById("gdpValIndustry").textContent = `${gdpMix.industry}%`;
    document.getElementById("gdpValAgri").textContent = `${gdpMix.agriculture_mining}%`;

    const exportsCloud = document.getElementById("topExportsCloud");
    exportsCloud.replaceChildren();
    (struct.top_exports || []).forEach(exp => {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = exp;
      exportsCloud.appendChild(tag);
    });

    const partnersCloud = document.getElementById("topPartnersCloud");
    partnersCloud.replaceChildren();
    (struct.top_trading_partners || []).forEach(prt => {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = prt;
      partnersCloud.appendChild(tag);
    });

    document.getElementById("structDebtVal").textContent = `${struct.public_debt_pct_gdp || 50.0}% of GDP`;
    document.getElementById("structForeignHoldVal").textContent = `${struct.foreign_ownership_pct_debt || 15.0}%`;
    document.getElementById("structReservesVal").textContent = `$${tot.fx_reserves_bn || 50}B (${tot.import_cover_months || 6} mos)`;
    document.getElementById("structBankingText").textContent = struct.banking_system_summary || "Banking system stable and well-capitalized.";
    document.getElementById("structAnchorText").textContent = struct.domestic_institutional_anchor || "Domestic institutional investors anchor sovereign issuance.";

    // 5. Section 4: Macro Metrics Table
    const metricsBody = document.getElementById("macroMetricsTableBody");
    metricsBody.replaceChildren();
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="mono">${c.rates.policy_rate.toFixed(2)}%</span><br><small style="color:var(--muted)">${rr.policy_rate_name || ""}</small></td>
      <td><span class="mono">${(rr.forward_inflation_12m || 3.5).toFixed(2)}%</span><br><small style="color:var(--muted)">${rr.forward_inflation_source || "Survey"}</small></td>
      <td><span class="mono" style="color:var(--good)">+${exAnteReal.toFixed(2)}%</span><br><small style="color:var(--muted)">Ex-Ante Policy</small></td>
      <td><span class="mono">${c.rates.yield_10y.toFixed(2)}%</span><br><small style="color:var(--muted)">10Y Benchmark</small></td>
      <td><span class="mono" style="color:var(--good)">+${(rr.ex_ante_real_yield_10y || (c.rates.yield_10y - 3.5)).toFixed(2)}%</span><br><small style="color:var(--muted)">10Y Real</small></td>
      <td><span class="mono">${c.fx.spot}</span><br><small style="color:var(--muted)">+${c.fx.carry_3m_ann.toFixed(1)}% Carry</small></td>
      <td><span class="mono">${tot.reer_deviation_pct > 0 ? "+" : ""}${tot.reer_deviation_pct || 0}%</span><br><small style="color:var(--muted)">${tot.reer_valuation_tag || "Fair Value"}</small></td>
      <td><span class="mono">${tot.current_account_pct_gdp > 0 ? "+" : ""}${tot.current_account_pct_gdp}% GDP</span><br><small style="color:var(--muted)">Current Account</small></td>
    `;
    metricsBody.appendChild(tr);

    // 6. Section 5: Recent Developments
    const devTimeline = document.getElementById("recentDevelopmentsTimeline");
    devTimeline.replaceChildren();
    (c.recent_developments || []).forEach(d => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      item.textContent = d;
      devTimeline.appendChild(item);
    });

    // What to Watch: Triggers
    const triggersList = document.getElementById("triggersList");
    triggersList.replaceChildren();
    (watch.key_triggers || []).forEach(t => {
      const el = document.createElement("div");
      el.style.fontSize = "12px";
      el.style.lineHeight = "1.4";
      el.innerHTML = `<span style="font-family:var(--font-mono); font-weight:700; color:var(--accent); background:var(--bg); padding:2px 6px; border-radius:4px;">${t.date}</span> <b>${t.event}:</b> ${t.detail}`;
      triggersList.appendChild(el);
    });

    // Invalidation Levels
    const invList = document.getElementById("invalidationList");
    invList.replaceChildren();
    (watch.technical_invalidation_levels || []).forEach(inv => {
      const el = document.createElement("div");
      el.innerHTML = `• <b>${inv.metric} (${inv.level}):</b> ${inv.action}`;
      invList.appendChild(el);
    });

    // Commodity Sensitivities
    const comList = document.getElementById("commoditySensitivitiesList");
    comList.replaceChildren();
    (watch.commodity_sensitivities || []).forEach(cs => {
      const el = document.createElement("div");
      el.innerHTML = `• <b>${cs.commodity} (${cs.threshold}):</b> ${cs.impact}`;
      comList.appendChild(el);
    });

    // 7. Section 6: Execution Desk Playbook
    const execGrid = document.getElementById("executionGrid");
    execGrid.replaceChildren();

    const execItems = [
      { label: "Trader Stance", val: rx.directive || "Receive Fixed" },
      { label: "Benchmark Swap / Futures", val: rx.swap_instrument || "N/A" },
      { label: "Benchmark Cash Bond", val: rx.cash_instrument || "N/A" },
      { label: "Liquidity Tier & Clip", val: `${rx.liquidity_tier || "Tier 1"} | ${rx.standard_market_clip || "Standard"}` },
      { label: "Clearing & Bid-Ask", val: `${rx.clearing_venue || "Bilateral"} | ${rx.bid_ask_spread || "1-2 bps"}` },
      { label: "DV01 Sizing ($10k Standard)", val: rx.recommended_sizing || "$10,000 DV01" }
    ];

    execItems.forEach(item => {
      const box = document.createElement("div");
      box.className = "exec-box";
      box.innerHTML = `
        <div class="exec-label">${item.label}</div>
        <div class="exec-val">${item.val}</div>
      `;
      execGrid.appendChild(box);
    });

    document.getElementById("traderLingoText").textContent = rx.trader_lingo_playbook || "Execution instructions loading...";
  }

  window.addEventListener("DOMContentLoaded", loadData);
  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("c") || params.get("country");
    if (requested && gbiData && gbiData.countries[requested.toLowerCase()]) {
      selectCountry(requested.toLowerCase());
    }
  });
})();
