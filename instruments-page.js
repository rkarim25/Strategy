/** Halal vs conventional instruments comparison tables (Instruments tab). */
(function () {
  const BADGE_CLASS = {
    conventional: "badge-conventional",
    halal: "badge-halal",
    levered: "badge-levered",
    none: "badge-none",
  };

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

  function initInstrumentsPage(root = document) {
    renderFeesTable(root.querySelector("#feesComparisonBody"));
    renderScreeningTable(root.querySelector("#screeningComparisonBody"));
  }

  window.initInstrumentsPage = initInstrumentsPage;
  document.addEventListener("DOMContentLoaded", () => initInstrumentsPage(document));
})();
