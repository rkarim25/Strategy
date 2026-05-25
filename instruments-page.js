/** Instruments page: halal vs conventional reference tables + searchable browser. */
(function () {
  const BADGE_CLASS = {
    conventional: "badge-conventional",
    halal: "badge-halal",
    levered: "badge-levered",
    none: "badge-none",
  };

  const ASSET_CLASS_ORDER = [
    "S&P 500",
    "Nasdaq 100",
    "FTSE 100",
    "FTSE 250",
    "DAX",
    "MSCI World",
    "MSCI EM",
    "Gold",
    "Halal US",
    "Halal World",
    "Halal EM",
  ];

  const LEVERAGE_ORDER = { "1x": 0, "2x": 1, "3x": 2 };

  const HASH_KEYS = ["q", "asset", "lev", "halal", "ccy", "sort", "dir"];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function badgeHtml(kind) {
    const label =
      kind === "halal"
        ? "Halal"
        : kind === "levered"
          ? "Levered"
          : kind === "none"
            ? "None"
            : "Conventional";
    const cls = BADGE_CLASS[kind] || BADGE_CLASS.conventional;
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function terClassFromNum(terNum) {
    if (typeof terNum !== "number" || Number.isNaN(terNum)) return "";
    if (terNum <= 0.10) return "ter-low";
    if (terNum <= 0.40) return "ter-mid";
    return "ter-high";
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Reference comparison tables (halal vs conventional)
  // ──────────────────────────────────────────────────────────────────────────

  function renderFeesTable(tbody) {
    if (!tbody || !window.HALAL_FEES_DATA) return;

    const rows = window.HALAL_FEES_DATA.flatMap((group) => {
      const header = `<tr class="group-row">
        <td colspan="4">${badgeHtml(group.badge)}${escapeHtml(group.group)}</td>
      </tr>`;
      const body = group.rows
        .map(
          (row) => `<tr>
        <td>${escapeHtml(row.productType)}</td>
        <td><code>${escapeHtml(row.ticker)}</code></td>
        <td class="ter-cell ${escapeHtml(row.terClass || "")}">${escapeHtml(row.ter)}</td>
        <td class="small">${escapeHtml(row.notes)}</td>
      </tr>`
        )
        .join("");
      return header + body;
    });

    tbody.innerHTML = rows.join("");
  }

  function renderScreeningTable(tbody) {
    if (!tbody || !window.HALAL_SCREENING_DATA) return;

    tbody.innerHTML = window.HALAL_SCREENING_DATA.map(
      (row) => `<tr>
      <td><strong>${escapeHtml(row.category)}</strong></td>
      <td>${escapeHtml(row.conventional)}</td>
      <td>${escapeHtml(row.halal)}</td>
    </tr>`
    ).join("");
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Instruments browser (search / filter / sort)
  // ──────────────────────────────────────────────────────────────────────────

  function uniqueSortedValues(rows, key, orderHint) {
    const values = Array.from(new Set(rows.map((r) => r[key]).filter(Boolean)));
    if (orderHint && orderHint.length) {
      values.sort((a, b) => {
        const ai = orderHint.indexOf(a);
        const bi = orderHint.indexOf(b);
        if (ai === -1 && bi === -1) return a.localeCompare(b);
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      });
    } else {
      values.sort((a, b) => a.localeCompare(b));
    }
    return values;
  }

  function populateSelect(select, values, formatter) {
    if (!select) return;
    const existing = new Set(
      Array.from(select.options).map((o) => o.value)
    );
    values.forEach((v) => {
      if (existing.has(v)) return;
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = formatter ? formatter(v) : v;
      select.appendChild(opt);
    });
  }

  function readHashState() {
    const hash = (location.hash || "").replace(/^#/, "");
    if (!hash) return {};
    const params = new URLSearchParams(hash);
    const out = {};
    HASH_KEYS.forEach((k) => {
      const v = params.get(k);
      if (v !== null && v !== "") out[k] = v;
    });
    return out;
  }

  function writeHashState(state) {
    const params = new URLSearchParams();
    const map = {
      q: state.search,
      asset: state.assetClass !== "all" ? state.assetClass : "",
      lev: state.leverage !== "all" ? state.leverage : "",
      halal: state.halal !== "all" ? state.halal : "",
      ccy: state.currency !== "all" ? state.currency : "",
      sort: state.sortKey !== "ticker" ? state.sortKey : "",
      dir: state.sortDir !== "asc" ? state.sortDir : "",
    };
    HASH_KEYS.forEach((k) => {
      if (map[k]) params.set(k, map[k]);
    });
    const next = params.toString();
    const url = next ? `#${next}` : location.pathname + location.search;
    history.replaceState(null, "", url);
  }

  function applyFilters(data, state) {
    const q = (state.search || "").trim().toLowerCase();
    return data.filter((row) => {
      if (state.assetClass !== "all" && row.assetClass !== state.assetClass) return false;
      if (state.leverage !== "all" && row.leverage !== state.leverage) return false;
      if (state.halal !== "all" && row.halal !== state.halal) return false;
      if (state.currency !== "all" && row.currency !== state.currency) return false;
      if (!q) return true;
      const hay = `${row.ticker} ${row.name} ${row.isin}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function applySort(rows, state) {
    const key = state.sortKey;
    const dir = state.sortDir === "desc" ? -1 : 1;
    const out = rows.slice();
    out.sort((a, b) => {
      let av = a[key];
      let bv = b[key];
      if (key === "terNum") {
        av = typeof av === "number" ? av : Number.POSITIVE_INFINITY;
        bv = typeof bv === "number" ? bv : Number.POSITIVE_INFINITY;
        if (av === bv) {
          // Secondary stable sort by ticker
          return a.ticker.localeCompare(b.ticker) * dir;
        }
        return (av - bv) * dir;
      }
      av = String(av || "");
      bv = String(bv || "");
      const cmp = av.localeCompare(bv, undefined, { sensitivity: "base" });
      if (cmp === 0) {
        return a.ticker.localeCompare(b.ticker) * dir;
      }
      return cmp * dir;
    });
    return out;
  }

  function rowHtml(row) {
    const halalClass = row.halal === "Halal" ? " row-halal" : "";
    const leverageCls = row.leverage === "2x" ? " lev-2x" : row.leverage === "3x" ? " lev-3x" : "";
    const halalBadge = row.halal === "Halal" ? "halal" : row.leverage !== "1x" ? "levered" : "conventional";
    const terClass = terClassFromNum(row.terNum);
    return `<tr class="${halalClass.trim()}">
      <td class="ticker-cell"><code>${escapeHtml(row.ticker)}</code></td>
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.assetClass)}</td>
      <td><span class="lev-pill${leverageCls}">${escapeHtml(row.leverage)}</span></td>
      <td>${badgeHtml(halalBadge)}</td>
      <td class="ter-cell ${terClass}">${escapeHtml(row.ter || "—")}</td>
      <td>${escapeHtml(row.currency || "—")}</td>
      <td>${escapeHtml(row.accDist || "—")}</td>
      <td><code>${escapeHtml(row.isin || "—")}</code></td>
      <td>${escapeHtml(row.issuer || "—")}</td>
      <td>${escapeHtml(row.structure || "—")}</td>
      <td class="notes-cell">${escapeHtml(row.notes || "")}</td>
    </tr>`;
  }

  function updateSortIndicators(table, state) {
    const heads = table.querySelectorAll("th.sortable");
    heads.forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === state.sortKey) {
        th.classList.add(state.sortDir === "desc" ? "sort-desc" : "sort-asc");
      }
    });
  }

  function renderBrowser(refs, state) {
    const data = window.ALL_INSTRUMENTS_DATA || [];
    const filtered = applyFilters(data, state);
    const sorted = applySort(filtered, state);

    if (sorted.length === 0) {
      refs.tbody.innerHTML = `<tr><td colspan="12" class="instruments-empty">
        No instruments match these filters. Try clearing the search or selecting "All".
      </td></tr>`;
    } else {
      refs.tbody.innerHTML = sorted.map(rowHtml).join("");
    }

    refs.count.innerHTML = `Showing <strong>${sorted.length}</strong> of <strong>${data.length}</strong> instruments`;
    updateSortIndicators(refs.table, state);
  }

  function initInstrumentsBrowser(root = document) {
    const tbody = root.querySelector("#instrumentsBrowserBody");
    if (!tbody) return;
    const data = window.ALL_INSTRUMENTS_DATA;
    if (!data || !data.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="instruments-empty">
        Instrument data not loaded.
      </td></tr>`;
      return;
    }

    const refs = {
      tbody,
      table: tbody.closest("table"),
      count: root.querySelector("#instrumentsCount"),
      searchInput: root.querySelector("#instrumentsSearch"),
      assetSelect: root.querySelector("#filterAssetClass"),
      leverageSelect: root.querySelector("#filterLeverage"),
      halalSelect: root.querySelector("#filterHalal"),
      currencySelect: root.querySelector("#filterCurrency"),
      resetBtn: root.querySelector("#instrumentsReset"),
    };

    populateSelect(
      refs.assetSelect,
      uniqueSortedValues(data, "assetClass", ASSET_CLASS_ORDER)
    );
    populateSelect(refs.currencySelect, uniqueSortedValues(data, "currency"));

    const hashState = readHashState();
    const state = {
      search: hashState.q || "",
      assetClass: hashState.asset || "all",
      leverage: hashState.lev || "all",
      halal: hashState.halal || "all",
      currency: hashState.ccy || "all",
      sortKey: hashState.sort || "ticker",
      sortDir: hashState.dir === "desc" ? "desc" : "asc",
    };

    if (refs.searchInput) refs.searchInput.value = state.search;
    if (refs.assetSelect) refs.assetSelect.value = state.assetClass;
    if (refs.leverageSelect) refs.leverageSelect.value = state.leverage;
    if (refs.halalSelect) refs.halalSelect.value = state.halal;
    if (refs.currencySelect) refs.currencySelect.value = state.currency;

    function rerender({ updateHash = true } = {}) {
      renderBrowser(refs, state);
      if (updateHash) writeHashState(state);
    }

    let searchTimer = null;
    refs.searchInput?.addEventListener("input", (e) => {
      state.search = e.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(rerender, 120);
    });

    const selectMap = [
      [refs.assetSelect, "assetClass"],
      [refs.leverageSelect, "leverage"],
      [refs.halalSelect, "halal"],
      [refs.currencySelect, "currency"],
    ];
    selectMap.forEach(([sel, key]) => {
      sel?.addEventListener("change", (e) => {
        state[key] = e.target.value;
        rerender();
      });
    });

    refs.resetBtn?.addEventListener("click", () => {
      state.search = "";
      state.assetClass = "all";
      state.leverage = "all";
      state.halal = "all";
      state.currency = "all";
      state.sortKey = "ticker";
      state.sortDir = "asc";
      if (refs.searchInput) refs.searchInput.value = "";
      if (refs.assetSelect) refs.assetSelect.value = "all";
      if (refs.leverageSelect) refs.leverageSelect.value = "all";
      if (refs.halalSelect) refs.halalSelect.value = "all";
      if (refs.currencySelect) refs.currencySelect.value = "all";
      rerender();
    });

    refs.table?.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (!key) return;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          // Default direction: ascending for text/numeric ticker/name/TER
          state.sortDir = "asc";
        }
        rerender();
      });
    });

    rerender({ updateHash: false });
  }

  function initInstrumentsPage(root = document) {
    renderFeesTable(root.querySelector("#feesComparisonBody"));
    renderScreeningTable(root.querySelector("#screeningComparisonBody"));
    initInstrumentsBrowser(root);
  }

  window.initInstrumentsPage = initInstrumentsPage;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initInstrumentsPage(document));
  } else {
    initInstrumentsPage(document);
  }
})();
