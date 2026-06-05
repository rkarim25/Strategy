/** Shared hash/query routing and strategy sidebar nav (static GitHub Pages). */
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

  const NAV_GROUPS = [
    { id: "leveraged", label: "Leveraged equity" },
    { id: "equity_1x", label: "Equity (max 1x)" },
    { id: "other", label: "Other" },
    { id: "tools", label: "Tools & research" },
  ];

  /** Single source of truth for strategy/asset sidebar links. */
  const STRATEGY_NAV_ITEMS = [
    {
      id: "lqq3",
      asset: "LQQ3 3x Nasdaq",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "leveraged",
      href: "lqq3_guarded.html#signalPage",
    },
    {
      id: "3bal",
      asset: "3BAL 3x EU Banks",
      strategy: "SMA20 1x/cash",
      group: "leveraged",
      href: "3bal_guarded.html#signalPage",
    },
    {
      id: "ndx",
      asset: "Nasdaq 100",
      strategy: "Guarded A5/B25",
      group: "leveraged",
      href: "ndx_guarded.html#signalPage",
    },
    {
      id: "spx",
      asset: "S&P 500",
      strategy: "Guarded A5/B25 SMA20 Lead",
      group: "leveraged",
      href: "index.html#signalPage",
      indexHref: "#signalPage",
      strategyNav: "guarded",
    },
    {
      id: "ftse250",
      asset: "FTSE 250",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "equity_1x",
      href: "ftse250_guarded.html#signalPage",
    },
    {
      id: "msci_em",
      asset: "MSCI EM",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "equity_1x",
      href: "msci_em_guarded.html#signalPage",
    },
    {
      id: "dax",
      asset: "DAX",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "equity_1x",
      href: "dax_guarded.html#signalPage",
    },
    {
      id: "msci_world",
      asset: "MSCI World",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "equity_1x",
      href: "msci_world_guarded.html#signalPage",
    },
    {
      id: "gold",
      asset: "Gold",
      strategy: "Guarded A5/B25 (max 1x)",
      group: "other",
      href: "gold_guarded.html#signalPage",
    },
    {
      id: "momentum",
      asset: "Research",
      strategy: "Momentum strategy",
      group: "tools",
      href: "index.html#momentumSignalPage",
      indexHref: "#momentumSignalPage",
      strategyNav: "momentum",
    },
    {
      id: "instruments",
      asset: "Tools",
      strategy: "Instruments",
      group: "tools",
      href: "instruments.html",
      secondary: true,
    },
  ];

  /** Back-compat label for anything still reading .label */
  for (const item of STRATEGY_NAV_ITEMS) {
    item.label = `${item.asset} — ${item.strategy}`;
  }

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

  function scrollToTop() {
    window.scrollTo(0, 0);
  }

  function setHash(id, { replace = true, scroll = true } = {}) {
    if (!id) return;
    const url = new URL(location.href);
    url.hash = id;
    url.searchParams.delete("page");
    url.searchParams.delete("strategy");
    const state = { siteTab: id };
    if (replace) history.replaceState(state, "", url);
    else history.pushState(state, "", url);
    if (scroll) scrollToTop();
  }

  function onRouteChange(handler) {
    window.addEventListener("hashchange", () => handler(location));
    window.addEventListener("popstate", () => handler(location));
  }

  function currentPageFile(loc = location) {
    const base = (loc.pathname.split("/").pop() || "index.html").toLowerCase();
    return base || "index.html";
  }

  function navItemPageFile(item) {
    return item.href.split("#")[0].toLowerCase();
  }

  function activeNavId(loc = location) {
    const page = currentPageFile(loc);
    if (page === "instruments.html") return "instruments";
    if (page !== "index.html") {
      const match = STRATEGY_NAV_ITEMS.find((item) => navItemPageFile(item) === page);
      return match ? match.id : null;
    }
    const pageId = pageFromLocation(loc);
    if (pageId && pageId.startsWith("momentum")) return "momentum";
    return "spx";
  }

  function hrefForItem(item, loc = location) {
    const page = currentPageFile(loc);
    const onIndex = page === "index.html";
    const currentPageId = pageFromLocation(loc) || "signalPage";

    const raw = onIndex && item.indexHref ? item.indexHref : item.href;
    const [file] = String(raw).split("#");

    const targetHash =
      item.id === "instruments"
        ? ""
        : item.id === "momentum"
          ? currentPageId && currentPageId.startsWith("momentum")
            ? currentPageId
            : "momentumSignalPage"
          : PAGE_IDS.has(currentPageId)
            ? currentPageId
            : "signalPage";

    if (!file) return `#${targetHash}`;
    return targetHash ? `${file}#${targetHash}` : file;
  }

  function renderStrategyNav(loc = location) {
    const nav = document.querySelector('[aria-label="Strategies"]');
    if (!nav) return;

    const page = currentPageFile(loc);
    const onIndex = page === "index.html";
    const activeId = activeNavId(loc);

    nav.replaceChildren();

    const shell = document.createElement("div");
    shell.className = "site-nav-sidebar";

    const brand = document.createElement("a");
    brand.className = "site-nav-brand";
    brand.href = "index.html#signalPage";
    brand.textContent = "Strategy";

    const list = document.createElement("div");
    list.className = "site-nav-list";

    for (const group of NAV_GROUPS) {
      const items = STRATEGY_NAV_ITEMS.filter((item) => item.group === group.id);
      if (!items.length) continue;

      const groupEl = document.createElement("section");
      groupEl.className = "site-nav-group";

      const heading = document.createElement("h2");
      heading.className = "site-nav-group-label";
      heading.textContent = group.label;
      groupEl.appendChild(heading);

      for (const item of items) {
        const link = document.createElement("a");
        link.className = "site-nav-item";
        if (item.secondary) link.classList.add("secondary");
        link.href = hrefForItem(item, loc);

        const asset = document.createElement("span");
        asset.className = "site-nav-item-asset";
        asset.textContent = item.asset;

        const strategy = document.createElement("span");
        strategy.className = "site-nav-item-strategy";
        strategy.textContent = item.strategy;

        link.appendChild(asset);
        link.appendChild(strategy);

        if (onIndex && item.strategyNav) {
          link.dataset.strategyNav = item.strategyNav;
        }

        if (item.id === activeId) {
          link.classList.add("active");
          link.setAttribute("aria-current", "page");
        }

        groupEl.appendChild(link);
      }

      list.appendChild(groupEl);
    }

    shell.appendChild(brand);
    shell.appendChild(list);
    nav.appendChild(shell);
  }

  function ensureSidebarStyles() {
    if (document.getElementById("site-nav-sidebar-styles")) return;
    const style = document.createElement("style");
    style.id = "site-nav-sidebar-styles";
    style.textContent = `
      :root {
        --siteSidebarW: 292px;
        --siteSidebarGap: 28px;
      }

      /* Strategy sidebar — overrides per-page pill-tab styles for this nav only. */
      .site-nav[aria-label="Strategies"] {
        all: unset;
        position: fixed;
        top: 0;
        left: 0;
        width: var(--siteSidebarW);
        height: 100vh;
        z-index: 30;
        display: block;
        box-sizing: border-box;
      }

      .site-nav-sidebar {
        display: flex;
        flex-direction: column;
        height: 100%;
        padding: 20px 14px 24px;
        border-right: 1px solid rgba(0, 0, 0, .08);
        background: rgba(251, 251, 253, .92);
        backdrop-filter: blur(20px);
        box-sizing: border-box;
      }

      .site-nav-brand {
        display: block;
        margin: 0 8px 18px;
        font-size: 22px;
        font-weight: 800;
        letter-spacing: -0.04em;
        color: #1d1d1f;
        text-decoration: none;
        line-height: 1.1;
      }
      .site-nav-brand:hover {
        color: #0071e3;
      }

      .site-nav-list {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
        padding-right: 4px;
        scrollbar-width: thin;
        scrollbar-color: rgba(0, 0, 0, .18) transparent;
      }

      .site-nav-group {
        margin-bottom: 18px;
      }
      .site-nav-group:last-child {
        margin-bottom: 0;
      }

      .site-nav-group-label {
        margin: 0 8px 8px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: rgba(0, 0, 0, .45);
      }

      .site-nav-item {
        display: flex;
        flex-direction: column;
        gap: 2px;
        margin: 0 0 4px;
        padding: 10px 12px 10px 14px;
        border-radius: 12px;
        border: 1px solid transparent;
        border-left: 3px solid transparent;
        text-decoration: none;
        color: inherit;
        transition: background .15s ease, border-color .15s ease;
      }
      .site-nav-item:hover {
        background: rgba(0, 0, 0, .04);
        border-left-color: rgba(0, 113, 227, .35);
      }
      .site-nav-item.active {
        background: #ffffff;
        border-color: rgba(0, 0, 0, .08);
        border-left-color: #0071e3;
        box-shadow: 0 1px 4px rgba(0, 0, 0, .06);
      }
      .site-nav-item-asset {
        font-size: 14px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #1d1d1f;
        line-height: 1.25;
      }
      .site-nav-item-strategy {
        font-size: 12px;
        font-weight: 500;
        color: #6e6e73;
        line-height: 1.35;
      }
      .site-nav-item.active .site-nav-item-asset {
        color: #0071e3;
      }

      body {
        padding-left: calc(var(--siteSidebarW) + var(--siteSidebarGap));
      }
      main {
        width: min(1120px, calc(100vw - var(--siteSidebarW) - var(--siteSidebarGap) - 40px));
        margin-left: auto;
        margin-right: auto;
      }

      /* Section tabs (Signal / Backtest / Monte Carlo) — subtle polish. */
      .site-nav[aria-label="Guarded strategy sections"],
      .site-nav[aria-label="Momentum strategy sections"] {
        margin-top: 4px;
      }

      @media (max-width: 980px) {
        .site-nav[aria-label="Strategies"] {
          position: sticky;
          top: 0;
          width: auto;
          height: auto;
          margin: 0 0 16px;
          padding: 0;
        }
        .site-nav-sidebar {
          height: auto;
          max-height: none;
          padding: 12px;
          border-right: none;
          border: 1px solid rgba(0, 0, 0, .08);
          border-radius: 18px;
          background: rgba(255, 255, 255, .88);
        }
        .site-nav-brand {
          margin: 0 4px 12px;
          font-size: 18px;
        }
        .site-nav-list {
          display: flex;
          flex-direction: row;
          flex-wrap: nowrap;
          gap: 8px;
          overflow-x: auto;
          overflow-y: hidden;
          padding-bottom: 4px;
        }
        .site-nav-group {
          display: contents;
        }
        .site-nav-group-label {
          display: none;
        }
        .site-nav-item {
          flex: 0 0 auto;
          min-width: 148px;
          margin: 0;
          padding: 10px 14px;
          border-left-width: 1px;
        }
        body {
          padding-left: 0;
        }
        main {
          width: min(1180px, calc(100vw - 40px));
        }
      }
    `;
    document.head.appendChild(style);
  }

  function initTabScroll() {
    window.addEventListener("hashchange", scrollToTop);
    window.addEventListener("popstate", scrollToTop);
    document.addEventListener("click", (event) => {
      const target = event.target.closest("[data-page-target]");
      if (target) scrollToTop();
    });
  }

  function initStrategyNav() {
    ensureSidebarStyles();
    renderStrategyNav();
    onRouteChange(() => renderStrategyNav());
    initTabScroll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initStrategyNav);
  } else {
    initStrategyNav();
  }

  window.SiteNav = {
    PAGE_IDS,
    STRATEGY_IDS,
    STRATEGY_NAV_ITEMS,
    NAV_GROUPS,
    pageFromLocation,
    strategyFromLocation,
    strategyForPage,
    setHash,
    scrollToTop,
    onRouteChange,
    renderStrategyNav,
    activeNavId,
  };
})();
