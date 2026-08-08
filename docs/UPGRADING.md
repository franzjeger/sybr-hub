# Upgrading

Behaviour changes that need a decision or a config edit, newest first. Changes
not listed here are backwards-compatible.

---

## Unreleased — production credential and VPN privilege boundary

The shipped systemd unit now requires
`/etc/sybr-hub-secrets/key-wrap.secret`, owned by root with mode `0600`.
`scripts/install-cachyos.sh` creates it once and never rotates an existing
value. Manual installations must create at least 32 random bytes there before
starting the service. Back it up offline together with an exported master key;
losing both makes encrypted customer data unrecoverable after a host rebuild.

The unit still enforces `NoNewPrivileges=yes`. Earlier documentation suggested
a `NOPASSWD` sudoers stanza for VPN commands, but systemd prevents that
elevation by design. Production deployments must establish privileged tunnels
outside the web process or use a separate, authenticated helper. Do not remove
`NoNewPrivileges` merely to make the old stanza work.

The application CSP now rejects inline script and style elements. Legacy
event/style attributes remain temporarily isolated behind CSP3 attribute-only
directives. The authenticated Swagger viewer is the sole path-specific external
script exception; its CDN bundle is pinned to an exact release and its inline
bootstrap requires a fresh response nonce.

---

## Unreleased — three new Graph permissions, and figures that used to be wrong

### Grant three permissions, drop two

`REQUIRED_GRAPH_PERMISSIONS` changed, and existing app registrations will not
have the additions until someone consents to them.

**Added.** `Device.Read.All` for the Entra device register, `Reports.Read.All`
for the usage reports, `SensitivityLabels.Read.All` for the labels endpoint
that replaced the one Microsoft withdrew.

**Removed.** `InformationProtectionPolicy.Read.All`, which governed that
withdrawn endpoint, and `PrivilegedAssignmentSchedule.Read.AzureADGroup`,
which nothing has ever called for.

Press **Check Permissions** on the customer card. It names what is missing.
Until the new ones are consented to, the sections that need them report a
refusal rather than an empty result — which is the point, but it does mean a
section going from silent to failed is progress, not a regression.

### Figures that changed without the tenant changing

Re-run an audit before comparing anything to a stored figure. Several numbers
were wrong in ways that make old reports and old trend lines untrustworthy:

- **MFA coverage could exceed 100%.** A user whose method lookup failed was
  removed from the denominator and, if a CA policy covered them, left in the
  numerator. Fonnafly read 102%. It reads 99.5% on the same evidence.
- **MFA coverage now names its two halves.** The headline still counts a user
  as covered when a CA policy forces MFA at sign-in, registered method or not.
  The registration percentage is printed beside it, because 99.5% coverage sat
  on the same page as "42 users have no MFA methods" with nothing to
  reconcile them.
- **"Ingen Intune-enheter funnet" was sometimes a refusal.** A tenant with
  devices and no enrolment read the same as a tenant with no devices. The
  Entra register is collected now and the gap is reported; CIS 6.1.1 fails
  where devices exist and none are managed, where it used to record info.
- **Reports that could not be read no longer score.** Purview labels, Intune
  and password protection each produced findings from files that were never
  fetched. Findings from those sections in reports generated before this
  release may be drawn from data that does not exist.

### Behaviour changes

- **`/api/open-private` is gone.** It ran a browser process on the server —
  headless, and a different machine from the operator's. The page opens the
  tab itself now. A web page cannot open a private window; the UI says so
  rather than claiming otherwise.
- **No third-party CDN in the application shell.** xterm, chart.js, marked,
  DOMPurify and the icon font are served from `static/vendor/`. The separate
  authenticated Swagger viewer still needs jsDelivr for its exact pinned
  bundle; installations that block `/docs` at the reverse proxy can remove
  that egress rule.
- **Usage Reports is a new section** and appears in the scope selector. It
  reads a 90-day window and reports licensed accounts with no activity.

---

## Unreleased — authentication, RBAC and transport hardening

Four things change how a running install behaves. The first two can stop the
toolkit reaching devices it reached yesterday, so read them before deploying.

### 1. TLS verification is on by default

`verify_ssl` now defaults to **true** for FortiGate and UniFi.

**Who is affected:** any device presenting a self-signed certificate — which is
the factory default for both — whose customer config does not already contain
an explicit `FortiGateVerifySSL` key.

**Symptom if you skip this:** connection failures with a certificate
verification error, on devices that worked before.

