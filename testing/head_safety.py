"""No GET route that writes may answer HEAD, and every read-only GET route does.

A HEAD probe (Outlook SafeLinks, Zscaler, FortiGate, a prefetch) runs the
handler and throws the body away, so a GET that writes performs its write with
nobody looking at the page. Whiteout found this when a scanner's HEAD spent a
participant's one-time resume link, and guarded itself with a test of its own.
This is that test for the whole fleet (5 October 2026), written so it keeps
working when a tool's routes move out of `app.py` into router modules:

* the ROUTES come from the running app (`adminroutes.app_routes`, which sees
  included routers), each with the function that handles it;
* the CODE is every runtime module of the tool (top-level `*.py`, `services/`,
  `modules/`) plus `phronon_common`'s own modules, parsed once into a call
  graph: a function writes when it calls a write helper by NAME (`execute`,
  `db_execute`, `execute_many`, `executemany`, `execute_rowcount`, ...), or
  calls a function that does, across modules and through import aliases. SQL
  written as a literal decides by its first word (SELECT/SHOW/DESCRIBE/EXPLAIN
  read, anything else writes). SQL the check cannot see (a variable, a
  parameter) counts as a write, unless the function also fetches rows
  (`fetchone`/`fetchall`/`fetchmany`): that is the shape of a read helper
  (`def _db_query_one(sql, params): cur.execute(sql, params); return
  cur.fetchone()`), and a function named like a write helper (`execute`,
  `db_execute`, ...) is a write helper whatever it fetches.
* only the branches a GET request can take: a handler that serves GET and
  POST from one function (`if request.method == "POST": ...`) writes in a
  branch a HEAD probe never reaches, so that branch is not followed; nor is
  anything after `if request.method == "GET": ... return` (Layoff's round-2
  door renders on GET and returns; only the POST below it admits anyone);
* the tool's `db.py` is a closed box: its read helpers run `cursor.execute`
  too, so reading inside it would make every read a write. Its helpers are
  judged by name at the call site, as Whiteout's own test always did.

`problems(app, tool_root)` lists both failures: a writing GET that answers
HEAD (the resume-link bug), and a read-only GET that does not (a scanner sees
405 and may flag an e-mailed link as broken). `phronon_common.routing.
answer_head(router, unsafe_paths=...)` is how a tool gets both right.

A writing GET has two right answers, and the tool chooses with a reason:

* GET only (`unsafe_paths`), when nobody would scan the link: in-app
  navigation (Whiteout's first-view GETs, Layoff's thank-you page) loses
  nothing by answering 405 to HEAD.
* HEAD anyway (`problems(..., cookie_gated={path: reason})`), when the write
  runs only for a request that carries a cookie (a signed-in educator, a
  participant's own pass) AND the link is one a scanner sees: the dashboard a
  retention mail links to, the identity page a join link redirects to. A
  scanner sends no cookies, so it reaches the read-only path; taking HEAD away
  would bring back the 405 HEAD support exists to prevent. The reason names
  the guard. A declared path that no longer writes, or is no GET route, is a
  problem too, so the list cannot go stale.

Deliberately NOT followed: FastAPI dependencies and middleware (they run for
every method alike), and calls through objects other than modules (`self.x()`).
No pytest import here (see __init__.py).
"""
from __future__ import annotations

import ast
from pathlib import Path

WRITE_METHODS = frozenset({"execute", "execute_many", "executemany", "db_execute", "db_executemany",
                           "db_execute_many", "execute_rowcount", "db_execute_rowcount"})
READ_SQL = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN")
FETCHES = frozenset({"fetchone", "fetchall", "fetchmany"})
RUNTIME_DIRS = ("services", "modules")
#: The tool's database layer: judged at the call site by helper name.
OPAQUE = frozenset({"db"})


def _method_test(test) -> str | None:
    """'post' when the If's body runs only for non-GET requests, 'get' when only
    for GET, None when the test is not about request.method."""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.left, ast.Attribute) and test.left.attr == "method"):
        return None
    op, right = test.ops[0], test.comparators[0]
    values = ([right.value] if isinstance(right, ast.Constant) else
              [e.value for e in getattr(right, "elts", []) if isinstance(e, ast.Constant)])
    if not values or not all(isinstance(v, str) for v in values):
        return None
    has_get = "GET" in values or "HEAD" in values
    if isinstance(op, (ast.Eq, ast.In)):
        return "get" if has_get else "post"
    if isinstance(op, (ast.NotEq, ast.NotIn)):
        return "post" if has_get else "get"
    return None


