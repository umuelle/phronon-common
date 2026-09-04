"""
phronon_common — small shared package for the Phronon teaching tools.

Holds only the genuinely-common, framework-agnostic pieces so each tool stops
copy-pasting (and slowly diverging) the same plumbing:

  * kanon            — k-anonymity display decisions (demographic-only suppression)
  * joincode         — collision-checked join-code generation
  * signing          — signed-cookie helpers (itsdangerous)
  * security_headers — SecurityHeadersMiddleware
  * csrf             — CSRF protection + middleware
  * rate_limit       — in-memory sliding-window rate limiter
  * lockout          — account-lockout policy (DB-backed pattern + memory fallback)
  * passwords        — the fleet password policy (min 12, no composition rules)
  * emails           — branded transactional-email building
  * provisioning     — hub→tool account-provisioning contract
  * exports          — spreadsheet formula-injection escaping (csv_safe)
  * sessions         — instantly revocable admin sessions (session_epoch)
  * twofactor        — TOTP second factor for admin logins (stdlib only)
  * legal            — the shared legal pages: one router, nine tools
  * participant      — one participant identity, resume and withdrawal mechanism
  * account          — self-service account management
  * audit            — the admin audit trail
  * shared_assets    — the CSS/JS masters each tool copies into its static/
  * testing          — the fleet test kit (imports no pytest; see its docstring)

README.md lists all thirty-odd of them, grouped, with the rules.

Keep tool-specific logic OUT of here — only what is identical everywhere.
"""

# THE GIT TAG IS THE REAL VERSION. Every tool's CI pins this package by tag
# (`…/phronon-common.git@vX.Y.Z`) and `server-ops/check_common_pin.py` compares
# those pins against the tag checked out at /var/www/phronon_common — that is
# the mechanism, and nothing at runtime reads the string below.
#
# It is DERIVED rather than typed, because a second hand-kept copy of a version
# is a copy that drifts: this line read "1.15.1" while the fleet ran v1.38.0,
# twenty-three tags behind, and the comment that used to sit here explained
# that no gate looks at it — which is why none noticed. There is now one place
# to change, `pyproject.toml`, and the pin gate already checks that against the
# tag.
def _version() -> str:
    from pathlib import Path as _Path

    # A checkout (the server, a sibling working copy): read the source of truth.
    pyproject = _Path(__file__).resolve().parent / "pyproject.toml"
    if pyproject.is_file():
        import re
        m = re.search(r'^version\s*=\s*"([^"]+)"',
                      pyproject.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    # An installed wheel: the metadata carries what pyproject said when built.
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version("phronon_common")
    except Exception:  # noqa: BLE001 — a version string must never break an import
        return "unknown"


__version__ = _version()
