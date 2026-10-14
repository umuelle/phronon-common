"""demographics.py: the fleet's one scheme for age, gender and the country.

The old spellings below are every value the six tools held in production on
14 October 2026 (counted that day, values only): each must either convert to
the scheme or, for a band of another scheme, stay as stored. A migration that
trusts ``canonical_age`` therefore rewrites exactly what converts.
"""
from __future__ import annotations

import pytest

from phronon_common import countries as C
from phronon_common import demographics as D


def test_the_scheme_is_six_age_bands_and_five_genders():
    assert D.AGE_VALUES == ("under 25", "25–34", "35–44", "45–54", "55–64", "65 or older")
    assert D.GENDER_VALUES == ("woman", "man", "non-binary", "another gender identity",
                               "prefer not to say")
    for options in (D.AGE_BANDS, D.GENDERS):
        for o in options:
            assert o.value and o.label and o.label_de, o
        assert len({o.value for o in options}) == len(options)


def test_every_stored_value_fits_a_thirty_character_column():
    """Drawbridge's gender column is varchar(30), the narrowest that will
    hold these; an age column narrower than 11 needs widening on adoption."""
    assert max(len(v) for v in D.GENDER_VALUES) <= 30
    assert max(len(v) for v in D.AGE_VALUES) == len("65 or older")


@pytest.mark.parametrize("lang", ["en", "de", "fr"])
def test_the_options_keep_the_stored_value_in_every_language(lang):
    assert [v for v, _ in D.age_options(lang)] == list(D.AGE_VALUES)
    assert [v for v, _ in D.gender_options(lang)] == list(D.GENDER_VALUES)
    labels = dict(D.gender_options(lang))
    assert labels["woman"] == ("Weiblich" if lang == "de" else "Woman")


@pytest.mark.parametrize("stored, expected", [
    # Layoff and Polarity Profiler
    ("Under 25", "under 25"), ("25–34", "25–34"), ("35–44", "35–44"), ("45–54", "45–54"),
    ("55–64", "55–64"), ("65 or older", "65 or older"), ("18–24", "under 25"),
    ("55+", None),
    # Whiteout
    ("under 25", "under 25"), ("65 or over", "65 or older"),
    # Inequality (ASCII hyphens, its own words)
    ("18-24", "under 25"), ("25-34", "25–34"), ("35-44", "35–44"), ("45-54", "45–54"),
    ("55-64", "55–64"), ("65+", "65 or older"), ("prefer_not_to_say", None),
    # Moral Mirror and Drawbridge: decade bands; only the youngest converts
    ("≤19", "under 25"), ("20–29", None), ("30–39", None), ("40–49", None),
    ("50–59", None), ("≥60", None),
    # nothing answered
    (None, None), ("", None), ("  ", None),
])
def test_an_old_age_answer_converts_only_when_its_band_is_in_the_scheme(stored, expected):
    assert D.canonical_age(stored) == expected


@pytest.mark.parametrize("stored, expected", [
    ("Female", "woman"), ("Male", "man"), ("Non-binary", "non-binary"),
    ("Prefer not to say", "prefer not to say"),                      # Layoff, PP
    ("woman", "woman"), ("man", "man"), ("non-binary", "non-binary"),
    ("prefer not to say", "prefer not to say"),                      # MM, Drawbridge
    ("another gender identity", "another gender identity"),          # Whiteout
    ("prefer_not_to_say", "prefer not to say"),                      # Inequality
    ("Weiblich", "woman"),
    (None, None), ("", None), ("something else", None),
])
def test_every_old_gender_answer_converts(stored, expected):
    assert D.canonical_gender(stored) == expected


def test_a_submitted_answer_must_be_a_value_the_page_offered():
    assert D.clean_age("25–34") == "25–34"
    assert D.clean_age("25-34") is None          # a spelling, not an offered value
    assert D.clean_age("Under 25") is None        # a label is not a value
    assert D.clean_age("") is None and D.clean_age(None) is None
    assert D.clean_gender("another gender identity") == "another gender identity"
    assert D.clean_gender("Female") is None


def test_a_label_is_shown_for_new_and_old_answers():
    assert D.age_label("under 25") == "Under 25"
    assert D.age_label("under 25", "de") == "Unter 25"
    assert D.age_label("Under 25") == "Under 25"   # Layoff's old spelling
    assert D.age_label("20–29") == "20–29"         # another scheme: shown as stored
    assert D.age_label(None) is None
    assert D.gender_label("Female") == "Woman"
    assert D.gender_label("woman", "de") == "Weiblich"


@pytest.mark.parametrize("value, member, stored", [
    ("alpha2", "DE", "DE"), ("alpha3", "DEU", "DEU"), ("name", "Germany", "Germany"),
])
def test_a_member_state_is_stored_as_the_select_offers_it(value, member, stored):
    assert D.clean_country(member, value=value) == stored
    assert D.clean_country(member, "typed text is ignored", value=value) == stored


def test_other_stores_what_was_typed_or_says_other():
    assert D.clean_country("OTHER", "  Kosovo ") == "Kosovo"
    assert D.clean_country(C.OTHER_LABEL, "Hong   Kong", value="name") == "Hong Kong"
    assert D.clean_country("OTHER", "") == C.OTHER_LABEL
    assert D.clean_country("OTHER", None) == C.OTHER_LABEL
    assert len(D.clean_country("OTHER", "x" * 300)) == D.COUNTRY_OTHER_MAX


def test_nothing_or_a_value_never_offered_stores_nothing():
    assert D.clean_country(None) is None
    assert D.clean_country("") is None
    assert D.clean_country("XX") is None
    assert D.clean_country("Germany", value="alpha2") is None   # a name where a code is stored
    assert D.clean_country("TW", value="alpha2") is None        # not a UN member state


def test_the_country_select_is_the_shared_list():
    assert D.country_options("en") == C.options("en")
    assert D.country_options("de", value="name")[-1] == (C.OTHER_LABEL, C.OTHER_LABEL_DE)
    assert len(D.country_options()) == 194


def test_the_hint_names_the_other_choice_in_both_languages():
    assert C.OTHER_LABEL in D.COUNTRY_HINT["en"]
    assert C.OTHER_LABEL_DE in D.COUNTRY_HINT["de"]
