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
    // "Up is good" green, for signed effects only, and admissible against
    // `worse` because the two differ strongly in lightness rather than in
    // hue alone. See CHART-STANDARD.md and chart_palette_check.py.
    up:      '#2e9e4f',
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
   * opts: min, max, step, reverse (true = the HIGH end sits on the LEFT —
   *   for scales like layoff rank 1..8 where the low number is the good
   *   end and belongs on the right), axisLeft, axisRight, betterIs
   *   ('higher'|'lower'|null: null = no judgement, moves stay ink), unit
   *   (suffix on printed values), verdict(delta) -> text (default signs
   *   the delta), rowH, labelW, labelMax, labelSize, rightW, aria,
   *   marker {at, label} a dashed reference line across all rows.
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
        ['a', 'b', 'only', 'lo', 'hi'].forEach(function (k) { if (has(r[k])) vals.push(r[k]); });
      });
      if (opts.marker && has(opts.marker.at)) vals.push(opts.marker.at);
      if (!vals.length) return;
      var vmin = Math.min.apply(null, vals), vmax = Math.max.apply(null, vals);
      var pad = (vmax - vmin || 1) * 0.15;
      lo = has(lo) ? lo : vmin - pad;
      hi = has(hi) ? hi : vmax + pad;
    }
    var step = opts.step || niceStep(hi - lo);
    function x(v) {
      var f = (v - lo) / (hi - lo);
      return plotX + (opts.reverse ? 1 - f : f) * plotW;
    }

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

      // The track first, under everything (a CI, a spread).
      if (has(r.lo) && has(r.hi)) {
        var tlo = Math.min(x(r.lo), x(r.hi)), thi = Math.max(x(r.lo), x(r.hi));
        row.appendChild(tag('rect', {
          x: tlo, y: y - 4, width: Math.max(thi - tlo, 3), height: 8,
          rx: 4, fill: C.range,
        }));
      }
      var a = r.a, b = has(r.b) ? r.b : r.only;
      var pair = has(a) && has(r.b);
      var delta = pair ? Math.round((r.b - a) * 100) / 100 : null;
      var improved = null;
      if (pair && opts.betterIs) {
        improved = delta === 0 ? null
                 : (opts.betterIs === 'higher' ? delta > 0 : delta < 0);
      }
      var TONESET = { better: C.better, worse: C.worse, ink: C.ink,
                      muted: C.muted };
      var moveColor = improved === null ? (pair ? C.muted : C.ink)
                    : (improved ? C.better : C.worse);
      if (!pair && r.tone) moveColor = TONESET[r.tone] || C.ink;

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
   * glyph (short text INSIDE the mark — the mark grows hollow with a toned
   * ring so the glyph is legible; identity, said twice with the name),
   * title}. opts.quadrants {x, y, labels: [TL, TR, BL, BR]} draws dashed
   * dividers through (x, y) and italic corner labels — for panel charts
   * whose四 corners mean something. opts: xMin/xMax/xStep, yMin/yMax/yStep, xLabel (under the axis),
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
    if (opts.quadrants) {
      var q = opts.quadrants;
      [[x(q.x), x(q.x), PAD_T, PAD_T + plotH], [PAD_L, PAD_L + plotW, y(q.y), y(q.y)]]
        .forEach(function (l2) {
          svg.appendChild(tag('line', {
            x1: l2[0], x2: l2[1], y1: l2[2], y2: l2[3],
            stroke: C.range, 'stroke-width': 1.5, 'stroke-dasharray': '6 4',
          }));
        });
      var corners = [
        [PAD_L + 8, PAD_T + 16, 'start'], [PAD_L + plotW - 8, PAD_T + 16, 'end'],
        [PAD_L + 8, PAD_T + plotH - 8, 'start'], [PAD_L + plotW - 8, PAD_T + plotH - 8, 'end'],
      ];
      (q.labels || []).forEach(function (lab, i2) {
        if (!lab) return;
        svg.appendChild(tag('text', {
          x: corners[i2][0], y: corners[i2][1], fill: C.muted,
          'font-size': 11, 'font-style': 'italic',
          'text-anchor': corners[i2][2],
        }, lab));
      });
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
      if (p.glyph) {
        // Hollow ring, toned; the glyph names the point inside it.
        g.appendChild(tag('circle', {
          cx: cx, cy: cy, r: pr, fill: C.surface,
          stroke: fill, 'stroke-width': 2.5,
        }));
        g.appendChild(tag('text', {
          x: cx, y: cy + 4.5, fill: C.ink, 'font-size': 13,
          'font-weight': 700, 'text-anchor': 'middle',
        }, p.glyph));
      } else if (p.shape === 'diamond') {
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
   * progression is the question. series: [{label, values[], tone OR color
   * (hex — segment identity lines), dash}]; opts: cats (x labels), yLabel,
   * xLabel, yMin/yMax/yStep, reverse (true = LOW values at the top, for
   * rank scales where 1 is the good end), legend (true draws a swatch row;
   * default is on from two series up), aria, height, unit, pointValues
   * (false suppresses the per-point numbers when many series would collide
   * — the data table carries them instead). Every point carries its value
   * by default.
   */
  function drawLine(host, series, opts) {
    if (!host || !series.length || !opts.cats || !opts.cats.length) return;
    var C = palette();
    var TONE = { better: C.better, worse: C.worse, ink: C.ink, muted: C.muted };
    var W = 900, H = opts.height || 380;
    var showLegend = opts.legend === true
                   || (opts.legend !== false && series.length > 1);
    // Two legend rows' worth of head-room when there are many segments: a
    // demographic breakdown routinely has six or eight of them.
    var legendRows = showLegend ? Math.ceil(series.length / 4) : 0;
    var PAD_L = 84, PAD_R = 30;
    var PAD_T = 40 + legendRows * 22, PAD_B = 70;
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
    function y(v) {
      var f = (v - lo) / (hi - lo);
      if (opts.reverse) f = 1 - f;
      return PAD_T + plotH - f * plotH;
    }

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
      var color = s.color || TONE[s.tone] || (si === 0 ? C.ink : C.muted);
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
          cx: x(i), cy: y(v), r: series.length > 3 ? 4 : 5, fill: color,
          stroke: C.surface, 'stroke-width': 2,
        }));
        if (opts.pointValues !== false) {
          svg.appendChild(tag('text', {
            x: x(i), y: y(v) - 11, fill: C.ink, 'font-size': 11,
            'font-weight': 600, 'text-anchor': 'middle',
            'font-variant-numeric': 'tabular-nums',
          }, fmt(Math.round(v * 100) / 100) + (opts.unit || '')));
        }
      });
      // The end-of-line label is only useful when there are one or two
      // lines; with a legend above, it just crowds the right edge.
      if (s.label && series.length === 2 && !showLegend) {
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
    if (showLegend) {
      var per = Math.ceil(series.length / legendRows);
      for (var lr = 0; lr < legendRows; lr++) {
        legendRow(svg, series.slice(lr * per, (lr + 1) * per)
          .map(function (se, si) {
            return { label: se.label,
                     fill: se.color || TONE[se.tone] || C.ink };
          }), PAD_L, 22 + lr * 22);
      }
    }
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

  /* ── drawGroupedBars: categories on X, one bar per series ───────────────
   * The classic comparison when the reader wants to see CATEGORIES side by
   * side (employees, rounds) rather than one row per unit. cats: the x
   * labels; series: [{label, values[], color, colors[] (one per bar, when
   * the CATEGORY carries the identity — a role, a party — rather than the
   * series), min[]/max[] (a range behind each bar: the spread the average
   * was taken over, drawn as a thin capped line so it reads as context,
   * never as a second bar)}]. Every bar carries its value.
   *
   * opts: horizontal (bars run along the x axis with the categories down
   * the left — for many categories, or long category names that would
   * crowd a vertical axis), decimals (force a fixed number of them on the printed values, so
   * a column of averages lines up as 2.00 / 4.33 rather than 2 / 4.33),
   * signColor {up, down} colours each bar by the sign of its value — for
   * signed effects, where the series is one meaning with two directions,
   * yLabel, yMin/yMax/yStep, reverse (true = the LOW value is the good
   * end and is drawn at the TOP — rank scales), unit, aria, height, legend
   * (false suppresses it; default on when there is more than one series),
   * baseline (the value bars grow FROM; defaults to the axis floor, or 0
   * when the scale spans it).
   */
  function drawGroupedBars(host, cats, series, opts) {
    if (!host || !cats.length || !series.length) return;
    if (opts.horizontal) return drawGroupedBarsH(host, cats, series, opts);
    var C = palette();
    var W = 900, H = opts.height || 400;
    var showLegend = opts.legend === true
                   || (opts.legend !== false && series.length > 1);
    var PAD_L = 76, PAD_R = 24;
    var PAD_T = showLegend ? 46 : 26;
    var PAD_B = opts.xLabel ? 74 : 56;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;

    var vals = [];
    series.forEach(function (se) {
      se.values.forEach(function (v) { if (has(v)) vals.push(v); });
      ['min', 'max'].forEach(function (k) {
        (se[k] || []).forEach(function (v) { if (has(v)) vals.push(v); });
      });
    });
    if (!vals.length) return;
    var lo = has(opts.yMin) ? opts.yMin : Math.min.apply(null, vals);
    var hi = has(opts.yMax) ? opts.yMax : Math.max.apply(null, vals);
    if (!has(opts.yMin) && !has(opts.yMax)) {
      var pad = (hi - lo || 1) * 0.18;
      if (lo > 0) lo = 0; else lo -= pad;
      if (hi < 0) hi = 0; else hi += pad;
    }
    var step = opts.yStep || niceStep(hi - lo);
    function y(v) {
      var f = (v - lo) / (hi - lo);
      if (opts.reverse) f = 1 - f;
      return PAD_T + plotH - f * plotH;
    }
    var base = has(opts.baseline) ? opts.baseline
             : (lo <= 0 && hi >= 0 ? 0 : (opts.reverse ? hi : lo));

    var svg = baseSvg(W, H, opts.aria);
    for (var t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) {
      var tv = Math.round(t * 100) / 100;
      svg.appendChild(tag('line', {
        x1: PAD_L, x2: PAD_L + plotW, y1: y(tv), y2: y(tv),
        stroke: tv === base ? C.range : C.grid,
        'stroke-width': tv === base ? 1.75 : 1,
      }));
      svg.appendChild(tag('text', {
        x: PAD_L - 10, y: y(tv) + 4, fill: C.muted, 'font-size': 11.5,
        'text-anchor': 'end', 'font-variant-numeric': 'tabular-nums',
      }, fmt(tv) + (opts.unit || '')));
    }
    if (opts.yLabel) {
      svg.appendChild(tag('text', {
        x: 18, y: PAD_T + plotH / 2, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
        transform: 'rotate(-90 18 ' + (PAD_T + plotH / 2) + ')',
      }, opts.yLabel));
    }

    function show(v) {
      return has(opts.decimals) ? Number(v).toFixed(opts.decimals)
                                : String(Math.round(v * 100) / 100);
    }
    var slot = plotW / cats.length;
    var groupW = Math.min(slot * 0.7, 90);
    var barW = groupW / series.length;
    cats.forEach(function (cat, i) {
      var cx = PAD_L + i * slot + slot / 2;
      series.forEach(function (se, si) {
        var v = se.values[i];
        if (!has(v)) return;
        var x0 = cx - groupW / 2 + si * barW;
        var top = Math.min(y(v), y(base)), bot = Math.max(y(v), y(base));
        var fill = (se.colors && se.colors[i])
                || se.color || (si === 0 ? C.muted : C.better);
        if (opts.signColor) {
          fill = v > base ? (opts.signColor.up || C.better)
               : v < base ? (opts.signColor.down || C.worse) : C.muted;
        }
        var rect = tag('rect', {
          x: x0 + 1, y: top, width: Math.max(barW - 2, 2),
          height: Math.max(bot - top, 1),
          fill: fill,
        });
        rect.appendChild(tag('title', {},
          cat + ' — ' + (se.label || '') + ': ' + fmt(show(v))
          + (opts.unit || '')));
        svg.appendChild(rect);
        // The range this average was taken over, behind the bar: a thin
        // capped line, in the bar's own colour at low opacity, so it reads
        // as the spread rather than as a value of its own.
        if (se.min && se.max
            && has(se.min[i]) && has(se.max[i]) && se.min[i] !== se.max[i]) {
          var ry1 = y(se.max[i]), ry2 = y(se.min[i]);
          var rcx = x0 + barW / 2;
          [[rcx - 2, ry1, 4, Math.abs(ry2 - ry1)],
           [rcx - 5, Math.min(ry1, ry2), 10, 2],
           [rcx - 5, Math.max(ry1, ry2) - 2, 10, 2]].forEach(function (r2) {
            svg.appendChild(tag('rect', {
              x: r2[0], y: r2[1], width: r2[2], height: r2[3],
              fill: fill, opacity: 0.55,
            }));
          });
        }
        svg.appendChild(tag('text', {
          x: x0 + barW / 2,
          // Below the bar when it hangs downward from the baseline, or the
          // label lands inside the bar it belongs to.
          y: (v < base && !opts.reverse) ? bot + 14 : top - 5,
          fill: C.ink, 'font-size': 11,
          'font-weight': 600, 'text-anchor': 'middle',
          'font-variant-numeric': 'tabular-nums',
        }, fmt(show(v)) + (opts.unit || '')));
      });
      svg.appendChild(tag('text', {
        x: cx, y: PAD_T + plotH + 18, fill: C.ink, 'font-size': 11.5,
        'text-anchor': 'middle',
      }, cat));
    });
    if (opts.xLabel) {
      svg.appendChild(tag('text', {
        x: PAD_L + plotW / 2, y: H - 12, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
      }, opts.xLabel));
    }
    if (showLegend) legendRow(svg, series.map(function (se, si) {
      return { label: se.label,
               fill: se.color || (si === 0 ? C.muted : C.better) };
    }), PAD_L, 22);
    if (opts.legendItems) legendRow(svg, opts.legendItems, PAD_L, 22);
    host.appendChild(svg);
  }

  /* The horizontal twin of drawGroupedBars: categories down the left, bars
   * running rightward. Same options; the value scale is the x axis. */
  function drawGroupedBarsH(host, cats, series, opts) {
    var C = palette();
    var showLegend = opts.legend === true
                   || (opts.legend !== false && series.length > 1);
    var W = 900, ROWH = opts.rowH || (series.length > 1 ? 20 : 26);
    var LABEL_W = opts.labelW || 220, PAD_R = 70;
    var PAD_T = showLegend ? 46 : 22, PAD_B = 46;
    var slot = ROWH * series.length + 16;
    var H = PAD_T + cats.length * slot + PAD_B;
    var plotW = W - LABEL_W - PAD_R;

    var vals = [];
    series.forEach(function (se) {
      se.values.forEach(function (v) { if (has(v)) vals.push(v); });
    });
    if (!vals.length) return;
    var lo = has(opts.yMin) ? opts.yMin : Math.min(0, Math.min.apply(null, vals));
    var hi = has(opts.yMax) ? opts.yMax : Math.max.apply(null, vals) * 1.12;
    var step = opts.yStep || niceStep(hi - lo);
    function x(v) { return LABEL_W + ((v - lo) / (hi - lo)) * plotW; }
    var base = has(opts.baseline) ? opts.baseline : (lo <= 0 ? 0 : lo);

    var svg = baseSvg(W, H, opts.aria);
    for (var t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) {
      var tv = Math.round(t * 100) / 100;
      svg.appendChild(tag('line', {
        x1: x(tv), x2: x(tv), y1: PAD_T - 8, y2: H - PAD_B + 4,
        stroke: tv === base ? C.range : C.grid,
        'stroke-width': tv === base ? 1.75 : 1,
      }));
      svg.appendChild(tag('text', {
        x: x(tv), y: H - PAD_B + 20, fill: C.muted, 'font-size': 11.5,
        'text-anchor': 'middle', 'font-variant-numeric': 'tabular-nums',
      }, fmt(tv) + (opts.unit || '')));
    }
    function showv(v) {
      return has(opts.decimals) ? Number(v).toFixed(opts.decimals)
                                : String(Math.round(v * 100) / 100);
    }
    cats.forEach(function (cat, i) {
      var y0 = PAD_T + i * slot + 8;
      var shown = String(cat);
      if (opts.labelMax && shown.length > opts.labelMax) {
        shown = shown.slice(0, opts.labelMax - 1) + '…';
      }
      var nameEl = tag('text', {
        x: LABEL_W - 12, y: y0 + (ROWH * series.length) / 2 + 4, fill: C.ink,
        'font-size': 12.5, 'font-weight': 600, 'text-anchor': 'end',
      }, shown);
      if (shown !== String(cat)) nameEl.appendChild(tag('title', {}, String(cat)));
      svg.appendChild(nameEl);
      series.forEach(function (se, si) {
        var v = se.values[i];
        if (!has(v)) return;
        var yb = y0 + si * ROWH;
        var left = Math.min(x(v), x(base)), right = Math.max(x(v), x(base));
        var fill = (se.colors && se.colors[i]) || se.color
                 || (si === 0 ? C.ink : C.muted);
        var rect = tag('rect', {
          x: left, y: yb + 2, width: Math.max(right - left, 1),
          height: ROWH - 4, fill: fill,
        });
        rect.appendChild(tag('title', {},
          cat + ' — ' + (se.label || '') + ': ' + fmt(showv(v))
          + (opts.unit || '')));
        svg.appendChild(rect);
        svg.appendChild(tag('text', {
          x: right + 6, y: yb + ROWH / 2 + 4, fill: C.ink, 'font-size': 11,
          'font-weight': 600, 'font-variant-numeric': 'tabular-nums',
        }, fmt(showv(v)) + (opts.unit || '')));
      });
    });
    if (showLegend) legendRow(svg, series.map(function (se, si) {
      return { label: se.label, fill: se.color || (si === 0 ? C.ink : C.muted) };
    }), LABEL_W, 22);
    host.appendChild(svg);
  }

  /* ── drawRadar: one closed profile per person, over shared spokes ───────
   * The one form where a RADAR earns its place: several people answered the
   * SAME items on the same scale, and the question is the shape of their
   * disagreement rather than any single value. Every spoke is one item, the
   * scale is identical on all of them, and the polygons are read against
   * each other — which is exactly what a radar does well and what a stack of
   * bars does badly.
   *
   * It is deliberately NOT offered for "one series, many attributes": a
   * lone polygon invites area comparisons that mean nothing, because a
   * radar's area depends on the arbitrary order of its spokes. Two or three
   * series is the useful range; past that the polygons occlude one another.
   *
   * spokes: the item labels. series: [{label, values[], color}].
   * opts: min, max, step, unit, aria, height, valueFormat(v) -> string,
   * pointValues (default: on when spokes x series stays small enough to
   * read — otherwise the data table carries them, which the caller should
   * always draw).
   */
  function drawRadar(host, spokes, series, opts) {
    if (!host || !spokes.length || !series.length) return;
    var C = palette();
    var TONE = { better: C.better, worse: C.worse, ink: C.ink, muted: C.muted,
                 up: C.up, warn: '#eda100' };
    var n = spokes.length;
    var W = 900, H = opts.height || 520;
    var legendH = 34;
    var cx = W / 2, cy = (H - legendH) / 2 + 6;
    // Room for the longest spoke label at the widest point.
    var R = Math.min(cy - 46, W / 2 - 190);
    var lo = has(opts.min) ? opts.min : 0;
    var hi = has(opts.max) ? opts.max : 1;
    var step = opts.step || niceStep(hi - lo);
    var fmtv = opts.valueFormat || function (v) {
      return String(Math.round(v * 100) / 100) + (opts.unit || '');
    };
    function angle(i) { return -Math.PI / 2 + (i / n) * Math.PI * 2; }
    function radius(v) {
      var f = (v - lo) / (hi - lo);
      return Math.max(0, Math.min(1, f)) * R;
    }
    function px(i, v) { return cx + radius(v) * Math.cos(angle(i)); }
    function py(i, v) { return cy + radius(v) * Math.sin(angle(i)); }

    var svg = baseSvg(W, H, opts.aria);

    // The rings, as polygons rather than circles: a circular grid reads as a
    // different scale from the straight edges the data draws.
    for (var t = lo; t <= hi + 1e-9; t += step) {
      var pts = [];
      for (var i = 0; i < n; i++) pts.push(px(i, t) + ',' + py(i, t));
      svg.appendChild(tag('polygon', {
        points: pts.join(' '), fill: 'none',
        stroke: Math.abs(t - hi) < 1e-9 ? C.range : C.grid,
        'stroke-width': Math.abs(t - hi) < 1e-9 ? 1.5 : 1,
      }));
      if (t > lo + 1e-9) {
        // On the BISECTOR between the first two spokes, not up the vertical:
        // spoke 0 sits at twelve o'clock, so ring labels stacked there ran
        // straight through its own item label.
        var la = angle(0) + (Math.PI * 2 / n) / 2;
        svg.appendChild(tag('text', {
          x: cx + radius(t) * Math.cos(la) + 2,
          y: cy + radius(t) * Math.sin(la) + 3,
          fill: C.muted, 'font-size': 10.5,
          'font-variant-numeric': 'tabular-nums',
        }, fmtv(Math.round(t * 100) / 100)));
      }
    }

    // The spokes, and their item labels at the rim.
    for (var i2 = 0; i2 < n; i2++) {
      svg.appendChild(tag('line', {
        x1: cx, y1: cy, x2: px(i2, hi), y2: py(i2, hi),
        stroke: C.grid, 'stroke-width': 1,
      }));
      var a = angle(i2);
      var lx = cx + (R + 14) * Math.cos(a), ly = cy + (R + 14) * Math.sin(a);
      var cos = Math.cos(a);
      svg.appendChild(tag('text', {
        x: lx, y: ly + 4, fill: C.ink, 'font-size': 11.5, 'font-weight': 600,
        'text-anchor': cos > 0.2 ? 'start' : cos < -0.2 ? 'end' : 'middle',
      }, String(spokes[i2])));
    }

    var showValues = opts.pointValues !== undefined
      ? opts.pointValues : (n * series.length <= 24);

    series.forEach(function (se, si) {
      var color = se.color || TONE[se.tone]
                || [C.better, C.worse, C.ink][si % 3];
      var pts = [];
      for (var i3 = 0; i3 < n; i3++) {
        var v = has(se.values[i3]) ? se.values[i3] : lo;
        pts.push(px(i3, v) + ',' + py(i3, v));
      }
      svg.appendChild(tag('polygon', {
        points: pts.join(' '), fill: color, 'fill-opacity': 0.12,
        stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round',
      }));
      for (var i4 = 0; i4 < n; i4++) {
        if (!has(se.values[i4])) continue;
        var vx = px(i4, se.values[i4]), vy = py(i4, se.values[i4]);
        var dot = tag('circle', {
          cx: vx, cy: vy, r: 4.5, fill: color,
          stroke: C.surface, 'stroke-width': 1.5,
        });
        dot.appendChild(tag('title', {},
          se.label + ' — ' + spokes[i4] + ': ' + fmtv(se.values[i4])));
        svg.appendChild(dot);
        if (showValues) {
          var aa = angle(i4);
          svg.appendChild(tag('text', {
            x: vx + 9 * Math.cos(aa), y: vy + 9 * Math.sin(aa) + 4,
            fill: C.ink, 'font-size': 10.5, 'font-weight': 600,
            'text-anchor': Math.cos(aa) > 0.2 ? 'start'
                         : Math.cos(aa) < -0.2 ? 'end' : 'middle',
            'font-variant-numeric': 'tabular-nums',
          }, fmtv(se.values[i4])));
        }
      }
    });

    legendRow(svg, series.map(function (se, si) {
      return { label: se.label,
               fill: se.color || TONE[se.tone]
                   || [C.better, C.worse, C.ink][si % 3] };
    }), 40, H - 12);
    host.appendChild(svg);
  }

  /* A row of swatch+word legend chips. Identity is never colour-alone: the
   * swatch always sits beside its words, and the table repeats the numbers. */
  function legendRow(svg, items, x0, y0) {
    var C = palette();
    var lx = x0;
    items.forEach(function (it) {
      svg.appendChild(tag('rect', {
        x: lx, y: y0 - 10, width: 13, height: 13, rx: 3,
        fill: it.hollow ? 'none' : it.fill,
        stroke: it.hollow ? C.range : 'none',
        'stroke-width': it.hollow ? 1.5 : null,
        'stroke-dasharray': it.hollow ? '3 2' : null,
      }));
      svg.appendChild(tag('text', {
        x: lx + 19, y: y0 + 1, fill: C.muted, 'font-size': 12,
      }, it.label));
      lx += 19 + String(it.label).length * 6.4 + 22;
    });
  }

  /* ── drawStackedBars: categories on X, one stack per category ───────────
   * cats: x labels; keys: the segment order — FIRST key sits at the BOTTOM
   * of each stack, so a scale whose good end is 1 (rank) is passed
   * reversed and reads with rank 1 on top; rows: per category a {key:count}
   * map; opts: fills, labels, darkText, legendKeys (the legend's own
   * order, when it should differ from the stacking order), yLabel, aria,
   * height, total (a fixed
   * denominator per category — the unfilled remainder then shows as a dashed
   * frame, so a partly-answered category can never look complete).
   */
  function drawStackedBars(host, cats, rows, opts) {
    if (!host || !cats.length) return;
    var C = palette();
    var KEYS = opts.keys || [];
    var W = 900, H = opts.height || 420;
    var PAD_L = 70, PAD_R = 24, PAD_T = 26, PAD_B = 84;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
    var maxY = 0;
    rows.forEach(function (r, i) {
      var sum = 0;
      KEYS.forEach(function (k) { sum += (r && r[k]) || 0; });
      maxY = Math.max(maxY, opts.total || sum);
    });
    maxY = maxY || 1;
    var step = opts.yStep || Math.max(1, niceStep(maxY));
    function y(v) { return PAD_T + plotH - (v / maxY) * plotH; }

    var svg = baseSvg(W, H, opts.aria);
    for (var t = 0; t <= maxY + 1e-9; t += step) {
      svg.appendChild(tag('line', {
        x1: PAD_L, x2: PAD_L + plotW, y1: y(t), y2: y(t),
        stroke: C.grid, 'stroke-width': 1,
      }));
      svg.appendChild(tag('text', {
        x: PAD_L - 10, y: y(t) + 4, fill: C.muted, 'font-size': 11.5,
        'text-anchor': 'end', 'font-variant-numeric': 'tabular-nums',
      }, fmt(Math.round(t))));
    }
    if (opts.yLabel) {
      svg.appendChild(tag('text', {
        x: 16, y: PAD_T + plotH / 2, fill: C.muted, 'font-size': 12.5,
        'text-anchor': 'middle',
        transform: 'rotate(-90 16 ' + (PAD_T + plotH / 2) + ')',
      }, opts.yLabel));
    }

    var slot = plotW / cats.length;
    var barW = Math.min(slot * 0.62, 74);
    cats.forEach(function (cat, i) {
      var cx = PAD_L + i * slot + slot / 2;
      var r = rows[i] || {};
      var total = opts.total || KEYS.reduce(function (a, k) {
        return a + ((r[k]) || 0);
      }, 0);
      if (opts.total) {
        svg.appendChild(tag('rect', {
          x: cx - barW / 2, y: y(opts.total), width: barW,
          height: plotH - (y(opts.total) - PAD_T),
          fill: 'none', stroke: C.range, 'stroke-width': 1.5,
          'stroke-dasharray': '4 3', rx: 3,
        }));
      }
      var acc = 0;
      KEYS.forEach(function (k) {
        var n = (r[k]) || 0;
        if (!n) return;
        var yTop = y(acc + n), yBot = y(acc);
        var rect = tag('rect', {
          x: cx - barW / 2, y: yTop, width: barW,
          height: Math.max(yBot - yTop, 1),
          fill: (opts.fills && opts.fills[k]) || C.muted,
          stroke: C.surface, 'stroke-width': 1.5,
        });
        rect.appendChild(tag('title', {},
          cat + ' — ' + ((opts.labels && opts.labels[k]) || k) + ': '
          + n + ' / ' + total));
        svg.appendChild(rect);
        if (yBot - yTop >= 14) {
          svg.appendChild(tag('text', {
            x: cx, y: (yTop + yBot) / 2 + 4.5,
            fill: (opts.darkText && opts.darkText[k]) ? C.ink : C.surface,
            'font-size': 11.5, 'text-anchor': 'middle',
            'font-variant-numeric': 'tabular-nums', 'pointer-events': 'none',
          }, String(n)));
        }
        acc += n;
      });
      svg.appendChild(tag('text', {
        x: cx, y: PAD_T + plotH + 18, fill: C.ink, 'font-size': 11.5,
        'text-anchor': 'middle',
      }, cat));
    });
    var items = (opts.legendKeys || KEYS).map(function (k) {
      return { label: (opts.labels && opts.labels[k]) || k,
               fill: (opts.fills && opts.fills[k]) || C.muted };
    });
    if (opts.legendExtra) items.push({ label: opts.legendExtra, hollow: true });
    legendRow(svg, items, PAD_L, H - 22);
    host.appendChild(svg);
  }

  /* ── drawPie: shares of one whole ────────────────────────────────────────
   * Reached for only when the reader's question really is "what fraction of
   * one whole" and the slices are few. slices: [{label, value, fill}];
   * opts: aria, height, unit, total (defaults to the sum). Every slice
   * carries its count and percentage, on the slice where it fits and on the
   * legend otherwise — a pie whose numbers live in a tooltip is unreadable
   * from the back of a room. opts.donut (0..1) punches a hole of that
   * fraction of the radius, for the tools whose charts have always been
   * doughnuts; opts.centre puts a short line of text in the hole.
   */
  function drawPie(host, slices, opts) {
    if (!host || !slices.length) return;
    var C = palette();
    var live = slices.filter(function (sl) { return sl.value > 0; });
    if (!live.length) return;
    var total = opts.total
      || slices.reduce(function (a, sl) { return a + (sl.value || 0); }, 0);
    if (!total) return;
    var W = 900, H = opts.height || 380;
    var cx = 300, cy = H / 2 - 6, R = Math.min(cy - 24, 130);
    var svg = baseSvg(W, H, opts.aria);

    var angle = -Math.PI / 2;                 // start at 12 o'clock
    live.forEach(function (sl) {
      var frac = sl.value / total;
      var end = angle + frac * Math.PI * 2;
      var mid = (angle + end) / 2;
      var big = frac > 0.5 ? 1 : 0;
      var path;
      var inner = opts.donut ? R * opts.donut : 0;
      if (frac >= 0.999 && !inner) {
        // A single full slice is a circle: an arc of exactly 360° collapses
        // to a point and draws nothing at all.
        path = tag('circle', { cx: cx, cy: cy, r: R, fill: sl.fill || C.muted,
                               stroke: C.surface, 'stroke-width': 2 });
      } else if (inner) {
        // An annulus sector: out along the start edge, round the outer arc,
        // back down the end edge, round the inner arc the other way.
        var e2 = frac >= 0.999 ? end - 0.0001 : end;
        path = tag('path', {
          d: 'M ' + (cx + inner * Math.cos(angle)) + ' ' + (cy + inner * Math.sin(angle))
            + ' L ' + (cx + R * Math.cos(angle)) + ' ' + (cy + R * Math.sin(angle))
            + ' A ' + R + ' ' + R + ' 0 ' + big + ' 1 '
            + (cx + R * Math.cos(e2)) + ' ' + (cy + R * Math.sin(e2))
            + ' L ' + (cx + inner * Math.cos(e2)) + ' ' + (cy + inner * Math.sin(e2))
            + ' A ' + inner + ' ' + inner + ' 0 ' + big + ' 0 '
            + (cx + inner * Math.cos(angle)) + ' ' + (cy + inner * Math.sin(angle)) + ' Z',
          fill: sl.fill || C.muted, stroke: C.surface, 'stroke-width': 2,
        });
      } else {
        path = tag('path', {
          d: 'M ' + cx + ' ' + cy
            + ' L ' + (cx + R * Math.cos(angle)) + ' ' + (cy + R * Math.sin(angle))
            + ' A ' + R + ' ' + R + ' 0 ' + big + ' 1 '
            + (cx + R * Math.cos(end)) + ' ' + (cy + R * Math.sin(end)) + ' Z',
          fill: sl.fill || C.muted, stroke: C.surface, 'stroke-width': 2,
        });
      }
      var pct = (frac * 100).toFixed(1) + '%';
      path.appendChild(tag('title', {},
        sl.label + ': ' + sl.value + ' (' + pct + ')'));
      svg.appendChild(path);
      if (frac >= 0.08) {
        var lr = inner ? (inner + R) / 2 / R : 0.62;
        svg.appendChild(tag('text', {
          x: cx + R * lr * Math.cos(mid), y: cy + R * lr * Math.sin(mid) + 5,
          fill: sl.darkText ? C.ink : C.surface, 'font-size': 14,
          'font-weight': 700, 'text-anchor': 'middle',
          'font-variant-numeric': 'tabular-nums', 'pointer-events': 'none',
        }, pct));
      }
      angle = end;
    });

    if (opts.centre) {
      svg.appendChild(tag('text', {
        x: cx, y: cy + 5, fill: C.ink, 'font-size': 15, 'font-weight': 700,
        'text-anchor': 'middle',
      }, opts.centre));
    }
    // The legend doubles as the readout: every slice, its count and share,
    // including the ones too thin to label on the pie.
    var ly = cy - (slices.length - 1) * 15;
    slices.forEach(function (sl) {
      var pct = ((sl.value || 0) / total * 100).toFixed(1) + '%';
      svg.appendChild(tag('rect', {
        x: 520, y: ly - 11, width: 14, height: 14, rx: 3,
        fill: sl.fill || C.muted,
      }));
      svg.appendChild(tag('text', {
        x: 545, y: ly, fill: C.ink, 'font-size': 13,
      }, sl.label));
      svg.appendChild(tag('text', {
        x: 880, y: ly, fill: C.muted, 'font-size': 13, 'text-anchor': 'end',
        'font-variant-numeric': 'tabular-nums',
      }, (sl.value || 0) + '  ·  ' + pct));
      ly += 30;
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
    drawDotRows: drawDotRows,
    drawShares: drawShares,
    drawBars: drawBars,
    drawScatter: drawScatter,
    drawLine: drawLine,
    drawGroupedBars: drawGroupedBars,
    drawRadar: drawRadar,
    drawStackedBars: drawStackedBars,
    drawPie: drawPie,
    legendRow: legendRow,
    dataTable: dataTable,
  };
})();
