/* Accessible data table for every Chart.js chart — Phronon fleet (FL-012).
 *
 * WHY IT IS DERIVED, NOT HAND-WRITTEN
 * There are 61 charts across five tools. A table typed out beside each one is
 * 61 chances to disagree with the chart it describes — and a data table that
 * quietly reports last month's numbers is worse than none, because a screen
 * reader user has no way to tell. This reads `chart.data` from the live Chart
 * instance, so the table IS the chart's data by construction. Change the chart
 * and the table changes with it.
 *
 * WHAT IT PRODUCES
 * A <details> after each canvas: a summary the eye can skip, a real <table>
 * with a <caption> taken from the canvas's own aria-label, one row per label
 * and one column per dataset. Sighted users get a chart; everyone gets numbers.
 *
 * WCAG 1.1.1: a chart is a non-text object whose information must be available
 * as text. The existing aria-label names what a chart SHOWS ("Average scores by
 * style"); it does not carry the values, which is what an educator actually
 * needs to read out in class.
 *
 * OPT OUT with data-no-table on the canvas — Whiteout's hand-drawn SVG charts
 * already ship their own tables and are not Chart.js at all.
 */
(function () {
  "use strict";

  var LABEL = "Data table";

  function textFor(canvas) {
    var label = canvas.getAttribute("aria-label") || "";
    if (!label && canvas.getAttribute("aria-labelledby")) {
      var el = document.getElementById(canvas.getAttribute("aria-labelledby"));
      if (el) label = el.textContent || "";
    }
    return label.replace(/^Chart:\s*/i, "").trim();
  }

  /* Chart.js stores numbers, {x,y} points, or null for a gap. A cell must say
     something true in each case — "null" or "[object Object]" is not a number
     a person can read. */
  function cell(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") {
      if ("y" in value) return String(value.y);
      if ("v" in value) return String(value.v);
      return JSON.stringify(value);
    }
    return String(value);
  }

  function buildTable(chart, canvas) {
    var data = chart.data || {};
    var datasets = (data.datasets || []).filter(function (d) { return d; });
    var labels = data.labels || [];
    if (!datasets.length) return null;

    /* A chart with no category labels (scatter, or a single unlabelled series)
       still has rows — number them rather than emitting a blank first column. */
    var rowCount = labels.length ||
      Math.max.apply(null, datasets.map(function (d) { return (d.data || []).length; }));
    if (!rowCount || !isFinite(rowCount)) return null;

    var table = document.createElement("table");
    table.className = "chart-data-table";

    var caption = document.createElement("caption");
    caption.textContent = textFor(canvas) || "Chart data";
    table.appendChild(caption);

    var thead = document.createElement("thead");
    var hrow = document.createElement("tr");
    var corner = document.createElement("th");
    corner.scope = "col";
    corner.textContent = labels.length ? "" : "#";
    hrow.appendChild(corner);
    datasets.forEach(function (d, i) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = d.label || ("Series " + (i + 1));
      hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    for (var r = 0; r < rowCount; r++) {
      var tr = document.createElement("tr");
      var th = document.createElement("th");
      th.scope = "row";
      th.textContent = labels.length ? cell(labels[r]) : String(r + 1);
      tr.appendChild(th);
      datasets.forEach(function (d) {
        var td = document.createElement("td");
        td.textContent = cell((d.data || [])[r]);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
  }

  function attach(canvas) {
    if (canvas.hasAttribute("data-no-table")) return true;
    if (canvas.dataset.tableAttached === "1") return true;
    if (!window.Chart || !window.Chart.getChart) return false;

    var chart = window.Chart.getChart(canvas);
    if (!chart) return false;                 // not built yet — try again later

    var table = buildTable(chart, canvas);
    if (!table) { canvas.dataset.tableAttached = "1"; return true; }

    var box = document.createElement("details");
    box.className = "chart-data";
    var summary = document.createElement("summary");
    summary.textContent = LABEL;
    box.appendChild(summary);
    box.appendChild(table);

    /* After the canvas's own container where there is one, so the table does
       not land inside a fixed-height chart box and get clipped. */
    var anchor = canvas.parentNode;
    var host = (anchor && anchor.nextSibling !== undefined) ? anchor : canvas;
    if (host.parentNode) host.parentNode.insertBefore(box, host.nextSibling);
    canvas.dataset.tableAttached = "1";
    return true;
  }

  /* Charts are created by inline scripts, by DOMContentLoaded handlers, and in
     at least one place after a fetch. So this retries briefly rather than
     assuming everything exists the moment it runs, and gives up quietly
     instead of spinning forever. */
  function sweep(attemptsLeft) {
    var canvases = document.querySelectorAll("canvas");
    var pending = 0;
    Array.prototype.forEach.call(canvases, function (c) {
      if (!attach(c)) pending++;
    });
    if (pending && attemptsLeft > 0) {
      setTimeout(function () { sweep(attemptsLeft - 1); }, 250);
    }
  }

  function start() { sweep(12); }            // ~3s, then stop

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
  window.addEventListener("load", function () { sweep(4); });

  /* For charts built later (a filter change, a tab): re-run by hand. */
  window.phrononChartTables = function () { sweep(4); };
})();
