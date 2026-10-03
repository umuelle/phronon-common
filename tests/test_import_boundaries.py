"""What importing a module drags in: checked by importing it, not by reading it.

Rules from the review of 3 October 2026:

- No production module imports the test kit. Changing a test helper must not
  be able to change what a server process loads.
- Only the modules that ARE web plumbing load a web framework. Writing an
  audit row, sending a mail or claiming a background job must work in a
  retention job or a script that never serves a request (audit.py loaded
  FastAPI through rate_limit until that day).
- Only passkeys loads py_webauthn.
- mail_diagnostics, run by the service user from scripts/send_test_emails.py,
  loads nothing outside the standard library and this package.

Each module is imported alone in a fresh interpreter, so one module's imports
cannot hide behind another's. A module added to the package is covered
automatically; if it is web plumbing, add it to WEB_MODULES with a reason.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
MODULES = sorted(p.stem for p in PKG.glob("*.py") if p.stem != "__init__")

#: Modules whose job is HTTP: they may load FastAPI/Starlette.
WEB_MODULES = {
    "csrf",              # a middleware
    "legal",             # the legal-pages router
    "rate_limit",        # a middleware
    "security_headers",  # a middleware
}

_PROBE = r"""
import importlib, json, sys
importlib.import_module("phronon_common." + sys.argv[1])
roots = sorted({n.split(".")[0] for n in sys.modules})
testing = sorted(n for n in sys.modules if n.startswith("phronon_common.testing"))
print(json.dumps({"roots": roots, "testing": testing}))
"""


def _loaded(module: str) -> dict:
    out = subprocess.run([sys.executable, "-c", _PROBE, module], cwd=PKG.parent,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def footprints():
    return {m: _loaded(m) for m in MODULES}


def test_no_production_module_imports_the_test_kit(footprints):
    offenders = {m: f["testing"] for m, f in footprints.items() if f["testing"]}
    assert offenders == {}


def test_only_web_plumbing_loads_a_web_framework(footprints):
    offenders = {m: sorted({"fastapi", "starlette"} & set(f["roots"]))
                 for m, f in footprints.items() if m not in WEB_MODULES}
    assert {m: r for m, r in offenders.items() if r} == {}


def test_only_passkeys_loads_webauthn(footprints):
    assert sorted(m for m, f in footprints.items() if "webauthn" in f["roots"]) == ["passkeys"]


def test_the_mail_diagnostic_is_stdlib_only(footprints):
    extra = {r for r in footprints["mail_diagnostics"]["roots"]
             if not r.startswith("__editable__")}   # pip install -e's finder (CI), not a dependency
    extra -= set(sys.stdlib_module_names) | {"phronon_common", "__main__", "_distutils_hack",
                                              "_virtualenv"}
    assert extra == set()


def test_the_old_mail_harness_name_is_the_same_module():
    from phronon_common import mail_diagnostics
    from phronon_common.testing import mail_harness
    import phronon_common.testing.mail_harness as again
    assert mail_harness is mail_diagnostics is again


def test_moved_names_answer_at_their_old_addresses():
    from phronon_common import account, audit, emails, rate_limit, request_ip
    assert emails.EMAIL_CHANGE_HOURS == account.EMAIL_CHANGE_HOURS == 2
    assert account.EMAIL_CHANGE_MAX_AGE == 2 * 3600
    assert rate_limit.client_ip is audit.client_ip is request_ip.client_ip
    assert rate_limit.default_trusted_proxies is request_ip.default_trusted_proxies
