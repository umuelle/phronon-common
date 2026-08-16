"""Find names a module reads but never binds — one implementation for the fleet.

WHY THIS EXISTS (external review, 16 August 2026).

Layoff's `delete_educator` read:

    if not require_admin(request):
        return RedirectResponse(...)
    ...
    db.db_execute("DELETE FROM admins WHERE id = %s", [educator_id])
    log_audit_event("admin_deleted", user["email"], ...)   # <- `user` is undefined

The guard checked the admin without BINDING them, so `user` was never defined.
Python does not care until that line runs, and that line only runs on the happy
path of a rarely-exercised admin route. The result was the worst shape a bug
can take: the DELETE had already committed, the NameError was swallowed by the
route's `except Exception`, the educator was shown "Error deleting educator" —
and the audit row that was supposed to record the deletion was never written.
A green test suite, a plausible error message, and a silently destructive
action that the trail cannot explain.

Nothing in the fleet's gates would have caught it. `compileall` only proves the
file parses. The route tests never reached that branch. pyflakes would have
found it in a second, but it is not a dependency of any tool here and adding
one to nine venvs to catch one class of bug is the wrong trade — this module is
about ninety lines and has no dependencies at all.

It is deliberately CONSERVATIVE. A false positive would train people to add
names to an ignore list, which ends with the check switched off. So: a name
assigned ANYWHERE in a function is treated as bound throughout it (that is
Python's own scoping rule), every enclosing scope is consulted, and anything
this module is unsure about is not reported.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

_BUILTINS = frozenset(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}


def _bound_by_target(node: ast.AST) -> set[str]:
    """Names bound by an assignment target, `for` target, `with … as`, etc."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            out.add(sub.id)
    return out


def _scope_bindings(node: ast.AST) -> set[str]:
    """Every name bound inside one scope, WITHOUT descending into nested scopes.

    Python binds a name for the whole function body regardless of where the
    assignment sits, so order is irrelevant here and a name assigned on line 90
    counts as bound on line 10. That is what makes this check conservative: it
    can only miss real bugs, never invent them.
    """
    bound: set[str] = set()

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            bound.add(a.arg)
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)

    # `bound.update(...)`, never `bound |= ...`: the augmented form inside this
    # nested function would make `bound` local to it and raise UnboundLocalError
    # on the first import statement. (Found by running this checker over itself.)
    def walk(n: ast.AST) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(child.name)          # the def itself binds its name…
                continue                        # …but its body is another scope
            if isinstance(child, ast.Lambda):
                continue
            if isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                # A comprehension has its own scope; its targets do not leak out.
                continue
            if isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign,
                                  ast.For, ast.AsyncFor)):
                target = getattr(child, "target", None) or getattr(child, "targets", [])
                for t in (target if isinstance(target, list) else [target]):
                    if t is not None:
                        bound.update(_bound_by_target(t))
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if item.optional_vars is not None:
                        bound.update(_bound_by_target(item.optional_vars))
            elif isinstance(child, ast.ExceptHandler) and child.name:
                bound.add(child.name)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    bound.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(child, (ast.Global, ast.Nonlocal)):
                bound.update(child.names)
            elif isinstance(child, ast.NamedExpr):
                bound.update(_bound_by_target(child.target))
            else:
                # `match` patterns bind through their own node types, which do
                # not exist before Python 3.10 — hence getattr rather than a
                # bare isinstance that would break the check on an older
                # interpreter (the fleet runs 3.10, CI has run others).
                _match_binders = tuple(
                    t for t in (getattr(ast, n, None)
                                for n in ("MatchAs", "MatchStar", "MatchMapping"))
                    if t is not None
                )
                if _match_binders and isinstance(child, _match_binders):
                    for attr in ("name", "rest"):
                        val = getattr(child, attr, None)
                        if isinstance(val, str):
                            bound.add(val)
            walk(child)

    walk(node)
    return bound


# Everything Python gives its own namespace. Comprehensions belong here: since
# Python 3, `[x for x in xs]` does NOT leak `x`, and its body is evaluated in
# that inner scope — miss this and every comprehension variable in the fleet
# reads as an undefined name.
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _comprehension_bindings(node: ast.AST) -> set[str]:
    """Names bound by the `for` clauses of a comprehension or lambda args."""
    bound: set[str] = set()
    if isinstance(node, ast.Lambda):
        args = node.args
        for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            bound.add(a.arg)
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)
        return bound
    for gen in getattr(node, "generators", []):
        bound.update(_bound_by_target(gen.target))
    # A walrus inside a comprehension binds in the ENCLOSING scope, but
    # treating it as inner only risks a miss, never a false alarm.
    for sub in ast.walk(node):
        if isinstance(sub, ast.NamedExpr):
            bound.update(_bound_by_target(sub.target))
    return bound


