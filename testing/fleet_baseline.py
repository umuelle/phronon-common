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

from phronon_common.registry import BACKOFFICE_DASHBOARD, BACKOFFICE_LOGIN

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


_REDIRECTS = (301, 302, 303, 307, 308)


class FleetBaseline:
    """The four checks. A tool subclasses this and supplies the constants.

    Every method returns a skip reason (a string) or None; the wrapper calls
    `pytest.skip` on the string. `fleet_app` and `client` are the tool's own
    fixtures, passed in by its wrapper.
    """

    #: One address fleet-wide since 3 October 2026; a wrapper no longer says
    #: where its login lives (two tools said "/backoffice"), the registry does.
    LOGIN_PATH = BACKOFFICE_LOGIN
    LOGIN_POST = BACKOFFICE_LOGIN
    PROTECTED_PREFIXES: tuple = ("/backoffice/",)
    #: The tool sets this from `strict_here(__file__)`.
    STRICT = False

    # ── the walk ────────────────────────────────────────────────────────────
    def walkable_get_routes(self, fleet_app) -> list:
        # Every route the app DISPATCHES, routers included (FL-082, 4 October
        # 2026). Until then this looped over `app.routes` and kept the
        # APIRoutes — which on FastAPI 0.139 skips every route inside an
        # included router: the shared legal pages in all nine tools, and every
        # route of a tool that keeps its routes in router modules. A walk that
        # cannot see a route cannot notice it answering 500.
        from phronon_common.adminroutes import app_routes

        routes = []
        for r in app_routes(fleet_app.app):
            if "GET" not in r.methods:
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

    def check_the_tools_stylesheet_ships_through_frontend_bundles(self, fleet_app, client):
        """Fleet-wide since v1.74.0 (owner, 4 October 2026; TO DO FL-078): a
        tool with its own static/css/backoffice.css enrols it for the
        frontend-only release path and serves it from the active bundle. The
        pilot ran in Layoff alone; the owner did not want one tool shipping its
        stylesheet differently from the rest. The hub has no such file.

        Checked against a scratch bundle folder, so no server is needed: the
        contract names the file and only tool-owned files, the app installed
        `phronon_common.frontend_assets` (its middleware is in the stack), the
        app's own Jinja environment links the active bundle during a request,
        the bundle URL is cached as immutable (never no-store), and /health
        names the bundle. Not through a page: most sign-in pages use the
        participant layout and never load backoffice.css; the real backoffice
        pages are walked in a browser by server-ops/frontend_check.py.
        """
        import json
        import shutil
        import tempfile

        from phronon_common import frontend_assets
        from phronon_common.registry import TOOLS
        from phronon_common.shared_assets import ASSETS

        base = Path(fleet_app.__file__).resolve().parent
        css = base / "static" / "css" / "backoffice.css"
        if not css.is_file():
            return None
        contract_file = base / "frontend" / "contract.json"
        assert contract_file.is_file(), (
            "static/css/backoffice.css exists but frontend/contract.json does not: "
            "the stylesheet is not enrolled for frontend-only releases (FL-078)")
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
        assert contract.get("tool") in TOOLS, f"contract names an unknown tool {contract.get('tool')!r}"
        assert "css/backoffice.css" in contract.get("assets", []), "the contract does not enrol css/backoffice.css"
        shared = {p.removeprefix("static/") for p in ASSETS.values()}
        assert not set(contract["assets"]) & shared, "a copy of a shared master may never be enrolled (FL-069)"
        fe = frontend_assets._installed
        assert fe is not None and fe.base_dir.resolve() == base, (
            "app.py never called frontend_assets.install(app, templates, BASE_DIR)")

        bid = "0123456789abcdef"
        scratch = Path(tempfile.mkdtemp(prefix="phronon-frontend-check-"))
        saved = (fe.root, fe._state)
        try:
            for rel in contract["assets"]:
                target = scratch / "bundles" / bid / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((base / "static" / rel).read_bytes())
            (scratch / "active.json").write_text(json.dumps(
                {"schema": 1, "tool": contract["tool"], "bundle": bid,
                 "files": {rel: "-" for rel in contract["assets"]}}))
            fe.root, fe._state = scratch, {"stamp": None, "good": None}

            r = client.get(f"/frontend/{bid}/css/backoffice.css")
            if r.status_code >= 500 and not self.STRICT:
                return "requires the live server environment (the bundle route answered 5xx)"
            assert r.status_code == 200 and r.content == css.read_bytes(), (
                f"/frontend/{bid}/css/backoffice.css answered {r.status_code}: the route "
                "frontend_assets.install adds is missing or shadowed by another route")
            assert r.headers.get("content-type", "").startswith("text/css")
            cache = r.headers.get("cache-control", "")
            assert "immutable" in cache and "no-store" not in cache, (
                f"a bundle must be cached as immutable, got {cache!r} "
                "(is /frontend/ public in security_headers.PUBLIC_PREFIXES?)")

            stack = [getattr(m, "kwargs", None) or getattr(m, "options", None) or {}
                     for m in fleet_app.app.user_middleware]
            assert any(getattr(o.get("dispatch"), "__name__", "") == "_frontend_snapshot" for o in stack), (
                "the one-bundle-per-request middleware is not installed")
            token = fe.begin_request()
            try:
                link = fe.env.from_string("{{ asset('/static/css/backoffice.css') }}").render()
            finally:
                fe.end_request(token)
            assert link == f"/frontend/{bid}/css/backoffice.css", (
                f"the app's asset() gave {link!r}, not the active bundle: install() must run "
                "after the asset global is set, on the environment the pages render with")

            health = client.get("/health")
            if health.status_code == 200:
                assert health.json().get("frontend_bundle") == bid, (
                    "/health does not name the active bundle: add "
                    '"frontend_bundle": frontend_assets.active_bundle()')
            elif self.STRICT:
                raise AssertionError(f"/health answered {health.status_code}")
        finally:
            fe.root, fe._state = saved
            shutil.rmtree(scratch, ignore_errors=True)
        return None

    def check_the_entry_addresses_are_the_fleet_ones(self, client):
        """One shape on every teaching tool (owner's decision, 3 October 2026).

        Signed out: the login page answers at BACKOFFICE_LOGIN with a password
        field, and /backoffice, /backoffice/ and BACKOFFICE_DASHBOARD all lead
        there. Two tools signed in at /backoffice and 404ed the login address,
        two listed sessions somewhere other than the dashboard address, two
        404ed /backoffice. The signed-in half (the dashboard renders, and
        /backoffice leads to it) needs a session and lives in each tool's own
        test of its entry addresses.
        """
        page = client.get(BACKOFFICE_LOGIN, follow_redirects=False)
        if page.status_code >= 500 and not self.STRICT:
            return "requires the live server environment (login page needs the database)"
        assert page.status_code == 200, (
            f"{BACKOFFICE_LOGIN} answered {page.status_code}: the sign-in page "
            "must live at the fleet address")
        assert 'type="password"' in page.text, f"{BACKOFFICE_LOGIN} has no password field"
        for path in ("/backoffice", "/backoffice/", BACKOFFICE_DASHBOARD):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code >= 500 and not self.STRICT:
                return f"requires the live server environment ({path} needs the database)"
            where = resp.headers.get("location", "")
            assert resp.status_code in _REDIRECTS, (
                f"{path} answered {resp.status_code} to a signed-out visitor; "
                f"it must lead to {BACKOFFICE_LOGIN}")
            # A trailing-slash hop (/backoffice/ -> /backoffice) is allowed as
            # long as the chain ends on the login page.
            final = client.get(path, follow_redirects=True)
            assert final.url.path == BACKOFFICE_LOGIN, (
                f"{path} -> {where} ends at {final.url.path}, not {BACKOFFICE_LOGIN}")
        return None
