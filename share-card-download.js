/* Download the join/share card as a JPG.
 *
 * Master copy — phronon_common/share-card-download.js. Do not edit a tool's copy;
 * edit this and run server-ops/sync_shared_assets.py --write.
 *
 * Usage in a template (needs html2canvas loaded first):
 *
 *   <button type="button" class="share-btn btn btn-secondary btn-sm"
 *           data-share-download>Download JPG</button>
 *   <script src="/static/vendor/html2canvas-1.4.1.min.js" defer></script>
 *   <script src="/static/js/share-card-download.js" defer></script>
 *
 * The file is named after the join code, so an educator who downloads several
 * cards gets ABC123.jpg / XYZ789.jpg rather than three copies of "card.jpg".
 * Resolution order: data-share-code on the button, then .share-class-code text,
 * then "join-card".
 *
 * The script wires itself up on DOMContentLoaded rather than going through each
 * tool's click dispatcher — the tools do not share one, and an inline handler
 * would break the CSP (script-src 'self' + nonce, no unsafe-inline).
 *
 * Why the SVG pre-pass: most tools render the QR code as inline <svg>, and the
 * rest use <img src="….svg">. html2canvas rasterises neither reliably — the QR
 * comes out blank, which is the one part of the card that has to survive. So
 * every SVG is rendered to a PNG first, swapped in for the capture, and put back
 * afterwards. JPEG has no alpha either, hence the explicit white background.
 */
(function () {
  'use strict';

  var SCALE = 2;           // 2× for a crisp image in Word / e-mail
  var JPEG_QUALITY = 0.95;

  function codeFor(button, card) {
    var explicit = button.getAttribute('data-share-code');
    if (explicit && explicit.trim()) return explicit.trim();
    var el = card.querySelector('.share-class-code');
    var text = el ? el.textContent : '';
    return (text && text.trim()) ? text.trim() : 'join-card';
  }

  /* Safe on every OS: letters, digits, dash, underscore; collapse the rest. */
  function toFilename(code) {
    var cleaned = code.replace(/\s+/g, '').replace(/[^A-Za-z0-9_-]/g, '-');
    cleaned = cleaned.replace(/-{2,}/g, '-').replace(/^-|-$/g, '');
    return (cleaned || 'join-card') + '.jpg';
  }

  /* Rasterise one <svg> element to a PNG data URI at its on-screen size. */
  function svgToPng(svg) {
    return new Promise(function (resolve, reject) {
      var rect = svg.getBoundingClientRect();
      var w = Math.max(1, Math.round(rect.width || svg.clientWidth || 200));
      var h = Math.max(1, Math.round(rect.height || svg.clientHeight || 200));

      var clone = svg.cloneNode(true);
      clone.setAttribute('width', w);
      clone.setAttribute('height', h);
      if (!clone.getAttribute('xmlns')) {
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      }

      var xml = new XMLSerializer().serializeToString(clone);
      var img = new Image();
      img.onload = function () {
        var canvas = document.createElement('canvas');
        canvas.width = w * SCALE;
        canvas.height = h * SCALE;
        var ctx = canvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve({ dataUrl: canvas.toDataURL('image/png'), width: w, height: h });
      };
      img.onerror = function () { reject(new Error('SVG rasterisation failed')); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
    });
  }

  /* Swap every SVG in the card for an equivalent PNG <img>.
   * Returns a function that puts the originals back. */
  function replaceSvgs(card) {
    var undo = [];

    var inline = Array.prototype.slice.call(card.querySelectorAll('svg'));
    var imgs = Array.prototype.slice.call(card.querySelectorAll('img'))
      .filter(function (img) { return /\.svg(\?|#|$)/i.test(img.getAttribute('src') || ''); });

    var work = inline.map(function (svg) {
      return svgToPng(svg).then(function (png) {
        var img = new Image();
        img.src = png.dataUrl;
        img.width = png.width;
        img.height = png.height;
        var parent = svg.parentNode;
        parent.replaceChild(img, svg);
        undo.push(function () { parent.replaceChild(svg, img); });
      });
    }).concat(imgs.map(function (img) {
      /* Same-origin SVG file: fetch it, inline it, rasterise it. */
      return fetch(img.src)
        .then(function (r) { return r.text(); })
        .then(function (text) {
          var holder = document.createElement('div');
          holder.innerHTML = text;
          var svg = holder.querySelector('svg');
          if (!svg) return;
          var rect = img.getBoundingClientRect();
          svg.setAttribute('width', Math.max(1, Math.round(rect.width || 200)));
          svg.setAttribute('height', Math.max(1, Math.round(rect.height || 200)));
          holder.style.cssText = 'position:absolute;left:-99999px;top:0';
          document.body.appendChild(holder);
          return svgToPng(svg).then(function (png) {
            document.body.removeChild(holder);
            var original = img.getAttribute('src');
            img.setAttribute('src', png.dataUrl);
            undo.push(function () { img.setAttribute('src', original); });
          });
        })
        .catch(function () { /* leave the <img> as-is; html2canvas may still cope */ });
    }));

    return Promise.all(work).then(function () {
      return function restore() {
        undo.forEach(function (fn) {
          try { fn(); } catch (e) { /* card is being torn down anyway */ }
        });
      };
    });
  }

  function download(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function capture(button) {
    var card = document.querySelector('.share-card');
    if (!card) return;
    if (typeof window.html2canvas !== 'function') {
      window.alert('Could not prepare the image: html2canvas did not load.');
      return;
    }

    var filename = toFilename(codeFor(button, card));
    var label = button.textContent;
    button.disabled = true;
    button.textContent = 'Preparing…';

    /* The on-screen controls are not part of the handout. .print-hide already
     * marks them for the print stylesheet; reuse it rather than invent a second
     * vocabulary. */
    var hidden = Array.prototype.slice.call(card.querySelectorAll('.print-hide'));
    hidden.forEach(function (el) { el.dataset.shareOldVis = el.style.visibility; el.style.visibility = 'hidden'; });

    var restoreSvgs = function () {};
    replaceSvgs(card)
      .then(function (restore) {
        restoreSvgs = restore;
        return window.html2canvas(card, {
          backgroundColor: '#ffffff',   // JPEG has no transparency
          scale: SCALE,
          useCORS: true,
          logging: false
        });
      })
      .then(function (canvas) {
        return new Promise(function (resolve) {
          canvas.toBlob(function (blob) { resolve(blob); }, 'image/jpeg', JPEG_QUALITY);
        });
      })
      .then(function (blob) {
        if (!blob) throw new Error('canvas.toBlob returned nothing');
        download(blob, filename);
      })
      .catch(function (err) {
        window.alert('Sorry — the image could not be generated. ' + (err && err.message ? err.message : ''));
      })
      .then(function () {
        restoreSvgs();
        hidden.forEach(function (el) {
          el.style.visibility = el.dataset.shareOldVis || '';
          delete el.dataset.shareOldVis;
        });
        button.disabled = false;
        button.textContent = label;
      });
  }

  function wire() {
    var buttons = document.querySelectorAll('[data-share-download]');
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener('click', function () { capture(button); });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
