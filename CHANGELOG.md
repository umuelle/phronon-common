# Changelog — phronon_common

Shared package for the Phronon teaching tools. Consumers pin a **git tag** (see
each tool's CI: `phronon_common @ git+…@vX.Y.Z`), so a change here only reaches a
tool when its pin is deliberately bumped — never implicitly on the next restart.

## 1.4.0 — 2026-07-29 (second harmonization wave)
**`rate_limit` rewritten as the superset of the five private copies.** It had
been the *smallest* of them, so adopting it as written would have weakened four
tools. Brought over first:
- **Trusted proxies** — it believed `X-Forwarded-For` from anyone, so a client
  could spoof its IP past the limit. Now honoured only behind a configured
  proxy. An EMPTY trusted list falls back to the default instead of meaning
  "trust nobody", which would have collapsed every visitor behind nginx into a
  single shared bucket (two tools' `.env` had it unset — a live latent bug).
- **Exact-match rules** — `("/backoffice", 5, 300, True)` no longer leaks the
  strict login limit onto every `/backoffice/...` page.
- `SlidingWindow` + `is_allowed(key, ...)` for in-route limits (Drawbridge,
  Whiteout), `Retry-After` on the 429, and it RETURNS rather than raises (a
  raised HTTPException in user middleware surfaces as a 500).
- The original `rules=[(prefix, max, window)]` call shape still works, so
  Layoff's existing wiring is untouched. 13 tests.

**`emails` is now the only copy of the reset e-mail.** The eight per-tool
`services/email.py` modules are 12-line wrappers supplying just TOOL_NAME and
DEFAULT_FROM; markup and SMTP handling live here.

Adopted by: all nine (rate limiting in CG/Inequality/LSR/Whiteout/Drawbridge/
Layoff; e-mail in all eight tools; security headers now including the hub).

## 1.3.0 — 2026-07-29
**New module `exports`** — `csv_safe` / `csv_safe_row`, the spreadsheet
formula-injection escaping (audit G2). One definition instead of the four
private copies the tools grew on 29 July.

Adoption wave (harmonization, TO DO D6/G7): LSR-profiler, Inequality and
Orgdesignsim replaced their private `services/csrf.py` with this package's
`csrf` module; Drawbridge's `generate_token`/`validate_token` are now thin
wrappers around `CSRFProtection`; CG/Inequality/LSR lockout went DB-backed via
`lockout`. Whiteout's CSRF stays its own (signed double-submit cookie — it
protects PRE-LOGIN participant POSTs, which the token scheme here does not
cover; recorded as deliberate).

## 1.2.1 — 2026-07-28
**Fix — the middleware ate the request body.**

Every protected POST answered 422 "Field required" with input null, including
backoffice logins, for requests carrying a perfectly valid CSRF token.

BaseHTTPMiddleware gives the route handler the same receive stream the
middleware reads from, so `await request.form()` in dispatch() drained it and
the handler saw no fields at all. Latent since the middleware was written; it
only surfaced in 1.2.0, because until the catch-all "/" exemption was refused
the middleware returned before it ever touched the body.

The raw body is now read once, the token parsed out of it, and a fresh receive
channel carrying the cached bytes put back before call_next. Multipart bodies
pass through untouched — those callers send the X-CSRF-Token header.

The 1.2.0 tests all drove a stand-in route taking no arguments, which is exactly
why they missed it. Two new tests read a real Form body and a real JSON body;
both fail against the 1.2.0 implementation. Verified on python 3.10 /
starlette 1.3.1: 20 pass with the fix, 1 fails without.

## 1.2.0 — 2026-07-28
**Security — CSRF middleware hardened; roadmap N1 (CSRF API reconciliation).**

`CSRFMiddleware` now **refuses a catch-all prefix**. `exempt_paths` entries are
matched with `path.startswith(...)`, so a bare `"/"` exempts every URL on the
site. That had shipped in two tools (LSR-profiler and ControversyGenerator),
disabling CSRF app-wide — including backoffice login, class management and user
administration — and it went unnoticed because nothing fails visibly when CSRF
is off. Passing `"/"` (or `""`) in `exempt_paths` now raises `ValueError`, which
surfaces at app boot. New in this release:

- `exempt_exact` — a set of EXACT paths, the supported way to exempt a site root
  that genuinely serves a POST (ControversyGenerator's student homepage).
- `session_cookie=None` — disables token/session binding, for tools whose cookie
  value is refreshed on every response (a bound token would never match).
- Failure **returns** a 403 instead of raising. User middleware sits outside
  Starlette's `ExceptionMiddleware`, so a raised `HTTPException` bypassed the
  app's 403 handler and surfaced as a 500. Content-negotiated: JSON when the
  caller sends `Accept: application/json`, HTML otherwise.
- `get_csrf_token(request, csrf_protection, session_cookie=None)` helper, so a
  tool's template global and its middleware cannot disagree about binding.
- First `tests/` in this repo (18 tests) — CI now runs them.

Adopted by: ControversyGenerator (replaces its deleted `services/csrf.py`).
LSR-profiler still ships its own copy, fixed in place.

## 1.1.0 — 2026-07-26
Timed session signatures. Tagged without a CHANGELOG entry or a `pyproject`
version bump — recorded here after the fact; `version` jumped 1.0.0 → 1.2.0.

## 1.0.0 — 2026-07-25
First versioned + pinned release. Repo made public; installable via
`pip install "phronon_common @ git+https://github.com/umuelle/phronon-common.git@v1.0.0"`.
Modules: kanon, joincode, signing, security_headers (per-request CSP nonce via a
`{nonce}` token in a custom `csp=`), csrf, rate_limit, lockout (5-attempt
exponential backoff), passwords, emails, provisioning (hub→tool contract).
Adopted by: Layoff, Moral Mirror (full services), + Drawbridge/Orgsim/Whiteout/
Phronon/Inequality/CG/LSR (lockout). Wider `services/` adoption tracked in the
roadmap N1 item (blocked on per-tool CSRF/rate-limit API reconciliation).

## 0.1.0
Initial extraction from Moral Mirror; imported by-path as a sibling folder.
