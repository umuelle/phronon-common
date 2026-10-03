"""Load and check a tool's OWN legal content (4 October 2026).

Each tool keeps what its notice says about ITS data in its own repository,
`legal_content/notice.json`, and passes it to the shared legal router:

    from phronon_common.legal_content import load_legal_config
    from phronon_common.legal import build_legal_router

    LEGAL = load_legal_config("whiteout", BASE_DIR / "legal_content" / "notice.json")
    app.include_router(build_legal_router("whiteout", config=LEGAL))
    NOTICE_VERSION = LEGAL["notice_version"]

WHY: until now all nine tools' entries lived in `legal_conf.py`, inside this
package, so changing one sentence of one tool's notice was a release of the
whole shared package: a tag, nine pin commits, a server check, activation and
a restart of every service. 13 of 39 releases in September/October changed
that file, 8 of them nothing else. With the content in the tool, a notice
change is one deploy of that tool.

What stays shared: the templates (`legal_templates/`, the operator,
infrastructure and rights text, which no tool may restate), the router, this
loader, and the fleet-wide defaults below. What moves: the per-tool entry,
field for field as it was in `legal_conf.TOOLS`.

The file is trusted repository content (it carries reviewed HTML fragments),
loaded ONCE at startup from an explicit path: no search, no network, no shared
mutable state. Anything wrong with it stops the application from starting,
which a deploy's boot check turns into a refused deploy.

`legal_conf.TOOLS` stays, frozen, as the content of tools that have not
migrated yet (and of earlier tool versions a rollback may restore). It is not
an editing location for a migrated tool.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SCHEMA_VERSION = 1

#: Fleet-wide facts, not per-tool content (the operator's infrastructure).
FLEET_DEFAULTS = {
    "log_retention_days": 14,   # nginx logrotate on the server; see legal_conf.py
}

LANGUAGES = {"en", "de"}

#: Prose fields: {language: reviewed HTML or text}. English always; German
#: whenever the tool serves German, EXCEPT `provenance` (the source credits),
#: which every German-serving tool publishes in English and the templates fall
#: back to (state on 4 October 2026, kept as it was).
PROSE = ("purpose", "collect", "basis", "retention", "access", "erasure", "provision", "provenance")
PROSE_ENGLISH_ONLY_OK = {"provenance"}

REQUIRED = {
    "schema_version": int, "tool_key": str, "tool_name": str, "domain": str,
    "languages": list, "notice_version": str, "last_updated": str,
    "art9": bool, "cookies": list,
    **{f: dict for f in PROSE},
}
OPTIONAL = {
    "cookies_de": list,      # required when the tool serves German
    "contact_email": str,    # default info@<domain>
    "is_hub": bool,          # default False
    "name_suite": bool,      # default True; Decision Room says False
}
COOKIE_AUDIENCES = {"participants", "backoffice", "all"}


class LegalConfigError(ValueError):
    """The tool's legal content is missing or malformed: the app must not start."""


