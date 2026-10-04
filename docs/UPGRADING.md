# Report outputs in the report's language (unreleased)

- **`POST /api/report/csv` takes an optional `lang`** (`"no"` or `"en"`,
  default `"no"`), as `/api/report/generate` does. A value the audit did not
  measure is now an empty cell with "ikke målt" / "not measured" beside it,
  not `0`, and the recommendation rows give the priority as a word (Kritisk,
  Høy, Middels, Lav) rather than `critical`/`high`. A script that reads the
  export by column header or priority code needs updating.
- **The report e-mail's subject is "Auditrapport: kunde (kjøring)"** for a
  manual send too (it was "Auditrapport — …"), and "Audit report: …" when the
  attached report is in English. A mail rule that matches the old subject
  needs updating.
- **Norwegian reports title the CIS controls in Norwegian.** The CIS id is
  unchanged.

---

# UniFi firmware table refreshed (unreleased)

- **UniFi firmware verdicts change on the next read.** The table is
  refreshed from Ubiquiti's own firmware feed and release notes (2026-10-04)
  and now knows the model codes a controller reports (U7PG2, US24P250,
  UDMPRO), which used to read "model unknown". Expect devices to move from
  unknown to current, and gateways still on UniFi OS 4.x, switches before
  7.5.15 and access points behind their line's newest release to show as
  outdated. The daily `firmware_check` (05:30) or a network audit updates
  the stored list.
- `GET /api/dashboard/alerts` adds `coverage.firmware.stale_tables`: the
  firmware tables (`unifi`, `fortigate`) past their 180-day window, with the
  day each was last updated, for the vendors the caller has devices from.
  Varsler shows it under "Hva er sjekket".

---

# Offline page and service worker (unreleased)

- **The service worker now controls the interface.** It was registered at
  `/static/` and controlled no page; it now registers with scope `/`, and
  `/static/sw.js` answers with `Service-Worker-Allowed: /`. A reverse proxy
  must pass that response through from the app unchanged (the app also writes
  the cache version into it). Browsers drop the old `/static/` registration on
  their next visit.
- **When a page load gets no answer at all, the browser shows the offline
  page** instead of its own error page, and returns to the app when the hub
  answers. An error page from a reverse proxy (502 while the hub restarts) is
  an answer and is shown as before. Nothing from `/api/` is ever cached, and
  page loads always go to the server.

---

# Every call names its customer (unreleased)

- **The server keeps no "active customer".** Each browser tab works on its
  own customer, so two tabs on two customers no longer save notes, list runs
  or build reports for each other. `POST /api/customers/switch` is gone, and
  `/api/customers`, `/api/dashboard/overview` and `/api/search/customers` no
  longer return `active_id` / `is_active`. A script must name the customer:
  - in the path: `/api/customer/{id}/notes`, `/api/customer/{id}/tags`
    (body `{tags}`), `/api/customer/{id}/files` (was `/api/files`),
    `/api/customer/{id}/status` (was `/api/status`),
    `/api/remediation/{id}` and `/api/remediation/{id}/summary`,
    `/api/fortigate/save/{id}`, `/api/unifi/save/{id}`,
    `/api/network-devices/{id}`, `/api/network/quick-audit/{id}`,
    `/api/network/config-backups/{id}`, `/api/network/save-config-backup/{id}`;
  - as `?customer_id=`: `/api/audit/stream`, `/api/audit/scope`,
    `/api/audit/sections`, `/api/audit/validate-permissions`,
    `/api/dashboard`, `/api/itglue/available-reports`;
  - as `customer_id` in the body: `/api/history/load`, `/api/report/generate`,
    `/api/report/csv`, `/api/email/send-report`, `/api/customer/wipe`,
    `/api/customer/renew`, `/api/itglue/upload/{audit,reports,credentials}`.
    `/api/fortigate/bootstrap` and `/api/provisioning/start` take it
    optionally; without it nothing is stored for, or bound to, a customer.
  - `GET /api/audit/progress` answers for the caller's running audit,
    whichever customer it is for, and says which (`customer_id`).
