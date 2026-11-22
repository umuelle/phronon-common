// The fleet's message panel (phronon_common.messages, owner 22 November 2026).
//
// One script for both sides. The tool renders the panel with the macro in
// account_templates/messages.html; this script keeps it current and sends:
//   * it asks data-poll-url?token=<last token> every data-poll-ms; the answer is
//     {"same": true} while nothing changed, else {"token", "messages",
//     "can_send", "state"}; it redraws the list from the messages;
//   * the form posts to its action (X-CSRF-Token from the page's meta, the
//     form's own fields); the answer is {"sent": true, ...as a poll} or
//     {"sent": false, "reason": "empty" | "too_fast" | "recipient" | "off" | "closed"};
//   * a message from somebody else that this browser has not seen yet shows a
//     short pop-up (data-toast), also after the page reloaded itself;
//   * what is being typed survives the page's own reloads (sessionStorage).
// The educator's side (data-mode="educator") has a Hide / Show again button
// on every message, posting to data-hide-url with id and hidden.
// Text is only ever written with textContent.
(function () {
  'use strict';
  var root = document.querySelector('[data-messages]');
  if (!root) { return; }
  var educator = root.getAttribute('data-mode') === 'educator';
  var words = {};
  try { words = JSON.parse(root.getAttribute('data-words') || '{}'); } catch (e) { words = {}; }
  var list = root.querySelector('[data-messages-list]');
  var empty = root.querySelector('[data-messages-empty]');
  var form = root.querySelector('[data-messages-form]');
  var field = form ? form.querySelector('textarea') : null;
  var to = form ? form.querySelector('select[name="to"]') : null;
  var status = root.querySelector('[data-messages-status]');
  var counter = root.querySelector('[data-messages-count]');
  var stateLine = root.querySelector('[data-messages-state]');
  var scope = root.getAttribute('data-scope') || 'messages';
  var token = root.getAttribute('data-token') || '';
  var pollUrl = root.getAttribute('data-poll-url');
  var pollMs = parseInt(root.getAttribute('data-poll-ms'), 10) || 3000;
  var hideUrl = root.getAttribute('data-hide-url');
  var maxLength = field ? (parseInt(field.getAttribute('maxlength'), 10) || 300) : 300;
  var seenKey = 'ph-messages-seen:' + scope;
  var draftKey = 'ph-messages-draft:' + scope;
  var shown = [];

  function say(key, values) {
    var text = words[key] || key;
    Object.keys(values || {}).forEach(function (k) { text = text.split('{' + k + '}').join(values[k]); });
    return text;
  }
  function store(key, value) {
    try {
      if (value === null) { window.sessionStorage.removeItem(key); } else { window.sessionStorage.setItem(key, value); }
    } catch (e) { /* storage off (private window, preview): the panel works without it */ }
  }
  function stored(key) {
    try { return window.sessionStorage.getItem(key); } catch (e) { return null; }
  }
  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var own = root.querySelector('input[name="csrf_token"]');
    return (meta && meta.getAttribute('content')) || (own ? own.value : '');
  }

  // ---- the list
  function item(m) {
    var li = document.createElement('li');
    li.className = 'ph-messages__item' + (m.mine ? ' ph-messages__item--mine' : '') +
      (m.direct ? ' ph-messages__item--direct' : '') + (m.hidden ? ' ph-messages__item--hidden' : '');
    li.setAttribute('data-message-id', String(m.id));
    var head = document.createElement('p');
    head.className = 'ph-messages__head';
    head.textContent = say('from_to', { from: m.from, to: m.to });
    var extra = [m.room, m.stage].filter(function (x) { return x; }).join(' · ');
    if (extra) {
      var small = document.createElement('span');
      small.className = 'ph-messages__when';
      small.textContent = ' · ' + extra;
      head.appendChild(small);
    }
    li.appendChild(head);
    var body = document.createElement('p');
    body.className = 'ph-messages__text';
    body.textContent = m.text;
    li.appendChild(body);
    if (educator) {
      if (m.hidden) {
        var mark = document.createElement('p');
        mark.className = 'ph-messages__hidden';
        mark.textContent = say('hidden');
        li.appendChild(mark);
      }
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm btn-ghost ph-messages__hide';
      button.setAttribute('data-message-hide', m.hidden ? '0' : '1');
      button.textContent = m.hidden ? say('show_again') : say('hide');
      li.appendChild(button);
    }
    return li;
  }
  function draw(messages) {
    if (!list) { return; }
    var atEnd = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    list.textContent = '';
    messages.forEach(function (m) { list.appendChild(item(m)); });
    if (empty) { empty.hidden = messages.length > 0; }
    if (atEnd || !shown.length) { list.scrollTop = list.scrollHeight; }
    shown = messages;
  }
  function setState(canSend, state) {
    if (!form) { return; }
    var off = !canSend;
    form.hidden = off;
    if (stateLine) {
      stateLine.hidden = !off;
      stateLine.textContent = off ? say(state === 'closed' ? 'closed' : 'off') : '';
    }
  }

  // ---- the pop-up
  var toast = null;
  var toastTimer = null;
  function closeToast() {
    if (toast) { toast.hidden = true; }
    clearTimeout(toastTimer);
  }
  function showToast(m) {
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'ph-messages-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      toast.setAttribute('data-toast', '');
      var line = document.createElement('p');
      line.className = 'ph-messages-toast__line';
      toast.appendChild(line);
      var read = document.createElement('button');
      read.type = 'button';
      read.className = 'ph-messages-toast__read';
      read.textContent = say('read');
      read.addEventListener('click', function () {
        closeToast();
        root.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (field && !form.hidden) { field.focus({ preventScroll: true }); }
      });
      toast.appendChild(read);
      var close = document.createElement('button');
      close.type = 'button';
      close.className = 'ph-messages-toast__close';
      close.setAttribute('aria-label', say('dismiss'));
      close.textContent = '×';
      close.addEventListener('click', closeToast);
      toast.appendChild(close);
      document.body.appendChild(toast);
    }
    toast.querySelector('.ph-messages-toast__line').textContent = say('new_from', { from: m.from });
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(closeToast, 8000);
  }
  function announce(messages) {
    var seen = parseInt(stored(seenKey), 10);
    var last = messages.length ? messages[messages.length - 1].id : 0;
    if (isNaN(seen)) { store(seenKey, String(last)); return; }   // the first look: nothing is new
    var fresh = messages.filter(function (m) {
      return m.id > seen && !m.mine && !m.hidden && !(educator && m.sender === 0);
    });
    if (fresh.length) { showToast(fresh[fresh.length - 1]); }
    if (last > seen) { store(seenKey, String(last)); }
  }

  function take(answer) {
    if (!answer || answer.preview || answer.same) { return; }
    if (answer.token !== undefined) { token = String(answer.token); }
    if (answer.messages) { draw(answer.messages); announce(answer.messages); }
    if (answer.can_send !== undefined) { setState(!!answer.can_send, answer.state); }
  }

  // ---- staying current
  function poll() {
    if (!pollUrl) { return; }
    var sep = pollUrl.indexOf('?') < 0 ? '?' : '&';
    fetch(pollUrl + sep + 'token=' + encodeURIComponent(token), {
      credentials: 'same-origin', headers: { 'Accept': 'application/json' }
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(take)
      .catch(function () { /* the next tick tries again */ });
  }

  // ---- writing
  function saveDraft() {
    if (!field) { return; }
    store(draftKey, JSON.stringify({ text: field.value, to: to ? to.value : '',
                                     focus: document.activeElement === field }));
  }
  function count() {
    if (!counter || !field) { return; }
    var left = maxLength - field.value.length;
    counter.hidden = left > 50;
    counter.textContent = say('chars_left', { n: String(left) });
  }
  function restoreDraft() {
    if (!field) { return; }
    var d = null;
    try { d = JSON.parse(stored(draftKey) || 'null'); } catch (e) { d = null; }
    if (!d) { return; }
    if (d.text) { field.value = d.text; }
    if (to && d.to && to.querySelector('option[value="' + String(d.to).replace(/"/g, '') + '"]')) { to.value = d.to; }
    if (d.focus && !form.hidden) {
      field.focus({ preventScroll: true });
      field.setSelectionRange(field.value.length, field.value.length);
    }
    count();
  }
  function send(ev) {
    ev.preventDefault();
    if (!field || !field.value.trim()) { return; }
    var button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; }
    if (status) { status.textContent = ''; }
    fetch(form.getAttribute('action'), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrf(), 'Accept': 'application/json',
                 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(new FormData(form)).toString()
    }).then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (answer) {
        if (answer && answer.preview) { return; }
        if (answer && answer.sent) {
          field.value = '';
          store(draftKey, JSON.stringify({ text: '', to: to ? to.value : '', focus: true }));
          count();
          if (list) { list.scrollTop = list.scrollHeight; }
          take(answer);
          if (list) { list.scrollTop = list.scrollHeight; }
          return;
        }
        if (status) { status.textContent = say(answer && answer.reason === 'too_fast' ? 'too_fast' : 'failed'); }
        if (answer) { take(answer); }
      })
      .catch(function () { if (status) { status.textContent = say('failed'); } })
      .then(function () { if (button) { button.disabled = false; } field.focus({ preventScroll: true }); });
  }

  if (form && field) {
    form.addEventListener('submit', send);
    field.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); form.requestSubmit(); }
    });
    field.addEventListener('input', function () { saveDraft(); count(); });
    field.addEventListener('focus', saveDraft);
    field.addEventListener('blur', saveDraft);
    if (to) { to.addEventListener('change', saveDraft); }
    window.addEventListener('pagehide', saveDraft);
  }
  if (educator && list && hideUrl) {
    list.addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-message-hide]');
      if (!button) { return; }
      var li = button.closest('[data-message-id]');
      button.disabled = true;
      fetch(hideUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf(), 'Accept': 'application/json',
                   'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ csrf_token: csrf(), id: li.getAttribute('data-message-id'),
                                    hidden: button.getAttribute('data-message-hide') }).toString()
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(take)
        .catch(function () { /* the next poll shows how it stands */ })
        .then(function () { button.disabled = false; });
    });
  }

  var initial = [];
  try { initial = JSON.parse(root.getAttribute('data-initial') || '[]'); } catch (e) { initial = []; }
  draw(initial);
  announce(initial);
  setState(root.getAttribute('data-can-send') === '1', root.getAttribute('data-state'));
  restoreDraft();
  setInterval(poll, pollMs);
})();
