"""The live admin-route check sees what the RUNNING app serves (FL-082).

`assert_admin_routes_are_gated` reads one file, `app.py`. A route that moves
into a router module does not fail it — it leaves it, silently. These tests
prove the live check (`assert_live_admin_routes_are_gated`) closes that gap:
it finds routes inside included routers, applies router prefixes, and refuses
an ungated admin route wherever its handler is written. Each refusal is shown
against a gated twin that passes, so a check that refused everything would
fail here too.

FastAPI is a test dependency of this package (requirements-test.txt), and no
import of it is skipped: a missing framework must fail the run.
"""
from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import RedirectResponse

from phronon_common.adminroutes import (
    admin_routes,
    app_routes,
    assert_live_admin_routes_are_gated,
    live_admin_routes,
    unguarded_live_admin_routes,
)

PREFIXES = ['/backoffice/users']
GUARDS = ["admin['role'] != 'ADMIN'"]


def _who(request: Request):
    """Stand-in for a tool's cookie reader (`get_admin_from_request`)."""
    return {'id': 1, 'role': request.headers.get('x-role', 'EDUCATOR')}


async def csrf_like(request: Request):
    """An app-wide dependency, as the tools wire `csrf_protect`."""
    return None


def require_admin(request: Request):
    """A guard DEPENDENCY, the other way a tool may gate a route."""
    if _who(request)['role'] != 'ADMIN':
        raise PermissionError


# ── handlers, written the way the tools write them ─────────────────────────

async def users_list(request: Request):
    admin = _who(request)
    if not admin or admin['role'] != 'ADMIN':
        return RedirectResponse('/backoffice/login', status_code=303)
    return {'users': []}


async def delete_user(request: Request, user_id: int):
    admin = _who(request)
    if not admin or admin['role'] != 'ADMIN':
        return RedirectResponse('/backoffice/login', status_code=303)
    return {'deleted': user_id}


async def delete_user_ungated(request: Request, user_id: int):
    admin = _who(request)
    if not admin:
        return RedirectResponse('/backoffice/login', status_code=303)
    return {'deleted': user_id}


async def bulk_narrowed(request: Request):
    # Whiteout's 9 August hole: the comparison is THERE, ANDed with something
    # that decides when it fires — an action outside the list walks through.
    admin = _who(request)
    action = request.query_params.get('action', '')
    if admin['role'] != 'ADMIN' and action in ('add', 'delete'):
        return RedirectResponse('/backoffice/login', status_code=303)
    return {'ok': True}


async def edit_user(request: Request, user_id: int):
    admin = _who(request)
    if not admin or admin['role'] != 'ADMIN':
        return RedirectResponse('/backoffice/login', status_code=303)
    return {'edit': user_id}


async def guarded_by_dependency(request: Request):
    return {'ok': True}


async def own_profile(request: Request):
    """Under the admin prefix, reachable by anyone signed in — on purpose."""
    return {'me': _who(request)['id']}


async def dashboard(request: Request):
    return {}


def _app(*, users_router_routes, extra=None, router_dependencies=()):
    """A tool-shaped app: an app-wide dependency, one route of its own, the
    user-management routes in an INCLUDED router, edit under a prefix."""
    app = FastAPI(dependencies=[Depends(csrf_like)])
    app.add_api_route('/backoffice/dashboard', dashboard, methods=['GET'])
    users = APIRouter(dependencies=list(router_dependencies))
    for path, endpoint, methods in users_router_routes:
        users.add_api_route(path, endpoint, methods=methods)
    app.include_router(users)
    edit = APIRouter()
    edit.add_api_route('/{user_id}/edit', edit_user, methods=['GET', 'POST'])
    app.include_router(edit, prefix='/backoffice/users')
    for path, endpoint, methods, deps in extra or ():
        r = APIRouter()
        r.add_api_route(path, endpoint, methods=methods, dependencies=deps)
        app.include_router(r)
    return app


GATED = [('/backoffice/users', users_list, ['GET']),
         ('/backoffice/users/{user_id}/delete', delete_user, ['POST'])]


def test_a_gated_app_passes():
    assert_live_admin_routes_are_gated(_app(users_router_routes=GATED), PREFIXES, GUARDS)