**Fix:** either install a trusted certificate on the device, or opt out for
that customer:

```jsonc
// MSP_DATA_DIR/customers/<id>/config.json  (encrypted; edit via the UI)
"FortiGateVerifySSL": false
```

Customers whose config already stores `false` are unaffected — only the
fallback for a missing key changed.

**Check before deploying:**

```bash
# Which customers have no explicit setting and will start verifying?
python3 - <<'EOF'
from app.core.customer import CustomerManager
for c in CustomerManager.list_customers():
    if c.get("FortiGateHost") and "FortiGateVerifySSL" not in c:
        print("will start verifying:", c.get("CustomerName"), c["FortiGateHost"])
EOF
```

### 2. SSH host keys are pinned

The first SSH connection to a device records its host key in
`MSP_DATA_DIR/known_hosts`. Later connections verify against it and **refuse**
on mismatch.

**Who is affected:** nobody on first deploy — every device is pinned silently
on first contact. It bites later, after a device is replaced, reflashed, or
its host key is regenerated.

**Symptom:** `Vertsnøkkelen for <host> har endret seg siden forrige tilkobling`.

**Fix, once you have confirmed the change is legitimate:**

```python
from app.services.ssh_connection import forget_host
forget_host("10.0.0.1")          # add port= if not 22
```

Do not clear the pin to make an error go away without knowing why the key
changed — that is the case the check exists for.

### 3. New accounts start scoped to no customers

Schema migration 14 adds `users.all_customers`.

**Existing accounts are migrated with the grant set**, so nobody loses access
on upgrade. Accounts created **after** the upgrade start with no customers and
see nothing until an admin assigns them.

Previously, a user with no `customer_access` rows could see *every* customer —
the failure mode of forgetting to assign someone was full access rather than
none.

**Onboarding a technician now takes one extra step:**

```python
from app.core.rbac import set_user_customers, set_all_customers
await set_user_customers(user_id, ["acme", "globex"])   # scope to specific customers
await set_all_customers(user_id, True)                  # or grant all, explicitly
```

Admins bypass the check entirely and need neither.

### 4. Uploaded OpenVPN profiles may be rejected

A profile containing a directive that can execute a program — `up`, `down`,
`route-up`, `plugin`, `script-security`, `client-connect` and similar — is
refused at import and at connect.

**Who is affected:** anyone with an existing `.ovpn` that uses a hook, usually
for custom DNS or routing.

**Symptom:** `Konfigurasjonen inneholder direktivet '<name>'`.

There is deliberately no allowlist. OpenVPN will run a shell command from a
config file, and profiles are operator-supplied data. If you have a profile
that genuinely needs a hook, the routing or DNS it performs is usually better
expressed as a split-tunnel route on the profile itself.

Note that `up-delay` and `up-restart` are *not* hooks and are unaffected.

---

## Unreleased — reports stop scoring data they never collected

No config change, but **numbers in customer-facing reports will move**, and if
you have already sent a report to a customer the new one may disagree with it.
Every change here is in the same direction: the report now declines to state
things it did not measure.

**What changes on a re-render:**

- **The risk radar may show fewer than five axes, or disappear.** Axes are
  drawn only where the underlying section produced data. Previously Azure
  defaulted to 80/100 and Email to 100/100 whether or not those sections ran,
  Devices and Data Protection fell back to 50, and a failed conditional-access
  fetch was averaged into Identity as a zero. The chart hides itself entirely
  below three axes, as it always did.
- **The compliance percentage may rise.** CIS 1.1.1 marked unreadable MFA
  state as a *failure*; it is now `info`, which `compliance_assessed` excludes
  from the denominator. A tenant whose Graph permissions blocked the user list
  was being scored non-compliant rather than un-assessed.
- **"MFA data is not available for this customer" now means what it says.**
  The executive summary previously printed it whenever coverage was 0%,
  including when 0% was a real, measured reading.
- **Reports for un-gradeable audits no longer print "None/100".**
- **Some open-WiFi findings will disappear.** See below.
- **Some "VMs without backup" findings will disappear.** See below.
- **Compliance controls whose collector section did not run now report
  `info`** instead of a grade. Eleven controls used to grade an empty or
  errored source file: CIS 4.3 failed for "no anti-spam policies"; CIS 2.1.2,
  4.4 and 9.2 *passed*, attesting that app credentials were not expired, that
  no external mail forwarding existed, and that there were no Defender alerts
  — from files that were never written. CIS 3.1.1, 3.2.1, 4.2, 4.5, 4.6 and
  7.2.2 warned on the same basis. Rows are still emitted, so nothing looks
  like N/A; they just no longer count for or against the tenant.
