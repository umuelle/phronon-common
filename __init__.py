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

Keep tool-specific logic OUT of here — only what is identical everywhere.
"""

# THE GIT TAG IS THE REAL VERSION. Every tool's CI pins this package by tag
# (`…/phronon-common.git@vX.Y.Z`) and `server-ops/check_common_pin.py` compares
# those pins against the tag checked out at /var/www/phronon_common — that is
# the mechanism, and nothing reads the string below. It sat at "1.7.0" while
# the fleet ran v1.13.2, and no gate noticed, because no gate looks here.
# Kept in step by hand as documentation for whoever opens this file first.
__version__ = "1.13.4"
