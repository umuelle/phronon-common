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

  function init() {
    if (!window.PublicKeyCredential || !navigator.credentials) return;  // stay hidden
    var reg = document.querySelectorAll('[data-passkey-register]');
    for (var i = 0; i < reg.length; i++) wire(reg[i], 'register');
    var login = document.querySelectorAll('[data-passkey-login]');
    for (var j = 0; j < login.length; j++) wire(login[j], 'login');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
