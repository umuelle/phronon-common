"""The password policy has ONE home, on the server and on the page.

Both halves below were byte-identical copies in all eight tools before
4 September 2026, and both exist because the copies had already drifted once.

SERVER SIDE (re-audit V1, 10 August 2026). Every set-password path once carried
its own `len(pw) < MIN_LENGTH` and its own "must be at least N characters" —
nine copies of a rule with one home. When the fleet gained an UPPER bound
(bcrypt cannot hash more than 72 bytes, and slicing silently made two long
passwords equivalent), every one of those copies would have gone on accepting
what bcrypt cannot store, and telling a too-LONG password it was too short.

TEMPLATE SIDE. Every tool hard-coded "at least 12 characters", so when the
policy gained the 72-byte ceiling the forms went on promising only the minimum
and then rejected long passphrases for a rule they had never mentioned. Worse,
Moral Mirror's three forms still said "min 10" with `minlength="10"` —
advertising, and client-side enforcing, a minimum two BELOW what its own server
required, so the form accepted what the server refused.

Source-level throughout: no database, no app import, so these can never skip.
A skipped test in a green run is indistinguishable from a passing one.

No pytest import here on purpose — see phronon_common/testing/__init__.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from phronon_common.passwords import MIN_LENGTH

# "min 12", "minimum 12", "at least 12 characters" — any restatement of the
# number that should have come from the shared hint.
_RESTATES_RULE = re.compile(
    r"(?:min(?:imum)?\.?\s*|at least\s*)\d+\s*(?:characters)?", re.IGNORECASE)
_MINLENGTH = re.compile(r'minlength="(\d+)"')
_HAND_ROLLED_LENGTH = re.compile(
    r"len\([^)]*(?:password|pw)[^)]*\)\s*[<>]=?\s*\d+", re.IGNORECASE)
_RESTATES_MINIMUM = re.compile(
    r"len\([^)]*\)\s*<\s*(?:pw_policy\.MIN_LENGTH|config\.MIN_PASSWORD_LENGTH)")
_HAND_WRITTEN_MESSAGE = re.compile(r"[Pp]assword must be at (?:least|most)[^\"']*")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def _code(app_py: Path | str) -> str:
    """app.py with comments stripped — a comment quoting the old message is
    not a restatement of it."""
    return re.sub(r"#[^\n]*", "", Path(app_py).read_text(encoding="utf-8"))


def password_setting_forms(root: Path | str) -> list[Path]:
    """Every template where a password is SET.

    Mail templates are excluded: they carry a link, not an input.
    """
    root = Path(root)
    return sorted(
        p for p in (root / "templates").rglob("*.html")
        if "new_password" in p.read_text(encoding="utf-8", errors="replace")
        and "email" not in p.parts
    )


# ── the page ────────────────────────────────────────────────────────────────

def assert_form_asks_for_the_shared_hint(template: Path | str, root: Path | str) -> None:
    src = Path(template).read_text(encoding="utf-8")
    assert "password_hint" in src, (
        f"{_rel(template, root)} sets a password but never states the rule, "
        f"or restates it by hand")


def assert_form_does_not_restate_the_rule(template: Path | str, root: Path | str) -> None:
    src = Path(template).read_text(encoding="utf-8")
    bad = _RESTATES_RULE.findall(src)
    assert not bad, f"{_rel(template, root)} restates the rule: {bad}"


def assert_minlength_matches_the_policy(template: Path | str, root: Path | str) -> None:
    """A minlength BELOW the policy makes the browser accept what the server
    refuses; above it makes the browser refuse what the server allows."""
    src = Path(template).read_text(encoding="utf-8")
    for value in _MINLENGTH.findall(src):
        assert int(value) == MIN_LENGTH, (
            f"{_rel(template, root)} enforces minlength={value}, "
            f"policy is {MIN_LENGTH}")


# ── the server ──────────────────────────────────────────────────────────────

def assert_no_hand_rolled_length_check(app_py: Path | str) -> None:
    src = _code(app_py)
    bad = _HAND_ROLLED_LENGTH.findall(src)
    assert not bad, f"restates the length rule: {bad}"
    bad2 = _RESTATES_MINIMUM.findall(src)
    assert not bad2, f"restates the minimum instead of asking the policy: {bad2}"


def assert_no_hand_written_password_message(app_py: Path | str) -> None:
    src = _code(app_py)
    bad = _HAND_WRITTEN_MESSAGE.findall(src)
    assert not bad, (
        f"hard-coded password message: {bad} — it cannot know WHICH rule "
        f"failed, so a too-long password gets told it is too short")


def assert_the_policy_is_reachable(app_py: Path | str) -> None:
    """A check that inspects nothing passes vacuously."""
    src = _code(app_py)
    assert "validate_password" in src or "_pw_ok" in src, (
        "this app validates passwords somewhere, or the test is pointed wrong")