def check_config(raw: dict, tool_key: str) -> list[str]:
    """Every problem with one tool's legal content, as plain sentences."""
    out: list[str] = []
    if not isinstance(raw, dict):
        return ["the file does not hold a JSON object"]
    if raw.get("schema_version") != SCHEMA_VERSION:
        out.append(f"schema_version is {raw.get('schema_version')!r}, this package reads {SCHEMA_VERSION}")
    if raw.get("tool_key") != tool_key:
        out.append(f"tool_key is {raw.get('tool_key')!r}, the application asked for {tool_key!r}")
    for field, kind in REQUIRED.items():
        if field not in raw:
            out.append(f"missing field {field!r}")
        elif not isinstance(raw[field], kind) or (kind is int and isinstance(raw[field], bool)):
            out.append(f"{field!r} must be a {kind.__name__}")
    for field, kind in OPTIONAL.items():
        if field in raw and not isinstance(raw[field], kind):
            out.append(f"{field!r} must be a {kind.__name__}")
    unknown = sorted(set(raw) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        out.append(f"unknown field(s) {', '.join(unknown)} (a typo, or a field this package does not render)")
    if out:
        return out

    langs = raw["languages"]
    if not langs or "en" not in langs or set(langs) - LANGUAGES:
        out.append(f"languages must include 'en' and only {sorted(LANGUAGES)}: {langs}")
    for value, name in ((raw["notice_version"], "notice_version"), (raw["last_updated"], "last_updated")):
        if not value.strip():
            out.append(f"{name} is empty")
    if not raw["domain"] or "/" in raw["domain"] or raw["domain"] != raw["domain"].lower():
        out.append(f"domain {raw['domain']!r} is not a bare lower-case host name")
    for field in PROSE:
        texts = raw[field]
        if set(texts) - LANGUAGES:
            out.append(f"{field!r} has a language this package does not serve: {sorted(set(texts) - LANGUAGES)}")
        if not isinstance(texts.get("en"), str) or not texts["en"].strip():
            out.append(f"{field!r} has no English text")
        if "de" in langs and field not in PROSE_ENGLISH_ONLY_OK and not (
                isinstance(texts.get("de"), str) and texts["de"].strip()):
            out.append(f"{field!r} has no German text, and the tool serves German")
        if any(not isinstance(v, str) for v in texts.values()):
            out.append(f"{field!r} must map languages to text")
    out += _check_cookies(raw["cookies"], "cookies")
    if "de" in langs:
        if "cookies_de" not in raw:
            out.append("the tool serves German but has no 'cookies_de' table")
        else:
            out += _check_cookies(raw["cookies_de"], "cookies_de")
            if [r[0] for r in raw["cookies_de"]] != [r[0] for r in raw["cookies"]]:
                out.append("cookies_de must list the same cookies, in the same order, as cookies")
    elif "cookies_de" in raw:
        out.append("'cookies_de' is given, but the tool does not serve German")
    return out


def _check_cookies(rows, field: str) -> list[str]:
    out = []
    if not rows:
        return [f"{field!r} is empty: every tool sets at least one cookie"]
    for i, row in enumerate(rows):
        if not (isinstance(row, list) and len(row) == 4 and all(isinstance(c, str) and c.strip() for c in row)):
            out.append(f"{field}[{i}] must be [name, description, lifetime, audience], all non-empty text")
        elif field == "cookies" and row[3] not in COOKIE_AUDIENCES:
            # The English table's audience is a key the code reads; the
            # German table prints it translated ("Teilnehmende", "alle").
            out.append(f"{field}[{i}] audience {row[3]!r} is not one of {sorted(COOKIE_AUDIENCES)}")
    return out


def finish(raw: dict) -> dict:
    """The render-ready configuration: the file's content plus the defaults the
    templates expect, in a fresh copy that shares nothing with anyone."""
    cfg = copy.deepcopy(raw)
    cfg["key"] = cfg.pop("tool_key")
    cfg.pop("schema_version")
    cfg.setdefault("contact_email", f"info@{cfg['domain']}")
    cfg.setdefault("is_hub", False)
    for k, v in FLEET_DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


def load_legal_config(tool_key: str, path) -> dict:
    """Read, check and finish a tool's legal content. Raises LegalConfigError."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LegalConfigError(f"{tool_key}: no legal content at {path}") from None
    except json.JSONDecodeError as e:
        raise LegalConfigError(f"{tool_key}: {path} is not valid JSON ({e})") from None
    problems = check_config(raw, tool_key)
    if problems:
        raise LegalConfigError(f"{tool_key}: {path}:\n  - " + "\n  - ".join(problems))
    return finish(raw)


def export_legacy_entry(tool_key: str) -> dict:
    """One `legal_conf.TOOLS` entry as the content of a tool's notice.json:
    the migration (4 October 2026) and its parity check use it. Explicit
    notice_version and last_updated; nothing the templates read changes."""
    from . import legal_conf
    entry = copy.deepcopy(legal_conf.TOOLS[tool_key])
    entry.setdefault("notice_version", legal_conf.NOTICE_VERSION)
    entry.setdefault("last_updated", legal_conf.LAST_UPDATED)
    for k in ("cookies", "cookies_de"):
        if k in entry:
            entry[k] = [list(r) for r in entry[k]]
    entry.pop("key", None)
    out = {"schema_version": SCHEMA_VERSION, "tool_key": tool_key}
    out.update(entry)
    return out
