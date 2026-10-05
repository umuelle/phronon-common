"""A tool that mounts the account kit: the kit's routes, once, and no leftovers.

phronon_common.account_kit (FL-083) serves a tool's sign-in, sign-out,
password-reset links, code prompt, authenticator setup, passkeys, Manage
account page and the administrator's two-factor reset from one router. Two
ways a tool can get that wrong without any page failing to render:

  * a route left behind in app.py, or added there again later. FastAPI answers
    a path with the FIRST route that matches, so whichever was registered
    first silently wins and the other is dead code that still looks live;
  * a template left behind. The tool's own template folder is searched before
    the kit's, so a stale `templates/account_kit/x.html` would replace the
    kit's page, and a stale `templates/backoffice/two_factor.html` is a copy
    the next edit lands in while the page people see comes from the kit.

Plain assertion functions (no pytest import, see __init__.py); each kit tool
calls them from its own tests/.
"""
from __future__ import annotations

from pathlib import Path

#: The page templates the kit replaced. A tool that mounts the kit carries none.
REPLACED_TEMPLATES = ("two_factor.html", "two_factor_verify.html", "account.html",
                      "account_confirm_email.html")


def effective_routes(app) -> list[tuple[str, str, str]]:
    """(path, METHOD, endpoint module) for every route the app answers,
    routers included.

    Recent FastAPI keeps an included router as one entry that expands lazily
    (`original_router`); older versions copied its routes in. Both are read."""
    out: list[tuple[str, str, str]] = []

    def walk(routes, prefix=""):
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
                continue
            module = getattr(getattr(route, "endpoint", None), "__module__", "")
            for method in sorted(getattr(route, "methods", None) or ()):
                out.append((prefix + route.path, method, module))

    walk(app.routes)
    return out


#: The module that answers a kit route: phase 2's, or the frozen phase 1 code
#: an adapter in phase 1's shape is served from (1.75.0, expand then contract).
KIT_MODULE = "phronon_common.account_kit"
PHASE_1_MODULE = "phronon_common.account_kit_v1"


def kit_routes(legacy_password_path: str | None = None, *,
               sign_in: bool = False) -> list[tuple[str, str]]:
    """The kit's (path, METHOD) pairs. `sign_in=True` is phase 2 (sign-in,
    sign-out, reset links and the admin two-factor reset too); the default is
    phase 1's set, which is what a tool's code from before its phase-2 deploy
    asks for."""
    if sign_in:
        from phronon_common import account_kit
        routes = [(p, "GET") for p in account_kit.GET_PATHS]
        routes += [(p, "POST") for p in account_kit.PATHS if p != account_kit.ACCOUNT_URL]
    else:
        from phronon_common import account_kit_v1
        gets = {"/backoffice/verify", "/backoffice/two-factor", "/backoffice/account",
                "/backoffice/account/email/confirm"}
        routes = [(p, "GET") for p in gets]
        routes += [(p, "POST") for p in account_kit_v1.PATHS if p != "/backoffice/account"]
    if legacy_password_path:
        routes += [(legacy_password_path, "GET"), (legacy_password_path, "POST")]
    return sorted(routes)


def assert_the_kit_is_mounted_once(app, legacy_password_path: str | None = None) -> None:
    routes = effective_routes(app)
    answered = [(path, method) for path, method, _module in routes]
    # Which phase the tool mounts: phase 2's own module answers the code prompt.
    phase_2 = any(path == "/backoffice/verify" and module == KIT_MODULE
                  for path, _method, module in routes)
    kit_module = KIT_MODULE if phase_2 else PHASE_1_MODULE
    wanted = kit_routes(legacy_password_path, sign_in=phase_2)
    twice = sorted({r for r in wanted if answered.count(r) > 1})
    assert not twice, (
        f"{twice} are answered twice — a copy of the route is still in app.py, and "
        f"only the one registered first is ever reached")
    by_kit = {(path, method) for path, method, module in routes
              if module == kit_module}
    missing = [r for r in wanted if r not in by_kit]
    assert not missing, f"the account kit does not answer {missing}"


def assert_no_template_shadows_the_kit(project_root: Path | str) -> None:
    templates = Path(project_root) / "templates"
    shadow = sorted(str(p.relative_to(templates))
                    for p in (templates / "account_kit").glob("*.html"))
    assert not shadow, f"{shadow} would replace the kit's own page"
    stale = [name for name in REPLACED_TEMPLATES if (templates / "backoffice" / name).exists()]
    assert not stale, (
        f"templates/backoffice/{stale} are copies the kit replaced; the page "
        f"people see is the kit's, so an edit there changes nothing")


#: The tool's own pages the kit renders: each tool's branded entrance.
OWN_ENTRANCE_PAGES = {"login.html": "/backoffice/login",
                      "password_reset.html": "/backoffice/password-reset"}


def assert_the_tool_keeps_its_entrance_pages(project_root: Path | str) -> None:
    """The kit renders the tool's own sign-in and reset pages and hands them
    `csrf_token`. A page that is missing, still reads another name for the
    token, or posts somewhere else renders, and every sign-in then fails."""
    templates = Path(project_root) / "templates" / "backoffice"
    for name, action in OWN_ENTRANCE_PAGES.items():
        page = templates / name
        assert page.is_file(), f"templates/backoffice/{name} is missing; the kit renders it"
        html = page.read_text(encoding="utf-8")
        assert 'name="csrf_token" value="{{ csrf_token }}"' in html, (
            f"{name}: the form's token must be the kit's `csrf_token`")
        assert f'action="{action}"' in html, f"{name}: the form must post to {action}"

