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
    static/                 the SPA; vendor/ holds the third-party JS and CSS
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
    m365_audit/             27 sections, CIS / NIST CSF / ISO 27001 mapped
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

## A refusal is not a zero

The rule the audit pipeline is built around, and the one most often broken
before it was written down. It applies at four places in a row, and the
failure looks the same at each: a collector cannot read something, the
absence is stored as an empty result, and everything downstream treats that
emptiness as a measurement of the tenant.

The shape it takes:

```python
except Exception:
    devices = []          # ← "we could not look" is now "there are none"
```

What that produced in practice: "Ingen Intune-enheter funnet" on a tenant
whose consent was fine and whose Intune service was simply not subscribed;
a CIS control recording a clean finding on evidence it had been refused;
"Custom banned password list is not configured" printed beside the 400 that
prevented the list from ever being read.

The six places, and what each must do:

1. **Collector.** Let `GraphPermissionError` reach the section, and write a
   `(not available)` block naming the cause. `GraphPermissionError` already
   separates a licence gap, a service refusal and a missing consent — see
   below. A section that could not read part of itself ends `FAILED`, even
   if the rest succeeded.
2. **Reader.** `_is_error_payload` blanks a stub before the parsers see it,
   which is what keeps a raw Graph status out of the customer report. Keep
   the `Error:` opening for anything a customer might see.
3. **Parser.** `_evidence_unavailable` recognises both shapes. Set
   `has_data=False` and carry the reason; never derive a count from a file
   that was not read.
4. **Scoring and controls.** Guard on `has_data` before scoring. A control
   with no evidence reports that it cannot verify — it does not pass and it
   does not fail.
5. **Baselines.** Every check in `app/baselines/*.json` declares
   `measured_when`. A check whose guard is false reports `not_measured`, and
   conformance is quoted over the checks that *were* assessed with the rest
   counted beside it. Nothing assessed at all gives `conformance_pct: None`,
   not `0` — zero conformance is a verdict and the absence of one is not.
6. **Drift.** `compute_drift` returns `None` totals, never `0`, when there was
   nothing to compare against. A first run, a predecessor that predates
   snapshots and a snapshot that will not decrypt all look identical to a
   clean diff otherwise — and "no policies were removed" is exactly the
   reassurance a reader acts on.

Layers 5 and 6 are belt and braces on each other by design: the drift check
in the baseline carries `measured_when: drift.measured`, *and* the field it
reads is `None` when unmeasured. Either alone would be correct. Both means
the next person to write a check cannot get it wrong by forgetting the guard.

There is a test at each boundary. When adding a collector, add one there too:
the mistake is easy to reintroduce and silent when you do.

### Telling refusals apart

A 401 or 403 from Graph is three different problems wearing one status code,
and each needs the opposite response:

| signal in the body | meaning | what to do |
|---|---|---|
| `Authentication_RequestFromNonPremiumTenant`, "premium licence" | the tenant lacks the Entra tier | buy or ignore; consent will not help |
| a `manage.microsoft.com` URL, nested `ErrorCode: Forbidden` | the service behind the endpoint declined | check the subscription, not the grant |
| anything else | the app registration is missing a role or its consent | grant it |

`GraphPermissionError` sets `is_licence_gap` and `is_service_refusal` from
the response body. Do not infer any of this from the status code alone: Intune
answers a tenant with no subscription with a 401 whose text is a Forbidden
from a different service entirely.

## Baselines, snapshots and drift

Three things that share one set of files.

**Snapshots.** Every audit stores the tenant's Conditional Access policies,
named locations and Intune profiles under `<run>/policy_snapshots/`, exactly
as Graph returned them, encrypted like every other artefact. The audit
evidence beside them is trimmed to a width a person reads, and a trimmed
policy cannot be put back — so the two files serve different readers and both
are kept. Restore is deliberately absent: it writes into a customer's tenant,
and every Graph permission this app asks for ends in `.Read.All`.
`tests/test_policy_backup.py` asserts that no route in that module is
anything but a GET.

**Drift** (`app/core/policy_drift.py`) compares a run's snapshots with the
newest *earlier* run that captured any — skipping empty ones, so one failed
audit does not cost the comparison. Only ids, display names and changed
*field names* travel; never field values, because a policy body carries group
memberships and exclusion lists and a drift summary is read in places a
policy dump should not appear.

**Baselines** (`app/baselines/*.json`) are what Sybr requires of a customer it
runs, as opposed to what CIS recommends in general. A baseline is data, not
code: a check names a dotted path through the report context, a comparison, a
severity, and one sentence of rationale written for the customer. Arguing
about a threshold does not mean touching the evaluator.

**No layer here emits prose.** A check returns a `reason_code` and the values
behind it; the report template and the browser build the sentence. The first
version wrote English sentences into `detail` while the baseline document
carried Norwegian-only titles, so one card showed both languages at once and
neither could be translated — and every i18n detector passed, because they
read JavaScript and this was a JSON document and a Python f-string. Titles and
rationales are `{"no": ..., "en": ...}`; `load_baseline` refuses a document
missing either.

