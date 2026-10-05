"""routing.answer_head and testing.head_safety: HEAD for read-only GETs only.

The detector is pinned on synthetic modules (every shape that decides a
verdict), then run end to end on a small FastAPI app split into a router
module, the way a tool looks after its app.py split.
"""
import ast
import sys
import textwrap
from pathlib import Path

import pytest

from phronon_common.testing import head_safety as hs


def _graph(tmp_path, files: dict) -> hs.CallGraph:
    paths = {}
    for name, src in files.items():
        p = tmp_path / (name.replace(".", "/") + ".py")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src))
        paths[name] = p
    return hs.CallGraph(paths)


@pytest.mark.parametrize("body, writes", [
    ('db.execute("UPDATE t SET x=1")', True),
    ('db.execute(sql, (1,))', True),                         # SQL not visible: a write
    ('db.execute(f"UPDATE {t} SET x=1")', True),
    ('db.execute_many(stmts)', True),
    ('db.db_execute("INSERT INTO t VALUES (1)")', True),
    ('db.execute_rowcount("DELETE FROM t")', True),
    ('db.execute("SELECT 1")', False),                       # a literal read
    ('db.execute(f"SELECT * FROM {t}")', False),
    ('db.query_one("SELECT 1")', False),                     # read helpers by name
    ('return 1', False),
])
def test_what_counts_as_a_write(tmp_path, body, writes):
    g = _graph(tmp_path, {"m": f"def f():\n    {body}\n"})
    assert g.writes(("m", "f")) is writes


def test_a_read_helper_with_hidden_sql_is_a_read_and_a_write_helper_is_not(tmp_path):
    g = _graph(tmp_path, {"m": """
        def _db_query_one(sql, params):
            cur = conn.cursor(); cur.execute(sql, params); return cur.fetchone()
        def execute(sql, params):
            cur = conn.cursor(); cur.execute(sql, params); return cur.fetchall()
        def page():
            return _db_query_one("SELECT 1", ())
        def save():
            execute("anything", ())
    """})
    assert not g.writes(("m", "page")) and not g.writes(("m", "_db_query_one"))
    assert g.writes(("m", "execute")) and g.writes(("m", "save"))


def test_writes_are_followed_across_modules_and_aliases(tmp_path):
    g = _graph(tmp_path, {
        "retention": "def postpone(i):\n    db.execute('UPDATE c SET d=1 WHERE id=%s', (i,))\n",
        "helpers": "import retention\ndef via_module(i):\n    retention.postpone(i)\n",
        "routes_x": """
            from retention import postpone as postpone_session
            from helpers import via_module
            def a(i):
                postpone_session(i)
            def b(i):
                via_module(i)
            def c():
                return 1
        """})
    assert g.writes(("routes_x", "a")) and g.writes(("routes_x", "b"))
    assert not g.writes(("routes_x", "c"))


def test_only_branches_a_get_can_take_are_followed(tmp_path):
    g = _graph(tmp_path, {"m": """
        def both(request):
            if request.method == "POST":
                db.execute("UPDATE t SET x=1")
            return 1
        def get_branch(request):
            if request.method == "GET":
                return 1
            else:
                db.execute("UPDATE t SET x=1")
        def not_post(request):
            if request.method != "POST":
                return 1
            db.execute("UPDATE t SET x=1")
        def round2_door(request):                    # Layoff's /round2/enter, in miniature
            if request.method == "GET":
                if request.cookies.get("p"):
                    return 2
                return 1
            db.execute("UPDATE t SET admitted=1")
        def falls_through(request):
            if request.method == "GET":
                x = 1
            db.execute("UPDATE t SET x=1")
    """})
    assert not g.writes(("m", "both")) and not g.writes(("m", "get_branch"))
    assert not g.writes(("m", "not_post")), "a GET returns before the write"
    assert not g.writes(("m", "round2_door")), "every GET path returns before the write"
    assert g.writes(("m", "falls_through")), "a GET branch that does not return falls through to the write"


