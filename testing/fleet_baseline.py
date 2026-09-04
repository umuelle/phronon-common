"""Fleet-baseline route and login-flow checks (TO DO H3, 2026-07-30).

The same four checks in every tool, so no suite is thinner than this floor:

1. every parameterless GET route answers without a server error,
2. the login form round-trips like a person uses it (CSRF token included,
   wrong password refused CLEANLY — a 403 here means the token pipeline is
   broken, which is the exact fault that silently broke 2FA enrolment),
3. anonymous visitors are redirected away from every protected page,
4. the security headers are on the page.

On the server (deploy gate, via run_tests.py) these run for real against the
deployment environment. Where the app cannot even be imported — a laptop
without the dependencies, a CI job without a database — the tool's wrapper
skips with an allowed environmental reason; the server run is the
authoritative gate.

Deliberately GET-only and parameterless: on most tools the suite runs against
the production database, so the walk must not guess IDs or touch routes whose
NAME suggests a side effect.

SHARED SINCE 4 SEPTEMBER 2026. All NINE copies — the eight tools and the hub —
were the same file but for three constants: the login path, the login POST
path, and the protected prefixes. Those stay per tool below.

No pytest import here (see phronon_common/testing/__init__.py), which is why
every check RETURNS a skip reason instead of skipping: the tool's wrapper owns
the pytest verbs, and owns them visibly.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

#: Routes whose name or path hints at a side effect stay out of the blind walk.
SIDE_EFFECT_HINTS = ("send", "mail", "export", "download", "withdraw",
                     "logout", "delete", "anonym", "reset")

_CSRF_INPUT = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
_CSRF_INPUT_REVERSED = re.compile(r'value="([^"]+)"\s+name="csrf_token"')


def set_env_fallbacks() -> None:
    """Harmless fallbacks so the import does not die on a machine without a
    real .env; on the server and in CI the real values are already set and
    setdefault changes nothing."""
    os.environ.setdefault("APP_SECRET_KEY", "b" * 64)
    os.environ.setdefault("SECRET_KEY", "b" * 64)
    os.environ.setdefault("DB_HOST", "127.0.0.1")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test")


def strict_here(test_file: Path | str) -> bool:
    """Strict only where the environment is the real one: the server.

    In CI and on laptops the database is a stub or absent, so DB-backed
    failures there are environmental, not behavioural — the deploy gate on the
    server is the authoritative run of this file.
    """
    return str(Path(test_file).resolve()).startswith(("/var/www/", "/opt/"))


def csrf_token(html: str) -> str:
    m = _CSRF_INPUT.search(html) or _CSRF_INPUT_REVERSED.search(html)
    assert m, "no csrf_token input on the login page"
    return m.group(1)


class FleetBaseline:
    """The four checks. A tool subclasses this and supplies the constants.

    Every method returns a skip reason (a string) or None; the wrapper calls
    `pytest.skip` on the string. `fleet_app` and `client` are the tool's own
    fixtures, passed in by its wrapper.
    """

    LOGIN_PATH = "/backoffice/login"
    LOGIN_POST = "/backoffice/login"
    PROTECTED_PREFIXES: tuple = ("/backoffice/",)
    #: The tool sets this from `strict_here(__file__)`.
    STRICT = False

    # ── the walk ────────────────────────────────────────────────────────────
    def walkable_get_routes(self, fleet_app) -> list:
        from fastapi.routing import APIRoute

        routes = []
        for r in fleet_app.app.routes:
            if not isinstance(r, APIRoute) or "GET" not in r.methods:
                continue
            if "{" in r.path:
                continue  # no guessing IDs against a real database
            hint = (r.path + " " + (r.name or "")).lower()
            if any(h in hint for h in SIDE_EFFECT_HINTS):
                continue
            routes.append(r.path)
        return sorted(set(routes))

    def check_every_parameterless_get_route_answers(self, fleet_app, client):
        paths = self.walkable_get_routes(fleet_app)
        assert paths, "route walk found nothing — did the app change its router?"
        broken = []
        for path in paths:
            resp = client.get(path)
            if resp.status_code >= 500:
                broken.append(path + " -> " + str(resp.status_code))
        if broken and not self.STRICT:
            return ("requires the live server environment (DB-backed routes "
                    "answer 5xx against the stubbed database: "
                    + ", ".join(broken) + ")")
        assert not broken, (
            "server error on GET (a page can be broken while every feature test "
            "stays green):\n  " + "\n  ".join(broken)
        )
        return None

    def check_login_flow_refuses_wrong_password_cleanly(self, client):
        page = client.get(self.LOGIN_PATH)
        if page.status_code >= 500 and not self.STRICT:
            return ("requires the live server environment (login page needs "
                    "the database)")
        assert page.status_code == 200, "login page did not render"
        token = csrf_token(page.text)
        resp = client.post(
            self.LOGIN_POST,
            data={"email": "baseline-nobody@phronon.org",
                  "password": "definitely-wrong-password-1234",
                  "csrf_token": token},
            follow_redirects=False,
        )
        assert resp.status_code != 403, (
            "403 on a well-formed login POST — the CSRF token pipeline is broken "
            "(generator and validator no longer bound the same way)."
        )
        if resp.status_code >= 500 and not self.STRICT:
            return ("requires the live server environment (login POST needs "
                    "the database)")
        assert resp.status_code < 500, "server error on the login POST"
        return None

    def check_anonymous_is_kept_out_of_protected_pages(self, fleet_app, client):
        checked = []
        for path in self.walkable_get_routes(fleet_app):
            if not any(path.startswith(p) for p in self.PROTECTED_PREFIXES):
                continue
            if path in (self.LOGIN_PATH, self.LOGIN_POST) \
                    or "login" in path or "password" in path:
                continue
            resp = client.get(path, follow_redirects=False)
            if resp.status_code >= 500 and not self.STRICT:
                return ("requires the live server environment (auth check on "
                        + path + " needs the database)")
            checked.append(path)
            # 3xx to login, 401, or 403 all keep the visitor out; JSON/XHR
            # endpoints legitimately answer 403 instead of redirecting.
            assert resp.status_code in (301, 302, 303, 307, 308, 401, 403), (
                path + " answered " + str(resp.status_code)
                + " to an anonymous visitor — expected to be kept out"
            )
        assert checked, ("no protected routes found under "
                         + repr(self.PROTECTED_PREFIXES))
        return None

    def check_security_headers_on_the_login_page(self, client):
        resp = client.get(self.LOGIN_PATH)
        csp = resp.headers.get("content-security-policy", "")
        assert "script-src" in csp, (
            "no Content-Security-Policy with script-src on the login page — "
            "the shared middleware (or its exact csp= argument) is missing"
        )
        return None
