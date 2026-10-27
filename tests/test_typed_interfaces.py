"""The shared package's interfaces pass a type checker (27 October 2026).

Gradual typing, from the third review: the modules in TYPED pass mypy with the
flags in pyproject.toml ([tool.mypy]). Every function is annotated, no Optional
is implicit, and no function hands back Any where it promises a type, so a
tool calling the clock, the mail claim, the signer, the rate limiter, the
registry or the audit trail is checked against what they really take and give.
A module joins TYPED when its annotations are done; TO DO FL-112 names the
rest. mypy is pinned in requirements-test.txt, which CI and the release's
candidate matrix install, so there it must run; on a machine without it the
test skips and says so.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

TYPED = (
    "assets", "audit", "hosts", "joincode", "kanon", "legal_content", "lockout",
    "once", "passwords", "rate_limit", "registry", "request_ip",
    "retention_heartbeat", "scheduler", "sessions", "signing",
)


def test_the_typed_interfaces_pass_the_type_checker(tmp_path):
    try:
        import mypy  # noqa: F401
    except ImportError:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("mypy is not installed; requirements-test.txt pins it")
        pytest.skip("mypy is not installed here (requirements-test.txt pins it)")
    # The package under its import name, whatever its checkout folder is called
    # (CI checks it out as phronon-common).
    (tmp_path / "phronon_common").symlink_to(ROOT, target_is_directory=True)
    args = [sys.executable, "-m", "mypy", "--config-file", str(ROOT / "pyproject.toml"),
            "--cache-dir", str(tmp_path / "cache")]
    for name in TYPED:
        args += ["-m", f"phronon_common.{name}"]
    r = subprocess.run(args, cwd=tmp_path, env=dict(os.environ, MYPYPATH=str(tmp_path)),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def test_every_typed_module_is_a_module_of_the_package():
    assert sorted(TYPED) == list(TYPED), "keep TYPED in alphabetical order"
    for name in TYPED:
        assert (ROOT / f"{name}.py").is_file(), name