def test_a_helper_defined_inside_runs_only_when_called(tmp_path):
    g = _graph(tmp_path, {"m": """
        def reset(request):                          # Controversy Generator's reset handler, in miniature
            def _mark_used(token):
                db.execute("UPDATE tokens SET used=1 WHERE t=%s", (token,))
            if request.method == "GET":
                return 1
            _mark_used(request.form["t"])
        def get_calls_it(request):
            def _mark_used(token):
                db.execute("UPDATE tokens SET used=1 WHERE t=%s", (token,))
            _mark_used(1)
    """})
    assert not g.writes(("m", "reset")), "the write is only reached on POST"
    assert g.writes(("m", "get_calls_it")), "a defined helper that IS called on GET still counts"


def test_the_tools_db_layer_is_judged_by_name(tmp_path):
    (tmp_path / "db.py").write_text("def db_query(sql):\n    cur.execute(sql)\n    return cur.fetchall()\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    assert "db" not in hs.runtime_files(tmp_path) and "app" in hs.runtime_files(tmp_path)


# ── end to end: a split app ──────────────────────────────────────────────────
def test_problems_on_a_split_app(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import APIRouter, FastAPI
    from phronon_common.routing import answer_head

    (tmp_path / "routes_area.py").write_text(textwrap.dedent("""
        from fastapi import APIRouter
        router = APIRouter()
        @router.get("/read")
        def read_page():
            return {"ok": 1}
        @router.get("/init")
        def init_page():
            db.execute("UPDATE p SET x=1")
            return {"ok": 1}
        @router.get("/forgot")
        def forgot_page():
            return {"ok": 1}
    """))
    monkeypatch.syspath_prepend(str(tmp_path))

    def build(unsafe):
        sys.modules.pop("routes_area", None)          # a fresh router: answer_head changes it in place
        import routes_area
        app = FastAPI()
        app.include_router(answer_head(routes_area.router, unsafe_paths=unsafe))
        return app

    assert hs.problems(build({"/init"}), tmp_path) == []
    leaked = hs.problems(build(set()), tmp_path)
    assert len(leaked) == 1 and "/init" in leaked[0] and "writes and answers HEAD" in leaked[0]
    needless = hs.problems(build({"/init", "/read"}), tmp_path)
    assert len(needless) == 1 and "/read" in needless[0] and "does not answer HEAD" in needless[0]

    # cookie-gated: the write needs a sign-in, scanners see the link, it keeps HEAD
    gated = {"/init": "writes only after require_educator; a scanner is not signed in"}
    assert hs.problems(build(set()), tmp_path, cookie_gated=gated) == []
    stale = hs.problems(build(set()), tmp_path, cookie_gated={**gated, "/read": "x", "/gone": "y"})
    assert any("/read" in s and "does not write" in s for s in stale), stale
    assert any("/gone" in s and "no GET route" in s for s in stale), stale
    both = hs.problems(build({"/init"}), tmp_path, cookie_gated=gated)
    assert len(both) == 1 and "take it out of unsafe_paths" in both[0], both
    unexplained = hs.problems(build(set()), tmp_path, cookie_gated={"/init": " "})
    assert len(unexplained) == 1 and "without a reason" in unexplained[0], unexplained
    sys.modules.pop("routes_area", None)


def test_answer_head_leaves_post_routes_and_unsafe_paths_alone():
    pytest.importorskip("fastapi")
    from fastapi import APIRouter
    from phronon_common.routing import answer_head
    r = APIRouter()
    r.get("/a")(lambda: 1)
    r.get("/b")(lambda: 1)
    r.post("/c")(lambda: 1)
    answer_head(r, unsafe_paths={"/b"})
    methods = {route.path: route.methods for route in r.routes}
    assert "HEAD" in methods["/a"] and "HEAD" not in methods["/b"] and "HEAD" not in methods["/c"]


def test_the_detector_reads_this_package(tmp_path):
    """The shared modules are part of every graph: a tool that writes through
    phronon_common (participant, passkeys, once) must not read as read-only."""
    g = hs.CallGraph(hs.shared_files())
    assert any(m.startswith("phronon_common.") for m, _ in g.direct), "no shared writer found"
