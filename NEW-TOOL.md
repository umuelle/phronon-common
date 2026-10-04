# Building a new tool on phronon_common

Written 3 October 2026 as the last step of the commons review; since
4 October 2026 the first step is one command (`server-ops/new_tool.py`, TO DO
FL-081). The worked example is `examples/minimal_tool/app.py`;
`tests/test_minimal_tool.py` runs it on every change to this package, so the
example cannot quietly go stale, and the scaffolder builds a new tool's
`app.py` from it.

## The rule in one sentence

A new tool **imports** the shared capabilities it needs and **owns** everything
about its own pages, data and workflow. It never starts as a copy of an existing
tool: copying Whiteout's account, participant or repair code is how the fleet
used to end up with nine diverging versions of one mechanism.

## What is shared, and what stays in the tool

| Shared (import it) | Stays in the tool (decide it there) |
|---|---|
| identity: `registry` | routes, templates, page wording |
| security: `security_headers`, `csrf`, `hosts`, `rate_limit`, `request_ip` | the database schema and migrations |
| sign-in: `passwords`, `lockout`, `twofactor`, `passkeys`, `sessions`, `account` | which accounts exist, roles, what a role may do |
| participants: `participant`, `joincode`, `kanon` | what is collected, scoring, results |
| data duties: `audit`, `exports`, `retention_heartbeat`, `once` | WHICH rows expire when, and what a deletion takes with it |
| mail: `emails`, `mail_diagnostics` | which events send mail, and their text |
| legal: `legal` (the router), `legal_content` (the loader) | its notice, `legal_content/notice.json` (what it collects, on what basis) |
| front end: `assets`, the masters in `shared_assets` | the tool's own CSS/JS |

Shared code never imports a tool. Where it needs the tool's database it takes a
**connection factory** you hand it (`AuditRecorder(get_db)`,
`once.once(get_db, …)`, `retention_heartbeat.record(get_db, …)`,
`passkeys.record_sign_in(get_db, …)`). Where tools legitimately differ, the
shared function takes a parameter; it never branches on a tool's name. If you
find yourself wanting `if tool == "mine"` in shared code, the difference
belongs in your tool.

## Steps

1. **Scaffold.** Work in a session that has `server-ops` and `phronon_common`
   (`server-ops/session.sh start <name> server-ops phronon_common`), then:

       server-ops/new_tool.py <key> --name "<Brand>" --dir <Folder> \
           --domain <domain> --port <port> [--locales en,de] \
           [--write-common] [--create-local-test-db]

   It refuses a folder that exists and any name, domain or port the fleet
   already uses; `--dry-run` lists what it would write. It creates
   `<Folder>/` as a git repository with one commit: `app.py` built from the
   example (the tool's key, its own `legal_content/notice.json`, `db.py`,
   templates and a backoffice sign-in at the fleet addresses), `schema.sql`
   and `migrations/001`, `ops/tool.json` (the facts server-ops reads, see
   below), a stub `ops/browser_journey.py`, the test kit's wrappers and the
   tool's own tests, `.github/workflows/ci.yml` on the two central actions,
   `.env.example` and `.env.test`, `TODO.md`, and the nginx site and
   systemd unit as TEMPLATES. `--write-common` adds the registry and
   shared-assets entries to the `phronon_common` beside it, uncommitted
   (it refuses a linked one). `--create-local-test-db` builds `<db>_test`
   on this Mac's test MySQL (README §9) and never touches an existing
   schema. In a session workspace, move the new folder into the primary
   workspace after `session.sh finish`, which leaves it in place.
2. **Identity, and the release it is.** The tool's entry in
   `registry.py` (key, folder, GitHub repo, unit, server path, port,
   entitlement key, brand, domain, locales) and its folder in
   `shared_assets.py` (`TOOLS`, `_TOOLS_WITH_PARTICIPANTS`) are printed by
   the scaffolder or written with `--write-common`. Both are a change to this
   package, so they go out as a release (below). The line the scaffolder
   prints for `server-ops/fleet.conf` lands with it:
   `server-ops/tool_registry_check.py` fails until the registry, `fleet.conf`
   and the tool's notice agree. **Land them when the tool passes the
   fleet-wide gates of deploy step 1b**: from then on every deploy in the
   fleet checks the new tool, and a fresh scaffold still fails three of them
   (retention, participant identity, audit wiring; TO DO FL-087). Until then
   keep both on the session branch, where the tool's own suite passes; its
   CI stays red on the identity test until the release. The notice lives in the tool,
   `legal_content/notice.json` (since v1.69.0; `legal_conf.py` is frozen for
   rollbacks and takes no new tool).
