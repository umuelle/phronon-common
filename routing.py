"""HEAD for read-only GET routes: one rule, one implementation, for every tool.

WHY HEAD. Corporate mail scanners and web proxies (Outlook SafeLinks, Zscaler,
FortiGate) probe a link with HEAD before letting a person through. FastAPI
registers GET only, so those probes got 405 and some gateways flagged the link
as broken. Every tool therefore lets its GET routes answer HEAD.

WHY NOT EVERY GET. A HEAD probe runs the handler and throws the body away, so a
GET that WRITES performs its write with nobody looking at the page. Whiteout
learned this when a scanner's HEAD spent a participant's one-time resume link.
Those routes are named in `unsafe_paths` and keep GET only;
`phronon_common.testing.head_safety` derives the set of writing GETs from the
code and fails a tool whose HEAD routes and writing routes overlap, in either
direction.

WHY HERE (5 October 2026). Eight tools each carried their own loop, one of them
with an exclusion list. A loop over `app.routes` also stops reaching routes the
moment they move into an included router (FastAPI 0.139 keeps one node per
router), so a tool that splits its `app.py` would silently lose HEAD. Apply it
to each router BEFORE `include_router`, and to the app for the routes the app
itself declares.
"""
from __future__ import annotations


def answer_head(routes_owner, unsafe_paths=frozenset()):
    """Let every GET route of `routes_owner` (an APIRouter, or the app for its
    own routes) answer HEAD too, except the paths in `unsafe_paths`: GETs that
    write. Returns `routes_owner`, so it can wrap an `include_router` argument."""
    from fastapi.routing import APIRoute

    unsafe = frozenset(unsafe_paths)
    for route in routes_owner.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods and route.path not in unsafe:
            route.methods.add("HEAD")
    return routes_owner
