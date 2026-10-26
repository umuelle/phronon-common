/* Makes a previewed participant page inert.
 *
 * The page is the real template with the real controls, because a greyed-out
 * form is not what a participant sees and an educator checking the screen
 * needs to see the screen. So instead of disabling anything, everything that
 * would LEAVE the page is swallowed here:
 *
 *   - form submissions, by a click or the Enter key (the submit event) and by
 *     a script calling form.submit(), which fires no event at all,
 *   - link navigations, including the footer's legal links, which would
 *     otherwise replace the frame with a page that has no banner and no
 *     preview context,
 *   - fetch(), so nothing a page's script sends on a timer reaches the
 *     network either.
 *
 * Ported from Whiteout on 7 October 2026 (TO DO FL-041) with one addition:
 * the form.submit() guard below. A page may submit by a script, with no
 * submit event to catch, and the gallery's frame is sandboxed without
 * allow-forms as well, so either guard alone would hold.
 *
 * Portable: no tool-specific selectors, no ids. Copy it as it is.
 *
 * The BANNER (owner, 11 September 2026): shown by the gallery, ABOVE the
 * framed screen, so the participant's page looks exactly like the page. The
 * markup still travels inside the participant document (preview_frame.html,
 * hidden), and this script reveals it only when the page is NOT framed: a
 * framed page opened on its own still says what it is. A swallowed click
 * tells the gallery to flash its banner (postMessage, same origin), so the
 * "that went nowhere" answer is still given, just outside the screen.
 *
 * Deliberately NOT here: keyboard handling. The gallery's arrows live in the
 * parent document, and a page's own keys stay its own.
 */
(function () {
  'use strict';

  function stop(e) {
    e.preventDefault();
    e.stopPropagation();
    flash();
    return false;
  }

  // Capture phase, so this runs before any handler the page installed itself:
  // a page's own script may listen for submit too, and a preview must win.
  document.addEventListener('submit', stop, true);

  // form.submit() fires no submit event, so the listener above never sees it.
  // A page may call it from a key or a swipe, and the shared actions.js calls
  // it for data-submit-form and data-submit-on-change.
  // requestSubmit() does fire the event; it is replaced too, for the same
  // answer either way.
  if (window.HTMLFormElement) {
    window.HTMLFormElement.prototype.submit = function () { flash(); };
    window.HTMLFormElement.prototype.requestSubmit = function () { flash(); };
  }

  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('a[href], button, [type="submit"]');
    if (!el) return;
    // An in-page control that only opens a <details> or a dialog is harmless
    // and useful to try — let it through.
    if (el.tagName === 'A') {
      var href = el.getAttribute('href') || '';
      if (href.charAt(0) === '#') return;
    }
    stop(e);
  }, true);

  // A page that saves over fetch() may do it on a timer, with no click at
  // all. Nothing reaches the network from a preview.
  if (window.fetch) {
    window.fetch = function () {
      return Promise.resolve(new Response('{"ok":false,"preview":true}', {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }));
    };
  }

  var framed = false;
  try { framed = window.top !== window.self; } catch (err) { framed = true; }
  var banner = document.querySelector('.preview-banner');
  if (banner && !framed) banner.hidden = false;

  var timer = null;
  function flash() {
    if (framed) {
      try { window.parent.postMessage({ type: 'preview-flash' }, window.location.origin); } catch (err) { /* no parent */ }
      return;
    }
    if (!banner) return;
    banner.classList.add('preview-banner--flash');
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      banner.classList.remove('preview-banner--flash');
    }, 700);
  }
}());
