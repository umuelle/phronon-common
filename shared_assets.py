"""What this package ships to each tool's static/ directory, and to whom.

Each tool is deployed as its own repository, so a shared stylesheet or script
cannot be imported — it has to be COPIED into that tool's `static/`. This module
is the single statement of which masters exist, where each copy belongs, and
which tools carry it. `server-ops/sync_shared_assets.py` reads it to copy and to
report drift; every tool's own suite reads it to fail when its copy has drifted,
so the check runs in the tool's CI as well as at deploy time.

Drift is not hypothetical: design-tokens.css and its nine copies had already
diverged by a blank line before any of this existed, with nothing to notice, and
`bulk-select.js` reached FIVE versions each holding one feature the others never
received.

The masters live beside this file and ship in the wheel (see pyproject's
package-data), so a tool that pip-installs the pinned tag can compare its copy
against the real master rather than against a checkout that may not be there.
"""
from __future__ import annotations

from pathlib import Path

#: Where the masters live — beside this module, in the installed package or in
#: the git checkout, whichever is being imported.
MASTERS = Path(__file__).resolve().parent

#: master filename in phronon_common  ->  path under each tool's repo
ASSETS = {
    "design-tokens.css":       "static/css/phronon-tokens.css",
    "rank-a11y.js":            "static/js/rank-a11y.js",
    "share-card.css":          "static/css/share-card.css",
    "backoffice-nav.css":      "static/css/backoffice-nav.css",
    "backoffice-core.css":     "static/css/backoffice-core.css",
    "two-factor.css":          "static/css/two-factor.css",
    "share-card-download.js":  "static/js/share-card-download.js",
    "actions.js":              "static/js/actions.js",
    "chart-table.js":          "static/js/chart-table.js",
    "svg-charts.js":           "static/js/svg-charts.js",
    "dashboard-table.js":      "static/js/dashboard-table.js",
    "bulk-select.js":          "static/js/bulk-select.js",
    "users-password.js":       "static/js/users-password.js",
}

