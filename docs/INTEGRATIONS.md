# Integrations

How to wire each upstream system, what credentials it needs, and where those
credentials are stored.

Two storage locations are used throughout:

- **OS keyring** — anything secret (API tokens, passwords, client secrets).
  Never written to disk in plaintext by the application.
- **Encrypted customer config** — non-secret settings (hostnames, ports, site
  names), in `MSP_DATA_DIR/customers/<id>/config.json`, AES-256-GCM at rest.

Read-only integrations are safe to point at production on day one. The
write-side is deliberately small and always operator-initiated — no scheduled
job creates a ticket.

---

## Microsoft 365 / Azure

The largest integration: 26 audit sections mapped to CIS, NIST CSF 2.0 and
ISO 27001:2022.

**Auth modes.** Per-customer app registration (`AuthMode: legacy`), or partner
delegation through GDAP (`AuthMode: gdap`).

**Config keys** (encrypted customer config):

| Key | Meaning |
|---|---|
| `TenantId` | Entra tenant GUID |
| `ClientId` | App registration client id |
| `AppObjectId` | App object id, used when renewing secrets |
| `PrimaryDomain` / `InitialDomain` | Tenant domains |
| `SubscriptionId` | Azure subscription, for the Azure sections |
| `AuthMode` | `legacy` or `gdap` |
| `SecretExpiry` / `CertExpiry` | Tracked so the UI can warn before expiry |

**Secrets** (keyring): `client_secret`, `cert_password`. For GDAP:
`partner_client_id`, `partner_client_secret` under the `gdap` tenant key.

**Permissions.** `app/core/config.py::REQUIRED_GRAPH_PERMISSIONS` is the single
source. `GraphClient.REQUIRED_PERMISSIONS` imports it, and `setup_helper.ps1`
is handed it on stdin — the array still in that script is a fallback for an
older caller, and a test asserts it has not drifted. Add a permission in one
place only; adding it in two of the three grants a consent nothing validates,
or demands one the wizard never asks for.

First-run setup requests the delegated scopes in `SETUP_SCOPES` to create the
registration, then the audit runs application-only.

`validate_permissions()` compares what is granted against that list and names
the difference. It is what the "Check Permissions" button calls, and it is the
first thing to run when a section reports a permission problem — it answers in
seconds what reading an error body guesses at.

A permission nobody calls for is privilege the tool need not hold. A test maps
each declared permission to the resource it governs and fails on any that
nothing requests; `PrivilegedAssignmentSchedule.Read.AzureADGroup` sat in all
three lists for a long time while PIM-for-groups was never queried, so every
install asked its customers to consent to a read it never performed.

**Endpoints that are not where you would expect.** Each of these was measured
against a live tenant, and each had been guessed wrong at least once. Verify
before changing them:

| what | endpoint | note |
|---|---|---|
| Directory settings | `v1.0/groupSettings` | `settings` is the beta alias; on v1.0 it is not a segment and answers 400 |
| Sensitivity labels | `beta/security/dataSecurityAndGovernance/sensitivityLabels` | the `informationProtection` path is gone; needs `SensitivityLabels.Read.All` — plural, the singular role exists too and is a different thing |
| Usage reports | `v1.0/reports/get*(period='D90')` | CSV only. `$format=application/json` is refused with "JSON format is not supported" |
| Entra devices | `v1.0/devices` | what the tenant *has*, as against `deviceManagement/managedDevices` for what Intune manages |
| OneDrive discovery (app-only) | `v1.0/users/{id}/drives` | the singular `/drive` endpoint does not support application permissions |

**OneDrive / SharePoint sharing coverage is bounded and explicit.** The audit
discovers every site collection's drives plus every directory user's drives,
then walks folders with `$expand=permissions`. Defaults are depth 3, 40 opened
folders per drive and 1500 actual outbound Graph attempts, including pagination
and throttling retries. The section records discovery failures, unreadable
drives/folders and limit hits. CIS 7.2.4 only passes on a clean zero when all of
those coverage fields say the scan completed; a found anonymous link still
fails even when the rest of the scan was partial.

**Usage reports carry two traps.** They answer CSV behind a 302 to storage, so
the request must follow redirects, and the column headings are prose that
`_report_key` folds to the camelCase the JSON form uses. Separately, the admin
centre can conceal user names in these reports; the counts stay accurate but
the principal names come back as opaque identifiers. The collector detects
that from the rows and says so, so nobody reads the hashes as corrupt output.

**Intune answers 401 on a tenant with no subscription**, with a body that is a
`Forbidden` from `manage.microsoft.com` rather than anything from Graph's auth
layer. That is not a consent problem and `validate_permissions()` will show
the DeviceManagement roles granted. Check the licences.

**PowerShell 7 is required** for the Exchange Online section and for first-run
app registration — those go through `exo_collector.ps1` and `setup_helper.ps1`
rather than Graph. Without `pwsh` on `PATH` (or `PWSH_PATH` set), the Exchange
section reports as skipped and the rest of the audit proceeds.

Azure sections additionally need the `Reader` and `Cost Management Reader`
roles on the subscription.

---

## FortiGate

**Read:** policy and admin audit, dashboard stats, CIS compliance checks,
threat summary. **Write:** config backups, pushed to IT Glue.

