# Sybr HUB — Roadmap

The product vision, from the May 2026 workshop:

> A read-mostly aggregator that pulls everything an MSP technician
> touches into one per-customer view, and lets the operator turn
> findings into Autotask tickets (immediate fix) or myITprocess
> recommendations (planned work) with one click.

This document is the source of truth for what's in scope and what
isn't. If a feature isn't here, it's not on the roadmap yet — open
an issue to discuss.

## Done in v1.0.0 (Initial release)

Validated audit layer carried forward from MSP-Toolkit-V2 v10.10.12.
The data-quality pass that produced v10.10.2–.12 is locked in by
regression tests in this repo.

- **Microsoft 365 audit** — 29 sections (25 M365 + 4 Azure), full pagination on every
  Graph list endpoint, explicit data-gap signalling (refuses to
  fabricate a grade when MFA data is missing). MFA coverage is *enforced*
  coverage: a Conditional-Access exclusion counts as unprotected even for a
  registered user, and a CA-excluded Global Admin or brute-forced account is a
  critical finding, not raw-data trivia.
- **Report generator** — CIS / NIST CSF 2.0 / ISO 27001:2022 control
  mapping; verdicts grounded in actual data rather than substring
  matching against banners. Summary cards and CIS verdicts are reconciled
  against the raw data they cite — no control passes on evidence it did not
  read, and no card counts a policy the appendix does not show.
- **FortiGate audit** — REST-API client, policy + admin audit, encrypted
  config backup, CIS-Fortinet compliance checks. A read the firewall
  refused is reported unavailable, never as "0 policies, score 100" — the
  same "a refusal is not a zero" guarantee the M365 pipeline holds.
- **UniFi audit** — both controller-API and direct-SSH modes; firmware
  currency + EOL detection in both modes. A controller that answers 403
  reads as unavailable, not as a site with zero devices and no rogue APs.
- **VPN tunnel management** — OpenVPN-3 and WireGuard backends.
  Required infrastructure: customer FortiGate / UniFi management
  interfaces are on internal LANs, so the toolkit needs a way to
  reach them. The VPN module is operator-facing connectivity, not a
  customer-facing VPN-as-a-service product.
- **IT Glue integration** — read organizations + flexible assets;
  write audit reports + FortiGate config backups as encrypted
  attachments.
- **DNS email security** — SPF / DKIM / DMARC / MTA-STS over DoH,
  distinguishes transport errors from "record absent".
- **AES-256-GCM at-rest encryption** for everything written under
  `~/Documents/MSPToolkit/`.
- **Stubs** for Autotask, myITprocess, RMM — so the integration
  contracts are visible and reviewable before the implementation
  lands.
- **In-app self-update** — an admin pulls the deployed branch to `origin`
  and re-execs onto the new code from Settings, for a host that sits behind
  a tailnet a browser can reach but a build environment cannot. Admin +
  `can_write` only, never scheduled, current-branch-to-`origin` only.

## v0.2.0 — Autotask read-side

Make the per-customer Hub view show real Autotask data.

- [x] `AutotaskClient.list_accounts`, `get_account`, `get_contract`
- [x] Customer ↔ Autotask Account binding (`POST /api/hub/{id}/link`)
- [x] Hub view shows Classification icon + active contract name
- [x] Per-customer dashboard pulls the latest audit summary alongside

Written against Autotask's published REST reference, not a live instance —
no customer here has credentials yet. `test_connection()` performs zone
discovery and one bounded query and reports the field names that came back;
treat the first real run as the verification and expect to adjust names.

## v0.3.0 — Autotask write-side

The "Create Ticket from Finding" button actually creates tickets.

- [x] `AutotaskClient.create_ticket`, never retried on a 5xx — that rule
      exists so a POST which applied the write and failed on the way out
      does not become a second ticket
- [x] `POST /hub/{id}/tickets`, technician floor plus the `can_write`
      grant. `rec_id` travels in the body, not the path: it is built from
      a message key plus params carrying tenant data, and a path segment
      cannot safely hold one
- [x] Title / description pre-fill from finding context, with the source
      run and `rec_id` in the ticket body — a ticket outlives the report
- [x] Idempotency on `UNIQUE(customer_id, rec_id, system)` (migration 18).
      A lost race reports the orphaned ticket id rather than hiding it
- [x] Operator chooses title, queue and priority in an inline panel
- [x] A real settings form on the Autotask card — it was "Kommer snart"
      behind a disabled button, so nowhere in the product could anyone
      enter the credentials the endpoint needs
