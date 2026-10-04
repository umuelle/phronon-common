"""A tool that mounts the account kit: the kit's routes, once, and no leftovers.

phronon_common.account_kit (FL-083) serves a tool's code prompt, authenticator
setup, passkeys and Manage account page from one router. Two ways a tool can
get that wrong without any page failing to render:

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


def kit_routes(legacy_password_path: str | None = None) -> list[tuple[str, str]]:
    from phronon_common import account_kit
    gets = {"/backoffice/verify", "/backoffice/two-factor", "/backoffice/account",
            "/backoffice/account/email/confirm"}
    routes = [(p, "GET") for p in gets]
    routes += [(p, "POST") for p in account_kit.PATHS if p != "/backoffice/account"]
    if legacy_password_path:
        routes += [(legacy_password_path, "GET"), (legacy_password_path, "POST")]
    return sorted(routes)


def assert_the_kit_is_mounted_once(app, legacy_password_path: str | None = None) -> None:
    routes = effective_routes(app)
    answered = [(path, method) for path, method, _module in routes]
    wanted = kit_routes(legacy_password_path)
    twice = sorted({r for r in wanted if answered.count(r) > 1})
    assert not twice, (
        f"{twice} are answered twice — a copy of the route is still in app.py, and "
        f"only the one registered first is ever reached")
    by_kit = {(path, method) for path, method, module in routes
              if module == "phronon_common.account_kit"}
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
