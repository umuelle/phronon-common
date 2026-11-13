"""No module a running service loads imports the test kit (TO DO FL-134,
13 November 2026). release_gate.py counts a change under testing/ as one no
service has loaded, so a release of the kit alone restarts nothing; this keeps
that true for the package's own modules."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            out |= {base} | {f"{base}.{a.name}" for a in node.names}
    return out


def test_no_runtime_module_imports_the_test_kit():
    offenders = []
    for path in sorted(ROOT.glob("*.py")):
        for name in _imports(path):
            if name.startswith(("phronon_common.testing", ".testing")):
                offenders.append(f"{path.name}: {name}")
    assert offenders == []
