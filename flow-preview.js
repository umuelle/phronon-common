/* The gallery around the framed participant screen.
 *
 * Everything here is an ENHANCEMENT. The arrows are real links and the screen
 * list is real links, so the preview works with JavaScript switched off, works
 * with the keyboard, and every screen has its own URL an educator can bookmark
 * or paste into a mail. What this file adds is the two things links cannot do:
 * the left/right keys, and a width toggle that does not need a round trip.
 *
 * Portable: no tool-specific selectors. Copy it as it is.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-preview-root]');
  if (!root) return;

  /* ← and → move between screens, the way a photo gallery does. Ignored while
     the focus is in a field, so typing in a form on this page is never eaten,
     and ignored with a modifier held, because Cmd+← is "back" in the browser
     and stealing it would be rude. */
  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var rel = e.key === 'ArrowLeft' ? 'prev' : (e.key === 'ArrowRight' ? 'next' : null);
    if (!rel) return;
    var link = root.querySelector('a[rel="' + rel + '"]');
    if (!link) return;
    e.preventDefault();
    window.location.href = link.href;
  });

  /* Grow the frame to whatever the screen inside it needs, so there is never a
     scrollbar within a scrollbar. Same origin, so the document is readable;
     wrapped anyway, because a frame that fails to measure should keep its
     fallback height rather than throw. */
  var frame = root.querySelector('.flow-preview__frame');
  function fit() {
    if (!frame) return;
    try {
      var doc = frame.contentDocument;
      if (!doc || !doc.body) return;
      // COLLAPSE FIRST. The frame's height IS the inner viewport height, so a
      // document that has been stretched to 14 000px reports at least 14 000px
      // of scrollHeight no matter how short its content has become — and the
      // frame could only ever grow. Widening from phone to full width left a
      // screen of empty space below the page (found in a browser, 23 August
      // 2026; nothing in the source says it).
      frame.style.height = '200px';
      var h = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
      frame.style.height = (h > 200 ? h + 24 : 900) + 'px';
    } catch (err) {
      frame.style.height = '900px';        // cross-origin, or not loaded yet
    }
  }
  /* Width. A participant is on a phone; an educator is not, and the screen an
     educator has never seen is the narrow one. */
  var stage = root.querySelector('.flow-preview__stage');
  var buttons = root.querySelectorAll('[data-preview-width]');
  var PHONE = 390;

  /* The chosen width rides in the address (#width=820), and every link back
     into this preview carries it, so the arrows, the keys and the screen list
     keep it from screen to screen. Nothing is stored on the educator's device
     (owner, 7 October 2026: no remembered width). A fresh visit starts at
     phone width. */
  function widthInAddress() {
    var m = /^#width=(\d+)$/.exec(window.location.hash);
    return m ? parseInt(m[1], 10) : PHONE;
  }

  function carryWidth(px) {
    var tag = px === PHONE ? '' : '#width=' + px;
    Array.prototype.forEach.call(document.querySelectorAll('a[href]'), function (a) {
      if (a.pathname === window.location.pathname) a.hash = tag;
    });
    if (window.location.hash !== tag && window.history.replaceState) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search + tag);
    }
  }

  function setWidth(px) {
    if (!stage) return;
    // 'none', NOT '' — the stylesheet's own max-width is the phone width, so
    // clearing the inline value fell back to it and "Full width" did nothing
    // (owner, 23 August 2026).
    stage.style.maxWidth = px ? px + 'px' : 'none';
    Array.prototype.forEach.call(buttons, function (b) {
      var on = String(b.dataset.previewWidth) === String(px);
      b.classList.toggle('btn-primary', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    carryWidth(px);
    // A narrower page is a taller page: re-measure, or the frame keeps the
    // height of the width it was last measured at.
    fit();
  }

  Array.prototype.forEach.call(buttons, function (b) {
    b.addEventListener('click', function () { setWidth(parseInt(b.dataset.previewWidth, 10) || 0); });
  });

  setWidth(widthInAddress());

  if (frame) {
    frame.addEventListener('load', function () { fit(); window.setTimeout(fit, 400); });
    window.addEventListener('resize', fit);
  }

  /* The banner lives up here, above the frame (owner, 11 September 2026).
     A click swallowed inside the frame posts a message; the answer — "that
     went nowhere" — is given by flashing this banner, not one in the page. */
  var banner = root.querySelector('.preview-banner');
  var flashTimer = null;
  window.addEventListener('message', function (e) {
    if (e.origin !== window.location.origin) return;
    if (!e.data || e.data.type !== 'preview-flash' || !banner) return;
    banner.classList.add('preview-banner--flash');
    window.clearTimeout(flashTimer);
    flashTimer = window.setTimeout(function () {
      banner.classList.remove('preview-banner--flash');
    }, 700);
  });
}());
