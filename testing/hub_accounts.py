"""The account list a tool gives the hub (users_kit.build_hub_accounts_router, TO DO FL-157).

The route is the shared kit's, and the kit's own suite drives it
(tests/test_users_kit.py). What only a tool's own suite can show is that the
route is mounted there, answers to THAT tool's secret and no other, and reads
that tool's account table and session counts. Each tool calls
`assert_the_hub_reads_accounts` from its own tests with accounts it just made.

Nothing here imports pytest: the caller hands in `monkeypatch.setenv`.
"""
from __future__ import annotations

from typing import Any, Callable

from phronon_common import provisioning, users_kit
from phronon_common.registry import ToolIdentity

SECRET = "hub-accounts-test-secret-000000000000"  # pragma: allowlist secret (test value)


def assert_the_hub_reads_accounts(client: Any, tool: ToolIdentity,
                                  setenv: Callable[[str, str], Any],
                                  expected: dict[str, dict]) -> dict[str, dict]:
    """Ask `client` (a browser signed in to nothing) for the account list.

    `expected` maps an address to the fields that account must show, for
    example `{"a@example.invalid": {"role": "admin", "sessions": 2}}`.
    Returns every listed account by address.
    """
    url, header = users_kit.HUB_ACCOUNTS_URL, provisioning.PROVISION_HEADER
    name = provisioning.secret_env_var(tool)

    # No secret on the server: nobody gets in, an empty header included.
    setenv(name, "")
    for sent in ({}, {header: ""}, {header: SECRET}):
        r = client.get(url, headers=sent)
        assert r.status_code == 401, f"{url} answered {r.status_code} with no secret configured"

    setenv(name, SECRET)
    for sent in ({}, {header: "wrong"}, {header: SECRET + "x"}):
        r = client.get(url, headers=sent)
        assert r.status_code == 401, f"{url} answered {r.status_code} to {sent!r}"
        assert "accounts" not in r.text, "a refused caller was shown the list"

    r = client.get(url, headers={header: SECRET})
    assert r.status_code == 200, f"{url} answered {r.status_code}: {r.text[:200]}"
    assert "$2" not in r.text, "the answer carries something that looks like a password hash"
    answer = r.json()
    assert answer.get("tool") == tool.entitlement_key, answer.get("tool")
    assert isinstance(answer.get("generated_at"), str)
    accounts = answer.get("accounts")
    assert isinstance(accounts, list) and accounts, "no accounts listed"

    listed: dict[str, dict] = {}
    for account in accounts:
        assert set(account) == set(users_kit.HUB_ACCOUNT_FIELDS), sorted(account)
        assert isinstance(account["email"], str) and account["email"] == account["email"].lower()
        assert isinstance(account["name"], str)
        assert account["role"] in ("admin", "educator"), account["role"]
        assert isinstance(account["active"], bool) and isinstance(account["two_factor"], bool)
        assert account["last_sign_in"] is None or isinstance(account["last_sign_in"], str)
        assert isinstance(account["sessions"], int) and account["sessions"] >= 0
        assert account["email"] not in listed, f"{account['email']} is listed twice"
        listed[account["email"]] = account

    for email, fields in expected.items():
        assert email.lower() in listed, f"{email} is not in the list"
        for field, value in fields.items():
            assert listed[email.lower()][field] == value, (
                f"{email}: {field} is {listed[email.lower()][field]!r}, expected {value!r}")

    assert client.head(url, headers={header: SECRET}).status_code == 200
    return listed
