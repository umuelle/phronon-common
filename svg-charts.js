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

  /* ── Shared scaffolding for the linear-axis forms ──────────────────────── */

  function baseSvg(W, H, aria) {
    return tag('svg', {
      viewBox: '0 0 ' + W + ' ' + H, width: '100%', role: 'img',
      'aria-label': aria,
      style: 'display:block; height:auto; min-width:700px; '
        + 'font-family:system-ui,-apple-system,"Segoe UI",sans-serif;',
    });
  }

  function niceStep(span) {
    var raw = span / 5;
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var r = raw / mag;
    return (r >= 5 ? 10 : r >= 2 ? 5 : r >= 1 ? 2 : 1) * mag;
  }

  /* ── drawDotRows: the row language on an arbitrary linear axis ──────────
   * Whiteout's drawRows is bound to the negative score scale; this is the
   * same grammar — label column, hollow start, coloured move, diamond end,
   * printed values, verdict column — for any numeric domain (ranks,
   * percentages, currency). Rows: {label, sub, a, b, only, fallback, title}
   *   a     hollow circle — the start / reference (optional)
   *   b     diamond — the result (optional)
   *   only  a single dot where there is no pair, drawn as the diamond
   * opts: min, max, step, axisLeft, axisRight, betterIs ('higher'|'lower'|
   *   null: null = no judgement, moves stay ink), unit (suffix on printed
   *   values), verdict(delta) -> text (default signs the delta), rowH,
   *   labelW, labelMax, labelSize, rightW, aria, marker {at, label} a
   *   dashed reference line across all rows.
   */
  function drawDotRows(host, rows, opts) {
    if (!host || !rows.length) return;
    var C = palette();
    var ROW = opts.rowH || 56, PAD_T = 30, PAD_B = 52;
    var LABEL_W = opts.labelW || 170, PAD_R = 12;
    var RIGHT_W = opts.rightW || 120;
    var W = 900, plotX = LABEL_W, plotW = W - LABEL_W - RIGHT_W - PAD_R;
    var H = PAD_T + rows.length * ROW + PAD_B;
    var unit = opts.unit || '';

    var lo = opts.min, hi = opts.max;
    if (!has(lo) || !has(hi)) {
      var vals = [];
      rows.forEach(function (r) {
        ['a', 'b', 'only'].forEach(function (k) { if (has(r[k])) vals.push(r[k]); });
      });
      if (opts.marker && has(opts.marker.at)) vals.push(opts.marker.at);
      if (!vals.length) return;
      var vmin = Math.min.apply(null, vals), vmax = Math.max.apply(null, vals);
      var pad = (vmax - vmin || 1) * 0.15;
      lo = has(lo) ? lo : vmin - pad;
      hi = has(hi) ? hi : vmax + pad;
    }
    var step = opts.step || niceStep(hi - lo);
    function x(v) { return plotX + ((v - lo) / (hi - lo)) * plotW; }

    var svg = baseSvg(W, H, opts.aria);

    for (var t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) {
      var tv = Math.round(t * 100) / 100;
      svg.appendChild(tag('line', {
        x1: x(tv), x2: x(tv), y1: PAD_T - 10, y2: H - PAD_B + 4,
        stroke: C.grid, 'stroke-width': 1,
      }));
      svg.appendChild(tag('text', {
        x: x(tv), y: H - PAD_B + 20, fill: C.muted, 'font-size': 12,
        'text-anchor': 'middle', 'font-variant-numeric': 'tabular-nums',
      }, fmt(tv) + (opts.tickUnit || '')));
    }
    if (opts.axisLeft) {
      svg.appendChild(tag('text', {
        x: plotX, y: H - PAD_B + 40, fill: C.muted, 'font-size': 12,
        'text-anchor': 'start',
      }, opts.axisLeft));
    }
    if (opts.axisRight) {
      svg.appendChild(tag('text', {
        x: plotX + plotW, y: H - PAD_B + 40, fill: C.muted, 'font-size': 12,
        'text-anchor': 'end',
      }, opts.axisRight));
    }
    if (opts.marker && has(opts.marker.at)) {
      svg.appendChild(tag('line', {
        x1: x(opts.marker.at), x2: x(opts.marker.at),
        y1: PAD_T - 10, y2: H - PAD_B + 4,
        stroke: C.ink, 'stroke-width': 1.5, 'stroke-dasharray': '5 4',
      }));
      if (opts.marker.label) {
        svg.appendChild(tag('text', {
          x: x(opts.marker.at), y: PAD_T - 14, fill: C.ink, 'font-size': 11,
          'font-weight': 600, 'text-anchor': 'middle',
        }, opts.marker.label));
      }
    }

    rows.forEach(function (r, i) {
      var y = PAD_T + i * ROW + ROW / 2 - 4;
      var row = tag('g', {});
      var shown = r.label;
      if (opts.labelMax && shown.length > opts.labelMax) {
        shown = shown.slice(0, opts.labelMax - 1) + '…';
      }
      var name = tag('text', {
        x: LABEL_W - 16, y: r.sub ? y + 3 : y + 8, fill: C.ink,
        'font-size': opts.labelSize || 14, 'font-weight': 600,
        'text-anchor': 'end',
      }, shown);
      if (shown !== r.label) name.appendChild(tag('title', {}, r.label));
      row.appendChild(name);
      if (r.sub) {
        row.appendChild(tag('text', {
          x: LABEL_W - 16, y: y + 19, fill: C.muted, 'font-size': 11,
          'text-anchor': 'end',
        }, r.sub));
      }

      var a = r.a, b = has(r.b) ? r.b : r.only;
      var pair = has(a) && has(r.b);
      var delta = pair ? Math.round((r.b - a) * 100) / 100 : null;
      var improved = null;
      if (pair && opts.betterIs) {
        improved = delta === 0 ? null
                 : (opts.betterIs === 'higher' ? delta > 0 : delta < 0);
      }
      var moveColor = improved === null ? (pair ? C.muted : C.ink)
                    : (improved ? C.better : C.worse);

      if (pair && Math.abs(x(r.b) - x(a)) > 1) {
        row.appendChild(tag('line', {
          x1: x(a), x2: x(r.b), y1: y, y2: y,
          stroke: moveColor, 'stroke-width': 3, 'stroke-linecap': 'round',
        }));
      }
      if (has(a)) {
        row.appendChild(tag('circle', {
          cx: x(a), cy: y, r: 6, fill: C.surface, stroke: C.muted,
          'stroke-width': 2,
        }));
        row.appendChild(tag('text', {
          x: x(a), y: y + 20, fill: C.muted, 'font-size': 11,
          'text-anchor': 'middle', 'font-variant-numeric': 'tabular-nums',
        }, fmt(a) + unit));
      }
      if (has(b)) {
        row.appendChild(tag('rect', {
          x: x(b) - 7, y: y - 7, width: 14, height: 14, rx: 2,
          fill: pair ? moveColor : C.ink,
          stroke: C.surface, 'stroke-width': 2,
          transform: 'rotate(45 ' + x(b) + ' ' + y + ')',
        }));
        var toRight = has(a) ? b >= a : true;
        row.appendChild(tag('text', {
          x: x(b) + (toRight ? 13 : -13), y: y - 13,
          fill: C.ink, 'font-size': 13, 'font-weight': 700,
          'text-anchor': toRight ? 'start' : 'end',
          'font-variant-numeric': 'tabular-nums',
        }, fmt(b) + unit));
      }

      var verdict = r.fallback || null, verdictColor = C.muted;
      if (pair) {
        if (opts.verdict) {
          verdict = opts.verdict(delta, r);
        } else {
          verdict = (delta > 0 ? '+' : '') + fmt(delta) + unit;
        }
        verdictColor = moveColor;
      }
      if (verdict) {
        row.appendChild(tag('text', {
          x: W - PAD_R, y: y + 3, fill: verdictColor, 'font-size': 12.5,
          'font-weight': pair ? 600 : 400, 'text-anchor': 'end',
        }, verdict));
      }
      if (r.title) row.appendChild(tag('title', {}, r.title));
      svg.appendChild(row);
    });
    host.appendChild(svg);
  }

  /* ── drawShares: one 100%-scaled segment bar per row ────────────────────
   * Whiteout's decisions chart, generalised. rows: {label, sub, counts,
   * total} — total is the FULL denominator, so the unanswered remainder
   * stays visible as a dashed frame and a half-answered row can never look
   * unanimous. opts: keys (segment order), fills {key}, labels {key},
   * darkText {key: true} for ink-on-light fills, legendExtra (label for the
   * empty frame; null = no frame legend), aria, rowH, labelW, labelMax.
   */
  function drawShares(host, rows, opts) {
    if (!host || !rows.length) return;
    var C = palette();
    var W = 900, ROW = opts.rowH || 52, BAR_H = 26, PAD_T = 14;
    var LEGEND_H = 40, PAD_B = 6;
    var LABEL_W = opts.labelW || 150, PAD_R = 16;
    var plotW = W - LABEL_W - PAD_R;
    var H = PAD_T + rows.length * ROW + LEGEND_H + PAD_B;
    var KEYS = opts.keys || [];
    var svg = baseSvg(W, H, opts.aria);

    rows.forEach(function (r, i) {
      var y0 = PAD_T + i * ROW + (ROW - BAR_H) / 2;
      var cyText = y0 + BAR_H / 2;
      var answered = 0;
      KEYS.forEach(function (k) { answered += (r.counts && r.counts[k]) || 0; });
      var total = Math.max(r.total || 0, answered, 1);
      var name = String(r.label || '');
      if (opts.labelMax && name.length > opts.labelMax) {
        name = name.slice(0, opts.labelMax - 1) + '…';
      }
      svg.appendChild(tag('text', {
        x: LABEL_W - 16, y: r.sub ? cyText - 2 : cyText + 4, fill: C.ink,
        'font-size': 14, 'font-weight': 600, 'text-anchor': 'end',
      }, name));
      if (r.sub) {
        svg.appendChild(tag('text', {
          x: LABEL_W - 16, y: cyText + 13, fill: C.muted,
          'font-size': 11, 'text-anchor': 'end',
          'font-variant-numeric': 'tabular-nums',
        }, r.sub));
      }
      svg.appendChild(tag('rect', {
        x: LABEL_W, y: y0, width: plotW, height: BAR_H,
        fill: 'none', stroke: C.range, 'stroke-width': 1.5,
        'stroke-dasharray': '4 3', rx: 4,
      }));
      var xCursor = LABEL_W;
      KEYS.forEach(function (k) {
        var count = (r.counts && r.counts[k]) || 0;
        if (!count) return;
        var w = (count / total) * plotW;
        var rect = tag('rect', {
          x: xCursor, y: y0, width: w, height: BAR_H,
          fill: (opts.fills && opts.fills[k]) || C.muted,
          stroke: C.surface, 'stroke-width': 2,
        });
        rect.appendChild(tag('title', {},
          r.label + ' — ' + ((opts.labels && opts.labels[k]) || k) + ': '
          + count + ' / ' + total));
        svg.appendChild(rect);
        if (w >= 18) {
          svg.appendChild(tag('text', {
            x: xCursor + w / 2, y: cyText + 4.5,
            fill: (opts.darkText && opts.darkText[k]) ? C.ink : C.surface,
            'font-size': 12.5, 'text-anchor': 'middle',
            'font-variant-numeric': 'tabular-nums',
            'pointer-events': 'none',
          }, String(count)));
        }
        xCursor += w;
      });
    });

    var items = KEYS.map(function (k) {
      return { label: (opts.labels && opts.labels[k]) || k,
               fill: (opts.fills && opts.fills[k]) || C.muted };
    });
    if (opts.legendExtra) items.push({ label: opts.legendExtra, hollow: true });
    var lx = LABEL_W, ly = H - 16;
    items.forEach(function (it) {
      svg.appendChild(tag('rect', {
        x: lx, y: ly - 10, width: 13, height: 13, rx: 3,
        fill: it.hollow ? 'none' : it.fill,
        stroke: it.hollow ? C.range : 'none',
        'stroke-width': it.hollow ? 1.5 : null,
        'stroke-dasharray': it.hollow ? '3 2' : null,
      }));
      svg.appendChild(tag('text', {
        x: lx + 19, y: ly + 1, fill: C.muted, 'font-size': 12,
      }, it.label));
      lx += 19 + it.label.length * 6.4 + 22;
    });
    host.appendChild(svg);
  }

  /* ── drawBars: vertical value bars (distributions, histograms) ──────────
   * bars: {label, value, sub} — the value is printed ON the bar (rule 3).
   * opts: yLabel, note, marker {at (bar index fraction 0..1 NOT supported —
   * use markerValue on the y scale), label}, aria, maxY, unit, barFill,
   * labelRotate (true tilts long bin labels).
   */
  function drawBars(host, bars, opts) {
    if (!host || !bars.length) return;
    var C = palette();
    var W = 900, H = opts.height || 360;
    var PAD_L = 64, PAD_R = 20, PAD_T = 26, PAD_B = opts.labelRotate ? 74 : 54;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
    var maxY = opts.maxY;
    if (!has(maxY)) {
      maxY = 0;
      bars.forEach(function (b) { maxY = Math.max(maxY, b.value); });
      maxY = maxY || 1;
    }
    var step = opts.step || Math.max(1, niceStep(maxY));
    function y(v) { return PAD_T + plotH - (v / maxY) * plotH; }
    var bw = plotW / bars.length;
    var svg = baseSvg(W, H, opts.aria);

    for (var t = 0; t <= maxY + 1e-9; t += step) {
      svg.appendChild(tag('line', {
        x1: PAD_L, x2: PAD_L + plotW, y1: y(t), y2: y(t),
        stroke: C.grid, 'stroke-width': 1,
      }));
      svg.appendChild(tag('text', {
        x: PAD_L - 8, y: y(t) + 4, fill: C.muted, 'font-size': 11.5,
        'text-anchor': 'end', 'font-variant-numeric': 'tabular-nums',
      }, fmt(Math.round(t * 100) / 100)));
    }
    if (opts.yLabel) {
      svg.appendChild(tag('text', {
        x: 16, y: PAD_T + plotH / 2, fill: C.muted, 'font-size': 12,
        'text-anchor': 'middle',
        transform: 'rotate(-90 16 ' + (PAD_T + plotH / 2) + ')',
      }, opts.yLabel));
    }

    bars.forEach(function (b, i) {
      var cx = PAD_L + i * bw + bw / 2;
      var barW = Math.min(bw * 0.64, 64);
      if (b.value > 0) {
        var rect = tag('rect', {
          x: cx - barW / 2, y: y(b.value),
          width: barW, height: PAD_T + plotH - y(b.value),
          fill: b.fill || opts.barFill || '#9aa3ad',
        });
        rect.appendChild(tag('title', {}, b.label + ': ' + fmt(b.value)
          + (opts.unit || '')));
        svg.appendChild(rect);
        svg.appendChild(tag('text', {
          x: cx, y: y(b.value) - 6, fill: C.ink, 'font-size': 12,
          'font-weight': 600, 'text-anchor': 'middle',
          'font-variant-numeric': 'tabular-nums',
        }, fmt(b.value) + (opts.unit || '')));
      }
      var lx = cx, lyy = PAD_T + plotH + 16;
      var lbl = tag('text', {
        x: lx, y: lyy, fill: C.muted, 'font-size': 11,
        'text-anchor': opts.labelRotate ? 'end' : 'middle',
        transform: opts.labelRotate
          ? 'rotate(-38 ' + lx + ' ' + lyy + ')' : null,
      }, b.label);
      svg.appendChild(lbl);
      if (b.sub) {
        svg.appendChild(tag('text', {
          x: cx, y: lyy + 14, fill: C.muted, 'font-size': 10,
          'text-anchor': 'middle',
        }, b.sub));
      }
    });
    if (has(opts.markerValue)) {
      svg.appendChild(tag('line', {
        x1: PAD_L, x2: PAD_L + plotW,
        y1: y(opts.markerValue), y2: y(opts.markerValue),
        stroke: C.ink, 'stroke-width': 1.5, 'stroke-dasharray': '5 4',
      }));
      if (opts.markerLabel) {
        svg.appendChild(tag('text', {
          x: PAD_L + plotW, y: y(opts.markerValue) - 6, fill: C.ink,
          'font-size': 11, 'font-weight': 600, 'text-anchor': 'end',
        }, opts.markerLabel));
      }
    }
    if (opts.note) {
      svg.appendChild(tag('text', {
        x: PAD_L + plotW / 2, y: H - 8, fill: C.muted, 'font-size': 12,
        'text-anchor': 'middle',
      }, opts.note));
    }
    host.appendChild(svg);
  }

  /* ── drawScatter: named points on two measured axes ─────────────────────
   * pts: {x, y, name, sub, shape ('circle'|'diamond'), tone ('better'|
   * 'worse'|'ink'|'muted'|'good'|'warn'|'range'), r (radius, default 7),
   * title}. opts: xMin/xMax/xStep, yMin/yMax/yStep, xLabel (under the axis),
   * yLabel (rotated), zeroY {label} dashed line at y=0, xMarker {at, label}
   * dashed vertical line, lines [{points: [{x,y}...], tone, dash, label}]
   * measured overlays (a Pareto frontier is a FACT about the points, not a
   * fit), xTick(v)/yTick(v) formatters, legend [{shape, tone, label}], aria,
   * height, padRight.
   * No trend lines, ever: a handful of points is not a statistic. The
   * `lines` overlays are for computed frontiers/limits only.
   */
  function drawScatter(host, pts, opts) {
    if (!host || !pts.length) return;
    var C = palette();
    var TONE = { better: C.better, worse: C.worse, ink: C.ink, muted: C.muted,
                 good: '#166b34', warn: '#eda100', range: C.range };
    var W = 900, H = opts.height || 440;
    var PAD_L = 96, PAD_R = opts.padRight || 40, PAD_T = 46, PAD_B = 76;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;

    function ext(get, min, max, pad) {
      if (has(min) && has(max)) return [min, max];
      var vs = pts.map(get);
      var lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
      var p = (hi - lo || 1) * (pad || 0.15);
      return [has(min) ? min : lo - p, has(max) ? max : hi + p];
    }
    var xe = ext(function (p) { return p.x; }, opts.xMin, opts.xMax);
    var ye = ext(function (p) { return p.y; }, opts.yMin, opts.yMax);
    var xs = opts.xStep || niceStep(xe[1] - xe[0]);
    var ys = opts.yStep || niceStep(ye[1] - ye[0]);
    function x(v) { return PAD_L + ((v - xe[0]) / (xe[1] - xe[0])) * plotW; }
    function y(v) { return PAD_T + plotH - ((v - ye[0]) / (ye[1] - ye[0])) * plotH; }

    var svg = baseSvg(W, H, opts.aria);
    for (var gx = Math.ceil(xe[0] / xs) * xs; gx <= xe[1] + 1e-9; gx += xs) {
      var gxv = Math.round(gx * 100) / 100;
      svg.appendChild(tag('line', { x1: x(gxv), x2: x(gxv), y1: PAD_T,
                                    y2: PAD_T + plotH, stroke: C.grid,
                                    'stroke-width': 1 }));
      svg.appendChild(tag('text', { x: x(gxv), y: PAD_T + plotH + 20,
                                    fill: C.muted, 'font-size': 12,
                                    'text-anchor': 'middle',
                                    'font-variant-numeric': 'tabular-nums' },
                          opts.xTick ? opts.xTick(gxv)
                                     : fmt(gxv) + (opts.xTickUnit || '')));
    }
    for (var gy = Math.ceil(ye[0] / ys) * ys; gy <= ye[1] + 1e-9; gy += ys) {
      var gyv = Math.round(gy * 100) / 100;
      svg.appendChild(tag('line', { x1: PAD_L, x2: PAD_L + plotW,
                                    y1: y(gyv), y2: y(gyv), stroke: C.grid,
                                    'stroke-width': 1 }));
      svg.appendChild(tag('text', { x: PAD_L - 10, y: y(gyv) + 4,
                                    fill: C.muted, 'font-size': 12,
                                    'text-anchor': 'end',
                                    'font-variant-numeric': 'tabular-nums' },
                          opts.yTick ? opts.yTick(gyv)
                                     : fmt(gyv) + (opts.yTickUnit || '')));
    }
    if (opts.xMarker && has(opts.xMarker.at)
        && opts.xMarker.at >= xe[0] && opts.xMarker.at <= xe[1]) {
      svg.appendChild(tag('line', {
        x1: x(opts.xMarker.at), x2: x(opts.xMarker.at),
        y1: PAD_T, y2: PAD_T + plotH,
        stroke: C.worse, 'stroke-width': 1.5, 'stroke-dasharray': '6 3',
      }));
      if (opts.xMarker.label) {
        svg.appendChild(tag('text', {
          x: x(opts.xMarker.at) - 6, y: PAD_T + 12, fill: C.worse,
          'font-size': 11, 'font-weight': 600, 'text-anchor': 'end',
        }, opts.xMarker.label));
      }
    }
    (opts.lines || []).forEach(function (ln) {
      if (!ln.points || ln.points.length < 2) return;
      var d = '';
      ln.points.forEach(function (p) {
        d += (d ? ' L ' : 'M ') + x(p.x) + ' ' + y(p.y);
      });
      svg.appendChild(tag('path', {
        d: d, fill: 'none', stroke: TONE[ln.tone] || C.muted,
        'stroke-width': 2.5, 'stroke-dasharray': ln.dash || '6 3',
        'stroke-linejoin': 'round',
      }));
      if (ln.label) {
        var lp = ln.points[ln.points.length - 1];
        svg.appendChild(tag('text', {
          x: x(lp.x) + 6, y: y(lp.y) - 6, fill: TONE[ln.tone] || C.muted,
          'font-size': 11, 'font-weight': 600,
        }, ln.label));
      }
    });
    if (opts.zeroY && ye[0] < 0 && ye[1] > 0) {
      svg.appendChild(tag('line', {
        x1: PAD_L, x2: PAD_L + plotW, y1: y(0), y2: y(0),
        stroke: C.ink, 'stroke-width': 1.5, 'stroke-dasharray': '5 4',
      }));
      if (opts.zeroY.label) {
        svg.appendChild(tag('text', {
          x: PAD_L + 6, y: y(0) - 8, fill: C.ink, 'font-size': 12,
          'font-weight': 600,
        }, opts.zeroY.label));
      }
    }
    if (opts.xLabel) {
      svg.appendChild(tag('text', {
        x: PAD_L + plotW / 2, y: H - 24, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
      }, opts.xLabel));
    }
    if (opts.yLabel) {
      svg.appendChild(tag('text', {
        x: 18, y: PAD_T + plotH / 2, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
        transform: 'rotate(-90 18 ' + (PAD_T + plotH / 2) + ')',
      }, opts.yLabel));
    }
    var legX = PAD_L;
    (opts.legend || []).forEach(function (it) {
      var LX = legX + 8, LY = PAD_T - 30;
      legX += 20 + it.label.length * 6.4 + 24;
      if (it.shape === 'diamond') {
        svg.appendChild(tag('rect', { x: LX - 6, y: LY - 6, width: 12,
                                      height: 12, rx: 2,
                                      fill: TONE[it.tone] || C.ink,
                                      stroke: C.surface, 'stroke-width': 2,
                                      transform: 'rotate(45 ' + LX + ' ' + LY + ')' }));
      } else {
        svg.appendChild(tag('circle', { cx: LX, cy: LY, r: 6,
                                        fill: TONE[it.tone] || C.ink,
                                        stroke: C.surface, 'stroke-width': 2 }));
      }
      svg.appendChild(tag('text', { x: LX + 12, y: LY + 4, fill: C.ink,
                                    'font-size': 12 }, it.label));
    });

    pts.forEach(function (p) {
      var g = tag('g', {});
      var cx = x(p.x), cy = y(p.y);
      var fill = TONE[p.tone] || C.ink;
      var pr = p.r || 7;
      if (p.shape === 'diamond') {
        g.appendChild(tag('rect', {
          x: cx - pr, y: cy - pr, width: pr * 2, height: pr * 2, rx: 2,
          fill: fill, stroke: C.surface, 'stroke-width': 2,
          transform: 'rotate(45 ' + cx + ' ' + cy + ')',
        }));
      } else {
        g.appendChild(tag('circle', {
          cx: cx, cy: cy, r: pr, fill: fill,
          stroke: C.surface, 'stroke-width': 2,
        }));
      }
      if (p.name) {
        g.appendChild(tag('text', {
          x: cx, y: cy - (p.r || 7) - 7, fill: TONE[p.nameTone] || C.ink,
          'font-size': p.nameSize || 12.5,
          'font-weight': 600, 'text-anchor': 'middle',
        }, p.name));
      }
      if (p.sub) {
        g.appendChild(tag('text', {
          x: cx, y: cy + 24, fill: C.muted, 'font-size': 11.5,
          'text-anchor': 'middle', 'font-variant-numeric': 'tabular-nums',
        }, p.sub));
      }
      if (p.title) g.appendChild(tag('title', {}, p.title));
      svg.appendChild(g);
    });
    host.appendChild(svg);
  }

  /* ── drawLine: values over an ordered category axis ─────────────────────
   * The one honest use of a line: an ORDER (serial position, rounds) whose
   * progression is the question. series: [{label, values[], tone}];
   * opts: cats (x labels), yLabel, xLabel, yMin/yMax/yStep, aria, height,
   * unit. Every point carries its value.
   */
  function drawLine(host, series, opts) {
    if (!host || !series.length || !opts.cats || !opts.cats.length) return;
    var C = palette();
    var TONE = { better: C.better, worse: C.worse, ink: C.ink, muted: C.muted };
    var W = 900, H = opts.height || 380;
    var PAD_L = 84, PAD_R = 30, PAD_T = 40, PAD_B = 70;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
    var vals = [];
    series.forEach(function (s) {
      s.values.forEach(function (v) { if (has(v)) vals.push(v); });
    });
    if (!vals.length) return;
    var lo = has(opts.yMin) ? opts.yMin : Math.min.apply(null, vals);
    var hi = has(opts.yMax) ? opts.yMax : Math.max.apply(null, vals);
    if (lo > 0 && !has(opts.yMin)) lo = 0;
    if (hi < 0 && !has(opts.yMax)) hi = 0;
    var pad = (hi - lo || 1) * 0.12;
    if (!has(opts.yMin)) lo -= pad;
    if (!has(opts.yMax)) hi += pad;
    var step = opts.yStep || niceStep(hi - lo);
    var n = opts.cats.length;
    function x(i) { return PAD_L + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW); }
    function y(v) { return PAD_T + plotH - ((v - lo) / (hi - lo)) * plotH; }

    var svg = baseSvg(W, H, opts.aria);
    for (var gy = Math.ceil(lo / step) * step; gy <= hi + 1e-9; gy += step) {
      var gyv = Math.round(gy * 100) / 100;
      svg.appendChild(tag('line', { x1: PAD_L, x2: PAD_L + plotW,
                                    y1: y(gyv), y2: y(gyv),
                                    stroke: gyv === 0 ? C.range : C.grid,
                                    'stroke-width': gyv === 0 ? 1.75 : 1 }));
      svg.appendChild(tag('text', { x: PAD_L - 10, y: y(gyv) + 4,
                                    fill: C.muted, 'font-size': 11.5,
                                    'text-anchor': 'end',
                                    'font-variant-numeric': 'tabular-nums' },
                          fmt(gyv) + (opts.unit || '')));
    }
    opts.cats.forEach(function (c, i) {
      svg.appendChild(tag('text', {
        x: x(i), y: PAD_T + plotH + 20, fill: C.muted, 'font-size': 11.5,
        'text-anchor': 'middle',
      }, String(c)));
    });
    if (opts.xLabel) {
      svg.appendChild(tag('text', {
        x: PAD_L + plotW / 2, y: H - 10, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
      }, opts.xLabel));
    }
    if (opts.yLabel) {
      svg.appendChild(tag('text', {
        x: 18, y: PAD_T + plotH / 2, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
        transform: 'rotate(-90 18 ' + (PAD_T + plotH / 2) + ')',
      }, opts.yLabel));
    }

    series.forEach(function (s, si) {
      var color = TONE[s.tone] || (si === 0 ? C.ink : C.muted);
      var d = '';
      s.values.forEach(function (v, i) {
        if (!has(v)) return;
        d += (d ? ' L ' : 'M ') + x(i) + ' ' + y(v);
      });
      if (d) {
        svg.appendChild(tag('path', {
          d: d, fill: 'none', stroke: color, 'stroke-width': 2.5,
          'stroke-linejoin': 'round',
          'stroke-dasharray': s.dash || null,
        }));
      }
      s.values.forEach(function (v, i) {
        if (!has(v)) return;
        svg.appendChild(tag('circle', {
          cx: x(i), cy: y(v), r: 5, fill: color,
          stroke: C.surface, 'stroke-width': 2,
        }));
        svg.appendChild(tag('text', {
          x: x(i), y: y(v) - 11, fill: C.ink, 'font-size': 11,
          'font-weight': 600, 'text-anchor': 'middle',
          'font-variant-numeric': 'tabular-nums',
        }, fmt(Math.round(v * 100) / 100) + (opts.unit || '')));
      });
      if (s.label && series.length > 1) {
        var li = s.values.length - 1;
        while (li >= 0 && !has(s.values[li])) li--;
        if (li >= 0) {
          svg.appendChild(tag('text', {
            x: x(li) + 10, y: y(s.values[li]) + 4, fill: color,
            'font-size': 12, 'font-weight': 600,
          }, s.label));
        }
      }
    });
    host.appendChild(svg);
  }

  /* ── dataTable: rule 3's second half, next to every chart ───────────────
   * The same numbers as text, in a collapsed <details> — the pattern
   * FL-012's chart-table.js produces for Chart.js charts, here for the
   * hand-drawn ones. headers: [...], rows: [[...], ...].
   */
  function dataTable(host, summary, headers, rows) {
    if (!host) return;
    var details = document.createElement('details');
    details.className = 'chart-data-table';
    var sum = document.createElement('summary');
    sum.textContent = summary;
    details.appendChild(sum);
    var table = document.createElement('table');
    var thead = document.createElement('thead');
    var trh = document.createElement('tr');
    headers.forEach(function (h) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = h;
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    rows.forEach(function (r) {
      var tr = document.createElement('tr');
      r.forEach(function (v, i) {
        var td = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) td.scope = 'row';
        td.textContent = String(v);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    details.appendChild(table);
    host.appendChild(details);
  }

  window.PhrononCharts = {
    palette: palette,
    has: has,
    fmt: fmt,
    tag: tag,
    declutter: declutter,
    drawRows: drawRows,
    drawDotRows: drawDotRows,
    drawShares: drawShares,
    drawBars: drawBars,
    drawScatter: drawScatter,
    drawLine: drawLine,
    dataTable: dataTable,
  };
})();
