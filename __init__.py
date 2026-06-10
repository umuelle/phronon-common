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

Moral Mirror is the first consumer; migrate the other tools opportunistically.
Keep tool-specific logic OUT of here — only what is identical everywhere.
"""

__version__ = "0.1.0"
