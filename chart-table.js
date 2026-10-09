/* Accessible data table for every Chart.js chart — Phronon fleet (FL-012).
 *
 * WHY IT IS DERIVED, NOT HAND-WRITTEN
 * There are 61 charts across five tools. A table typed out beside each one is
 * 61 chances to disagree with the chart it describes — and a data table that
 * quietly reports the wrong numbers is worse than none, because a screen reader
 * user has no way to tell. This reads `chart.data` from the live Chart
 * instance, so the table IS the chart's data.
 *
 * WHY IT IS A PLUGIN AND NOT A SWEEP  (the first version got this wrong)
 * The first version walked the DOM a few times after load and gave up after
 * ~3s. Two things broke, both found on a real results page and neither
 * visible on a test page:
 *
 *   * Layoff's "Other Classes" series is created as `new Array(n).fill(null)`
 *     and filled in by a later fetch. The sweep captured the nulls, so the
 *     chart drew bars while the table showed nothing but em dashes — exactly
 *     the silent disagreement this file exists to prevent.
 *   * The aggregate serial-position chart is CONSTRUCTED inside a fetch
 *     callback, long after the sweep had stopped looking. It got no table.
 *
 * Registering a Chart.js plugin fixes both: `afterUpdate` fires when a chart is
 * created AND every time its data changes, so the table is rebuilt from
 * whatever the chart currently holds. It must therefore be loaded WITHOUT
 * `defer`, immediately after Chart.js, so the plugin exists before any inline
 * script constructs a chart.
 *
 * NUMBERS ARE ROUNDED TO TWO DECIMALS (owner, 15 August 2026). A mean printed
 * as 2.769230769230769 is fake precision: it states a certainty the underlying
 * count of participants cannot support, and it is unreadable. Two decimals
 * always, including on whole numbers, so a column reads as one column.
 *
 * PER-CHART OPTIONS, set on the <canvas>:
 *   data-no-table          — skip (Whiteout's SVG charts ship their own)
 *   data-table-unit="%"    — suffix every value, so 100 reads as 100.00%
 *   data-table-decimals="0"— override the two-decimal default
 */
