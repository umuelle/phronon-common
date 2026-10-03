"""A process keeps the release it started with (server layout since 3 October 2026).

The server's /var/www/phronon_common is a symlink to an immutable release
directory, swapped by `server-ops/common_release.sh activate`. This builds the
same layout in a temporary folder: two copies of this package, A and B, that
differ in one module and one template; a symlink pointing at A; a process that
imports the package through it; the symlink swapped to B; and only THEN a lazy
import and a template read. Both must still come from A.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]

_CHILD = r"""
import json, os, sys
root, b = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
import phronon_common                      # started on release A
link = os.path.join(root, "phronon_common")
tmp = link + ".next"
os.symlink(b, tmp)
os.replace(tmp, link)                      # activate B, as the release script does
import phronon_common.joincode as late     # a lazy import after the switch
import phronon_common.legal as legal       # a module that reads templates by __file__
print(json.dumps({
    "late_file": late.__file__,
    "marker": getattr(late, "RELEASE_MARKER", "A"),
    "templates": str(legal._TEMPLATES),
    "now_points_at": os.path.realpath(link),
}))
"""


def _copy(dest: Path) -> Path:
    shutil.copytree(PKG, dest, ignore=shutil.ignore_patterns(
        ".git", "tests", "__pycache__", ".github", "*.pyc"))
    return dest


def test_a_worker_keeps_its_release_when_the_symlink_moves(tmp_path):
    a = _copy(tmp_path / "releases" / "A")
    b = _copy(tmp_path / "releases" / "B")
    (b / "joincode.py").write_text((b / "joincode.py").read_text() + "\nRELEASE_MARKER = 'B'\n")
    root = tmp_path / "www"
    root.mkdir()
    (root / "phronon_common").symlink_to(a)

    out = subprocess.run([sys.executable, "-c", _CHILD, str(root), str(b)],
                         capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}).stdout
    got = json.loads(out.strip().splitlines()[-1])

    assert got["now_points_at"] == str(b.resolve())          # the switch happened
    assert got["marker"] == "A"                               # ...and did not reach this process
    assert Path(got["late_file"]).resolve().is_relative_to(a.resolve())
    assert Path(got["templates"]).resolve().is_relative_to(a.resolve())


def test_a_new_process_gets_the_new_release(tmp_path):
    a = _copy(tmp_path / "releases" / "A")
    root = tmp_path / "www"
    root.mkdir()
    (root / "phronon_common").symlink_to(a)
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); import phronon_common as p; "
         "print(p.__path__[0])", str(root)],
        capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(a.resolve())
