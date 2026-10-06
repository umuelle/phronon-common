"""The fleet-baseline floor must not go vacuous off the server (TO DO FL-061).

Two faults, both found by the 18 September 2026 test review and fixed on
6 October 2026:

1. Off the server every check returned a skip at the FIRST server error, so
   one database-backed page removed the rest of the walk: a later route that
   let an anonymous visitor in was never asked. The checks now ask every route
   before any verdict, and the access-control assertions hold everywhere.
2. Strictness was keyed on the server path alone, so in CI (which has had a
   MySQL service since 18 September) a 5xx was the allowed skip "requires the
   live server environment", and an app that could not even be imported was
   the same allowed skip. Now CI and any `*_test` run are strict, and an
   import failure is a skip no allow-list can permit.

Each test below fails against the code before that day.
"""
from __future__ import annotations

import types

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from phronon_common.testing import fleet_baseline as kit  # noqa: E402
from phronon_common.testing import run_reporting  # noqa: E402

LOGIN = kit.BACKOFFICE_LOGIN


def _app(routes: dict[str, int]):
    """A tiny app: each path answers the given status (302 leads to login)."""
    app = FastAPI()

    def make(code):
        def view():
            if code in (301, 302, 303, 307, 308):
                return RedirectResponse(LOGIN, status_code=code)
            return JSONResponse({"code": code}, status_code=code)
        return view

    for i, (path, code) in enumerate(routes.items()):
        app.add_api_route(path, make(code), methods=["GET"], name=f"r{i}")
    app.add_api_route(LOGIN, lambda: HTMLResponse('<input type="password" name="password">'),
                      methods=["GET"], name="login_page")
    return types.SimpleNamespace(app=app), TestClient(app, raise_server_exceptions=False)


class Lenient(kit.FleetBaseline):
    STRICT = False


class Strict(kit.FleetBaseline):
    STRICT = True


# ── 1. every route is asked before any verdict ──────────────────────────────

def test_a_server_error_no_longer_hides_a_page_that_lets_an_anonymous_visitor_in():
    # Sorted walk order: /backoffice/a answers 500 first, /backoffice/b is open.
    fleet_app, client = _app({"/backoffice/a": 500, "/backoffice/b": 200,
                              "/backoffice/c": 302})
    with pytest.raises(AssertionError, match="/backoffice/b"):
        Lenient().check_anonymous_is_kept_out_of_protected_pages(fleet_app, client)


def test_off_a_gate_only_server_errors_skip_and_the_skip_names_all_of_them():
    fleet_app, client = _app({"/backoffice/a": 500, "/backoffice/b": 302,
                              "/backoffice/c": 503})
    reason = Lenient().check_anonymous_is_kept_out_of_protected_pages(fleet_app, client)
    assert reason and "/backoffice/a -> 500" in reason and "/backoffice/c -> 503" in reason


def test_where_strict_a_server_error_on_a_protected_page_fails():
    fleet_app, client = _app({"/backoffice/a": 500, "/backoffice/b": 302})
    with pytest.raises(AssertionError, match="/backoffice/a -> 500"):
        Strict().check_anonymous_is_kept_out_of_protected_pages(fleet_app, client)


def test_an_entry_address_that_answers_is_found_behind_one_that_errors():
    fleet_app, client = _app({"/backoffice": 500, "/backoffice/": 302,
                              kit.BACKOFFICE_DASHBOARD: 200})
    with pytest.raises(AssertionError, match=kit.BACKOFFICE_DASHBOARD):
        Lenient().check_the_entry_addresses_are_the_fleet_ones(client)


def test_the_route_walk_names_every_broken_route():
    fleet_app, client = _app({"/x": 500, "/y": 200, "/z": 502})
    reason = Lenient().check_every_parameterless_get_route_answers(fleet_app, client)
    assert reason and "/x -> 500" in reason and "/z -> 502" in reason
    with pytest.raises(AssertionError, match="/z -> 502"):
        Strict().check_every_parameterless_get_route_answers(fleet_app, client)


# ── 2. strict wherever a database exists ─────────────────────────────────────

@pytest.mark.parametrize("env, strict", [
    ({}, False),                                  # a bare local pytest
    ({"GITHUB_ACTIONS": "true"}, True),           # CI: MySQL service since 18 Sep
    ({"DB_NAME": "layoff_exercise_test"}, True),  # run_tests.py with .env.test
    ({"DB_NAME": "layoff_exercise"}, False),      # a live name is not a test run
])
def test_strictness_follows_the_database(monkeypatch, tmp_path, env, strict):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert kit.strict_here(tmp_path / "tests" / "test_fleet_baseline.py") is strict



# ── an app that cannot import is never an allowed skip ──────────────────────

def _skip(reason):
    return types.SimpleNamespace(skipped=True, nodeid="tests/test_fleet_baseline.py::t",
                                 longrepr=("file", 1, "Skipped: " + reason))


@pytest.mark.parametrize("reason", [
    "requires the live server environment (app import: ModuleNotFoundError: No module named 'webauthn')",
    "requires the live server environment (TestClient import: RuntimeError)",
    "requires the live server environment (TestClient: RuntimeError)",
    "requires the live server environment (fastapi)",
    "Could not import app.py: ImportError: x",
])
def test_an_import_failure_is_unexpected_whatever_the_allow_list_says(reason):
    sink: list = []
    run_reporting.collect_unexpected_skip(
        _skip(reason), run_reporting.BASE_ALLOWED_SKIPS + ("Could not import",), sink)
    assert len(sink) == 1


def test_an_environmental_skip_is_still_allowed():
    sink: list = []
    run_reporting.collect_unexpected_skip(
        _skip("requires the live server environment (login POST needs the database)"),
        run_reporting.BASE_ALLOWED_SKIPS, sink)
    assert sink == []