To add or change a check:

1. Add it to the JSON with a `measured_when` guard naming the `has_data` flag
   (or equivalent) for the evidence it reads, and `title`/`why` in both
   languages.
2. **Bump `version`.** The version is what lets last year's report still be
   read against the requirements that applied then. Changing the checks
   without it silently rewrites old verdicts.
3. Run `tests/test_baseline.py`. It builds a real report context from an
   empty run and asserts every `path` and `measured_when` resolves — two
   checks in the first draft named fields that existed nowhere, and the guard
   would have reported them `not_measured` forever: safe, and silently
   useless.

A new reason code means a new entry in `REASON_CODES` in the module that
emits it, plus a `bl_`/`drift_` string in **both** `app/reports/i18n.py` and
`static/ui_i18n.json`, in both languages. `tests/test_i18n_coverage.py`
enforces all of that: an untranslated code renders as nothing at all, which is
worse than the wrong language.

`SYBR_BASELINE` overrides which baseline is the house standard. It is an
environment variable rather than a stored setting because reports are built
by the scheduler as well as by a request, and the two must not be able to
disagree about which standard judged a run.

Where it surfaces: the customer report carries a Sybr Standard section ahead
of the CIS one (what we require, then what the benchmark says) with drift
below it; the technical report carries drift with ids under Conditional
Access; the customer card shows conformance and the change list, reading the
same two endpoints the report reads.

## Which customer are we talking to

`active.txt`, the global config slot and the global certificate path together
answer "which tenant is this process working on". They are process-global,
stored on disk, and read by roughly two dozen routes — notes, tags, audit
scope, the dashboard, the IT-Glue and FortiGate lookups.

**A background job must never write them.** The scheduler used to: each
iteration switched the active customer, copied that customer's config and
certificate into the global slots, audited whatever the globals then said,
and restored the original at the end. For the length of a cycle — minutes per
tenant, hours in total — every technician's requests were reading a variable
the scheduler was rewriting. A note saved during a cycle landed on whichever
customer the scheduler had reached. And because an audit reads the customer
*name* and the customer *credentials* as two separate reads of that global, a
switch landing between them files one tenant's findings under another
customer's name.

The correct pattern is the one the bulk-audit route has always used, and it
needs no globals at all:

```python
full_cust = CustomerManager.get_customer(cust_id)
auth = get_auth_for_customer(full_cust, CustomerManager.get_cert_path(cust_id))
collector = AuditCollector(auth=auth, out_dir=make_output_dir(cust_name))
```

Everything downstream already takes the customer explicitly —
`make_output_dir`, `build_report_context` and the report/email step all do.
Use `get_auth_for_customer` rather than `AuthManager.from_config`; it is also
the only one of the two with a GDAP branch.

`tests/test_scheduler_isolation.py` makes `set_active`, `save_config` and the
certificate copy raise, so a background job that reaches for a global fails
loudly in CI rather than quietly in production.

**What this does not fix.** Two technicians still share one active customer:
switching customer is a global act, so notes, tags and the dashboard follow
whoever switched last. That is the product's current single-active-customer
model, and changing it means per-session customer context — an API change,
not a bug fix. The remaining window is click-versus-click and seconds wide,
where the old one was cycle-long.

## Front-end assets

`static/` is served by the app, not by a build step. Two things follow.

**No third-party CDN.** xterm, chart.js, marked, DOMPurify and the icon font
live in `static/vendor/` and are served from the app. A console holding every
customer's credentials should not execute script from a host outside the
tailnet, and the terminal and charts have to work during an outage, which is
when the operator needs them and when a route out may not exist.

**The cache key is a digest, not a version.** `sw.js` serves `/static/`
cache-first, so a changed file is only picked up when `CACHE_VERSION` changes.
That value is rewritten at request time from the app version plus a hash of
every asset `index.html` references — read out of the markup, so it cannot
drift from what the page actually loads. Do not add a hand-maintained list of
assets beside it.

## User-facing text

Every string a person reads goes through `t()` and lives in
`static/ui_i18n.json` in both languages — and the key has to *be* there.
`t('status_watch', 'Følg med')` renders the fallback when the key is missing,
so the Norwegian UI looks perfect while the English one says "Følg med".
Forty-five keys had accumulated that way, in both directions, with every
detector passing: they measure whether a string is routed through `t()`, not
whether routing it accomplished anything. A separate test now checks that
every key a script names exists in both languages.

Backend-generated text is not covered by any of the detectors, which read
JavaScript only. Anything a route or a core module returns for display must
carry a code the presentation translates — see the baselines section above. `tests/test_i18n_coverage.py` holds
the detectors and a per-script budget; all seven scripts read zero on all
three counts, and the budgets only ever go down.

The detectors are worth understanding before trusting them. Each has been
wrong in a way that made the codebase look clean: one looked at three of the
seven scripts, one required an æ, ø or å before calling a string Norwegian,
and one skipped any string containing the quote character it was not
delimited by — which is most of a file that builds markup. If a count reads
zero, confirm the detector can see the file before believing it.


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
