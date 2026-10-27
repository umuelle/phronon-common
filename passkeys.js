/* Passkeys: add one on the account page, sign in with one on the login page.
 *
 * Master copy — phronon_common/passkeys.js. Do not edit a tool's copy; edit
 * this and run server-ops/sync_shared_assets.py --write.
 *
 * FL-065 (2 October 2026). The server side is phronon_common/passkeys.py; this
 * file only moves the browser's half of the two WebAuthn ceremonies: fetch the
 * options, ask the browser (Touch ID, Face ID, Windows Hello, a security key),
 * post the answer back. Templates carry attributes and no behaviour.
 *
 * Account page:
 *   <div data-passkey-register hidden
 *        data-options-url="/backoffice/passkeys/options"
 *        data-submit-url="/backoffice/passkeys"
 *        data-csrf="{{ token }}">
 *     <input data-passkey-name …>            optional label, e.g. "MacBook"
 *     <button type="button" data-passkey-start>Add a passkey</button>
 *     <p data-passkey-status role="status"></p>
 *   </div>
 *   On success the page reloads, so the new passkey shows in the list.
 *
 * Login page:
 *   <div data-passkey-login hidden
 *        data-options-url="/backoffice/login/passkey/options"
 *        data-submit-url="/backoffice/login/passkey"
 *        data-csrf="{{ token }}">
 *     <button type="button" data-passkey-start>Sign in with a passkey</button>
 *     <p data-passkey-status role="status"></p>
 *   </div>
 *   On success the browser goes where the server says ({"redirect": …}).
 *
 *   Since 1.83.0 (owner, 10 October 2026: "after setting up a passkey, other
 *   sites know that this is established"), two more ways in, both optional:
 *   - data-autofill-url="/backoffice/login/passkey/autofill" on the
 *     block and autocomplete="username webauthn" on the e-mail field: as the
 *     page opens the browser is asked with mediation "conditional", so it
 *     lists a saved passkey in the field's autofill (one tap and Touch ID).
 *     The waiting request is renewed every four minutes, before its
 *     five-minute challenge expires, and cancelled before the button asks,
 *     since a browser refuses a second request while one is open.
 *   - "Log in" with the password left empty, in the form that holds that
 *     e-mail field, asks for the passkey in place of sending the form.
 *
 *   Since 1.84.0 (owner, 11 October 2026: a password manager filled both
 *   fields, so neither way above ever started): after a passkey sign-in the
 *   browser keeps a marker in its own storage (localStorage
 *   "phronon-passkey-signin" = "1", nothing else, never sent to the server).
 *   On the next visit the page hides the sign-in form and the element marked
 *   data-passkey-or, and shows the element marked data-passkey-use-password
 *   (it holds a link, "Use e-mail and password instead", which brings the
 *   form back for this visit). Each tool's cookie table lists the marker.
 *
 *   Since 1.97.0 (owner, 27 October 2026: in Safari the fingerprint prompt
 *   took a long time to appear): the button asks the browser at once, inside
 *   the click, with a challenge the page fetched before. Every challenge
 *   request replaces the one in the server's cookie, so the page keeps the
 *   options of the latest one: the autofill request's, or in the
 *   passkey-first view a challenge fetched from data-autofill-url only for the
 *   button, renewed on the same four-minute clock. A ready challenge is used
 *   once, and only while it has more than a minute left, the prompt's own
 *   timeout. Without one (the page has just opened, or the last one was used)
 *   the click fetches a challenge first, as before.
 *
 * Both blocks start `hidden` and are shown only when the browser can do
 * passkeys at all, so nobody is offered a button that cannot work. The server
 * answers every POST with JSON: options, {"ok": true}, {"redirect": url} or
 * {"error": message-safe-to-show}.
 *
 * Requests are form-encoded with the page's CSRF token, like every other form
 * in the fleet, so each tool checks them with the CSRF helper it already has.
 * Wired on DOMContentLoaded; no inline handlers (CSP: script-src 'self').
 */