- **The "SharePoint external sharing is at its most permissive level"
  recommendation no longer fires from missing data.** `sharing_level` defaults
  to `"warning"`, and the recommendation was the one consumer not checking
  `has_data`.
- **The executive summary no longer opens with "the environment has 0 users
  (0 active, 0 guests)"** when the user list could not be read.
- **CIS 4.4 will change for essentially every tenant.** It read
  `28_exchange_mailbox_forwarding.txt`, which the collector writes on every
  run and titles "MAILBOX FORWARDING" — so its substring test for
  "forwarding" was true whenever the Exchange section ran, and every such
  tenant was told external forwarding had been detected. It also treated
  `29_exchange_inbox_rules_external_fwd.txt` as evidence, when by the
  collector's naming convention that is the *all-clear* file; the finding
  goes to `29_..._WARN.txt`. Both `_WARN` files are now the trigger, matching
  what `_compute_risk` already did. **If you dismissed a 4.4 warning as noise,
  that was correct — but re-check any tenant where you did, because the old
  control could not have caught a real detection either.**
- **CIS 6.1.1** no longer fails with "devices are enrolled but no Intune
  compliance policies are configured" when the policy file is simply absent.
- **CIS 5.2.3** no longer fails with "No DKIM record found" for a domain
  whose DKIM lookup did not run — once per domain, so multi-domain tenants
  saw several.
- **SharePoint sharing capability has a third state.** An absent or
  unrecognised "Sharing Capability" used to fall through to `warning`, which
  every consumer reads as a finding. Because the parser's `has_data` is true
  as soon as the *site list* parses, a tenant whose admin-settings call failed
  got a permissive-sharing recommendation, an amber CIS 7.2.1 and a red panel
  from a field nobody read. It now renders as a neutral "unknown" pill.

### Trend history: past audits may have recorded false zeroes

`save_audit_metrics` wrote `0` for every metric whose section produced no
data, into both `_audit_metrics.json` and the `audit_metrics` table.
`_compute_trends` skips `None` but not `0`, so a single throttled or
permission-denied audit recorded MFA coverage, user count and Secure Score as
zero — and the next report drew that as a collapse and recovery in the
customer's history. A later correct audit adds a row; it cannot retract that
one.

Unknown metrics are now stored as SQL `NULL` (every affected column was
already nullable) and skipped by the trend comparison. A *measured* zero is
still stored as `0` — the distinction is the point.

**Existing rows are not migrated**, because a stored `0` is indistinguishable
from a real one. If a trend chart shows an inexplicable cliff, that is the
likely cause; the offending row can be removed by hand:

```sql
-- inspect first
SELECT audit_date, mfa_coverage_pct, total_users, risk_score
FROM audit_metrics WHERE customer_name = '<name>' ORDER BY audit_date;

DELETE FROM audit_metrics WHERE id = <the bogus row>;
```

### Reports no longer die on an unreadable previous run

`load_previous_metrics` caught `(json.JSONDecodeError, OSError)`, which does
not include `cryptography.exceptions.InvalidTag`. A `_audit_metrics.json`
that could not be decrypted — after a master-key rotation, a recreated
keyring entry, or corruption — propagated out of `build_report_context` and
failed the whole report. It is now logged and skipped: you lose the trend
chart for that run, not the report.

### Open-WiFi findings on UniFi controller sites

The UniFi audit defaulted a WLAN's security field to `"open"` when the
controller did not return one. That produced a critical-priority
recommendation naming the SSID, plus a risk penalty, for networks that may
well be encrypted. A WLAN whose security cannot be read now renders as
`Unknown` (amber) in the WLAN table and raises no finding.

**Audits saved before this change cannot be corrected retroactively** — the
string `"open"` is already in `61_unifi_audit.txt`, indistinguishable from a
genuine reading. If you have acted on an open-WiFi finding for a controller
site and could not reproduce it on the device, that is the likely cause.
**Re-run the network audit** to get a truthful value; new audit files also
carry a `security_label` field alongside the raw value.

`WEP` also no longer shares the green "not open" colour with WPA2/WPA3 in the
WLAN table.

### Azure VM backup coverage

