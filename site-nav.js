/** Shared hash/query routing for Strategy site tabs (static GitHub Pages). */
(function () {
  const PAGE_IDS = new Set([
    "signalPage",
    "backtestPage",
    "monteCarloPage",
    "instrumentsPage",
    "momentumSignalPage",
    "momentumBacktestPage",
    "momentumMonteCarloPage",
  ]);
  const STRATEGY_IDS = new Set(["guardedStrategy", "momentumStrategy"]);
  const PAGE_QUERY = {
    signal: "signalPage",
    backtest: "backtestPage",
    "monte-carlo": "monteCarloPage",
    montecarlo: "monteCarloPage",
    instruments: "instrumentsPage",
  };
  const STRATEGY_QUERY = {
    spx: "guardedStrategy",
    guarded: "guardedStrategy",
    momentum: "momentumStrategy",
  };

  function hashId(loc = location) {
    return (loc.hash || "").replace(/^#/, "");
  }

  function pageFromLocation(loc = location) {
    const id = hashId(loc);
    if (PAGE_IDS.has(id)) return id;
    const page = new URLSearchParams(loc.search).get("page");
    if (page) {
      const mapped = PAGE_QUERY[String(page).toLowerCase()];
      if (mapped) return mapped;
    }
    return null;
  }

  function strategyFromLocation(loc = location) {
    const id = hashId(loc);
    if (STRATEGY_IDS.has(id)) return id;
    const strategy = new URLSearchParams(loc.search).get("strategy");
    if (strategy) {
      const mapped = STRATEGY_QUERY[String(strategy).toLowerCase()];
      if (mapped) return mapped;
    }
    return null;
  }

  function strategyForPage(pageId) {
    if (!pageId) return null;
    if (pageId.startsWith("momentum")) return "momentumStrategy";
    if (PAGE_IDS.has(pageId)) return "guardedStrategy";
    return null;
  }

  function setHash(id, { replace = true } = {}) {
    if (!id) return;
    const url = new URL(location.href);
    url.hash = id;
    url.searchParams.delete("page");
    url.searchParams.delete("strategy");
    const state = { siteTab: id };
    if (replace) history.replaceState(state, "", url);
    else history.pushState(state, "", url);
  }

  function onRouteChange(handler) {
    window.addEventListener("hashchange", () => handler(location));
    window.addEventListener("popstate", () => handler(location));
  }

  window.SiteNav = {
    PAGE_IDS,
    STRATEGY_IDS,
    pageFromLocation,
    strategyFromLocation,
    strategyForPage,
    setHash,
    onRouteChange,
  };
})();