(function () {
  "use strict";

  var SUMMARY = "Data table";

  function decimalsFor(canvas) {
    var raw = canvas.getAttribute("data-table-decimals");
    var n = raw === null ? 2 : parseInt(raw, 10);
    return isFinite(n) && n >= 0 ? n : 2;
  }

  function captionFor(canvas) {
    var label = canvas.getAttribute("aria-label") || "";
    if (!label && canvas.getAttribute("aria-labelledby")) {
      var el = document.getElementById(canvas.getAttribute("aria-labelledby"));
      if (el) label = el.textContent || "";
    }
    return label.replace(/^Chart:\s*/i, "").trim() || "Chart data";
  }

  /* A cell must say something true for every shape Chart.js allows: a number,
     null for a gap, or a {x,y} point. "null" and "[object Object]" are not
     numbers a person can read. */
  function num(value, decimals, unit) {
    if (value === null || value === undefined || value === "") return "—";
    var n = typeof value === "number" ? value : parseFloat(value);
    if (!isFinite(n)) return String(value);
    return n.toFixed(decimals) + (unit || "");
  }

  function axisTitle(chart, axis, fallback) {
    try {
      var sc = chart.options.scales[axis];
      var t = sc && sc.title && sc.title.text;
      if (t) return String(t);
    } catch (e) { /* no scales (pie, doughnut) */ }
    return fallback;
  }

  /* Scatter and bubble carry TWO measures per point, so a single value column
     throws half the data away — which is what the first version did to the
     employee-assessment chart, leaving a meaningless "Series 1" of y values. */
  function isPointSeries(datasets) {
    return datasets.some(function (d) {
      var first = (d.data || [])[0];
      return first && typeof first === "object" && "x" in first;
    });
  }

  function buildTable(chart, canvas) {
    var data = chart.data || {};
    var datasets = (data.datasets || []).filter(Boolean);
    var labels = data.labels || [];
    if (!datasets.length) return null;

    var decimals = decimalsFor(canvas);
    var unit = canvas.getAttribute("data-table-unit") || "";
    var points = isPointSeries(datasets);

    var rowCount = labels.length || Math.max.apply(null, datasets.map(function (d) {
      return (d.data || []).length;
    }));
    if (!rowCount || !isFinite(rowCount)) return null;

    var table = document.createElement("table");
    table.className = "chart-data-table";
    var caption = document.createElement("caption");
    caption.textContent = captionFor(canvas);
    table.appendChild(caption);

    var headers = [];
    if (points) {
      var xName = axisTitle(chart, "x", "x");
      var yName = axisTitle(chart, "y", "y");
      datasets.forEach(function (d, i) {
        var prefix = datasets.length > 1 ? (d.label || "Series " + (i + 1)) + " — " : "";
        headers.push(prefix + xName, prefix + yName);
      });
    } else {
      datasets.forEach(function (d, i) {
        /* A pie or a single-series bar often carries no dataset label, and
           "Series 1" tells the reader nothing the caption has not already
           said. */
        headers.push(d.label || (datasets.length === 1 ? "Value" : "Series " + (i + 1)));
      });
    }

    var thead = document.createElement("thead");
    var hrow = document.createElement("tr");
    var corner = document.createElement("th");
    corner.scope = "col";
    corner.textContent = labels.length ? "" : "#";
    hrow.appendChild(corner);
    headers.forEach(function (h) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = h;
      hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    for (var r = 0; r < rowCount; r++) {
      var tr = document.createElement("tr");
      var rh = document.createElement("th");
      rh.scope = "row";
      rh.textContent = labels.length ? String(labels[r]) : String(r + 1);
      tr.appendChild(rh);
      datasets.forEach(function (d) {
        var v = (d.data || [])[r];
        if (points) {
          var td1 = document.createElement("td");
          var td2 = document.createElement("td");
          td1.textContent = v && typeof v === "object" ? num(v.x, decimals, unit) : "—";
          td2.textContent = v && typeof v === "object" ? num(v.y, decimals, unit) : "—";
          tr.appendChild(td1); tr.appendChild(td2);
        } else {
          var td = document.createElement("td");
          td.textContent = num(v && typeof v === "object" && "y" in v ? v.y : v, decimals, unit);
          tr.appendChild(td);
        }
      });
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
  }

  function fingerprint(chart) {
    try {
      return JSON.stringify({
        l: chart.data.labels,
        d: (chart.data.datasets || []).map(function (s) { return [s.label, s.data]; })
      });
    } catch (e) { return String(Math.random()); }
  }

  function render(chart) {
    var canvas = chart && chart.canvas;
    if (!canvas || canvas.hasAttribute("data-no-table")) return;

    /* afterUpdate also fires on resize, and rebuilding the DOM on every
       resize frame would be wasteful — so only rebuild when the numbers
       actually changed. */
    var print = fingerprint(chart);
    if (canvas.dataset.tablePrint === print) return;
    canvas.dataset.tablePrint = print;

    var table = buildTable(chart, canvas);
    var box = canvas.parentNode && canvas.parentNode.querySelector
      ? document.getElementById(canvas.id ? "chart-data-" + canvas.id : "")
      : null;

    if (!table) { if (box) box.remove(); return; }

    if (!box) {
      box = document.createElement("details");
      box.className = "chart-data";
      if (canvas.id) box.id = "chart-data-" + canvas.id;
      var summary = document.createElement("summary");
      summary.textContent = SUMMARY;
      box.appendChild(summary);
      /* After the canvas's container, so the table does not land inside a
         fixed-height chart box and get clipped. */
      var host = canvas.parentNode || canvas;
      if (host.parentNode) host.parentNode.insertBefore(box, host.nextSibling);
    } else {
      var old = box.querySelector("table");
      if (old) old.remove();
    }
    box.appendChild(table);
  }

  if (window.Chart && window.Chart.register) {
    window.Chart.register({
      id: "phrononDataTable",
      afterUpdate: render,
      afterDestroy: function (chart) {
        var el = chart.canvas && chart.canvas.id
          ? document.getElementById("chart-data-" + chart.canvas.id) : null;
        if (el) el.remove();
      }
    });
  }

  /* Safety net for any chart built before this file ran (it should be loaded
     immediately after Chart.js, without defer, so this normally finds none). */
  function sweep() {
    if (!window.Chart || !window.Chart.getChart) return;
    Array.prototype.forEach.call(document.querySelectorAll("canvas"), function (c) {
      var chart = window.Chart.getChart(c);
      if (chart) render(chart);
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sweep);
  } else {
    sweep();
  }
  window.addEventListener("load", sweep);
  window.phrononChartTables = sweep;
})();
