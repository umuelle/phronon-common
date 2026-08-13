// Shared delegated-actions dispatcher (CSP hardening 2026-07-24; consolidated
// into one master 2026-08-13, fleet TO DO FL-017).
//
// THIS FILE IS THE MASTER. Each tool carries a copy at static/js/actions.js,
// because the tools deploy one repo at a time; `server-ops/sync_shared_assets.py`
// copies this out and reports drift. Edit HERE, then run the script with
// --write. Do not edit a tool's copy: the next sync overwrites it.
//
// Anything tool-specific belongs in that tool's own static/js/actions-local.js,
// loaded AFTER this file. Six copies had drifted apart precisely because
// per-tool wrappers were pasted into a file that called itself "canonical"
// while nothing tracked it, and a delete confirmation sat dead for months in
// Controversy Generator as a result (README §12, 11 August 2026).
//
// The CSP is script-src 'self' + per-request nonce — no 'unsafe-inline' — so
// inline on*= handlers are dead. Behaviour is wired through data-attributes,
// handled here by event delegation on document (which also catches
// dynamically-added elements):
//
//   data-click / data-change / data-keyup / data-input = "fnName"
//        calls window.fnName(...args) with `this` = the element.
//        data-args is a JSON array; the string "$this" resolves to the element
//        and "$event" to the event, e.g. data-args='[3,"$this"]'.
//   data-prevent          on a data-click element: preventDefault() after the call.
//   data-confirm="msg"    on ANY element: confirm() gate before the click.
//                         on a <form>:    confirm() gate before submit.
//   data-validate="fn"    on a <form>: submit only if window.fn.call(form, ev) is truthy.
//   data-gate="fn"        click: run window.fn first; a falsy return cancels the
//        + data-gate-args click (JSON array, "$this" resolves to the element).
//   data-navigate="/url"  click → window.location.href = url
//   data-submit-form="id" click → document.getElementById(id).submit()
//   data-submit-on-change change → submit the owning form
//   data-uppercase-code   input → force UPPERCASE, strip non [A-Z0-9]
//   data-hide-on-error    on an <img>: hide it if it fails to load (capture phase,
//                         because the error event does not bubble).
(function () {
  'use strict';
  window.pagePrint  = function () { window.print(); };
  window.pageClose  = function () { window.close(); };
  window.pageReload = function () { window.location.reload(); };
  window.pageScrollTop = function () { window.scrollTo({ top: 0 }); };
  window.pageBack = function () { history.back(); };
  window.removeParent = function () { if (this.parentElement) this.parentElement.remove(); };

  function args(el, ev) {
    var raw = el.getAttribute('data-args');
    if (!raw) return [];
    var arr;
    try { arr = JSON.parse(raw); } catch (e) { console.error('bad data-args:', raw); return []; }
    return arr.map(function (a) {
      return a === '$this' ? el : (a === '$event' ? ev : a);
    });
  }
  function call(name, el, ev) {
    var fn = window[name];
    if (typeof fn === 'function') return fn.apply(el, args(el, ev));
    console.error('data-action refers to missing function:', name);
  }

  document.addEventListener('click', function (ev) {
    var c = ev.target.closest('[data-confirm]');
    if (c && c.tagName !== 'FORM' && !window.confirm(c.getAttribute('data-confirm'))) {
      ev.preventDefault(); return;
    }
    var nav = ev.target.closest('[data-navigate]');
    if (nav) { window.location.href = nav.getAttribute('data-navigate'); return; }
    var sf = ev.target.closest('[data-submit-form]');
    if (sf) { var f = document.getElementById(sf.getAttribute('data-submit-form')); if (f) f.submit(); return; }
    var gate = ev.target.closest('[data-gate]');
    if (gate) {
      var g = window[gate.getAttribute('data-gate')];
      var gargs = gate.getAttribute('data-gate-args');
      var ok = typeof g === 'function'
        ? g.apply(gate, gargs ? JSON.parse(gargs).map(function (a) { return a === '$this' ? gate : a; }) : [])
        : true;
      if (!ok) { ev.preventDefault(); return; }
    }
    var el = ev.target.closest('[data-click]');
    if (el) {
      call(el.getAttribute('data-click'), el, ev);
      if (el.hasAttribute('data-prevent')) ev.preventDefault();
    }
  });

  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f.hasAttribute) return;
    if (f.hasAttribute('data-confirm') &&
        !window.confirm(f.getAttribute('data-confirm'))) {
      ev.preventDefault(); return;
    }
    var v = f.getAttribute('data-validate');   // form submits only if the fn returns truthy
    if (v && typeof window[v] === 'function' && !window[v].call(f, ev)) ev.preventDefault();
  });

  document.addEventListener('change', function (ev) {
    var el = ev.target;
    if (!el.getAttribute) return;
    if (el.hasAttribute('data-submit-on-change') && el.form) { el.form.submit(); return; }
    var n = el.getAttribute('data-change');
    if (n) call(n, el, ev);
  });

  document.addEventListener('keyup', function (ev) {
    var el = ev.target;
    if (el.getAttribute && el.getAttribute('data-keyup')) call(el.getAttribute('data-keyup'), el, ev);
  });

  document.addEventListener('input', function (ev) {
    var el = ev.target;
    if (!el.getAttribute) return;
    if (el.hasAttribute('data-uppercase-code')) {
      el.value = el.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); return;
    }
    var n = el.getAttribute('data-input');
    if (n) call(n, el, ev);
  });
})();

// Hide an image that fails to load, for elements marked data-hide-on-error.
// Separate listener because the error event does not bubble — it has to be
// caught in the capture phase, which is why this cannot live in the block above.
//
// The listener ALONE is not enough, and that is not theoretical: every tool
// loads this file with `defer` at the end of <body>, while the images sit
// higher up the page, so a broken image has usually already fired its error
// event by the time this line runs — the handler then never sees it. Driving
// the real file in a browser is what showed this (FL-014); reading it did not.
// So also sweep once for images that failed BEFORE we were listening: a
// finished-but-broken image is `complete` with naturalWidth 0.
document.addEventListener('error', function (ev) {
  var el = ev.target;
  if (el && el.tagName === 'IMG' && el.hasAttribute('data-hide-on-error')) {
    el.style.display = 'none';
  }
}, true);

(function () {
  'use strict';
  function hideAlreadyBroken() {
    var imgs = document.querySelectorAll('img[data-hide-on-error]');
    for (var i = 0; i < imgs.length; i++) {
      if (imgs[i].complete && imgs[i].naturalWidth === 0) imgs[i].style.display = 'none';
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hideAlreadyBroken);
  } else {
    hideAlreadyBroken();   // script added after parsing; run it now
  }
  window.addEventListener('load', hideAlreadyBroken);   // catches slow failures
})();
