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

## What an account can reach

Roles were applied a route at a time. 84 of 331 endpoints carried a
`require_role`, the interface hid nothing at all, and the two facts compounded:
a viewer saw the whole menu, clicked into things, and met a wall — or met no
wall, because the route needing the check was one of the 247 without one.

Decorating the remaining 247 is 247 chances to forget one. `core/features.py`
names the *features* instead — a thing a person goes to do, with the role floor
and any capability it needs, and the views it owns. Routes ask the table what
they require via `require_feature`; `/auth/me` sends the list this account
resolves to; the interface hides `data-view-gate` and `data-feature` elements
that are not in it.

One source, two readers. The screen cannot drift from the rule it displays
because it does not hold a copy of it — a test asserts `_features` is only ever
assigned from the server's answer.

Three tests keep the table honest rather than decorative: every view in
`index.html` belongs to exactly one feature, every navigation control is gated
on the view it opens, and the gate names the view the button *actually* opens.
Asking for a feature that does not exist raises rather than granting access —
the worst failure a table like this could have is a silent yes.

This is a different axis from `can_write` below, deliberately kept separate:
"may reach this at all" and "may change things" are different questions, and
conflating them is how one of them stops being asked.

## Write is a grant, not a role

Every account is read-only. Changing anything needs `can_write`, and that is a
per-user grant nobody inherits — admins included, because a capability implied
by a role is not a capability.

Enforced in `middleware/write_guard.py`, not on the routes. There are 163
mutating endpoints; a decorator on each is 163 chances to forget one, and the
forgotten one is the one that matters. A request that changes something is
denied *unless nothing exempted it*.

So the interesting content of that module is the exemption table, and it is
meant to be read rather than scrolled past. Four groups, a sentence of
reasoning each:

| group | why it stays open |
|---|---|
| `SESSION` | login, logout, refresh, first-run setup, and changing your own password — none can depend on a capability the account may not have |
| `NAVIGATION` | switching customer changes what you are looking at, not what is; gating it leaves a read-only account able to read one tenant |
| `LOOKUPS` | a question with a body too big for a query string — DNS, TLS, connection tests |
| `DOCUMENTS` | producing a report to read; archive *deletion* is not here |

Matching is exact, never by prefix: a prefix rule silently covers whatever is
added underneath it later. A test asserts every exemption names a route that
actually exists, and another caps the list at a size somebody will still read —
once it needs scrolling, default-deny has quietly become default-allow.

Two capabilities, layered:

- `can_write` — change Sybr HUB: notes, tags, hosts, settings, users.
- `tenant_write` — change a customer's Microsoft tenant. Requires `can_write`
  underneath it: an account that may not save a note here has no business
  changing configuration there.

**The migration turns it off for everyone**, which means the first grant cannot
be made through the interface — granting is itself a write.
`scripts/grant_write.py` is that key, and it ships in the same change, because
a lock with no key is not a security model but an outage.

The interface does the same thing twice, and the split matters.

`apiFetch` refuses a mutating call the account cannot make and says why. That
half cannot be forgotten, because every request goes through it — which is what
makes it the load-bearing one: most controls are built at runtime out of
`innerHTML`, so there is no list of them to mark and never will be.

`data-write` hides the controls that live in `index.html`, so the interface
does not show a button whose only outcome is a toast. That half *can* be
forgotten, so `tests/test_write_controls_are_marked.py` maps each handler to
the endpoints its function calls and fails on any that writes without the
attribute. Adding a control without marking it fails there rather than in front
of a customer.

The client never keeps its own copy of the exemption list — `/auth/me` sends
the middleware's own set. A second copy would go stale in exactly one
direction: offering something the server refuses.

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

## Deploying policies into a customer tenant

The half that writes, and the only routes in this application that change
anything outside it. `require_tenant_write` existed for months and guarded
nothing until these arrived — a gate standing in a field.

Two requests, deliberately. `/plan` reads the tenant, renders the template
against it and returns what would change, including what it refuses and why,
with each policy's rationale attached: a plan that says "3 policies will be
created" is not one anybody can consent to. `/apply` takes the fingerprint
that plan returned, and refuses if the tenant's policies have moved since —
the operator approved a change to a state that no longer exists, and applying
anyway overwrites whatever moved it.

An adversarial read of this module before it ever ran against a tenant found
four real defects in it. They are fixed, and worth recording because each was
invisible from inside:

- **PATCH replaces a complex property wholesale.** Sending a template's
  `conditions` would have cleared whatever the live policy had beside them —
  the customer's `excludeUsers`, trusted locations, risk levels. On an adopted
  MFA policy that is the directory sync account losing its exclusion, silently,
  under a plan that said "conditions changed". `merge_into` now merges the
  standard into the live body, and the plan carries a before/after per field so
  the reader sees values rather than key names. The cost, stated: a standard
  cannot *remove* something this way, which is the safer direction to be wrong.
- **A re-deploy un-enforced the baseline.** Templates ship report-only so a
  human enables after review; the next deployment diffed `state` and PATCHed it
  back. `would_weaken` makes state raise-only unless explicitly overridden.
