"""countries.py: the 193 UN member states plus Other, one list for the fleet.

The tests read the module the way the tools will: build a select, look up a
stored value, group answers by region. The counts pin the data, so an edit
that drops or adds a state, or moves one between regions, fails here first.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from phronon_common import countries as C

PKG = Path(__file__).resolve().parents[1]


def test_exactly_the_193_member_states_are_offered():
    assert len(C.MEMBERS) == 193
    offered = [v for v, _ in C.options(other=False)]
    assert len(offered) == len(set(offered)) == 193
    # Non-members and contested entries are never in the list.
    for code in ("TW", "XK", "PS", "HK", "MO", "VA", "EH", "PR", "GL"):
        assert code not in offered
        assert not C.is_member(code)
    assert len(C.NON_MEMBERS) == 57          # 56 ISO non-member entries + Kosovo


def test_every_member_has_all_three_codes_and_both_names():
    for c in C.MEMBERS:
        assert len(c.alpha2) == 2 and c.alpha2.isupper()
        assert len(c.alpha3) == 3 and c.alpha3.isupper()
        assert len(c.numeric) == 3 and c.numeric.isdigit()
        assert c.name and c.name_de and c.member
    for field in ("alpha2", "alpha3", "numeric", "name", "name_de"):
        values = [getattr(c, field) for c in C.MEMBERS]
        assert len(set(values)) == 193, field


def test_region_counts_are_the_fleet_roll_up():
    assert Counter(c.region for c in C.MEMBERS) == {
        "Africa": 54, "Europe": 47, "Asia-Pacific": 37, "Latin America": 33,
        "Middle East / Central Asia": 20, "North America": 2}
    # The two states Drawbridge grouped differently from Layoff and PP.
    assert C.region_of("AZ") == "Europe"
    assert C.region_of("PK") == "Asia-Pacific"


def test_m49_subregions_cover_every_member():
    counts = Counter(c.subregion for c in C.MEMBERS)
    assert set(counts) == set(C.SUBREGIONS)
    assert counts["Northern Africa"] == 6 and counts["Sub-Saharan Africa"] == 48
    assert counts["Western Asia"] == 17 and counts["Northern America"] == 2
    merged = Counter(C.subregion_of(c.alpha2, merge_pacific=True) for c in C.MEMBERS)
    assert merged[C.PACIFIC_ISLANDS] == 12           # Whiteout's bucket
    assert not {"Melanesia", "Micronesia", "Polynesia"} & set(merged)


@pytest.mark.parametrize("stored", [
    "DE", "DEU", "276", 276, "Germany", "Deutschland", "germany", " Germany ",
])
def test_lookup_reads_every_form_a_tool_stores(stored):
    assert C.lookup(stored).alpha2 == "DE"


@pytest.mark.parametrize("stored, code", [
    # Inequality / Whiteout spellings
    ("Korea (South)", "KR"), ("Korea (North)", "KP"), ("Turkey", "TR"),
    ("Czechia", "CZ"), ("Brunei", "BN"), ("Congo (Democratic Republic)", "CD"),
    ("Cote d'Ivoire", "CI"),
    # Layoff / PP spellings
    ("DR Congo", "CD"), ("Republic of Congo", "CG"), ("Cape Verde", "CV"),
    # pycountry's formal names and PP's former German labels
    ("Korea, Republic of", "KR"), ("Korea, Republik", "KR"), ("Viet Nam", "VN"),
    # Numeric code without padding, as an int or a string
    (4, "AF"), ("4", "AF"), ("004", "AF"),
])
def test_old_spellings_resolve_to_the_same_state(stored, code):
    assert C.lookup(stored).alpha2 == code


def test_non_members_resolve_for_old_answers_but_are_not_members():
    tw = C.lookup("Taiwan")
    assert tw.alpha2 == "TW" and not tw.member and tw.numeric == "158"
    assert C.region_of("Taiwan") == "Asia-Pacific"
    assert C.region_of("Palestinian Territories") == "Middle East / Central Asia"
    assert C.region_of("Kosovo") == "Europe"
    assert C.lookup("Kosovo").numeric is None
    assert C.member("Taiwan") is None
    assert C.subregion_of("Taiwan", default="Not stated") == "Not stated"


def test_codes_match_exactly_so_typed_text_is_not_misread():
    assert C.lookup("in") is None             # a typed answer, not India
    assert C.lookup("IN").name == "India"
    assert C.lookup("india").alpha2 == "IN"   # names ignore case


def test_region_of_handles_empty_other_and_unknown():
    assert C.region_of(None) is None and C.region_of("  ") is None
    assert C.region_of(C.OTHER_CODE) == "Other"
    assert C.region_of(C.OTHER_LABEL) == "Other"
    assert C.region_of("Atlantis") == "Other"
    assert C.region_of("Atlantis", default="Not stated") == "Not stated"
    assert C.subregion_of(None) is None


def test_options_store_the_requested_value_with_other_last():
    by_code = C.options()
    assert by_code[-1] == (C.OTHER_CODE, C.OTHER_LABEL)
    assert ("DE", "Germany") in by_code
    assert ("DEU", "Germany") in C.options(value="alpha3")
    by_name = C.options(value="name")
    assert by_name[-1] == (C.OTHER_LABEL, C.OTHER_LABEL)
    assert ("Germany", "Germany") in by_name
    with pytest.raises(ValueError):
        C.options(value="numeric")


def test_german_options_keep_english_values_and_sort_for_a_german_reader():
    de = C.options("de", value="name")
    labels = [label for _, label in de]
    assert ("Germany", "Deutschland") in de       # stored value stays English
    assert de[-1] == (C.OTHER_LABEL, C.OTHER_LABEL_DE)
    # Umlauts sort with their base letter, not after Z.
    assert labels.index("Afghanistan") < labels.index("Ägypten") < labels.index("Albanien")
    assert labels.index("Österreich") < labels.index("Pakistan")
    # Short forms, matching the English clean names.
    assert {"Südkorea", "Nordkorea", "Russland", "Iran", "Bolivien"} <= set(labels)
    assert "Korea, Republik" not in labels


def test_english_options_are_alphabetical():
    labels = [label for _, label in C.options(other=False)]
    assert labels == sorted(labels, key=C.sort_key)


def test_name_of_falls_back_to_english_for_other_languages():
    assert C.name_of("KR", "de") == "Südkorea"
    assert C.name_of("KR", "fr") == "South Korea"
    assert C.name_of("nowhere") is None


def test_the_module_needs_nothing_outside_the_standard_library():
    probe = ("import json, sys; import phronon_common.countries; "
             "print(json.dumps(sorted({n.split('.')[0] for n in sys.modules})))")
    out = subprocess.run([sys.executable, "-c", probe], cwd=PKG.parent,
                         capture_output=True, text=True, check=True).stdout
    roots = set(json.loads(out.strip().splitlines()[-1]))
    extra = roots - set(sys.stdlib_module_names) - {
        "phronon_common", "__main__", "_distutils_hack", "_virtualenv"}
    assert {r for r in extra if not r.startswith("__editable__")} == set()
    assert "pycountry" not in roots