- **Removed, nothing in the app called them:** `/api/dashboard/security-report`,
  `/api/dashboard/vpn-status`, `/api/customer/{id}/unified` and
  `/api/latest-report`.
- **Trend rows of earlier audits may name the wrong customer.** Their
  customer id came from the setup staging file. `python
  scripts/rebuild_metrics_trend.py --apply` rebuilds them from the runs.
- **Tailscale nodes per customer.** Migration 28 adds the table
  `tailscale_node_customers`. A node tagged `tag:customer-<slug>` in the
  tailnet (the customer id lowercased, other characters as `-`) shows on
  that customer's Tilgang tab; a technician can also assign a node by hand
  there, which wins over the tag.

---

# Varsler from stored state (unreleased)

- **Database migrations 26 and 27** add `tls_endpoints` and
  `device_firmware`. Both start empty and fill as TLS checks and firmware
  reads run; Varsler lists certificates and firmware from them whether or not
  an alert channel is set up.
- **The daily `cert_expiry_check` now connects to customer endpoints.** Besides
  the hub's own Tailscale certificate it re-checks every stored TLS endpoint
  and every FortiGate, UniFi controller and network appliance the customer
  settings name (a TLS handshake on the configured port, nothing else).
- **New daily task `firmware_check` (05:30, on by default)** polls every
  FortiGate and every UniFi controller in controller mode that the hub reaches
  directly. Customers reachable only over VPN are recorded as unread until the
  site collector or a network audit reads them. Switch it off under
  Administrasjon › Varsler og planlagte oppgaver if that traffic is unwanted.
- `GET /api/tls/auto-discover` now lists only the caller's customers'
  endpoints, and each carries `customer_id`. `GET /api/alerts/config` adds
  `teams_webhook_set`.

---

# Navigation (unreleased)

- **Settings moved to Administrasjon,** a page in the avatar menu
  (`#/admin/<pane>`), admins only. Integrasjoner is a pane there and no
  longer a page in the top bar, so a technician no longer opens integration
  settings (saving them was already admin-only). A technician's avatar menu
  opens Konto: language, MFA and password.
- **M365-status, Filer, Historikk and the policy views are tabs of the
  customer page.** Bookmarks to the old addresses redirect to the matching
  tab of the customer the browser tab last opened, or to Kunder when there
  is none.
- **The active-customer bar is gone.** Switch customer from Kunder, Oversikt
  or the search (Ctrl+K), which lists recent customers first.
- **The dashboard's Helse, Fornyelser, Kostnader and Domener tabs are gone
  from Oversikt.** Fornyelser, Kostnader and Domener are under Verktøy ›
  Lisenser og hosting when the billing module is on. Report-archive cleanup
  is under Administrasjon › Lagring og backup.

---

# English reports and network finding ids (unreleased)

- **An English report is English throughout.** The CIS details, the
  "cannot be verified" lines, the score's missing-data notes, the standard's
  requirements and the network section were Norwegian in English reports.
  Reports regenerated from older runs read differently in English; the
  Norwegian text is unchanged.
- **Each unreadable network file has its own recommendation id.** Database
  migration 25 moves remediation status, tickets and reserved ticket
  operations recorded under the shared id to the file's own id on start-up,
  using the runs and ticket titles to tell which file it was. A status
  nothing ties to a file stays under the old id and the finding reads as
  open; set it again. Nothing is deleted.

---

# Backup of the Microsoft 365 data (unreleased)

- **Grant two Graph application permissions for the check to work:**
  `BackupRestore-Control.Read.All` (whether Microsoft 365 Backup is enabled)
  and `BackupRestore-Configuration.Read.All` (its protection policies and how
  many mailboxes, OneDrive accounts and sites they protect). Add both under
  the audit app's API permissions (Microsoft Graph, Application) and grant
  admin consent; **Sjekk tillatelser** on the customer card lists them as
  missing until then. New setups request them.
