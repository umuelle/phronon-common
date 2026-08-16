"""`recipient_domain` — the one implementation, and why it is strict.

Four tools grew their own copy of this twelve-line helper (Controversy
Generator, LSR, Whiteout, Moral Mirror). By 16 August 2026 three of them
returned the WHOLE string for input containing no "@" — so a participant who
mistyped their address had their raw input written to the journal in full, by
the helper whose entire purpose is to stop that. Three also left surrounding
whitespace in. CG's was strict; CG's is now everyone's.

The lesson is the fleet's oldest (README §3) and it turns out to apply to
twelve-line helpers as much as to CSRF: a job with several private copies is a
job where a fix misses the rest. These cases are the contract, so the next
person to "simplify" this has to break a named test to do it.
"""
import pytest

from phronon_common.emails import recipient_domain


@pytest.mark.parametrize("address, expected", [
    ("ada@example.org", "@example.org"),
    ("Ada.Lovelace+tag@sub.uni-example.ac.uk", "@sub.uni-example.ac.uk"),
    # Whitespace is stripped: a trailing space in a form field must not become
    # a different domain in the log, and "@example.org " reads as a typo in the
    # code rather than in the data.
    ("  ada@example.org  ", "@example.org"),
])
def test_the_domain_survives(address, expected):
    assert recipient_domain(address) == expected


@pytest.mark.parametrize("address", [
    "",
    None,
    "not-an-address",          # THE regression: three copies returned this whole
    "ada",                     # string back, prefixed with "@"
    "   ",
    "ada@",                    # an "@" with nothing after it is not a domain
])
def test_anything_that_is_not_an_address_reveals_nothing(address):
    assert recipient_domain(address) == "(no address)"


@pytest.mark.parametrize("address", [
    "ada@example.org",
    "ada.lovelace@example.org",
    "not-an-address",
    "ada",
])
def test_the_mailbox_never_survives(address):
    """The part before the "@" is the part that identifies a person."""
    out = recipient_domain(address)
    mailbox = address.split("@", 1)[0]
    assert mailbox not in out or out == "(no address)"


def test_it_never_raises_on_odd_input():
    """It is called from exception handlers and background workers, where a
    raise would replace the error being reported with its own."""
    for odd in (123, object(), b"ada@example.org", ["a"]):
        assert isinstance(recipient_domain(odd), str)
