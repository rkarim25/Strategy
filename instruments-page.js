/** Filterable instruments table for Strategy site Instruments tab. */
(function () {
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function initInstrumentsPage(root = document) {
    const tableBody = root.querySelector("#instrumentsTableBody");
    const searchInput = root.querySelector("#instrumentsSearch");
    const countEl = root.querySelector("#instrumentsCount");
    const filterButtons = root.querySelectorAll("[data-instrument-leverage]");
    if (!tableBody || !window.INSTRUMENTS_DATA) return;

    let leverageFilter = "all";

    function rowMatchesSearch(row, query) {
      if (!query) return true;
      const haystack = [
        row.ticker,
        row.name,
        row.isin,
        row.issuer,
        row.notes,
        row.currency,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    }

    function render() {
      const query = (searchInput?.value || "").trim().toLowerCase();
      const rows = window.INSTRUMENTS_DATA.filter((row) => {
        const levOk = leverageFilter === "all" || row.leverage === leverageFilter;
        return levOk && rowMatchesSearch(row, query);
      });

      tableBody.innerHTML = rows.length
        ? rows
            .map(
              (row) => `<tr>
          <td><strong>${escapeHtml(row.leverage)}</strong></td>
          <td><code>${escapeHtml(row.ticker)}</code></td>
          <td>${escapeHtml(row.name)}</td>
          <td>${escapeHtml(row.ter)}</td>
          <td>${escapeHtml(row.accDist)}</td>
          <td>${escapeHtml(row.currency)}</td>
          <td><code>${escapeHtml(row.isin)}</code></td>
          <td>${escapeHtml(row.issuer)}</td>
          <td class="small">${escapeHtml(row.notes)}</td>
        </tr>`
            )
            .join("")
        : `<tr><td colspan="9">No instruments match the current filters.</td></tr>`;

      if (countEl) {
        const total = window.INSTRUMENTS_DATA.length;
        countEl.textContent =
          rows.length === total
            ? `Showing ${total} instruments`
            : `Showing ${rows.length} of ${total} instruments`;
      }
    }

    filterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        leverageFilter = button.dataset.instrumentLeverage || "all";
        filterButtons.forEach((btn) => {
          btn.classList.toggle("active", btn === button);
        });
        render();
      });
    });

    searchInput?.addEventListener("input", render);
    render();
  }

  window.initInstrumentsPage = initInstrumentsPage;
  document.addEventListener("DOMContentLoaded", () => initInstrumentsPage(document));
})();
