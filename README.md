# Sybr HUB

[![CI](https://github.com/franzjeger/sybr-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/franzjeger/sybr-hub/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A read-mostly aggregator for MSP technicians.

Sybr HUB pulls everything an MSP technician needs to know about a
customer — Microsoft 365 audit results, Autotask classification,
active contract, IT Glue documentation, RMM device status — into one
per-customer view, and lets the operator turn findings into Autotask
tickets or myITprocess recommendations with one click.

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
| **Microsoft 365** | Full security audit (26 sections, CIS / NIST CSF / ISO 27001 mapped) | — |
| **FortiGate** | Policy + admin audit over REST API | Config backups → IT Glue |
| **UniFi** | Device + firmware audit (controller-API or direct-SSH) | — |
| **DNS / email security** | SPF / DKIM / DMARC / MTA-STS | — |
| **Autotask PSA** | Account, Classification, Contract | Create Ticket *(manual click only)* |
| **IT Glue** | Documentation pointers | Audit reports + firewall config backups |
| **myITprocess** | — | Push Recommendation *(manual click only)* |
| **RMM (Datto / Ninja / Atera / …)** | Device status | Deep-link WebRemote sessions |
| **VPN** (OpenVPN-3 / WireGuard) | Tunnel state | Required so the toolkit can reach customer-internal FortiGate / UniFi management interfaces |

**The write side is deliberately small and operator-initiated.** No
scheduled audit ever creates a ticket. The technician reads the
audit, decides what's a ticket and what's a planning item, and
clicks the corresponding button.

## What it explicitly does NOT do

- Replace your RMM, ticketing system, or documentation tool
- Auto-create tickets, auto-remediate, or take any action on its own
- Replace your RMM. Sybr HUB supports scoped web RDP and an isolated remote
  browser through Apache Guacamole, while provider-specific WebRemote remains
  a deep-link into the existing RMM.
- Store anything in the cloud (everything runs on your own host)

## Quick start

```bash
git clone https://github.com/franzjeger/sybr-hub
cd sybr-hub
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

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

## Documentation

- [`ROADMAP.md`](ROADMAP.md) — what's built, what's next
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module layout
- [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md) — wiring each upstream system
- [`docs/UPGRADING.md`](docs/UPGRADING.md) — behaviour changes that need a decision
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure

## Status

**Pre-1.0 (v0.1.0)** — the audit layer and report generator are battle-tested
(carried forward from MSP-Toolkit-V2 v10.10.12, validated against
multiple real Microsoft 365 tenants). The integration write-side
(Autotask, myITprocess, RMM) is scaffolded but not yet wired —
contributions welcome.

## License

MIT — see [`LICENSE`](LICENSE).

Built by [SYBR](https://github.com/franzjeger) — a Norwegian MSP
solving its own daily-workflow problem in the open.
