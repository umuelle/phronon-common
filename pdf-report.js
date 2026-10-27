/**
 * pdf-report.js — the fleet's PDF report builder, on jsPDF (window.jspdf).
 *
 * MASTER COPY: phronon_common/pdf-report.js. Do not edit a tool's copy —
 * `server-ops/sync_shared_assets.py` overwrites it and reports the drift.
 *
 * One builder for the three tools that make a PDF in the browser (TO DO
 * FL-098, 26 October 2026): Layoff's results report, Whiteout's session
 * report and Polarity Profiler's personal profile. Each had grown its own
 * page cursor, its own "does this fit?", its own SVG-to-picture routine and
 * its own idea of which characters jsPDF can print. What each report LOOKS
 * like stays the tool's own: its cover, its headings, its colours. This file
 * is the machinery underneath, so a fix lands in all three at once.
 *
 *   PhrononPdf.ready()                 is jsPDF loaded?
 *   PhrononPdf.safe(text)              text jsPDF's built-in fonts can print
 *   PhrononPdf.svgCanvas(svg, scale)   an inline SVG chart as a canvas, drawn by
 *                                      the chart engine (svg-charts.js)
 *   PhrononPdf.revealPanels(selector)  show hidden tab panels; returns restore()
 *   PhrononPdf.report(options)         a report: the page cursor and its writers
 *
 * A report (all lengths in mm):
 *   r.doc            the jsPDF document, for a tool's own drawing (covers)
 *   r.W, r.H         page width and height
 *   r.margin         the left, right and top margin
 *   r.usable         r.W - 2 * r.margin
 *   r.y              the cursor; writers read and advance it
 *   r.page()         a new page, cursor at the top margin
 *   r.room(mm)       a new page unless mm still fits above the bottom limit
 *   r.text(t, x, y, o)   one text at a place, wrapped to o.maxW; returns its height
 *   r.write(t, o)        a paragraph at the cursor, flowed across pages
 *   r.image(src, o)      a canvas or data URL, fitted, at the cursor
 *   r.svg(el, o)         a chart: svgCanvas, then r.image (a Promise)
 *   r.dom(el, o)         page markup via html2canvas, then r.image (a Promise)
 *   r.table(el, o)       an HTML table as text columns
 *   r.eachPage(fn, o)    fn(doc, page, total) on pages o.from..o.to, after the build
 *   r.save(filename)
 *
 * CHARACTERS. The fonts jsPDF carries are WinAnsi: Latin-1 plus a few
 * typographic marks (dashes, curly quotes, the bullet, the ellipsis). Any
 * other character is not refused: jsPDF prints a different glyph and measures
 * the string wrongly, which is how Whiteout's first report printed "−32" as
 * '" 3 2' and ran table columns into each other. `safe()` turns the ones that
 * carry meaning into ASCII (the minus sign, arrows, ▲▼, ✓, ≥, Δ …) and drops
 * what is left, so a symbol added to a page later cannot break a layout.
 * Whiteout's rules (the strictest copy), keeping what WinAnsi can print:
 * every writer here passes its text through it, and a tool's own doc.text()
 * calls must too.
 */
