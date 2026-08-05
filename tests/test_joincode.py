"""The join-code alphabet is an accessibility promise, not a detail.

A join code is read off a projected slide at the back of a room and typed on a
phone. O/0 and I/1 are indistinguishable in most sans-serif faces, so a code
containing them locks a participant out of the session for reasons that have
nothing to do with the exercise. Fleet policy since 2026-08-05.
"""
import pytest

from phronon_common.joincode import ALPHABET, generate_join_code

AMBIGUOUS = set("OI01")


def test_the_alphabet_excludes_every_look_alike_character():
    assert not (set(ALPHABET) & AMBIGUOUS), (
        "O/0 and I/1 cannot be told apart on a slide — neither side of either "
        "pair may be generated")


def test_the_alphabet_is_uppercase_alphanumeric():
    # Every tool validates typed codes as [A-Z0-9]; a generated code that did
    # not match its own validator would be rejected at the join form.
    assert ALPHABET.isalnum() and ALPHABET == ALPHABET.upper()
    assert len(set(ALPHABET)) == len(ALPHABET), "no duplicate characters"


def test_generated_codes_never_contain_a_look_alike():
    for _ in range(500):
        code = generate_join_code()
        assert len(code) == 6
        assert not (set(code) & AMBIGUOUS), f"ambiguous character in {code}"


def test_length_is_honoured():
    assert len(generate_join_code(4)) == 4
    assert len(generate_join_code(10)) == 10


def test_a_taken_code_is_retried():
    seen = []

    def exists(code):
        seen.append(code)
        return len(seen) < 3        # first two are taken

    code = generate_join_code(6, exists=exists)
    assert len(seen) == 3 and seen[-1] == code


def test_it_raises_rather_than_return_a_duplicate():
    """Silently handing out a code that is already in use would drop a class
    into someone else's session — louder is safer."""
    with pytest.raises(RuntimeError):
        generate_join_code(6, exists=lambda code: True, max_attempts=5)
