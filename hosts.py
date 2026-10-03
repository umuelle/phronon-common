"""The Host names a tool will answer to — one list, derived from the notice.

WHY (external review, 16 August 2026). No tool validated the Host header, and
nginx forwards whatever arrives as `$host`. Several tools then build outgoing
URLs from the request — Controversy Generator's e-mailed pairing and withdrawal
links, Inequality's join links — so a forged Host would put an attacker's
domain into a message we send to a participant, over our own name.

Exploitability is limited: a browser will not let a page set an arbitrary Host,
so this needs a direct HTTP client, and nginx only routes a request to a tool
when the name matches its `server_name`. It is defence in depth rather than a
live hole. But "canonical URLs come from configuration, not from the request"
is the property worth having, and this is where it is cheapest to state.

THE LIST IS DERIVED, NOT TYPED. It comes from the tool's canonical domain in
`registry`, the one place that says what a tool is. The published notice names
the same domain: `server-ops/tool_registry_check.py` fails when legal_conf's
domain and the registry's disagree. (Until 3 October 2026 this read
legal_conf, which tied host enforcement to the legal-page configuration.)

FOUR ADDITIONS, each of which breaks something if it is missing:

  * `www.<domain>`   — nginx's server_name includes it.
  * `localhost`, `127.0.0.1` — the deploy boots the new version on a throwaway
    port and asks it for /health before restarting anything, and the hub polls
    every tool at 127.0.0.1:<port> for the session overview. Starlette strips
    the port before comparing, so no port needs listing.
  * `testserver`     — what FastAPI's TestClient sends. Without it every route
    test in the fleet fails, which is a loud failure rather than a silent one,
    but there is no reason to inflict it.
"""
from __future__ import annotations

from phronon_common.registry import TOOLS

# Not "*" anywhere. A wildcard here would make the middleware a decoration.
_ALWAYS = ("localhost", "127.0.0.1", "testserver")


def trusted_hosts(tool_key: str, extra: tuple[str, ...] = ()) -> list[str]:
    """Allowed Host values for one tool, from its published domain."""
    domain = TOOLS[tool_key].canonical_domain
    return [domain, f"www.{domain}", *_ALWAYS, *extra]
