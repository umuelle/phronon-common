# Changelog — phronon_common

Shared package for the Phronon teaching tools. Consumers pin a **git tag** (see
each tool's CI: `phronon_common @ git+…@vX.Y.Z`), so a change here only reaches a
tool when its pin is deliberately bumped — never implicitly on the next restart.

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