- **Nothing breaks without them.** They are warn-only in the permission check,
  and the new section, **Microsoft 365 Backup** (`34_m365_backup`), reports
  Microsoft 365 Backup as "could not be read" with the reason, never as "no
  backup". Third-party backup apps (Veeam, Keepit, AvePoint, Datto and others)
  are still recognised, from the service principals the audit can already
  read.
- **A new CIS row, CIS v8 11.2 (backup of the Microsoft 365 data),** and a new check in the Essential Eight and NIS2
  baselines (both now version 2026.2). A tenant where neither Microsoft 365
  Backup nor a known backup app reaches mail, OneDrive or SharePoint gets a
  high-priority recommendation. Reports regenerated from older runs show the
  row as "cannot be verified".

---

# Forwarding, DKIM and Advisor ids (unreleased)

- **Run a new audit before trusting the forwarding findings.** Inbox rules and
  mailbox forwarding to a recipient in the directory were all reported as
  external. The Exchange helper now looks each such recipient up with
  `Get-Recipient`, which the Exchange Administrator role the audit app
  already holds covers. Runs recorded before the upgrade keep their old
  classification.
- **CIS 5.2.3 changes for many tenants.** DKIM is decided per domain on
  Exchange Online's own signing config (`25_exchange_dkim`, which the report
  never read before) and on who the domain's SPF record says sends its mail,
  not on whether some DKIM-looking record exists in DNS. A domain Exchange
  sends for without signing now fails the control; reports regenerated from
  older runs can change verdict.
- **Advisor recommendation ids no longer depend on the language.** Database
  migration 24 moves remediation status, linked tickets and reserved ticket
  operations to the new ids on start-up. Nothing is deleted.
- **`GET /api/settings` no longer returns storage paths to non-admins,** and
  `PUT /api/auth/users/{id}` refuses to change the system account's role,
  capabilities or active flag. Scripts against the API may notice.

---

# Azure VM backup coverage (unreleased)

- **Earlier reports may have listed backed-up VMs as unprotected.** Until
  this fix, every Azure VM in scope appeared under "VMs without backup", with
  a high-priority recommendation, whether or not a vault protected it. Run a
  new audit for customers with Azure VMs before relying on the backup section,
  and correct any report that went out with that finding.
- The audit now also writes `30_azure_vms.json` and `52_azure_backup.json`.
  Reports from older runs still read the text files.

---

# October 2026 quality and copy (v1.2.0)

- **Saving a settings card only changes what that card sends.** Saving one
  integration card used to reset the audit folder, the certificate folder,
  the SMTP setup and e-mail auto-send. If yours were reset by an earlier
  save, set them again once.
- **Saving the webhook card no longer turns scheduled audits off.** Check
  Settings → Automatisk audit that audits are on if you saved that card
  before. (That tab was labelled E-post.)
- **The Terskler tab is gone.** Its values were never stored or used.
- **Connection tests for IT Glue, Autotask and myITprocess need an admin.**
- **A new version waits for you.** After an upgrade the app offers the new
  version in a toast instead of reloading every open tab, so terminal and RDP
  sessions survive. Accept it when convenient.
- **No inline JavaScript.** The CSP is `script-src-attr 'none'`. A reverse
  proxy that rewrites the CSP header must keep that directive.
- **Request bodies are validated.** A client that sent unknown keys or wrong
  types now gets 422 with `error` and `detail`. The SPA does not; a script
  against the API might.
- **The report's NIST column uses CSF 2.0 ids,** and the 0-100 score is
  labelled Sikkerhetsscore / Security score. Reports generated earlier keep
  the old labels.
