"""A tool that serves German publishes its cookie table in German.

THE RULE (owner, 19 August 2026). Until that day there was ONE cookie list per
tool and the German pages printed a German heading row — Name · Zweck ·
Lebensdauer · Betrifft — over English cells. It survived as long as the
lifetime column held nothing but "4 hours", which a German reader can read
anyway. On 19 August that cell became "6 hours (educators) / 3 hours
(administrators)": a sentence, not a value.

So: **`languages` containing "de" obliges the tool to carry `cookies_de`**, and
these tests are what makes that an obligation rather than an intention. They
are written for the TENTH tool — the one nobody has built yet — because the
three that exist today were translated by hand and are correct by inspection.
Adding "de" to a tool's languages without translating its table fails here,
before a deploy discovers it and before a reader does.

WHY EACH CHECK EXISTS, since none of them is obvious:

  * Names must match position for position. A cookie name is a literal the
    browser sends; it is not translatable, and a German table that renames one
    describes a cookie that does not exist.
  * Lifetimes must parse to the SAME seconds. This is the pairing that decays:
    the German cell is edited by someone reading German prose, the `max_age` by
    someone reading Python, and nothing sits between them.
  * A German cell must actually parse. `lifetime_seconds` treats an unknown
    unit word as "no number published", which SKIPS the row — so a typo in a
    unit does not fail a check, it removes one. That is the failure mode this
    file exists to make impossible.
  * The German text must not be the English text. A half-done translation is
    the likeliest way this regresses, and it looks complete from a distance.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import legal_conf  # noqa: E402
from phronon_common.legal import render_legal  # noqa: E402
from phronon_common.legal_conf import lifetime_seconds  # noqa: E402

ALL_TOOLS = sorted(legal_conf.TOOLS)

#: The agreed German vocabulary for the "Betrifft" column. Kept short and
#: closed: a fourth value would mean a fourth audience, which is a decision
#: about the notice, not a translation choice.
GERMAN_AUDIENCES = {"Teilnehmende", "Backoffice", "alle"}


def _german_tools():
    return [k for k in ALL_TOOLS if "de" in legal_conf.get_tool(k)["languages"]]


def test_at_least_one_tool_serves_german():
    """If this ever fails, the rest of the file is passing vacuously."""
    assert _german_tools(), "no tool declares German — these checks assert nothing"


@pytest.mark.parametrize("key", ALL_TOOLS)
def test_german_tools_carry_a_german_table_and_others_do_not(key):
    cfg = legal_conf.get_tool(key)
    serves_german = "de" in cfg["languages"]
    has_table = bool(cfg.get("cookies_de"))
    if serves_german:
        assert has_table, (
            f"{key} serves German at /de/cookies but has no `cookies_de` — its "
            f"German page would print English cells under a German heading row, "
            f"which is what this rule replaced"
        )
    else:
        assert not has_table, (
            f"{key} carries `cookies_de` but does not declare German, so nothing "
            f"renders it. Either add 'de' to its languages or drop the table — an "
            f"unrendered translation is one nobody proof-reads and everybody trusts"
        )


@pytest.mark.parametrize("key", _german_tools())
def test_the_two_tables_describe_the_same_cookies_in_the_same_order(key):
    cfg = legal_conf.get_tool(key)
    en = [row[0] for row in cfg["cookies"]]
    de = [row[0] for row in cfg["cookies_de"]]
    assert de == en, (
        f"{key}: a cookie name is a literal the browser sends, not something to "
        f"translate or reorder.\n  EN: {en}\n  DE: {de}"
    )


@pytest.mark.parametrize("key", _german_tools())
def test_both_languages_publish_the_same_lifetimes(key):
    cfg = legal_conf.get_tool(key)
    for (name, _ep, en_life, _ea), (_dn, _dp, de_life, _da) in zip(
            cfg["cookies"], cfg["cookies_de"]):
        en_secs, de_secs = lifetime_seconds(en_life), lifetime_seconds(de_life)
        assert de_secs == en_secs, (
            f"{key}/{name} publishes different lifetimes per language:\n"
            f"  EN {en_life!r} → {en_secs}\n  DE {de_life!r} → {de_secs}"
        )


@pytest.mark.parametrize("key", _german_tools())
def test_a_german_lifetime_that_states_a_number_can_be_parsed(key):
    """An unknown unit word removes a check instead of failing one."""
    cfg = legal_conf.get_tool(key)
    for (name, _ep, en_life, _ea), (_dn, _dp, de_life, _da) in zip(
            cfg["cookies"], cfg["cookies_de"]):
        if not lifetime_seconds(en_life):
            continue  # "browser session" and similar carry no number either way
        assert lifetime_seconds(de_life), (
            f"{key}/{name}: {de_life!r} states a lifetime that "
            f"`legal_conf.LIFETIME_SECONDS` cannot read, so nothing checks it "
            f"against the code. Add the unit word there."
        )


@pytest.mark.parametrize("key", _german_tools())
def test_the_german_cells_are_actually_german(key):
    cfg = legal_conf.get_tool(key)
    for (name, en_purpose, _el, en_who), (_dn, de_purpose, _dl, de_who) in zip(
            cfg["cookies"], cfg["cookies_de"]):
        assert de_purpose != en_purpose, (
            f"{key}/{name}: the German purpose is the English sentence verbatim"
        )
        assert de_who in GERMAN_AUDIENCES, (
            f"{key}/{name}: “{de_who}” is not one of the agreed German audience "
            f"words {sorted(GERMAN_AUDIENCES)}"
        )


@pytest.mark.parametrize("key", _german_tools())
def test_the_rendered_german_page_uses_the_german_table(key):
    """The end-to-end one: config is only half of it, the template picks."""
    html = render_legal(key, "cookies", "de")
    # Drop the Name column first: a cookie NAMED `backoffice` (Polarity
    # Profiler) is not an untranslated cell, and the template wraps every name
    # in <code>. Without this the check reports the one thing that must not be
    # translated as though it had been missed.
    html = re.sub(r"<code>.*?</code>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    for english in (" hours", " minutes", "participants", "backoffice"):
        assert english not in text, (
            f"{key}'s German cookie page still contains “{english.strip()}” — the "
            f"template is reading `cfg.cookies` rather than `cfg.cookies_de`"
        )
    assert "Lebensdauer" in text and "Betrifft" in text


@pytest.mark.parametrize("key", _german_tools())
def test_the_english_page_is_untouched_by_any_of_this(key):
    html = render_legal(key, "cookies", "en")
    text = re.sub(r"<[^>]+>", " ", html)
    assert "Lebensdauer" not in text and "Teilnehmende" not in text


# ── The role word, one language at a time ───────────────────────────────────

def test_german_says_lehrperson_and_never_kursleitung():
    """Owner, 19 August 2026. Layoff said "Lehrperson" and Whiteout
    "Kursleitung" — the same drift that "facilitator" vs "educator" was on the
    English side, and it lasted as long because each notice reads consistent on
    its own. The comparison only exists across tools, so only a fleet-wide
    check can make it."""
    src = (Path(__file__).resolve().parents[1] / "legal_conf.py").read_text(encoding="utf-8")
    assert "Kursleitung" not in src, (
        "the fleet's German word for an educator is “Lehrperson”"
    )
    assert "Lehrperson" in src