- **The lockout rail read `includeUsers` only**, so a policy over every
  administrator *role* — the shape of our own template — passed, because "all"
  is not in an empty set. It now covers roles and groups, and counts
  `authenticationStrength` as a control that can fail.
- **Nothing checked the break-glass group.** Graph accepts an unresolvable GUID
  in `excludeGroups`, so a typo, another customer's id, a deleted group or an
  empty one all satisfied the rail with an exclusion that excludes nobody. The
  plan now resolves it and counts its members.

Four rails, and they refuse rather than warn:

| rail | why |
|---|---|
| **Lockout guard** | a policy targeting All users, excluding nobody, granting a control that can fail is the accident that ends tenants. Recovery is a support case with Microsoft measured in days. There is no override flag, because the flag would be clicked by the same hand |
| **Report-only on arrival** | a new policy lands `enabledForReportingButNotEnforced`, so you learn it would have blocked the finance department before it does |
| **Restore point first** | taken at the moment of the write, not borrowed from the last audit — a restore point from six hours ago describes a tenant that no longer exists |
| **No deletion unless asked** | a policy in the tenant and not in the standard is far more often something the customer added on purpose |

The screen is `app-policy-deploy.js`, reached from Tools. It shows what the
API returns and adds nothing: the refusals with their reason, each policy's
rationale, and the consent state. The confirmation carries the fingerprint the
plan was *read* against rather than one computed at the moment of the click —
recomputing would confirm whatever the tenant looks like then, which is exactly
the state nobody reviewed. The break-glass field starts empty and gates the
button, because an unfilled exclusion excludes nobody.

**Adoption is how an inherited tenant is handled.** The plan matches template
to tenant by display name, which is right for a tenant we set up and wrong for
every tenant we take over: five sensible policies under five names nobody at
Sybr chose, so deploying the standard beside them yields ten policies where
five were meant, and overlapping Conditional Access is harder to reason about
than no deployment at all.

`suggest` scores a live policy against a template one on *what it does* — the
controls granted, who is covered, which client apps are caught — and returns
candidates with their reasons. "All users require MFA" and "Sybr — Require MFA
for all users" share no words a matcher could use and are the same policy;
two policies both called "MFA" can be nothing alike.

It is a shortlist for a person and never an input to a plan. Adoption is an
explicit mapping, confirmed once per customer and stored, and adopting renames:
the policy takes the standard's name so every later comparison is the ordinary
one, and the rename appears in the plan's changed fields because it is a real
change. A mapping whose target has since been deleted raises rather than
falling back to a create — that fallback would produce the duplicate adoption
exists to prevent, at the moment somebody believed they had prevented it.

**Restore is the same two requests pointed at a stored state.** Two kinds of
source: restore points, written immediately before a deployment and holding
exactly what it replaced, and audit snapshots, which are older and answer "what
did this tenant look like last Tuesday" rather than "undo what I just did".

It shares every rail rather than getting gentler ones, including the lockout
guard — a deliberate trade. A stored policy that targets everyone with no
exclusion was presumably working when captured, so refusing it is inconvenient;
but "it worked before" is not a guarantee it works now, and a restore path that
waives the guard is a deployment path that waives it, one POST away. Policies
added since the source was captured are left alone unless asked for: a restore
that removed them would roll back other people's work as well as the
deployment.

Templates live in `app/policy_templates/*.json`, the same shape as baselines
and for the same reason. Placeholders are required, never defaulted: every
policy excludes a break-glass group whose id differs per tenant, and an
unfilled placeholder is an exclusion that excludes nobody inside a policy that
applies to everybody. Rendering refuses while one is unset.

### Asking for the permission

Sybr HUB holds twenty-two Graph permissions and every one ends in `.Read.All`.
It deliberately does **not** hold `AppRoleAssignment.ReadWrite.All`, so it
cannot widen its own access — the property that keeps a compromised toolkit
from becoming a way into every customer's tenant. A test asserts the app-only
set never gains one of the four escalation permissions.

That leaves one honest route to a write permission: a Global Admin signs in and
grants it. `modules/m365_audit/consent.py` is that flow, in the product rather
than as a page of portal instructions. Device code, because the operator is
usually not at the machine the toolkit runs on, and because first-run setup
already works that way. The delegated token lives for one grant and is never
stored.

Two things have to happen and the portal does them together, which makes them
easy to conflate: *declaring* puts the permission on the registration, and
*assigning* is the consent that makes it real. A registration declaring what
nobody assigned still reports missing consent — the exact state this exists to
leave behind. Both halves are idempotent, because re-running after an
interruption is the ordinary case.

This needs `Policy.ReadWrite.ConditionalAccess`, which is deliberately **not**
in `REQUIRED_GRAPH_PERMISSIONS` — an MSP that never deploys should not see a
consent gap reported on every audit for a power it does not want. The plan
reads the granted roles and reports `missing_consent` separately from the
capability check, so nobody goes to argue with the wrong party: `tenant_write`
is ours to grant, the Graph consent is the customer's.

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