def _loaded_names(node: ast.AST) -> list[ast.Name]:
    """Name reads directly in this scope, not in any nested scope."""
    out: list[ast.Name] = []

    def walk(n: ast.AST) -> None:
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _SCOPE_NODES):
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                out.append(child)
            walk(child)

    walk(node)
    return out


def undefined_names(source: str, filename: str = "<source>") -> list[tuple[int, str, str]]:
    """(line, name, function) for every name read but never bound in scope.

    Decorators, default values and annotations are evaluated in the ENCLOSING
    scope, so they are checked there rather than inside the function.
    """
    tree = ast.parse(source, filename=filename)
    module_names = _scope_bindings(tree)

    findings: list[tuple[int, str, str]] = []

    def visit(node: ast.AST, enclosing: set[str], path: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = enclosing | _scope_bindings(child)
                name = f"{path}.{child.name}" if path else child.name
                for n in _loaded_names(child):
                    if n.id not in inner and n.id not in _BUILTINS:
                        findings.append((n.lineno, n.id, name))
                visit(child, inner, name)
            elif isinstance(child, (ast.Lambda, ast.ListComp, ast.SetComp,
                                    ast.DictComp, ast.GeneratorExp)):
                inner = enclosing | _comprehension_bindings(child)
                for n in _loaded_names(child):
                    if n.id not in inner and n.id not in _BUILTINS:
                        findings.append((n.lineno, n.id, path or "<module>"))
                visit(child, inner, path)
            elif isinstance(child, ast.ClassDef):
                # Class bodies do not form a closure for their methods; the
                # methods see the enclosing FUNCTION scope, not the class body.
                visit(child, enclosing, f"{path}.{child.name}" if path else child.name)
            else:
                visit(child, enclosing, path)

    visit(tree, module_names | _BUILTINS, "")
    return sorted(set(findings))


def unreachable_statements(source: str, filename: str = "<source>") -> list[tuple[int, str]]:
    """(line, why) for every statement that can never run.

    THE OTHER HALF OF THE SAME LESSON. LSR's `delete_class` had its
    `return RedirectResponse(...)` at function level instead of inside the
    `if not cls:` branch above it, so the entire deletion — ownership check,
    consent fork, the DELETE itself — sat below a return and never ran. "Delete
    class" in the backoffice did nothing, silently, and every test passed. The
    same tool's internal schedule route had `today = ...` stranded after a
    return inside an except-handler, which left `today` unbound for the loop
    that read it.

    Dead code after a return is never intentional in this codebase, and it is
    invisible in review precisely because it reads as ordinary code. Nothing
    else in the gates looks at reachability: the file compiles, the import
    works, and the tests exercise the path that returns early.

    THE ONE ESCAPE HATCH: a comment containing the word "unreachable" directly
    above the dead statement marks it as deliberate — Drawbridge keeps a
    retired upload handler that way. It is a comment rather than a config list
    because it has to be read by whoever next opens that file, which is the
    only place the decision means anything.
    """
    tree = ast.parse(source, filename=filename)
    lines = source.splitlines()
    _TERMINAL = (ast.Return, ast.Raise, ast.Continue, ast.Break)
    findings: list[tuple[int, str]] = []

    def _marked(lineno: int) -> bool:
        i = lineno - 2                      # the line above, 0-indexed
        while i >= 0 and not lines[i].strip():
            i -= 1
        return i >= 0 and "unreachable" in lines[i].strip().lower() and \
            lines[i].strip().startswith("#")

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block[:-1]):
                if isinstance(stmt, _TERMINAL):
                    nxt = block[i + 1]
                    ln = getattr(nxt, "lineno", stmt.lineno)
                    if not _marked(ln):
                        findings.append((
                            ln,
                            f"unreachable — the {type(stmt).__name__.lower()} on "
                            f"line {stmt.lineno} always runs first",
                        ))
                    break
    return sorted(set(findings))


def assert_no_unreachable_code(app_py: Path | str) -> None:
    """Raise AssertionError naming every dead statement. For use from a test."""
    path = Path(app_py)
    found = unreachable_statements(path.read_text(encoding="utf-8"), str(path))
    if found:
        lines = "\n".join(f"  {path.name}:{ln}  {why}" for ln, why in found)
        raise AssertionError(
            "statement(s) that can never run — usually a return that has "
            "drifted out of the branch it belonged to:\n" + lines
        )


def assert_no_undefined_names(app_py: Path | str) -> None:
    """Raise AssertionError naming every undefined read. For use from a test."""
    path = Path(app_py)
    found = undefined_names(path.read_text(encoding="utf-8"), str(path))
    if found:
        lines = "\n".join(f"  {path.name}:{ln}  {name!r} in {fn}()"
                          for ln, name, fn in found)
        raise AssertionError(
            "name(s) read but never bound — each one is a NameError waiting for "
            "the branch that reaches it:\n" + lines
        )
