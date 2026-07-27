# Upgrading

Behaviour changes that need a decision or a config edit, newest first. Changes
not listed here are backwards-compatible.

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
