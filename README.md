# phronon_common

Small shared package for the Phronon teaching tools — the genuinely-common,
framework-agnostic plumbing, so each tool stops copy-pasting (and slowly diverging)
the same code. See `MoralMirror-Development-Concept.md` §1.9.

| Module | Purpose |
|---|---|
| `kanon` | k-anonymity display decisions — **demographic-only** suppression (class totals & randomized conditions always show) |
| `joincode` | collision-checked, unambiguous join codes |
| `signing` | signed-cookie helpers (itsdangerous) |
| `security_headers` | `SecurityHeadersMiddleware` |
| `csrf` | `CSRFProtection` + `CSRFMiddleware` (configurable session cookie) |
| `rate_limit` | in-memory sliding-window `RateLimitMiddleware` |

## Use it from a tool

During development the simplest path is an editable install into the tool's venv:

```bash
pip install -e ../phronon_common
```

Moral Mirror also adds the parent `4a_Webprojects` dir to `sys.path` as a fallback
(see `Moral-mirror/config.py`), so `import phronon_common` works without the install.

**Rule:** only put here what is *identical* across tools. Tool-specific logic stays
in the tool. Moral Mirror is the first consumer; migrate the other tools opportunistically.
