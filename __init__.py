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

Keep tool-specific logic OUT of here — only what is identical everywhere.
"""

__version__ = "1.4.0"
