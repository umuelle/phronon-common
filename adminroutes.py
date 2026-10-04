"""Which admin-only routes are not actually gated on the admin role.

WHY THIS EXISTS. On 9 August 2026 Whiteout's `GET /backoffice/users` was found
to check only that the caller was logged in. Every WRITE on that page was
admin-only, and the template hid the checkboxes and the action column from an
educator — so the roles had been thought about. What was missing was the gate on
the READ: any logged-in educator got the whole staff directory (display name,
e-mail, role, active flag, last login, created date) with the buttons stripped
out, and the navigation linked them to it.

Two things made it survivable for weeks:

  1. **Hiding the controls is not withholding the data.** The query runs before
     the template does, so a `{% if role == 'admin' %}` around the buttons
     changes what is drawn, not what was fetched. This is the same shape as the
     teaching material that sat behind a login-checked route *and* under a
     public `/static` mount (README §3) — a gate that governs the wrong layer.

  2. **Nothing tested role separation.** The fleet-baseline auth test asks "does
     an ANONYMOUS request get bounced?", and it did. No test anywhere asked
     whether one logged-in role could reach another's pages, so every deploy was
     green.

This module closes (2) for the whole fleet in one implementation, because the
fleet's own rule is that a job with nine private copies is a job where a fix
applied to one silently misses the rest.

DELIBERATELY SOURCE-LEVEL. It reads `app.py` and never starts the app, so it
needs no database, no cookies and no live server — which means it CANNOT skip.
The tools whose route tests are mocked locally (Polarity Profiler, Inequality) would otherwise
have no coverage of this at all, and a skipped test is indistinguishable from a
passing one in a green run. Same reasoning as `tests/test_join_codes.py`.

DELIBERATELY SUBSTRING, NOT REGEX. A guard is named by the exact text a tool
writes, e.g. `sess['fac_role'] != 'admin'`. Finding this bug involved two
regexes that were too clever — one matched `role, is_active … FROM admins` as a
role check (false positive), the other missed `sess['fac_role'] != 'admin'`
because of the bracket (false negative). A plain substring is dull and
predictable, which is what a security check should be.

TWO WAYS IN (4 October 2026, FL-082). The source-level check reads ONE file,
`app.py`. That was the whole app while every route lived there; it stops
being true the day a tool moves routes into router modules, and a route that
moves out of `app.py` does not fail the check — it silently leaves it, which
is the failure mode this module exists to prevent. `assert_live_admin_routes_
are_gated` asks the RUNNING app instead: every route it actually dispatches
(routers included, prefixes applied), whichever file the handler lives in.
"Gated" means the same thing in both — the guard text in the handler, not
narrowed by an `and` — plus, for the live check only, a guard DEPENDENCY the
tool names (a `Depends(require_admin)` on the route or its router). The
source-level functions stay for the tools whose routes are all in `app.py`.
"""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
from typing import Callable, Iterable, NamedTuple


class Route(NamedTuple):
    method: str
    path: str
    handler: str
    lineno: int

    def __str__(self) -> str:  # what a failing test prints
        return f'{self.method} {self.path}  ({self.handler}, app.py:{self.lineno})'


def _decorated_routes(node: ast.AST) -> list[tuple[str, str]]:
    """(METHOD, path) for each web-framework decorator on a function."""
    found = []
    for dec in getattr(node, 'decorator_list', []):
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        # @app.get('/x') / @router.post('/x')
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr.upper()
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'ROUTE'):
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant) \
                and isinstance(dec.args[0].value, str):
            found.append((method, dec.args[0].value))
    return found


def admin_routes(source: str, prefixes: Iterable[str]) -> list[tuple[Route, str]]:
    """Every handler whose route path starts with one of `prefixes`.

    Returns (route, handler_source) pairs so a caller can inspect the body.
    """
    prefixes = tuple(prefixes)
    tree = ast.parse(source)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routes = _decorated_routes(node)
        if not routes:
            continue
        body = ast.get_source_segment(source, node) or ''
        for method, path in routes:
            if path.startswith(prefixes):
                out.append((Route(method, path, node.name, node.lineno), body))
    return out


