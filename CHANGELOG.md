# Changelog — phronon_common

Shared package for the Phronon teaching tools. Consumers pin a **git tag** (see
each tool's CI: `phronon_common @ git+…@vX.Y.Z`), so a change here only reaches a
tool when its pin is deliberately bumped — never implicitly on the next restart.

## 1.30.0 — 2026-09-03

- **The eight participant notices, for the fleet identity mechanism.**
  `notice_version` `2026-09-03-identity` on all eight (the hub, which has no
  participants, is untouched). Every participant cookie table now publishes
  ONE cookie at **8 hours** carrying a random identifier and nothing else;
  the rows for cookies that carried answers, a submission reference or a raw
  withdrawal token are gone, because those moved to the server. Drawbridge
  gains a `drawbridge_csrf` row, separate from the pass so the deletion form
  still works when there is no pass left. German tables moved with the
  English ones (Layoff, Polarity Profiler; Whiteout already published 8 h).
- **Erasure rewritten for the five tools whose deletion route is new or
  changed** (Inequality, Layoff, OrgDesignSim, Moral Mirror, Polarity
  Profiler): a link the participant holds, replaceable at
  `/withdrawal-link` where an address exists, that keeps working for as long
  as any record of theirs exists. Polarity Profiler's says plainly that the
  report link is only a report link — it no longer deletes anything.
  Moral Mirror's states its two declared exceptions: no replacement is
  possible, and nothing per person survives the deadline.

## 1.29.2 — 2026-09-03

- **`RESUME_TOKENS_DDL` no longer pins a charset.** `DEFAULT CHARSET=utf8mb4`
  means utf8mb4_0900_ai_ci on MySQL 8 and overrides a database that is
  utf8mb4_unicode_ci — so the table disagreed with the one it references and
  comparing the two columns raised 1267 inside a sweep that swallows its own
  exceptions. The table now inherits its database's collation, and the comment
  states the rule: a tool that JOINs must name the collation to match the
  referenced TABLE, not the database.

## 1.29.1 — 2026-09-03

- `ParticipantCookie.mint()` — the signed cookie value without a response to
  set it on. Every tool's tests need to hand a TestClient a valid participant
  cookie; the alternative was eight copies of a reach into the private signer,
  which is also eight tests that keep passing after the signing rule changes
  under them. `set()` now goes through it, so the two cannot diverge.

## 1.29.0 — 2026-09-03

- **`participant.py` — the fleet participant mechanism** (owner's decision,
  3 September 2026): random participant id, the signed 8-hour resume cookie
  (`ParticipantCookie`), hashed withdrawal tokens with the rotation rule,
  one-time 30-minute resume links (`issue/peek/spend_resume_token` over the
  tool's own DB callables, shared DDL), the typed confirmation word in every
  accepted locale, the 10-per-5-minutes withdrawal rate limit. Additive —
  nothing changes for a tool until it adopts it.
- `emails.py`: `send_participant_resume` and `send_withdrawal_link`, the two
  participant mails the mechanism needs, worded once.

## 1.28.3 — 2026-09-03

- **Inequality Explorer and OrgDesignSim notices: the fleet retention clock.**
  Both tools converged on the owner's contract (FL-056): one deadline per
  session, 30 days after the first close or after the last response /
  completed run; educator warned 14 days ahead, participants 7; three 30-day
  postponements; a session nobody joins deleted at 90 days; reopening or
  closing again never moves the anchor. Inequality was 30 days after EACH
  response (a shortening for nobody, a per-session date for everyone);
  OrgDesignSim was 90 days after EACH run's completion (a SHORTENING — see
  the deploy note in `server-ops/DELETION-JOBS.md`). `notice_version`
  `2026-09-03-retention` on both; erasure paragraphs name the same date.
  Header table brought up to date for Inequality, PP and OrgDesignSim.

## 1.28.2 — 2026-09-03

- `backoffice-core.css` declares the `--bo-*` palette, radii and font itself
  (Whiteout's values). Polarity Profiler's dashboard shipped with invisible
  buttons because its base never loaded the sheet that declared the tokens the
  shared rules read; Inequality had the same hole. The shared sheet loads last,
  so these values now apply to every backoffice, including Moral Mirror's own
  warm palette, which the owner's dashboard rule overrides.

## 1.28.1 — 2026-09-03

- **The dashboard vocabulary** (owner's decision from eight screenshots:
  Whiteout's dashboard is the fleet's). `backoffice-core.css` gains, verbatim
  from Whiteout, `.btn` and its `-primary/-secondary/-danger/-sm/-link`
  variants with hover states, `.bo-page-header`, `.code-chip`, `.badge-test`,
  `.bo-table` hover and test-row tints, the `.table-*` controls, and the
  width decision the 26 August note left open: `.bo-content` is 1320px
  everywhere. Load order is settled with it — this sheet loads LAST in every
  backoffice base. Gate: `server-ops/fleet_dashboard_check.py`; standard:
  README §3 "The dashboard has one shape". (v1.28.0 is the same stylesheet
  tagged a minute early, before `pyproject.toml` moved; nothing pins it.)

## 1.27.2 — 2026-09-02

- English legal templates: `_controller.html` "cross-class research use" →
  "cross-session", `_logging.html` "anonymising class data" → "session
  data". Same finding as 1.27.1, other language; found on the live
  Inequality notice. Templates only — read from disk, no restart needed.

## 1.27.1 — 2026-09-02

- German legal templates: `_controller.html` and `_logging.html` said
  "Lehrende" for the educator; the fleet word is "Lehrperson" (README §9).
  Found on the live PP notice minutes after 1.27.0 went out — the fleet
  vocabulary gate scans the tools' templates, not this package's.

## 1.27.0 — 2026-09-02

- **The container is a SESSION, fleet-wide** (owner's decision, README §9).
  `legal_conf.py`: every one of the nine notices says *session* where it said
  class, survey, scenario or "class/session"; German says *Session* (not
  Kurs / Sitzung / Klasse) and *Lehrperson* (not Lehrende / Moderierende); the
  participant cookies are "participant tokens", no longer "session tokens",
  and OrgDesignSim's retention list no longer uses "sessions" for three
  different tables. **Every tool's `notice_version` is now `2026-09`**, set
  explicitly per block (Controversy Generator, Inequality, OrgDesignSim and
  the hub had inherited the fleet default until now — CG-011). The fleet
  default `NOTICE_VERSION` and `LAST_UPDATED` move with it. The consent and
  acknowledgement wordings that changed in the tools are archived in
  `server-ops/CONSENT-WORDING-ARCHIVE.md` under the same date.
- `svg-charts.js`: the band label reads "everyone in the session ranked
  between …" (was "the whole class …"). Synced to the six tools that load it.
- `joincode.py`, `audit.py`, `share-card.css`: comments only — the `class_*`
  audit action names and the `.share-class-code` selector are identifiers and
  keep their names; the docstrings now say so instead of listing per-tool nouns.
- `tests/test_locale_promises_match.py` follows the wording ("small session" /
  "kleinen Session").

(1.25.0 — `joincode.validate_typed_code`, and 1.26.0 — `retention_heartbeat`,
both 1 September 2026, shipped without a changelog entry; see git tags.)

## 1.24.0 — 2026-08-25

- **Whiteout notice `2026-08-o`**: the required participation box is an
  acknowledgment, not consent. The record bullet ("Your consent, as a
  record — that you ticked the box to take part") described the required box
  as consent that could not be refused without losing the class — the EDPB
  ambiguity flagged by the 25 August external review. It now reads "Your
  acknowledgment and consents, as a record", states that participation rests
  on the legitimate interest named above, and scopes Art. 7(1) to the
  genuinely optional boxes. Both locales; Whiteout's checkbox wording moves
  in the same change (`wo-ack-2026-08-25`) and both are archived in
  server-ops/CONSENT-WORDING-ARCHIVE.md.

## 1.23.0 — 2026-08-25

- **Cache headers are method-aware** (external review, 25 August 2026): the
  public-path allowlist now applies only to GET/HEAD. Responses to POST and
  every other state-changing method are `no-store` regardless of path —
  previously the response to `POST /join`, which can echo the e-mail address
  the person just typed, went out with no cache header because `/join` sits
  on the public list. No response to a state-changing method is ever
  cacheable in this fleet; they are all per-person by construction. New
  `tests/test_security_headers.py` pins both directions (public GET stays
  cacheable, POST on the same path does not).

## 1.22.0 — 2026-08-24

- Whiteout notice **2026-08-n**: the what-had-your-group-decided question is
  asked in **every session** once the group's ranking agreement is final — no
  longer only in sessions running the optional second round — and its
  per-group counts gained an audience: they may now also appear in the **class
  results handout**, not only on the projector. The bullet stops scoping the
  question to the optional round and says both, in both languages.

  Same field, same basis, same storage, still never beside a name, still not
  part of the research data. What changed is *when the question is asked* and
  *who may see the counts afterwards* — both are things a participant weighs
  when deciding how honestly to answer, so both belong in the version they are
  stamped with. Whiteout's participant-facing wording (`gr2.strategy_privacy`)
  moved in the same change; the private-lean bullet is untouched (its counts
  stay out of the handout).

## 1.21.0 — 2026-08-20

- Whiteout notice **2026-08-m**: the prediction and the winter question moved
  from the ranking screen to the one after it, so the two bullets that said
  "when you send your ranking" and "on the same screen" now say where the
  questions actually are.

  Nothing about the data changed — same fields, same basis, same storage on the
  identifiable participant row rather than behind the demographic consent. A
  notice that describes a screen has to be right about which screen.

## 1.20.0 — 2026-08-20

- Whiteout notice **2026-08-l**: the two tables of private counts — what each
  group thought it had decided, and what each member would privately have done
  — may now be shown to the class on the projector, so the bullets stop saying
  "shown to your educator only" and say who else may see them, in both
  languages.

  The counts themselves did not change. The AUDIENCE did, and that is the part
  a notice describes: a group of six that answers unanimously is six people's
  private answers on a wall, so both bullets now say plainly that a unanimous
  group can be read off the counts. Whiteout's participant-facing wording moved
  in the same change. Nobody had answered either question outside the demo
  classes and the owner's own test class when this shipped.

## 1.19.0 — 2026-08-20

- Whiteout notice **2026-08-k**: the private stay-or-go question asked before
  the second round enters the stored-data list, in both languages.

## 1.18.0 — 2026-08-20

- `tests/test_locale_promises_match.py`: a promise made in one locale must be
  made in the other. Found two bullets missing from the Polarity Profiler's
  German notice on the first run.

## 1.17.0 — 2026-08-20

- FL-036: `[hidden]` hides everywhere — an author `display` rule no longer
  beats it. FL-037: `assets.py`, content-hash cache-busting, so a deployed
  change cannot be masked by a stale cached file.

## 1.16.0 — 2026-08-20

- `csv_download`: the four things an export must do, in one shape (FL-022,
  cheap half).

## 1.15.1 — 2026-08-19

- `max_age_for` documents why it fails towards the LONGER session, and what
  that costs. Docstring only; no behaviour change, so no tool needs restarting
  to pick it up.

  It matters because the asymmetry reads as a bug to whoever finds it next: an
  unrecognised role gets the educator limit, which means a mistyped key
  (`row.get("Role")`) is indistinguishable from an empty role column and
  answers six hours while looking like working code. The trade is deliberate —
  strictness here would cut every educator to three hours the moment a role
  column went empty mid-class — and the key is therefore checked at the CALL
  SITE by `server-ops/fleet_session_length_check.py`, which reads the argument
  of every call to this function with `ast`.

## 1.15.0 — 2026-08-19

- **A tool that declares a locale publishes its cookie table in that locale.**
  `cookies_de` beside `cookies` for Layoff, Polarity Profiler and Whiteout —
  same cookies, same order, German purpose, lifetime and audience.
  `_cookie_table.html` picks by `lang`, with **no fallback to English**: the
  environment runs `StrictUndefined`, so a German page without the table raises
  instead of quietly serving the wrong language.

  The German pages had printed a German heading row over English cells since
  they were built. That was survivable while the lifetime column held "4 hours"
  — a number reads in any language — and stopped being survivable on 19 August,
  when it became "6 hours (educators) / 3 hours (administrators)". The gap did
  not grow; the content grew into it.

- **New `legal_conf.lifetime_seconds()` and `LIFETIME_SECONDS`, knowing English
  AND German units.** This parser used to live in `server-ops/closing_audit.py`,
  which now imports it. It belongs next to the sentences it reads: a new locale
  adds its unit words to one table, and every reader of the published text
  learns them at once. An unrecognised unit makes a cell parse to nothing, which
  SKIPS the row rather than failing it — a typo in "Stunden" would delete a
  check, not break one, which is why both languages are spelled out in full.

- The German word for an educator is **Lehrperson** (owner). Whiteout said
  *Kursleitung*, Layoff said *Lehrperson* — the same drift "facilitator" vs
  "educator" was in English, surviving as long because each notice reads
  consistent on its own. Audience column: *Teilnehmende*, *Backoffice*, *alle*.

- New `tests/test_cookie_tables_de.py`, written for the tenth tool rather than
  the three that exist: adding `"de"` to a tool's `languages` without
  translating its table fails six tests. It also pins the pairing that decays —
  identical cookie names in identical order, and lifetimes that parse to the
  same seconds in both languages.

- `notice_version` unchanged again: being shown the same promise in your own
  language is not a different promise. `last_updated` moves.

## 1.14.2 — 2026-08-19

- **Whiteout's published notice says "educator", not "facilitator"** (owner,
  19 August 2026). It was the only tool in the fleet using the other word, in
  23 places on its own privacy and cookie pages, while the other eight say
  "your educator" and Whiteout's own `admins.role` column has stored
  `'educator'` all along. Nothing about who that person is or what they can see
  changed — same role, same permissions, same promises.

- `notice_version` deliberately unchanged. It is stamped on each participant's
  record to say which notice they were shown, and a synonym does not change
  what they were told; bumping it would put a "something changed" signal in
  every future record and a no-op entry in the wording archive.

- The German text is NOT touched here: it says *Kursleitung* where Layoff says
  *Lehrperson*, which is the same drift in the other language and needs the
  owner's sign-off before it moves. (Approved and done in 1.15.0, below. The
  first draft of this line cited "TO DO FL-032" — a number already held by the
  skip-link defect; the item never needed one, it was approved the same day.)

## 1.14.1 — 2026-08-19

- `pyproject.toml` was left at 1.13.40 when v1.14.0 was cut, so the tag
  installs as the wrong version — the exact drift the comment in that file
  warns about, caught by `deploy.sh`'s pin gate before anything reached the
  server. **v1.14.0 is superseded: pin this one.** The tag was not moved,
  because CI on all nine tools had already installed from it and a tag that
  names two different trees is worse than a tag nobody should use.

## 1.14.0 — 2026-08-19

- **Session length now depends on the role: educators 6 hours, admins and
  owners 3.** New in `sessions.py`: `EDUCATOR_SESSION_MAX_AGE`,
  `ADMIN_SESSION_MAX_AGE`, `MAX_SESSION_AGE` (the ceiling — build signers with
  it), `is_privileged()`, `max_age_for(role)` and `session_age_ok(signer, raw,
  role)`. Role spellings are compared case-insensitively, and an unknown or
  empty role gets the LONGER session, which is the behaviour it had before.

- `signing.DEFAULT_MAX_AGE` is now `MAX_SESSION_AGE` (6 h) rather than a flat
  4 h. **It is a ceiling, not the session length.** A signer is constructed
  before anyone has logged in, so it cannot know the role; every consumer must
  call `session_age_ok(...)` with the role from the account ROW once it has
  read it, or an admin gets six hours.

- `legal_conf.py`: every tool's backoffice cookie row publishes both numbers,
  and `last_updated` moves to 2026-08-19 fleet-wide. `notice_version` is
  deliberately unchanged — it is recorded against each participant's own
  submission as the notice they were shown, and nothing a participant is told
  has changed. Two unrelated corrections in Layoff's table, found by widening
  `closing_audit.py`'s cookie parser: `layoff_participant` published 24 hours
  where the code sets 30 minutes, `layoff_flash` 10 minutes where it sets 5.

- Bumping the minor rather than the patch: a tool that takes this pin without
  adding the second age check silently lengthens its admin sessions from four
  hours to six.

## 1.13.40 — 2026-08-18

- `.bo-account` is one column at the page's own width — the shape the Sessions,
  Classes and Users tables already use. Three cards abreast turned one account
  into a dashboard and put every field in a narrow well.

## 1.13.39 — 2026-08-17

- `.bo-account` lays the Manage account cards across the full page width, like
  every other backoffice page, instead of two columns capped at 60rem.

## 1.13.38 — 2026-08-17

- `backoffice-core.css` gains `.bo-account`: the Manage account page lays its
  cards out in two balanced columns on a desktop and one on a phone. Multi-column
  rather than grid, so a tall card beside a short one does not leave a hole under
  the short one — which is the exact shape this page has.

## 1.13.37 — 2026-08-17

- New `account.py`: e-mail-address change tokens (signed, bound to the account,
  the address they were issued from and the session epoch) plus the fleet's one
  address and display-name validator. It backs the Manage account page that now
  replaces the stand-alone change-password page in all nine tools.
- Three shared mail bodies in `emails.py`: confirm-your-new-address (to the new
  address), address-change-requested (to the old one, while the link is still
  unused) and two-factor-reset-by-an-administrator. The SMTP conversation is
  extracted to one `_smtp_send`, so the mails added since the reset mail no
  longer each carry a copy of the host/port/STARTTLS handling.
- `twofactor.is_required` now answers True for OWNER as well as ADMIN. The hub's
  own role was the one role the rule exempted; nothing depended on it yet.

## 1.13.31 — 2026-08-16

- Redact password-reset tokens and Drawbridge Prolific recruitment identifiers
  from uvicorn access records.
- Send `Referrer-Policy: no-referrer` on credential-bearing URLs so a secret
  suppressed on its own route cannot reappear as a same-origin static-asset
  referrer.
- Correct the 30 + 3×30-day public retention arithmetic for Controversy,
  Drawbridge and Moral Mirror.
- Version Drawbridge's exact retained research shape and Layoff's accurate
  pseudonymisation wording.
- Correct Drawbridge's browser-hash and erasure wording: a support message does
  not expose the participant's duplicate-prevention hash, and the hash is
  pseudonymous rather than incapable of singling out a browser session.

## 1.8.2
Legal routes answer HEAD explicitly (methods=[GET, HEAD]) — routes nested
via include_router do not get Starlette's automatic GET->HEAD, and corporate
web filters probe HEAD first.

## 1.8.1
Name every legal route (impressum, legal_notice, privacy, cookies, terms,
legal, imprint, privacy_de, cookies_de) so templates can url_path_for() them;
Phronon's base template does, and unnamed routes 500ed every page render.

## 1.8.0
Shared legal pages (phronon-legal-blueprint.md): `legal.py` (router factory +
`render_legal`), `legal_conf.py` (all nine tools' per-tool config in ONE file)
and `legal_templates/` (bilingual EN/DE partials). Route map: /impressum
(German § 5 DDG canonical), /legal-notice, /privacy, /cookies, /terms, /legal,
/imprint→301 /legal, plus /de/privacy + /de/cookies on German-UI tools.
tests/test_legal.py enforces the anti-regression register (no TMG/TTDSG/RStV/
VSBG/BFSG/ODR citations, no "5 business days", no "fully anonymous", no
"SHA-256", recipients/logging blocks byte-identical). footer.html now links
Impressum · Privacy · Cookies · Terms · Accessibility.

## 1.6.0 — 2026-07-29 (A1: two-factor login)
**New module `twofactor`** — TOTP (RFC 6238) plus single-use recovery codes,
**standard library only**. `pyotp` was the obvious choice and was rejected: the
algorithm is ~20 lines of HMAC, while a new dependency means nine checksum-lock
rebuilds and nine more things to audit. Correctness is pinned to the RFC's own
published test vectors, so it cannot silently drift from what phone apps do.

Scope is ADMIN accounts only, by the owner's decision — educators are numerous,
often first-time users on a teaching day, and a lockout mid-class is worse than
the risk it removes.

Includes ±30 s clock-drift tolerance, constant-time comparison, and recovery
codes hashed with bcrypt (passed in, so this module imports nothing external).
16 tests, six of them the RFC vectors.

## 1.5.0 — 2026-07-29 (A2: revocable sessions)
**New module `sessions`** — instantly revocable admin sessions via a
`session_epoch` integer on the account row, signed into the session cookie and
compared on every request. Revoking is one UPDATE (`session_epoch + 1`), which
invalidates every cookie already issued for that account, on every device, with
no sweep job.

Chosen over a sessions TABLE deliberately: the table costs a write per request
(or stale data), a cleanup job, and another thing that can fail during login,
and buys only per-device revocation, which nothing here has asked for. The
epoch delivers the whole of A2 — "cut off the sessions this person already
has" — for one column. Adding the table later is still possible; the epoch
remains the "revoke everything" switch alongside it.

Existing cookies carry no epoch and read as 0, which is the migration default,
so adopting this does NOT log anyone out by itself. 5 tests.

Adopted by all nine, wired at each tool's single session chokepoint, with
revocation on: password change/reset (self-service and admin-set), account
deactivation, and role change.

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
