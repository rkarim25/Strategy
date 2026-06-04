/** Shared hash/query routing and strategy tab nav (static GitHub Pages). */
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

  /** Single source of truth for top-level strategy/asset tabs. */
  const STRATEGY_NAV_ITEMS = [
    {
      id: "spx",
      label: "Guarded A5/B25 SMA20 Lead (SPX)",
      href: "index.html#signalPage",
      indexHref: "#signalPage",
      strategyNav: "guarded",
    },
    {
      id: "ndx",
      label: "Guarded A5/B25 (Nasdaq 100)",
      href: "ndx_guarded.html#signalPage",
    },
    {
      id: "gold",
      label: "Guarded A5/B25 (Gold, max 1x)",
      href: "gold_guarded.html#signalPage",
    },
    {
      id: "ftse250",
      label: "Guarded A5/B25 (FTSE 250, max 1x)",
      href: "ftse250_guarded.html#signalPage",
    },
    {
      id: "msci_em",
      label: "Guarded A5/B25 (MSCI EM, max 1x)",
      href: "msci_em_guarded.html#signalPage",
    },
    {
      id: "dax",
      label: "Guarded A5/B25 (DAX, max 1x)",
      href: "dax_guarded.html#signalPage",
    },
    {
      id: "msci_world",
      label: "Guarded A5/B25 (MSCI World, max 1x)",
      href: "msci_world_guarded.html#signalPage",
    },
    {
      id: "lqq3",
      label: "Guarded A5/B25 (LQQ3 3x, max 1x)",
      href: "lqq3_guarded.html#signalPage",
    },
    {
      id: "momentum",
      label: "Momentum Strategy Research",
      href: "index.html#momentumSignalPage",
      indexHref: "#momentumSignalPage",
      strategyNav: "momentum",
    },
    {
      id: "instruments",
      label: "Instruments",
      href: "instruments.html",
      secondary: true,
    },
  ];

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

  function renderStrategyNav(loc = location) {
    const nav = document.querySelector('[aria-label="Strategies"]');
    if (!nav) return;

    const page = currentPageFile(loc);
    const onIndex = page === "index.html";
    const activeId = activeNavId(loc);

    nav.replaceChildren();
    for (const item of STRATEGY_NAV_ITEMS) {
      const link = document.createElement("a");
      link.className = "site-nav-link";
      if (item.secondary) link.classList.add("secondary");
      link.textContent = item.label;

      if (onIndex && item.indexHref) {
        link.href = item.indexHref;
        if (item.strategyNav) link.dataset.strategyNav = item.strategyNav;
      } else {
        link.href = item.href;
      }

      if (item.id === activeId) {
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      }

      nav.appendChild(link);
    }
  }

  /**
   * Inject the small bit of CSS needed to visually separate the "secondary"
   * Instruments tab from the guarded/momentum strategy tabs. Kept here so all
   * 8 pages get the same styling without each one having to be edited.
   */
  function ensureSecondaryNavStyles() {
    if (document.getElementById("site-nav-secondary-styles")) return;
    const style = document.createElement("style");
    style.id = "site-nav-secondary-styles";
    style.textContent = `
      .site-nav[aria-label="Strategies"] .site-nav-link.secondary {
        margin-left: 10px;
        padding-left: 18px;
        border-left: 1px solid rgba(0, 0, 0, .14);
        border-radius: 0 999px 999px 0;
      }
      .site-nav[aria-label="Strategies"] .site-nav-link.secondary.active {
        border-left: 1px solid rgba(0, 0, 0, .14);
      }
      @media (max-width: 720px) {
        .site-nav[aria-label="Strategies"] .site-nav-link.secondary {
          margin-left: 0;
          padding-left: 12px;
          border-left: none;
          border-top: 1px solid rgba(0, 0, 0, .1);
          border-radius: 999px;
          width: 100%;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function initStrategyNav() {
    ensureSecondaryNavStyles();
    renderStrategyNav();
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
    pageFromLocation,
    strategyFromLocation,
    strategyForPage,
    setHash,
    onRouteChange,
    renderStrategyNav,
    activeNavId,
  };
})();