- **Provisioning reports each step.** A deploy that failed part-way says
  which steps were applied. The SSH deploy path sends whole `config` blocks
  and has not yet been run against a physical FortiGate.

---

# October 2026 modules (v1.2.0)

- **Optional parts are modules.** remote (SSH, terminal, RDP, remote browser),
  tailscale, pentest, provisioning, billing (ALSO and Uniweb) and ai. A
  switched-off module answers 404 on its routes, hides its views and keeps its
  scheduled jobs from running. Admins switch them under Settings → Moduler.
- **The first start decides the defaults once** from evidence of use: stored
  SSH hosts or keys turn on remote, a Tailscale key turns on tailscale, scan
  history turns on pentest, ALSO or Uniweb credentials turn on billing, a
  Claude key turns on ai, and provisioning stays on for any install that
  already has accounts. Check Settings → Moduler after upgrading and switch on
  anything that was used without leaving such evidence.

---

# October 2026 security boundaries (v1.2.0)

- **Viewers no longer reach the technician areas.** VPN, SSH/RDP/remote
  browser, Tailscale, pentest, TLS discovery and the AI console now enforce
  their feature from `app/core/features.py` on the server. A viewer who used
  them through a direct link gets 403.
- **Changing a device's address clears its stored secret.** Repointing an SSH
  host (hostname, port or username), a FortiGate (host or port), a UniFi
  controller or a VPN profile's endpoint without re-entering the password,
  token or key deletes the stored one. The response says what was cleared;
  enter it again before connecting.
- **Existing SSH keys become MSP-wide.** Keys now belong to a customer.
  Migration 23 leaves every existing key without one, which only admins and
  all-customer accounts may attach to a host. A scoped technician creates
  keys for one of their customers. Deleting a key is admin-only.
- **VPN profiles that reach the hub's files are refused.** OpenVPN profiles
  with `auth-user-pass <file>`, `config`, `status`, `writepid`, `management`
  or key material given as a file path, and WireGuard profiles with
  `PreUp/PostUp/PreDown/PostDown` or malformed fields, are refused on save and
  on connect. Paste keys and certificates as inline blocks.
- **VPN secrets move out of the profile table on first read.** Passwords,
  PSKs, private keys and inline OpenVPN key blocks now live only in the
  encrypted secret store. Existing rows are migrated the first time a profile
  is listed or read. Backups taken before that still hold them in plaintext:
  rotate those credentials if a backup may have left your control.
- **Changing your password signs out your other sessions,** and refresh tokens
  rotate on every use; a reused refresh token signs that session out.
- **The remote browser starts with an empty profile every session** and runs
  in a bubblewrap sandbox when `bwrap` is installed. Without it the status
  says `sandboxed: false`. Install `bubblewrap` on the host.
- **`/rdp/launch` no longer uses Remmina,** and passes the password to
  xfreerdp on stdin.
- **Tailscale changes are admin-only;** reading the tailnet is technician.

---

# September 2026 review remediation (v1.1.9)

- **`SYBR_TRUSTED_PROXY_HOPS` now defaults to 0, and 0 is almost certainly
  right.** It counts trusted proxies *behind* the one terminating at this
  process — none, for the shipped `tailscale serve` deployment. The previous
  default of 1 read one entry too far left in `X-Forwarded-For` and returned
  the caller-supplied value, so a rotating header bought a fresh rate-limit
  bucket per request and the login log recorded whatever the caller wrote.
  Only set this above 0 if you run a chain of reverse proxies.
- **`SYBR_DISABLE_HIBP=1` turns off the breached-password lookup.** Setting a
  password now checks the first five characters of its SHA-1 against
  api.pwnedpasswords.com (k-anonymity; the password never leaves the host).
  This is the only outbound call the toolkit makes without an integration
  being configured — disable it on an air-gapped install or where egress has
  to be declarable. The local rules and blocklist still apply.
