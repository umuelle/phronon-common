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


# ── Language twins (FL-089 follow-up, 6 October 2026) ────────────────────────
#
# Layoff, Whiteout and Polarity Profiler serve every participant page twice:
# `/x` in English and `/{lang}/x` in each other language they speak. Each tool
# wrote the twins by hand (about 650 lines between them), each with its own
# copies of the language check, the prefix and the `/en/x -> /x` redirect, and
# three different rules for when that redirect applies. Whiteout's twins also
# re-declared every form field by hand, and a field added to a page but not to
# its twin answered 500 in German for four days.
#
# One rule now, the strictest of the three: `/en/x` redirects to `/x` (301,
# query kept) for GET and HEAD only, because a redirected POST loses its body;
# a page whose link carries a token (`keep_prefix`) is never redirected, because
# some mail gateways drop the query string on a redirect and the token IS the
# query string; an unknown language is a 404. The twin's endpoint is the base
# handler itself, so FastAPI binds the same form and query fields to both.

def lang_prefix(lang: str, locales, canonical: str = "en") -> str:
    """The URL prefix for `lang`: '' for the canonical language and for any
    language the tool does not speak, '/de', ... for the others. `lang` often
    arrives unchecked from a query string; a value like '/evil.example' used
    to become a protocol-relative redirect (Whiteout and Polarity Profiler,
    fixed 6 October 2026), so nothing outside `locales` ever becomes a prefix."""
    return f"/{lang}" if lang in locales and lang != canonical else ""


def locale_prefixes(locales) -> tuple:
    """Every prefix a request may arrive with: '' and '/<lang>' for each
    language, the canonical one included (`/en/x` is served for a POST). For
    per-path lists such as rate-limit rules, which match literally."""
    return ("",) + tuple(f"/{lang}" for lang in locales)


def add_language_twins(router, locales, paths, *, keep_prefix=(), canonical: str = "en") -> list:
    """Register `/{lang}` + path for each listed route of `router`, in the
    order the routes were registered, appended to `router` (call it at the
    bottom of the module, after the base routes). Returns the twin paths.

    A twin answers with the base handler: `lang` comes from the path, every
    other field binds as on the base. `/en/x` redirects to `/x` for GET/HEAD
    unless x is in `keep_prefix`; a language outside `locales` is a 404.
    Refuses (ValueError) a listed path with no route, and a twin that exists.
    """
    from fastapi.routing import APIRoute

    locales = tuple(locales)
    keep = frozenset(keep_prefix)
    wanted = list(dict.fromkeys(paths))
    bases = [r for r in list(router.routes) if isinstance(r, APIRoute) and r.path in wanted]
    missing = [p for p in wanted if p not in {r.path for r in bases}]
    if missing:
        raise ValueError(f"add_language_twins: no route at {missing}")
    existing = {r.path for r in router.routes if isinstance(r, APIRoute)}
    made = []
    for base in bases:
        twin = "/{lang}" + ("" if base.path == "/" else base.path)
        if twin in existing:
            raise ValueError(f"add_language_twins: {twin} already exists (a hand-written twin?)")
        router.add_api_route(
            twin, base.endpoint, methods=sorted(base.methods), name=f"{base.name}_lang",
            response_class=base.response_class, status_code=base.status_code,
            dependencies=list(base.dependencies), include_in_schema=base.include_in_schema,
            route_class_override=_twin_route_class(locales, canonical, base.path in keep))
        made.append(twin)
    return made


def _twin_route_class(locales, canonical, keep_prefix):
    from fastapi import HTTPException
    from fastapi.routing import APIRoute
    from starlette.responses import RedirectResponse

    from starlette.routing import Match

    class LanguageTwin(APIRoute):
        def matches(self, scope):
            # A first segment that is no language of this tool is no match, so
            # routing goes on to the routes after this one. Answering 404 here
            # shadowed every later path of the same shape: Polarity Profiler's
            # /{lang}/report/{token} took /withdraw/report/<x> (7 October 2026).
            match, child = super().matches(scope)
            if match != Match.NONE:
                lang = child.get("path_params", {}).get("lang", "")
                if lang not in locales and lang != canonical:
                    return Match.NONE, {}
            return match, child

        def get_route_handler(self):
            inner = super().get_route_handler()

            async def handler(request):
                lang = request.path_params.get("lang", "")
                if lang == canonical and not keep_prefix and request.method in ("GET", "HEAD"):
                    tail = request.url.path[len(lang) + 1:] or "/"
                    query = request.url.query
                    return RedirectResponse(tail + ("?" + query if query else ""), status_code=301)
                if lang not in locales:
                    raise HTTPException(status_code=404)
                return await inner(request)
            return handler

    return LanguageTwin


def guard_query_lang(router, locales, paths=None):
    """Answer 404 when a route's `?lang=` names a language outside `locales`.

    A base page takes `lang` as an optional query parameter (FastAPI exposes
    the handler's `lang` argument that way), and nothing checked it: a value
    like '/evil.example' reached redirects and file names. Applies to every
    route of `router` (or the listed paths), before its handler runs.

    It wraps the route's own `get_route_handler`: FastAPI 0.139 builds the
    handler from it on every request that reaches the route through an
    included router, so replacing `route.app` alone would check nothing."""
    from fastapi import HTTPException
    from fastapi.routing import APIRoute, request_response

    locales = frozenset(locales)
    chosen = None if paths is None else frozenset(paths)
    for route in router.routes:
        if not isinstance(route, APIRoute) or (chosen is not None and route.path not in chosen):
            continue

        def guarded_handler(_build=route.get_route_handler):
            inner = _build()

            async def handler(request):
                if any(v not in locales for v in request.query_params.getlist("lang")):
                    raise HTTPException(status_code=404)
                return await inner(request)
            return handler

        route.get_route_handler = guarded_handler
        route.app = request_response(guarded_handler())
    return router