(function () {
  'use strict';

  function b64urlToBuf(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out.buffer;
  }

  function bufToB64url(buf) {
    var bytes = new Uint8Array(buf), bin = '';
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function creationOptions(o) {
    if (window.PublicKeyCredential && PublicKeyCredential.parseCreationOptionsFromJSON) {
      return PublicKeyCredential.parseCreationOptionsFromJSON(o);
    }
    o.challenge = b64urlToBuf(o.challenge);
    o.user.id = b64urlToBuf(o.user.id);
    (o.excludeCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
    return o;
  }

  function requestOptions(o) {
    if (window.PublicKeyCredential && PublicKeyCredential.parseRequestOptionsFromJSON) {
      return PublicKeyCredential.parseRequestOptionsFromJSON(o);
    }
    o.challenge = b64urlToBuf(o.challenge);
    (o.allowCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
    return o;
  }

  function credentialJSON(cred) {
    if (typeof cred.toJSON === 'function') {
      try { return JSON.stringify(cred.toJSON()); } catch (e) { /* fall through */ }
    }
    var r = cred.response, response = { clientDataJSON: bufToB64url(r.clientDataJSON) };
    if (r.attestationObject) {
      response.attestationObject = bufToB64url(r.attestationObject);
      if (typeof r.getTransports === 'function') response.transports = r.getTransports();
    } else {
      response.authenticatorData = bufToB64url(r.authenticatorData);
      response.signature = bufToB64url(r.signature);
      if (r.userHandle) response.userHandle = bufToB64url(r.userHandle);
    }
    return JSON.stringify({
      id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type, response: response,
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
      authenticatorAttachment: cred.authenticatorAttachment || undefined
    });
  }

  function post(url, fields) {
    var body = new URLSearchParams();
    Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
    return fetch(url, {
      method: 'POST', credentials: 'same-origin', body: body,
      headers: { 'Accept': 'application/json' }
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        // Our routes answer {"error": …}; a rate limiter or FastAPI itself
        // answers {"detail": …}, which is a string for a 429 and a list for a
        // validation error (not worth showing).
        var msg = data.error || (typeof data.detail === 'string' ? data.detail : '');
        if (res.status === 429 && !data.error) msg = 'Too many attempts. Wait a minute and try again.';
        if (!res.ok || data.error) throw new Error(msg || 'Something went wrong. Please try again.');
        return data;
      });
    });
  }

  function friendly(err) {
    // The browser's own errors: the user closed the prompt, or it timed out.
    if (err && (err.name === 'NotAllowedError' || err.name === 'AbortError')) {
      return 'Cancelled. Nothing was changed.';
    }
    if (err && err.name === 'InvalidStateError') {
      return 'This device already has a passkey for this account.';
    }
    return (err && err.message) || 'Something went wrong. Please try again.';
  }

  function wire(box, mode) {
    var start = box.querySelector('[data-passkey-start]');
    var status = box.querySelector('[data-passkey-status]');
    var nameInput = box.querySelector('[data-passkey-name]');
    var csrf = box.getAttribute('data-csrf') || '';
    if (!start) return;
    box.hidden = false;

    function say(msg) { if (status) status.textContent = msg; }

    start.addEventListener('click', function () {
      start.disabled = true;
      say(mode === 'register' ? 'Follow the prompt on your device…' : 'Waiting for your passkey…');
      post(box.getAttribute('data-options-url'), { csrf_token: csrf })
        .then(function (options) {
          return mode === 'register'
            ? navigator.credentials.create({ publicKey: creationOptions(options) })
            : navigator.credentials.get({ publicKey: requestOptions(options) });
        })
        .then(function (cred) {
          var fields = { csrf_token: csrf, credential: credentialJSON(cred) };
          if (nameInput) fields.name = nameInput.value;
          return post(box.getAttribute('data-submit-url'), fields);
        })
        .then(function (data) {
          if (data.redirect) { window.location.assign(data.redirect); return; }
          say('Passkey added.');
          window.location.reload();
        })
        .catch(function (err) { say(friendly(err)); start.disabled = false; });
    });
  }

  var RENEW_MS = 4 * 60 * 1000;
  var MARKER = 'phronon-passkey-signin';

  // Private browsing or blocked storage: no marker, the page stays as it is.
  function remembered() {
    try { return window.localStorage.getItem(MARKER) === '1'; } catch (e) { return false; }
  }
  function remember() {
    try { window.localStorage.setItem(MARKER, '1'); } catch (e) { /* not kept */ }
  }

  // Shown or not, whatever a tool's own CSS says about `display` for the
  // element's class (a class rule beats the [hidden] attribute).
  function show(el, on) {
    if (!el) return;
    el.hidden = !on;
    el.style.display = on ? '' : 'none';
  }

  function wireLogin(box) {
    var start = box.querySelector('[data-passkey-start]');
    var status = box.querySelector('[data-passkey-status]');
    var csrf = box.getAttribute('data-csrf') || '';
    var field = document.querySelector('input[autocomplete~="webauthn"]');
    var form = field && field.form;
    var waiting = null;      // the AbortController of the autofill request
    var renew = null;
    var reoffers = 2;        // after a refused passkey; never a loop of requests
    var ready = null;        // the latest challenge's options, as JSON text
    var readyAt = 0;
    var inFlight = null;     // the challenge request on its way, if any
    box.hidden = false;

    function say(msg) { if (status) status.textContent = msg; }

    // The server keeps one challenge per browser (its cookie), the latest one
    // it handed out, so `ready` always holds the latest options that arrived.
    function fetchChallenge(url) {
      var req = post(url, { csrf_token: csrf });
      inFlight = req;
      return req.then(function (options) {
        if (inFlight === req) inFlight = null;
        ready = JSON.stringify(options);
        readyAt = Date.now();
        return options;
      }, function (err) {
        if (inFlight === req) inFlight = null;
        throw err;
      });
    }

    // Used once, and only while it outlives the prompt by a margin (RENEW_MS
    // is the five-minute challenge less the prompt's one-minute timeout).
    function takeReady() {
      var options = ready && Date.now() - readyAt < RENEW_MS ? JSON.parse(ready) : null;
      ready = null;
      return options;
    }

    // No ready challenge: wait for the one on its way, else fetch one. Never
    // two at once, or the cookie could end up holding the other challenge.
    function challengeForButton() {
      var pending = inFlight ? inFlight.then(null, function () { return null; })
                             : Promise.resolve(null);
      return pending.then(function () {
        return takeReady() || fetchChallenge(box.getAttribute('data-options-url'))
          .then(function () { return takeReady(); });
      });
    }

    function signIn(cred) {
      return post(box.getAttribute('data-submit-url'),
                  { csrf_token: csrf, credential: credentialJSON(cred) })
        .then(function (data) {
          remember();
          if (data.redirect) window.location.assign(data.redirect);
        });
    }

    function stopWaiting() {
      if (renew) { clearTimeout(renew); renew = null; }
      if (waiting) { waiting.abort(); waiting = null; }
    }

    function offerInAutofill() {
      var url = box.getAttribute('data-autofill-url');
      if (!url) return;
      // No autofill offer in this browser: still keep a challenge ready.
      if (!field || !PublicKeyCredential.isConditionalMediationAvailable) { keepReady(); return; }
      PublicKeyCredential.isConditionalMediationAvailable().then(function (available) {
        if (!available) { keepReady(); return; }
        stopWaiting();
        var ctrl = new AbortController();
        var picked = false;
        waiting = ctrl;
        renew = setTimeout(offerInAutofill, RENEW_MS);
        fetchChallenge(url)
          .then(function (options) {
            if (ctrl.signal.aborted) return null;
            return navigator.credentials.get({
              publicKey: requestOptions(options), mediation: 'conditional', signal: ctrl.signal
            });
          })
          .then(function (cred) {
            if (!cred || ctrl.signal.aborted) return null;
            picked = true;
            ready = null;            // this challenge is spent
            stopWaiting();
            say('Signing in…');
            return signIn(cred);
          })
          .catch(function (err) {
            if (!picked) return;     // renewed, cancelled, or no autofill here
            say(friendly(err));      // a passkey was picked and refused
            if (reoffers-- > 0) offerInAutofill();
          });
      }).catch(function () { keepReady(); });   // no autofill offer; the button remains
    }

    // The passkey-first view shows no e-mail field to offer the passkey in, so
    // it only keeps a challenge ready for the button, on the autofill budget
    // and the autofill clock.
    function keepReady() {
      var url = box.getAttribute('data-autofill-url');
      if (!url) return;
      stopWaiting();
      renew = setTimeout(keepReady, RENEW_MS);
      fetchChallenge(url).catch(function () { /* the button fetches its own */ });
    }

    function askForPasskey(afterFailure) {
      stopWaiting();
      if (start) start.disabled = true;
      say('Waiting for your passkey…');
      var options = takeReady();
      var asked = options
        // Still inside the click, as Safari wants it: no round trip first.
        ? navigator.credentials.get({ publicKey: requestOptions(options) })
        : challengeForButton().then(function (fetched) {
          return navigator.credentials.get({ publicKey: requestOptions(fetched) });
        });
      asked
        .then(signIn)
        .catch(function (err) {
          say(afterFailure || friendly(err));
          if (start) start.disabled = false;
          offerInAutofill();
        });
    }

    if (start) start.addEventListener('click', function () { askForPasskey(); });

    // The passkey first: this browser has signed in with one before.
    var orLine = box.querySelector('[data-passkey-or]');
    var usePassword = box.querySelector('[data-passkey-use-password]');
    var passkeyFirst = !!(form && usePassword && remembered());
    show(usePassword, passkeyFirst);
    if (passkeyFirst) {
      show(form, false);
      show(orLine, false);
      var link = usePassword.querySelector('a, button') || usePassword;
      link.addEventListener('click', function (e) {
        e.preventDefault();
        show(form, true);
        show(orLine, true);
        show(usePassword, false);
        if (field) field.focus();
        offerInAutofill();
      });
      if (start) start.focus();
    }

    if (form) {
      var password = form.querySelector('input[type="password"]');
      form.addEventListener('submit', function (e) {
        if (!password || password.value) return;      // a password: send the form
        e.preventDefault();
        askForPasskey('No passkey was used. Type your password, or try your passkey again.');
      });
    }

    if (passkeyFirst) keepReady();
    else offerInAutofill();
  }

  function init() {
    if (!window.PublicKeyCredential || !navigator.credentials) return;  // stay hidden
    var reg = document.querySelectorAll('[data-passkey-register]');
    for (var i = 0; i < reg.length; i++) wire(reg[i], 'register');
    var login = document.querySelectorAll('[data-passkey-login]');
    for (var j = 0; j < login.length; j++) wireLogin(login[j]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