- **The common-password blocklist now contains passwords that can be
  reached.** Every previous entry was 8–9 characters and already rejected by
  the length rule, so the list decided nothing. A test now fails if an entry
  is unreachable.
- **`/api/docs/list` and `/api/changelog` answer 503 when the files are
  absent** instead of returning an empty tree and an empty string. `docs/` and
  `CHANGELOG.md` live at the repository root and are not package data, so a
  wheel or container install has never carried them — the tabs looked empty
  rather than unavailable. Packaging them is still open; the honest signal is
  the fix that shipped.
- Building from source now requires `setuptools>=77`. `license = "MIT"` is
  PEP 639's SPDX string form and older setuptools rejects it outright. Build
  isolation hid this by always fetching the newest setuptools.
- The AI console defaults to `claude-opus-5` with a 16000-token ceiling.
  Adaptive thinking is on by default on that model and its tokens count
  against `max_tokens`, so the previous 4096 would have truncated ordinary
  answers. A model configured in Settings still wins.

---

# September 2026 security remediation (v1.1.9)

- New user creation defaults to scoped/no customers. Customer access updates use
  `{access_mode: "all" | "scoped", customer_ids: [...]}` atomically. Empty scoped
  access means no customers. Administrators retain their explicit global role.
- Migration 19 no longer grants everyone all customers. If an older build already
  ran that migration, review every account: previous administrative intent cannot
  safely be reconstructed automatically. Review effective access in the user UI.
- Audit/setup starts use POST. GET only reconnects to an existing run; setup also
  requires the tenant-write capability. Bulk audit uses POST and requires admin.
- Logout invalidates refresh sessions. Live WebSockets close on permission/session
  revocation, expiry and user deactivation. Browser origins are validated.
- New key backups require an independent wrapping secret; machine-bound v2 backups
  remain readable for migration with that secret configured. Never discard old
  key backups until an isolated restore succeeds.
- Backup format 3 encrypts every payload. Signed format 2 remains restorable, but
  its DB payload is plaintext. See RETENTION for old-copy handling.
- MFA, protected action approvals and bounded AI conversations are available.
  Legacy AI CLI execution and in-place app updates are disabled.
- Customer removal now explicitly retires its registration. Historical data has
  a separate offline purge and retention workflow.
- Security report grades are unknown when required evidence is stale or absent.
  Firmware is unknown without maintained vendor policy; a version number is not
  evidence that a device has the necessary security patches.

See [DEPLOYMENT](DEPLOYMENT.md), [RETENTION](RETENTION.md) and
[INTEGRATION_ACCEPTANCE](INTEGRATION_ACCEPTANCE.md) before rollout.

---

# Upgrading

Behaviour changes that need a decision or a config edit, newest first. Changes
not listed here are backwards-compatible.

---

## Unreleased — Defender incidents permission (re-consent needed)

`REQUIRED_GRAPH_PERMISSIONS` gained **`SecurityIncident.Read.All`**. The Defender
for Office section calls `security/incidents` and has always documented that it
needs this permission, but the grant was never in the declared set — so setup
never requested it, no tenant ever consented to it, and the incidents read
returned a 403 on every audit while the section quietly degraded.

**Existing app registrations need a one-time re-consent.** Press **Check
Permissions** on the customer card; it names what is missing, then re-run the
consent grant (or `setup`). The permission is *warn-only*: until it is consented
the audit still completes and every other section is unaffected — only the
Defender incidents block reports a refusal instead of data.

Nothing to consent means nothing changes. A section going from a silent empty
result to an actual incidents list is the point of the fix.

A new test (`tests/test_graph_permissions.py`) now enforces the rule this gap
broke: when a section documents that it *requires* a permission, that permission
must be in the declared set — so a called-but-undeclared permission fails CI
instead of surfacing as a live 403 months later.

---

## Unreleased — in-app self-update (Settings → Update now)