def _terminates(stmts) -> bool:
    """True when the block always leaves the function (return or raise)."""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    return isinstance(last, ast.If) and _terminates(last.body) and _terminates(last.orelse)


def _get_reachable(stmts) -> list:
    """The statements a GET request can reach: none after a GET-only branch
    that always returns."""
    out = []
    for s in stmts:
        out.append(s)
        if isinstance(s, ast.If) and _method_test(s.test) == "get" and _terminates(s.body):
            break
    return out


def walk_get(node):
    """ast.walk, minus the branches a GET (or HEAD) request cannot take, and
    minus the bodies of functions DEFINED inside: they run only when called,
    and a call is followed like any other (Controversy Generator's reset
    handler defines _mark_used, which writes, and calls it only on POST)."""
    todo = [node]
    while todo:
        n = todo.pop()
        yield n
        if n is not node and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(n, ast.If):
            branch = _method_test(n.test)
            if branch == "post":
                todo.extend([n.test, *_get_reachable(n.orelse)])
                continue
            if branch == "get":
                todo.extend([n.test, *_get_reachable(n.body)])
                continue
        for _field, value in ast.iter_fields(n):
            if isinstance(value, list):
                if value and all(isinstance(v, ast.stmt) for v in value):
                    value = _get_reachable(value)
                todo.extend(v for v in value if isinstance(v, ast.AST))
            elif isinstance(value, ast.AST):
                todo.append(value)


def runtime_files(tool_root: Path) -> dict[str, Path]:
    """dotted module name -> file, for the tool's own runtime code."""
    root = Path(tool_root)
    out = {p.stem: p for p in sorted(root.glob("*.py"))
           if not p.name.startswith(("test_", "conftest")) and p.stem not in OPAQUE}
    for d in RUNTIME_DIRS:
        for p in sorted((root / d).rglob("*.py")):
            out[".".join(p.relative_to(root).with_suffix("").parts)] = p
    return out


def shared_files() -> dict[str, Path]:
    import phronon_common
    pkg = Path(phronon_common.__file__).resolve().parent
    return {f"phronon_common.{p.stem}": p for p in sorted(pkg.glob("*.py")) if p.stem != "__init__"}


class CallGraph:
    """Functions keyed (module, name); edges by bare name, import alias or
    module attribute; writers by method name."""

    def __init__(self, files: dict[str, Path]):
        self.funcs: dict[tuple, ast.AST] = {}
        self.names: dict[str, dict] = {}       # module -> local name -> ("mod", m) | ("func", m, f)
        self.trees = {}
        for mod, path in files.items():
            try:
                self.trees[mod] = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
        for mod, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.funcs.setdefault((mod, node.name), node)
        for mod, tree in self.trees.items():
            self.names[mod] = self._imports(mod, tree)
        self.direct = {k for k, node in self.funcs.items() if self._writes(node)}
        self.edges = {k: self._callees(k[0], node) for k, node in self.funcs.items()}
        self._memo: dict[tuple, bool] = {}

    def _resolve_module(self, mod: str, node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        base = mod.split(".")[:-node.level] if "." in mod else []
        return ".".join(base + ([node.module] if node.module else [])) or None

    def _imports(self, mod: str, tree: ast.Module) -> dict:
        out = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in self.trees:
                        out[a.asname or a.name.split(".")[0]] = ("mod", a.name)
            elif isinstance(node, ast.ImportFrom):
                src = self._resolve_module(mod, node)
                if not src:
                    continue
                for a in node.names:
                    local = a.asname or a.name
                    if f"{src}.{a.name}" in self.trees:
                        out[local] = ("mod", f"{src}.{a.name}")
                    elif src in self.trees:
                        out[local] = ("func", src, a.name)
        return out

    @staticmethod
    def _sql_kind(c) -> str | None:
        """'read' / 'write' for an execute-family call whose SQL is a literal,
        'unknown' when the SQL is not visible, None for any other call."""
        if not isinstance(c, ast.Call):
            return None
        name = c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
        if name not in WRITE_METHODS:
            return None
        first = c.args[0] if c.args else None
        text = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else (
            first.values[0].value if isinstance(first, ast.JoinedStr) and first.values
            and isinstance(first.values[0], ast.Constant) else None)
        if not isinstance(text, str) or not text.strip():
            return "unknown"
        return "read" if text.lstrip().upper().startswith(READ_SQL) else "write"

    def _writes(self, node) -> bool:
        kinds = [k for k in (self._sql_kind(c) for c in walk_get(node)) if k]
        if "write" in kinds:
            return True
        if "unknown" not in kinds:
            return False
        fetches = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in FETCHES
                      for c in walk_get(node))
        return getattr(node, "name", "") in WRITE_METHODS or not fetches

    def _callees(self, mod: str, node) -> set:
        names = self.names.get(mod, {})
        out = set()
        for c in walk_get(node):
            if not isinstance(c, ast.Call):
                continue
            f = c.func
            if isinstance(f, ast.Name):
                if (mod, f.id) in self.funcs:
                    out.add((mod, f.id))
                elif names.get(f.id, ("",))[0] == "func":
                    out.add((names[f.id][1], names[f.id][2]))
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                target = names.get(f.value.id)
                if target and target[0] == "mod":
                    out.add((target[1], f.attr))
        return {k for k in out if k in self.funcs}

    def writes(self, key: tuple) -> bool:
        """True if the function writes, or reaches a function that does."""
        if key in self._memo:
            return self._memo[key]
        self._memo[key] = False                       # cycles count as "not via this path"
        result = key in self.direct or any(self.writes(c) for c in self.edges.get(key, ()))
        self._memo[key] = result
        return result