**Config keys:** `FortiGateHost`, `FortiGatePort` (default 443),
`FortiGateVDOM` (default `root`), `FortiGateVerifySSL`, `FortiGateApiUser`,
`FortiGateAdminUser`, `FortiGateBootstrappedAt`.

**Secrets:** `fortigate_api_token`, `fortigate_admin_password`,
`fortigate_admin_user`.

> **`FortiGateVerifySSL` defaults to true.** A device presenting a self-signed
> certificate — the factory default — will fail to connect until you either
> install a trusted certificate or set `FortiGateVerifySSL: false` for that
> customer explicitly. This is per-device and deliberate: the previous default
> silently accepted any certificate on every device.

**Getting a token.** Either create a REST API admin in the FortiGate GUI and
paste the token, or use `POST /api/fortigate/generate-token/{customer_id}`,
which creates the API user over SSH. A factory-default unit can be brought up
end to end with `POST /api/fortigate/bootstrap`: it sets the admin password,
applies basic hardening, moves the GUI to port 8443, creates the API user and
returns the credentials — which are then stored in the keyring.

**SSH host keys** are pinned on first contact in `MSP_DATA_DIR/known_hosts`
and verified afterwards. A changed key is refused. After a legitimate device
replacement or firmware reflash, clear the pin:

```python
from app.services.ssh_connection import forget_host
forget_host("10.0.0.1")            # add port= if not 22
```

---

## UniFi

Two modes, set by `UniFiMode`:

- `controller` — a UniFi Network controller or UniFi OS console.
- `direct` — standalone devices reached over SSH, listed in
  `UniFiDirectDevices`.

**Config keys:** `UniFiHost`, `UniFiIsUniFiOS`, `UniFiSite` (default
`default`), `UniFiMode`, `UniFiDirectDevices`.

**Secrets:** `unifi_username`, `unifi_password`. Cloud Site Manager uses
`ui_cloud_token`, or a global API key in app settings under
`unifi_site_manager_api_key`.

Direct-device SSH uses the same host-key pinning as FortiGate. Certificate
verification follows the same secure-by-default rule; UniFi devices ship with
self-signed certificates, so expect to opt out per device.

Subnet discovery (`POST /api/network/scan`) is capped at a /22 (1024
addresses) per scan.

---

## VPN

Not an integration so much as the connectivity layer the others depend on:
customer FortiGate and UniFi management interfaces live on internal LANs.

Four backends: WireGuard, OpenVPN, FortiGate IPsec (strongSwan) and Azure VPN.
Profiles are stored in the `vpn_profiles` table; profile secrets (private keys,
PSKs, passwords) are split out and stored encrypted under
`MSP_DATA_DIR/vpn_secrets/<profile_id>/`.

Several backends need privileged commands to create interfaces or change
routes. The production unit intentionally uses `NoNewPrivileges=yes`, so
`sudo` cannot elevate even with a `NOPASSWD` rule. Establish those tunnels
outside the web service, or put the privileged operations behind a separately
authenticated and narrowly scoped helper. Do not grant this web process broad
`sudo ip`, `sudo tee`, or root access; a web compromise would inherit it.

> **Uploaded OpenVPN profiles are refused if they contain a directive that can
> execute a program** (`up`, `down`, `plugin`, `script-security`, and the rest
> of that family). An `.ovpn` file is operator-supplied data, not code, and
> OpenVPN will happily run a shell command from one. `--script-security 0` is
> also pinned on the command line. If you have a profile that legitimately
> needs a hook, it will need an explicit allowlist mechanism — deliberately
> not provided.

---

## IT Glue

**Read:** documentation pointers. **Write:** audit reports and FortiGate config
backups, as flexible assets with attachments.

`ITGlueClient(api_key=..., region=...)` — region selects the API base URL and
defaults to `eu`. Set the key in Settings.

`upload_credentials()` writes tenant credentials — including the client secret
and, optionally, the `.pfx` certificate — into an IT Glue flexible asset. That
is intentional: IT Glue is a credential vault and this is how the toolkit
documents what it created. Be aware it is doing so.

---

## Autotask PSA

**Read:** account, classification, active contract. **Write:** create ticket,
on an explicit operator click only.

`AutotaskClient(api_integration_code=..., username=..., secret=..., zone_url=...)`.
The zone URL is per-tenant; Autotask's zone information endpoint returns it for
a given username.

---

## myITprocess

**Write only:** push a recommendation, on an explicit operator click.

`MyITProcessClient(api_key=..., base_url=...)`, default base URL
`https://api.myitprocess.com`.

---

## RMM (Datto / Ninja / Atera / …)

**Read:** device status. **Write:** deep links into the vendor's own WebRemote.

`app/integrations/rmm.py` is a provider interface, not a finished client. Sybr
HUB deliberately does not implement remote control — it links out to the RMM
that already does.

---

## DNS / email security

No credentials. `app/services/dns_checker.py` queries live DNS for SPF, DKIM,
DMARC and MTA-STS.

Results are three-state — pass / warn / fail — plus an explicit
**unverifiable** when a lookup could not be answered. That distinction is
deliberate: a timeout must never be rendered as "no record present", because
"you have no SPF record" and "we could not check your SPF record" call for
very different responses from a technician.

---

## Status

Per the README, the audit layer and report generator are battle-tested; the
write-side clients (Autotask, myITprocess, RMM) are scaffolded but not yet
wired to routes. Treat the interfaces above as the intended shape rather than
as something you can point at production today.
