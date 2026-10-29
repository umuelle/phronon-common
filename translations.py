"""Translation files: one loader and one ``t()`` for the fleet (FL-098 point 7).

Three tools translate their participant pages from ``i18n/<lang>.json``: Layoff
(ten languages), Whiteout and Polarity Profiler (English and German). The
three files have the same shape (nested objects, dotted keys, ``{name}``
placeholders filled by ``str.format``) and the same template API (``t()``,
``locale``), and each tool had its own loader.

WHAT EACH HAD (checked 12 October 2026)
  * Layoff (core.py): read the file on every render, no cache; a missing or
    broken file meant the whole English file; no per-string fallback, so a
    key missing from de.json printed the key itself; ``str.format`` even on a
    list when keyword arguments were given (a TypeError); plain ``str``.
  * Whiteout (core.py): the same, plus list indexes in a key
    (``demographics.age_bands.0``, added after the demographics page shipped
    showing the keys on 3 August 2026) and formatting only of strings. Its
    own code mutates the dict it loads (it writes a version's scenario
    overrides into ``translations['rank']``), which is harmless only because
    every call read a fresh copy from disk.
  * Polarity Profiler (i18n.py): cached; each language deep-merged over
    English, so a missing string falls back to English PER STRING (whole
    sections go to the browser as JSON, where a hole shows as ``undefined``);
    a lookup that misses in the merged data tries English again; the
    TEMPLATE translator returns ``markupsafe.Markup`` and formats with
    ``Markup.format``, which escapes every interpolated value. Two dozen PP
    strings carry their own markup and render through ``| safe``; before
    16 August 2026 that let an educator's class name (``<script>``) through
    as stored HTML on a page a participant reaches from an e-mail.

WHAT THE SHARED ONE DOES, with PP's behaviour as the floor
  * ``Catalog(directory, languages)`` loads ``<lang>.json`` for the listed
    languages only (anything else is the default language, so a ``lang``
    from a query string never names a file), parses each once, and merges it
    over the default language (English) per string. Lists are replaced
    whole, never merged by position: Layoff's option arrays are parallel to
    a fixed value list and its code checks their length.
  * The default language's file missing or broken raises (PP); another
    language's missing or broken file logs a warning and reads as English.
  * ``Catalog.load(lang)`` returns a fresh copy, so a caller that edits the
    dict (Whiteout) cannot change what the next request sees. The copy is
    parsed from cached JSON text, which is several times faster than a deep
    copy of the same tree; ``Catalog.as_json(lang)`` hands out that text for
    a page that gives its strings to the browser (Layoff's ``i18n_json``).
  * ``t(key, **values)``: dotted keys through objects and list indexes
    (Whiteout); a miss tries the fallback (English) and then returns the key
    itself (all three), logging the first miss of each key once; a value
    that is not a string (a list, an object) comes back as it is (PP,
    Whiteout); ``str.format`` runs only on strings and only when values are
    given (all three: "{{" stays doubled without values).
  * ``html=True`` is PP's template translator: the result is ``Markup``, the
    translation's own markup is kept, every interpolated value is escaped,
    and a value that is already ``Markup`` (one ``t()`` nested in another)
    passes through. ``html=False`` returns ``str``, for mail subjects, JSON
    and logs, where an escaped "&amp;" would be wrong.
  * A translation whose placeholders do not match the values given (a
    translator's typo, ``{nmae}``) used to raise and turn the page into a
    500 in all three tools. It now logs with the traceback and falls back to
    the English string for that key; if that fails too, the text is returned
    unformatted.

PLURALS are not the loader's business in any of the three: the code picks
the key (``scenario.remaining_one`` / ``remaining_many``,
``group.away_others_one`` / ``_many``).

WHICH TRANSLATOR WHERE. A template that pipes ``t()`` through ``| safe`` must
use ``html=True``; a plain-``str`` translator must never meet ``| safe``,
since its interpolated values are not escaped. ``html=True`` output is
trusted HTML: inside an attribute, a translation that contains a double
quote ends the attribute, so in attributes use the ``html=False`` translator
(Jinja's autoescape then escapes the whole value) and in a ``<script>`` use
``| tojson``.

``markupsafe`` (Jinja's, in the ``web`` extra) is imported only when an
``html=True`` translator is built, so a script or retention job that sends a
translated mail needs nothing outside the standard library.
"""
from __future__ import annotations

import copy
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional

if TYPE_CHECKING:
    import os

logger = logging.getLogger(__name__)

_MISSING = object()
_FORMAT_ERRORS = (KeyError, IndexError, ValueError, AttributeError, TypeError)

# Keys already reported as missing, so a missing string logs once per process,
# not once per page view. Bounded: a key built from data must not grow it.
_reported: set[str] = set()
_REPORT_LIMIT = 1000


