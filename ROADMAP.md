# Sybr HUB — Roadmap

The product vision, from the May 2026 workshop:

> A read-mostly aggregator that pulls everything an MSP technician
> touches into one per-customer view, and lets the operator turn
> findings into Autotask tickets (immediate fix) or myITprocess
> recommendations (planned work) with one click.

This document is the source of truth for what's in scope and what
isn't. If a feature isn't here, it's not on the roadmap yet — open
an issue to discuss.

## Done in v0.1.0 (Initial release)

Validated audit layer carried forward from MSP-Toolkit-V2 v10.10.12.
The data-quality pass that produced v10.10.2–.12 is locked in by 243
regression tests in this repo.

- **Microsoft 365 audit** — 26 sections, full pagination on every
  Graph list endpoint, explicit data-gap signalling (refuses to
  fabricate a grade when MFA data is missing).
- **Report generator** — CIS / NIST CSF 2.0 / ISO 27001:2022 control
  mapping; verdicts grounded in actual data rather than substring
  matching against banners.
- **IT Glue integration** — read organizations + flexible assets;
  write audit reports as encrypted attachments.
- **DNS email security** — SPF / DKIM / DMARC / MTA-STS over DoH,
  distinguishes transport errors from "record absent".
- **AES-256-GCM at-rest encryption** for everything written under
  `~/Documents/MSPToolkit/`.
- **Stubs** for Autotask, myITprocess, RMM — so the integration
  contracts are visible and reviewable before the implementation
  lands.

## v0.2.0 — Autotask read-side

Make the per-customer Hub view show real Autotask data.

- [ ] `AutotaskClient.list_accounts`, `get_account`, `get_contract`
- [ ] Customer ↔ Autotask Account binding (stored in customer config)
- [ ] Hub view shows Classification icon + active contract name
- [ ] Per-customer dashboard pulls the latest audit summary alongside

## v0.3.0 — Autotask write-side

The "Create Ticket from Finding" button actually creates tickets.

- [ ] `AutotaskClient.create_ticket` (manual only — guarded by
      `Depends(get_current_user)`, never called from scheduled code)
- [ ] Title / description pre-fill from finding context
- [ ] Idempotency — re-running an audit and re-clicking should not
      create duplicate tickets for the same finding
- [ ] Operator chooses Queue + Priority in a modal before submit

## v0.4.0 — myITprocess integration

Findings that need planning rather than immediate action.

- [ ] `MyITProcessClient.list_accounts` + customer binding
- [ ] `MyITProcessClient.create_recommendation`
- [ ] "Push to myITprocess as Recommendation" button on findings
- [ ] Operator picks category + priority

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

- Remote browser via Guacamole / x11vnc — use the RMM's WebRemote
- VPN management — separate concern, not workflow-critical
- Penetration testing module — not aligned with "read-mostly
  aggregator" framing
- Auto-remediation of any kind — operator discretion is the workflow

## Versioning

Semver. The integration write-side is the user-facing API surface
that needs the most caution: any breaking change to `AutotaskClient`
or `MyITProcessClient` method signatures is a major bump.

Release notes go in `CHANGELOG.md`. Each release should be testable
end-to-end against at least one real customer tenant before tagging.
