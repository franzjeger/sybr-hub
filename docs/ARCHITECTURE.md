# Architecture

Module layout and the reasoning behind it. For wiring individual upstream
systems see [`INTEGRATIONS.md`](INTEGRATIONS.md).

## Shape

Sybr HUB is a single FastAPI process with a SQLite database. Everything runs
on the operator's own host: there is no cloud component, no message broker,
and no background worker fleet.

```
main.py                     entry point — reads SYBR_HUB_* env vars, runs uvicorn
app/
  web/                      HTTP layer
    server.py               create_app(): middleware, exception handler, routers
    middleware/             auth (JWT + RBAC), rate limiting
    routes/                 auth, hub, vpn, fortigate, unifi
  core/                     cross-cutting concerns, no HTTP knowledge
    auth.py                 password hashing, JWT, sessions, user CRUD
    rbac.py                 per-customer access checks
    database.py             schema migrations, connection pool
    encryption.py           AES-256-GCM at rest, master key in the OS keyring
    credentials.py          per-customer secrets in the OS keyring
    customer.py             multi-tenant customer registry
    validation.py           input validators for values reaching a shell or device CLI
    config.py               paths, branding, app settings
  services/                 device and tunnel access
    vpn_manager.py          profile CRUD and connection state
    vpn_backends/           wireguard, openvpn, fortigate_ipsec, azure
    ssh_connection.py       SSH with trust-on-first-use host-key pinning
    fortigate_api.py        FortiGate REST + CLI-over-SSH
    unifi_api.py            UniFi controller and Site Manager
    dns_checker.py          SPF / DKIM / DMARC / MTA-STS over live DNS
    remediation.py          per-customer remediation tracking
  modules/                  audit collectors
    m365_audit/             26 sections, CIS / NIST CSF / ISO 27001 mapped
    fortigate_audit/        policy and admin audit
    unifi_audit/            device, firmware and subnet scanning
  integrations/             write-side clients (autotask, itglue, myitprocess, rmm)
  reports/                  Jinja2 templates + WeasyPrint PDF generation
  models/                   Pydantic request/response and domain models
```

## Layering

Dependencies point inward: `web` → `services`/`modules` → `core`. Nothing in
`core` imports from `web`. The audit collectors know nothing about HTTP and
can be driven from a script.

Function-local imports appear throughout. A few are load-bearing — `core.auth`
and `core.encryption` are mutually dependent — but most are historical. Prefer
module-level imports in new code: a deferred import hides a missing dependency
until the feature is exercised, which is how four modules stayed absent from
this repo while appearing to work.

## Request path

An authenticated request passes through, outermost first:

1. **RateLimitMiddleware** — per-IP budget, so a flood is rejected before it
   costs a database round-trip. Stricter budget for `/api/auth/login`,
   `/api/auth/setup` and the VPN endpoints.
2. **AuthMiddleware** — extracts the JWT from the `Authorization` header or
   the `access_token` cookie, rejects blacklisted tokens, rejects tokens whose
   session has been revoked, loads the user onto `request.state`.
3. **Route dependencies** — `require_role(...)` for a role floor,
   `require_customer_access(...)` for routes carrying a `{customer_id}`.
4. **Handler**.

Errors raised as `ToolkitError` subclasses are mapped to their declared status
codes by a handler registered in `create_app()`.

Public paths bypass step 2 entirely and are listed in one place,
`middleware/auth._PUBLIC_PATHS`. That list is the only sanctioned way to open
a route up; a test asserts every other route carries an auth dependency.

## Authentication

- Argon2id password hashing (t=3, m=64 MiB, p=4).
- JWT access tokens (60 min) and refresh tokens (30 days), HS256, signed with
  a secret generated per install and stored encrypted in the database.
- Sessions are rows in `sessions`. An access token carries its session id, and
  the middleware rejects a token whose session is gone — that is what makes
  "log out everywhere" immediate rather than eventual.
- Revoked tokens go in an in-memory cache and the `token_blacklist` table, so
  a restart does not resurrect them.
- Tokens are also set as `HttpOnly` cookies with `SameSite=Strict`. There is
  no separate CSRF token; `SameSite` is the defence for the cookie path.

## Authorization

Two independent checks:

- **Role floor** — `viewer < technician < admin`.
- **Customer scope** — a user reaches a customer if they are an admin, hold
  the `users.all_customers` grant, or have a matching `customer_access` row.

Both are applied by `require_customer_access(min_role)`. Accounts created
after schema version 14 start scoped; accounts that predate it were migrated
with the blanket grant so nobody lost access on upgrade.

## Data at rest

- **SQLite** (`msp_toolkit.db`) holds users, sessions, VPN profiles, audit
  metrics and caches. Schema changes are numbered migrations in
  `core/database.py`; the runner retries a migration whose version bump failed,
  so every migration body must be safe to run twice.
- **Encrypted files** hold per-customer config, certificates and the activity
  log. AES-256-GCM with a magic header, so plaintext and encrypted files can
  coexist during migration.
- **OS keyring** holds the master encryption key and per-customer API tokens.
  The master key is additionally backed up to three locations, wrapped with a
  machine-derived passphrase.

## Connection pooling

`get_db()` serves connections from a pool keyed on **both** the database path
and the running event loop. Both parts matter:

- aiosqlite dispatches results back to the loop that created the connection,
  and more than one loop is routine — a test client drives the app on its own
  loop while the caller uses another.
- aiosqlite starts one **non-daemon** thread per connection. An undisposed
  connection therefore blocks interpreter exit. Every disposal path terminates
  the thread: `close()` where a loop is alive, `abandon()` where it is not.

If you add code that opens connections outside `get_db()`, make sure it closes
them. A leaked connection does not fail loudly; it hangs shutdown.

## Testing

`pytest`, `asyncio_mode = auto`. The suite covers parsers, encryption, RBAC,
migrations, the connection pool and the whole web layer.

Two conventions worth keeping:

- **Verify a regression test by breaking the code.** Several tests here
  initially passed against the unfixed code — a coverage check that walked the
  wrong route structure, a pagination test seeded in the wrong order. A green
  test proves nothing until you have watched it go red.
- **Guard the guard.** Where a test enumerates something (routes, migrations),
  assert the enumeration is non-trivial, so an upstream change cannot make it
  pass vacuously.
