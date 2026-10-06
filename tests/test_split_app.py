"""testing.split_app: a split tool's tests keep one namespace and one source.

The modules here are tiny stand-ins for app.py, core.py and a router module,
loaded under the names a tool uses, so the view finds them the way it finds a
real tool's modules in sys.modules.
"""
import importlib.util
import sys
import textwrap

import pytest

from phronon_common.testing import split_app


def _tool(tmp_path, monkeypatch, files: dict):
    """Write the files, load each as the top-level module of its name, and
    return (root, {name: module})."""
    mods = {}
    for name, src in files.items():
        path = tmp_path / f"{name}.py"
        path.write_text(textwrap.dedent(src))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in files:
        spec = importlib.util.spec_from_file_location(name, tmp_path / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, mod)
        spec.loader.exec_module(mod)
        mods[name] = mod
    return tmp_path, mods


FILES = {
    "core": """
        def send(x):
            return "real"
        LIMIT = 5
    """,
    "routes_site": """
        from core import send, LIMIT
        def page():
            return send(1)
    """,
    "app": """
        import routes_site
        from core import send
        TITLE = "Tool"
    """,
}


def test_runtime_files_are_app_first_then_the_standard_names(tmp_path):
    for name in ["app", "core", "config", "db", "retention", "template_env", "routes_users",
                 "routes_site", "domain_exercise", "conftest", "create_admin", "build_brand"]:
        (tmp_path / f"{name}.py").write_text("")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "seed.py").write_text("")
    names = [p.name for p in split_app.runtime_files(tmp_path)]
    assert names == ["app.py", "config.py", "core.py", "db.py", "domain_exercise.py", "retention.py",
                     "routes_site.py", "routes_users.py", "template_env.py"]


def test_runtime_source_reads_every_module_with_app_first(tmp_path):
    (tmp_path / "app.py").write_text("A = 1\n")
    (tmp_path / "core.py").write_text("C = 2\n")
    assert split_app.runtime_source(tmp_path) == "A = 1\n\n\nC = 2\n"


def test_reading_a_name_finds_the_module_that_defines_it(tmp_path, monkeypatch):
    root, m = _tool(tmp_path, monkeypatch, FILES)
    view = split_app.view(m["app"], root)
    assert view.TITLE == "Tool"
    assert view.page is m["routes_site"].page
    assert view.LIMIT == 5
    with pytest.raises(AttributeError, match="no module of the split app defines 'nothing'"):
        view.nothing


def test_a_patch_reaches_every_module_that_holds_the_name(tmp_path, monkeypatch):
    """The bug the view exists for: after the split, `monkeypatch.setattr(app,
    "send", fake)` patched app.send while routes_site called its own copy, and
    the test silently stopped faking anything."""
    root, m = _tool(tmp_path, monkeypatch, FILES)
    view = split_app.view(m["app"], root)
    with monkeypatch.context() as mp:
        mp.setattr(view, "send", lambda x: "fake")
        assert m["routes_site"].page() == "fake"
        assert m["core"].send(1) == m["app"].send(1) == "fake"
    assert m["routes_site"].page() == "real", "undo restores every module"
    assert m["core"].send is m["app"].send is m["routes_site"].send


def test_a_module_that_rebound_the_name_is_left_alone(tmp_path, monkeypatch):
    files = dict(FILES, routes_users="""
        def send(x):
            return "its own"
    """)
    root, m = _tool(tmp_path, monkeypatch, files)
    view = split_app.view(m["app"], root)
    with monkeypatch.context() as mp:
        mp.setattr(view, "send", lambda x: "fake")
        assert m["routes_users"].send(1) == "its own"
        assert m["routes_site"].page() == "fake"


def test_deleting_a_name_removes_it_wherever_it_is_the_same_object(tmp_path, monkeypatch):
    root, m = _tool(tmp_path, monkeypatch, FILES)
    view = split_app.view(m["app"], root)
    del view.LIMIT
    assert not hasattr(m["core"], "LIMIT") and not hasattr(m["routes_site"], "LIMIT")


def test_mock_patch_object_restores_every_module(tmp_path, monkeypatch):
    """mock.patch.object finds the name through __getattr__, so on exit it
    deletes it and sets it again. Until 1.78.0 the delete took the name out of
    every module and the set then raised (TO DO FL-089)."""
    from unittest import mock
    root, m = _tool(tmp_path, monkeypatch, FILES)
    view = split_app.view(m["app"], root)
    real = m["core"].send
    with mock.patch.object(view, "send", return_value="fake"):
        assert m["routes_site"].page() == "fake"
    assert m["core"].send is m["app"].send is m["routes_site"].send is real
    assert m["routes_site"].page() == "real"
    with mock.patch.object(view, "LIMIT", 7):
        assert m["core"].LIMIT == m["routes_site"].LIMIT == 7
    assert m["core"].LIMIT == m["routes_site"].LIMIT == 5
    assert not hasattr(m["app"], "LIMIT"), "the restore adds the name nowhere new"


def test_a_module_of_the_same_name_from_elsewhere_is_not_part_of_the_view(tmp_path, monkeypatch):
    (tmp_path / "tool").mkdir()
    root, m = _tool(tmp_path / "tool", monkeypatch, {"app": "TITLE = 'Tool'\n"})
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "core.py").write_text("LIMIT = 99\n")
    spec = importlib.util.spec_from_file_location("core", other / "core.py")
    stray = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "core", stray)
    spec.loader.exec_module(stray)
    (root / "core.py").write_text("LIMIT = 5\n")      # the tool HAS a core.py, not loaded from here
    view = split_app.view(m["app"], root)
    with pytest.raises(AttributeError):
        view.LIMIT


def test_install_makes_import_app_the_view(tmp_path, monkeypatch):
    root, m = _tool(tmp_path, monkeypatch, FILES)
    view = split_app.install(m["app"], root)
    import app as imported                            # what a test file's `import app` gets
    assert imported is view and imported.page is m["routes_site"].page
    from app import LIMIT
    assert LIMIT == 5


def test_runtime_code_may_not_read_through_the_view(tmp_path, monkeypatch):
    """The view stands in for app in TESTS; runtime code that reached a name
    through `import app` would pass every test and break in production."""
    files = dict(FILES, retention="""
        def score():
            import app
            return app.LIMIT
    """)
    root, m = _tool(tmp_path, monkeypatch, files)
    split_app.install(m["app"], root)
    with pytest.raises(RuntimeError, match="retention.py reads app.LIMIT through the test view"):
        m["retention"].score()


def test_install_on_import_hands_out_the_view_on_first_import(tmp_path, monkeypatch):
    (tmp_path / "core.py").write_text("LIMIT = 5\n")
    (tmp_path / "app.py").write_text("from core import LIMIT\nTITLE = 'Tool'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for mod in ("app", "core"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    split_app.install_on_import(tmp_path)
    import app
    assert isinstance(app, split_app.SplitApp) and app.TITLE == "Tool" and app.LIMIT == 5
    monkeypatch.delitem(sys.modules, "app")
