"""The fleet's one scheme for the questions about you (owner, 14 October 2026).

THE RULE. Every tool that asks a participant's age, gender or country asks it
the same way, and every answer is optional:

  * age in six bands: under 25, 25–34, 35–44, 45–54, 55–64, 65 or older;
  * gender: woman, man, non-binary, another gender identity, prefer not to
    say. The fourth invites no self-description (Whiteout's W28: a choice
    that asked "please specify" with nowhere to type was a false promise);
  * country: the 193 UN member states plus "Other / not listed" with a box
    to type the country in (``countries``), and one hint under the select.

What a tool STORES is the English value of the option, whatever the page's
language, so aggregates read the same in every language; the label is what
the page shows. A tool keeps its own extra questions (Layoff's industry,
Inequality's income, Whiteout's experience): only these three are shared.

WHY THESE (decided 14 October 2026 against the live answers of that day).
Four age schemes were live: decade bands in Drawbridge (556 answers) and
Moral Mirror (34), and "25–34" bands, spelled three ways, in Layoff (100),
Polarity Profiler (61), Whiteout (40) and Inequality (25). The two families
share no boundary, so no answer converts from one to the other. The owner
chose the "25–34" bands as the standard: Moral Mirror moves to them (its
earlier answers stay as stored), and Drawbridge keeps decade bands for its
Prolific research set, which stays one scheme (Drawbridge's own decision,
in Drawbridge). Gender: every stored answer converts to the five options
(Layoff's and Polarity Profiler's "Female" and "Male" become "woman" and
"man"); Inequality's "Other / Prefer not to say" can only become "prefer
not to say". Country: one spelling for every state; on 14 October no
stored answer in the three tools that store names needed rewriting.

OLD ANSWERS. ``canonical_age`` and ``canonical_gender`` read what a tool
stored before: an old spelling of a value in this scheme converts (Layoff's
"Under 25", Inequality's "25-34" and "prefer_not_to_say", "18–24" and
"≤19" into "under 25", "65+" into "65 or older"); a band of another scheme
("20–29", "55+") does not, returns None, and stays as stored. A tool's
migration rewrites only what converts. ``age_label`` and ``gender_label``
show any stored value, so a session from before the change still reads.

Standard library only, no I/O.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

from . import countries


class Option(NamedTuple):
    value: str       # what is stored (English, whatever the page language)
    label: str       # English label
    label_de: str    # German label


AGE_BANDS: tuple = (
    Option("under 25", "Under 25", "Unter 25"),
    Option("25–34", "25–34", "25–34"),
    Option("35–44", "35–44", "35–44"),
    Option("45–54", "45–54", "45–54"),
    Option("55–64", "55–64", "55–64"),
    Option("65 or older", "65 or older", "65 oder älter"),
)

GENDERS: tuple = (
    Option("woman", "Woman", "Weiblich"),
    Option("man", "Man", "Männlich"),
    Option("non-binary", "Non-binary", "Nicht-binär"),
    Option("another gender identity", "Another gender identity", "Andere Geschlechtsidentität"),
    Option("prefer not to say", "Prefer not to say", "Keine Angabe"),
)

AGE_VALUES = tuple(o.value for o in AGE_BANDS)
GENDER_VALUES = tuple(o.value for o in GENDERS)

#: The sentence under the country select.
COUNTRY_HINT = {
    "en": "All UN member states are listed. If your country or region is not "
          "listed, choose “Other / not listed” and type it in.",
    "de": "Aufgeführt sind alle UN-Mitgliedstaaten. Wenn Ihr Land oder Ihre "
          "Region nicht dabei ist, wählen Sie „Andere / nicht aufgeführt“ und "
          "tragen Sie es ein.",
}
#: Placeholder of the box behind "Other / not listed".
COUNTRY_OTHER_PLACEHOLDER = {
    "en": "Please specify your country or region",
    "de": "Bitte nennen Sie Ihr Land oder Ihre Region",
}
#: The longest typed country kept (every tool's column holds at least 100).
COUNTRY_OTHER_MAX = 100

# Old spellings of values in this scheme, as the tools stored them before
# 14 October 2026. Compared after _fold(): case, spaces and the kind of dash
# do not matter.
_AGE_ALIASES = {
    "under 25": "under 25", "unter 25": "under 25", "18-24": "under 25",
    "≤19": "under 25", "<=19": "under 25", "19 or under": "under 25",
    "25-34": "25–34", "35-44": "35–44", "45-54": "45–54", "55-64": "55–64",
    "65 or older": "65 or older", "65 or over": "65 or older", "65+": "65 or older",
    "65 oder älter": "65 or older",
}
_GENDER_ALIASES = {
    "woman": "woman", "female": "woman", "weiblich": "woman", "frau": "woman",
    "man": "man", "male": "man", "männlich": "man", "mann": "man",
    "non-binary": "non-binary", "nonbinary": "non-binary", "nicht-binär": "non-binary",
    "another gender identity": "another gender identity",
    "andere geschlechtsidentität": "another gender identity",
    "prefer not to say": "prefer not to say", "prefer_not_to_say": "prefer not to say",
    "other / prefer not to say": "prefer not to say", "keine angabe": "prefer not to say",
}
_DASHES = re.compile(r"\s*[‐‑‒–—−-]\s*")


def _fold(value) -> str:
    """Case, surrounding and doubled spaces, and the kind of dash ignored."""
    text = " ".join(str(value).split()).casefold()
    return _DASHES.sub("-", text)


def _labels(opts: tuple, lang: str) -> list:
    return [(o.value, o.label_de if lang == "de" else o.label) for o in opts]


def age_options(lang: str = "en") -> list:
    """[(stored value, label), ...] in the order the page shows them."""
    return _labels(AGE_BANDS, lang)


def gender_options(lang: str = "en") -> list:
    return _labels(GENDERS, lang)


def clean_age(value) -> Optional[str]:
    """A submitted age: one of the six values exactly, else None (nothing
    answered, or something the page never offered)."""
    return value if value in AGE_VALUES else None


def clean_gender(value) -> Optional[str]:
    return value if value in GENDER_VALUES else None


def canonical_age(stored) -> Optional[str]:
    """The value in this scheme for an answer a tool stored before, or None
    when it has none (empty, or a band of another scheme such as "20–29")."""
    if stored is None or not str(stored).strip():
        return None
    return _AGE_ALIASES.get(_fold(stored))


def canonical_gender(stored) -> Optional[str]:
    if stored is None or not str(stored).strip():
        return None
    return _GENDER_ALIASES.get(_fold(stored))


def _label_of(opts: tuple, value, lang: str, canonical) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    found = canonical(value)
    for o in opts:
        if o.value == found:
            return o.label_de if lang == "de" else o.label
    return str(value)


def age_label(stored, lang: str = "en") -> Optional[str]:
    """What a page shows for a stored age: this scheme's label, or the
    stored text itself for a band of an older scheme ("20–29")."""
    return _label_of(AGE_BANDS, stored, lang, canonical_age)


def gender_label(stored, lang: str = "en") -> Optional[str]:
    return _label_of(GENDERS, stored, lang, canonical_gender)


def country_options(lang: str = "en", *, value: str = "alpha2") -> list:
    """The country select: the 193 member states and "Other / not listed"
    last (``countries.options``), storing ``value`` ("alpha2", "alpha3" or
    the English "name")."""
    return countries.options(lang, value=value)


def clean_country(choice, other_text=None, *, value: str = "alpha2") -> Optional[str]:
    """What to store for a country answer.

    * nothing chosen -> None;
    * a member state, given as the select offers it -> that value;
    * "Other / not listed" with text typed -> the text, spaces tidied and cut
      to COUNTRY_OTHER_MAX characters; with the box left empty -> "Other /
      not listed" (an answer: the participant said their country is not in
      the list);
    * anything else (a value the select never offered) -> None.
    """
    if choice is None or not str(choice).strip():
        return None
    choice = str(choice).strip()
    if choice in (countries.OTHER_CODE, countries.OTHER_LABEL):
        typed = " ".join(str(other_text or "").split())[:COUNTRY_OTHER_MAX].strip()
        return typed or countries.OTHER_LABEL
    offered = {v for v, _ in countries.options("en", value=value, other=False)}
    return choice if choice in offered else None
