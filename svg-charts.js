'use strict';
/* Phronon fleet chart engine — hand-drawn SVG, no chart library.
 * MASTER copy: phronon_common/svg-charts.js, synced to each tool's
 * static/js/svg-charts.js by server-ops/sync_shared_assets.py. Edit the
 * master, run --write, redeploy the tools. CSP: script-src 'self'.
 *
 * Extracted from Whiteout's session-charts.js on 25 August 2026 (FL-027):
 * the row renderer that survived the first real class, made fleet-wide. The
 * method that produces the look is written down in
 * server-ops/CHART-STANDARD.md — the four rules in short:
 *
 *   1. Pick the form from the question, never from the library's menu.
 *   2. Validate the palette (server-ops/chart_palette_check.py gates it);
 *      never carry meaning by colour alone — direction, shape and text say
 *      it again.
 *   3. Put the numbers on the marks AND in a table.
 *   4. Anchor axes at the meaningful end (scores: 0 on the RIGHT, real
 *      minus signs, both ends named) and never zoom an axis to the data to
 *      make noise look like a finding.
 *
 * Colours come from the --chart-* tokens in design-tokens.css when the page
 * carries them, with the validated values as fallbacks, so a tool without
 * the token sheet (Layoff) still draws correctly.
 *
 * API (window.PhrononCharts):
 *   palette()                the resolved colour set {ink, muted, range,
 *                            grid, better, worse, surface}
 *   has(v), fmt(v), tag(name, attrs, text)
 *   drawRows(host, rows, opts)   the row renderer, documented below
 */
