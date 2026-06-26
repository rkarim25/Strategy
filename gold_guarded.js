const WORKER_DAILY_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=daily&symbol=gold";
  const WORKER_QUOTE_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=quote&symbol=gold";
  const EXPECTED_TICKER = "GC=F";
  const STATIC_DAILY_URL = "gold_daily.csv";
  const STATIC_SIGNAL_URL = "latest_gold_signal.json";
  const STATIC_SITE_DATA_URL = "gold_guarded_site_data.json";
  const AUTO_REFRESH_MS = 30 * 60 * 1000;
  const MIN_REFRESH_MS = 5 * 60 * 1000;
  const FOCUS_STALE_MS = 10 * 60 * 1000;
  const RANGE_SESSIONS = { "1w": 5, "1m": 21, "3m": 63, "1y": 252, "5y": 1260, "10y": 2520, "20y": 5040, "30y": 7560 };
  const DEFAULT_GUARDED = {
    triggerA: 0.05,
    triggerB: 0.25,
    hold2: 0.40,
    hold3: 0.15,
    leadPct: 0.0075,
    tradingCost: 0.001,
    cashRate: 0.04,
    maxLeverage: 1,
    maxHold2: null,
    maxHold3: null,
  };
  const INITIAL_CAPITAL = 100;
  const ANNUAL_INFLOW = 10;
  const TRADING_DAYS = 252;
  let latestRows = [];
  let latestRowsSource = "none";
  let chartRange = "1y";
  let chartRangeOffset = 0;
  let equityChartRange = "full";
  let equityChartRangeOffset = 0;
  let chartPoints = [];
  let chartPlot = null;
  let signalPnlPoints = [];
  let signalPnlPlot = null;
  let equityChartPoints = [];
  let equityChartPlot = null;
  let optimizerResults = [];
  let refreshInFlight = null;
  let lastRefreshAttemptAt = 0;
  let lastRefreshFinishedAt = null;
  let lastSuccessfulWorkerRefreshAt = null;
  let staticSiteData = null;
  let staticSignalMetadata = null;

  const $ = (id) => document.getElementById(id);
  const fmtMoney = (x) => Number.isFinite(x) ? x.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "-";
  const fmtWholeNumber = (x) => Number.isFinite(x) ? Math.round(x).toLocaleString() : "-";
  const fmtWholeCurrency = (x) => Number.isFinite(x) ? "$" + Math.round(x).toLocaleString() : "-";
  const fmtCompactCurrency = (x) => {
    if (!Number.isFinite(x)) return "-";
    const sign = x < 0 ? "-" : "";
    const abs = Math.abs(x);
    const units = [
      { value: 1e12, suffix: "t" },
      { value: 1e9, suffix: "b" },
      { value: 1e6, suffix: "m" },
      { value: 1e3, suffix: "k" },
    ];
    const unit = units.find((item) => abs >= item.value);
    if (!unit) return `${sign}$${Math.round(abs).toLocaleString()}`;
    return `${sign}$${Math.round(abs / unit.value).toLocaleString()}${unit.suffix}`;
  };
  const fmtPct = (x) => Number.isFinite(x) ? (x * 100).toFixed(2) + "%" : "-";
  const fmtSignedPct = (x) => Number.isFinite(x) ? `${x >= 0 ? "+" : ""}${fmtPct(x)}` : "-";
  const fmtPctWhole = (x) => Number.isFinite(x) ? x.toFixed(2) + "%" : "-";
  const fmtLeverageLabel = (x) => x === 0 ? "Cash" : `${x}x`;
  const fmtMarkerLeverageLabel = (x) => x === 0 ? "0x" : `${x}x`;
  const escapeSvgText = (value) => String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");


  function capLeverage(lev, params = DEFAULT_GUARDED) {
    const maxLev = params.maxLeverage;
    if (!Number.isFinite(maxLev) || maxLev <= 0) return lev;
    return Math.min(lev, maxLev);
  }
  const pageScope = () => document.querySelector("main") || document;

  document.querySelectorAll("[data-page-target]").forEach((button) => {
    button.addEventListener("click", () => showPage(button.dataset.pageTarget, pageScope()));
  });
  if ($("refresh")) $("refresh").addEventListener("click", () => refresh({ reason: "manual", allowManualOverride: true, force: true }));
  document.querySelectorAll("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      chartRange = button.dataset.range;
      chartRangeOffset = 0;
      $("chartStart").value = "";
      $("chartEnd").value = "";
      setActiveRangeButton(chartRange);
      renderChart();
      renderSignalPnlChart();
      updateRangeNudgeStates();
    });
  });
  document.querySelectorAll("[data-equity-range]").forEach((button) => {
    button.addEventListener("click", () => {
      equityChartRange = button.dataset.equityRange;
      equityChartRangeOffset = 0;
      $("equityChartStart").value = "";
      $("equityChartEnd").value = "";
      setActiveEquityRangeButton(equityChartRange);
      renderBacktestEquityChart();
      updateRangeNudgeStates();
    });
  });
  document.querySelectorAll(".range-nudge").forEach((button) => {
    button.addEventListener("click", () => {
      nudgeChartWindow(button.dataset.rangeChart, button.dataset.rangeStep, button.dataset.rangeDirection);
    });
  });
  if ($("applyCustomRange")) $("applyCustomRange").addEventListener("click", () => {
    chartRange = "custom";
    chartRangeOffset = 0;
    setActiveRangeButton(chartRange);
    renderChart();
    renderSignalPnlChart();
    updateRangeNudgeStates();
  });
  if ($("applyEquityCustomRange")) $("applyEquityCustomRange").addEventListener("click", () => {
    equityChartRange = "custom";
    equityChartRangeOffset = 0;
    setActiveEquityRangeButton(equityChartRange);
    renderBacktestEquityChart();
    updateRangeNudgeStates();
  });
  if ($("priceChart")) $("priceChart").addEventListener("mousemove", showChartTooltip);
  if ($("priceChart")) $("priceChart").addEventListener("mouseleave", () => {
    hideChartTooltip();
  });
  if ($("signalPnlChart")) $("signalPnlChart").addEventListener("mouseleave", () => {
    hideSignalPnlTooltip();
  });
  if ($("equityChart")) $("equityChart").addEventListener("mouseleave", () => {
    hideEquityChartTooltip();
  });
  window.addEventListener("resize", () => {
    renderChart();
    renderSignalPnlChart();
    renderBacktestEquityChart();
  });
  window.addEventListener("focus", () => refreshIfStale("focus"));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshIfStale("tab visible");
  });

  async function loadStaticHistoricalBacktest() {
    try {
      const signalMetadata = await loadStaticSignalMetadata();
      const siteData = await loadStaticSiteData();
      const { text: csv } = await fetchTextWithDiagnostics(STATIC_DAILY_URL, "Static historical back-test data");
      const rows = parseCsv(csv);
      if (rows.length < 260) throw new Error("Not enough static historical rows. Need at least ~260 rows.");

      latestRows = rows;
      latestRowsSource = "static";
      const eodResult = computeSignal(rows);
      let liveResult = eodResult;
      const staticQuotePrice = Number(signalMetadata?.quote_price);
      if (Number.isFinite(staticQuotePrice) && staticQuotePrice > 0) {
        liveResult = computeSignal(appendIntradayRow(rows, staticQuotePrice, signalMetadata.quote_timestamp || signalMetadata.generated_at_utc));
        const quoteTime = formatMetadataTime(signalMetadata.quote_timestamp || signalMetadata.generated_at_utc);
        liveResult.explanation = `Scheduled static quote fallback from ${signalMetadata.quote_source || "latest_gold_signal.json"}${quoteTime ? ` (${quoteTime})` : ""}. This intraday signal remains provisional.`;
      }
      render(eodResult, liveResult);
      renderChart();
      renderSignalPnlChart();
      renderBacktestEquityChart();
      renderTopDrawdownsTable();
      updateRangeNudgeStates();
      setStatus(`Preloaded ${rows.length} Gold sessions (${rows[0].date} to ${rows[rows.length - 1].date}).${siteData?.generated_at_utc ? " Metrics through " + siteData.sample?.end_date + "." : ""}${describeStaticSignalMetadata(signalMetadata)} Auto-refresh will check live data next.`);
    } catch (err) {
      console.error(err);
      $("equityChartMeta").textContent = "Static historical back-test data could not be loaded. Use Refresh now to try live daily data.";
      setStatus("Static historical data error: " + err.message, true);
    }
  }

  async function loadStaticSignalMetadata() {
    try {
      const { text } = await fetchTextWithDiagnostics(STATIC_SIGNAL_URL, "Static gold signal metadata");
      staticSignalMetadata = JSON.parse(text);
      return staticSignalMetadata;
    } catch (err) {
      console.warn(err);
      staticSignalMetadata = null;
      return null;
    }
  }

  async function loadStaticSiteData() {
    try {
      const { text } = await fetchTextWithDiagnostics(STATIC_SITE_DATA_URL, "Gold site data");
      staticSiteData = JSON.parse(text);
      applySiteData(staticSiteData);
      return staticSiteData;
    } catch (err) {
      console.warn(err);
      staticSiteData = null;
      return null;
    }
  }

  function applySiteData(data) {
    if (!data) return;
    const bt = data.default_backtest;
    const bh = data.buy_and_hold_1x;
    const mc = data.monte_carlo;
    const sample = data.sample;
    const set = (id, value) => {
      const el = $(id);
      if (el && value != null) el.textContent = value;
    };
    set("kpiDefaultCagr", bt?.cagr_pct);
    set("kpiDefaultMaxDd", bt?.max_drawdown_pct);
    set("kpiDefaultSharpe", bt?.sharpe_fmt);
    set("kpiDefaultVol", bt?.ann_volatility_pct);
    set("kpiDefaultEnd", bt?.end_value_fmt);
    set("kpiDefaultCalmar", bt?.calmar_fmt);
    set("kpiBhCagr", bh?.cagr_pct);
    set("kpiBhMaxDd", bh?.max_drawdown_pct);
    set("backtestSampleRange", sample ? `${sample.start_date} to ${sample.end_date}` : "-");
    set("mcMedianCagr", mc?.median_cagr_pct);
    set("mcMedianMaxDd", mc?.median_max_drawdown_pct);
    if ($("backtestCallout") && bt && bh) {
      const original = Array.isArray(data.comparison_table)
        ? data.comparison_table.find((row) => String(row.strategy || "").includes("Original Guarded"))
        : null;
      if (original) {
        $("backtestCallout").textContent =
          `On ${data.asset_label || "GC=F"} (${sample?.start_date || "?"} to ${sample?.end_date || "?"}), ` +
          `Guarded A5/B25 delivered ${bt.cagr_pct} CAGR and ${bt.max_drawdown_pct} max drawdown vs buy-and-hold ` +
          `${bh.cagr_pct} / ${bh.max_drawdown_pct}. The original A10/B20 variant posted ${original.cagr_pct} CAGR ` +
          `and ${original.max_drawdown_pct} max drawdown.`;
      } else {
        $("backtestCallout").textContent =
          `On ${data.asset_label || "GC=F"}, Guarded A5/B25 delivered ${bt.cagr_pct} CAGR and ${bt.max_drawdown_pct} max drawdown ` +
          `vs buy-and-hold ${bh.cagr_pct} / ${bh.max_drawdown_pct}.`;
      }
    }
    set("mcProbDd40", mc?.prob_max_dd_worse_40pct_fmt);
    set("mcProbDd35", mc?.prob_max_dd_worse_35pct_fmt);
    set("mcProbDd50", mc?.prob_max_dd_worse_50pct_fmt);
    set("mcProbBelowStart", mc?.prob_end_below_start_fmt);
    set("siteDataGenerated", data.generated_at_utc ? `Generated ${data.generated_at_utc}` : "");

    const comparisonBody = $("comparisonTableBody");
    if (comparisonBody && Array.isArray(data.comparison_table)) {
      comparisonBody.innerHTML = data.comparison_table.map((row) => {
        const strong = row.strategy === bt?.strategy ? "<strong>" : "";
        const strongEnd = row.strategy === bt?.strategy ? "</strong>" : "";
        return `<tr>
          <td>${strong}${row.strategy}${strongEnd}</td>
          <td>${strong}${row.cagr_pct || "-"}${strongEnd}</td>
          <td>${row.ann_volatility_pct || "-"}</td>
          <td>${row.sharpe_fmt || "-"}</td>
          <td>${row.max_drawdown_pct || "-"}</td>
          <td>${row.end_value_fmt || "-"}</td>
          <td>${row.rebalances ?? "-"}</td>
          <td>${row.cash_pct || "-"}</td>
        </tr>`;
      }).join("");
    }

    const diag = $("diagnosticsBody");
    if (diag && bt) {
      diag.innerHTML = `
        <tr><td>Cash days</td><td>${bt.pct_days_cash?.toFixed(2)}%</td><td>1x days</td><td>${bt.pct_days_1x?.toFixed(2)}%</td></tr>
        <tr><td>2x days</td><td>${bt.pct_days_2x?.toFixed(2)}%</td><td>3x days</td><td>${bt.pct_days_3x?.toFixed(2)}%</td></tr>
        <tr><td>2x entries</td><td>${bt.tier2_entries ?? "-"}</td><td>3x entries</td><td>${bt.tier3_entries ?? "-"}</td></tr>
        <tr><td>Lead-only days</td><td>${bt.lead_only_days ?? "-"}</td><td>Rebalances</td><td>${bt.rebalances ?? "-"}</td></tr>
        <tr><td>Total trading costs</td><td>${bt.trading_costs_total != null ? fmtCompactCurrency(bt.trading_costs_total) : "-"}</td><td>Total funding costs</td><td>${bt.funding_costs_total != null ? fmtCompactCurrency(bt.funding_costs_total) : "-"}</td></tr>
      `;
    }

    const mcBody = $("mcComparisonBody");
    if (mcBody && mc && Array.isArray(data.comparison_table)) {
      const rows = data.comparison_table.filter((row) =>
        /Guarded A5\/B25|Original Guarded/.test(String(row.strategy || ""))
      );
      if (rows.length) {
        mcBody.innerHTML = rows.map((row) => {
          const isDefault = row.strategy === bt?.strategy;
          const strong = isDefault ? "<strong>" : "";
          const strongEnd = isDefault ? "</strong>" : "";
          const probDd40 = isDefault ? (mc.prob_max_dd_worse_40pct_fmt || "-") : "-";
          return `<tr>
            <td>${strong}${row.strategy}${strongEnd}</td>
            <td>${isDefault ? strong + (mc.median_cagr_pct || "-") + strongEnd : "-"}</td>
            <td>${isDefault ? `${mc.p10_cagr_pct || "-"} / ${mc.p90_cagr_pct || "-"}` : "-"}</td>
            <td>${isDefault ? strong + (mc.median_max_drawdown_pct || "-") + strongEnd : row.max_drawdown_pct || "-"}</td>
            <td>${isDefault ? `${mc.p10_max_drawdown_pct || "-"} / ${mc.p90_max_drawdown_pct || "-"}` : "-"}</td>
            <td>${isDefault ? (mc.median_sharpe_fmt || "-") : row.sharpe_fmt || "-"}</td>
            <td>${isDefault ? strong + (mc.median_end_value_fmt || "-") + strongEnd : row.end_value_fmt || "-"}</td>
            <td>${probDd40}</td>
          </tr>`;
        }).join("");
      }
    }
  }

  async function refresh(options = {}) {
    const {
      reason = "manual",
      allowManualOverride = true,
      force = false
    } = options;
    const now = Date.now();
    if (refreshInFlight) return refreshInFlight;
    if (!force && now - lastRefreshAttemptAt < MIN_REFRESH_MS) {
      updateAutoRefreshStatus(`Skipped ${reason} refresh to avoid repeated worker calls.`);
      return null;
    }

    lastRefreshAttemptAt = now;
    refreshInFlight = (async () => {
      try {
        setStatus(`${reason === "manual" ? "Manual refresh" : "Auto-refresh"}: fetching daily Gold (GC=F) data...`);
        const { text: csv } = await fetchTextWithDiagnostics(WORKER_DAILY_URL, "Daily Gold data");

        const rows = parseCsv(csv);
        if (rows.length < 260) throw new Error("Not enough daily data. Need at least ~260 rows.");
        const lastClose = rows[rows.length - 1]?.close;
        if (Number.isFinite(lastClose) && lastClose > 5000) {
          throw new Error("Live feed looks like SPX, not gold (GC=F). Using static gold_daily.csv instead.");
        }
        latestRows = rows;
        latestRowsSource = "live";
        const eodResult = computeSignal(rows);

        setStatus(`${reason === "manual" ? "Manual refresh" : "Auto-refresh"}: fetching live gold quote...`);
        let livePriceInfo = null;
        let quoteWarning = "";
        try {
          livePriceInfo = await getLivePrice({ allowManualOverride });
        } catch (quoteErr) {
          console.warn(quoteErr);
          quoteWarning = quoteErr.message || String(quoteErr);
        }

        const liveRows = livePriceInfo?.price == null ? rows : appendIntradayRow(rows, livePriceInfo.price);
        const liveResult = computeSignal(liveRows);
        if (livePriceInfo?.price == null) {
          liveResult.explanation = quoteWarning
            ? `Live quote unavailable; showing last completed close as placeholder. ${quoteWarning}`
            : "No intraday price provided; showing last completed close as placeholder.";
        }

        render(eodResult, liveResult);
        renderChart();
        renderSignalPnlChart();
        renderBacktestEquityChart();
        renderTopDrawdownsTable();
        updateRangeNudgeStates();
        const quoteStatus = livePriceInfo?.price == null
          ? `Live quote failed; using last completed close. ${quoteWarning}`
          : `Live quote loaded from ${livePriceInfo.source}.`;
        lastSuccessfulWorkerRefreshAt = new Date();
        setStatus(`Loaded ${rows.length} daily rows. Last completed close: ${eodResult.latest.date}. ${quoteStatus}`, livePriceInfo?.price == null);
      } catch (err) {
        console.error(err);
        if (latestRows.length && latestRowsSource === "static") {
          setStatus("Live refresh failed; static historical back-test data remains loaded. " + err.message, true);
          renderChart();
          renderSignalPnlChart();
          renderBacktestEquityChart();
          renderTopDrawdownsTable();
          updateRangeNudgeStates();
        } else {
          setStatus("Error: " + err.message, true);
        }
      } finally {
        lastRefreshFinishedAt = new Date();
        refreshInFlight = null;
        updateAutoRefreshStatus();
      }
    })();
    return refreshInFlight;
  }

  function setStatus(message, isError = false) {
    $("status").textContent = message;
    $("status").className = isError ? "small bad" : "small";
    updateAutoRefreshStatus();
  }

  function updateAutoRefreshStatus(prefix = "") {
    const parts = [];
    if (prefix) parts.push(prefix);
    parts.push(window.SiteNav?.AUTO_REFRESH_HOURS_LABEL || "Auto-refreshes every 30 minutes during UK LSE hours while this page is open.");
    parts.push("Enter a manual gold (GC=F) level then click refresh to override the live quote.");
    if (staticSignalMetadata?.generated_at_utc) parts.push(`Static data generated: ${formatMetadataTime(staticSignalMetadata.generated_at_utc)}.`);
    if (staticSignalMetadata?.data_asof) parts.push(`Static daily data through: ${staticSignalMetadata.data_asof}.`);
    if (staticSignalMetadata?.quote_price) {
      const quoteTime = formatMetadataTime(staticSignalMetadata.quote_timestamp || staticSignalMetadata.generated_at_utc);
      parts.push(`Static quote fallback: ${fmtMoney(Number(staticSignalMetadata.quote_price))}${quoteTime ? ` as of ${quoteTime}` : ""}.`);
    }
    if (lastRefreshFinishedAt) parts.push(`Last refresh attempt: ${formatRefreshTime(lastRefreshFinishedAt)}.`);
    if (lastSuccessfulWorkerRefreshAt) parts.push(`Last successful worker refresh: ${formatRefreshTime(lastSuccessfulWorkerRefreshAt)}.`);
    $("autoRefreshStatus").textContent = parts.join(" ");
  }

  function formatRefreshTime(date) {
    return date.toLocaleString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "short"
    });
  }

  function formatMetadataTime(value) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isFinite(parsed.getTime())) return formatRefreshTime(parsed);
    return String(value);
  }

  function describeStaticSignalMetadata(metadata) {
    if (!metadata) return " Static signal metadata was not available.";
    const parts = [];
    if (metadata.generated_at_utc) parts.push(`generated ${formatMetadataTime(metadata.generated_at_utc)}`);
    if (metadata.data_asof) parts.push(`daily data through ${metadata.data_asof}`);
    if (metadata.quote_price) {
      const quoteTime = formatMetadataTime(metadata.quote_timestamp || metadata.generated_at_utc);
      parts.push(`static quote ${fmtMoney(Number(metadata.quote_price))}${quoteTime ? ` as of ${quoteTime}` : ""}`);
    }
    return parts.length ? ` Static refresh ${parts.join("; ")}.` : " Static signal metadata loaded.";
  }

  function startAutoRefresh() {
    updateAutoRefreshStatus();
    window.SiteNav?.registerAutoRefresh?.(
      () => refresh({ reason: "scheduled", allowManualOverride: false }),
      AUTO_REFRESH_MS
    ) ?? window.setInterval(() => {
      if (!document.hidden) refresh({ reason: "scheduled", allowManualOverride: false });
    }, AUTO_REFRESH_MS);
  }

  function refreshIfStale(reason) {
    if (window.SiteNav?.isUkLseTradingHours && !window.SiteNav.isUkLseTradingHours()) return;
    const referenceTime = lastRefreshFinishedAt?.getTime() ?? lastRefreshAttemptAt;
    if (!referenceTime || Date.now() - referenceTime >= FOCUS_STALE_MS) {
      refresh({ reason, allowManualOverride: false });
    }
  }

  async function fetchTextWithDiagnostics(url, label) {
    let response;
    try {
      response = await fetch(url, { cache: "no-store" });
    } catch (err) {
      throw new Error(`${label} request could not reach ${url}. ${networkFailureHint(err)}`);
    }

    const text = await response.text();
    if (!response.ok) {
      const body = text.trim().slice(0, 240);
      throw new Error(`${label} request to ${url} failed: HTTP ${response.status} ${response.statusText}${body ? ` - ${body}` : ""}`);
    }
    return { response, text };
  }

  function networkFailureHint(err) {
    const reason = err?.message ? `Browser error: ${err.message}. ` : "";
    return `${reason}This usually means the network, DNS, proxy, TLS inspection, browser extension, or CORS policy blocked the request before the site received an HTTP status.`;
  }

  function showPage(pageId, scope = pageScope(), options = {}) {
    scope.querySelectorAll(".page").forEach((page) => {
      page.classList.toggle("active", page.id === pageId);
    });
    scope.querySelectorAll("[data-page-target]").forEach((button) => {
      button.classList.toggle("active", button.dataset.pageTarget === pageId);
    });
    if (options.updateHash !== false && window.SiteNav) {
      SiteNav.setHash(pageId, { replace: options.replaceHash !== false });
    }
    if (pageId === "signalPage") {
      renderChart();
      renderSignalPnlChart();
    }
    if (pageId === "backtestPage") {
      renderBacktestEquityChart();
      renderTopDrawdownsTable();
    }
  }

  function applyRouteFromLocation() {
    if (!window.SiteNav) return;
    const pageId = SiteNav.pageFromLocation();
    if (pageId && $(pageId)) showPage(pageId, pageScope(), { updateHash: false });
  }

  if (window.SiteNav) {
    SiteNav.onRouteChange(() => applyRouteFromLocation());
    applyRouteFromLocation();
  }

  function parseCsv(csv) {
    const lines = csv.trim().split(/\r?\n/);
    const header = lines.shift().split(",").map((h) => h.trim().toLowerCase());
    const dateIdx = header.indexOf("date");
    const closeIdx = header.indexOf("close");
    if (dateIdx < 0 || closeIdx < 0) throw new Error("CSV must include Date and Close columns.");

    return lines.map((line) => {
      const parts = line.split(",");
      return {
        date: parts[dateIdx],
        close: Number(parts[closeIdx])
      };
    }).filter((row) => row.date && Number.isFinite(row.close) && row.close > 0);
  }

  async function getLivePrice(options = {}) {
    const { allowManualOverride = true } = options;
    if (allowManualOverride) {
      const manual = Number($("manualIntradayPrice").value);
      if (Number.isFinite(manual) && manual > 0) {
        return { price: manual, source: "manual override" };
      }
    }

    const { response, text } = await fetchTextWithDiagnostics(WORKER_QUOTE_URL, "Intraday gold quote");
    let parsedJson = null;
    try {
      parsedJson = JSON.parse(text);
    } catch (_) {
      try {
        const parsed = parseCsv(text);
        if (parsed.length) {
          return { price: parsed[parsed.length - 1].close, source: `${WORKER_QUOTE_URL} (CSV fallback)` };
        }
      } catch (_) {
        // Fall through to diagnostic below.
      }
    }

    if (parsedJson && parsedJson.ticker && EXPECTED_TICKER && String(parsedJson.ticker) !== EXPECTED_TICKER) {
      throw new Error(`Live quote ticker mismatch: got ${parsedJson.ticker}, expected ${EXPECTED_TICKER}. Worker may be stale — using last completed close.`);
    }
    const price = Number(parsedJson?.price ?? parsedJson?.close ?? parsedJson?.last ?? parsedJson?.value);
    if (Number.isFinite(price) && price > 0) {
      return { price, source: parsedJson?.source || `${WORKER_QUOTE_URL} (HTTP ${response.status})` };
    }
    throw new Error(`Intraday quote response from ${WORKER_QUOTE_URL} must return JSON with price/close/last or CSV with Date,Close.`);
  }

  function appendIntradayRow(rows, price, timestamp = null) {
    const out = rows.slice();
    const now = new Date();
    const stamp = timestamp ? String(timestamp) : now.toISOString().replace("T", " ").slice(0, 16) + " UTC";
    out.push({ date: stamp, close: price });
    return out;
  }

  function sma(values, endIndex, window) {
    if (endIndex + 1 < window) return NaN;
    let sum = 0;
    for (let i = endIndex - window + 1; i <= endIndex; i++) sum += values[i];
    return sum / window;
  }

  function computeSignal(rows) {
    const params = DEFAULT_GUARDED;
    const closes = rows.map((r) => r.close);
    let highWater = closes[0];
    let highWaterDate = rows[0].date;
    let regime = "base";
    let entryClose = null;
    let entryDate = null;
    let baseEntryClose = null;
    let baseEntryDate = null;
    let previousTargetLeverage = 0;
    let targetLeverage = 0;
    let explanation = "";

    const updateActiveEntryTracking = (close, date) => {
      if (targetLeverage === 1 && previousTargetLeverage !== 1) {
        baseEntryClose = close;
        baseEntryDate = date;
      } else if (targetLeverage === 0) {
        baseEntryClose = null;
        baseEntryDate = null;
      }
      previousTargetLeverage = targetLeverage;
    };

    for (let i = 0; i < rows.length; i++) {
      const close = closes[i];
      const avg20 = sma(closes, i, 20);
      if (close >= highWater) {
        highWater = close;
        highWaterDate = rows[i].date;
      }

      const dd = close / highWater - 1;
      const aboveSma = Number.isFinite(avg20) && close > avg20;
      const recoveryOk = Number.isFinite(avg20) && close >= avg20 * (1 - params.leadPct);
      const baseLev = aboveSma ? 1 : 0;

      if (regime === "tier3") {
        if (close / entryClose - 1 >= params.hold3) {
          regime = "base";
          entryClose = null;
          entryDate = null;
        } else {
          targetLeverage = capLeverage(recoveryOk ? 3 : baseLev);
          explanation = recoveryOk
            ? "3x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
            : "3x tier is armed, but lead guard failed; using base cash/1x rule.";
          updateActiveEntryTracking(close, rows[i].date);
          continue;
        }
      }

      if (regime === "tier2") {
        if (dd <= -params.triggerB && recoveryOk) {
          regime = "tier3";
          entryClose = close;
          entryDate = rows[i].date;
          targetLeverage = capLeverage(3);
          explanation = "Drawdown hit B=-25% and lead guard passed; upgraded to 3x.";
          updateActiveEntryTracking(close, rows[i].date);
          continue;
        }
        if (close / entryClose - 1 >= params.hold2) {
          regime = "base";
          entryClose = null;
          entryDate = null;
        } else {
          targetLeverage = capLeverage(recoveryOk ? 2 : baseLev);
          explanation = recoveryOk
            ? "2x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
            : "2x tier is armed, but lead guard failed; using base cash/1x rule.";
          updateActiveEntryTracking(close, rows[i].date);
          continue;
        }
      }

      if (dd <= -params.triggerB && recoveryOk) {
        regime = "tier3";
        entryClose = close;
        entryDate = rows[i].date;
        targetLeverage = capLeverage(3);
        explanation = "Drawdown is at/through -25% and price is inside the 0.75% SMA20 lead guard; enter 3x.";
      } else if (dd <= -params.triggerA && recoveryOk) {
        regime = "tier2";
        entryClose = close;
        entryDate = rows[i].date;
        targetLeverage = capLeverage(2);
        explanation = "Drawdown is at/through -5% and price is inside the 0.75% SMA20 lead guard; enter 2x.";
      } else {
        targetLeverage = baseLev;
        explanation = aboveSma
          ? "No recovery tier active; base rule says 1x because close is above SMA20."
          : "No recovery tier active; base rule says cash because close is below SMA20.";
      }
      updateActiveEntryTracking(close, rows[i].date);
    }

    const lastIndex = rows.length - 1;
    const latest = rows[lastIndex];
    const latestSma = sma(closes, lastIndex, 20);
    const latestDd = latest.close / highWater - 1;
    const recoveryTarget = entryClose == null
      ? null
      : regime === "tier3"
        ? entryClose * (1 + params.hold3)
        : entryClose * (1 + params.hold2);
    const activeEntryClose = targetLeverage <= 0
      ? null
      : targetLeverage >= 2
        ? entryClose
        : baseEntryClose;
    const activeEntryDate = targetLeverage <= 0
      ? null
      : targetLeverage >= 2
        ? entryDate
        : baseEntryDate;
    const activeEntryLeverage = activeEntryClose == null ? null : targetLeverage;
    const activeEntryPnl = activeEntryClose == null ? null : latest.close / activeEntryClose - 1;

    return {
      latest,
      latestSma,
      highWater,
      highWaterDate,
      latestDd,
      regime,
      entryClose,
      entryDate,
      recoveryTarget,
      aboveSma: latest.close > latestSma,
      recoveryOk: latest.close >= latestSma * (1 - params.leadPct),
      targetLeverage,
      activeEntryClose,
      activeEntryDate,
      activeEntryLeverage,
      activeEntryPnl,
      explanation
    };
  }

  function readNumber(id, fallback = NaN) {
    const value = Number($(id).value);
    return Number.isFinite(value) ? value : fallback;
  }

  function readOptionalNumber(id) {
    const value = Number($(id).value);
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  function calculatorParamsFromInputs() {
    const triggerA = readNumber("calcTriggerA") / 100;
    const triggerB = readNumber("calcTriggerB") / 100;
    const hold2 = readNumber("calcHold2") / 100;
    const hold3 = readNumber("calcHold3") / 100;
    const leadPct = Math.max(readNumber("calcLeadPct", DEFAULT_GUARDED.leadPct * 100) / 100, 0);
    const tradingCost = Math.max(readNumber("calcTradingCost", 0.1) / 100, 0);
    const cashRate = Math.max(readNumber("calcCashRate", 4) / 100, 0);
    const maxHold2 = readOptionalNumber("calcMaxHold2");
    const maxHold3 = readOptionalNumber("calcMaxHold3");
    if (!(triggerA > 0 && triggerB > triggerA && hold2 > 0 && hold3 > 0)) {
      throw new Error("Use positive values and keep B greater than A.");
    }
    return { triggerA, triggerB, hold2, hold3, leadPct, maxHold2, maxHold3, tradingCost, cashRate };
  }

  function guardedLeverageForParams(rows, params) {
    const closes = rows.map((row) => row.close);
    const leverage = [];
    let highWater = closes[0];
    let regime = "base";
    let entryClose = null;
    let entryIndex = null;
    let tier2Entries = 0;
    let tier3Entries = 0;

    for (let i = 0; i < rows.length; i++) {
      const close = closes[i];
      const avg20 = sma(closes, i, 20);
      if (close >= highWater) highWater = close;

      const dd = close / highWater - 1;
      const aboveSma = Number.isFinite(avg20) && close > avg20;
      const recoveryOk = Number.isFinite(avg20) && close >= avg20 * (1 - (params.leadPct ?? 0));
      const baseLev = aboveSma ? 1 : 0;
      let target = baseLev;

      if (regime === "tier3") {
        const hitGain = entryClose != null && close / entryClose - 1 >= params.hold3;
        const hitTime = params.maxHold3 != null && entryIndex != null && i - entryIndex >= params.maxHold3;
        if (hitGain || hitTime) {
          regime = "base";
          entryClose = null;
          entryIndex = null;
        } else {
          leverage.push(capLeverage(recoveryOk ? 3 : baseLev));
          continue;
        }
      }

      if (regime === "tier2") {
        const hitGain = entryClose != null && close / entryClose - 1 >= params.hold2;
        const hitTime = params.maxHold2 != null && entryIndex != null && i - entryIndex >= params.maxHold2;
        if (dd <= -params.triggerB && recoveryOk) {
          regime = "tier3";
          entryClose = close;
          entryIndex = i;
          tier3Entries += 1;
          leverage.push(capLeverage(3));
          continue;
        }
        if (hitGain || hitTime) {
          regime = "base";
          entryClose = null;
          entryIndex = null;
        } else {
          leverage.push(capLeverage(recoveryOk ? 2 : baseLev));
          continue;
        }
      }

      if (dd <= -params.triggerB && recoveryOk) {
        regime = "tier3";
        entryClose = close;
        entryIndex = i;
        tier3Entries += 1;
        target = capLeverage(3);
      } else if (dd <= -params.triggerA && recoveryOk) {
        regime = "tier2";
        entryClose = close;
        entryIndex = i;
        tier2Entries += 1;
        target = capLeverage(2);
      }
      leverage.push(capLeverage(target));
    }

    return { leverage, tier2Entries, tier3Entries };
  }

  function backtestParameterizedGuarded(rows, params) {
    const { leverage, tier2Entries, tier3Entries } = guardedLeverageForParams(rows, params);
    let aum = INITIAL_CAPITAL;
    let peak = aum;
    let prevLev = 1;
    let prevYear = new Date(rows[0].date).getUTCFullYear();
    let tradingCosts = 0;
    let rebalances = 0;
    const equity = [];
    const returns = [];
    const dailyCash = params.cashRate / TRADING_DAYS;

    for (let i = 0; i < rows.length; i++) {
      const year = new Date(rows[i].date).getUTCFullYear();
      if (i > 0 && year !== prevYear) {
        aum += ANNUAL_INFLOW;
        peak = Math.max(peak, aum);
      }

      // No lookahead: the leverage decided at the prior close is held through today,
      // matching the Python engine (signal from close[i] earns return[i+1]).
      const lev = i > 0 ? leverage[i - 1] : leverage[0];
      if (Math.abs(lev - prevLev) > 1e-9) {
        const cost = Math.abs(lev - prevLev) * aum * params.tradingCost;
        aum -= cost;
        tradingCosts += cost;
        rebalances += 1;
        prevLev = lev;
      }

      let ret = 0;
      if (i > 0) {
        const spxRet = rows[i].close / rows[i - 1].close - 1;
        if (lev <= 0) {
          ret = dailyCash;
        } else {
          const funding = lev > 1 ? (lev - 1) * params.cashRate / TRADING_DAYS : 0;
          ret = lev * spxRet - funding;
        }
        aum *= 1 + ret;
      }

      peak = Math.max(peak, aum);
      equity.push(aum);
      returns.push(ret);
      prevYear = year;
    }

    return {
      ...portfolioStats(rows, equity, returns),
      tradingCosts,
      rebalances,
      leverage,
      equity,
      tier2Entries,
      tier3Entries,
    };
  }

  function portfolioStats(rows, equity, returns) {
    const start = new Date(rows[0].date);
    const end = new Date(rows[rows.length - 1].date);
    const years = Math.max((end - start) / (365.25 * 24 * 60 * 60 * 1000), 1e-9);
    const endValue = equity[equity.length - 1];
    const cagr = Math.pow(endValue / equity[0], 1 / years) - 1;
    let peak = equity[0];
    let maxDrawdown = 0;
    for (const value of equity) {
      peak = Math.max(peak, value);
      maxDrawdown = Math.min(maxDrawdown, value / peak - 1);
    }
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / Math.max(returns.length - 1, 1);
    const stdev = Math.sqrt(variance);
    const sharpe = stdev > 0 ? Math.sqrt(TRADING_DAYS) * mean / stdev : NaN;
    return { cagr, maxDrawdown, sharpe, endValue };
  }

  function runCalculator() {
    if (!latestRows.length) {
      $("calcStatus").textContent = "Load data first with Refresh signal.";
      return null;
    }
    try {
      const params = calculatorParamsFromInputs();
      const result = backtestParameterizedGuarded(latestRows, params);
      renderCalculatorResult(result);
      $("calcStatus").textContent = `Calculated ${latestRows.length} sessions from ${latestRows[0].date} to ${latestRows[latestRows.length - 1].date}.`;
      $("calcStatus").className = "small section-gap";
      return result;
    } catch (err) {
      $("calcStatus").textContent = "Calculator error: " + err.message;
      $("calcStatus").className = "small bad section-gap";
      return null;
    }
  }

  function renderCalculatorResult(result) {
    $("calcCagr").textContent = fmtPct(result.cagr);
    $("calcMaxDd").textContent = fmtPct(result.maxDrawdown);
    $("calcSharpe").textContent = Number.isFinite(result.sharpe) ? result.sharpe.toFixed(3) : "-";
    $("calcEndValue").textContent = "$" + fmtMoney(result.endValue);
    $("calcTrades").textContent = result.rebalances.toLocaleString();
    $("calcCosts").textContent = "$" + fmtMoney(result.tradingCosts);
    const n = result.leverage.length || 1;
    const pct = (lev) => (100 * result.leverage.filter((x) => x === lev).length / n).toFixed(2) + "%";
    $("calcExposure").textContent = `${pct(0)} / ${pct(1)} / ${pct(2)} / ${pct(3)}`;
    $("calcTierEntries").textContent = `2x entries: ${result.tier2Entries}; 3x entries: ${result.tier3Entries}`;
  }

  function resetCalculator() {
    $("calcTriggerA").value = DEFAULT_GUARDED.triggerA * 100;
    $("calcTriggerB").value = DEFAULT_GUARDED.triggerB * 100;
    $("calcHold2").value = DEFAULT_GUARDED.hold2 * 100;
    $("calcHold3").value = DEFAULT_GUARDED.hold3 * 100;
    $("calcLeadPct").value = DEFAULT_GUARDED.leadPct * 100;
    $("calcMaxHold2").value = "";
    $("calcMaxHold3").value = "";
    $("calcTradingCost").value = 1;
    $("calcCashRate").value = 4;
    runCalculator();
  }

  function rangeValues(startId, endId, stepId) {
    const start = readNumber(startId);
    const end = readNumber(endId);
    const step = readNumber(stepId);
    if (!(Number.isFinite(start) && Number.isFinite(end) && step > 0 && end >= start)) {
      throw new Error(`Invalid optimizer range near ${startId}.`);
    }
    const values = [];
    for (let value = start; value <= end + step / 10; value += step) values.push(Number(value.toFixed(6)));
    return values;
  }

  function optimizerValues(fixId, calcId, startId, endId, stepId) {
    if ($(fixId).checked) {
      const fixed = readNumber(calcId);
      if (!(Number.isFinite(fixed) && fixed > 0)) throw new Error(`Fixed value for ${calcId} is invalid.`);
      return [fixed];
    }
    return rangeValues(startId, endId, stepId);
  }

  function runOptimizer() {
    if (!latestRows.length) {
      $("optStatus").textContent = "Load data first with Refresh signal.";
      return;
    }
    try {
      const aValues = optimizerValues("optFixA", "calcTriggerA", "optAStart", "optAEnd", "optAStep");
      const bValues = optimizerValues("optFixB", "calcTriggerB", "optBStart", "optBEnd", "optBStep");
      const hold2Values = optimizerValues("optFixX", "calcHold2", "optHold2Start", "optHold2End", "optHold2Step");
      const hold3Values = optimizerValues("optFixY", "calcHold3", "optHold3Start", "optHold3End", "optHold3Step");
      const comboCount = aValues.length * bValues.length * hold2Values.length * hold3Values.length;
      if (comboCount > 7000) throw new Error(`Grid has ${comboCount.toLocaleString()} combinations. Narrow the range or increase step size.`);

      const objective = $("optObjective").value;
      const tradingCost = Math.max(readNumber("calcTradingCost", 0.1) / 100, 0);
      const cashRate = Math.max(readNumber("calcCashRate", 4) / 100, 0);
      const leadPct = Math.max(readNumber("calcLeadPct", DEFAULT_GUARDED.leadPct * 100) / 100, 0);
      const maxHold2 = readOptionalNumber("calcMaxHold2");
      const maxHold3 = readOptionalNumber("calcMaxHold3");
      optimizerResults = [];

      for (const a of aValues) {
        for (const b of bValues) {
          if (b <= a) continue;
          for (const hold2 of hold2Values) {
            for (const hold3 of hold3Values) {
              const params = {
                triggerA: a / 100,
                triggerB: b / 100,
                hold2: hold2 / 100,
                hold3: hold3 / 100,
                maxHold2,
                maxHold3,
                leadPct,
                tradingCost,
                cashRate,
              };
              const result = backtestParameterizedGuarded(latestRows, params);
              optimizerResults.push({ params, result, score: optimizerScore(result, objective) });
            }
          }
        }
      }

      optimizerResults.sort((a, b) => b.score - a.score);
      renderOptimizerResults();
      const objectiveLabel = $("optObjective").selectedOptions[0].textContent.toLowerCase();
      const searched = [
        $("optFixA").checked ? `A fixed at ${fmtPctWhole(aValues[0])}` : `A searched ${aValues.length} values`,
        $("optFixB").checked ? `B fixed at ${fmtPctWhole(bValues[0])}` : `B searched ${bValues.length} values`,
        $("optFixX").checked ? `X fixed at ${fmtPctWhole(hold2Values[0])}` : `X searched ${hold2Values.length} values`,
        $("optFixY").checked ? `Y fixed at ${fmtPctWhole(hold3Values[0])}` : `Y searched ${hold3Values.length} values`,
      ].join("; ");
      $("optStatus").textContent = `Searched ${comboCount.toLocaleString()} combinations for ${objectiveLabel}. ${searched}.`;
      $("optStatus").className = "small section-gap";
    } catch (err) {
      $("optStatus").textContent = "Optimizer error: " + err.message;
      $("optStatus").className = "small bad section-gap";
    }
  }

  function optimizerScore(result, objective) {
    if (objective === "drawdown") return result.maxDrawdown;
    if (objective === "sharpe") return Number.isFinite(result.sharpe) ? result.sharpe : -Infinity;
    return result.cagr;
  }

  function renderOptimizerResults() {
    const count = Math.max(3, Math.min(readNumber("optResultCount", 10), 25));
    const displayResults = diversifiedOptimizerResults(count);
    const rows = displayResults.map((item, index) => {
      const p = item.params;
      const r = item.result;
      return `<tr>
        <td>${index + 1}</td>
        <td>${fmtPctWhole(p.triggerA * 100)}</td>
        <td>${fmtPctWhole(p.triggerB * 100)}</td>
        <td>${fmtPctWhole(p.hold2 * 100)}</td>
        <td>${fmtPctWhole(p.hold3 * 100)}</td>
        <td>${fmtPct(r.cagr)}</td>
        <td>${fmtPct(r.maxDrawdown)}</td>
        <td>${Number.isFinite(r.sharpe) ? r.sharpe.toFixed(3) : "-"}</td>
        <td>$${fmtMoney(r.endValue)}</td>
        <td>${r.rebalances.toLocaleString()}</td>
      </tr>`;
    });
    $("optimizerRows").innerHTML = rows.length ? rows.join("") : `<tr><td colspan="10">No combinations passed the selected filters.</td></tr>`;
  }

  function diversifiedOptimizerResults(count) {
    const chosen = [];
    const seenCombos = new Set();
    const add = (item) => {
      const key = [
        item.params.triggerA,
        item.params.triggerB,
        item.params.hold2,
        item.params.hold3,
      ].map((x) => x.toFixed(6)).join("|");
      if (seenCombos.has(key) || chosen.length >= count) return;
      seenCombos.add(key);
      chosen.push(item);
    };

    const diversifyBy = [
      ["optFixX", (item) => item.params.hold2],
      ["optFixY", (item) => item.params.hold3],
      ["optFixA", (item) => item.params.triggerA],
      ["optFixB", (item) => item.params.triggerB],
    ];

    for (const [fixId, selector] of diversifyBy) {
      if ($(fixId).checked) continue;
      const seenValues = new Set();
      for (const item of optimizerResults) {
        const valueKey = selector(item).toFixed(6);
        if (seenValues.has(valueKey)) continue;
        seenValues.add(valueKey);
        add(item);
        if (chosen.length >= count) return chosen;
      }
    }

    for (const item of optimizerResults) add(item);
    return chosen;
  }

  function useBestOptimizerResult() {
    if (!optimizerResults.length) {
      $("optStatus").textContent = "Run the optimizer first.";
      return;
    }
    const { params } = optimizerResults[0];
    $("calcTriggerA").value = (params.triggerA * 100).toFixed(2);
    $("calcTriggerB").value = (params.triggerB * 100).toFixed(2);
    $("calcHold2").value = (params.hold2 * 100).toFixed(2);
    $("calcHold3").value = (params.hold3 * 100).toFixed(2);
    runCalculator();
  }

  function render(eod, live) {
    renderSignal("eod", eod);
    renderSignal("live", live);
    $("latestDate").textContent = eod.latest.date;
    $("highWater").textContent = `${fmtMoney(eod.highWater)} (${eod.highWaterDate})`;
    $("tier2Level").textContent = fmtMoney(eod.highWater * (1 - DEFAULT_GUARDED.triggerA));
    $("tier3Level").textContent = fmtMoney(eod.highWater * (1 - DEFAULT_GUARDED.triggerB));
    $("aboveSma").textContent = eod.aboveSma ? "Yes" : "No";
    $("leadGuardLevel").textContent = Number.isFinite(eod.latestSma)
      ? fmtMoney(eod.latestSma * (1 - DEFAULT_GUARDED.leadPct))
      : "-";
  }


  function rangeWindowLength(range) {
    if (range === "full") return latestRows.length;
    if (range === "custom") return null;
    return RANGE_SESSIONS[range] || latestRows.length;
  }

  function maxRangeOffset(range) {
    if (!latestRows.length || range === "custom") return 0;
    const len = rangeWindowLength(range);
    return Math.max(0, latestRows.length - len);
  }

  function updateRangeNudgeStates() {
    document.querySelectorAll(".range-nudge").forEach((button) => {
      const chartKind = button.dataset.rangeChart;
      const stepKey = button.dataset.rangeStep;
      const direction = button.dataset.rangeDirection;
      const range = chartKind === "equity" ? equityChartRange : chartRange;
      const offset = chartKind === "equity" ? equityChartRangeOffset : chartRangeOffset;
      const step = RANGE_SESSIONS[stepKey];
      if (!step) return;
      if (direction === "forward") {
        button.disabled = range === "custom" || offset === 0;
        return;
      }
      if (range === "custom") {
        button.disabled = false;
        return;
      }
      const activeLen = range === stepKey ? rangeWindowLength(range) : step;
      const projectedOffset = range === stepKey ? offset + step : step;
      button.disabled = projectedOffset > maxRangeOffset(stepKey) && range !== "full";
    });
  }

  function nudgeCustomRange(chartKind, step, direction) {
    const startEl = chartKind === "equity" ? $("equityChartStart") : $("chartStart");
    const endEl = chartKind === "equity" ? $("equityChartEnd") : $("chartEnd");
    const startValue = startEl.value || latestRows[0].date;
    const endValue = endEl.value || latestRows[latestRows.length - 1].date;
    let startIdx = latestRows.findIndex((row) => row.date >= startValue);
    let endIdx = latestRows.length - 1;
    for (let i = latestRows.length - 1; i >= 0; i--) {
      if (latestRows[i].date <= endValue) {
        endIdx = i;
        break;
      }
    }
    if (startIdx < 0) startIdx = 0;
    const delta = direction === "back" ? -step : step;
    const newStartIdx = Math.max(0, Math.min(latestRows.length - 1, startIdx + delta));
    const newEndIdx = Math.max(newStartIdx, Math.min(latestRows.length - 1, endIdx + delta));
    startEl.value = latestRows[newStartIdx].date;
    endEl.value = latestRows[newEndIdx].date;
    if (chartKind === "equity") {
      equityChartRange = "custom";
      setActiveEquityRangeButton("custom");
      renderBacktestEquityChart();
    } else {
      chartRange = "custom";
      setActiveRangeButton("custom");
      renderChart();
      renderSignalPnlChart();
    }
    updateRangeNudgeStates();
  }

  function nudgeChartWindow(chartKind, stepKey, direction) {
    if (!latestRows.length) return;
    const step = RANGE_SESSIONS[stepKey];
    if (!step) return;
    let range = chartKind === "equity" ? equityChartRange : chartRange;
    let offset = chartKind === "equity" ? equityChartRangeOffset : chartRangeOffset;

    if (range === "custom") {
      nudgeCustomRange(chartKind, step, direction);
      return;
    }

    if (range === "full" && chartKind === "equity") {
      range = stepKey;
      offset = direction === "back" ? step : 0;
    } else if (range !== stepKey) {
      range = stepKey;
      offset = direction === "back" ? step : 0;
    } else {
      offset = direction === "back"
        ? Math.min(maxRangeOffset(stepKey), offset + step)
        : Math.max(0, offset - step);
    }

    if (chartKind === "equity") {
      equityChartRange = range;
      equityChartRangeOffset = offset;
      setActiveEquityRangeButton(range);
      renderBacktestEquityChart();
    } else {
      chartRange = range;
      chartRangeOffset = offset;
      setActiveRangeButton(range);
      renderChart();
      renderSignalPnlChart();
    }
    updateRangeNudgeStates();
  }

  function sliceRowsByRange(range, offset, startInput, endInput, fullStartDate = null) {
    if (!latestRows.length) return [];
    const n = latestRows.length;
    if (range === "custom") {
      const start = startInput?.value;
      const end = endInput?.value;
      return latestRows.filter((row) => (!start || row.date >= start) && (!end || row.date <= end));
    }
    if (range === "full") return fullStartDate ? latestRows.filter((row) => row.date >= fullStartDate) : latestRows.slice();
    const len = RANGE_SESSIONS[range] || n;
    const endExclusive = Math.max(1, n - offset);
    const start = Math.max(0, endExclusive - len);
    return latestRows.slice(start, endExclusive);
  }

  function computeStrategyDrawdownEpisodes() {
    if (!latestRows.length) return [];
    const equity = backtestParameterizedGuarded(latestRows, DEFAULT_GUARDED).equity;
    const episodes = [];
    let peakValue = equity[0];
    let peakDate = latestRows[0].date;
    let inEpisode = false;
    let episodePeakDate = peakDate;
    let episodePeakValue = peakValue;
    let troughDate = peakDate;
    let troughValue = peakValue;

    for (let i = 0; i < latestRows.length; i++) {
      const value = equity[i];
      const date = latestRows[i].date;
      if (value >= peakValue) {
        if (inEpisode) {
          const peakIdx = latestRows.findIndex((row) => row.date === episodePeakDate);
          const troughIdx = latestRows.findIndex((row) => row.date === troughDate);
          episodes.push({
            peakDate: episodePeakDate,
            troughDate,
            recoveryDate: date,
            depth: troughValue / episodePeakValue - 1,
            tradingDays: Math.max(0, troughIdx - peakIdx),
            periodStart: episodePeakDate,
            periodEnd: date,
          });
          inEpisode = false;
        }
        peakValue = value;
        peakDate = date;
        continue;
      }
      if (!inEpisode) {
        inEpisode = true;
        episodePeakDate = peakDate;
        episodePeakValue = peakValue;
        troughDate = date;
        troughValue = value;
      } else if (value < troughValue) {
        troughDate = date;
        troughValue = value;
      }
    }

    if (inEpisode) {
      const lastDate = latestRows[latestRows.length - 1].date;
      const peakIdx = latestRows.findIndex((row) => row.date === episodePeakDate);
      const troughIdx = latestRows.findIndex((row) => row.date === troughDate);
      episodes.push({
        peakDate: episodePeakDate,
        troughDate,
        recoveryDate: null,
        depth: troughValue / episodePeakValue - 1,
        tradingDays: troughIdx - peakIdx,
        periodStart: episodePeakDate,
        periodEnd: lastDate,
      });
    }
    return episodes;
  }

  function renderTopDrawdownsTable() {
    const tbody = $("topDrawdownsBody");
    if (!tbody) return;
    if (!latestRows.length) {
      tbody.innerHTML = '<tr><td colspan="7">Load historical data to compute drawdowns.</td></tr>';
      return;
    }
    const top = computeStrategyDrawdownEpisodes()
      .sort((a, b) => a.depth - b.depth)
      .slice(0, 20);
    if (!top.length) {
      tbody.innerHTML = '<tr><td colspan="7">No drawdown episodes found.</td></tr>';
      return;
    }
    tbody.innerHTML = top.map((episode, index) => {
      const recovery = episode.recoveryDate || "Open";
      const period = `${episode.periodStart} to ${episode.periodEnd}`;
      return `<tr>
        <td>${index + 1}</td>
        <td>${fmtPct(episode.depth)}</td>
        <td>${episode.peakDate}</td>
        <td>${episode.troughDate}</td>
        <td>${recovery}</td>
        <td>${period}</td>
        <td>${episode.tradingDays}</td>
      </tr>`;
    }).join("");
  }

  function setActiveRangeButton(range) {
    document.querySelectorAll("[data-range]").forEach((button) => {
      button.classList.toggle("active", button.dataset.range === range);
    });
  }

  function setActiveEquityRangeButton(range) {
    document.querySelectorAll("[data-equity-range]").forEach((button) => {
      button.classList.toggle("active", button.dataset.equityRange === range);
    });
  }

  function dateTickLimit(length) {
    if (length <= 5) return length;
    if (length <= 21) return Math.min(length, 5);
    if (length <= 63) return 6;
    if (length <= 252) return 7;
    if (length <= 1260) return 9;
    if (length <= 2520) return 11;
    if (length <= 5040) return 13;
    return 15;
  }

  function chartDateTicks(data, xScale) {
    const tickCount = Math.min(dateTickLimit(data.length), data.length);
    const seen = new Set();
    const ticks = [];
    for (let i = 0; i < tickCount; i++) {
      const index = Math.round((i / Math.max(tickCount - 1, 1)) * (data.length - 1));
      if (seen.has(index)) continue;
      seen.add(index);
      const date = data[index].date;
      const parsed = new Date(date + "T00:00:00Z");
      const label = data.length > 1260
        ? String(parsed.getUTCFullYear())
        : parsed.toLocaleDateString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" });
      ticks.push({ index, date, label, x: xScale(index) });
    }
    return ticks;
  }

  function buildTradeAnnotations(rows, leverage) {
    const annotations = Array(rows.length).fill(null);
    const openLegs = [];
    const latest = rows[rows.length - 1];
    const createBaseTrade = (index, prevLev, nextLev) => {
      const isBuy = nextLev > prevLev;
      return {
        type: isBuy ? "buy" : "sell",
        action: isBuy ? "Buy/add" : "Sell/reduce",
        from: prevLev,
        to: nextLev,
        transition: `${fmtLeverageLabel(prevLev)} -> ${fmtLeverageLabel(nextLev)}`,
        reason: isBuy
          ? "Target leverage increased under Guarded A5/B25/X40/Y15 lead-guard logic."
          : "Target leverage decreased under Guarded A5/B25/X40/Y15 lead-guard logic.",
        entryLabel: "",
        exitLabel: "",
        pnlLabel: "",
        detail: "",
      };
    };

    for (let unit = 1; unit <= (leverage[0] || 0); unit++) {
      openLegs.push({ entryIndex: 0, entryDate: rows[0].date, entryClose: rows[0].close, unit });
    }

    for (let index = 1; index < rows.length; index++) {
      const prevLev = leverage[index - 1];
      const nextLev = leverage[index];
      if (nextLev === prevLev) continue;

      const trade = createBaseTrade(index, prevLev, nextLev);
      if (nextLev > prevLev) {
        for (let unit = prevLev + 1; unit <= nextLev; unit++) {
          openLegs.push({ entryIndex: index, entryDate: rows[index].date, entryClose: rows[index].close, unit });
        }
        trade.entryLabel = `entry ${fmtMoney(rows[index].close)}`;
      } else {
        const closedLegs = [];
        for (let count = 0; count < prevLev - nextLev; count++) {
          const leg = openLegs.pop();
          if (leg) {
            leg.exitIndex = index;
            leg.exitDate = rows[index].date;
            leg.exitClose = rows[index].close;
            closedLegs.push(leg);
          }
        }
        if (closedLegs.length) {
          const totalEntry = closedLegs.reduce((sum, leg) => sum + leg.entryClose, 0);
          const avgEntry = totalEntry / closedLegs.length;
          const pnl = (rows[index].close * closedLegs.length) / totalEntry - 1;
          trade.entryLabel = `${closedLegs.length > 1 ? "avg buy entry" : "buy entry"} ${fmtMoney(avgEntry)}`;
          trade.exitLabel = `sell/reduce exit ${fmtMoney(rows[index].close)}`;
          trade.pnlLabel = `${closedLegs.length > 1 ? "Weighted NDX P&L from entry" : "NDX P&L from entry"} ${fmtSignedPct(pnl)}`;
        }
      }
      annotations[index] = trade;
    }

    annotations.forEach((trade, index) => {
      if (!trade || trade.type !== "buy") return;
      const nextSellIndex = annotations.findIndex((candidate, candidateIndex) => (
        candidateIndex > index && candidate?.type === "sell"
      ));
      const exitRow = nextSellIndex >= 0 ? rows[nextSellIndex] : latest;
      const pnl = exitRow.close / rows[index].close - 1;
      trade.exitLabel = nextSellIndex >= 0
        ? `next reduce ${exitRow.date} at ${fmtMoney(exitRow.close)}`
        : `open to ${exitRow.date} at ${fmtMoney(exitRow.close)}`;
      trade.pnlLabel = nextSellIndex >= 0
        ? `NDX P&L to next reduce ${fmtSignedPct(pnl)}`
        : `Open NDX P&L ${fmtSignedPct(pnl)}`;
    });

    annotations.forEach((trade) => {
      if (!trade) return;
      trade.detail = [trade.entryLabel, trade.exitLabel, trade.pnlLabel].filter(Boolean).join("; ");
    });
    return annotations;
  }

  function chartDataForRange() {
    if (!latestRows.length) return [];
    const closes = latestRows.map((row) => row.close);
    const leverage = guardedLeverageForParams(latestRows, DEFAULT_GUARDED).leverage;
    const trades = buildTradeAnnotations(latestRows, leverage);
    const fullData = latestRows.map((row, index) => ({
      index,
      date: row.date,
      close: row.close,
      sma: sma(closes, index, 20),
      leverage: leverage[index],
      prevLeverage: index > 0 ? leverage[index - 1] : 0,
      trade: trades[index]
    }));
    const rows = sliceRowsByRange(chartRange, chartRangeOffset, $("chartStart"), $("chartEnd"));
    const allowed = new Set(rows.map((row) => row.date));
    return fullData.filter((row) => allowed.has(row.date));
  }

  function tradeMarkerColor(trade) {
    if (trade.type === "buy") return trade.to >= 2 ? "#2563eb" : "#15803d";
    return trade.to <= 0 ? "#b42318" : "#b45309";
  }

  function tradePnlDetail(trade) {
    return trade?.pnlLabel || "Trade P&L from matched entry unavailable";
  }

  function renderChart() {
    const svg = $("priceChart");
    const data = chartDataForRange();
    if (!svg || !latestRows.length) return;
    if (data.length < 2) {
      svg.innerHTML = "";
      chartPoints = [];
      chartPlot = null;
      $("chartMeta").textContent = "Choose a wider date range to draw the chart.";
      return;
    }

    const width = 900;
    const height = 360;
    const pad = { left: 66, right: 24, top: 24, bottom: 54 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const values = data.flatMap((point) => Number.isFinite(point.sma) ? [point.close, point.sma] : [point.close]);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const buffer = (maxValue - minValue) * 0.06 || maxValue * 0.02;
    const yMin = minValue - buffer;
    const yMax = maxValue + buffer;
    const xScale = (index) => pad.left + (index / Math.max(data.length - 1, 1)) * plotWidth;
    const yScale = (value) => pad.top + ((yMax - value) / (yMax - yMin)) * plotHeight;
    const linePath = (selector) => data
      .map((point, index) => {
        const value = selector(point);
        return Number.isFinite(value) ? `${xScale(index).toFixed(2)},${yScale(value).toFixed(2)}` : null;
      })
      .filter(Boolean)
      .join(" ");
    chartPlot = {
      left: pad.left,
      right: width - pad.right,
      top: pad.top,
      bottom: height - pad.bottom,
      width,
      height,
    };
    const visibleTradeCount = data.filter((point) => point.trade).length;
    const showTransitionLabels = visibleTradeCount > 0 && visibleTradeCount <= 25;
    const markerForPoint = (point, index) => {
      if (!point.trade) return "";
      const x = xScale(index).toFixed(2);
      const y = yScale(point.close).toFixed(2);
      const color = tradeMarkerColor(point.trade);
      const shape = point.trade.type === "buy"
        ? '<polygon points="0,-6 -5,4.5 5,4.5" />'
        : '<polygon points="-5,-4.5 5,-4.5 0,6" />';
      const labelY = point.trade.type === "buy" ? -12 : 20;
      const compactLabel = fmtMarkerLeverageLabel(point.trade.to);
      const label = showTransitionLabels
        ? `<g transform="translate(0 ${labelY})">
            <rect x="-11" y="-8" width="22" height="14" rx="7" fill="#ffffff" stroke="${color}" stroke-width="1.1" />
            <text x="0" y="2.5" fill="${color}" stroke="none" font-size="9" font-weight="800" text-anchor="middle">${compactLabel}</text>
          </g>`
        : "";
      const title = `${point.trade.action} on ${point.date}: ${point.trade.transition} at close ${fmtMoney(point.close)}. ${point.trade.detail}. ${point.trade.reason}`;
      return `
        <g transform="translate(${x} ${y})" fill="${color}" stroke="#ffffff" stroke-width="1.6" aria-label="${escapeSvgText(title)}">
          <title>${escapeSvgText(title)}</title>
          ${shape}
          ${label}
        </g>
      `;
    };

    chartPoints = data.map((point, index) => ({
      ...point,
      x: xScale(index),
      y: yScale(point.close)
    }));

    const grid = [];
    for (let i = 0; i <= 4; i++) {
      const value = yMin + ((yMax - yMin) * i) / 4;
      const y = yScale(value);
      grid.push(`
        <line x1="${pad.left}" y1="${y.toFixed(2)}" x2="${width - pad.right}" y2="${y.toFixed(2)}" stroke="#e5e7eb" stroke-width="1" />
        <text x="${pad.left - 10}" y="${(y + 4).toFixed(2)}" fill="#667085" font-size="12" font-weight="600" text-anchor="end">${fmtWholeNumber(value)}</text>
      `);
    }

    const startDate = data[0].date;
    const endDate = data[data.length - 1].date;
    const xTicks = chartDateTicks(data, xScale);
    const xGrid = xTicks.map((tick, index) => {
      const anchor = index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle";
      return `
        <line x1="${tick.x.toFixed(2)}" y1="${pad.top}" x2="${tick.x.toFixed(2)}" y2="${height - pad.bottom}" stroke="#eef0f3" stroke-width="1" />
        <line x1="${tick.x.toFixed(2)}" y1="${height - pad.bottom}" x2="${tick.x.toFixed(2)}" y2="${height - pad.bottom + 5}" stroke="#98a2b3" stroke-width="1" />
        <text x="${tick.x.toFixed(2)}" y="${height - 18}" fill="#667085" font-size="12" font-weight="600" text-anchor="${anchor}">${tick.label}</text>
      `;
    });
    svg.innerHTML = `
      <defs>
        <clipPath id="pricePlotClip"><rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" /></clipPath>
      </defs>
      <rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" rx="12" fill="#ffffff" stroke="#e5e7eb" />
      ${xGrid.join("")}
      ${grid.join("")}
      <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <g clip-path="url(#pricePlotClip)">
        <polyline points="${linePath((point) => point.close)}" fill="none" stroke="#2563eb" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        <polyline points="${linePath((point) => point.sma)}" fill="none" stroke="#d97706" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
        ${data.map(markerForPoint).join("")}
      </g>
    `;
    $("chartMeta").textContent = `${data.length} trading sessions shown: ${startDate} to ${endDate}. Latest close ${fmtMoney(data[data.length - 1].close)}, SMA20 ${fmtMoney(data[data.length - 1].sma)}.`;
  }

  function hideChartTooltip() {
    $("chartTooltip").style.display = "none";
  }

  function showChartTooltip(event) {
    if (!chartPoints.length || !chartPlot) return;
    const svg = $("priceChart");
    const rect = svg.getBoundingClientRect();
    const ctm = svg.getScreenCTM();
    if (!ctm) {
      hideChartTooltip();
      return;
    }
    const svgPoint = svg.createSVGPoint();
    svgPoint.x = event.clientX;
    svgPoint.y = event.clientY;
    const cursor = svgPoint.matrixTransform(ctm.inverse());
    const svgX = cursor.x;
    const svgY = cursor.y;
    if (
      svgX < chartPlot.left ||
      svgX > chartPlot.right ||
      svgY < chartPlot.top ||
      svgY > chartPlot.bottom
    ) {
      hideChartTooltip();
      return;
    }

    const ratio = (svgX - chartPlot.left) / (chartPlot.right - chartPlot.left);
    const index = Math.max(0, Math.min(chartPoints.length - 1, Math.round(ratio * (chartPoints.length - 1))));
    const nearest = chartPoints[index];
    const tooltip = $("chartTooltip");
    tooltip.innerHTML = `
      <strong>${nearest.date}</strong><br>
      Close: ${fmtMoney(nearest.close)}<br>
      SMA20: ${fmtMoney(nearest.sma)}
      ${nearest.trade ? `<br><span style="color: ${nearest.trade.type === "buy" ? "#15803d" : "#b42318"}; font-weight: 700;">${nearest.trade.action}: ${nearest.trade.transition}</span><br>${nearest.trade.detail}<br>${nearest.trade.reason}` : ""}
    `;
    tooltip.style.display = "block";
    const tooltipWidth = Math.max(tooltip.offsetWidth, 190);
    const tooltipHeight = Math.max(tooltip.offsetHeight, 64);
    const chartWidth = chartPlot.width || 900;
    const chartHeight = chartPlot.height || 360;
    const plotLeftPx = (chartPlot.left / chartWidth) * rect.width;
    const plotRightPx = (chartPlot.right / chartWidth) * rect.width;
    const pointerX = (nearest.x / chartWidth) * rect.width;
    const pointerY = (nearest.y / chartHeight) * rect.height;
    const openRight = pointerX + tooltipWidth + 18 < plotRightPx;
    const left = openRight ? pointerX + 14 : Math.max(plotLeftPx, pointerX - tooltipWidth - 14);
    const top = Math.max(10, Math.min(pointerY - tooltipHeight - 10, rect.height - tooltipHeight - 10));
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }

  function selectedWindowPnlData() {
    const selected = chartDataForRange();
    if (selected.length < 2) {
      return { points: [], meta: "Choose a wider date range to draw selected-window equity P&L." };
    }

    const entryOffset = selected.findIndex((point) => point.leverage > 0 && point.prevLeverage <= 0);
    let startOffset = entryOffset;
    let startReason = "first in-window entry";
    if (startOffset < 0) {
      startOffset = selected.findIndex((point) => point.leverage > 0);
      startReason = "already active at first selected exposure";
    }
    if (startOffset < 0) {
      const startDate = selected[0].date;
      const endDate = selected[selected.length - 1].date;
      return {
        points: [],
        meta: `No default strategy market exposure from ${startDate} to ${endDate}; widen the range or choose a period with leverage above cash.`,
      };
    }

    const active = selected.slice(startOffset);
    if (active.length < 2) {
      return {
        points: [],
        meta: `Entry found on ${active[0].date} at ${fmtLeverageLabel(active[0].leverage)}, but at least one later session is needed to draw P&L.`,
      };
    }

    let strategy = INITIAL_CAPITAL;
    let spx = INITIAL_CAPITAL;
    let prevLev = active[0].leverage;
    let tradingCosts = 0;
    let rebalances = 0;
    const dailyCash = DEFAULT_GUARDED.cashRate / TRADING_DAYS;
    const points = [{
      date: active[0].date,
      strategy,
      spx,
      close: active[0].close,
      leverage: active[0].leverage,
      dailyReturn: 0,
      trade: active[0].trade,
    }];

    for (let i = 1; i < active.length; i++) {
      const point = active[i];
      const prevPoint = active[i - 1];
      const lev = point.leverage;
      if (Math.abs(lev - prevLev) > 1e-9) {
        const cost = Math.abs(lev - prevLev) * strategy * DEFAULT_GUARDED.tradingCost;
        strategy -= cost;
        tradingCosts += cost;
        rebalances += 1;
        prevLev = lev;
      }

      const spxReturn = point.close / prevPoint.close - 1;
      const funding = lev > 1 ? (lev - 1) * DEFAULT_GUARDED.cashRate / TRADING_DAYS : 0;
      const dailyReturn = lev <= 0 ? dailyCash : lev * spxReturn - funding;
      strategy *= 1 + dailyReturn;
      spx *= 1 + spxReturn;
      points.push({
        date: point.date,
        strategy,
        spx,
        close: point.close,
        leverage: lev,
        dailyReturn,
        trade: point.trade,
      });
    }

    const first = active[0];
    const last = points[points.length - 1];
    const transition = `${fmtLeverageLabel(first.prevLeverage)} -> ${fmtLeverageLabel(first.leverage)}`;
    const entryLabel = entryOffset >= 0 ? transition : fmtLeverageLabel(first.leverage);
    const windowReturn = last.strategy / active[0].strategy - 1;
    const benchmarkReturn = last.spx / active[0].spx - 1;
    const costLabel = rebalances
      ? `Includes ${fmtWholeCurrency(tradingCosts)} in subsequent rebalance costs`
      : "No subsequent rebalance costs";
    return {
      points,
      meta: `Starts ${first.date} at ${entryLabel} (${startReason}); chart rebased to 0% at window start. Strategy ${fmtSignedPct(windowReturn)} vs Gold ${fmtSignedPct(benchmarkReturn)} through ${last.date}. ${costLabel}.`,
    };
  }

  function hideSignalPnlTooltip() {
    $("signalPnlTooltip").style.display = "none";
    const hoverLayer = $("signalPnlHoverLayer");
    if (hoverLayer) hoverLayer.style.display = "none";
  }

  function renderSignalPnlChart() {
    const svg = $("signalPnlChart");
    if (!svg || !latestRows.length) return;
    const { points, meta } = selectedWindowPnlData();
    if (points.length < 2) {
      svg.innerHTML = "";
      signalPnlPoints = [];
      signalPnlPlot = null;
      $("signalPnlMeta").textContent = meta;
      return;
    }

    const rebased = rebaseEquityToReturns(points.map((point) => ({
      date: point.date,
      strategy: point.strategy,
      spx: point.spx,
    }))).map((point, index) => ({
      ...points[index],
      ...point,
    }));

    const width = 900;
    const height = 260;
    const pad = { left: 64, right: 22, top: 18, bottom: 40 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const returns = rebased.flatMap((point) => [point.strategyReturn, point.spxReturn]).filter(Number.isFinite);
    let yMin = Math.min(...returns, 0);
    let yMax = Math.max(...returns, 0);
    const buffer = Math.max((yMax - yMin) * 0.1, 0.02);
    yMin -= buffer;
    yMax += buffer;
    const returnRange = Math.max(yMax - yMin, 1e-9);
    const xScale = (index) => pad.left + (index / Math.max(rebased.length - 1, 1)) * plotWidth;
    const yScale = (ratio) => pad.top + ((yMax - ratio) / returnRange) * plotHeight;
    const linePath = (selector) => rebased
      .map((point, index) => {
        const value = selector(point);
        return Number.isFinite(value) ? `${xScale(index).toFixed(2)},${yScale(value).toFixed(2)}` : null;
      })
      .filter(Boolean)
      .join(" ");

    signalPnlPlot = {
      left: pad.left,
      right: width - pad.right,
      top: pad.top,
      bottom: height - pad.bottom,
      width,
      height,
    };
    signalPnlPoints = rebased.map((point, index) => ({
      ...point,
      x: xScale(index),
      strategyY: yScale(point.strategyReturn),
      spxY: yScale(point.spxReturn),
    }));
    const visibleTradeCount = points.filter((point) => point.trade).length;
    const showTransitionLabels = visibleTradeCount > 0 && visibleTradeCount <= 18;
    const markerForPoint = (point, index) => {
      if (!point.trade) return "";
      const x = xScale(index).toFixed(2);
      const y = yScale(point.strategyReturn).toFixed(2);
      const color = tradeMarkerColor(point.trade);
      const shape = point.trade.type === "buy"
        ? '<polygon points="0,-5.5 -4.5,4 4.5,4" />'
        : '<polygon points="-4.5,-4 4.5,-4 0,5.5" />';
      const labelY = point.trade.type === "buy" ? -11 : 18;
      const compactLabel = fmtMarkerLeverageLabel(point.trade.to);
      const label = showTransitionLabels
        ? `<g transform="translate(0 ${labelY})">
            <rect x="-10" y="-7" width="20" height="13" rx="6.5" fill="#ffffff" stroke="${color}" stroke-width="1" />
            <text x="0" y="2.2" fill="${color}" stroke="none" font-size="8.5" font-weight="800" text-anchor="middle">${compactLabel}</text>
          </g>`
        : "";
      const title = `${point.trade.action} on ${point.date}: strategy equity ${fmtWholeCurrency(point.strategy)}; ${point.trade.transition}; ${tradePnlDetail(point.trade)}. ${point.trade.reason}`;
      return `
        <g transform="translate(${x} ${y})" fill="${color}" stroke="#ffffff" stroke-width="1.4" aria-label="${escapeSvgText(title)}">
          <title>${escapeSvgText(title)}</title>
          ${shape}
          ${label}
        </g>
      `;
    };

    const yTicks = returnAxisTicks(yMin, yMax);
    const zeroLine = yMin <= 0 && yMax >= 0
      ? `<line x1="${pad.left}" y1="${yScale(0).toFixed(2)}" x2="${width - pad.right}" y2="${yScale(0).toFixed(2)}" stroke="#98a2b3" stroke-width="1.2" stroke-dasharray="5 4" />`
      : "";
    const yGrid = yTicks.map((value) => {
      const y = yScale(value);
      const isZero = Math.abs(value) < 1e-9;
      return `
        <line x1="${pad.left}" y1="${y.toFixed(2)}" x2="${width - pad.right}" y2="${y.toFixed(2)}" stroke="${isZero ? "#d0d5dd" : "#e5e7eb"}" stroke-width="1" />
        <text x="${pad.left - 10}" y="${(y + 4).toFixed(2)}" fill="#667085" font-size="12" font-weight="600" text-anchor="end">${fmtReturnAxis(value)}</text>
      `;
    });
    const xTicks = chartDateTicks(rebased, xScale);
    const xGrid = xTicks.map((tick, index) => {
      const anchor = index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle";
      return `
        <line x1="${tick.x.toFixed(2)}" y1="${pad.top}" x2="${tick.x.toFixed(2)}" y2="${height - pad.bottom}" stroke="#eef0f3" stroke-width="1" />
        <text x="${tick.x.toFixed(2)}" y="${height - 14}" fill="#667085" font-size="12" font-weight="600" text-anchor="${anchor}">${tick.label}</text>
      `;
    });

    svg.innerHTML = `
      <defs>
        <clipPath id="signalPnlPlotClip"><rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" /></clipPath>
      </defs>
      <rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" rx="12" fill="#ffffff" stroke="#e5e7eb" />
      ${xGrid.join("")}
      ${yGrid.join("")}
      ${zeroLine}
      <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <g clip-path="url(#signalPnlPlotClip)">
        <polyline points="${linePath((point) => point.strategyReturn)}" fill="none" stroke="#2563eb" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />
        <polyline points="${linePath((point) => point.spxReturn)}" fill="none" stroke="#d97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        ${rebased.map(markerForPoint).join("")}
      </g>
      <g id="signalPnlHoverLayer" style="display: none;">
        <line id="signalPnlHoverLine" x1="0" y1="${pad.top}" x2="0" y2="${height - pad.bottom}" stroke="#475467" stroke-width="1" stroke-dasharray="4 4" />
        <circle id="signalPnlHoverStrategy" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />
        <circle id="signalPnlHoverSpx" r="4" fill="#d97706" stroke="#ffffff" stroke-width="2" />
      </g>
      <rect id="signalPnlHoverCapture" x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent" pointer-events="all" />
    `;
    const hoverCapture = $("signalPnlHoverCapture");
    if (hoverCapture) {
      hoverCapture.addEventListener("mousemove", showSignalPnlTooltip);
      hoverCapture.addEventListener("mouseleave", hideSignalPnlTooltip);
    }
    $("signalPnlMeta").textContent = meta;
  }

  function showSignalPnlTooltip(event) {
    if (!signalPnlPoints.length || !signalPnlPlot) return;
    const svg = $("signalPnlChart");
    const rect = svg.getBoundingClientRect();
    const ctm = svg.getScreenCTM();
    if (!ctm) {
      hideSignalPnlTooltip();
      return;
    }
    const chartWidth = signalPnlPlot.width || 900;
    const chartHeight = signalPnlPlot.height || 260;
    const svgPoint = svg.createSVGPoint();
    svgPoint.x = event.clientX;
    svgPoint.y = event.clientY;
    const cursor = svgPoint.matrixTransform(ctm.inverse());
    const svgX = cursor.x;
    const svgY = cursor.y;
    if (
      svgX < signalPnlPlot.left ||
      svgX > signalPnlPlot.right ||
      svgY < signalPnlPlot.top ||
      svgY > signalPnlPlot.bottom
    ) {
      hideSignalPnlTooltip();
      return;
    }

    const ratio = (svgX - signalPnlPlot.left) / (signalPnlPlot.right - signalPnlPlot.left);
    const index = Math.max(0, Math.min(signalPnlPoints.length - 1, Math.round(ratio * (signalPnlPoints.length - 1))));
    const nearest = signalPnlPoints[index];
    const nearestX = nearest.x;
    const hoverLayer = $("signalPnlHoverLayer");
    if (hoverLayer) {
      hoverLayer.style.display = "block";
      $("signalPnlHoverLine").setAttribute("x1", nearestX.toFixed(2));
      $("signalPnlHoverLine").setAttribute("x2", nearestX.toFixed(2));
      $("signalPnlHoverStrategy").setAttribute("cx", nearestX.toFixed(2));
      $("signalPnlHoverStrategy").setAttribute("cy", nearest.strategyY.toFixed(2));
      $("signalPnlHoverSpx").setAttribute("cx", nearestX.toFixed(2));
      $("signalPnlHoverSpx").setAttribute("cy", nearest.spxY.toFixed(2));
    }

    const tooltip = $("signalPnlTooltip");
    tooltip.innerHTML = `
      <strong>${nearest.date}</strong><br>
      Strategy: ${fmtSignedPct(nearest.strategyReturn)}<br>
      Gold buy &amp; hold: ${fmtSignedPct(nearest.spxReturn)}<br>
      Leverage: ${fmtLeverageLabel(nearest.leverage)}
      ${nearest.trade ? `<br><span style="color: ${tradeMarkerColor(nearest.trade)}; font-weight: 700;">${nearest.trade.action}: ${nearest.trade.transition}</span><br>${tradePnlDetail(nearest.trade)}` : ""}
    `;
    tooltip.style.display = "block";
    const tooltipWidth = Math.max(tooltip.offsetWidth, 235);
    const tooltipHeight = Math.max(tooltip.offsetHeight, 78);
    const plotLeftPx = (signalPnlPlot.left / chartWidth) * rect.width;
    const plotRightPx = (signalPnlPlot.right / chartWidth) * rect.width;
    const pointerX = (nearestX / chartWidth) * rect.width;
    const pointerY = (Math.min(nearest.strategyY, nearest.spxY) / chartHeight) * rect.height;
    const openRight = pointerX + tooltipWidth + 18 < plotRightPx;
    const left = openRight ? pointerX + 14 : Math.max(plotLeftPx, pointerX - tooltipWidth - 14);
    const top = Math.max(10, Math.min(pointerY - tooltipHeight - 10, rect.height - tooltipHeight - 10));
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }

  function buyHoldWithInflows(rows) {
    let value = INITIAL_CAPITAL;
    let prevYear = new Date(rows[0].date).getUTCFullYear();
    const equity = [];
    for (let i = 0; i < rows.length; i++) {
      const year = new Date(rows[i].date).getUTCFullYear();
      if (i > 0 && year !== prevYear) value += ANNUAL_INFLOW;
      if (i > 0) value *= rows[i].close / rows[i - 1].close;
      equity.push(value);
      prevYear = year;
    }
    return equity;
  }

  function latestRowsSourceLabel() {
    if (latestRowsSource === "static") return "Static historical back-test data loaded";
    if (latestRowsSource === "live") return "Updated from refreshed daily data";
    return "Historical data loaded";
  }

  function equityDataForRange() {
    if (!latestRows.length) return [];
    const strategy = backtestParameterizedGuarded(latestRows, DEFAULT_GUARDED).equity;
    const spx = buyHoldWithInflows(latestRows);
    const fullData = latestRows.map((row, index) => ({
      date: row.date,
      strategy: strategy[index],
      spx: spx[index],
    }));
    const rows = sliceRowsByRange(equityChartRange, equityChartRangeOffset, $("equityChartStart"), $("equityChartEnd"), staticSiteData?.sample?.start_date);
    const allowed = new Set(rows.map((row) => row.date));
    return fullData.filter((row) => allowed.has(row.date));
  }

  function rebaseEquityToReturns(data) {
    if (!data.length) return [];
    const baseStrategy = data[0].strategy;
    const baseSpx = data[0].spx;
    return data.map((point) => ({
      ...point,
      strategyReturn: baseStrategy > 0 ? point.strategy / baseStrategy - 1 : 0,
      spxReturn: baseSpx > 0 ? point.spx / baseSpx - 1 : 0,
    }));
  }

  function nicePercentStep(spanPct, targetTicks = 6) {
    const raw = spanPct / Math.max(targetTicks - 1, 1);
    if (!Number.isFinite(raw) || raw <= 0) return 1;
    const exponent = Math.floor(Math.log10(raw));
    const base = Math.pow(10, exponent);
    const fraction = raw / base;
    const multiplier = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
    return multiplier * base;
  }

  function returnAxisTicks(minReturn, maxReturn, maxTicks = 7) {
    const minPct = minReturn * 100;
    const maxPct = maxReturn * 100;
    const span = Math.max(maxPct - minPct, 1e-9);
    const step = nicePercentStep(span, maxTicks);
    const ticks = [];
    const start = Math.floor(minPct / step) * step;
    for (let pct = start; pct <= maxPct + step * 0.001; pct += step) {
      ticks.push(pct / 100);
      if (ticks.length >= maxTicks + 1) break;
    }
    if (minReturn <= 0 && maxReturn >= 0 && !ticks.some((tick) => Math.abs(tick) < 1e-9)) {
      ticks.push(0);
    }
    const unique = [...new Set(ticks.map((tick) => Math.round(tick * 1e6) / 1e6))].sort((a, b) => a - b);
    if (unique.length <= maxTicks + 1) return unique;
    const stride = Math.ceil(unique.length / maxTicks);
    return unique.filter((_, index) => index % stride === 0 || index === unique.length - 1);
  }

  function fmtReturnAxis(ratio) {
    const pct = ratio * 100;
    if (Math.abs(pct) < 0.05) return "0%";
    const sign = pct >= 0 ? "+" : "";
    const abs = Math.abs(pct);
    if (abs >= 10000) return `${sign}${Math.round(abs / 1000)}k%`;
    if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k%`;
    const digits = abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
    return `${sign}${abs.toFixed(digits)}%`;
  }

  function hideEquityChartTooltip() {
    $("equityChartTooltip").style.display = "none";
    const hoverLayer = $("equityHoverLayer");
    if (hoverLayer) hoverLayer.style.display = "none";
  }

  function renderBacktestEquityChart() {
    const svg = $("equityChart");
    if (!svg || !latestRows.length) return;
    const data = rebaseEquityToReturns(equityDataForRange());
    if (data.length < 2) {
      svg.innerHTML = "";
      equityChartPoints = [];
      equityChartPlot = null;
      $("equityChartMeta").textContent = "Choose a wider date range to draw the equity chart.";
      return;
    }

    const width = 900;
    const height = 360;
    const pad = { left: 76, right: 24, top: 24, bottom: 54 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const returns = data.flatMap((point) => [point.strategyReturn, point.spxReturn]).filter(Number.isFinite);
    let yMin = Math.min(...returns, 0);
    let yMax = Math.max(...returns, 0);
    const buffer = Math.max((yMax - yMin) * 0.1, 0.02);
    yMin -= buffer;
    yMax += buffer;
    const returnRange = Math.max(yMax - yMin, 1e-9);
    const xScale = (index) => pad.left + (index / Math.max(data.length - 1, 1)) * plotWidth;
    const yScale = (ratio) => pad.top + ((yMax - ratio) / returnRange) * plotHeight;
    const linePath = (selector) => data
      .map((point, index) => `${xScale(index).toFixed(2)},${yScale(selector(point)).toFixed(2)}`)
      .join(" ");

    equityChartPlot = {
      left: pad.left,
      right: width - pad.right,
      top: pad.top,
      bottom: height - pad.bottom,
      width,
      height,
    };
    equityChartPoints = data.map((point, index) => ({
      ...point,
      x: xScale(index),
      strategyY: yScale(point.strategyReturn),
      spxY: yScale(point.spxReturn),
    }));

    const yTicks = returnAxisTicks(yMin, yMax);
    const zeroLine = yMin <= 0 && yMax >= 0
      ? `<line x1="${pad.left}" y1="${yScale(0).toFixed(2)}" x2="${width - pad.right}" y2="${yScale(0).toFixed(2)}" stroke="#98a2b3" stroke-width="1.2" stroke-dasharray="5 4" />`
      : "";
    const yGrid = yTicks.map((value) => {
      const y = yScale(value);
      const isZero = Math.abs(value) < 1e-9;
      return `
        <line x1="${pad.left}" y1="${y.toFixed(2)}" x2="${width - pad.right}" y2="${y.toFixed(2)}" stroke="${isZero ? "#d0d5dd" : "#e5e7eb"}" stroke-width="1" />
        <text x="${pad.left - 12}" y="${(y + 4).toFixed(2)}" fill="#667085" font-size="12" font-weight="600" text-anchor="end">${fmtReturnAxis(value)}</text>
      `;
    });
    const xTicks = chartDateTicks(data, xScale);
    const xGrid = xTicks.map((tick, index) => {
      const anchor = index === 0 ? "start" : index === xTicks.length - 1 ? "end" : "middle";
      return `
        <line x1="${tick.x.toFixed(2)}" y1="${pad.top}" x2="${tick.x.toFixed(2)}" y2="${height - pad.bottom}" stroke="#eef0f3" stroke-width="1" />
        <line x1="${tick.x.toFixed(2)}" y1="${height - pad.bottom}" x2="${tick.x.toFixed(2)}" y2="${height - pad.bottom + 5}" stroke="#98a2b3" stroke-width="1" />
        <text x="${tick.x.toFixed(2)}" y="${height - 18}" fill="#667085" font-size="12" font-weight="600" text-anchor="${anchor}">${tick.label}</text>
      `;
    });

    const startDate = data[0].date;
    const endDate = data[data.length - 1].date;
    svg.innerHTML = `
      <defs>
        <clipPath id="equityPlotClip"><rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" /></clipPath>
      </defs>
      <rect x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" rx="12" fill="#ffffff" stroke="#e5e7eb" />
      ${xGrid.join("")}
      ${yGrid.join("")}
      ${zeroLine}
      <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#98a2b3" stroke-width="1.2" />
      <g clip-path="url(#equityPlotClip)">
        <polyline points="${linePath((point) => point.strategyReturn)}" fill="none" stroke="#2563eb" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />
        <polyline points="${linePath((point) => point.spxReturn)}" fill="none" stroke="#d97706" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      </g>
      <g id="equityHoverLayer" style="display: none;">
        <line id="equityHoverLine" x1="0" y1="${pad.top}" x2="0" y2="${height - pad.bottom}" stroke="#475467" stroke-width="1" stroke-dasharray="4 4" />
        <circle id="equityHoverStrategy" r="4.5" fill="#2563eb" stroke="#ffffff" stroke-width="2" />
        <circle id="equityHoverSpx" r="4" fill="#d97706" stroke="#ffffff" stroke-width="2" />
      </g>
      <rect id="equityHoverCapture" x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent" pointer-events="all" />
    `;
    const hoverCapture = $("equityHoverCapture");
    if (hoverCapture) {
      hoverCapture.addEventListener("mousemove", showEquityChartTooltip);
      hoverCapture.addEventListener("mouseleave", hideEquityChartTooltip);
    }
    const last = data[data.length - 1];
    $("equityChartMeta").textContent = `${latestRowsSourceLabel()}; ${data.length} trading sessions from ${startDate} to ${endDate}. Cumulative return rebased to 0% at range start: strategy ${fmtSignedPct(last.strategyReturn)} vs Gold buy &amp; hold ${fmtSignedPct(last.spxReturn)}.`;
  }

  function showEquityChartTooltip(event) {
    if (!equityChartPoints.length || !equityChartPlot) return;
    const svg = $("equityChart");
    const rect = svg.getBoundingClientRect();
    const chartWidth = equityChartPlot.width || 900;
    const chartHeight = equityChartPlot.height || 360;
    const svgPoint = svg.createSVGPoint();
    svgPoint.x = event.clientX;
    svgPoint.y = event.clientY;
    const cursor = svgPoint.matrixTransform(svg.getScreenCTM().inverse());
    const svgX = cursor.x;
    const svgY = cursor.y;
    if (
      svgX < equityChartPlot.left ||
      svgX > equityChartPlot.right ||
      svgY < equityChartPlot.top ||
      svgY > equityChartPlot.bottom
    ) {
      hideEquityChartTooltip();
      return;
    }

    const ratio = (svgX - equityChartPlot.left) / (equityChartPlot.right - equityChartPlot.left);
    const index = Math.max(0, Math.min(equityChartPoints.length - 1, Math.round(ratio * (equityChartPoints.length - 1))));
    const nearest = equityChartPoints[index];
    const nearestX = nearest.x;
    const hoverLayer = $("equityHoverLayer");
    if (hoverLayer) {
      hoverLayer.style.display = "block";
      $("equityHoverLine").setAttribute("x1", nearestX.toFixed(2));
      $("equityHoverLine").setAttribute("x2", nearestX.toFixed(2));
      $("equityHoverStrategy").setAttribute("cx", nearestX.toFixed(2));
      $("equityHoverStrategy").setAttribute("cy", nearest.strategyY.toFixed(2));
      $("equityHoverSpx").setAttribute("cx", nearestX.toFixed(2));
      $("equityHoverSpx").setAttribute("cy", nearest.spxY.toFixed(2));
    }

    const tooltip = $("equityChartTooltip");
    tooltip.innerHTML = `
      <strong>${nearest.date}</strong><br>
      Default strategy: ${fmtSignedPct(nearest.strategyReturn)}<br>
      Gold buy &amp; hold: ${fmtSignedPct(nearest.spxReturn)}
    `;
    tooltip.style.display = "block";
    const tooltipWidth = Math.max(tooltip.offsetWidth, 220);
    const tooltipHeight = Math.max(tooltip.offsetHeight, 64);
    const plotLeftPx = (equityChartPlot.left / chartWidth) * rect.width;
    const plotRightPx = (equityChartPlot.right / chartWidth) * rect.width;
    const pointerX = (nearestX / chartWidth) * rect.width;
    const pointerY = (Math.min(nearest.strategyY, nearest.spxY) / chartHeight) * rect.height;
    const openRight = pointerX + tooltipWidth + 18 < plotRightPx;
    const left = openRight ? pointerX + 14 : Math.max(plotLeftPx, pointerX - tooltipWidth - 14);
    const top = Math.max(10, Math.min(pointerY - tooltipHeight - 10, rect.height - tooltipHeight - 10));
    tooltip.style.left = left + "px";
    tooltip.style.top = top + "px";
  }

  function renderSignal(prefix, result) {
    const lev = $(prefix + "Leverage");
    lev.textContent = result.targetLeverage.toFixed(0) + "x";
    lev.className =
      "stat-value signal " + (result.targetLeverage >= 3 ? "bad" : result.targetLeverage >= 2 ? "warn" : "good");
    $(prefix + "Explanation").textContent = result.explanation;
    $(prefix + "Date").textContent = result.latest.date;
    $(prefix + "Close").textContent = fmtMoney(result.latest.close);
    $(prefix + "Sma20").textContent = fmtMoney(result.latestSma);
    $(prefix + "Sma20Gap").textContent = Number.isFinite(result.latestSma)
      ? fmtPct(result.latest.close / result.latestSma - 1)
      : "-";
    $(prefix + "Drawdown").textContent = fmtPct(result.latestDd);
    $(prefix + "Regime").textContent = result.regime;
    $(prefix + "LastEntryLevel").textContent = result.activeEntryClose == null
      ? "-"
      : `${fmtMoney(result.activeEntryClose)} (${result.activeEntryLeverage.toFixed(0)}x, ${result.activeEntryDate})`;
    $(prefix + "LastEntryPnl").textContent = fmtPct(result.activeEntryPnl);
    $(prefix + "RecoveryTarget").textContent = result.recoveryTarget == null ? "-" : fmtMoney(result.recoveryTarget);
    $(prefix + "RecoveryTargetGap").textContent = result.recoveryTarget == null
      ? "-"
      : fmtPct(result.recoveryTarget / result.latest.close - 1);
  }

  startAutoRefresh();
  updateRangeNudgeStates();
  loadStaticHistoricalBacktest().then(() => refresh({ reason: "initial live", allowManualOverride: false, force: true }));