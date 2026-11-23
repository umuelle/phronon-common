/* The fleet's tab strip (TO DO FL-161, 22 November 2026). CSP: script-src 'self'.
 *
 * Markup, styled by backoffice-core.css (.tabs__nav / .tabs__tab / .active):
 *
 *   <div class="tabs__nav" role="tablist"
 *        data-tab-store="tool:page-tab"     optional: remember the tab in this window
 *        data-tab-default="responses"       optional: the tab to open on
 *        data-tab-drop="done err">          optional: address parameters a switch removes
 *     <a href="?tab=responses" class="tabs__tab active" role="tab"
 *        data-tab="responses" aria-controls="panel-responses">Responses</a>
 *     ...
 *   </div>
 *   <section id="panel-responses" role="tabpanel">...</section>
 *
 * Each tab is a link to ?tab=<name>, so a right-click offers "open in a new
 * window" and Cmd-click opens a new tab. A plain click switches here and writes
 * the tab into the address, so a reload and a copied link open it too.
 *
 * A click or a key also scrolls the page until the strip sits at the top of
 * the window, under the sticky bar (owner, 23 November 2026, as Layoff did).
 * The first opening does not scroll, so a page that restores its scroll
 * position after a refresh keeps it.
 *
 * The tab to open on: the one the address names (?tab=, or #name for old
 * bookmarks), else the one remembered in this window, else data-tab-default,
 * else the one the page marked .active, else the first. A panel is shown with
 * both `hidden` and the .active class, so a sheet may style either.
 *
 * For a page's own script (load this file before it):
 *   PhrononTabs.onShow(function (name, panel, byUser) {...})
 *       called for the tab open now and again on every change; byUser is true
 *       for a click or a key, false for the first opening and for show().
 *   PhrononTabs.show(name, remember)   open a tab; remember (default true)
 *       also writes it into the address and this window's memory.
 *   PhrononTabs.current()              the open tab's name, or null.
 * All three act on the page's first tab strip.
 */
(function () {
  'use strict';
  if (window.PhrononTabs) return;

  var strips = [];
  var listeners = [];

  function param(name) {
    try { return new URLSearchParams(window.location.search).get(name); } catch (e) { return null; }
  }

  function Strip(nav) {
    this.nav = nav;
    this.tabs = Array.prototype.slice.call(nav.querySelectorAll('.tabs__tab[data-tab]'));
    this.key = nav.getAttribute('data-tab-store');
    this.drop = (nav.getAttribute('data-tab-drop') || '').split(/\s+/).filter(Boolean);
    this.open = null;
  }

  Strip.prototype.names = function () {
    return this.tabs.map(function (t) { return t.getAttribute('data-tab'); });
  };

  Strip.prototype.has = function (name) {
    return !!name && this.names().indexOf(name) >= 0;
  };

  Strip.prototype.panel = function (tab) {
    var id = tab.getAttribute('aria-controls');
    return id ? document.getElementById(id) : null;
  };

  Strip.prototype.first = function () {
    var hash = (window.location.hash || '').replace('#', '');
    var stored = null;
    if (this.key) {
      try { stored = sessionStorage.getItem(this.key); } catch (e) { /* private mode */ }
    }
    var marked = this.nav.querySelector('.tabs__tab.active[data-tab]');
    var candidates = [param('tab'), hash, stored, this.nav.getAttribute('data-tab-default'),
                      marked && marked.getAttribute('data-tab'), this.names()[0]];
    for (var i = 0; i < candidates.length; i++) {
      if (this.has(candidates[i])) return candidates[i];
    }
    return null;
  };

  Strip.prototype.remember = function (name) {
    if (this.key) {
      try { sessionStorage.setItem(this.key, name); } catch (e) { /* private mode */ }
    }
    try {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', name);
      this.drop.forEach(function (p) { url.searchParams.delete(p); });
      if (this.has(url.hash.replace('#', ''))) url.hash = '';
      history.replaceState(history.state, '', url);
    } catch (e) { /* an old browser keeps the address as it was */ }
  };

  Strip.prototype.show = function (name, remember, byUser) {
    if (!this.has(name)) return false;
    var self = this;
    var shown = null;
    this.tabs.forEach(function (t) {
      var mine = t.getAttribute('data-tab') === name;
      t.classList.toggle('active', mine);
      t.setAttribute('aria-selected', mine ? 'true' : 'false');
      var p = self.panel(t);
      if (p) {
        p.hidden = !mine;
        p.classList.toggle('active', mine);
        if (mine) shown = p;
      }
    });
    this.open = name;
    if (remember) this.remember(name);
    if (byUser) this.bringUp();
    if (this === strips[0]) {
      listeners.forEach(function (fn) { fn(name, shown, !!byUser); });
    }
    return true;
  };

  Strip.prototype.bringUp = function () {
    var calm = false;
    try { calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { /* old browser */ }
    try {
      this.nav.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
    } catch (e) {
      this.nav.scrollIntoView(true);
    }
  };

  Strip.prototype.wire = function () {
    var self = this;
    this.tabs.forEach(function (t) {
      t.addEventListener('click', function (e) {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        self.show(t.getAttribute('data-tab'), true, true);
      });
    });
    // Arrow keys, Home and End move between tabs; Space opens the focused one
    // (Enter does, as on any link).
    this.nav.addEventListener('keydown', function (e) {
      var i = self.tabs.indexOf(document.activeElement);
      if (i < 0) return;
      var n = self.tabs.length;
      var next = e.key === 'ArrowRight' ? (i + 1) % n
               : e.key === 'ArrowLeft' ? (i - 1 + n) % n
               : e.key === 'Home' ? 0
               : e.key === 'End' ? n - 1
               : e.key === ' ' ? i : -1;
      if (next < 0) return;
      e.preventDefault();
      self.tabs[next].focus();
      self.show(self.tabs[next].getAttribute('data-tab'), true, true);
    });
  };

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll('.tabs__nav'), function (nav) {
      var s = new Strip(nav);
      if (!s.tabs.length) return;
      strips.push(s);
      s.wire();
    });
    strips.forEach(function (s) {
      var name = s.first();
      // Write the address only when it already names this strip's tab, so a
      // page opened without one keeps its plain address.
      if (name) s.show(name, s.has(param('tab')), false);
    });
  }

  window.PhrononTabs = {
    onShow: function (fn) {
      listeners.push(fn);
      var s = strips[0];
      if (s && s.open) {
        var tab = s.tabs[s.names().indexOf(s.open)];
        fn(s.open, s.panel(tab), false);
      }
    },
    show: function (name, remember) {
      var s = strips[0];
      return s ? s.show(name, remember !== false, false) : false;
    },
    current: function () {
      return strips[0] ? strips[0].open : null;
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
