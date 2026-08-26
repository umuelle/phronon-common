/**
 * dashboard-table.js — search + sort + optional pagination for backoffice tables.
 *
 * MASTER COPY: phronon_common/dashboard-table.js. Do not edit a tool's copy —
 * `server-ops/sync_shared_assets.py` overwrites it and reports the drift.
 *
 * Consolidated 26 August 2026 (FL-030). Eight tools carried eight versions of
 * this file: five were 94–99.5% identical to Layoff's, Whiteout's was the same
 * logic reformatted, and Moral Mirror's was the same API written more tersely.
 * What actually differed between them was the block of `initSortableTable(...)`
 * calls at the FOOT of the file — which table, which searchable columns —
 * which is configuration, not code. That block now lives in each tool's own
 * `static/js/dashboard-table-local.js`, loaded after this file, exactly as
 * `actions-local.js` sits behind the shared `actions.js` (FL-017).
 *
 * This engine is therefore byte-identical everywhere, and every tool gets the
 * pagination support all eight copies already had and only some used.
 *
 * Hooks into:
 *   <input id="{prefix}-search">       — text filter
 *   <table id="{prefix}-table">        — sortable table
 *   <tr data-name=… data-code=…>       — row metadata for filter + sort
 *   <th class="sortable-col" data-sort="text|date|number" data-sort-key="…">
 *   <p id="{prefix}-empty-msg">        — shown when no rows match
 *
 * Optional (pass as 4th argument object):
 *   pageSizeId   — id of a <select> controlling rows per page
 *   paginationId — id of a container for Prev/Next buttons + info line
 */
'use strict';

function initSortableTable(tableId, searchId, searchKeys, options) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const tbody       = table.querySelector('tbody');
  const searchInput = document.getElementById(searchId);
  const emptyMsg    = document.getElementById(tableId.replace('-table', '-empty-msg'));

  const pageSizeSelect = options && options.pageSizeId
    ? document.getElementById(options.pageSizeId) : null;
  const paginationEl = options && options.paginationId
    ? document.getElementById(options.paginationId) : null;

  let pageSize = pageSizeSelect ? (parseInt(pageSizeSelect.value) || 0) : 0;
  let page = 1;
  let visibleRows = [];

  // --- Render (filter + paginate) ----------------------------------------
  function render() {
    const term    = searchInput ? searchInput.value.trim().toLowerCase() : '';
    const allRows = Array.from(tbody.querySelectorAll('tr'));
    visibleRows   = allRows.filter(row => {
      if (!term) return true;
      const haystack = (searchKeys || []).map(k => row.dataset[k] || '').join(' ').toLowerCase();
      return haystack.includes(term);
    });

    allRows.forEach(r => { r.style.display = 'none'; });
    const start = pageSize > 0 ? (page - 1) * pageSize : 0;
    const end   = pageSize > 0 ? start + pageSize : visibleRows.length;
    visibleRows.slice(start, end).forEach(r => { r.style.display = ''; });

    if (emptyMsg) emptyMsg.hidden = visibleRows.length > 0;
    if (paginationEl) renderPagination();
  }

  function renderPagination() {
    const total = visibleRows.length;
    if (!paginationEl) return;
    if (pageSize === 0 || total === 0) { paginationEl.innerHTML = ''; return; }
    const totalPages = Math.ceil(total / pageSize);
    const from = Math.min((page - 1) * pageSize + 1, total);
    const to   = Math.min(page * pageSize, total);
    paginationEl.innerHTML =
      '<span class="pagination-info">Showing ' + from + '–' + to + ' of ' + total + '</span>' +
      '<button class="btn btn-sm btn-secondary" data-go="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>← Prev</button>' +
      '<button class="btn btn-sm btn-secondary" data-go="' + (page + 1) + '"' + (page >= totalPages ? ' disabled' : '') + '>Next →</button>';
    paginationEl.querySelectorAll('[data-go]').forEach(btn => {
      btn.addEventListener('click', () => { page = +btn.dataset.go; render(); });
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => { page = 1; render(); });
  }
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener('change', () => {
      pageSize = parseInt(pageSizeSelect.value) || 0;
      page = 1;
      render();
    });
  }

  // --- Sort ---------------------------------------------------------------
  let currentSort = null;
  let currentDir  = 'asc';

  const sortableHeaders = table.querySelectorAll('th.sortable-col');
  sortableHeaders.forEach(th => {
    th.classList.add('sortable');
    th.tabIndex = 0;
    th.setAttribute('role', 'button');
    th.setAttribute('aria-sort', 'none');
    th.addEventListener('click', () => sortBy(th));
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(th); }
    });
  });

  function compareText(a, b) {
    return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
  }
  function compareDate(a, b) {
    if (!a && !b) return 0; if (!a) return 1; if (!b) return -1;
    return a.localeCompare(b);
  }
  function compareNumber(a, b) {
    return (parseFloat(a) || 0) - (parseFloat(b) || 0);
  }

  function sortBy(th) {
    const key  = th.dataset.sortKey;
    const type = th.dataset.sort || 'text';
    if (currentSort === key) {
      currentDir = currentDir === 'asc' ? 'desc' : 'asc';
    } else {
      currentSort = key;
      currentDir  = 'asc';
    }
    sortableHeaders.forEach(h => {
      h.classList.remove('is-sorted-asc', 'is-sorted-desc');
      h.setAttribute('aria-sort', 'none');
    });
    th.classList.add(currentDir === 'asc' ? 'is-sorted-asc' : 'is-sorted-desc');
    th.setAttribute('aria-sort', currentDir === 'asc' ? 'ascending' : 'descending');

    const cmpFn = type === 'date' ? compareDate
                : type === 'number' ? compareNumber : compareText;
    Array.from(tbody.querySelectorAll('tr'))
      .sort((rowA, rowB) => {
        const a = (rowA.dataset[key] || '').toLowerCase();
        const b = (rowB.dataset[key] || '').toLowerCase();
        return currentDir === 'asc' ? cmpFn(a, b) : -cmpFn(a, b);
      })
      .forEach(row => tbody.appendChild(row));
    page = 1;
    render();
  }

  render();
}
