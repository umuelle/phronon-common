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
    "svg-charts.js":           "static/js/svg-charts.js",
    "dashboard-table.js":      "static/js/dashboard-table.js",
    "bulk-select.js":          "static/js/bulk-select.js",
    "users-password.js":       "static/js/users-password.js",
    "recovery-codes.js":       "static/js/recovery-codes.js",
    "passkeys.js":             "static/js/passkeys.js",
    "country-other.js":        "static/js/country-other.js",
    "flow-preview.js":         "static/js/flow-preview.js",
    "flow-preview-frame.js":   "static/js/flow-preview-frame.js",
    "pdf-report.js":           "static/js/pdf-report.js",
    "messages.js":             "static/js/messages.js",
    "messages.css":            "static/css/messages.css",
    "tabs.js":                 "static/js/tabs.js",
}

# WHY A TOOL CARRIES FEWER (the lists themselves are in each ops/tool.json).
# Only a tool that uses an asset gets a copy.
#   * The Phronon hub has no participant flow: it carries what the account
#     kit's pages and its backoffice need (the tokens, the two backoffice
#     sheets, two-factor.css, actions.js, recovery-codes.js and passkeys.js;
#     since PH-007, 19 November 2026).
#   * design-tokens.css: not Layoff. The master carries @font-face rules for
#     self-hosted Source Serif 4 / Source Sans 3; Layoff uses Inter from its own
#     static/vendor/fonts/fonts.css, so the master would add ten 404s per page.
#   * rank-a11y.js: only the drag-ranking exercises, Layoff and Whiteout.
#   * svg-charts.js (the fleet chart engine, FL-027): not OrgDesignSim, whose
#     fairness scatter is server-rendered SVG that works with JS off. No tool
#     uses Chart.js any more, and its table helper chart-table.js was retired
#     in 1.107.0 (TO DO FL-098).
#   * actions.js (the delegated-actions dispatcher, FL-017): not Moral Mirror
#     or Whiteout, which use small per-feature scripts (confirm-submit.js,
#     bulk-select.js), a different design rather than a drifted copy.
#     Tool-specific actions live in each tool's actions-local.js, and
#     dashboard-table.js's per-tool setup in dashboard-table-local.js, so the
#     masters stay byte-identical everywhere.
#   * country-other.js (the box behind "Other / not listed", 14 October 2026):
#     only the tools that ask a country, Drawbridge, Inequality, Layoff, Moral
#     Mirror, Polarity Profiler and Whiteout; each adopts it with the shared
#     scheme (demographics.py).
#   * flow-preview.js and flow-preview-frame.js (the educator's preview of the
#     participant screens, FL-041): only the tools that have the preview,
#     Drawbridge, Inequality, Moral Mirror and Whiteout. Copies until
#     26 October 2026 (TO DO FL-098 point 3): flow-preview.js was identical in
#     all four, and the frame script's two versions differed only in comments.
#   * pdf-report.js (the PDF report builder, FL-098, 26 October 2026): only
#     the three tools that make a PDF in the browser, Layoff, Polarity
#     Profiler and Whiteout. Each keeps its own cover and page design.
#   * messages.js and messages.css (messages inside a session, 22 November
#     2026, TO DO FL-160): only the tools that let their teams write to each
#     other, Peak Season so far (phronon_common.messages).
#   * tabs.js (the tab strip, 22 November 2026, TO DO FL-161): the seven tools
#     with tabbed pages, Controversy Generator, Drawbridge, Layoff, Moral
#     Mirror, Peak Season, Polarity Profiler and Whiteout.
#
# LOOK SHARED, ARE NOT (checked 26 October 2026, FL-098 point 3): Polarity
# Profiler's and Whiteout's lang-switcher.js, and Moral Mirror's and
# Whiteout's confirm-submit.js, share a name but not their code; each is the
# tool's own script for its own pages.


def master_path(asset: str) -> Path:
    """The master file for `asset`. Raises KeyError for an unknown name."""
    if asset not in ASSETS:
        raise KeyError(f"{asset!r} is not a shared asset. Known: {', '.join(ASSETS)}")
    return MASTERS / asset


def master_for_copy(copy_path: str) -> Path:
    """The master behind the place a tool's copy had, e.g. "static/js/passkeys.js".
    For a tool's tests since the tools take the files from the release: what
    read the copy reads the master. Raises KeyError for any other path."""
    wanted = copy_path.lstrip("/")
    for asset, copy in ASSETS.items():
        if copy == wanted:
            return master_path(asset)
    raise KeyError(f"{copy_path!r} is not the place of a shared asset's copy")