def _guard_is_narrowed(body: str, guard: str) -> bool:
    """True when the tool's guard string sits inside an `and`.

    PRESENCE IS NOT ENFORCEMENT, and that cost a live hole. On 9 August 2026
    Whiteout's `POST /backoffice/users` read

        if sess['fac_role'] != 'admin' and action in ('add', 'delete', …):

    which CONTAINS the role comparison — so a substring check passed it — and
    stops nobody who sends an action outside that list. The handler then
    rendered the whole staff directory to an educator. The GET route beside it
    had been closed the day before; the POST was the same page by another verb.

    The rule is deliberately narrow: **only `and` narrows a guard.** Two
    earlier attempts at this function were too clever and both produced
    confident noise —

      * treating every compound condition as suspect flagged the six tools that
        write `if not admin or admin['role'] != 'ADMIN'`, which is a STRICTER
        guard (it refuses when either holds), not a weaker one;
      * looking for any `if` whose test mentions "admin" flagged Inequality's
        `if user_id == current["id"] and role_val != "ADMIN"` — ordinary
        business logic that happens to name the role, while its actual guard
        lives in an assignment on the line above.

    An over-broad security check is not the safe direction to err in: the fix
    for the noise is to break something. So this asks one question only — is
    the DECLARED guard being ANDed with something that narrows when it fires?
    """
    try:
        tree = ast.parse(body.lstrip())
    except SyntaxError:
        return False        # unparseable: leave the substring result alone
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            segment = ast.get_source_segment(body.lstrip(), node) or ''
            if guard in segment:
                return True
    return False


def unguarded_admin_routes(source: str,
                           prefixes: Iterable[str],
                           guards: Iterable[str],
                           allow: Iterable[str] = ()) -> list[Route]:
    """Admin-area routes whose handler contains none of `guards`.

    `guards` are exact strings the tool writes to enforce the admin role, e.g.
    ``"sess['fac_role'] != 'admin'"`` or ``'require_admin(request)'``. A handler
    is considered gated if ANY of them appears in its source.

    `allow` names handlers that are deliberately reachable by a non-admin — a
    self-service password change under the same path prefix, say. Naming one is
    a decision; leaving one out by accident is the bug this catches.
    """
    guards = tuple(guards)
    allowed = set(allow)
    if not guards:
        raise ValueError('name at least one guard string, or this passes vacuously')
    bad = []
    for route, body in admin_routes(source, prefixes):
        if route.handler in allowed:
            continue
        matched = [g for g in guards if g in body]
        if not matched:
            bad.append(route)
            continue
        # The guard is present — but is it unconditional? A role check ANDed
        # with something else guards only what that something else selects.
        if all(_guard_is_narrowed(body, g) for g in matched):
            bad.append(route)
    return bad


def assert_admin_routes_are_gated(app_py, prefixes, guards, allow=()) -> None:
    """Raise AssertionError naming every ungated admin route. For tests."""
    source = app_py.read_text(encoding='utf-8')
    routes = admin_routes(source, prefixes)
    assert routes, (
        f'no routes found under {list(prefixes)} — the prefixes are wrong, or '
        f'the routes moved. A check that inspects nothing passes vacuously.')
    bad = unguarded_admin_routes(source, prefixes, guards, allow)
    assert not bad, (
        'admin-only routes reachable by any logged-in user:\n  '
        + '\n  '.join(str(r) for r in bad)
        + '\n\nGate the ROUTE, not just the template: the query runs before the '
          'template does, so hiding the buttons still hands over the data.')


# ── The running app (FL-082, 4 October 2026) ────────────────────────────────
# Everything above reads `app.py` as text. Everything below asks the app that
# would serve the request. Lazy imports throughout: this module is not web
# plumbing (tests/test_import_boundaries.py), and the source-level half must
# keep working where FastAPI is not installed.

class AppRoute(NamedTuple):
    """One route the running app dispatches, as the app sees it."""
    path: str                    # the full path, router prefixes applied
    methods: frozenset           # what the router answers, HEAD included
    name: str
    endpoint: Callable
    dependencies: tuple          # every dependency callable, nested ones too


class LiveRoute(NamedTuple):
    methods: str
    path: str
    handler: str
    source: str                  # the file the handler is defined in
    lineno: int

    def __str__(self) -> str:    # what a failing test prints
        return f'{self.methods} {self.path}  ({self.handler}, {self.source}:{self.lineno})'


def _dependency_calls(dependant) -> tuple:
    """Every dependency callable under `dependant`, outermost first."""
    out = []

    def walk(node):
        for dep in getattr(node, 'dependencies', None) or ():
            call = getattr(dep, 'call', None)
            if call is not None:
                out.append(call)
            walk(dep)

    walk(dependant)
    return tuple(out)