def test_it_sees_routes_inside_included_routers_with_their_prefix():
    app = _app(users_router_routes=GATED)
    found = {(r.path, r.handler) for r, _, _ in live_admin_routes(app, PREFIXES)}
    assert found == {('/backoffice/users', 'users_list'),
                     ('/backoffice/users/{user_id}/delete', 'delete_user'),
                     ('/backoffice/users/{user_id}/edit', 'edit_user')}
    # ...and the app-wide dependency reaches the included routes.
    for r in app_routes(app):
        assert csrf_like in r.dependencies, r.path


def test_an_ungated_route_in_an_included_router_is_refused():
    """The mutation: one guard removed, in a router module, not app.py."""
    app = _app(users_router_routes=[GATED[0],
                                    ('/backoffice/users/{user_id}/delete',
                                     delete_user_ungated, ['POST'])])
    bad = unguarded_live_admin_routes(app, PREFIXES, GUARDS)
    assert [(r.path, r.handler) for r in bad] == [
        ('/backoffice/users/{user_id}/delete', 'delete_user_ungated')]
    assert 'test_adminroutes_live.py' in bad[0].source and bad[0].lineno > 0
    with pytest.raises(AssertionError, match='delete_user_ungated'):
        assert_live_admin_routes_are_gated(app, PREFIXES, GUARDS)


def test_a_guard_narrowed_by_and_is_refused():
    app = _app(users_router_routes=GATED + [('/backoffice/users/bulk', bulk_narrowed, ['POST'])])
    assert [r.handler for r in unguarded_live_admin_routes(app, PREFIXES, GUARDS)] == [
        'bulk_narrowed']


def test_a_guard_dependency_counts_only_when_it_is_named():
    route = ('/backoffice/users/export', guarded_by_dependency, ['GET'],
             [Depends(require_admin)])
    app = _app(users_router_routes=GATED, extra=[route])
    assert [r.handler for r in unguarded_live_admin_routes(app, PREFIXES, GUARDS)] == [
        'guarded_by_dependency']
    assert unguarded_live_admin_routes(app, PREFIXES, GUARDS,
                                       guard_dependencies=[require_admin]) == []


def test_a_router_wide_guard_dependency_gates_its_routes():
    app = _app(users_router_routes=[('/backoffice/users/export', guarded_by_dependency, ['GET'])],
               router_dependencies=[Depends(require_admin)])
    assert unguarded_live_admin_routes(app, PREFIXES, GUARDS,
                                       guard_dependencies=[require_admin]) == []
    assert [r.handler for r in unguarded_live_admin_routes(app, PREFIXES, GUARDS)] == [
        'guarded_by_dependency']


def test_allow_exempts_a_named_handler_and_nothing_else():
    app = _app(users_router_routes=GATED + [('/backoffice/users/me', own_profile, ['GET'])])
    assert [r.handler for r in unguarded_live_admin_routes(app, PREFIXES, GUARDS)] == ['own_profile']
    assert unguarded_live_admin_routes(app, PREFIXES, GUARDS, allow=['own_profile']) == []


def test_nothing_to_inspect_is_a_failure_not_a_pass():
    app = _app(users_router_routes=GATED)
    with pytest.raises(AssertionError, match='serves no routes'):
        assert_live_admin_routes_are_gated(app, ['/backoffice/staff'], GUARDS)
    with pytest.raises(ValueError):
        unguarded_live_admin_routes(app, PREFIXES)


def test_the_text_check_cannot_see_a_route_that_left_app_py():
    """Why the live check exists. An `app.py` that only includes a router has
    no admin routes in its TEXT, so the source-level check finds nothing to
    refuse — while the app serves an ungated one."""
    composition_root = (
        "from fastapi import FastAPI\n"
        "from routers import users\n"
        "app = FastAPI()\n"
        "app.include_router(users.router)\n")
    assert admin_routes(composition_root, PREFIXES) == []
    app = _app(users_router_routes=[('/backoffice/users/{user_id}/delete',
                                     delete_user_ungated, ['POST'])])
    assert unguarded_live_admin_routes(app, PREFIXES, GUARDS)


def test_app_routes_reports_effective_methods():
    app = _app(users_router_routes=GATED)
    by_path = {r.path: r.methods for r in app_routes(app)}
    assert by_path['/backoffice/users/{user_id}/edit'] == frozenset({'GET', 'POST'})
    assert by_path['/backoffice/dashboard'] == frozenset({'GET'})
