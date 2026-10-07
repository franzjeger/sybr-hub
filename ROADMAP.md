# Sybr HUB — Roadmap

The product vision, from the May 2026 workshop:

> A read-mostly aggregator that pulls everything an MSP technician
> touches into one per-customer view, and lets the operator turn
> findings into Autotask tickets (immediate fix) or myITprocess
> recommendations (planned work) with one click.

This document is the source of truth for what's in scope and what
isn't. If a feature isn't here, it's not on the roadmap yet — open
an issue to discuss.

## October 2026 quality work — complete locally

The execution plan and completion criteria are in
[docs/TODO.md, G35–41](docs/TODO.md#g-quality-execution-plan-october-2026).

- [x] First: isolated settings saves, preserved policy drafts and correct IT Glue
      stored-secret handling (35–37).
- [x] Next: integration check evidence, the guided policy workflow and visible
      risk-score coverage (38–40).
- [x] Then: acyclic frontend imports, shared form helpers and broader strict
      typing (41).

Customer isolation and capability checks are preserved. Captured evidence stays
separate from human alignment reviews. Local implementation and verification are
complete; live-system checks remain in section A and broader service rollout in
F34. C14 is complete locally; C15 is the next repository cleanup item.

October live-log follow-up is tracked in [docs/TODO.md, H42–47](docs/TODO.md#h-october-live-log-follow-up).
Collector and historical-report corrections are implemented. Tenant-side
Exchange/Purview consent and identity licences still need live
validation; active key-backup recovery was verified in isolation, with old
installation copies preserved; completed Intune, Teams, SharePoint and DNS reads do not imply
those remaining services are available.
Manual customer sign-in now retains an undelivered attempt after connection
failure, blocks simultaneous exchanges and provides explicit recovery advice.
Manual setup also repairs saved app consent for Exchange Online/Purview, waits
for fresh token roles and retains credentials until verification succeeds.
Administrator sign-in is still needed to apply those tenant-side grants.

## Done in v1.0.0 (Initial release)


Validated audit layer carried forward from MSP-Toolkit-V2 v10.10.12.
The data-quality pass that produced v10.10.2–.12 is locked in by
regression tests in this repo.

- **Microsoft 365 audit** — 28 sections (24 M365 + 4 Azure), full pagination on every
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
  **Retired by the September 2026 security review:** live git/pip/reexec updates
  are disabled. Build and verify an immutable artifact, then follow
  [the deployment and rollback procedure](docs/DEPLOYMENT.md).

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
- [x] Idempotency on `UNIQUE(customer_id, rec_id, system)`
      (pre-squash migration 18; now part of the squashed baseline).
      A lost race reports the orphaned ticket id rather than hiding it
      — superseded by the follow-up (pre-squash migration 20), which
      reserves the operation before the provider request and requires
      reconciliation of ambiguous outcomes.
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

- [ ] `RMMProvider` interface (the early stub was removed unused in 2026-10)
- [ ] Datto RMM driver (most common in our customer base)
- [ ] Hub view shows per-device "Open WebRemote" buttons
- [ ] Optional: Ninja, Atera drivers in subsequent releases

## v0.6.0 — Workshop carry-overs

Small but explicit items from the May 2026 workshop notes that don't
fit elsewhere:

- [x] Verify what the M365 audit currently checks for *backup*
      (Workshop note: "Frank, sjekk hva audit sjekker etter når det
      gjelder backup"). Answered October 2026: only Azure VM backup, from
      the Recovery Services vaults in the Azure subscriptions in scope.
      Nothing checks backup of the Microsoft 365 data itself (mailboxes,
      OneDrive, SharePoint, Teams); Exchange retention policies are
      collected, but retention is not backup.
- [x] Fix the Azure VM backup report (flagged as wrong). It was: the parser
      skipped every protected-item line, so every VM was reported as having
      no backup. Fixed October 2026, with tests that run the real collector.
- [x] Check backup of the Microsoft 365 data: Microsoft 365 Backup through
      Graph (`/solutions/backupRestore`), and third-party backup recognised
      from its app consent grants (Veeam, AvePoint, Keepit and the like).
      Done October 2026: section `34_m365_backup`, a verdict per workload
      (mail, OneDrive, SharePoint, with Teams shown), CIS row 11.2, a check in
      the Essential Eight and NIS2 baselines, and a recommendation when
      neither source shows anything. Needs `BackupRestore-Control.Read.All`
      and `BackupRestore-Configuration.Read.All`; without them Microsoft 365
      Backup reads as "could not be read". Not yet verified against a live
      tenant with Microsoft 365 Backup enabled.
- [x] The customer page is the hub of the work: findings first, worst
      first, with ticket and plan actions and the PSA/IT Glue links on the
      page itself (October 2026). Since then the navigation follows it:
      Oversikt, Kunder and Verktøy on top, Administrasjon as a page, no
      active-customer bar, and the customer page's tabs (Funn, Audit,
      Policyer, Vurderinger, Nettverk, Tilgang, Detaljer) in the address.

## Out of scope (deliberately)

Things that were in the original MSP-Toolkit-V2 codebase but are not
part of the Sybr HUB vision and should not return without an explicit
decision:

- Auto-remediation of any kind — operator discretion is the workflow
- VPN-as-a-service for customer employees — see the note below

Several capabilities sit outside the read-mostly framing and are kept as
**optional modules** an administrator switches on or off
(`app/core/modules.py`, October 2026): remote access (SSH, terminal, web RDP
and the remote browser via Guacamole), Tailscale administration, pentest,
provisioning, licences and hosting (ALSO, Uniweb) and the AI console. A
module that is off answers 404 and runs no jobs; a new install starts with
all of them off. That is the decision, recorded so it is not re-argued one
feature at a time.

VPN management is **in scope** as infrastructure (the toolkit must
reach customer-internal management interfaces) — the operator-facing
VPN routes are kept. What's out is any future "VPN-as-a-service for
end-users" framing — Sybr HUB is for MSP technicians, not customer
employees.

## Policy workspace — October 2026

Requested as a coherent customer policy section, with packages above the
individual Microsoft 365 services.

- [x] Four packages: security foundation, recommended workplace, secure
      collaboration and advanced protection.
- [x] Service library for Entra ID, Conditional Access, Intune, SharePoint,
      OneDrive, Teams, Purview, Exchange and Defender, available before audit.
- [x] Concrete proposed settings, licensing, dependencies, rollout stages,
      pilot impact, verification, rollback and primary Microsoft sources.
- [x] Tailored, encrypted customer plans and documented human assessments,
      with revision conflicts, evidence and expiring exceptions.
- [x] Separate captured inventory and drift from recommendations; a template
      name match never counts as verified effective configuration.

These are Sybr starting points with customer-specific scope and licensing,
not a certification. Saving a plan changes Hub data. Microsoft tenant writes
remain in the existing separately guarded CA/Intune deployment flows;
recommendations for the other services have manual administration runbooks.
Broader automatic evaluation is tracked as item F34 in docs/TODO.md.

## Known cleanup, deferred by choice

Recorded here so they are decisions rather than forgotten debt. None
blocks a release; each is a focused change that deserves its own PR and
its own review rather than being smuggled into an unrelated one.

- [x] **Operational correctness, backlog B6–B13** (October 2026). Known
  master-key configuration failures stop startup with a concise recovery
  message. Scheduled and bulk audits share the customer page's readiness
  rule. Firmware alerts read the same stored FortiGate and UniFi verdicts
  as Varsler. Excel leaves unmeasured values empty and names the gaps, and
  bulk reports use the hub's language. Scheduled reports include a PDF,
  same-customer tabs retain separate historical selections, and background
  integration reads preserve edits. The next repository item is language
  cleanup C15; live-system verification remains in section A of
  [docs/TODO.md](docs/TODO.md).
- [x] **Converge the two migration paths.** Resolved the other way round:
  the runner in `app/core/database.py` is what every install runs and is
  transactional, so it stays the single authority. The unused Alembic setup
  (`migrations/`, `alembic.ini`) is removed.
- [x] **Break up the report-builder giants.**
  `app/reports/compliance.py::_build_compliance_map` (~1800 lines) is a table
  of 35 controls, pinned by a characterisation snapshot, and
  `app/services/provisioning.py::_deploy_via_rest` (~980) is 16 named steps.
- [x] **The recommendations builder.** `_build_recommendations` (806 lines)
  is a table of 31 rules, pinned by its own characterisation snapshot.
- [x] **Recommendation ids that move.** Remediation state is keyed on a rec's
  id. The Azure Advisor ids no longer depend on the language (migration 24,
  October 2026). Each unreadable network file has its own id, named by the
  file (migration 25; a bare old id that no run or ticket ties to a file
  keeps its row and reads as open). Stored params hold values, a count or
  None, and `relocalise_recommendations` puts the words in for the reader,
  reading the words older runs froze in ("Ukjent antall", "bruker(e)", the
  Advisor label) back as values.
- [x] **The parsers read text the collectors wrote.** Every collector the
  report reads now writes a JSON sidecar beside its text file
  (`BaseSection._save_sidecar`), and the parsers read it first, with the text
  as the fallback for older runs (October 2026). Sections nothing reads are
  still text only.
- [x] **Reports carry the other language.** Every CIS row's title and detail
  is a key in `app/reports/i18n.py` (the pattern is described at the top of
  `compliance.py`), and so are the score's data gaps, the house standard's
  wording, the network section's labels, the CSV export and the report
  e-mail. `tests/test_english_reports.py` and `tests/test_norwegian_reports.py`
  render both reports in each language and fail on the other language
  outside the tenant's own data; the second also scans the Norwegian side of
  the whole table.
- **Verify the SSH provisioning path on a real FortiGate.** It sends whole
  `config` blocks and reads the answer for errors, which is how FortiOS keeps
  context, but it has only run against a fake device.
- [x] **Inline styles.** The SPA is built on design tokens and classes
  (`app/web/static/app.css`); 43 `style="display:none"` attributes remain,
  held by a budget that only goes down, and the frontend is ES modules without
  globals (October 2026).
- [x] **One active customer per user, on the server.** Every per-customer
  call names its customer; the server keeps no active customer (October
  2026).
- **Verify against live systems.** Autotask and myITprocess, the Exchange
  helper's recipient lookup, Microsoft 365 Backup and the UniFi model codes
  were built against published references and fakes. See docs/TODO.md,
  section A.

The actionable backlog, with where each item lives and when it is done, is
[docs/TODO.md](docs/TODO.md).

## Versioning

Semver. The integration write-side is the user-facing API surface
that needs the most caution: any breaking change to `AutotaskClient`
or `MyITProcessClient` method signatures is a major bump.

The `v0.2.0`–`v0.6.0` labels above are planning milestones, not release
tags: that work shipped inside the `v1.0.0` and `v1.1.x` releases. The
actual version is resolved from the git tag (see `app/core/version.py`),
and the current release is `v1.2.0`.

Release notes go in `CHANGELOG.md`. Each release should be testable
end-to-end against at least one real customer tenant before tagging.
