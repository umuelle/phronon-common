/* Recovery codes: download them as a .txt before you may continue.
 *
 * Master copy — phronon_common/recovery-codes.js. Do not edit a tool's copy;
 * edit this and run server-ops/sync_shared_assets.py --write.
 *
 * The page that shows freshly made recovery codes is the only chance to keep
 * them: only hashes are stored, so they can never be shown again. An educator
 * who clicked straight past it found out on the day they lost their phone.
 * GitHub's answer, adopted on 2 October 2026 at the owner's request: a Download
 * button that saves the codes as a text file, and a continue button that stays
 * locked until the download has happened. Download is the ONLY unlock, by the
 * owner's choice — copying does not count.
 *
 * Usage in a template:
 *
 *   <ul class="tfa-codes" data-recovery-codes data-recovery-tool="Whiteout Exercise">
 *     {% for c in codes %}<li>{{ c }}</li>{% endfor %}
 *   </ul>
 *   <a class="tfa-btn" href="…" data-recovery-done>I have saved my recovery codes</a>
 *   <script src="{{ asset('/static/js/recovery-codes.js') }}" defer></script>
 *
 * The script inserts the Download button itself, straight after the list, so a
 * template carries attributes and no behaviour. Optional attributes on the list:
 *   data-recovery-button-class  classes for the Download button
 *                               (default "tfa-btn tfa-btn--secondary")
 *   data-recovery-account       the account's e-mail, written into the file
 *
 * The file is named after the tool ("whiteout-exercise-recovery-codes.txt"):
 * one person can hold accounts on several tools, each with its own codes, and
 * nine downloads called "recovery-codes.txt" would overwrite each other.
 *
 * The file is built in the browser from the codes already on the page. Nothing
 * is fetched, so the codes are never served a second time and no download route
 * exists that could hand them out.
 *
 * Without JavaScript the continue button simply works: a lock that cannot be
 * lifted would strand the user on the page. The lock is set by this script.
 *
 * Wired on DOMContentLoaded, never through an inline handler: the fleet CSP is
 * script-src 'self' + nonce, no unsafe-inline. Styles are set through the CSSOM
 * (el.style), which that CSP allows, so the locked look also works on the
 * Phronon hub, which does not load two-factor.css.
 */
(function () {
  'use strict';

  function slug(name) {
    var s = (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    return s || 'phronon';
  }

  function today() {
    var d = new Date();
    function two(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate());
  }

  function fileText(list, codes) {
    var tool = list.getAttribute('data-recovery-tool') || 'Phronon';
    var account = list.getAttribute('data-recovery-account');
    var lines = [
      tool + ' recovery codes',
      '',
      'Site:    ' + window.location.origin,
    ];
    if (account) lines.push('Account: ' + account);
    lines.push('Created: ' + today());
    lines.push('');
    lines.push('Use one of these at sign-in if you lose your authenticator app.');
    lines.push('Each code works once. Keep this file somewhere safe, such as');
    lines.push('your password manager, and delete any other copies.');
    lines.push('');
    return lines.concat(codes).join('\r\n') + '\r\n';
  }

  function lock(done) {
    done.setAttribute('aria-disabled', 'true');
    done.style.opacity = '0.45';
    done.style.cursor = 'not-allowed';
    if (done.tagName === 'BUTTON') done.disabled = true;
    else done.setAttribute('tabindex', '-1');
  }

  function unlock(done) {
    done.removeAttribute('aria-disabled');
    done.style.opacity = '';
    done.style.cursor = '';
    if (done.tagName === 'BUTTON') done.disabled = false;
    else done.removeAttribute('tabindex');
  }

  function wire(list) {
    var codes = [];
    var items = list.querySelectorAll('li');
    for (var i = 0; i < items.length; i++) {
      var c = items[i].textContent.trim();
      if (c) codes.push(c);
    }
    if (!codes.length) return;

    var tool = list.getAttribute('data-recovery-tool') || 'Phronon';
    var filename = slug(tool) + '-recovery-codes.txt';

    var button = document.createElement('button');
    button.type = 'button';
    button.className = list.getAttribute('data-recovery-button-class') ||
                       'tfa-btn tfa-btn--secondary';
    button.textContent = 'Download';
    button.setAttribute('data-recovery-download', '');
    button.style.marginBottom = '0.8rem';

    var hint = document.createElement('p');
    hint.className = 'tfa-muted';
    hint.setAttribute('role', 'status');
    hint.textContent = 'Download the codes to continue.';

    list.parentNode.insertBefore(button, list.nextSibling);
    button.parentNode.insertBefore(hint, button.nextSibling);

    var done = document.querySelector('[data-recovery-done]');
    var downloaded = false;
    if (done) {
      lock(done);
      done.addEventListener('click', function (e) {
        if (!downloaded) e.preventDefault();
      });
    }

    button.addEventListener('click', function () {
      var blob = new Blob([fileText(list, codes)], { type: 'text/plain;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      downloaded = true;
      hint.textContent = 'Saved as ' + filename + '.';
      if (done) unlock(done);
    });
  }

  function init() {
    var lists = document.querySelectorAll('[data-recovery-codes]');
    for (var i = 0; i < lists.length; i++) wire(lists[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
