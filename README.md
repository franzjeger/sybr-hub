# Sybr HUB

[![CI](https://github.com/franzjeger/sybr-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/franzjeger/sybr-hub/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A read-mostly aggregator for MSP technicians.

Sybr HUB pulls everything an MSP technician needs to know about a
customer — Microsoft 365 audit results, Autotask classification,
active contract, IT Glue documentation — into one per-customer view,
and lets the operator turn findings into Autotask tickets or
myITprocess recommendations with one click.

## Why

Most MSP tools either do one job well (an auditor, a ticketing
system, an RMM) or try to do everything and end up doing nothing
well. Sybr HUB takes a deliberate middle path: it's the
**aggregator** between best-of-breed tools, not a replacement for
them.

Read from everything. Write to a deliberate few.

## What it does

| Domain | Read | Write |
|---|---|---|
| **Microsoft 365** | Security audit (28 sections, 24 M365 + 4 Azure; CIS, NIST CSF and ISO 27001 mapped) | Conditional Access and Intune/Entra baselines, only for accounts granted `tenant_write`, one operator click at a time |
| **FortiGate** | Policy and admin audit over the REST API | Config backups to IT Glue |
| **UniFi** | Device and firmware audit (controller API or direct SSH) | — |
| **DNS / email security** | SPF, DKIM, DMARC, MTA-STS | — |
| **Autotask PSA** | Account, classification, contract | Create a ticket from a finding *(operator click only)* |
| **myITprocess** | Accounts (for linking) | Add a finding to planning *(operator click only)* |
| **IT Glue** | Documentation pointers | Audit reports and firewall config backups |
| **VPN** (OpenVPN 3, WireGuard, FortiGate IPsec, Azure) | Tunnel state | Reaches customer-internal management interfaces for the network audit |

**The write side is small and operator-initiated.** No scheduled job ever
creates a ticket, a plan item or a tenant change. The technician reads the
findings, decides what is a ticket and what is planned work, and clicks.

### Optional modules

An administrator switches these on or off under Settings → Moduler. A module
that is off is gone: its routes answer 404 and its scheduled jobs do not run.
A new install starts with all of them off.

| Module | What it adds |
|---|---|
| Remote access | Saved hosts, SSH terminal, RDP and an isolated remote browser (Apache Guacamole) |
| Tailscale | Tailnet devices and keys |
| Pentest | Reconnaissance and service tests against exposed services |
| Provisioning | Wizard that sets up a new customer network on FortiGate and UniFi |
| Licences and hosting | ALSO licences, renewals and costs; Uniweb hosting |
| Sybrt AI | An assistant with tool access; messages are processed by Anthropic after the operator agrees |

## What it does not do

- Replace your RMM, ticketing system or documentation tool. RMM WebRemote stays
  a deep link into the RMM; there is no RMM integration.
- Create tickets, remediate or change anything on its own.
- Host the application for you.

## Quick start

```bash
git clone https://github.com/franzjeger/sybr-hub
cd sybr-hub
python3.14 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock
# Create once; keep a separate recovery copy outside your data/backups.
install -d -m 700 .local-secrets
python -c 'import os,secrets; p=".local-secrets/key-wrap.secret"; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,secrets.token_bytes(48)); os.close(fd)'
export SYBR_KEY_WRAP_SECRET_FILE="$PWD/.local-secrets/key-wrap.secret"
python main.py
```

The repository is private; configure GitHub authentication before cloning.
Do not put a GitHub token in the clone URL.

Open <http://localhost:8099/>. The default bind is loopback, and plain-HTTP
authentication is **refused** from any other machine — the app answers 403
rather than accepting a password in cleartext. For access from elsewhere,
serve TLS (`SYBR_HUB_SSL_CERT` / `SYBR_HUB_SSL_KEY`) or put a terminator in
front of a loopback bind; the Tailscale setup in the installer does the
latter. `SYBR_ALLOW_INSECURE_AUTH=1` overrides this for a terminator the
process cannot detect.

For production deployment behind systemd: see
[`scripts/sybr-hub.service`](scripts/sybr-hub.service) — edit the
`User`/`Group`/`WorkingDirectory` placeholders to match your install. Before
starting it manually, create `/etc/sybr-hub-secrets/key-wrap.secret` as a
root-owned `0600` file containing at least 32 random bytes. The CachyOS
installer creates this credential automatically; keep an offline backup of it
alongside an exported master key.

For release preparation, cutover and rollback, use [the deployment runbook](docs/DEPLOYMENT.md).
The in-app live updater is disabled.

## Documentation

- [`ROADMAP.md`](ROADMAP.md) — what's built, what's next
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module layout
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) — wiring each upstream system
- [`docs/UPGRADING.md`](docs/UPGRADING.md) — behaviour changes that need a decision
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure

## Status

The current release is **v1.2.0**; what has landed since is under «Ikke utgitt» in
[`CHANGELOG.md`](CHANGELOG.md). Versioning is semver from `v1.0.0`. The audit
layer and report generator are carried forward from the earlier MSP-Toolkit
engine, whose history lives in [`docs/HISTORY.md`](docs/HISTORY.md).

The Autotask and myITprocess write sides are wired: a finding becomes a ticket
or a plan item on an operator's click, idempotently, and nothing scheduled can
reach either. **Neither has spoken to a live instance yet**: both were written
against the published API contract, so run the integration's connection test
first and expect to adjust a field name.

## License

MIT — see [`LICENSE`](LICENSE).

Built by [SYBR](https://github.com/franzjeger), a Norwegian MSP solving its own
daily-workflow problem.