# Only tools that actually use the asset get a copy. rank-a11y.js is for the
# drag-ranking exercises; share-card.css for anything with a join/share page.
# The Phronon hub has no participant flow, so it takes neither — and it does not
# reference design-tokens.css either, so it is excluded from all three.
_TOOLS_WITH_PARTICIPANTS = {
    "ControversyGenerator", "Drawbridge-Drama", "Inequality", "Layoff-Exercise",
    "polarity-profiler", "Moral-mirror", "Orgdesignsim", "Whiteout",
}
ONLY_FOR = {
    # Layoff-Exercise is deliberately excluded from design-tokens.css. The master
    # carries an @font-face block for self-hosted Source Serif 4 / Source Sans 3
    # under clean filenames; Layoff uses Inter instead, loaded from its own
    # static/vendor/fonts/fonts.css with Google's hashed filenames. Syncing the
    # master onto it adds ten @font-face rules pointing at files Layoff does not
    # have — ten 404s per page load and no visual gain. Its copy looking "52 lines
    # behind" is correct, not drift.
    "design-tokens.css": _TOOLS_WITH_PARTICIPANTS - {"Layoff-Exercise"},
    "rank-a11y.js": {"Layoff-Exercise", "Whiteout"},
    "share-card.css": _TOOLS_WITH_PARTICIPANTS,
    # "Download JPG" on the join/share card. Goes wherever share-card.css goes;
    # each of those templates also loads static/vendor/html2canvas-1.4.1.min.js.
    "share-card-download.js": _TOOLS_WITH_PARTICIPANTS,
    # The educator backoffice nav bar. Every teaching tool has one; the hub's
    # admin area has its own layout and is not part of this.
    "backoffice-nav.css": _TOOLS_WITH_PARTICIPANTS,
    # Core backoffice typography (H3½): the fleet reference look for the
    # shared bo-* vocabulary. Same audience as the nav sheet.
    "backoffice-core.css": _TOOLS_WITH_PARTICIPANTS,
    "two-factor.css": _TOOLS_WITH_PARTICIPANTS,
    # The backoffice bulk-action bar. It had drifted into FIVE versions by
    # 4 September 2026 — the base engine, Whiteout's data-bulk-bar auto-init,
    # Moral Mirror's GET/field-name support and Layoff's data-bulk-confirm with
    # its {n} substitution — each holding one real feature the others never
    # received. The master is the union; every addition defaults to what the
    # base engine already did, and the auto-init finds nothing in the five tools
    # that bootstrap from a template <script> instead.
    "bulk-select.js": _TOOLS_WITH_PARTICIPANTS,
    # Show/hide + generate on the educator password fields. Eight copies, one
    # of which differed by a trailing comment.
    "users-password.js": _TOOLS_WITH_PARTICIPANTS,
    # FL-012: derives an accessible data table from each Chart.js chart's own
    # data — the Chart.js-era companion. An FL-027-ported page builds its table
    # in the engine instead (P.dataTable), so a fully ported tool drops this
    # file. Down to polarity-profiler, the last tool still drawing with Chart.js;
    # delete this entry when PP lands. Layoff dropped it on 26 August with its
    # aggregate page, along with the Chart.js and datalabels bundles.
    "chart-table.js": {"polarity-profiler"},
    # FL-027 (25 August 2026): the fleet chart engine, extracted from
    # Whiteout's session-charts.js. Eight of the nine are on it — Whiteout
    # (the source), Layoff, Drawbridge, Inequality, Controversy Generator and
    # Moral Mirror draw with it. OrgDesignSim is deliberately NOT here: its
    # fairness scatter is server-rendered SVG that works with JS off, and it
    # takes the shared palette through design-tokens.css, so a copy of the
    # engine would be 1,200 unused lines. Chart.js is
    # not gone yet: polarity-profiler is wholly on it, and Layoff's cross-class
    # aggregate page still is. The Phronon hub draws nothing.
    "svg-charts.js": {"Whiteout", "Layoff-Exercise", "Drawbridge-Drama",
                      "Inequality", "ControversyGenerator", "Moral-mirror"},
    # The delegated-actions dispatcher (FL-017, 13 August 2026). Six copies had
    # drifted apart while the header called each of them "canonical" and nothing
    # tracked them — which is how a delete confirmation sat dead for months in
    # Controversy Generator. The master is the union of what the copies did;
    # anything tool-specific moved to that tool's own static/js/actions-local.js,
    # loaded after this file, so this one can stay byte-identical everywhere.
    # Moral Mirror, the Phronon hub and Whiteout are deliberately excluded: they
    # use small per-feature scripts (confirm-submit.js, bulk-select.js) instead
    # of a dispatcher, which is a different architecture, not a drifted copy.
    "actions.js": _TOOLS_WITH_PARTICIPANTS - {"Moral-mirror", "Whiteout"},
    # FL-030 (26 August 2026): search + sort + pagination for backoffice
    # tables. Eight tools, eight versions — five 94–99.5% identical to
    # Layoff's, Whiteout's the same logic reformatted, Moral Mirror's the same
    # API written more tersely. The only real difference was the block of
    # initSortableTable(...) calls at the FOOT of each file, which is
    # configuration, not code: it now lives in each tool's own
    # dashboard-table-local.js, the actions.js/actions-local.js pattern.
    # Every teaching tool has backoffice tables; the hub's admin area does not
    # use this vocabulary.
    "dashboard-table.js": _TOOLS_WITH_PARTICIPANTS,
}

TOOLS = [
    "ControversyGenerator", "Drawbridge-Drama", "Inequality", "Layoff-Exercise",
    "polarity-profiler", "Moral-mirror", "Orgdesignsim", "Phronon", "Whiteout",
]

def master_path(asset: str) -> Path:
    """The master file for `asset`. Raises KeyError for an unknown name."""
    if asset not in ASSETS:
        raise KeyError(f"{asset!r} is not a shared asset. Known: {', '.join(ASSETS)}")
    return MASTERS / asset


def assets_for(tool: str) -> list[str]:
    """The masters `tool` (a repository directory name) should carry."""
    return [a for a in ASSETS
            if ONLY_FOR.get(a) is None or tool in ONLY_FOR[a]]


def drifted(tool: str, tool_dir: Path) -> list[str]:
    """Assets whose copy under `tool_dir` is missing or differs from the master.

    Returns a list of human-readable reasons — empty when every copy matches.
    """
    out = []
    for asset in assets_for(tool):
        master = master_path(asset)
        if not master.is_file():
            out.append(f"{asset}: no master in phronon_common")
            continue
        dest = Path(tool_dir) / ASSETS[asset]
        if not dest.exists():
            out.append(f"{ASSETS[asset]}: missing (master {asset})")
        elif dest.read_bytes() != master.read_bytes():
            out.append(f"{ASSETS[asset]}: differs from master {asset}")
    return out