3. **Accounts.** The scaffold signs in with `passwords`' rules, `lockout`,
   `sessions` (the epoch and the role-aware age) and `CookieSigner`, and it
   refuses an account with two-factor switched on. Before the first deploy
   that sign-in is replaced by `account_kit`, which serves sign-in (password,
   code, passkey), sign-out, the reset links, authenticator setup, recovery
   codes, passkeys, the Manage account page, the administrator's two-factor
   reset and the gate for a temporary password or an un-enrolled
   administrator, with the fleet's lockout, rate limits and messages: build
   an `AccountKit` adapter (Moral Mirror's and Drawbridge's app.py are the
   two worked examples, one with an app-wide CSRF dependency, one with
   per-form checks), mount `build_account_router(...)` and install
   `account_gate(...)` as middleware. The tool keeps its own
   `backoffice/login.html` and `backoffice/password_reset.html`. Admins must
   use two-factor.
4. **The tool itself.** Sessions, the participant pages, the public join
   sheet at `/share/<code>`, retention (`retention.py`), `/about` and
   `/llms.txt` from a `ToolPresentation` entry, the `/accessibility`
   statement, and the notice's real text (reviewed before anything is
   published). The tool's `TODO.md` lists them; `ops/tool.json` leaves
   their sections empty rather than declaring exceptions, so the gates that
   read them (`retention_contract_check.py`, `share_card_layout_check.py`,
   `audit_wiring_scan.py`) say what is missing.
5. **Tests.** The fleet invariants come from `phronon_common.testing`; the tool
   keeps thin wrappers. `server-ops/fleet_testkit_check.py <dir>` lists the
   wrapper files every tool must carry and fails a tool that re-implements
   what the kit owns. The scaffold has the conftest (with
   `run_lock.hold_the_test_database(session)`), the baseline, identity,
   shared-assets and CSRF wrappers; the account, password-form, mail and
   machine-facing ones come with those features. The stub browser journey
   fails on purpose until the participant flow exists, so CI's journey step
   and deploy step 1d are red until then.
   A tool that gains its own `static/css/backoffice.css` enrols it for
   frontend-only releases: `frontend/contract.json`, `frontend_assets.install(app,
   templates, BASE_DIR)` and `"frontend_bundle": frontend_assets.active_bundle()`
   in /health (the baseline's `check_the_tools_stylesheet_ships_through_frontend_bundles`
   refuses less; the scaffold has no such file yet).
6. **The server, by hand.** The scaffolder prints each of these and installs
   none: the databases `<db>` and `<db>_test` with their users, built from
   `schema.sql` (the `_test` one before the first deploy), the `.env`, the
   service user `svc-<key>` and the unit, `requirements.lock` generated on the
   server, DNS, the nginx site and its certificate (then
   `server-ops/nginx_mirror_check.py --write`), the GitHub repository. Then
   `./deploy.sh <key>` from the primary workspace runs every gate.
7. **Preview.** `server-ops/preview.py <key>` works once the tool is in
   `fleet.conf`; the scaffolder prints its `.claude/launch.json` entry.
8. **Before calling it done:** `server-ops/closing_audit.py` and
   `CHANGE-CHECKLIST.md`, like any change.

### What server-ops knows about the tool: `ops/tool.json`

Each tool carries its own facts for the gates (FL-080): its test schema, the
`.env.example` contract, the audit scan's files and tables, the session
verifier, and for a teaching tool retention, participant policy, the probe
admin row, the share card and mutation-probe targets. `server-ops/tool_manifest.py`
describes the format; `./tool_manifest.py --file <Folder>/ops/tool.json`
checks a new tool's manifest before its registry entry exists.

## Changing the shared package because of the new tool

The registry entry is always such a change. Sometimes the new tool also needs
something the shared package does not offer yet: add it as a parameter or a
new function, never as a branch on the tool's name. Either way, prove it in
every tool before tagging:

    server-ops/common_candidate_matrix.py <commit>

Then tag it, set the fleet's one pin (`PHRONON_COMMON_TAG` in
`server-ops/fleet-pins.env`, since 4 October 2026), and run
`server-ops/common_release.sh publish <tag>`, `verify <tag>`, `activate <tag>`
and `refresh <tag>`; `common_release.sh status` must report every worker on
the new release. README §3 and the header of `common_release.sh` have the
reasons for each step.

## What the review decided stays local (do not "harmonize" these)

- **Repair and manual entry.** Whiteout, Layoff and Polarity Profiler share a
  documented behaviour contract, not an implementation: their data, scoring and
  privacy rules differ for good reasons.
- **Scoring, consent, deletion rules and which events send mail.** Each tool's
  own decision, recorded in its notice.
- **Authentication policy details** such as the hub's mandatory two-factor.