def deep_merge(base: Mapping, overlay: Mapping) -> dict:
    """``overlay`` wins at every leaf; keys it omits keep ``base``'s value.

    Objects merge recursively; lists and strings are replaced whole. Returns
    a new structure that shares nothing mutable with either argument."""
    merged = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def lookup(translations: Any, key: str, default: Any = None) -> Any:
    """The value at a dotted key: object members and list indexes."""
    value = translations
    for part in key.split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return default
    return value


def _report_missing(key: str) -> None:
    if key in _reported or len(_reported) >= _REPORT_LIMIT:
        return
    _reported.add(key)
    logger.warning("translations: no string for %r; showing the key", key)


def make_translator(translations: Mapping, *, fallback: Optional[Mapping] = None,
                    html: bool = False) -> Callable[..., Any]:
    """``t(key, **values)`` over ``translations``, missing keys from ``fallback``.

    ``fallback`` is normally the English data; ``Catalog.translator`` passes
    it. A tool that builds its own dict (Whiteout merges a session's frozen
    content over the current file) passes its dict and the English data here.
    """
    if html:
        from markupsafe import Markup
    else:
        Markup = None  # type: ignore[misc,assignment]  # read only when html is True

    def _format(text: str, values: dict[str, Any]) -> str:
        template = Markup(text) if html else text
        return template.format(**values) if values else template

    def t(key: str, **values: Any) -> Any:
        value = lookup(translations, key, _MISSING)
        if value is _MISSING and fallback is not None:
            value = lookup(fallback, key, _MISSING)
        if value is _MISSING:
            _report_missing(key)
            return key
        if not isinstance(value, str):
            return value
        try:
            return _format(value, values)
        except _FORMAT_ERRORS:
            logger.exception("translations: %r does not take the values %s",
                             key, sorted(values))
        english = lookup(fallback, key) if fallback is not None else None
        if isinstance(english, str) and english != value:
            try:
                return _format(english, values)
            except _FORMAT_ERRORS:
                logger.exception("translations: the fallback for %r fails too", key)
        return Markup(value) if html else value

    return t


class Catalog:
    """A tool's ``i18n/`` folder: ``<lang>.json`` per language, English first.

    ``languages`` is what the tool speaks (its SUPPORTED_LANGUAGES); the
    first one, or ``default``, is canonical and must exist.
    """

    def __init__(self, directory: str | os.PathLike[str], languages: Iterable[str] = ("en",), *,
                 default: Optional[str] = None):
        self.directory = Path(directory)
        self.languages = tuple(languages)
        if not self.languages:
            raise ValueError("a catalog needs at least one language")
        self.default = default or self.languages[0]
        if self.default not in self.languages:
            raise ValueError("default language %r is not in %r"
                             % (self.default, self.languages))
        self._cache: dict[str, dict[str, Any]] = {}
        self._json: dict[str, str] = {}
        self._lock = threading.Lock()

    def language(self, lang: Optional[str]) -> str:
        """``lang`` if this tool speaks it, else the default language."""
        return lang if lang in self.languages else self.default

    def _read(self, lang: str) -> dict:
        path = self.directory / ("%s.json" % lang)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("top level is not an object")
            return data
        except (OSError, ValueError):
            if lang == self.default:
                raise
            logger.warning("translations: cannot load %s; using %s",
                           path, self.default, exc_info=True)
            return {}

    def _data(self, lang: Optional[str]) -> dict:
        """The merged, cached data. Shared: never hand it to a caller."""
        lang = self.language(lang)
        with self._lock:
            if lang not in self._cache:
                data = self._read(lang)
                if lang != self.default:
                    data = deep_merge(self._data_unlocked(self.default), data)
                self._cache[lang] = data
            return self._cache[lang]

    def _data_unlocked(self, lang: str) -> dict:
        if lang not in self._cache:
            self._cache[lang] = self._read(lang)
        return self._cache[lang]

    def as_json(self, lang: Optional[str]) -> str:
        """The language's strings over English as JSON text (``json.dumps``
        with its defaults), made once per language."""
        lang = self.language(lang)
        text = self._json.get(lang)
        if text is None:
            text = json.dumps(self._data(lang))
            with self._lock:
                self._json[lang] = text
        return text

    def load(self, lang: Optional[str]) -> dict:
        """The language's strings over English, as a copy the caller may edit."""
        data: dict[str, Any] = json.loads(self.as_json(lang))
        return data

    def translator(self, lang: Optional[str], *, html: bool = False) -> Callable[..., Any]:
        """``t()`` for one language; ``html=True`` for templates (see module doc)."""
        return make_translator(self._data(lang), fallback=self._data(self.default),
                               html=html)

    def clear(self) -> None:
        """Forget the parsed files (tests; a file changed under a running app)."""
        with self._lock:
            self._cache.clear()
            self._json.clear()
