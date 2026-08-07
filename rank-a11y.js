/* Accessible reordering for drag-and-drop ranking lists — Phronon fleet.
 *
 * WHY THIS EXISTS
 * Sortable.js gives us mouse/touch dragging and nothing else. That fails three
 * WCAG 2.2 AA criteria at once:
 *
 *   2.5.7 Dragging Movements (NEW in WCAG 2.2, level AA) — anything achievable
 *         by dragging must also be achievable with a SINGLE POINTER without
 *         dragging. A participant with a tremor, or using a head-pointer,
 *         eye-tracker or switch, cannot drag. A keyboard shortcut does NOT
 *         satisfy this criterion; it explicitly requires a pointer path.
 *   2.1.1 Keyboard — the ranking is the whole exercise, so with drag-only
 *         input a keyboard-only participant cannot complete it at all.
 *   2.4.7 / 4.1.2 — hidden shortcuts announced only in an aria-label are
 *         invisible to sighted keyboard users.
 *
 * So each row gets two REAL buttons (move up / move down). Buttons are
 * single-pointer operable, keyboard operable, focusable, and discoverable —
 * one control satisfying all three criteria, instead of a hidden shortcut.
 *
 * Deliberately NOT using inline onclick: the fleet serves
 * `script-src 'self' <nonce>` with no unsafe-inline, so handlers are attached
 * with addEventListener from this file (served from /static, i.e. 'self').
 *
 * Usage:
 *   PhrononRankA11y.enhance({
 *     list: '#rank-list',                 // element or selector
 *     itemSelector: '.rank-item',         // rows within the list
 *     onChange: updateNumbers,            // called after every move
 *     labelOf: el => el.dataset.name,     // accessible name of a row
 *     strings: { up: 'Move up', down: 'Move down', moved: '{name}, position {pos} of {total}' }
 *   });
 *
 * Safe to call more than once on the same list: it will not add a second set
 * of buttons.
 */
(function (global) {
  'use strict';

  function resolve(target) {
    return typeof target === 'string' ? document.querySelector(target) : target;
  }

  function enhance(options) {
    var list = resolve(options.list);
    if (!list || list.getAttribute('data-rank-a11y') === 'on') return;
    list.setAttribute('data-rank-a11y', 'on');

    var itemSelector = options.itemSelector || 'li';
    var onChange = typeof options.onChange === 'function' ? options.onChange : function () {};
    var s = options.strings || {};
    var upLabel = s.up || 'Move up';
    var downLabel = s.down || 'Move down';
    // "{name} moved to position {pos} of {total}"
    var movedTpl = s.moved || '{name}: position {pos} of {total}';
    var labelOf = typeof options.labelOf === 'function' ? options.labelOf : function (el, i) {
      var t = (el.textContent || '').trim().replace(/\s+/g, ' ');
      return t.length > 60 ? t.slice(0, 60) : (t || 'Item ' + (i + 1));
    };

    // One polite live region per list, so a screen reader announces the new
    // position after a move. Without this the reorder is silent and the user
    // has no way to confirm what happened.
    var live = document.createElement('div');
    live.className = 'rank-a11y-live';
    live.setAttribute('aria-live', 'polite');
    live.setAttribute('aria-atomic', 'true');
    // Visually hidden but NOT display:none — hidden elements are not announced.
    live.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;' +
                         'clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;';
    list.parentNode.insertBefore(live, list.nextSibling);

    function items() {
      return Array.prototype.slice.call(list.querySelectorAll(itemSelector));
    }

    function announce(el, index, total) {
      live.textContent = movedTpl
        .replace('{name}', labelOf(el, index))
        .replace('{pos}', index + 1)
        .replace('{total}', total);
    }

    function refreshDisabled() {
      var all = items();
      all.forEach(function (el, i) {
        var up = el.querySelector('.rank-a11y-btn--up');
        var down = el.querySelector('.rank-a11y-btn--down');
        if (up) up.disabled = (i === 0);
        if (down) down.disabled = (i === all.length - 1);
      });
    }

    function move(el, delta, buttonClass) {
      var all = items();
      var i = all.indexOf(el);
      var j = i + delta;
      if (i < 0 || j < 0 || j >= all.length) return;

      if (delta < 0) {
        list.insertBefore(el, all[j]);
      } else {
        // Insert AFTER the following sibling. nextSibling may be null on the
        // last row, and insertBefore(node, null) appends — which is correct.
        list.insertBefore(el, all[j].nextSibling);
      }

      onChange();
      refreshDisabled();

      var after = items();
      var pos = after.indexOf(el);
      announce(el, pos, after.length);

      // Keep focus on the button the user pressed. If it just became disabled
      // (the row reached an end), move focus to the opposite button so focus is
      // never lost to the document body — a 2.4.3 focus-order failure.
      var btn = el.querySelector('.' + buttonClass);
      if (btn && !btn.disabled) {
        btn.focus();
      } else {
        var alt = el.querySelector(
          buttonClass === 'rank-a11y-btn--up' ? '.rank-a11y-btn--down' : '.rank-a11y-btn--up'
        );
        if (alt) alt.focus();
      }
    }

    /* The accessible name of a move button, e.g. "Move up: Steel wool".
     *
     * The comment here used to promise the name identified the ROW, while the
     * line below set only "Move up" / "Move down" — so a screen-reader user
     * tabbing a sixteen-item list met thirty-two controls with two names
     * between them, and could not tell which row a button belonged to.
     * (External review, 7 August 2026.)
     *
     * Word order is the translator's, not ours: if the localised string
     * contains {name} it is substituted in place, which is what German and
     * RTL locales need. Only when it does not do we append.
     */
    function buttonLabel(isUp, el, index) {
      var base = isUp ? upLabel : downLabel;
      var name = labelOf(el, index);
      if (!name) return base;
      return base.indexOf('{name}') !== -1
        ? base.replace('{name}', name)
        : base + ': ' + name;
    }

    function makeButton(dir, el) {
      var btn = document.createElement('button');
      btn.type = 'button';   // never submit the surrounding form
      var isUp = dir === 'up';
      btn.className = 'rank-a11y-btn rank-a11y-btn--' + dir;
      btn.innerHTML = '<span aria-hidden="true">' + (isUp ? '▲' : '▼') + '</span>';
      // The visible glyph is decorative; the real name comes from aria-label so
      // it names the ROW being moved, not just the direction.
      btn.setAttribute('aria-label', buttonLabel(isUp, el, items().indexOf(el)));
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        move(el, isUp ? -1 : 1, 'rank-a11y-btn--' + dir);
      });
      // Sortable listens for pointerdown on the row; stop it here so pressing a
      // button never starts a drag.
      ['pointerdown', 'mousedown', 'touchstart'].forEach(function (evt) {
        btn.addEventListener(evt, function (e) { e.stopPropagation(); });
      });
      return btn;
    }

    items().forEach(function (el) {
      if (el.querySelector('.rank-a11y-controls')) return;
      var group = document.createElement('span');
      group.className = 'rank-a11y-controls';
      group.appendChild(makeButton('up', el));
      group.appendChild(makeButton('down', el));
      el.appendChild(group);
    });

    refreshDisabled();
    return { refresh: refreshDisabled };
  }

  global.PhrononRankA11y = { enhance: enhance };
})(window);