## The runs are the record; audit_metrics is a cache of them

Each run directory holds the evidence and `_audit_metrics.json`, the figures
parsed from it. The `audit_metrics` table holds one row per run so a trend can
be charted without re-parsing everything. When the two disagree, the run wins.

They had drifted three ways, and the fixes are in `scripts/`:

- **A row per write, not per run.** `save_audit_metrics` runs when an audit
  finishes *and* when a report is generated from it, so most runs appeared two
  or three times — sixty rows for twenty-one runs.
- **Readings frozen at parse time.** A row keeps whatever the parsers said on
  the day, so a fixed parser never reaches it. Two rows here recorded MFA
  coverage of 101.6% and 100.5%, from a bug since fixed. A trend mixing
  readings from before and after a fix describes which day each point was
  parsed on, not the tenant.
- **`audit_date` is the save time**, minutes after the run it belongs to, so a
  row cannot be matched back to its run by time alone.

`rebuild_metrics_trend.py` rebuilds the table from the runs: one row per run,
dated from the run directory, holding what the current parsers read from
evidence that has not changed. Rows for a customer with no surviving runs are
left alone — they are the last trace of something.

This is a repair a derived table can take and a record cannot. Correcting
`_audit_metrics.json` in place is a different act, and
`repair_metrics_timestamps.py` is deliberately narrow for that reason: it
restores one field whose value is recoverable exactly from the run's own name.

Every reader of `audit_metrics` today takes the newest row per customer
(`ORDER BY audit_date DESC LIMIT 1`, or the equivalent first-wins loop in the
security report), so the older rows were charting nothing. That is why this is
tidiness rather than a fix — worth doing because an impossible figure sitting
in a table is a trap for whoever writes the next chart.

## Recommendations outlive the language they were written in

A recommendation is produced once, when the audit runs, and read for months
afterwards. Storing only the finished sentence meant a run collected in
Norwegian showed Norwegian to an English reader forever, and the only way out
was to run the audit again — a strange thing to ask of a report about last
month.

`T` returns `Localised`, a `str` subclass carrying the key and params it was
built from. It *is* the text: templates, f-strings and `json.dumps` treat it as
an ordinary string, which is why this needed no change at any of the
twenty-eight places a recommendation is built. `_label_recommendations` reads
the key and params back off it, so the sentence and its recipe cannot drift
apart — they are the same object.

`save_audit_metrics` persists both, and `/api/dashboard` rebuilds the text in
the requesting language. A run from before this carries no recipe and keeps its
stored words, which beats a blank line —
`scripts/backfill_recommendation_recipes.py` gives those runs the recipe
without re-auditing the tenant, since recommendations are a pure function of
the audit files already on disk. It adds `rec_id` and the four recipe fields
and **nothing else**: the stored sentence stays exactly as written, because an
audit run is a record of what we said on a day, and rephrasing it to whatever
today's code would say is an edit of that record rather than a repair. It is a
dry run until `--apply`.

**Identity is separate from wording.** Remediation state used to be keyed on
the rendered title, so an operator who marked something done in Norwegian found
it open again in English — the same finding under a name the database had never
seen. Each recommendation now carries `rec_id`, built from the title key plus
only those params that name *which* thing it is about:

```python
_REC_IDENTITY_PARAMS = ("domain", "part", "category", "sku", "name")
```

A count is deliberately excluded. "3 users without MFA" and "5 users without
MFA" are one finding at two moments, and an id that moved with the number would
undo every item an operator had marked done. `tests/test_recommendation_identity.py`
holds both halves: the id is identical across languages, and unchanged when the
count moves.

Rows store the id, so `/api/remediation` resolves it back to a sentence from
the latest run. An id shown raw in the panel means the finding no longer
appears — kept rather than hidden, because the note attached to it is worth
more than the tidiness.

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

Four detectors, and each exists because the ones before it were blind to
something:

| detector | what it reads | the gap it closed |
|---|---|---|
| `untranslated_text_nodes` | markup between `>` and `<` | — |
| `norwegian_literals_in_js` | Norwegian literals in scripts | text built in JS, not markup |
| `text_shown_to_a_person` | args to `showToast`/`confirm`/`alert` | strings with no Norwegian letter |
| `literals_assigned_to_the_page` | literals assigned to `textContent` | a button label set in JS is in no markup and no call |
| `literals_in_a_table_of_labels` | bare strings in a `*Labels` object | a value in an object literal is near nothing |

The first three are user-facing *by construction* — you do not assign to
`textContent` or call `showToast` for any other reason — which is what keeps
them free of judgement calls. The label-table one leans on naming instead,
which is weaker, so the exemption list beside it (`_TECHNICAL_VOCABULARY`) is
by value rather than by pattern: "Access Point" and "Botnet" are how the
vendors' own consoles spell them, and translating them would make the
interface harder to match against, not easier.

A broad "any word-like literal not passed to `t()`" detector was tried first
and abandoned: 913 hits across the scripts, overwhelmingly SVG path data and
CSS values. A budget on that number could only ever be noise, and a budget
nobody reads is worse than no budget.

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