(function (global) {
  'use strict';

  // Named first, so meaning survives; the last rule keeps the layout.
  var CHARS = [
    [/\u2212/g, '-'],                                   // minus sign
    // An arrow that already has a sign behind it is decoration ("down 54.5"
    // drawn as "- -54.5"); where the number has no sign of its own, the
    // arrow is the only direction there is and keeps its + or -.
    [/[\u25b2\u25bc]\s*(?=[+\-\u2212])/g, ''],
    [/\u25b2\s*/g, '+ '],                               // up triangle
    [/\u25bc\s*/g, '- '],                               // down triangle
    [/\u2194/g, '<->'], [/\u2190/g, '<-'], [/\u2192/g, '->'],
    [/\u2265/g, '>='], [/\u2264/g, '<='], [/\u2260/g, '!='],
    [/[\u2713\u25cf]/g, '\u2022'],                      // tick, black circle: the bullet
    [/\u25cb/g, 'o'],                                   // white circle
    [/\u26a0\s*/g, '! '],                               // warning sign
    [/\u0394/g, 'Delta'],
    [/\u2500/g, '-'],                                   // box-drawing line
    [/\u00a0/g, ' '],                                   // no-break space
    // Whatever is still outside Latin-1 and the WinAnsi extras goes.
    [/[^\x00-\xff\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178]/g, ''],
  ];

  function safe(t) {
    t = String(t == null ? '' : t);
    CHARS.forEach(function (r) { t = t.replace(r[0], r[1]); });
    return t;
  }

  function ready() {
    return !!(global.jspdf && global.jspdf.jsPDF);
  }

  /* An inline SVG chart as a canvas at `scale` (default 2: a 1x raster looks
   * soft on paper). The picture is the chart engine's own
   * (PhrononCharts.chartPng in svg-charts.js), so a chart prints exactly as it
   * saves: on white, sized from its viewBox (a chart in a hidden tab works), in
   * the font the page showed it in, read through a data URL, which a page whose
   * CSP allows img-src data: but not blob: still loads. A page that prints
   * charts loads svg-charts.js; it is looked up at call time, so a report
   * without charts does not need it. Resolves {canvas, width, height}, the
   * width and height in the SVG's own units. */
  function svgCanvas(svg, scale) {
    var C = global.PhrononCharts;
    if (!C || !C.chartPng) {
      return Promise.reject(new Error('the chart engine (svg-charts.js) is not loaded'));
    }
    scale = scale || 2;
    return C.chartPng(svg, { scale: scale, background: '#ffffff' })
      .then(C.blobDataUrl)
      .then(function (url) {
        return new Promise(function (resolve, reject) {
          var img = new Image();
          img.onload = function () {
            var canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            canvas.getContext('2d').drawImage(img, 0, 0);
            resolve({ canvas: canvas, width: canvas.width / scale, height: canvas.height / scale });
          };
          img.onerror = function () { reject(new Error('could not rasterise a chart')); };
          img.src = url;
        });
      });
  }

  /* A report covers every tab, whichever one is open, and nothing can be
   * captured while it is display:none (html2canvas returns a 0x0 canvas,
   * which jsPDF rejects as a corrupt PNG). Shows every matching panel that is
   * hidden, undoing only how it was hidden: the hidden attribute is removed
   * (so the panel takes its stylesheet's display, a grid stays a grid), and a
   * panel still not displayed gets display:block. Returns the function that
   * puts them back. */
  function revealPanels(selector) {
    var undo = [];
    Array.prototype.forEach.call(document.querySelectorAll(selector), function (p) {
      undo.push([p, p.hidden, p.style.display, p.style.visibility]);
      if (p.hidden) p.hidden = false;
      var cs = getComputedStyle(p);
      if (cs.display === 'none') p.style.display = 'block';
      if (cs.visibility === 'hidden') p.style.visibility = 'visible';
    });
    return function restore() {
      undo.forEach(function (u) {
        u[0].hidden = u[1];
        u[0].style.display = u[2];
        u[0].style.visibility = u[3];
      });
    };
  }

  function rgb(c) {
    if (c == null) return [0, 0, 0];
    return typeof c === 'number' ? [c, c, c] : c;
  }

  function fontStyle(o) {
    if (o.bold && o.italic) return 'bolditalic';
    if (o.bold) return 'bold';
    if (o.italic) return 'italic';
    return 'normal';
  }

  /* options: orientation 'portrait' | 'landscape', margin (mm), bottom (mm:
   * nothing is written below H - bottom; default the margin), compress. */
  function report(options) {
    options = options || {};
    var doc = new global.jspdf.jsPDF({
      orientation: options.orientation || 'portrait', unit: 'mm', format: 'a4',
      compress: !!options.compress,
    });
    var r = {
      doc: doc,
      // jsPDF works in points and reports A4 as 210.0016 x 297.0001 mm.
      W: Math.round(doc.internal.pageSize.getWidth() * 100) / 100,
      H: Math.round(doc.internal.pageSize.getHeight() * 100) / 100,
      margin: options.margin == null ? 14 : options.margin,
    };
    r.bottom = options.bottom == null ? r.margin : options.bottom;
    r.usable = r.W - 2 * r.margin;
    r.y = r.margin;

    r.page = function () {
      doc.addPage();
      r.y = r.margin;
      return r;
    };

    r.room = function (mm) {
      if (r.y + mm <= r.H - r.bottom) return false;
      r.page();
      return true;
    };

    // Font, size and colour for the next text: o.size (pt), o.bold, o.italic,
    // o.font ('helvetica' by default), o.color (a grey 0-255 or [r, g, b]).
    r.font = function (o) {
      o = o || {};
      if (o.size) doc.setFontSize(o.size);
      doc.setFont(o.font || 'helvetica', fontStyle(o));
      var c = rgb(o.color);
      doc.setTextColor(c[0], c[1], c[2]);
      return r;
    };

    /* One text at (x, y), not moving the cursor. o: the font options above,
     * o.maxW wraps it, o.align, o.underline, o.lineFactor (the height per line
     * as a share of the size; 0.42 by default). Returns its height in mm. */
    r.text = function (t, x, y, o) {
      o = o || {};
      r.font(o);
      var size = o.size || doc.getFontSize();
      var factor = o.lineFactor || 0.42;
      var s = safe(t);
      if (o.maxW) {
        var lines = doc.splitTextToSize(s, o.maxW);
        doc.text(lines, x, y, { align: o.align || 'left' });
        return lines.length * size * factor;
      }
      doc.text(s, x, y, { align: o.align || 'left', charSpace: o.charSpace });
      if (o.underline) {
        var tw = doc.getTextWidth(s);
        var ux = o.align === 'right' ? x - tw : x;
        var c = rgb(o.color);
        doc.setDrawColor(c[0], c[1], c[2]);
        doc.setLineWidth(0.25);
        doc.line(ux, y + 0.8, ux + tw, y + 0.8);
      }
      return size * factor;
    };

    /* A paragraph at the cursor, line by line, starting a page wherever the
     * next line does not fit. o: the font options, o.x (the margin), o.width
     * (r.usable), o.lineH (mm per line; size * 0.42), o.room (mm a line needs;
     * lineH), o.after (mm below the paragraph; 0). Returns the lines written. */
    r.write = function (t, o) {
      o = o || {};
      r.font(o);
      var x = o.x == null ? r.margin : o.x;
      var lineH = o.lineH || (o.size || doc.getFontSize()) * 0.42;
      var lines = doc.splitTextToSize(safe(t), o.width || r.usable);
      lines.forEach(function (line) {
        if (r.room(o.room || lineH)) r.font(o);
        doc.text(line, x, r.y);
        r.y += lineH;
      });
      r.y += o.after || 0;
      return lines.length;
    };

    /* A picture at the cursor. src: {canvas, width, height} (width and height
     * only give the proportions) or {dataUrl, width, height}. o.w (r.usable)
     * is the width to fit, o.maxH (the page height inside the margins) caps the
     * height and narrows the picture to match; o.x (centred in the usable
     * width by default, o.left for the margin), o.format ('PNG'),
     * o.quality (for 'JPEG', 0.9), o.after (mm below, 0). A picture without
     * pixels is skipped rather than handed to jsPDF, which would reject the
     * whole document. Returns false when skipped. */
    r.image = function (src, o) {
      o = o || {};
      if (!src) return false;
      var canvas = src.canvas;
      if (canvas && (!canvas.width || !canvas.height)) return false;
      var pw = src.width || (canvas && canvas.width);
      var ph = src.height || (canvas && canvas.height);
      if (!pw || !ph) return false;
      var format = o.format || 'PNG';
      var data = src.dataUrl || canvas.toDataURL(
        format === 'JPEG' ? 'image/jpeg' : 'image/png', o.quality || 0.9);
      var w = o.w || r.usable;
      var h = w * (ph / pw);
      var maxH = o.maxH || (r.H - 2 * r.margin);
      if (h > maxH) { w = w * (maxH / h); h = maxH; }
      if (o.room !== false) r.room(h + (o.roomExtra || 0));
      var x = o.x != null ? o.x : (o.left ? r.margin : r.margin + (r.usable - w) / 2);
      // 'FAST' = Flate-compress the bitmap: a mostly white chart embedded raw
      // is megabytes for one page, and nothing visible is lost.
      doc.addImage(data, format, x, r.y, w, h, undefined, 'FAST');
      r.y += h + (o.after || 0);
      return true;
    };

    // A chart. Resolves false when it would not rasterise: one broken chart
    // must not cost the whole report.
    r.svg = function (el, o) {
      o = o || {};
      return svgCanvas(el, o.scale).then(function (c) { return r.image(c, o); },
                                         function () { return false; });
    };

    // Page markup that is not an SVG (a histogram of divs, a legend).
    r.dom = function (el, o) {
      o = o || {};
      if (typeof global.html2canvas !== 'function') return Promise.resolve(false);
      var scale = o.scale || 2;
      return global.html2canvas(el, { backgroundColor: '#ffffff', scale: scale,
                                      useCORS: true, logging: false, onclone: o.onclone })
        .then(function (canvas) {
          return r.image({ canvas: canvas, width: canvas.width / scale,
                           height: canvas.height / scale }, o);
        }, function () { return false; });
    };

    /* An HTML table as text: the header row in bold, a rule under it, cells
     * wrapped to two lines (a cut at one line can turn a phrase into a
     * different claim). A table without a <thead> takes its column count from
     * its widest row. o.size (8; 6.6 past six columns), o.lineH (3.4),
     * o.after (3). Returns false for a table with no rows. */
    r.table = function (node, o) {
      o = o || {};
      var text = function (el) { return (el.textContent || '').replace(/\s+/g, ' ').trim(); };
      var heads = [];
      node.querySelectorAll('thead th').forEach(function (th) { heads.push(text(th)); });
      var rows = [];
      node.querySelectorAll('tbody tr').forEach(function (tr) {
        rows.push(Array.prototype.map.call(tr.cells, text));
      });
      if (!rows.length) return false;
      var nCols = heads.length || Math.max.apply(null, rows.map(function (x) { return x.length; }));
      if (!nCols) return false;
      var colW = r.usable / nCols;
      var size = o.size || (nCols > 6 ? 6.6 : 8);
      var lineH = o.lineH || 3.4;
      r.room(14);
      function cellLines(t) {
        var lines = doc.splitTextToSize(safe(t), colW - 2);
        if (lines.length > 2) {
          lines = lines.slice(0, 2);
          lines[1] = lines[1].replace(/.{2}$/, '..');
        }
        return lines;
      }
      function writeRow(cells, lead, bold) {
        r.font({ size: size, bold: bold, color: 20 });
        var wrapped = cells.map(cellLines);
        var tall = Math.max.apply(null, wrapped.map(function (w) { return w.length; }));
        if (r.room(lead + tall * lineH)) r.font({ size: size, bold: bold, color: 20 });
        wrapped.forEach(function (w, i) {
          w.forEach(function (line, n) {
            doc.text(line, r.margin + i * colW, r.y + n * lineH);
          });
        });
        r.y += tall * lineH + 1.2;
      }
      if (heads.length) {
        writeRow(heads, 6, true);
        doc.setDrawColor(200);
        doc.line(r.margin, r.y - 2.5, r.margin + r.usable, r.y - 2.5);
      }
      rows.forEach(function (cells) { writeRow(cells, 4, false); });
      r.y += o.after == null ? 3 : o.after;
      return true;
    };

    /* After the build: fn(doc, page, total) on each page from o.from (1) to
     * o.to (the last), for page numbers and footers. */
    r.eachPage = function (fn, o) {
      o = o || {};
      var total = doc.getNumberOfPages();
      var last = o.to == null ? total : (o.to < 0 ? total + o.to : o.to);
      for (var p = o.from || 1; p <= last; p++) {
        doc.setPage(p);
        fn(doc, p, total);
      }
      return r;
    };

    r.save = function (filename) {
      doc.save(filename);
      return r;
    };

    return r;
  }

  global.PhrononPdf = {
    ready: ready, safe: safe, svgCanvas: svgCanvas,
    revealPanels: revealPanels, report: report,
  };
})(window);
