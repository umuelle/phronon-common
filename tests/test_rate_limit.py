"""Rate limiting: the two properties the private copies had and this one lacked.

Both are regressions this module would have introduced fleet-wide when the
tools adopted it (harmonization 2026-07-29), so they are pinned here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.rate_limit import (  # noqa: E402
    RateLimitConfig, SlidingWindow, is_allowed,
)


# ── exact vs prefix rules ────────────────────────────────────────────────────

def test_exact_rule_does_not_leak_onto_subpaths():
    cfg = RateLimitConfig(
        rules=[("/backoffice", 5, 300, True),      # login only
               ("/backoffice/", 120, 60, False)],  # everything else under it
    )
    assert cfg.get_rule("/backoffice") == (5, 300)
    assert cfg.get_rule("/backoffice/dashboard") == (120, 60)


def test_first_match_wins_in_declaration_order():
    cfg = RateLimitConfig(rules=[("/a/specific", 1, 60, False), ("/a/", 99, 60, False)])
    assert cfg.get_rule("/a/specific/thing") == (1, 60)


def test_unmatched_path_uses_default_rule_or_is_unlimited():
    assert RateLimitConfig(rules=[]).get_rule("/anything") is None
    assert RateLimitConfig(rules=[], default_rule=(200, 60)).get_rule("/x") == (200, 60)


def test_three_tuple_rules_still_accepted():
    """Layoff has passed 3-tuples since this module's first version."""
    cfg = RateLimitConfig(rules=[("/educator/login", 10, 60)])
    assert cfg.get_rule("/educator/login") == (10, 60)


# ── the sliding window itself ────────────────────────────────────────────────

def test_window_blocks_after_the_limit_and_reports_retry_after():
    w = SlidingWindow()
    for _ in range(3):
        allowed, _, _ = w.check("k", 3, 60)
        assert allowed
    allowed, count, retry_after = w.check("k", 3, 60)
    assert not allowed and count == 3 and 0 < retry_after <= 60


def test_window_keys_are_independent():
    w = SlidingWindow()
    w.check("a", 1, 60)
    allowed, _, _ = w.check("b", 1, 60)
    assert allowed, "one key's limit must not affect another"


def test_expired_hits_leave_the_window():
    w = SlidingWindow()
    assert w.check("k", 1, 0)[0]
    assert w.check("k", 1, 0)[0], "a zero-length window must never stay blocked"


def test_is_allowed_helper_tracks_its_key():
    key = "test-is-allowed-unique"
    assert is_allowed(key, max_requests=2, window_seconds=60)
    assert is_allowed(key, max_requests=2, window_seconds=60)
    assert not is_allowed(key, max_requests=2, window_seconds=60)


# ── trusted proxies: the security property, tested without a live app ────────

class _FakeClient:
    def __init__(self, host): self.host = host


class _FakeRequest:
    def __init__(self, peer, forwarded=None):
        self.client = _FakeClient(peer)
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


def test_empty_trusted_list_falls_back_to_the_default_not_to_trust_nobody():
    """An empty list must not collapse every visitor into one 127.0.0.1 bucket."""
    from phronon_common.rate_limit import client_ip
    assert client_ip(_FakeRequest("127.0.0.1", "203.0.113.9"), []) == "203.0.113.9"
    assert client_ip(_FakeRequest("127.0.0.1", "203.0.113.9"), None) == "203.0.113.9"


@pytest.mark.parametrize("peer,forwarded,trusted,expected", [
    # Behind our own nginx: believe the header.
    ("127.0.0.1", "203.0.113.9", ["127.0.0.1"], "203.0.113.9"),
    # Direct from the internet: the header is attacker-controlled, ignore it.
    ("198.51.100.7", "203.0.113.9", ["127.0.0.1"], "198.51.100.7"),
    # No header at all.
    ("198.51.100.7", None, ["127.0.0.1"], "198.51.100.7"),
    # Several hops: the original client is the first entry.
    ("127.0.0.1", "203.0.113.9, 70.41.3.18", ["127.0.0.1"], "203.0.113.9"),
])
def test_forwarded_header_is_trusted_only_behind_a_known_proxy(peer, forwarded, trusted, expected):
    from phronon_common.rate_limit import client_ip
    assert client_ip(_FakeRequest(peer, forwarded), trusted) == expected
