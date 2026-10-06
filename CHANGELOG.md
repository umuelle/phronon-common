# Changelog — phronon_common

Shared package for the Phronon teaching tools. Consumers pin a **git tag** (see
each tool's CI: `phronon_common @ git+…@vX.Y.Z`), so a change here only reaches a
tool when its pin is deliberately bumped — never implicitly on the next restart.


## 1.78.0 — 2026-10-06

The contract steps of FL-080 and FL-083: every tool's LIVE commit now uses the
new shapes, so the old ones go. FL-083 expanded in 1.75.0; FL-080 in each
tool's own tests, live in all nine since 6 October. With them, the complete
audit vocabulary.

- **`shared_assets`:** `ONLY_FOR`, `TOOLS`, `assets_for(tool)` and
  `drifted(tool, dir)` are removed. Which masters a tool carries is its own
  `ops/tool.json` (operations.shared_assets), read by
  `server-ops/sync_shared_assets.py` and each tool's
  `tests/test_shared_assets_match.py`; the module keeps `ASSETS`,
  `master_path()` and, as prose, why a tool carries fewer (FL-080).
- **`account_kit`:** `account_kit_v1.py` (the frozen 1.74.0 kit that served an
  adapter in phase 1's shape) is deleted, with the phase-1 fields
  `register_failure`, `error_status`, `login_rate_limit` and
  `AccountTables.last_login_at`. `AccountTables.transaction`,
  `set_pending_cookie`, `not_an_admin` and `after_two_factor_reset` are
  required again. The switches `password_change_checks_confirmation` and
  `sign_in_page_shows_messages` are removed and their behaviour is the only
  one: a password change checks the confirmation and refuses the current
  password, and the sign-in page shows the keyed `?msg=`/`?err=` texts. Moral
  Mirror and Drawbridge set neither (FL-083 (c), (g)).
- **`testing.account_kit`:** `kit_routes()` is the whole kit's route set;
  `sign_in=True` is still accepted, `sign_in=False` raises. `PHASE_1_MODULE`
  is gone. `testing.manage_account` drops `KIT_V1_PY`.
- **`testing.split_app`:** `mock.patch.object(view, name, ...)` restores
  every module on exit. It deletes the name and sets it again, because the
  view finds names through `__getattr__`; the delete took the name out of
  every module and the set then raised. The view now puts a name it deleted
  back where it was (FL-089).
- **`audit.ACTIONS` is complete** (TO DO FL-089): every action name a tool or
  the account kit writes, 79 in all, grouped by topic. It held 18 while the
  fleet wrote about 60. New: `audit.SYNONYMS`, the names one tool wrote for an
  event the vocabulary names otherwise (`class_anonymized`, `session_deleted`,
  OrgDesignSim's `scenario_*`, ...) with the name to use; both stay listed,
  because stored rows keep the name they were written with. Nothing at runtime
  reads either; server-ops/audit_wiring_scan.py (deploy step 1b) refuses a tool
  that writes an unlisted name, or a synonym it did not already write.

## 1.77.0 — 2026-10-05

- **`testing.split_app`:** a tool's tests after its `app.py` is split into the
  standard layout (FL-089). `view(app, root)` is one namespace over the split
  modules: reading a name finds the module that defines it, and a patch
  (`monkeypatch.setattr(app, "send", fake)`) reaches every module bound to the
  same object, so a test can never silently stop faking because the caller now
  looks the name up elsewhere. `install()` puts the view in place of `app` for
  suites that `import app` at the top; `install_on_import()` does it on the
  first import, for a conftest that must not import the app. The view refuses
  reads from the tool's own runtime code: Whiteout's retention.py reached
  `app._exercise` through a lazy `import app`, which the split would have
  broken in production while every test passed. `runtime_source(root)` /
  `runtime_files(root)` are every runtime module, app.py first, for source
  checks.
- **`testing.head_safety`:** a GET branch that always returns ends what a GET
  can reach (Layoff's round-2 door renders on GET; only its POST admits), and
  a function defined inside a handler is reached through its calls, not
  walked (Controversy Generator's reset handler defines `_mark_used` and calls
  it on POST only). `problems(..., cookie_gated={path: reason})` lets a GET
  that writes keep HEAD when the write needs a sign-in or a participant's
  cookie, which a scanner never sends, and the link is one scanners see (the
  fleet's dashboard address, OrgDesignSim's identity page); a declared path
  that stops writing, or is no GET route, is a problem, and a reason is
  required.
- **`testing.csrf_fetch.app_source` and `testing.manage_account`** read every
  runtime module (app.py first) where they read app.py alone: after a split
  the CSRF check and the account handlers live in core.py and
  routes_accounts.py.

## 1.76.0 — 2026-10-05

- **`routing.answer_head(router_or_app, unsafe_paths=...)`:** one rule for HEAD
  in every tool. Read-only GET routes answer HEAD, so corporate link scanners
  (SafeLinks, Zscaler, FortiGate) do not see 405; the GETs that write are named
  and keep GET only, because a HEAD probe runs the handler and would perform
  the write (Whiteout's resume-link bug). Eight tools carried their own loop,
  and a loop over `app.routes` stops reaching routes once they move into an
  included router: apply this to each router before `include_router`. Prepares
  the fleet-wide `app.py` split (FL-082).
- **`testing.head_safety`:** Whiteout's guard for the whole fleet.
  `problems(app, tool_root)` reads the routes from the RUNNING app (included
  routers too) and a call graph over the tool's runtime modules and this
  package: a GET that writes and answers HEAD, or a read-only GET that does
  not, is a problem. A write is a write helper called by name, with literal
  SQL decided by its first word, hidden SQL counted as a write unless the
  function fetches rows, the tool's `db.py` judged at the call site, and only
  the branches a GET request can take. Calibrated on the fleet: Whiteout's
  hand-kept list reproduced exactly; Polarity Profiler, Inequality and the hub
  clean; 13 writing GETs in five tools to be named or fixed as each adopts it.

## 1.75.0 — 2026-10-05

- **Runs the code that is live (expand, then contract).** An adapter in phase
  1's shape (it passes `register_failure`: Moral Mirror's and Drawbridge's
  code before their phase-2 deploys) is served by `account_kit_v1`, a frozen
  copy of 1.74.0's kit, so moving the fleet to 1.75.0 changes nothing for
  them until they deploy phase 2. `AccountKit` is keyword-only so phase 2's
  new fields can be absent in phase 1's shape; a mixture of the two shapes is
  refused. `testing.account_kit` and `testing.manage_account` read whichever
  generation a tool mounts (`kit_routes(sign_in=True)` for phase 2). Found by
  the candidate matrix: the first 1.75.0 commit (07d98b2) made the live code
  fail at import (`last_login_at`). Delete `account_kit_v1.py` once no tool
  mounts the kit in phase 1's shape (TO DO FL-083).
- **Review fixes before release (5 October 2026), each with a test that fails
  without it:** the code prompt refuses a locked account (a right code no
  longer signs it in) and budgets guesses per account; a right password no
  longer clears the failure count while a code is owed (someone holding the
  password could re-enter it between code guesses and never reach the lock);
  failures are counted with one atomic increment (parallel failures counted
  as one); a reset link is claimed by a conditional UPDATE whose row count
  decides, and only for an active account; sign-out also clears the pending
  sign-in and the unconfirmed authenticator secret; the gate opens exact
  paths and paths below them (a bare prefix let `/backoffice/accounts...`
  through); an unknown or deactivated address costs a bcrypt check like a
  wrong password. Phase-1 adapters keep working unchanged: the new routes
  switch on only for an adapter that declares them.
- **The account kit serves the rest of the account code (TO DO FL-083).**
  New routes: `GET/POST /backoffice/login` (password, then the code prompt or
  a session), `POST /backoffice/logout`, `GET/POST /backoffice/password-reset`
  (ask for a link, set the password) and `POST
  /backoffice/users/{user_id}/reset-two-factor` (an administrator clears
  another account's second factor); every GET answers HEAD. New
  `account_gate(kit)`: the must-change and forced-enrolment middleware a tool
  installs where its own was. New `reset_token_hash(raw)`. The sign-in and
  reset pages stay the tool's own templates (`backoffice/login.html`,
  `backoffice/password_reset.html`), rendered with a fixed context.
- **The policies are the fleet's (owner's decision, 4 October 2026):
  Drawbridge's rule wherever the pilot tools differed.** (a) Every failure
  (password, code, passkey) counts by `lockout`. (b) A re-shown form answers
  400. (c) Sign-in: five a minute per address, one budget with the passkey;
  a locked account refused (429) before its password is read; "Invalid email
  or password." for an unknown, wrong or deactivated account. (d) Reset: five
  per five minutes per address; no link for a deactivated account; 400 for a
  request that is neither step; a completed reset leaves a lockout to run
  out. (e) Sign-out needs a session and its own token.
- **The forced-enrolment gate covers the account page (MM-007, DB-007).**
  Both tools' gates exempted it because it is on the must-change list, so an
  administrator without an authenticator could change their name and
  sign-in address.
- **Adapter changes (breaking for the two kit tools, which move with this
  release).** Removed: `register_failure`, `error_status`, `login_rate_limit`
  (decided points). Added: `set_pending_cookie`, `not_an_admin`,
  `after_two_factor_reset`, `reset_token_hours`; `AccountTables` gained
  `transaction` (required), `reset_tokens`, `reset_token_owner` and
  `reset_token_spent` (a flag, or a timestamp when the name ends in `_at`);
  `last_login_at` is renamed `clock` and also stamps a reset link's expiry.
  Differences kept as they were, each documented: `csrf_field_required`,
  `signed_in_redirect_status`, `drop_dead_session_cookie`,
  `sign_in_page_shows_messages`, `must_change_allows_two_factor`,
  `gate_account`. The sign-in page renders during a database outage (the
  session lookup failing counts as signed out there only).
- **`testing.account_kit`:** the route list includes the new routes;
  `assert_the_tool_keeps_its_entrance_pages` checks the two templates the kit
  renders exist, carry `csrf_token` and post to the kit's paths.
  **`testing.manage_account`** reads the kit's gate lists for a kit tool.
- Tests: `tests/test_account_kit.py` 45 → 73: the new routes driven, a
  refusing CSRF hook on every POST, each of (a) to (e), each new field, the
  gate (lists, hook, fail-open, the account page, must-change before
  enrolment). Suite: 502 passed.

## 1.74.0 — 2026-10-04

- **`frontend_assets`: every tool's own `backoffice.css` can ship without a
  full deploy (TO DO FL-078).** The pilot ran in Layoff alone, in a module of
  its own; the owner did not want one tool shipping its stylesheet
  differently from the rest. The module moved here unchanged in behaviour:
  `install(app, templates, BASE_DIR)` wraps the `asset` global (enrolled
  files come from the active immutable bundle), adds the
  one-bundle-per-request middleware and the `/frontend/<id>/<path>` route;
  `active_bundle()` feeds /health. The bundle folder is
  `/var/www/.phronon-frontend/<registry service>`. A tool without
  `frontend/contract.json` is unaffected. The web framework loads only inside
  `install`.
- **`/frontend/` is public** in `security_headers.PUBLIC_PREFIXES`, so a
  bundle keeps its year-long immutable caching instead of no-store.
- **`fleet_baseline.check_the_tools_stylesheet_ships_through_frontend_bundles`:**
  a tool with its own backoffice.css must enrol it, install the module, link
  the active bundle on the login page, serve it as immutable and name it in
  /health. Checked against a scratch bundle folder, so it runs anywhere. The
  hub has no such file and passes.

## 1.73.0 — 2026-10-04

- **A malformed passkey is refused, never a 500 (FL-086).** `passkeys.
  verify_registration` and `verify_authentication` caught py_webauthn's
  "invalid response" errors but not its parse errors (`InvalidJSONStructure`,
  `InvalidCBORData`, ...), so broken JSON or nonsense CBOR with a valid
  challenge ended in a server error, in all nine tools: when adding a passkey
  (signed in) and when signing in with one (anonymous, but only with a real
  credential id, since the tool looks the passkey up first). Both now catch
  `WebAuthnException`, the base of everything py_webauthn raises, and answer
  with the usual `PasskeyError` refusal. Test:
  `test_a_malformed_credential_is_refused_at_both_steps` (six broken variants
  of a real credential at each step; red before the fix).

## 1.72.0 — 2026-10-04

- **The account kit (TO DO FL-083, pilot).** New `account_kit.py`:
  `build_account_router(AccountKit(...))` serves the routes an account holder
  uses on themselves — the code prompt after the password (`/backoffice/verify`),
  setting up / replacing / switching off the authenticator and new recovery
  codes (`/backoffice/two-factor`), the five passkey routes, and the Manage
  account page (`/backoffice/account`, `/name`, `/email`, `/email/confirm`,
  `/password`, plus an optional old password address). Its four pages ship in
  `account_templates/` (package-data) and render inside the tool's own
  `backoffice/base.html` once `install_templates(env)` has run. The tool
  supplies an `AccountKit` adapter: its tables and DB helpers
  (`AccountTables`), its session, pending-login and enrolment cookies, its
  `render` and CSRF hook, its audit recorder, mail module, lockout policy and
  rate limit, and the few policies in which the two pilot tools differed
  (`error_status`, `password_change_checks_confirmation`,
  `password_form_required`, `must_change_url`, `legacy_password_path`,
  `AccountPageLayout`), each documented as deliberate or as an accident kept so
  that adopting the kit changes nothing. The kit names no tool; a test checks.
  Moral Mirror and Drawbridge adopt it; the other seven are untouched.
  `ACCOUNT_MESSAGES` / `ACCOUNT_ERRORS` are the fixed `?msg=` / `?err=` texts.
- **Every kit page answers HEAD as it answers GET.** Mail scanners and proxies
  probe a link with HEAD first, and the address-change confirmation is a mailed
  link. The tools add HEAD in a loop over `app.routes`, which on FastAPI 0.139
  never reaches an included router's routes, so the kit adds it to its own GET
  routes. Found in review: without it each kit page answered HEAD with 405.
- **Identifier checks match the whole name** (`account_kit` and `once`):
  `re.match` with `$` accepted a trailing newline (`"admins\n"`); both use
  `fullmatch` now. Only tool constants reach them.
- **`testing.account_kit`:** a kit tool answers each kit route exactly once
  (a leftover copy in app.py would silently win or lose) and carries no stale
  or shadowing copy of the kit's templates.
- **`testing.manage_account` reads kit tools where the code now lives:** a
  route body is looked up in the kit when app.py has none, the pages are the
  kit's templates, and the account page's row is followed from the adapter's
  `current_account=`. Tools without the kit are read exactly as before.
- **`tests/test_import_boundaries.py`:** `account_kit` is web plumbing and
  reaches py_webauthn through `passkeys`, by design.
- Tests: `tests/test_account_kit.py` (44): templates parse and keep the
  password-form, CSRF and recovery-code rules; every route driven against
  MySQL tables named like no real tool's, through a stand-in adapter, including
  the passkey one-use rule and a refusing CSRF hook on every POST.
## 1.71.0 — 2026-10-04

- **`adminroutes`: the role-gating check can ask the RUNNING app (FL-082).**
  `assert_live_admin_routes_are_gated(app, prefixes, guards, allow=(),
  guard_dependencies=())` takes the FastAPI app instead of `app.py`'s text: it
  walks every route the app dispatches — routers included, prefixes applied —
  and reads the handler's source wherever it is written. "Gated" means what it
  meant: a declared guard string in the handler, not narrowed by an `and`; the
  live check also accepts a declared guard DEPENDENCY on the route, its router
  or the app. Why: a route that moves out of `app.py` into a router module does
  not fail the text check, it silently leaves it. OrgDesignSim, which split its
  `app.py` into router modules the same day, uses the live check; the
  source-level `assert_admin_routes_are_gated` is unchanged for the other eight.
  New helpers: `app_routes(app)` (every dispatched APIRoute with its effective
  path, methods and dependencies), `live_admin_routes`,
  `unguarded_live_admin_routes`. Tests: `tests/test_adminroutes_live.py`,
  including the mutation (an ungated route in an included router is refused).
- **`testing.fleet_baseline` walks included routers.** `walkable_get_routes`
  looped over `app.routes` and kept the APIRoutes; on FastAPI 0.139
  `include_router()` adds ONE node holding the router, so every included route
  was invisible to the walk — the shared legal pages in all nine tools, and
  every route of a tool whose routes live in routers. It now uses
  `adminroutes.app_routes`. **Effect on every tool when its pin is bumped:** the
  "every parameterless GET answers" and "anonymous is kept out" walks now also
  request the legal pages (`/impressum`, `/legal-notice`, `/privacy`,
  `/cookies`, `/terms`, `/legal`, `/imprint`, and `/de/privacy`, `/de/cookies`
  where served).
- **`testing.manage_account`: `APP_SOURCES`.** A tool may list its source files
  (default: `app.py` alone, as before); handlers are found by route in
  whichever listed file holds them, `@router.<verb>(...)` as well as
  `@app.<verb>(...)`, and never read across a file boundary.
- **`testing.passwords`:** the three server-side checks accept one path or a
  list of paths.

## 1.70.0 — 2026-10-04

- **`testing.run_lock`: one test run per test database at a time (FL-085).**
  A tool's `<db>_test` schema is written by its suite, and on the owner's Mac
  also by the candidate matrix, the browser gate, the coverage diagnostic and
  the mutation probe, from several sessions at once. Two Layoff suites started
  together failed 9 to 12 tests each, a different set every time, and passed
  on a rerun. `hold_the_test_database(session)`, called from a conftest's
  `pytest_sessionstart`, holds the MySQL named lock
  `phronon-test-run.<DB_NAME>` on a connection of its own until the process
  ends; a second run waits and says so (`PHRONON_TEST_RUN_WAIT`, default
  600 s), then stops red before its first test. No DB_NAME or no reachable
  database: no lock, and the run goes on as before. MySQL drops the lock with
  the connection, so a killed run leaves nothing behind. No pytest import.
- Tested against real MySQL, including a real pytest run that is stopped
  (exit 2, no test ran, the reason printed) and a holder killed with SIGKILL.

## 1.69.0 — 2026-10-04

- **Each tool owns its legal content.** New `legal_content.py`:
  `load_legal_config(tool_key, path)` reads a tool's own
  `legal_content/notice.json`, checks it (schema version, the tool's key,
  every required field and type, no unknown fields, English everywhere and
  German wherever the tool serves German except the source credits, the
  cookie tables' shape and order, an explicit notice version) and returns a
  fresh object. `build_legal_router(key, config=...)` and
  `render_legal(..., config=...)` render from it; one loaded object feeds both
  the pages and the notice version an app records. A broken file stops the app
  at startup. Why: 13 of the last 39 releases changed `legal_conf.py`, 8 of
  them nothing else, and each was a fleet release for one tool's sentence.
- **Backward compatible.** Without `config=` the router still reads
  `legal_conf.TOOLS`, now FROZEN (a test fails on any change to it) for tools
  that have not migrated and for rollbacks. All nine published notices render
  byte for byte as before (72 pages compared, incl. Decision Room).
- **`testing.legal_content.LegalContent`:** the content checks that ran here
  over all nine entries (forbidden strings, Impressum, Art. 13 essentials,
  German tables, promise counts, session lifetimes) now run in each tool's own
  suite against its own file.

## 1.68.0 — 2026-10-03

- **Drawbridge notice `2026-10-03-db-comparison` (TO DO DB-003, owner-approved
  wording).** The research-row bullet in the retention section now says what a
  kept row is used for: it counts toward the "All previous responses" totals an
  educator can open next to their own session's results; no single response is
  shown and small gender/age groups are hidden. Wording only; archived in
  `CONSENT-WORDING-ARCHIVE.md`.

## 1.67.0 — 2026-10-03

- **The backoffice nav bar grows instead of clipping** (`backoffice-nav.css`).
  The bar had a fixed 58px height and only the phone rule (≤720px) let it
  grow, while its links wrapped. Between 721px and about 1200px a tool with
  many links stacked them in two or three 58px rows centred in a 58px bar:
  Whiteout at 1024px showed four links above the viewport and one below the
  bar; Polarity Profiler, Layoff and Inequality did the same at 800px. Live
  since the shared nav (29 July). The bar is now `min-height` with
  `flex-wrap`: the account area drops to a second row first, then the links
  take a row of their own. A bar that fits stays exactly 58px. On a wrapped
  bar `scroll-padding-top` is larger so keyboard focus is not hidden under it.
- **Phones: a long account address no longer pushes "Log out" off the
  screen.** The account row may shrink and cuts the address with an ellipsis.
- Gate: `server-ops/browser_submit_check.py` measures every nav control at
  800, 1024 and 1180px, with the real and with a long account address.

## 1.66.0 — 2026-10-03

- **A process holds its release's `.release` file open** (`_RELEASE_MARKER`),
  so `server-ops/common_release.sh status` reads the release each worker
  ACTUALLY loaded from /proc/<pid>/fd instead of inferring it from start
  times. A checkout or a wheel has no `.release`; nothing is opened.
- **CI runs the DB-backed tests against MySQL and they may not skip.** The
  workflow has a MySQL service and sets `PHRONON_REQUIRE_DB=1`;
  `tests/conftest.py`'s `test_db` fixture fails instead of skipping there.
  Until now the tests proving the passkey one-use rule and `once()` under real
  row locks skipped on every CI run. `mysql-connector-python==9.7.0` joins
  requirements-test.txt (the fleet's version).

## 1.65.0 — 2026-10-03

- **`testing.repair_contract`** (contract version `2026-09-25`): the README's
  repair contract as three assertions each tool runs on its own routes:
  `assert_refusal_changes_nothing` (snapshot every row the route could touch,
  attempt, require a refusal, compare), `assert_audit_never_names` (no
  participant address in ANY column of the audit rows; the educator may be
  named), `assert_page_never_shows` (a value promised private appears nowhere
  in the page, hidden fields included). Shared as behaviour, not code: each
  tool keeps its routes, SQL and audit actions. First use found Layoff writing
  participant addresses into three audit actions.
- **`NEW-TOOL.md` and `examples/minimal_tool/app.py`:** how a new tool stands on
  this package (what to import, what stays in the tool, the seven steps, and
  what the review decided must stay local). The example imports no tool's code
  and `tests/test_minimal_tool.py` runs it (headers + CSP nonce, the shared
  legal pages, CSRF on a POST, the Host check, and that it loads no tool
  module), so a wiring change here breaks the example's test, not the next new
  tool. No runtime code changed.

## 1.64.0 — 2026-10-03

- **One release per process.** On first import the package resolves its own
  location (`__path__`, `__file__`) through any symlink. On the server
  `/var/www/phronon_common` becomes a symlink to an immutable release
  directory (`server-ops/common_release.sh`); with this, a worker's later
  imports and every template it reads come from the release it started with,
  however the symlink moves. Before, a worker loaded part of one version at
  startup and the rest, lazily, from whatever the shared checkout held later.
  A checkout or a wheel is unaffected (the path is already real).
  New test `tests/test_release_pin.py` swaps a symlink under a running process.

## 1.63.0 — 2026-10-03

Boundary cleanups from the commons review of 3 October 2026. No behaviour
changes; every old import keeps working.

- **`mail_diagnostics`** is the live sample-mail harness, moved out of the test
  kit: eight production scripts (`scripts/send_test_emails.py`) imported
  `phronon_common.testing.mail_harness`, so a test-helper change could change
  what a production script loads. `testing.mail_harness` is now the SAME
  module object under its old name (a `sys.modules` alias, not a re-export),
  so patching through either name patches the code that runs.
- **`request_ip`** holds `client_ip` and `default_trusted_proxies`, with no web
  framework import. `audit` took `client_ip` from `rate_limit`, so writing an
  audit row loaded FastAPI and Starlette's middleware. `rate_limit` and
  `audit` re-export the identical objects.
- **`account.EMAIL_CHANGE_HOURS`**: the address-change lifetime moved from
  `emails` to the account policy it belongs to; `emails` imports it (and
  `emails.EMAIL_CHANGE_HOURS` still answers). Account policy no longer depends
  on the mail module.
- **`hosts`** reads the tool's domain from `registry` instead of `legal_conf`.
  Same answer: `server-ops/tool_registry_check.py` fails when the two disagree.
- **New test `tests/test_import_boundaries.py`** imports every module alone in
  a fresh interpreter and fails when a production module loads the test kit,
  a non-web module loads FastAPI/Starlette, anything but `passkeys` loads
  py_webauthn, or `mail_diagnostics` loads anything outside the stdlib.

## 1.62.0 — 2026-10-03

Two guarantees tightened after a review of the shared code (3 October 2026).
Each has a test that failed before the change.

- **A passkey challenge signs in once.** Deleting the challenge cookie did not
  stop a replay: whoever held a copy of the cookie and the signed answer could
  send both again within five minutes, and synced passkeys (iCloud, Google)
  keep no counter that would refuse it. Verified in all nine tools before the
  fix. The cookie now carries its issue time (`open_sealed_challenge`), and
  `record_sign_in(get_db, passkey_id, sign_count, issued_at)` stores the use
  with ONE conditional UPDATE that succeeds only if the challenge was issued
  after the passkey's last use. No new table, no migration. Tools must call it
  in place of their own `UPDATE passkeys SET sign_count …` and refuse the
  sign-in when it returns False. `open_challenge` is unchanged for
  registration. A challenge issued in the same second as the passkey's last
  use is refused (whole seconds; no person is that fast), and cookies sealed
  by 1.61.0 are refused once, as if expired.
- **`once` re-arms only what it claimed.** With several keys it claimed in
  one UPDATE that could not say which rows it had won, so a failed send
  released every row, including rows another worker had claimed and was
  still mailing about. It now claims key by key in one transaction (sorted,
  so overlapping batches cannot deadlock) and releases only its own rows. The
  module docstring now says what it does not promise: a crash after claiming
  sends nothing, and an unknown send outcome may be sent again.

## 1.61.0 — 2026-10-03

- **Polarity Profiler loses the old name below the waterline (PP-004, owner
  3 October 2026).** `registry` PP entry: `service` and `server_path` are now
  `polarity-profiler` / `/var/www/polarity-profiler`, and `legacy_domains` is
  empty: `lsr-profiler.org` and its redirect are retired (no QR posters in use).
- **PP notice `2026-10-03-pp-name`.** The provenance line says "The Polarity
  Profiler framework…" instead of "The LSR framework…", and the cookie table
  names the renamed two-factor cookies `pp_pending_totp` / `pp_pending2fa`
  (EN and DE). Wording only; archived in `CONSENT-WORDING-ARCHIVE.md`.
- Comments and docstrings say Polarity Profiler where they said LSR.

## 1.60.0 — 2026-10-03

- **One set of entry addresses (owner's decision).** `registry.BACKOFFICE_LOGIN`
  (`/backoffice/login`) and `registry.BACKOFFICE_DASHBOARD`
  (`/backoffice/dashboard`) for the eight teaching tools, `HUB_LOGIN` /
  `HUB_DASHBOARD` (`/admin/login`, `/admin`) for the hub, and
  `ToolIdentity.login_path` / `.dashboard_path`. Until now two tools signed in
  at `/backoffice` (and 404ed the login address), two listed sessions away from
  the dashboard address, and two 404ed `/backoffice`; every server-ops script
  kept its own table of who was where.
- **Test kit:** `FleetBaseline.check_the_entry_addresses_are_the_fleet_ones`
  (signed out: the login page answers at the fleet address with a password
  field; `/backoffice`, `/backoffice/` and the dashboard address all lead to it).
  `LOGIN_PATH` / `LOGIN_POST` now default to the registry value.

## 1.59.0 — 2026-10-02

- **Passkeys (FL-065).** New `passkeys.py`: the only caller of py_webauthn
  (`webauthn==3.0.1`, now in the `web` extra). Owner's decisions: a passkey signs
  in on its own (no password, no code) and counts as two-factor, so every
  ceremony requires user verification; password + code stays the fallback;
  administrators still enrol an authenticator app. Discoverable credentials,
  attestation `none`, relying party = the tool's own host. The challenge lives
  in a signed 5-minute cookie (`passkey_challenge`) bound to its purpose. New
  shared script `passkeys.js` (all nine) wires the account-page and login-page
  blocks by data attributes. `testing/soft_authenticator.py` is a software
  authenticator with a real P-256 key, so each tool's route tests run the real
  verification.
- **Mail:** `send_two_factor_confirmation` gains `passkey_added` and
  `passkey_removed`; their wording explains what a passkey can do instead of
  reminding about recovery codes.
- **Legal:** every notice lists passkey data under educators (EN; DE for Layoff,
  Polarity Profiler and Whiteout) and the `passkey_challenge` cookie;
  `last_updated` 2026-10-02 everywhere. `notice_version` unchanged: nothing about
  participants changed.
- **`backoffice-core.css`:** `.bo-passkeys` list and `.bo-inline-form`.
- **Test kit:** `manage_account` now fails a template that lists recovery codes
  without the download lock (FL-066 deleted the last unlocked list, on all
  eight account pages), and resolves `{{ … }}` placeholders in form actions to
  route parameters.

## 1.58.0 — 2026-10-02

- **Recovery codes must be downloaded before the user can continue.** New shared
  script `recovery-codes.js`, shipped to all nine tools through
  `shared_assets` (the hub included). On the page that shows freshly made
  recovery codes it adds a Download button that saves them as
  `<tool>-recovery-codes.txt`, and it keeps the "I have saved my recovery
  codes" button locked until the download has happened. Modelled on GitHub's
  enrolment, at the owner's request; Download is the only unlock (owner's
  choice, copying does not count). The file is built in the browser from the
  codes on the page, so nothing serves the codes a second time. Without
  JavaScript the button is never locked.
- **`emails.send_two_factor_confirmation(..., event)`**: one mail for the three
  changes an account holder makes to their own two-factor: `enabled`,
  `replaced` (new authenticator) and `codes_regenerated`. It asks them to check
  that the codes are saved, points to the account page to make new ones (the
  fleet cannot show codes again, unlike GitHub), and doubles as the "this was
  not you" alarm. Never carries a code or the secret. A failed send is logged
  with the domain only and never raised.

## 1.57.0 — 2026-10-01

- **`once`: a background side effect happens at most once, however many
  workers run the job.** Every tool runs its background jobs in each uvicorn
  worker, and the workers start them together after every restart. On
  1 October Drawbridge mailed an educator the same retention warning twice,
  0.17 s apart: it sent first and stamped afterwards. Controversy Generator
  and Moral Mirror had the same code, and Polarity Profiler sent all four of
  its background mails that way. Whiteout had found and fixed the race on
  25 August, and the fix stayed in Whiteout.

  `once.once(get_db, table, column, keys, action, mark=…, restore=…)` claims
  the row(s) with a conditional UPDATE, runs the action only if this caller
  changed them, and puts the mark back if the action fails or raises. Marks:
  a timestamp (`NOW`, `UTC_NOW`; "unmarked" = NULL), a value (a deadline, a
  flag; "unmarked" = any other value), over one row or a batch. It reads
  `cursor.rowcount` itself, because several tools' `execute` helpers return
  `lastrowid`, which is 0 for every UPDATE. Every background mail in the
  fleet now goes through it, including in the tools that run one worker.

## 1.55.0 — 2026-09-22

- **`.print-hide` goes back inside `@media print`.** Promoted into
  `backoffice-core.css` on 26 August with the other 228 byte-identical rules,
  it arrived WITHOUT its wrapper: `.print-hide { display: none !important }` at
  the top level of a sheet that loads last, with `!important`. For twenty-seven
  days it hid on screen what it was written to hide on paper.

  Whiteout was the tool that paid: its session page carries the class on
  seventeen wrappers, and the educator lost **Presentation mode**, **Download
  PDF**, **Download charts & tables**, twelve per-chart **Download PNG**
  buttons, and the small-group "best member" figures FL-045 shows the educator
  while withholding them from the room. No other tool uses the class on a page
  that loads this sheet — the join sheets carry it too, but with the correctly
  scoped copy in `share-card.css`.

  Nothing caught it in four weeks of green deploys. Every test asserted the
  buttons were in the HTML, which they were; the dead-rule gate compares rule
  bodies, and the bodies matched — it was the SCOPE that was dropped, and no
  gate read scope. Two now do: `server-ops/fleet_print_scope_check.py` (deploy
  step, refuses a hide-on-paper class that hides outside a print scope, and any
  shared rule promoted out of a media block) and the real-browser journey, which
  asks the browser whether the educator can SEE the three export controls.

  The six tools that also declared the rule locally, correctly scoped, drop
  their now-redundant copy; Inequality and Polarity Profiler load this sheet and
  no `backoffice.css` of their own, which is why the rule stays here.

## 1.54.0 — 2026-09-21

- **`suite_link` becomes `name_suite`, and now covers the Terms text too.**
  Renamed because it never only governed a link: the Terms page names the
  suite twice in its own prose — "<tool> and the other Phronon tools are
  teaching and discussion aids", and "The Phronon name, wordmark and logo …
  are protected works". A property that must not be traceable to its siblings
  was still naming them in the body while the footer stayed quiet.

  With `name_suite: False` those two sentences speak about the property alone.
  Default unchanged; the other nine render exactly as before.

  Found by a test asserting no page on Moral Mirror's Decision Room door
  mentions Phronon — the footer had been fixed in 1.53.0, and the Terms page
  failed anyway. Option B (legal pages indexable, the rest not) makes this
  matter: an indexed page naming the suite is a searchable route back.

## 1.53.0 — 2026-09-21

- **A legal footer can leave out the suite line.** Every property still ends
  its legal pages with "<tool> — part of Phronon"; one that sets
  `suite_link: False` in its `legal_conf` entry gets its own name alone.

  Moral Mirror's Decision Room door is the first to need it. That door exists
  so that naming the study does not shape the answers, and the footer put a
  live link to the hub on every legal page — where the hub describes Moral
  Mirror as "a modular ethics experiment … participants answer framed moral
  dilemmas under randomized conditions". Two clicks from a privacy notice to
  the hypothesis.

  What a reader is owed is the identity of the CONTROLLER, and the Impressum
  names it either way. The brand of the suite is not part of that.

  Default is unchanged, so the other nine properties render exactly as before.

## 1.52.0 — 2026-09-18

- **The full set of sample e-mails goes once a day per tool; later runs that
  day send one canary** (owner's decision). Live sending is not muted and never
  will be — receiving the mail is the proof that delivery works, and one real
  delivery still has to succeed on every run. What this stops is a tool
  deployed several times in one day spending the provider's entire daily budget
  on proving the same thing twenty times over: on 18 September that happened to
  Polarity Profiler, and every further deploy of it failed on
  `450 … Mail send limit exceeded`.

  `send_all(samples, recipient, project_root=...)` consults a `.last-full-mail-send`
  stamp beside the tool's code (git-ignored). Without `project_root` nothing is
  throttled, which is what each tool's `scripts/send_test_emails.py` passes when
  it is run by hand. A full set that had a failure is NOT recorded as done, so
  one bad day cannot leave a tool on canaries with nothing proved.

## 1.51.0 — 2026-09-18

- **`testing.mail_harness.load_project_env` fills gaps instead of overwriting
  the caller — it was repointing test runs at the LIVE database.** The function
  gives a hand-run pytest on the server the SMTP credentials systemd would
  otherwise inject, and it did that by writing every key of the tool's `.env`
  into `os.environ`. `DB_NAME` is one of those keys, and
  `server-ops/run_tests.py` deliberately sets `DB_NAME=<db>_test` before pytest
  starts, precisely so the deploy gate's suite cannot touch production. So on
  the server the first live-mail test in a run silently switched the whole
  process to the production database, and everything after it saw that name.

  Measured the day it was found: in Polarity Profiler, whose disposable-schema
  guards are evaluated per fixture rather than at collection, seventeen
  database-backed tests reported "skipped" on every deploy and had not executed
  on the server for months — inside a green result, because that skip reason was
  permitted until this morning. In the tools whose guards are module-level the
  tests ran instead, and were spared writing to production only because their
  connection pool had been built earlier in the run against the test schema.
  That is luck, and not the sort worth keeping.

  The fix is `os.environ.setdefault`: what the caller set survives, and the mail
  settings the caller does not pass are exactly the ones still missing.
  `tests/test_mail_env_never_repoints_the_database.py` holds it.

## 1.45.0 — 2026-09-05

- **Polarity Profiler's cheap identifiers finish their rename (PP-004).** The
  fleet key becomes `polarity` and the entitlement key `polarity_profiler`;
  `github_repo` becomes `polarity-profiler`. Because the registry is the one
  place that says what a tool is, changing `entitlement_key` here also changed
  the hub's card key, `fleet_client`'s row and the environment variable the
  provisioning guard looks for — `PROVISION_SECRET_POLARITY_PROFILER` — without
  another file being edited.
- **What deliberately keeps `lsr`, recorded in TO DO PP-004:** the systemd unit,
  the server path, the service user, the database and its user — invisible to
  every participant and educator, and a rename costs a maintenance window and,
  for the database, a dump and restore of live participant rows. Also
  `lsr-profiler.org` and its redirect, which printed classroom QR codes point
  at, and the stored `lsr-research-…` / `lsr-notice-ack-…` version strings,
  which are written into participant rows and resolve to archived wording.
- The rollout put the provisioning secret under BOTH names at once so the hub
  and the tool kept talking through the deploy.

## 1.44.0 — 2026-09-04

- **Inequality Explorer's retention promise, corrected (IE-002).** The notice
  said that without research consent "your demographic and reflection answers
  are deleted outright" — true, and incomplete. The RESPONSE itself stayed: the
  session link, the exact timestamp and all ten quintile answers, indefinitely,
  in a cohort of twenty with a named educator. Someone who DECLINED research use
  was left more identifiable than someone who agreed, which is the opposite of
  what a consent question is for.
- It now says: without consent, **the whole response is deleted** — name,
  address, answers, demographics, reflection. With consent, the record is kept
  but cut loose from the session and coarsened to the month, and the
  participant's deletion link keeps working on it.
- `notice_version` for this tool becomes `2026-09-04-ie002`; the other seven
  participant tools stay on `2026-09-04-identity`. Both wordings are in
  `server-ops/CONSENT-WORDING-ARCHIVE.md`, so a stored version still resolves to
  the sentence that was shown.

## 1.43.0 — 2026-09-04

- **`audit.AuditRecorder` — the audit trail, bound once per project.** Every
  tool wrapped `record()` in a private `_audit(...)` supplying its own
  connection factory and, in one case, its proxy configuration: nine copies of
  the same four lines, differing only in the name of the callable they closed
  over. 128 lines of wrapper become 69 lines of binding, and the four distinct
  connection callables and three proxy configurations stay declared rather than
  flattened.
- Keyword-only after the action, deliberately: the wrappers did NOT agree on
  what the second positional argument meant — Controversy Generator's was
  `admin`, everyone else's was `request` — so a shared positional signature
  would have rebound arguments silently. No call site in the fleet passes one
  positionally, which is what made this safe.
- **`provisioning.require_internal_secret()` and `secret_env_var()`.** Seven
  tools guard `/api/internal/schedule` with the same eight lines and spell out
  their own environment variable name (`PROVISION_SECRET_DRAWBRIDGE_DRAMA` and
  so on). The name is derivable from the registry's entitlement key — verified
  against all seven, zero mismatches — which is the same key the hub already
  uses to look the secret up.

## 1.42.0 — 2026-09-04

- **One duration per tool, and the hub reads it** (owner, 4 September 2026).
  The hub's cards and each tool's own /about disagreed about every one of the
  eight, and two of those were contradictions rather than formatting: Layoff
  said 90–120 min on the hub and "~20 minutes" on its own page, and
  OrgDesignSim said ">30 min" against "Multi-week". The owner settled the
  values; `duration` is now a single field the hub chip and /about both read.
  OrgDesignSim's "Multi-week" had been describing the SIMULATED 52 weeks under
  a heading that means real time. Whiteout's "35–90 minutes depending on the
  plan (compact / full / with Group Ranking 2)" loses its plan clause, because
  the hub renders this in a chip.
- **"Students" stays in the audience labels; "participants" is for
  participant-facing text and the backoffice** (owner). The labels say who a
  tool is FOR, which is a different question from what the people in a session
  are called. Two tools had drifted the other way and are corrected; the hub's
  Drawbridge blurb ("student-facing") and Moral Mirror blurb ("students answer
  framed dilemmas") were the only two places the word described the people, and
  those now read as the tools themselves already did.
- **The hub's last two per-tool tables are gone.** `Phronon/app.py`'s card list
  and `Phronon/fleet_client.py`'s FLEET both build from the registry now. They
  were the reason the hub could link Polarity Profiler at its retired domain in
  one file while using the current one in the other, and why its cards
  described five tools in wording those tools had moved on from. The only
  per-tool fact `fleet_client` still owns is which tools have participant
  sessions to report.

## 1.41.0 — 2026-09-04

- **`machine_facing.py` and a populated `ToolPresentation`** (external plan,
  item 3). Every tool assembled its own JSON-LD graphs, `/llms.txt` and About
  context from a private `_TOOL` dict — roughly 560 identical lines across the
  eight, plus nine robots handlers written out by hand. Two of that dict's
  seven keys, `name` and `url`, were never presentation: they are identity, and
  they are gone from the tools entirely.
- **Verified against production, not against a reading of the source.** The 32
  live artefacts — `/llms.txt`, `robots.txt` and the JSON-LD from `/` and
  `/about` for every tool — were captured before the change and the builders
  reproduce all of them byte for byte.
- **The robots builder takes ORDERED rules**, not two lists. The fleet's files
  genuinely differ: six tools and the hub put `Allow: /` first, Drawbridge and
  Layoff put their exclusions first, and the original standard is
  first-match-wins. Reshuffling nine live files to make one function tidier
  would be changing what they say in order to share how they are built. Every
  file comes out unchanged — except one.
- **Layoff Exercise was inviting crawlers into its educator sign-in.** It
  excluded `/admin/` and not `/backoffice/`, and it has both, so it was the one
  property in the fleet whose backoffice was welcome in the index. Nothing
  leaked — the page is behind a login either way — but it behaved unlike the
  other eight and nobody could see it, because robots.txt is read by crawlers
  and not by people. `missing_private_prefixes()` is what found it and what
  keeps it found.
- Each tool carries `tests/test_machine_facing_is_shared.py`: its presentation
  is in the registry, its robots rules cover its own private prefixes, and it
  has not started rebuilding the graph builders.

## 1.40.0 — 2026-09-04

- **`registry.py` — one place that says what a tool IS** (external plan, item
  2). A tool is identified by six strings — fleet key `lsr`, workspace
  directory `polarity-profiler`, GitHub repository `lsr-profiler`, systemd unit
  `lsr-profiler`, entitlement key `lsr_profiler`, brand "Polarity Profiler" —
  and nothing held them together, so code took whichever was nearest. That is
  how a fleet test derived a tool's identity from its checkout directory and
  turned CI red on all nine repositories: GitHub checks `ControversyGenerator`
  out as `controversy-generator`.
- **`ToolIdentity` holds the operational facts; `ToolPresentation` is separate**
  and holds none of them. Deployment mechanics stay in `fleet.conf`;
  `server-ops/tool_registry_check.py` compares the two so they cannot disagree
  in silence.
- **It found two live disagreements on its first run, both the same shape:** a
  RETIRED domain used where the current one belongs. `Phronon/app.py` linked
  Polarity Profiler at `lsr-profiler.org` while `fleet_client.py`, in the same
  repository, used `polarity-profiler.org` — the hub disagreeing with itself
  about one tool. And that tool's sample-mail script built reset links on the
  retired domain. Both corrected. The registry models the distinction rather
  than flattening it: `canonical_domain` is the only address anything may build
  a URL on, `legacy_domains` is what nginx redirects from.
- Names work the same way: `display_name` ("Whiteout Exercise" — notice,
  e-mail, page titles) and `short_name` ("Whiteout" — the hub's card) are both
  accepted where a name is DISPLAYED and neither anywhere else. That asymmetry
  already existed; it is written down now instead of argued about.
- **`FLEET_TOOL_NAMES` is derived from the registry**, not listed a second time.
  A hand-kept copy is how five tools came to be missing a name from the e-mail
  leak check.
- Each tool also carries `tests/test_identity_matches_the_registry.py`, so its
  own CI — where server-ops is not checked out — fails on the push that makes
  its brand or its domain disagree.

## 1.39.0 — 2026-09-04

Guardrail and packaging debt, closed before more is shared (external plan,
item 1).

- **`shared_assets.py` — the front-end manifest moves into the package.** Which
  master exists, where its copy belongs in each tool, and which tools carry it,
  was known only to `server-ops/sync_shared_assets.py`, **which was wired into
  nothing** — not the deploy gate, not any CI workflow. Thirteen masters were
  kept in step by hand. The manifest is here now, and the checking runs in two
  places: `deploy.sh` runs the sync script READ-ONLY (never `--write`: a deploy
  that silently rewrote a tool's static/ would ship an unreviewed asset and
  dirty the other tools' working copies), and every tool's own suite carries
  `tests/test_shared_assets_match.py`, so drift fails on the push that caused
  it rather than at the next deploy.
- **The CSS and JS masters now ship in the wheel.** A tool cannot import a
  stylesheet, so the only way its CI — where the package comes from the pinned
  tag — can compare its copy against the real master is for the master to be
  packaged. `package-data` gained `*.css` and `*.js`.
- **`package_build_check.py` — the clean-wheel gate.** It builds from a COPY of
  the source tree (a leftover `build/` or `*.egg-info` makes setuptools ship
  files pyproject no longer declares — the first version of this gate passed
  while `phronon_common.testing` was deleted from `packages`), asserts every
  module, legal partial and master is inside the wheel, then imports all 34
  modules from an interpreter whose only path to the package is the unpacked
  wheel, run from outside the workspace so the sibling checkout cannot answer
  for it. Proven against both faults.
- **FastAPI, Starlette and Jinja2 are declared** as a `web` extra: `csrf`,
  `legal`, `rate_limit` and `security_headers` import them, and the package
  claimed only `itsdangerous`. The ten pins now install `phronon_common[web]`.
- **`__version__` is derived, not typed.** It read "1.15.1" while the fleet ran
  v1.38.0 — twenty-three tags behind — and the comment sitting next to it
  explained that no gate looks there, which is exactly why it drifted. One
  source now: `pyproject.toml`, which the pin gate already checks against the
  tag.
- **README rewritten** against the actual 34 modules, grouped, with the rules
  and the tag-and-pin ritual. It had said "Moral Mirror is the first consumer,
  migrate the others opportunistically" and pointed at a OneDrive path from
  before the workspace moved.

## 1.38.0 — 2026-09-04

- **The tool is called OrgDesignSim** (owner, 4 September 2026) — the spelling
  on its own logo. `FLEET_TOOL_NAMES` carried "Orgdesignsim", and so did the
  tool's `services/email.py`, its mail subjects, its page titles and the hub's
  fleet listing. All 138 occurrences of the brand across the fleet now read
  OrgDesignSim.
- **What deliberately did NOT change: the identifiers.** The local repository
  directory, the systemd unit, the server path, the database and the fleet key
  stay `Orgdesignsim` / `orgdesignsim` / `orgsim`, exactly as Polarity
  Profiler's service, directory and database stayed `lsr` when it was renamed.
  A dozen gates key their per-tool tables on the directory name; renaming that
  is its own change, with its own migration, not a side effect of a brand fix.
- The signed DPIA determination of 20 August keeps the name it was signed with.

## 1.37.0 — 2026-09-04

- **`testing/mail_harness.py` — the sample-mail harness.** Around each tool's
  own `_send_*` functions, `scripts/send_test_emails.py` carried 130 identical
  lines in all eight: the .env parser, the recipient allowlist, the "are we on
  the server" test, the send/skip/error decision, `send_all` and the CLI. Six of
  the eight were byte-identical; the other two differed only in comment wording.
  The scripts go from 3,320 lines to 2,010.
- Each script keeps a zero-argument wrapper of the same name for
  `load_project_env`, `running_on_server` and `live_sending_status`, because
  conftest and the e-mail contract reach for them on that module, by name. The
  skip reasons are unchanged to the byte: `_ALLOWED_SKIPS` recognises "Local
  working copy" and "SEND_TEST_EMAILS=0", and rewording either fails every
  tool's server run.
- **`FLEET_TOOL_NAMES` now lives with the harness**, which is what puts a brand
  name into a real message; `email_delivery` re-exports it. The scripts import
  it instead of keeping a copy, so the contract's assertion asks for identity
  rather than equality: a tool that goes back to its own copy fails even if the
  copy is correct that day.
- **Two front-end masters move in: `bulk-select.js` and `users-password.js`,**
  now in `server-ops/sync_shared_assets.py`. `bulk-select.js` had drifted into
  FIVE versions, each holding one real feature the other four never received —
  the base engine, Whiteout's `data-bulk-bar` auto-init, Moral Mirror's
  GET/field-name support, and Layoff's `data-bulk-confirm` with its `{n}`
  substitution. The master is the union: every addition defaults to what the
  base engine already did, and the auto-init finds nothing in the five tools
  that bootstrap from a template `<script>`. `users-password.js` had eight
  copies differing by one trailing comment.
- Verified: identical full-suite outcome in all nine; widening the recipient
  allowlist still fails every tool's suite; a drifted JS copy is still reported
  by the sync gate.

## 1.36.0 — 2026-09-04

- **`testing/run_reporting.py` — how a test RUN reports itself.** The last
  114 lines of every conftest.py were byte-identical in eight tools (the ninth,
  the hub, had 43 of them): the allowed-skip list, the hook that collects an
  unrecognised skip, the rule that a skip only fails the run where green is a
  GATE, and the test-summary e-mail. `tests/conftest.py` went from 2,310 lines
  across the fleet to 1,405.
- **The three hooks stay in each conftest**, because pytest finds them by NAME
  in the project's own conftest — and because a tool's own allowed skips belong
  in that project. Several are half of a matched pair with a reason string in a
  test file (Whiteout's `DISPOSABLE_DB_REASON`), and those comments moved with
  them, unchanged.
- Eight of the allowed skips are true in every tool and are `BASE_ALLOWED_SKIPS`
  here; a tool adds its own with `kit.BASE_ALLOWED_SKIPS + (...)`. Two tools —
  Moral Mirror and the hub — add none.
- The hub still sends no test-summary e-mail: it never had that hook, and this
  change does not add behaviour. Worth a decision separately.
- Verified: identical full-suite outcome before and after in all nine, the
  summary mail builds the same subject, body and URGENT headers per tool, and a
  skip with an unrecognised reason still fails the run where green is a gate.

## 1.35.0 — 2026-09-04

- **`testing/fleet_baseline.py` — the floor every tool stands on.** The four
  baseline checks (every parameterless GET route answers, the login form
  round-trips like a person uses it, anonymous visitors are kept out of
  protected pages, the security headers are on the page) were the same 173-line
  file in all NINE repos — the eight tools and the hub — differing in exactly
  three constants: the login path, the login POST path, and the protected
  prefixes. Those stay in each wrapper, which is now 72 lines.
- **This one covers the hub too.** Phronon has no participant flow and no
  password forms, so the five participant-facing kit tests do not apply there,
  but it is a FastAPI app with a login and protected pages like the rest.
  `fleet_testkit_check.py` now checks the baseline file in all nine and the
  other five in the eight tools.
- The checks RETURN a skip reason instead of skipping, because the kit must not
  import pytest; the wrapper owns the pytest verbs, and owns them visibly, so a
  skip is still reported at the line where it happens. `strict_here(__file__)`
  keeps the old rule intact: DB-backed failures are environmental on a laptop
  and behavioural on the server, where the deploy gate is the real run.
- Verified per tool: identical pass/skip outcome before and after, in all nine.
  Two revert checks against Whiteout proved the shared assertions still bite —
  removing `script-src` from the CSP argument, and adding an unguarded GET route
  under `/backoffice/` — and two more proved the gate catches a deleted wrapper
  and a forked one.

## 1.34.0 — 2026-09-04

- **`testing/email_delivery.py` — the e-mail contract.** 244 of each tool's
  ~330 lines were identical once the tool's own name and domain are
  substituted: the SMTP capture, the password-reset assertions, the sampler
  configuration and the live send. What stays local is the tool's name, its
  sender address, and the mail TYPES only it has.
- **It fixes a live defect, not only duplication.** `FLEET_TOOL_NAMES` existed
  in eight copies and **five had drifted**: they omitted "Whiteout Exercise"
  and repeated the tool's own name instead. The leak check is
  `[n for n in FLEET_TOOL_NAMES if n != TOOL_NAME]`, so those five had silently
  stopped checking for a Whiteout brand leak — the exact class of bug the check
  exists to catch. The canonical list lives here now; the five scripts are
  repaired, and a new assertion compares each script's list with this one, by
  NAME rather than order, so it cannot drift again.
- The seven parametrized "outside address" cases became one test that names
  every address that got through, rather than stopping at the first. That is
  why each tool collects five fewer tests: minus six from the collapse, plus
  the new fleet-list assertion. No assertion was lost.

## 1.33.0 — 2026-09-04

- **`testing/manage_account.py` — the Manage account contract.** 309 lines
  copied into eight tools in four versions; the four differed in exactly three
  things. Two are real and stay overridable: which template holds the backoffice
  nav (`base.html`, or `components/navbar.html` in Controversy Generator and
  Inequality), and which route resets another account's two-factor (Layoff
  administers accounts under `/admin/educators`, not `/backoffice/users`).
  - The third difference was **`NAME_FIELD`, which no copy has ever read** —
    Polarity Profiler was maintaining a different value for a knob nobody used.
    Dropped rather than carried forward.
  - Shipped as mixin classes so each tool subclasses them and keeps the ten
    original test groupings, and their incident docstrings, in its own suite.
    29 tests before, 29 after, in every tool.
- `server-ops/fleet_testkit_check.py` covers this file too: a tool that deletes
  it, or forks the route/SQL helpers back into itself, fails the deploy.

## 1.32.0 — 2026-09-04

- **`phronon_common.testing` — the fleet test kit.** The cross-cutting tests
  were copied, not shared: three were byte-identical in all eight tools, so a
  fix to one missed seven and a ninth tool would start with none of them. The
  password policy checks (server and template halves) and the fetch/CSRF
  scanner now live here as plain functions that raise AssertionError; each
  tool keeps a thin wrapper that points them at its own root.
  - **Nothing here imports pytest**, at module level or inside a function, so
    the kit costs every production venv nothing. The pytest wiring —
    parametrize, ids — stays local, which is also what keeps each tool's own
    CI running the check. `test_no_dead_or_undefined_code.py` over
    `undefined_names.py` was already built this way; this generalises it.
  - Genuinely per-tool declarations stay per-tool: `TOKEN_READ_FROM`,
    `ACCEPT_JSON_REQUIRED`, `CSRF_SCOPE_PREFIXES`, and whether the CSRF drift
    check reads the tool's own `app.py` or, for the three tools on the shared
    middleware, `phronon_common.csrf` resolved BY IMPORT.
  - Gate: `server-ops/fleet_testkit_check.py`, which fails a deploy if a tool
    deletes one of these tests or forks the scanner back into itself.
- **Packaging: the subpackage needed its own `package-dir` entry.** With only
  the root mapping, `pip wheel` produced a wheel containing no
  `phronon_common/testing` at all and said nothing — the tools would have
  imported the kit from the sibling checkout locally and failed in CI, which
  installs from the tag. Verified by unzipping the wheel and importing it from
  a clean venv, not by reading the config.

## 1.31.0 — 2026-09-04

- **The eight participant notices, corrected against what the code does.**
  `notice_version` `2026-09-04-identity` on all eight. An external review of
  the identity and retention waves found four notices describing something
  other than the running system, and this is the wording half of the fix
  (`server-ops/CONSENT-WORDING-ARCHIVE.md` carries the full per-tool record):
  - **Polarity Profiler (German)** — the erasure section still offered the
    report page as a deletion route, removed by migration 023; never named
    `/withdrawal-link`; and claimed no identifier survives the anonymisation
    deadline, which is untrue for a participant who consented to research use.
    It is now a translation of the English rather than an older text beside it.
  - **Inequality Explorer** — the retention section said a withdrawal "has to
    reach us before" the deadline while the erasure section on the same page
    said the participant's own link keeps working afterwards. Both are now
    true and distinguishable. The cookie table also gained `withdraw_once`
    (5 minutes), which was live and unpublished.
  - **OrgDesignSim** — the pass is 8 hours, not 24, in both places the notice
    said 24. The implementation moved with the fleet cookie in 1.30.0.
  - **Whiteout** — the erasure section named no recovery route, so a
    participant who lost the 7-day warning mail had none. It now points at
    `/withdrawal-link` in both languages.
  - **Moral Mirror** — new retention bullet: answers from an abandoned
    activity are deleted when the 8-hour pass expires (owner's decision).
  - **Layoff, OrgDesignSim, Whiteout** — the provision sections now say what
    the required address is for, and that it is used for nothing else.

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