Backup coverage is a cross-reference between the VM list
(`30_azure_vms*.txt`) and Recovery Services Vault protected items
(`52_azure_backup*.txt`). The cross-reference ran even when the vault half was
missing or errored, so every VM came out "not backed up" — a high-priority
recommendation naming each server, plus a red "VMs without backup" panel.

Coverage is now reported only when both halves were read. Where the vault data
is missing, the panel says so instead of showing a 0/0 split, and no
recommendation is raised. **A vault that was read and contains nothing is
unchanged** — that is a real finding.

**If a customer was told their VMs are unprotected and you could not
reproduce it in the portal**, check whether `52_azure_backup*.txt` in that
audit is empty or starts with `Error:`. The usual cause is the app
registration lacking Reader on the vault's resource group.

---

## Unreleased — the CI dependency scan was never running

`pip-audit` was invoked as:

```
pip-audit -r requirements.txt --disable-pip --strict
```

`--disable-pip` is only accepted with a hashed requirements file or with
`--no-deps`, and `requirements.txt` is neither. Every run exited on argument
validation before scanning anything:

```
ERROR: the --disable-pip flag can only be used with a hashed requirements
       files or if the --no-deps flag has been provided
```

The step carries `continue-on-error: true`, so that error was swallowed and
the job reported success. **The security check has been green since it was
added without ever having looked at a dependency.** It now runs as
`pip-audit -r requirements.txt --strict`, which also audits transitive
dependencies.

### What it found — three pins need a decision

Every fix is blocked by an *upper* bound in `requirements.txt`, so none of
these clear with a `pip install -U`:

| Package | Resolves to | Advisories | First fixed | Current pin |
|---|---|---|---|---|
| `cryptography` | 45.0.7 | PYSEC-2026-35, -36, -2141, GHSA-537c-gmf6-5ccf | 48.0.1 clears all four | `>=44.0.0,<46.0` |
| `weasyprint` | 66.0 | PYSEC-2026-2034 | 68.0 | `>=64.0,<67.0` |
| `pytest` | 8.4.2 | PYSEC-2026-1845 | 9.0.3 | `>=8.0.0,<9.0` |

`weasyprint` also carries PYSEC-2026-3412, for which no fixed version is
published yet.

**These are deliberately not bumped here** — they want a run against your
install, not just a green unit suite.

- **`cryptography` → `>=46.0.7,<49.0`** is the one that matters for a
  deployed instance: it signs JWTs via `PyJWT[crypto]` and generates the
  self-signed certificate. Resolves cleanly to 48.0.1.
- **`weasyprint` → `>=68.0,<69.0`** resolves to 68.1. The existing `<67.0`
  cap is commented as deliberate ("dodge the not-yet-released breaking-change
  line"), and PDF output is worth eyeballing after the bump — a rendering
  regression will not show up in the test suite.
- **`pytest` → `>=9.0.3`** is test-only and does not affect a deployed
  instance. It is also entangled: with `pytest-asyncio<1.0` still in place,
  the resolver satisfies pytest 9 by walking `pytest-asyncio` *back* to
  0.23.3 rather than forward. Taking pytest 9 means lifting the
  `pytest-asyncio` cap too, and 1.x changed the fixture loop scoping and
  `asyncio_mode` defaults. Budget for suite churn.

Verified resolvable together with `pip install --dry-run`:
`cryptography-48.0.1 pytest-9.1.1 pytest-asyncio-0.23.3 weasyprint-68.1`.
That is a resolution, not an endorsement — see the pytest-asyncio note above.

---

### Also in this change

No action needed, listed for completeness:

- **`blacklist_token()` is now a coroutine.** Internal API; nothing outside
  the repo calls it.
- **Authentication is now enforced.** It previously was not — the middleware
  existed but was never registered. If you have scripts hitting the API
  directly, they now need a token from `POST /api/auth/login`.
- **First run** is reachable only at `/api/auth/status` and
  `/api/auth/setup` until the first admin exists. Everything else answers 401.
- **`pip install .` works.** The build backend previously named a module that
  does not exist.
- **Requests are roughly 3× faster** (10.3 ms → 3.4 ms authenticated), from
  connection pooling and not re-running `PRAGMA journal_mode` per connection.

### Rolling back

The schema migration is additive — a column with a default — so an older build
will run against an upgraded database. It will ignore `users.all_customers`
and fall back to the previous "no rows means unrestricted" behaviour, which is
more permissive, not less. Nothing else in this change is persisted in a form
an older build cannot read.