def app_routes(app) -> list[AppRoute]:
    """Every APIRoute `app` dispatches, INCLUDING those inside included routers.

    Iterating `app.routes` is not enough on the FastAPI this fleet pins
    (0.139): `include_router()` no longer copies a router's routes onto the
    app, it appends ONE node that holds the router, so a loop over
    `app.routes` that keeps the APIRoutes silently skips every included route
    (the legal pages have been invisible to such loops since the shared legal
    router arrived). `fastapi.routing.iter_route_contexts` is FastAPI's own
    walk through those nodes and returns each route with its EFFECTIVE path,
    methods and dependencies. On an older FastAPI, which copied routes flat,
    the plain loop was already complete.

    Call it on an app that has finished building: the walk fixes the routes'
    effective view (FastAPI caches it until a route is added).
    """
    from fastapi.routing import APIRoute
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:          # FastAPI before the lazy include
        iter_route_contexts = None
    routes = getattr(app, 'routes', app)
    out = []
    if iter_route_contexts is None:
        for r in routes:
            if isinstance(r, APIRoute):
                out.append(AppRoute(r.path, frozenset(r.methods or ()), r.name,
                                    r.endpoint, _dependency_calls(r.dependant)))
        return out
    for ctx in iter_route_contexts(routes):
        if not isinstance(ctx.original_route, APIRoute):
            continue
        out.append(AppRoute(ctx.path, frozenset(ctx.methods or ()), ctx.name,
                            ctx.endpoint or ctx.original_route.endpoint,
                            _dependency_calls(ctx.dependant)))
    return out


def _handler_source(endpoint) -> tuple[str, str, int]:
    """(dedented source, file, first line) of a route's handler.

    ('', '?', 0) when Python cannot show it — a lambda built at runtime, a
    callable object — and the caller then treats the route as UNGATED: a
    handler nobody can read is not one anybody has checked.
    """
    fn = inspect.unwrap(endpoint)
    try:
        lines, lineno = inspect.getsourcelines(fn)
        path = inspect.getsourcefile(fn) or '?'
    except (OSError, TypeError):
        return '', '?', 0
    try:
        shown = os.path.relpath(path)
    except ValueError:           # another drive (Windows): keep it absolute
        shown = path
    if shown.startswith('..'):
        shown = path
    return textwrap.dedent(''.join(lines)), shown, lineno


def live_admin_routes(app, prefixes: Iterable[str]) -> list[tuple[LiveRoute, str, tuple]]:
    """(route, handler_source, dependency_calls) under `prefixes`, from the RUNNING app."""
    prefixes = tuple(prefixes)
    out = []
    for r in app_routes(app):
        if not r.path.startswith(prefixes):
            continue
        body, source, lineno = _handler_source(r.endpoint)
        methods = ', '.join(sorted(r.methods)) or '?'
        handler = getattr(r.endpoint, '__name__', None) or r.name or '?'
        out.append((LiveRoute(methods, r.path, handler, source, lineno), body,
                    r.dependencies))
    return out


def unguarded_live_admin_routes(app,
                                prefixes: Iterable[str],
                                guards: Iterable[str] = (),
                                allow: Iterable[str] = (),
                                guard_dependencies: Iterable[Callable] = ()) -> list[LiveRoute]:
    """Admin-area routes of the running app that nothing gates on the role.

    A route is gated when its handler contains one of `guards` and not every
    guard it contains is narrowed by an `and` (exactly the source-level rule,
    `unguarded_admin_routes`), OR when one of `guard_dependencies` runs before
    it — on the route, its router, or the app. `allow` names handlers that are
    deliberately reachable by a non-admin.
    """
    guards = tuple(guards)
    deps = tuple(guard_dependencies)
    allowed = set(allow)
    if not guards and not deps:
        raise ValueError('name at least one guard string or guard dependency, '
                         'or this passes vacuously')
    bad = []
    for route, body, calls in live_admin_routes(app, prefixes):
        if route.handler in allowed:
            continue
        if deps and any(any(c is d for d in deps) for c in calls):
            continue
        matched = [g for g in guards if g in body]
        if not matched or all(_guard_is_narrowed(body, g) for g in matched):
            bad.append(route)
    return bad


def assert_live_admin_routes_are_gated(app, prefixes, guards=(), allow=(),
                                       guard_dependencies=()) -> None:
    """Raise AssertionError naming every ungated admin route the app serves.

    The live counterpart of `assert_admin_routes_are_gated`: it takes the
    FastAPI app, not a file, so a route counts wherever its handler lives.
    """
    routes = live_admin_routes(app, prefixes)
    assert routes, (
        f'the running app serves no routes under {list(prefixes)} — the prefixes '
        f'are wrong, or the routes moved. A check that inspects nothing passes '
        f'vacuously.')
    bad = unguarded_live_admin_routes(app, prefixes, guards, allow, guard_dependencies)
    assert not bad, (
        'admin-only routes reachable by any logged-in user:\n  '
        + '\n  '.join(str(r) for r in bad)
        + '\n\nGate the ROUTE, not just the template: the query runs before the '
          'template does, so hiding the buttons still hands over the data.')