An admin can now update the deployment from inside the app: **Settings →
Advanced → Update now** pulls the running branch to its `origin` counterpart and
re-execs the process onto the new code. It exists because the host often sits
behind a tailnet a browser can reach but a build environment cannot, so "ssh in
and `git pull`" is not always available.

**This needs one systemd change to work, and it is a deliberate relaxation.**
The shipped unit now lists `/opt/sybr-hub` in `ReadWritePaths`, so the service
can rewrite its own checkout — otherwise `ProtectSystem=strict` keeps the code
read-only and the button fails with a permission error. `scripts/install-cachyos.sh`
applies this automatically; a manual install must add it to the unit and
`systemctl daemon-reload`. **If you would rather keep the code directory
read-only, drop `/opt/sybr-hub` from `ReadWritePaths`** and update by hand — the
endpoint then reports the failure instead of updating.

What the change does *not* touch: `NoNewPrivileges=yes` stays on. The update
re-execs in place (`os.execv`) rather than calling `systemctl restart`, so the
web process never gains privilege. The endpoint is admin-only and `can_write`
gated, is unreachable from scheduled code, only ever fast-forwards the current
branch to `origin` (no ref comes from the request), and refuses a dirty tree or
a detached HEAD. Migrations run at startup, so they apply on the restart.

**Safety, in order.** Because the host is hard to reach by hand, the update is
built so a failure at any step leaves the running version intact:

- It **refuses local commits** that are ahead of `origin` (a hotfix made on the
  box) rather than discarding them — push or remove them first.
- It installs the **target's** dependencies *before* moving `HEAD`, so a `pip`
  failure leaves both the tree and the running process untouched.
- It advances with `git merge --ff-only` — a true fast-forward, never a rewind.
- It **import-smokes the new code** in a subprocess and, if it cannot even
  import (a syntax/import error — the common bad deploy), **rolls `HEAD` back**
  and refuses *before* the re-exec.

The one failure it cannot catch is a *runtime* one that only shows on boot — a
broken startup migration, a master key it can no longer unwrap. For that the
unit now carries a crash-loop backstop (`StartLimitIntervalSec=180`,
`StartLimitBurst=5`): after five failed starts in three minutes systemd parks
the service in a visible `failed` state instead of restarting forever. Recover
by hand on the host:

```sh
cd /opt/sybr-hub
sudo -u sybrhub git reset --hard <last-good-commit>   # git reflog shows it
sudo systemctl reset-failed sybr-hub
sudo systemctl start sybr-hub
```

---

## Unreleased — active customer is now per user

Authenticated users no longer share the process-wide `active.txt` selection.
After upgrade, each user must select a customer once; the server intentionally
does not copy the legacy selection into every account. Choices are stored
separately and are filtered through the user's current customer grants on every
request. Revoking access therefore also invalidates an already selected
customer.

The TUI, CLI and scheduler's single-customer mode retain the legacy global
selection because they have no authenticated web user. Background all-customer
audits continue to receive customer records explicitly and never switch it.

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
  numerator. One tenant read 102%. It reads 99.5% on the same evidence.
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

forget_host("10.0.0.1")  # add port= if not 22
```

Do not clear the pin to make an error go away without knowing why the key
changed — that is the case the check exists for.

### 3. New accounts start scoped to no customers

Schema migration 14 adds `users.all_customers`.

**Existing accounts without explicit customer rows keep their broad grant;
accounts with explicit rows remain scoped.** Accounts created **after** the upgrade start with no customers and
see nothing until an admin assigns them.

Previously, a user with no `customer_access` rows could see *every* customer —
the failure mode of forgetting to assign someone was full access rather than
none.

**Onboarding a technician now takes one extra step:**

```python
from app.core.rbac import set_user_customers, set_all_customers

await set_user_customers(user_id, ["acme", "globex"])  # scope to specific customers
await set_all_customers(user_id, True)  # or grant all, explicitly
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
