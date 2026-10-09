# phronon_common

The shared package for the nine Phronon teaching tools. Each tool is its own
repository, deployed on its own, so anything they must agree about lives here
and is consumed by a **pinned git tag** — never implicitly on the next restart.

```
phronon_common @ git+https://github.com/umuelle/phronon-common.git@vX.Y.Z
```

`server-ops/check_common_pin.py` compares that pin across CI, every repository
and the tag checked out at `/var/www/phronon_common`, which is what production
imports. One version, everywhere, or the deploy stops.

## What is in here

### Platform

| Module | Purpose |
|---|---|
| `access_log` | keeps bearer tokens out of the access log |
| `assets` | cache-busting query strings derived from the file, not from a person |
| `frontend_assets` | a tool's own `backoffice.css` from an immutable bundle: the app's half of the frontend-only release path |
| `csrf` | `CSRFProtection` + `CSRFMiddleware` |
| `hosts` | the Host names a tool answers to, derived from its notice |
| `legal` / `legal_conf` | the shared legal pages: one router, nine tools |
| `rate_limit` | in-app sliding-window rate limiting |
| `security_headers` | `SecurityHeadersMiddleware` (the `csp=` argument is required) |
| `routing` | `answer_head`: read-only GET routes answer HEAD (link scanners), writing GETs never do |
| `sessions` | instantly revocable admin sessions (`session_epoch`) |
| `signing` | signed-cookie helpers (itsdangerous) |

### Accounts and access

| Module | Purpose |
|---|---|
| `account` | self-service account management — the parts that must not differ |
| `account_kit` | the account ROUTES, pages and gate from a per-tool adapter: sign-in, sign-out, reset links, code prompt, authenticator setup, recovery codes, passkeys, Manage account, the admin two-factor reset, and the must-change / forced-enrolment gate (FL-083: Moral Mirror, Drawbridge) |
| `adminroutes` | finds admin-only routes that are not gated on the admin role — in `app.py`'s text, or (`assert_live_admin_routes_are_gated`) in the running app, routers included |
| `lockout` | the fleet account-lockout policy |
| `passwords` | the fleet password policy (minimum 12, no composition rules) |
| `provisioning` | the hub → tool account-provisioning contract |
| `twofactor` | TOTP second factor for admin logins, standard library only |
| `audit` | the admin audit trail |
| `request_ip` | whose address a request is from, behind the trusted proxy (re-exported by `rate_limit` and `audit`) |

### Participants, data and retention

| Module | Purpose |
|---|---|
| `participant` | one participant identity, resume and withdrawal mechanism |
| `joincode` | collision-checked, unambiguous join codes |
| `kanon` | k-anonymity display decisions — demographic-only suppression |
| `exports` | spreadsheet formula-injection escaping (`csv_safe`) |
| `retention_heartbeat` | last-successful-run heartbeat for the retention workers |
| `emails` | branded transactional-email building |
| `mail_diagnostics` | the live sample-mail run (`scripts/send_test_emails.py`): where sample mail may go, and whether to send at all. Was `testing.mail_harness` (still importable) |

### Front-end masters

`shared_assets` is the manifest: which master exists, where its copy belongs in
each tool, and which tools carry it. The masters themselves sit beside it —
`design-tokens.css`, `backoffice-nav.css`, `backoffice-core.css`,
`share-card.css`, `two-factor.css`, `actions.js`, `bulk-select.js`,
`dashboard-table.js`, `rank-a11y.js`, `share-card-download.js`,
`svg-charts.js`, `users-password.js` — and they ship in the
wheel, so a tool can compare its copy against the real master.

Copy them out with `server-ops/sync_shared_assets.py --write`. Never edit a
tool's copy: the fix would reach one tool and miss eight.

### The test kit — `phronon_common.testing`

Fleet invariants implemented once, as plain functions and mixins that raise
`AssertionError`. **Nothing here imports pytest** — this package is installed in
every production venv — and the pytest wiring stays in each tool's own `tests/`
wrapper, so a tool cannot quietly stop running a check while its CI stays green.

| Module | The invariant |
|---|---|
| `passwords` | the policy has one home, on the server and on the page |
| `csrf_fetch` | every `fetch()` that POSTs sends the token where this tool reads it |
| `manage_account` | the Manage account page: wiring and the guards that make it safe |
| `account_kit` | a tool mounting `account_kit` answers each of its routes once, with no stale template copies, and keeps its own sign-in and reset pages |
| `email_delivery` | what the messages say, and whether they actually go out |
| `fleet_baseline` | routes answer, login round-trips, anonymous visitors stay out, the stylesheet ships through bundles |
| `run_reporting` | an unrecognised skip fails the run where green is a gate |
| `head_safety` | no GET route that writes answers HEAD, every read-only GET route does |
| `run_lock` | one test run per test database at a time; a second run waits, then stops red |
| `undefined_names` | names a module reads but never binds |

## Using it from a tool

Starting a NEW tool: read `NEW-TOOL.md` and begin from `examples/minimal_tool/app.py`.

Install the pinned tag, as CI and the server do:

```bash
pip install "phronon_common[web] @ git+https://github.com/umuelle/phronon-common.git@vX.Y.Z"
```

The `web` extra pulls FastAPI, Starlette and Jinja2, which `csrf`, `legal`,
`rate_limit` and `security_headers` need. The rest of the package is
framework-agnostic and needs only `itsdangerous`.

For local work the sibling checkout is enough: every test file that imports the
kit adds the workspace root to `sys.path` when `phronon_common/` sits beside the
tool, because the tool venvs do not pip-install it.

## The rules

1. **Only what is identical everywhere.** Tool-specific logic stays in the tool.
   The fleet keeps its real differences; what it does not keep is nine private
   copies of one rule.
2. **Nothing is promoted without the gate that stops it drifting back.** Each
   extraction ships with a `server-ops` check: `fleet_testkit_check.py`,
   `sync_shared_assets.py`, `backoffice_css_dead_rule_check.py`,
   `package_build_check.py`, `check_common_pin.py`.
3. **A tag, ten pins, then the server checkout** — in that order, or `deploy.sh`
   refuses. The version in `pyproject.toml` is the tag you are ABOUT to create.