- [x] `tests/test_autotask_write_side.py` asserts no unattended module can
      reach the write side, which is what keeps the workshop's rule true

**Unverified against a live instance.** The ticket field names come from
Autotask's published reference. Run `/api/autotask/test` first and compare
`sample_fields`; expect to adjust. `autotask_default_queue_id`,
`autotask_default_priority` and `autotask_default_status` are settings
because status and priority are picklists a customised instance renumbers.

## v0.4.0 — myITprocess integration

Findings that need planning rather than immediate action.

- [x] `MyITProcessClient.list_accounts` + `MyITProcessAccountId` binding
      through `POST /hub/{id}/link`
- [x] `MyITProcessClient.create_recommendation`, never retried on a 5xx
- [x] "Til planlegging" button beside the ticket button on every finding
- [x] Operator picks category + priority (free text — see below)
- [x] `POST /hub/{id}/recommendations`, technician plus `can_write`, sharing
      `_push_finding` with the ticket endpoint so the duplicate-race handling
      exists once rather than twice
- [x] Idempotent per system, so one finding may be both a ticket and a
      recommendation but never two recommendations

**Weaker verification than Autotask, and the difference matters.** The Autotask
client was written against a published REST reference somebody had read. This
one was not: `app.myitprocess.com` was unreachable from the environment it was
built in, so the request shape comes from the contract the old stub declared.

What that changes in the code, deliberately:

- the base URL is a setting, so a wrong host is a settings change;
- the created id is read from a short list of candidate keys rather than one
  guess, and an unrecognised response says what it actually got;
- a collection is accepted bare or wrapped;
- category and priority are free text, because a dropdown of guessed
  vocabulary is worse than a field holding the real value;
- `/api/myitprocess/test` reports the field names that came back.

Run that test first. Expect to change something.

## v0.5.0 — RMM deep-link

Workshop direction: leverage existing RMM WebRemote rather than
building remote control. Start with one provider, add others as
demand surfaces.

- [ ] `RMMProvider` interface (already stubbed)
- [ ] Datto RMM driver (most common in our customer base)
- [ ] Hub view shows per-device "Open WebRemote" buttons
- [ ] Optional: Ninja, Atera drivers in subsequent releases

## v0.6.0 — Workshop carry-overs

Small but explicit items from the May 2026 workshop notes that don't
fit elsewhere:

- [ ] Verify what the M365 audit currently checks for *backup*
      (Workshop note: "Frank, sjekk hva audit sjekker etter når det
      gjelder backup")
- [ ] Fix the Azure Advisor VM backup report (flagged as wrong)
- [ ] Sybr HUB navigation reorganised around per-customer Hub view
      rather than per-feature tabs

## Out of scope (deliberately)

Things that were in the original MSP-Toolkit-V2 codebase but are not
part of the Sybr HUB vision and should not return without an explicit
decision:

- Auto-remediation of any kind — operator discretion is the workflow
- VPN-as-a-service for customer employees — see the note below

Two entries that used to be here have since been decided the other way,
and are recorded rather than quietly dropped:

- **Remote browser and web RDP via Guacamole** — now in scope and shipped.
  `docs/ARCHITECTURE.md` documents the boundary it runs behind: temporary
  JDBC connections, uniquely named, deleted on stop, swept by instance
  prefix after a crash. Provider WebRemote remains a deep-link.
- **Penetration testing module** — `app/modules/pentest/` exists. It has
  not been re-argued against the "read-mostly aggregator" framing, so it
  sits here as a known inconsistency rather than an endorsement.

VPN management is **in scope** as infrastructure (the toolkit must
reach customer-internal management interfaces) — the operator-facing
VPN routes are kept. What's out is any future "VPN-as-a-service for
end-users" framing — Sybr HUB is for MSP technicians, not customer
employees.

## Versioning

Semver. The integration write-side is the user-facing API surface
that needs the most caution: any breaking change to `AutotaskClient`
or `MyITProcessClient` method signatures is a major bump.

The `v0.2.0`–`v0.6.0` labels above are planning milestones, not release
tags: that work shipped inside the `v1.0.0` and `v1.1.x` releases. The
actual version is resolved from the git tag (see `app/core/version.py`),
and the current release is `v1.1.1`.

Release notes go in `CHANGELOG.md`. Each release should be testable
end-to-end against at least one real customer tenant before tagging.
