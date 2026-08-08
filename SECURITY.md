# Security policy

## Supported versions

Pre-1.0. Only the most recent minor release receives security
attention. Once we tag 1.0.0, this section will spell out a real
support window.

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

- Issues that require the attacker to already have `User.admin`
  privileges (you can already do anything as admin)
- Self-XSS in the web UI from a same-origin user pasting attacker
  content into a textarea they own
- Denial-of-service from very large audit runs (we'll add rate
  limits to integrations as they land)

## Built-in safeguards

- Data at rest is AES-256-GCM encrypted (`app/core/encryption.py`)
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
