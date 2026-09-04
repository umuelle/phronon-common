/**
 * users-password.js — show/hide toggle + random password generator.
 *
 * Markup:
 *   <div class="pw-input-wrap">
 *     <input type="password" id="initial_password" ...>
 *     <button type="button" class="pw-toggle"   data-target="initial_password">Show</button>
 *     <button type="button" class="pw-generate" data-target="initial_password">Generate</button>
 *   </div>
 *
 * Works for any number of password fields on the page (create form, reset rows, …).
 */
'use strict';

(function () {
  var ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

  function randomPassword(len) {
    var out = '';
    var rng = window.crypto || window.msCrypto;
    if (rng && rng.getRandomValues) {
      var buf = new Uint32Array(len);
      rng.getRandomValues(buf);
      for (var i = 0; i < len; i++) out += ALPHABET[buf[i] % ALPHABET.length];
    } else {
      for (var j = 0; j < len; j++) {
        out += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
      }
    }
    return out;
  }

  function reveal(input, toggleBtn, show) {
    input.type = show ? 'text' : 'password';
    if (toggleBtn) {
      toggleBtn.textContent = show ? 'Hide' : 'Show';
      toggleBtn.classList.toggle('is-on', show);
    }
  }

  function toggleFor(target) {
    return document.querySelector('.pw-toggle[data-target="' + target + '"]');
  }

  document.addEventListener('click', function (e) {
    var toggle = e.target.closest && e.target.closest('.pw-toggle');
    if (toggle) {
      var inp = document.getElementById(toggle.dataset.target);
      if (inp) reveal(inp, toggle, inp.type === 'password');
      return;
    }
    var gen = e.target.closest && e.target.closest('.pw-generate');
    if (gen) {
      var field = document.getElementById(gen.dataset.target);
      if (field) {
        field.value = randomPassword(14);
        reveal(field, toggleFor(gen.dataset.target), true); // reveal so admin can copy it
      }
    }
  });
})();
