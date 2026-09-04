/**
 * bulk-select.js — checkbox bulk-select + action bar for backoffice tables.
 *
 * MASTER COPY (phronon_common, 4 September 2026). Each tool carries a synced
 * copy under static/js/; edit this one and run
 * server-ops/sync_shared_assets.py --write. It had drifted into FIVE versions,
 * each holding one real feature the other four had never received.
 *
 * Two ways to wire a table, both supported:
 *   - declare it:  <table id="…" data-bulk-bar="…" data-bulk-count="…"
 *                         data-csrf="…">  — picked up on DOMContentLoaded, so
 *                  no inline bootstrap is needed under a strict CSP;
 *   - call it:     initBulkSelect({ tableId, barId, countId, csrfToken }).
 *
 * Each data row needs: <input type="checkbox" class="bulk-cb" value="{id}">
 * Each bulk-bar action button needs data-bulk-url, and may declare:
 *   data-bulk-action   a value posted as `action`
 *   data-bulk-confirm  a confirmation, preferred over data-confirm; {n} in it
 *                      is replaced by the number selected
 *   data-bulk-method   GET or POST (default POST; a GET form sends no token)
 *   data-bulk-name     the field name for the ids (default `ids`)
 */
'use strict';

function initBulkSelect(cfg) {
  const table  = document.getElementById(cfg.tableId);
  const bar    = document.getElementById(cfg.barId);
  const countEl = document.getElementById(cfg.countId);
  if (!table || !bar) return;

  const tbody     = table.querySelector('tbody');
  const selectAll = table.querySelector('.bulk-select-all');

  function getCbs() {
    return Array.from(tbody.querySelectorAll('input.bulk-cb:not([disabled])'));
  }

  function update() {
    const cbs      = getCbs();
    const checked  = cbs.filter(cb => cb.checked);
    const n        = checked.length;
    if (countEl) countEl.textContent = n;
    bar.hidden = n === 0;

    if (selectAll) {
      selectAll.indeterminate = n > 0 && n < cbs.length;
      selectAll.checked       = n > 0 && n === cbs.length;
    }

    // Enable/disable action buttons that require a minimum selection state
    bar.querySelectorAll('[data-bulk-url]').forEach(btn => {
      const onlyActive = btn.dataset.bulkOnlyActive === '1';
      if (onlyActive) {
        const activeCount = checked.filter(cb => cb.dataset.active === '1').length;
        btn.disabled = activeCount === 0;
      } else {
        btn.disabled = n === 0;
      }
    });
  }

  if (selectAll) {
    selectAll.addEventListener('change', () => {
      getCbs().forEach(cb => { cb.checked = selectAll.checked; });
      update();
    });
  }

  tbody.addEventListener('change', e => {
    if (e.target.classList.contains('bulk-cb')) update();
  });

  bar.addEventListener('click', e => {
    const btn = e.target.closest('[data-bulk-url]');
    if (!btn || btn.disabled) return;

    const url     = btn.dataset.bulkUrl;
    const action  = btn.dataset.bulkAction || '';
    // data-bulk-confirm FIRST (Layoff, 2 September 2026). A tool that loads
    // static/js/actions.js on every backoffice page has a dispatcher gating ANY
    // [data-confirm] click on a window.confirm() of its own. That listener sits
    // on `document` — one step further out than this bar — so a data-confirm
    // here is asked twice: once by us, and once again AFTER form.submit() has
    // begun navigating, which leaves a modal sitting on a page that is leaving.
    // data-confirm is still honoured for the tools that carry no dispatcher.
    const msg     = btn.dataset.bulkConfirm || btn.dataset.confirm;
    const checked = getCbs().filter(cb => cb.checked);
    if (!checked.length) return;
    // {n} is the number selected. The dashboard's confirmations are translated
    // server-side into ten languages, and the placeholder is how a sentence
    // says "thirteen" in a word order this file cannot know; the archived
    // list's own bulk handler substituted it before this engine replaced it,
    // so dropping it would have put a literal "{n}" in front of the educator.
    if (msg && !confirm(msg.replace('{n}', checked.length))) return;

    // Moral Mirror's module list posts to a GET view with its own field name,
    // so the verb and the field are declarable. Both default to what every
    // other bulk bar in the fleet already does.
    const method    = (btn.dataset.bulkMethod || 'POST').toUpperCase();
    const valueName = btn.dataset.bulkName || 'ids';

    const form = document.createElement('form');
    form.method = method;
    form.action = url;

    function hidden(name, value) {
      const el = document.createElement('input');
      el.type  = 'hidden';
      el.name  = name;
      el.value = value;
      form.appendChild(el);
    }

    // A GET form carries no CSRF token: it changes nothing, and the token
    // would land in the URL and in every log that records one.
    if (method !== 'GET') hidden('csrf_token', cfg.csrfToken);
    if (action) hidden('action', action);
    checked.forEach(cb => hidden(valueName, cb.value));

    document.body.appendChild(form);
    form.submit();
  });

  const deselectBtn = bar.querySelector('.bulk-deselect');
  if (deselectBtn) {
    deselectBtn.addEventListener('click', () => {
      getCbs().forEach(cb => { cb.checked = false; });
      if (selectAll) { selectAll.checked = false; selectAll.indeterminate = false; }
      update();
    });
  }
}

// Auto-init from data attributes so no inline bootstrap is needed (CSP:
// script-src 'self', no 'unsafe-inline'). Any <table data-bulk-bar="…"> wires up.
//
// Added here 2 September 2026, when the dashboard moved onto the fleet table.
// This file already carried Whiteout's engine byte for byte and was loaded by
// nothing — the bootstrap was the only part missing, and a table declaring
// data-bulk-bar with nothing reading it renders checkboxes that tick and a
// bulk bar that never appears.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('table[data-bulk-bar]').forEach((t) => {
    initBulkSelect({
      tableId: t.id,
      barId: t.dataset.bulkBar,
      countId: t.dataset.bulkCount,
      csrfToken: t.dataset.csrf,
    });
  });
});
