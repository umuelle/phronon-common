"""What this package ships to each tool's static/ directory.

Each tool is deployed as its own repository, so a shared stylesheet or script
cannot be imported — it has to be COPIED into that tool's `static/`. This module
is the single statement of which masters exist and where each copy belongs.
WHICH of them a tool carries is the tool's own `ops/tool.json`
(operations.shared_assets, since 1.78.0; TO DO FL-080 moved it there).
`server-ops/sync_shared_assets.py` reads both to copy and to report drift; every
tool's own suite reads both to fail when its copy has drifted, so the check runs
in the tool's CI as well as at deploy time.

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
    "recovery-codes.js":       "static/js/recovery-codes.js",
    "passkeys.js":             "static/js/passkeys.js",
}

# WHY A TOOL CARRIES FEWER (the lists themselves are in each ops/tool.json).
# Only a tool that uses an asset gets a copy.
#   * The Phronon hub has no participant flow and no educator backoffice
#     vocabulary: it carries only recovery-codes.js and passkeys.js, which all
#     nine need for two-factor and passkeys.
#   * design-tokens.css: not Layoff. The master carries @font-face rules for
#     self-hosted Source Serif 4 / Source Sans 3; Layoff uses Inter from its own
#     static/vendor/fonts/fonts.css, so the master would add ten 404s per page.
#   * rank-a11y.js: only the drag-ranking exercises, Layoff and Whiteout.
#   * svg-charts.js (the fleet chart engine, FL-027): not OrgDesignSim, whose
#     fairness scatter is server-rendered SVG that works with JS off; not
#     Polarity Profiler, still on Chart.js.
#   * chart-table.js (accessible tables for Chart.js charts, FL-012): only
#     Polarity Profiler, the last tool on Chart.js; it goes when PP is ported.
#   * actions.js (the delegated-actions dispatcher, FL-017): not Moral Mirror
#     or Whiteout, which use small per-feature scripts (confirm-submit.js,
#     bulk-select.js), a different design rather than a drifted copy.
#     Tool-specific actions live in each tool's actions-local.js, and
#     dashboard-table.js's per-tool setup in dashboard-table-local.js, so the
#     masters stay byte-identical everywhere.


def master_path(asset: str) -> Path:
    """The master file for `asset`. Raises KeyError for an unknown name."""
    if asset not in ASSETS:
        raise KeyError(f"{asset!r} is not a shared asset. Known: {', '.join(ASSETS)}")
    return MASTERS / asset
