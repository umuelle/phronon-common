# Building a new tool on phronon_common

Written 3 October 2026 as the last step of the commons review. The worked
example is `examples/minimal_tool/app.py`; `tests/test_minimal_tool.py` runs it
on every change to this package, so the example cannot quietly go stale.

## The rule in one sentence

A new tool **imports** the shared capabilities it needs and **owns** everything
about its own pages, data and workflow. It never starts as a copy of an existing
tool: copying Whiteout's account, participant or repair code is how the fleet
used to end up with nine diverging versions of one mechanism.

## What is shared, and what stays in the tool

| Shared (import it) | Stays in the tool (decide it there) |
|---|---|
| identity: `registry` (+ `legal_conf` for the published notice) | routes, templates, page wording |
| security: `security_headers`, `csrf`, `hosts`, `rate_limit`, `request_ip` | the database schema and migrations |
| sign-in: `passwords`, `lockout`, `twofactor`, `passkeys`, `sessions`, `account` | which accounts exist, roles, what a role may do |
| participants: `participant`, `joincode`, `kanon` | what is collected, scoring, results |
| data duties: `audit`, `exports`, `retention_heartbeat`, `once` | WHICH rows expire when, and what a deletion takes with it |
| mail: `emails`, `mail_diagnostics` | which events send mail, and their text |
| legal: `legal` (the router) | the tool's entry in `legal_conf` (what it collects, on what basis) |
| front end: `assets`, the masters in `shared_assets` | the tool's own CSS/JS |

Shared code never imports a tool. Where it needs the tool's database it takes a
**connection factory** you hand it (`AuditRecorder(get_db)`,
`once.once(get_db, …)`, `retention_heartbeat.record(get_db, …)`,
`passkeys.record_sign_in(get_db, …)`). Where tools legitimately differ, the
shared function takes a parameter; it never branches on a tool's name. If you
find yourself wanting `if tool == "mine"` in shared code, the difference
belongs in your tool.

## Steps

1. **Identity.** Add the tool to `phronon_common/registry.py` (key, workspace
   folder, GitHub repo, systemd unit, server path, port, entitlement key, brand,
   domain, locales) and its entry to `legal_conf.py` (what it collects, the
   legal basis, cookies, retention). `server-ops/tool_registry_check.py` fails
   until the two agree with each other and with `fleet.conf`.
2. **Wiring.** Start `app.py` from `examples/minimal_tool/app.py`: middleware in
   that order, the legal router, `asset_url`, the audit recorder bound to your
   `get_db`. Read `SECRET_KEY` from the environment with no default.
3. **Accounts.** Use `passwords`, `lockout`, `twofactor`, `passkeys`,
   `sessions` and `account` for the backoffice sign-in; the tool owns its
   `admins` table and its routes. The entry addresses are fixed fleet-wide:
   `registry.BACKOFFICE_LOGIN` and `registry.BACKOFFICE_DASHBOARD`.
4. **Front end.** Register the tool in `shared_assets.ASSETS` / `ONLY_FOR` and
   copy the masters with `server-ops/sync_shared_assets.py --write`. Never edit
   a copied master in the tool; fix the master.
5. **Tests.** The fleet invariants come from `phronon_common.testing`; the tool
   keeps thin wrappers. `server-ops/fleet_testkit_check.py` lists the wrapper
   files every tool must carry (`tests/conftest.py`,
   `tests/test_fleet_baseline.py`, `tests/test_shared_assets_match.py`,
   `tests/test_identity_matches_the_registry.py`, and the account, mail and
   CSRF ones) and fails a tool that re-implements what the kit owns. Give the
   tool a disposable `*_test` schema (`.env.test`) before any DB test runs,
   and let its conftest hold that schema for the run
   (`run_lock.hold_the_test_database(session)` in `pytest_sessionstart`).
6. **CI and deploy.** Copy a tool's `.github/workflows/ci.yml` (MySQL service,
   schema from migrations, the `phronon_common` pin at the fleet's tag, the
   browser-journey action). Add the line to `server-ops/fleet.conf`, the nginx
   site, the systemd unit. `./deploy.sh <key>` then runs every gate.
7. **Before calling it done:** `server-ops/closing_audit.py` and
   `CHANGE-CHECKLIST.md`, like any change.

## Changing the shared package because of the new tool

Sometimes the new tool needs something the shared package does not offer yet.
Add it as a parameter or a new function, never as a branch on the tool's name,
then prove it in every tool before tagging:

    server-ops/common_candidate_matrix.py <commit>

Tag, bump the ten pins, `server-ops/common_release.sh publish <tag>` and
`activate <tag>`, deploy the fleet, and `common_release.sh status` must report
every worker on the new release. README §3 has the reasons for each step.

## What the review decided stays local (do not "harmonize" these)

- **Repair and manual entry.** Whiteout, Layoff and Polarity Profiler share a
  documented behaviour contract, not an implementation: their data, scoring and
  privacy rules differ for good reasons.
- **Scoring, consent, deletion rules and which events send mail.** Each tool's
  own decision, recorded in its notice.
- **Authentication policy details** such as the hub's mandatory two-factor.