def graph_for(tool_root) -> CallGraph:
    return CallGraph({**shared_files(), **runtime_files(Path(tool_root))})


def _key(endpoint) -> tuple:
    fn = getattr(endpoint, "__wrapped__", endpoint)
    return (getattr(fn, "__module__", ""), getattr(fn, "__name__", ""))


def problems(app, tool_root, graph: CallGraph | None = None, cookie_gated=None) -> list[str]:
    """Every GET route whose HEAD does not match whether it writes.

    `cookie_gated`: {path: reason} for writing GETs that keep HEAD because the
    write needs a cookie a scanner never sends (see the module docstring)."""
    from phronon_common.adminroutes import app_routes

    graph = graph or graph_for(tool_root)
    declared = dict(cookie_gated or {})
    found, seen, matched = [], 0, set()
    for path, reason in declared.items():
        if not (isinstance(reason, str) and reason.strip()):
            found.append(f"{path}: declared cookie-gated without a reason; name the guard")
    for r in app_routes(app):
        if "GET" not in r.methods:
            continue
        key = _key(r.endpoint)
        if key not in graph.funcs:
            continue                                  # not code this graph can read (a mount, a lambda)
        seen += 1
        writes, head = graph.writes(key), "HEAD" in r.methods
        if r.path in declared:
            matched.add(r.path)
            if not writes:
                found.append(f"{r.path} ({key[0]}.{key[1]}) is declared cookie-gated but does not "
                             f"write: take it off the list")
            elif not head:
                found.append(f"{r.path} ({key[0]}.{key[1]}) is declared cookie-gated, so it keeps "
                             f"HEAD, but it does not answer HEAD: take it out of unsafe_paths")
            continue
        if writes and head:
            found.append(f"{r.path} ({key[0]}.{key[1]}) writes and answers HEAD: a scanner's probe "
                         f"would perform the write; name it in answer_head(..., unsafe_paths=), or, "
                         f"when the write needs a sign-in or a participant's cookie and scanners see "
                         f"the link, declare it cookie-gated with the guard as the reason")
        elif not writes and not head:
            found.append(f"{r.path} ({key[0]}.{key[1]}) is read-only and does not answer HEAD: a "
                         f"scanner gets 405; apply answer_head to its router")
    for path in sorted(set(declared) - matched):
        found.append(f"{path} is declared cookie-gated but is no GET route this check can read")
    if not seen:
        found.append("no GET route could be matched to its code: the check sees nothing")
    if not graph.direct:
        found.append("the detector found no writing function at all: it sees nothing")
    return found
