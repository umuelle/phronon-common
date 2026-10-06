"""A tool's tests after its app.py is split by area (TO DO FL-089, README §9).

Before the split, the tests treated `app` as one namespace: `app.helper(...)`,
`monkeypatch.setattr(app, "send", fake)`, and source checks that read
`app.py`. After it, the code lives in `core.py`, `retention.py`, `routes_*.py`
and `domain_*.py`. Two helpers keep those tests honest without rewriting each:

* `view(app_module, root)` is the namespace the tests knew. Reading a name
  finds the module that defines it. SETTING one (monkeypatch) sets it in every
  module bound to that same object, as patching `app.NAME` did when one file
  held everything, so a test can never silently stop patching because the
  caller now looks the name up in another module. (OrgDesignSim's pilot moved
  every patch by hand and found 61 tests that had quietly turned into skips.)
* `install(app_module, root)` puts that view in sys.modules under the app's
  module name, for a suite whose files `import app` at the top (Whiteout:
  41 of them): `app.NAME`, `from app import NAME` and patches on `app` then
  reach the split modules without editing each file. Call it in conftest,
  right after importing app.
* `install_on_import(root)` does the same lazily, for a suite whose conftest
  must not import the app itself (Controversy Generator: no app, no threads
  at collection): the first `import app` anywhere loads the real module and
  hands out the view.
* `runtime_source(root)` is the text of every runtime module, app.py first,
  for checks that read code. One file at a time is joined with a blank line,
  so a pattern that does not span files behaves as before.

No pytest import here (see __init__.py).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: Standard module names (README §9); app.py comes first wherever it matters.
_RUNTIME = re.compile(r"(app|core|config|db|retention|template_env|routes_\w+|domain\w*)")


def runtime_files(root) -> list[Path]:
    """app.py first, then the tool's other top-level runtime modules by name."""
    root = Path(root)
    files = sorted(p for p in root.glob("*.py") if _RUNTIME.fullmatch(p.stem))
    return sorted(files, key=lambda p: (p.name != "app.py", p.name))


def runtime_source(root) -> str:
    return "\n\n".join(p.read_text(encoding="utf-8") for p in runtime_files(root))


class SplitApp:
    """One namespace over a split app's modules (see the module docstring).

    For TESTS only, and it enforces that: a read from the tool's own runtime
    code (its top-level modules, services/, modules/, scripts/) raises. Whiteout's
    retention.py read `app._exercise` through a lazy `import app`; after the
    split that name was no longer on app, production would have caught the
    AttributeError and kept scores as NULL, and with this view installed every
    test would still have passed."""

    def __init__(self, modules, root=None):
        object.__setattr__(self, "_modules", tuple(modules))
        object.__setattr__(self, "_root", Path(root).resolve() if root else None)
        #: name -> the modules a delete took it from (see __setattr__).
        object.__setattr__(self, "_deleted", {})

    def _refuse_runtime_caller(self, name):
        if self._root is None:
            return
        caller = Path(sys._getframe(2).f_code.co_filename).resolve()
        if caller.parent == self._root or (caller.is_relative_to(self._root) and
                                           caller.relative_to(self._root).parts[0] in ("services", "modules", "scripts")):
            raise RuntimeError(
                f"{caller.name} reads app.{name} through the test view; runtime code must import "
                f"{name} from the module that defines it (app.py is only the composition root)")

    def __getattr__(self, name):
        self._refuse_runtime_caller(name)
        for m in self._modules:
            if name in vars(m):
                return vars(m)[name]
        raise AttributeError(f"no module of the split app defines {name!r}")

    def __setattr__(self, name, value):
        try:
            current = getattr(self, name)
        except AttributeError:
            # mock.patch.object restores a name it did not find in the view's
            # own __dict__ by deleting it and setting it again: put it back in
            # the modules the delete took it from.
            if name not in self._deleted:
                raise
            for m in self._deleted.pop(name):
                setattr(m, name, value)
            return
        for m in self._modules:
            if name in vars(m) and vars(m)[name] is current:
                setattr(m, name, value)

    def __delattr__(self, name):
        current = getattr(self, name)
        held = [m for m in self._modules if name in vars(m) and vars(m)[name] is current]
        for m in held:
            delattr(m, name)
        self._deleted[name] = held

    @property
    def modules(self) -> tuple:
        """The split app's modules, app first: for a test that scans every
        function the app has (`vars(app)` sees the view, not the code)."""
        return self._modules

    def __repr__(self):
        return f"<split app: {', '.join(m.__name__ for m in self._modules)}>"


def view(app_module, root) -> SplitApp:
    """The split app's modules that are loaded, app first, as one namespace."""
    root = Path(root).resolve()
    mods = [app_module]
    for p in runtime_files(root)[1:]:
        m = sys.modules.get(p.stem)
        if m is not None and Path(getattr(m, "__file__", "") or "").resolve().parent == root:
            mods.append(m)
    return SplitApp(mods, root)


def install(app_module, root) -> SplitApp:
    """The view, also as sys.modules[app's name], so later imports get it."""
    v = view(app_module, root)
    sys.modules[app_module.__name__] = v
    return v


def install_on_import(root, name: str = "app") -> None:
    """Make the first `import app` (from root) return the view (see the module
    docstring). Python returns sys.modules[name] once a module has run, so the
    loader runs the real app.py and then puts the view in its place."""
    import importlib.abc
    import importlib.machinery

    root = Path(root).resolve()

    class _Loader(importlib.abc.Loader):
        def __init__(self, real):
            self.real = real

        def create_module(self, spec):
            return self.real.create_module(spec)

        def exec_module(self, module):
            self.real.exec_module(module)
            sys.modules[name] = view(module, root)

    class _Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname != name:
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, [str(root)])
            if spec is not None:
                spec.loader = _Loader(spec.loader)
            return spec

    if not any(type(f).__name__ == "_Finder" and getattr(f, "_root", None) == root for f in sys.meta_path):
        finder = _Finder()
        finder._root = root
        sys.meta_path.insert(0, finder)
