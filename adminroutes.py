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
The tools whose route tests are mocked locally (LSR, Inequality) would otherwise
have no coverage of this at all, and a skipped test is indistinguishable from a
passing one in a green run. Same reasoning as `tests/test_join_codes.py`.

DELIBERATELY SUBSTRING, NOT REGEX. A guard is named by the exact text a tool
writes, e.g. `sess['fac_role'] != 'admin'`. Finding this bug involved two
regexes that were too clever — one matched `role, is_active … FROM admins` as a
role check (false positive), the other missed `sess['fac_role'] != 'admin'`
because of the bracket (false negative). A plain substring is dull and
predictable, which is what a security check should be.
"""
from __future__ import annotations

import ast
from typing import Iterable, NamedTuple


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
        if not any(g in body for g in guards):
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
