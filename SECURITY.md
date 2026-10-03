# Security policy

## Supported versions

Security fixes target the latest reviewed release. Identify an installation by
its exact source revision, dependency lock and image/wheel digest; a version
label alone may not identify older deployments.

## Reporting a vulnerability

**Do not open a public GitHub issue for security reports.**

Email <support@sybr.no> with:

- A description of the issue
- Steps to reproduce (or a PoC)
- Affected version / commit SHA
- Your name + how you'd like to be credited (or "anonymous")

You'll get an acknowledgement within 72 hours. We aim to ship a fix
within 14 days for high-severity issues; less urgent ones may take
longer but you'll get progress updates.

## Scope

In scope:

- Bypasses of `can_write`, `tenant_write`, MFA or session revocation, including
  attacks that start with an administrator role

- Anything that leaks one customer's data into another customer's
  view
- Anything that lets an unauthenticated user reach an authenticated
  endpoint
- Anything that creates an Autotask ticket or myITprocess
  recommendation without explicit operator action (this would
  violate a core product invariant — see [`ROADMAP.md`](ROADMAP.md))
- Path traversal, SSRF, deserialisation, command injection in any
  route under `app/web/routes/`
- Credentials or tenant-identifying data committed to the repository
  (see [`CONTRIBUTING.md`](CONTRIBUTING.md))

Out of scope:

- Self-XSS in the web UI from a same-origin user pasting attacker
  content into a textarea they own
- Denial-of-service from very large audit runs (we'll add rate
  limits to integrations as they land)

## Built-in safeguards

- Customer configuration and audit files use AES-256-GCM. SQLite still stores
  usernames, password hashes and operational metadata in plaintext; selected
  secret fields are encrypted. Protect the host and data-directory permissions.
- Format-3 backups encrypt every payload member, including the DB. Their
  filenames and manifest metadata remain visible; see [retention](docs/RETENTION.md).
- Local TOTP MFA, single-use recovery codes and five-minute step-up checks are
  available. Set `SYBR_REQUIRE_MFA=1` to require enrollment for privileged users.
- Master key lives in the OS keyring; authenticated multi-location backups are
  wrapped with an independent operator secret. The production unit receives it
  through a root-owned systemd credential, not a process environment value.
- Audit collectors refuse to fabricate a grade when blocking data
  is missing — they return grade `?` rather than guessing
- Integration write-side endpoints are guarded by FastAPI auth
  dependencies that scheduled-audit code paths can't satisfy

## Sensitive data in tracked files

Customer names, real tenant domains, internal hostnames, and
personal email addresses must never enter tracked content. The
`.gitignore` excludes the obvious traps; reviews should still flag
any leak.
