"""The fleet test kit — invariants every tool must keep, implemented once.

WHY THIS EXISTS
The fleet's cross-cutting tests were copied, not shared. Three of them were
byte-identical in all eight tools, which means a fix to one of them missed
seven, and a tool added in future would start with none of them. That is the
same failure the shared package was created to end (README §3: a job with nine
private copies is a job where a fix misses eight).

THE SHAPE, and why it is not "shared pytest files"
The assertions live here as plain functions that raise AssertionError. The
pytest wiring — parametrize, ids, fixtures — stays in each tool's own
`tests/` file, which is a thin wrapper that points the shared assertion at its
own root.

Two reasons for that split, both load-bearing:

  1. **`phronon_common` must not depend on pytest.** It is installed into every
     production venv. Nothing here imports pytest, at module level or inside a
     function, so the test kit costs production nothing.
  2. **Each tool must still be checked by its OWN suite.** If the tests moved
     wholesale into this package, a tool could stop running them and its CI
     would still be green. The local wrapper is what keeps the check inside the
     project's own gate — the same reason `test_no_dead_or_undefined_code.py`
     was already built this way, over `undefined_names.py`, and that file is
     the precedent this kit generalises.

WHAT IS IN HERE
`passwords` and `csrf_fetch` are plain assertion functions, re-exported below.
`manage_account`, `email_delivery` and `fleet_baseline` are larger contracts,
so each tool imports the MODULE and subclasses its mixins — same split, same
reasons. `fleet_baseline` is the only one that applies to all NINE repos: the
hub has no participant flow and no password forms, but it is a FastAPI app with
a login and protected pages like the rest.

The discovery helpers return plain lists so the caller can parametrize over
them and get one test per file, with the file's name in the test id, rather
than a single opaque assertion over the whole tree.
"""
from phronon_common.testing.csrf_fetch import (  # noqa: F401
    app_source,
    assert_declaration_matches_the_code,
    assert_every_post_fetch_names_json_in_accept,
    assert_every_post_fetch_sends_the_token,
    assert_no_post_fetch_relies_on_formdata_alone,
    shared_middleware_source,
)
from phronon_common.testing.passwords import (  # noqa: F401
    assert_form_asks_for_the_shared_hint,
    assert_form_does_not_restate_the_rule,
    assert_minlength_matches_the_policy,
    assert_no_hand_rolled_length_check,
    assert_no_hand_written_password_message,
    assert_the_policy_is_reachable,
    password_setting_forms,
)

__all__ = [
    "app_source",
    "shared_middleware_source",
    "assert_declaration_matches_the_code",
    "assert_every_post_fetch_sends_the_token",
    "assert_no_post_fetch_relies_on_formdata_alone",
    "assert_every_post_fetch_names_json_in_accept",
    "password_setting_forms",
    "assert_form_asks_for_the_shared_hint",
    "assert_form_does_not_restate_the_rule",
    "assert_minlength_matches_the_policy",
    "assert_no_hand_rolled_length_check",
    "assert_no_hand_written_password_message",
    "assert_the_policy_is_reachable",
]
