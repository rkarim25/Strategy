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
      id: "lqq3",
      label: "LQQ3 3x Nasdaq — Guarded A5/B25 (max 1x)",
      href: "lqq3_guarded.html#signalPage",
    },
    {
      id: "ndx",
      label: "Nasdaq 100 — Guarded A5/B25",
      href: "ndx_guarded.html#signalPage",
    },
    {
      id: "spx",
      label: "S&P 500 — Guarded A5/B25 SMA20 Lead",
      href: "index.html#signalPage",
      indexHref: "#signalPage",
      strategyNav: "guarded",
    },
    {
      id: "gold",
      label: "Gold — Guarded A5/B25 (max 1x)",
      href: "gold_guarded.html#signalPage",
    },
    {
      id: "ftse250",
      label: "FTSE 250 — Guarded A5/B25 (max 1x)",
      href: "ftse250_guarded.html#signalPage",
    },
    {
      id: "msci_em",
      label: "MSCI EM — Guarded A5/B25 (max 1x)",
      href: "msci_em_guarded.html#signalPage",
    },
    {
      id: "dax",
      label: "DAX — Guarded A5/B25 (max 1x)",
      href: "dax_guarded.html#signalPage",
    },
    {
      id: "msci_world",
      label: "MSCI World — Guarded A5/B25 (max 1x)",
      href: "msci_world_guarded.html#signalPage",
    },
    {
      id: "momentum",
      label: "Research — Momentum strategy",
      href: "index.html#momentumSignalPage",
      indexHref: "#momentumSignalPage",
      strategyNav: "momentum",
    },
    {
      id: "instruments",
      label: "Tools — Instruments",
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
    const currentPageId = pageFromLocation(loc) || "signalPage";

    function hrefForItem(item) {
      // UX improvement: preserve the current section (signal/backtest/monte-carlo/instruments)
      // when switching assets, so the user doesn't get bounced back to Signal every time.
      const raw = onIndex && item.indexHref ? item.indexHref : item.href;
      const [file, hash = ""] = String(raw).split("#");

      const targetHash =
        item.id === "instruments"
          ? "" // instruments.html has no internal hash routing
          : item.id === "momentum"
            ? currentPageId && currentPageId.startsWith("momentum") ? currentPageId : "momentumSignalPage"
            : PAGE_IDS.has(currentPageId) ? currentPageId : "signalPage";

      if (!file) return `#${targetHash}`;
      return targetHash ? `${file}#${targetHash}` : file;
    }

    nav.replaceChildren();

    const shell = document.createElement("div");
    shell.className = "site-nav-sidebar";

    const title = document.createElement("div");
    title.className = "site-nav-sidebar-title";
    title.textContent = "Strategy";

    const select = document.createElement("select");
    select.className = "site-nav-select";
    select.setAttribute("aria-label", "Select strategy tab");

    for (const item of STRATEGY_NAV_ITEMS) {
      const opt = document.createElement("option");
      opt.value = hrefForItem(item);
      opt.textContent = item.label;
      if (item.id === activeId) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => {
      const next = select.value;
      if (next) location.href = next;
    });

    const helper = document.createElement("div");
    helper.className = "site-nav-sidebar-helper";
    helper.textContent = onIndex
      ? "Switch between assets and research tabs."
      : "Switch assets; section stays the same.";

    shell.appendChild(title);
    shell.appendChild(select);
    shell.appendChild(helper);
    nav.appendChild(shell);
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
      :root { --siteSidebarW: 278px; }

      /* Side dropdown wrapper replaces the old pill-tab layout. */
      .site-nav[aria-label="Strategies"] {
        position: fixed;
        top: 18px;
        left: 18px;
        width: var(--siteSidebarW);
        z-index: 20;
        display: block;
        margin: 0;
        padding: 0;
        border: none;
        background: transparent;
        backdrop-filter: none;
      }

      .site-nav-sidebar {
        border: 1px solid rgba(0, 0, 0, .10);
        border-radius: 18px;
        padding: 14px;
        background: rgba(255, 255, 255, .78);
        backdrop-filter: blur(18px);
        box-shadow: 0 18px 45px rgba(0, 0, 0, .08);
      }
      .site-nav-sidebar-title {
        font-size: 12px;
        letter-spacing: .02em;
        text-transform: uppercase;
        color: rgba(0, 0, 0, .60);
        font-weight: 700;
        margin: 0 0 10px;
      }
      .site-nav-select {
        width: 100%;
        border-radius: 14px;
        padding: 10px 12px;
        background: rgba(255, 255, 255, .92);
        border: 1px solid rgba(0, 0, 0, .12);
        font-weight: 650;
      }
      .site-nav-sidebar-helper {
        margin-top: 10px;
        font-size: 12px;
        line-height: 1.35;
        color: rgba(0, 0, 0, .55);
      }

      /* Make room for the sidebar on desktop. */
      body { padding-left: calc(var(--siteSidebarW) + 36px); }
      main { width: min(1180px, calc(100vw - 40px - var(--siteSidebarW) - 36px)); }

      /* Mobile: sidebar becomes a normal top dropdown bar. */
      @media (max-width: 980px) {
        body { padding-left: 0; }
        .site-nav[aria-label="Strategies"] {
          position: sticky;
          top: 0;
          left: 0;
          width: auto;
          margin: 14px 0;
          padding: 5px;
          border: 1px solid rgba(0, 0, 0, .07);
          border-radius: 18px;
          background: rgba(255, 255, 255, .72);
          backdrop-filter: blur(18px);
        }
        .site-nav-sidebar { box-shadow: none; border: none; padding: 0; background: transparent; }
        .site-nav-sidebar-title { display: none; }
        .site-nav-sidebar-helper { display: none; }
        .site-nav-select { border-radius: 999px; }
        main { width: min(1180px, calc(100vw - 40px)); }
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