(function () {
  var NS = 'http://www.w3.org/2000/svg';

  var FALLBACK = {
    ink:     '#171717',
    muted:   '#666666',
    range:   '#d4d4d4',
    grid:    '#ececec',
    better:  '#2a78d6',   // the validated diverging pair: ΔE 26.1 under
    worse:   '#c0392b',   // deuteranopia, where green/red measures 8.6
    surface: '#ffffff',
  };

  var _palette = null;
  function palette() {
    if (_palette) return _palette;
    var out = {}, cs = null;
    try { cs = getComputedStyle(document.documentElement); } catch (e) { /* no DOM */ }
    for (var k in FALLBACK) {
      var v = cs ? cs.getPropertyValue('--chart-' + k).trim() : '';
      out[k] = v || FALLBACK[k];
    }
    _palette = out;
    return out;
  }

  function has(v) { return v !== null && v !== undefined; }

  // A real minus sign, not a hyphen: the axis ticks use one, and a row of
  // numbers where the label and the tick disagree looks like a bug.
  function fmt(v) { return String(v).replace('-', '−'); }

  function tag(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) {
      if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
    }
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /* Nudge the sub-row numbers apart when a spread is tight enough that they
   * would sit on top of each other. Dropping one would be worse: the reader
   * cannot tell a hidden number from an absent one. Glyph width at font-size
   * 11 is about 6.2 units, and these are tabular figures so the estimate
   * holds. */
  function declutter(subs, lo, hi) {
    var GAP = 5;
    function span(sp) {
      var w = sp.text.length * 6.2;
      if (sp.anchor === 'end')    return [sp.at - w, sp.at];
      if (sp.anchor === 'middle') return [sp.at - w / 2, sp.at + w / 2];
      return [sp.at, sp.at + w];
    }
    for (var i = 1; i < subs.length; i++) {
      var prev = span(subs[i - 1]), cur = span(subs[i]);
      if (cur[0] < prev[1] + GAP) {
        var shift = prev[1] + GAP - cur[0];
        subs[i].at += shift;
      }
    }
    var last = subs[subs.length - 1];
    if (last) {
      var s = span(last);
      if (s[1] > hi) last.at -= s[1] - hi;
    }
    var first = subs[0];
    if (first) {
      var f = span(first);
      if (f[0] < lo) first.at += lo - f[0];
    }
  }

  /* ── The row renderer ───────────────────────────────────────────────────
   * One horizontal row per unit of comparison (a group, a segment, a round),
   * on a shared score axis anchored at 0 on the RIGHT. Scores are negative
   * penalty points: 0 is a perfect match and a mark further right is better.
   *
   * `rows` are plain objects; every field is optional except `label`:
   *   label, sub        the two lines in the left-hand column
   *   best, worst       the ends of the grey spread track
   *   avg               hollow circle — the starting point compared FROM
   *   grp               filled diamond — the result, compared TO
   *   crowd             grey triangle — a computed (not chosen) answer
   *   mid               filled grey dot — an intermediate stage
   *   section           true = this row opens a new section (rule above it)
   *   fallback          right-column text when there is no comparison yet
   *   title             hover title for the whole row
   *
   * `opts`:
   *   rowH, labelW, labelSize, labelMax, sectionGap, rightW
   *   aria              REQUIRED: the chart described in a sentence
   *   band              {best, worst} pale reference field behind every row
   *   crowdIsRef        judge the result against `crowd`, not `avg`
   *   crowdIsResult     no diamond: the crowd itself is the judged result
   *   legs              decompose the total under each row (dots: avg→crowd,
   *                     dashes: crowd→result)
   *   verdictLabel      name the judged move ("Discussion", "Aggregation")
   *   dividerAfter      row index to draw a dotted divider after
   *   axisLeft/axisRight  the two axis end labels (defaults below)
   *   bandLabel         function(best, worst) -> the band's caption
   *   words             {closer, further, matched} for the plain verdict
   */
  function drawRows(host, rows, opts) {
    if (!host || !rows.length) return;
    var C = palette();
    var ROW = opts.rowH || 64, PAD_T = 30, PAD_B = 52;
    var SECTION_GAP = opts.sectionGap || 26;
    var LABEL_W = opts.labelW || 140, PAD_R = 12;
    // The right-hand gutter holds the verdict, right-anchored at the
    // drawing's edge; charts with a named verdict carry the long form and
    // get the wider gutter without anyone remembering to ask for it.
    var RIGHT_W = opts.rightW || (opts.verdictLabel ? 200 : 120);
    var W = 900;                                  // viewBox units; scales to fit
    var plotX = LABEL_W, plotW = W - LABEL_W - RIGHT_W - PAD_R;
    var WORDS = opts.words || {};
    var CLOSER = WORDS.closer || ' closer';
    var FURTHER = WORDS.further || ' further';
    var MATCHED = WORDS.matched || 'matched';
    // Each section row pushes itself and everything below it down by the gap.
    var pushes = [], pushed = 0;
    rows.forEach(function (r) {
      if (r.section) pushed += SECTION_GAP;
      pushes.push(pushed);
    });
    var H = PAD_T + rows.length * ROW + PAD_B + pushed;

    // The axis always ends at 0 — the benchmark itself — and its far end
    // rounds up past the worst value on the page, so rows stay comparable
    // across rows and reloads. No upper clamp: a clamp would silently draw an
    // out-of-range score outside its own plot.
    var worst = 0;
    rows.forEach(function (r) {
      ['best', 'worst', 'avg', 'grp', 'crowd', 'mid'].forEach(function (k) {
        if (has(r[k])) worst = Math.max(worst, -r[k]);
      });
    });
    var band = opts.band && has(opts.band.best) && has(opts.band.worst)
      ? opts.band : null;
    if (band) worst = Math.max(worst, -band.worst);
    var maxX = Math.max(Math.ceil((worst + 4) / 20) * 20, 20);
    function x(v) { return plotX + plotW - ((-v) / maxX) * plotW; }

    var svg = tag('svg', {
      viewBox: '0 0 ' + W + ' ' + H,
      width: '100%',
      role: 'img',
      'aria-label': opts.aria,
      // min-width, not shrink-to-fit: a 900-unit viewBox squeezed into a
      // 375px phone renders the 14px labels at about 6px. The wrapper
      // scrolls instead.
      style: 'display:block; height:auto; min-width:700px; '
        + 'font-family:system-ui,-apple-system,"Segoe UI",sans-serif;',
    });

    /* The yardstick, behind everything: the population's own spread, so a
     * row difference can be read against what a difference is worth. The
     * axis stays anchored at 0 — zooming to the data would make noise look
     * like a finding. */
    if (band) {
      var bandLo = Math.min(x(band.best), x(band.worst));
      var bandHi = Math.max(x(band.best), x(band.worst));
      svg.appendChild(tag('rect', {
        x: bandLo, y: PAD_T - 10,
        width: Math.max(bandHi - bandLo, 2),
        height: H - PAD_B + 4 - (PAD_T - 10),
        fill: '#f6f6f6',
      }));
      var bandText = opts.bandLabel
        ? opts.bandLabel(band.best, band.worst)
        : 'the whole class ranked between ' + fmt(band.best)
          + ' and ' + fmt(band.worst);
      svg.appendChild(tag('text', {
        x: (x(band.best) + x(band.worst)) / 2, y: PAD_T - 16,
        fill: C.muted, 'font-size': 11, 'text-anchor': 'middle',
      }, bandText));
    }

    /* Axis: solid hairline gridlines, one step off the surface. */
    for (var t = 0; t <= maxX; t += 20) {
      svg.appendChild(tag('line', {
        x1: x(-t), x2: x(-t), y1: PAD_T - 10, y2: H - PAD_B + 4,
        stroke: C.grid, 'stroke-width': 1,
      }));
      svg.appendChild(tag('text', {
        x: x(-t), y: H - PAD_B + 20, fill: C.muted, 'font-size': 12,
        'text-anchor': 'middle', 'font-variant-numeric': 'tabular-nums',
      }, t === 0 ? '0' : '−' + t));
    }
    // Both ends of the axis are named — in a projected room nobody infers.
    svg.appendChild(tag('text', {
      x: plotX, y: H - PAD_B + 40, fill: C.muted, 'font-size': 12,
      'text-anchor': 'start',
    }, opts.axisLeft || '← further from the benchmark'));
    svg.appendChild(tag('text', {
      x: plotX + plotW, y: H - PAD_B + 40, fill: C.muted, 'font-size': 12,
      'text-anchor': 'end',
    }, opts.axisRight || '0 is a perfect match →'));

    /* One row per unit. */
    rows.forEach(function (r, i) {
      var y = PAD_T + i * ROW + ROW / 2 - 6 + pushes[i];
      var best = r.best, avg = r.avg, wst = r.worst, grp = r.grp;
      // Where the coloured move STARTS: mid if present, else the crowd when
      // the chart judges the discussion, else the average.
      var ref = has(r.mid) ? r.mid
              : (opts.crowdIsRef && has(r.crowd) ? r.crowd : avg);
      // Where it ENDS: the result, or the crowd itself on a crowd chart.
      var crowdIsResult = !!opts.crowdIsResult && !has(grp) && has(r.crowd);
      var endV = crowdIsResult ? r.crowd : grp;
      var comparable = has(ref) && has(endV);
      // A tie is neither: 0.0, in the muted colour, not a red loss.
      var delta = comparable ? Math.round((endV - ref) * 10) / 10 : null;
      var better = comparable && delta > 0;
      var deltaColor = !comparable || delta === 0 ? C.muted
                     : (better ? C.better : C.worse);

      var row = tag('g', {});

      /* A rule ABOVE a row that opens a section — edge to edge: it divides
       * the CHART, not the plotting area. */
      if (r.section) {
        row.appendChild(tag('line', {
          x1: 0, x2: W, y1: y - ROW / 2 - SECTION_GAP / 2 + 2,
          y2: y - ROW / 2 - SECTION_GAP / 2 + 2,
          stroke: C.muted, 'stroke-width': 2.5,
        }));
      }

      // The left-hand column: what this row stands for, and how many people.
      var shown = r.label;
      if (opts.labelMax && shown.length > opts.labelMax) {
        shown = shown.slice(0, opts.labelMax - 1) + '…';
      }
      var name = tag('text', {
        x: LABEL_W - 16, y: r.sub ? y + 3 : y + 8, fill: C.ink,
        'font-size': opts.labelSize || 14, 'font-weight': 600, 'text-anchor': 'end',
      }, shown);
      if (shown !== r.label) name.appendChild(tag('title', {}, r.label));
      row.appendChild(name);
      if (r.sub) {
        row.appendChild(tag('text', {
          x: LABEL_W - 16, y: y + 19, fill: C.muted, 'font-size': 11,
          'text-anchor': 'end',
        }, r.sub));
      }

      // The spread of individual scores: best → worst, a thin rounded track.
      if (has(best) && has(wst)) {
        var lo = Math.min(x(best), x(wst)), hi = Math.max(x(best), x(wst));
        row.appendChild(tag('rect', {
          x: lo, y: y - 4, width: Math.max(hi - lo, 3), height: 8,
          rx: 4, fill: C.range,
        }));
      }

      // The move from the reference point to the result. Direction is the
      // primary channel — rightward is nearer zero, so rightward is better —
      // and the colour agrees.
      if (comparable && Math.abs(x(endV) - x(ref)) > 1) {
        row.appendChild(tag('line', {
          x1: x(ref), x2: x(endV), y1: y, y2: y,
          stroke: deltaColor, 'stroke-width': 3, 'stroke-linecap': 'round',
        }));
      }
      // The earlier leg — where the people started, to the reference point —
      // stays muted: context for the coloured move, not the move itself.
      // NOT when the crowd is the reference: both marks are already on the
      // row, and a grey line between them means a second thing in the spread
      // track's colour.
      if (!opts.crowdIsRef
          && has(ref) && has(avg) && ref !== avg && Math.abs(x(ref) - x(avg)) > 1) {
        row.appendChild(tag('line', {
          x1: x(avg), x2: x(ref), y1: y, y2: y,
          stroke: C.range, 'stroke-width': 3, 'stroke-linecap': 'round',
        }));
      }

      // Where these people started — hollow, so it reads as context.
      if (has(avg)) {
        row.appendChild(tag('circle', {
          cx: x(avg), cy: y, r: 6, fill: C.surface, stroke: C.muted, 'stroke-width': 2,
        }));
      }

      // A computed answer — the members' positions averaged into one ranking
      // and scored. A grey TRIANGLE: filled like a result (it is an answer),
      // muted like context (nobody chose it). Drawn before the diamond so
      // the chosen answer stays on top where they land together.
      if (has(r.crowd)) {
        var chh = crowdIsResult ? 11 : 8, cw = crowdIsResult ? 10 : 7;
        row.appendChild(tag('path', {
          d: 'M ' + x(r.crowd) + ' ' + (y - chh)
           + ' L ' + (x(r.crowd) + cw) + ' ' + (y + chh * 0.62)
           + ' L ' + (x(r.crowd) - cw) + ' ' + (y + chh * 0.62) + ' Z',
          fill: crowdIsResult ? deltaColor : C.muted,
          stroke: C.surface, 'stroke-width': 2,
        }));
        if (crowdIsResult) {
          row.appendChild(tag('text', {
            x: x(r.crowd) + (better ? 15 : -15), y: y - 15,
            fill: C.ink, 'font-size': 13, 'font-weight': 700,
            'text-anchor': better ? 'start' : 'end',
            'font-variant-numeric': 'tabular-nums',
          }, fmt(r.crowd)));
        }
      }

      // The intermediate stage: a filled grey dot between the hollow start
      // and the diamond result. When the result lands within a diamond's
      // width, the dot steps up a row-height's tenth — the x position, the
      // only axis that carries meaning, is untouched.
      if (has(r.mid)) {
        var midY = (has(grp) && Math.abs(x(r.mid) - x(grp)) < 14) ? y - 11 : y;
        if (midY !== y) {
          row.appendChild(tag('line', {
            x1: x(r.mid), x2: x(r.mid), y1: midY + 5, y2: y - 5,
            stroke: C.range, 'stroke-width': 1.5,
          }));
        }
        row.appendChild(tag('circle', {
          cx: x(r.mid), cy: midY, r: 6, fill: C.muted,
          stroke: C.surface, 'stroke-width': 2,
        }));
      }

      // The result: a filled diamond with a 2px surface ring. It carries the
      // verdict's colour — ink only while there is nothing to compare.
      if (has(grp)) {
        row.appendChild(tag('rect', {
          x: x(grp) - 7, y: y - 7, width: 14, height: 14, rx: 2,
          fill: comparable ? deltaColor : C.ink,
          stroke: C.surface, 'stroke-width': 2,
          transform: 'rotate(45 ' + x(grp) + ' ' + y + ')',
        }));
        // Direct label, above the diamond and on the far side from the
        // circle, so the pair never collides.
        var toRight = has(ref) ? grp >= ref : true;
        row.appendChild(tag('text', {
          x: x(grp) + (toRight ? 13 : -13), y: y - 13,
          fill: C.ink, 'font-size': 13, 'font-weight': 700,
          'text-anchor': toRight ? 'start' : 'end',
          'font-variant-numeric': 'tabular-nums',
        }, fmt(grp)));
      }

      // The numbers the row is judged AGAINST, on their own line underneath.
      // Anchors point each label away from the track.
      var subs = [];
      if (has(wst))   subs.push({ at: x(wst) - 9,  anchor: 'end',    text: fmt(wst) });
      if (has(avg))   subs.push({ at: x(avg),      anchor: 'middle', text: fmt(avg) });
      if (has(r.mid)) subs.push({ at: x(r.mid),    anchor: 'middle', text: fmt(r.mid) });
      // Not when the crowd is the result: its value is already printed above
      // the triangle, and the same number twice on one row reads as two.
      if (has(r.crowd) && !crowdIsResult) subs.push({ at: x(r.crowd), anchor: 'middle', text: fmt(r.crowd) });
      if (has(best))  subs.push({ at: x(best) + 9, anchor: 'start',  text: fmt(best) });
      subs.sort(function (a, b) { return a.at - b.at; });
      declutter(subs, plotX, plotX + plotW + 12);
      subs.forEach(function (sp) {
        row.appendChild(tag('text', {
          x: sp.at, y: y + 18, fill: C.muted, 'font-size': 11,
          'text-anchor': sp.anchor, 'font-variant-numeric': 'tabular-nums',
        }, sp.text));
      });

      /* The two halves of the coloured move, under the row they add up to.
       * Dots are the aggregation half (start to crowd), dashes the
       * discussion half (crowd to result), each in its own direction's
       * colour: the halves regularly point in opposite directions, which is
       * the thing worth seeing and the thing a single bar hides. */
      if (opts.legs && comparable && has(r.crowd)) {
        [{ from: avg, to: r.crowd, y: y + 28, dash: '0.5 5' },
         { from: r.crowd, to: endV, y: y + 38, dash: '5 4' }].forEach(function (leg) {
          if (!has(leg.from) || !has(leg.to)) return;
          var up = leg.to > leg.from;
          var flat = Math.abs(x(leg.to) - x(leg.from)) < 1;
          var color = flat ? C.muted : (up ? C.better : C.worse);
          // The line stops short of the head, or the dashes run through it.
          var head = flat ? 0 : (up ? 7 : -7);
          row.appendChild(tag('line', {
            x1: x(leg.from), x2: x(leg.to) - head, y1: leg.y, y2: leg.y,
            stroke: color,
            'stroke-width': 3,
            'stroke-dasharray': leg.dash,
            'stroke-linecap': 'round',
          }));
          if (!flat) {
            row.appendChild(tag('path', {
              d: 'M ' + x(leg.to) + ' ' + leg.y
               + ' L ' + (x(leg.to) - head) + ' ' + (leg.y - 4)
               + ' L ' + (x(leg.to) - head) + ' ' + (leg.y + 4) + ' Z',
              fill: color,
            }));
          }
        });
      }

      // The right-hand column says where this row stands. While there is
      // nothing to compare it says so rather than going blank — an empty
      // row would read as a missing feature instead of as pending work.
      var verdict = r.fallback || null, verdictColor = C.muted;
      if (comparable) {
        // AGAINST `ref`, not against the average: the arrow, the colour and
        // the number must describe the SAME move.
        var d = Math.abs(delta);
        if (opts.verdictLabel) {
          verdict = opts.verdictLabel + ' '
                  + (delta === 0 ? '0.0' : (better ? '▲ +' : '▼ −') + d);
        } else {
          verdict = delta === 0 ? MATCHED
                  : (better ? '▲ ' : '▼ ') + d + (better ? CLOSER : FURTHER);
        }
        verdictColor = deltaColor;
      }
      if (verdict) {
        // Right-anchored at the drawing's edge: the verdicts line up as a
        // flush right column; the gutter width keeps them out of the plot.
        row.appendChild(tag('text', {
          x: W - PAD_R, y: y + 3, fill: verdictColor, 'font-size': 12.5,
          'font-weight': comparable ? 600 : 400, 'text-anchor': 'end',
        }, verdict));
      }

      if (r.title) row.appendChild(tag('title', {}, r.title));
      svg.appendChild(row);

      // A dotted divider under this row (e.g. stayed above, went below).
      if (opts.dividerAfter === i && i < rows.length - 1) {
        var dy = PAD_T + (i + 1) * ROW - 6;
        svg.appendChild(tag('line', {
          x1: 16, x2: W - PAD_R, y1: dy, y2: dy,
          stroke: C.muted, 'stroke-width': 1.5, 'stroke-dasharray': '3 5',
        }));
      }
    });

    host.appendChild(svg);
  }

  window.PhrononCharts = {
    palette: palette,
    has: has,
    fmt: fmt,
    tag: tag,
    declutter: declutter,
    drawRows: drawRows,
  };
})();
