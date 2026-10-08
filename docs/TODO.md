# Sybr HUB: backlog

The actionable follow-ups as of October 2026, after the overhaul that ended
with PR #33. Each item says **what**, **where** and **done when**. ROADMAP.md
holds the product scope and the decisions; this file holds the work. Anyone
picking an item up, person or agent, should read CONTRIBUTING.md first: it
lists the checks every change must pass and the conventions that keep them
green.

Items are grouped, then roughly ordered by value within each group. Checked
items are complete; their numbers stay stable so commits and tests can refer
to them. The quality plan G35–41 below is complete locally. C15 is the next
repository item. Section A still needs live systems.
The October access repair is also complete: first-run administrators receive
full customer, Hub-write and tenant-write access, and schema 29 repairs the
initial active administrator on existing installs. See docs/UPGRADING.md.
The October live recheck of Intune and Teams now completes: nullable Teams
settings no longer crash, and Settings Catalog / ADMX use Graph beta.
Intune read-role and successful service-plan provisioning were verified;
an earlier 403 was not proof of a missing subscription. These targeted reads
do not close the broader Exchange and backup checks in A1.
The subsequent log review is recorded in H42–44 below. The latest live run
collected Intune, Teams, SharePoint and DNS. Exchange consent, identity
licensing remain explicit external follow-ups. Active-installation key recovery
was verified in isolation; older installation copies remain preserved.

---

## A. Needs a person and a live system

These cannot be finished in the repository. Each was built against published
documentation, fakes or mocks, and says so in its code.

1. **One audit against a real tenant.**
   - What it proves: the Exchange helper's recipient lookup for forwarding
     (`app/helpers/exo_collector.ps1`, `Resolve-RecipientInfo`, read by
     `app/modules/m365_audit/sections/exchange.py`); whether Microsoft 365
     Backup answers a plain audit app with `BackupRestore-Control.Read.All`
     and `BackupRestore-Configuration.Read.All`
     (`app/modules/m365_audit/sections/m365_backup.py`; Microsoft documents
     these APIs for "registered Backup Controller applications"); that every
     JSON sidecar matches its text file on real data.
   - Done when: a run's `34_m365_backup`, `28*`/`29*` forwarding files and
     sidecars read right in both reports, and the findings match what the
     tenant's admin centre shows.
2. **Autotask and myITprocess against live instances.** Written against
   their published references. Run `/api/autotask/test` and compare
   `sample_fields`; create one ticket and one recommendation from a finding.
   Done when: both round trips work and the field names are confirmed.
3. **SSH provisioning on a physical FortiGate**
   (`app/services/provisioning.py`, SSH deploy path). Done when: a deploy to a
   lab FortiGate applies and reports each step.
4. **UniFi model codes from a real controller.** The firmware table
   (`app/modules/unifi_audit/firmware_db.py`) is keyed by model code taken
   from Ubiquiti's catalog and firmware feed; for UCG-Fiber, UDR7 and
   EFG-Core the two disagree and both are keys. Done when: a controller's
   `stat/device` codes are checked against the table. UXG-Pro is judged
   against the UXG line by inference from build tags; confirm it.
5. **CIS numbering.** The compliance map (`app/reports/compliance.py`) says
   its ids follow CIS Microsoft 365 Foundations v3.1; a review suspected some
   ids and titles do not. Done when: every id and title is checked against
   the benchmark document (needs a CIS account) and corrected, with the
   characterisation snapshot regenerated and explained.

## B. Correctness

6. [x] **Concise start-up configuration failures** (October 2026).
   `app/web/middleware/startup_config.py` checks the master key before the
   router's lifespan. A known key configuration error sends one ASGI startup
   failure with the cause and recovery settings; unexpected failures retain
   their diagnostics. `tests/test_startup_config.py` checks the protocol and
   real non-zero exits through both `main.py` and Uvicorn, with no traceback.
7. [x] **One rule for "ready to audit"** (October 2026). Both scheduler modes
   and `app/web/routes/audit.py::_bulk_targets` use `credentials.m365_ready`:
   tenant plus app id and a stored secret, or GDAP with a tenant. Scheduler
   and bulk tests cover missing secrets and delegated access.
8. [x] **Firmware alerts follow the stored lifecycle verdicts** (October
   2026). `app/services/alert_engine.py` uses `firmware_inventory.attention`,
   as Varsler does, for FortiGate and UniFi. End-of-life is critical; outdated
   firmware is a warning with the available version. The sweep does no fleet
   poll. `tests/test_firmware_inventory.py` checks agreement, failed reads,
   retired customers, distinct devices and an unreadable inventory.
9. [x] **Excel export preserves unknown values** (October 2026). The metrics
   writer already stores an unread section as `null`; Excel tried to round
   those percentages and crashed. It now leaves unknown values empty, keeps
   measured zeros and appends a translated column naming the unmeasured
   fields. `tests/test_dashboard_export_language.py` covers both languages,
   nulls, absent fields, measured zero and customers without a run. Older
   metrics that flattened missing data to zero must be regenerated; a zero
   alone cannot establish whether it was measured (see docs/UPGRADING.md). Imported text that
   starts like a spreadsheet formula is neutralised in both exports.
10. [x] **Bulk reports follow `ui_language`** (October 2026). The bulk route
    reads the hub's language once per cycle for both report generation and
    summary context, falling back to Norwegian for an invalid setting.
    `tests/test_bulk_audit_targets.py` covers Norwegian, English and fallback.
11. [x] **Scheduled reports include a PDF** (October 2026). The scheduled
    audit renders HTML and PDF before automatic e-mail. If rendering fails,
    it logs the failure and sends no incomplete report. The report-e-mail
    tests cover generation order and failure; the existing sender attaches
    the generated PDF.
12. [x] **Separate selected runs in same-customer browser tabs** (October
    2026). Requests carry a per-document `X-Audit-Tab`; selections remain
    scoped to authenticated user and customer. Server-owned collection is
    still shared, with bounded browser selections and support for legacy
    API clients. An end-to-end route test loads two actual runs and verifies
    each tab's CSV contains its own measured values.
13. [x] **Integration reads preserve edits** (October 2026). Settings loads
    populate only untouched fields, including passwords and checkboxes.
    Browser tests delay the settings response, edit fields, then refresh
    status again; untouched fields populate and drafts stay intact.

## C. Language

14. [x] **Background notification language and literal data** (October 2026).
    Alert-sweep activity, scheduled and bulk audit notifications, credential
    notices and auto-disabled task messages now use keyed text in the Hub's
    configured language. Simple Teams cards use literal TextRuns; Slack uses
    plain-text blocks, so customer names and exception strings cannot become
    markdown links or channel mentions. Task delivery checks require HTTP 2xx.
    Scheduled completion includes the actual report context and failed sections.
    Norwegian/English and mocked-delivery regressions cover these paths.
15. **Collectors' own English text reaches Norwegian reports** (Teams guest
    labels such as "Admins and Guest Inviters", FortiGate's "is an allow-all
    rule", the break-glass notes). `tests/test_norwegian_reports.py` treats
    anything in a run's files as data, so it passes them. Done when: the
    collectors store codes and the reports word them.
16. **Smaller copy**: `SOURCE` labels ("manuell tabell") and the history
    timestamp's fixed `nb-NO` locale in `app-integrations.js`; alert dates
    shown as ISO in sentences. Done when: keyed and formatted for the reader.

## D. Product

17. [x] **Customer page KPI tiles do not show the score's gaps.** The reports
    list what the score could not measure; `_audit_metrics.json` does not
    store the gaps, so the page cannot. Done when: the metrics carry the
    gap keys and values, and the tiles show the same note.
    Done by G40: `_audit_metrics.json` stores `risk_coverage`, and the
    customer page shows it.
18. **Microsoft 365 data backup**: native Microsoft 365 Backup is unproven
    live (A1), and third-party apps are found by display name only, so a
    renamed app is missed and nothing reads the last successful backup.
    Done when: a vendor API or a heuristic beyond the name is in place, or
    the limit stays documented.
19. **RMM deep-link** (ROADMAP v0.5.0, not started): an `RMMProvider`
    interface, a Datto RMM driver and per-device "Open WebRemote" buttons.
20. [x] **Fleet and status cards**: Verktøy › Nettverk shows "Ikke lest ennå"
    on a fresh install until "Oppdater nå" or the daily firmware job; the
    FortiGate integration card's status is yes/no, not a count; the card
    dot means "last read OK", not "online now". Done (October 2026): a
    FortiGate with a token and no reading is read once when Nettverk opens;
    the card counts read, failed and unread firewalls; the dot and footer
    say "last read", with its time.
21. [x] **Expiry banners**: expired and critical now look almost alike; only
    the title and dot differ. Done (October 2026): expired has a solid red
    edge, a warning icon and a solid badge; every line says its state.
22. [x] **Terminal light palette** is modelled on GitHub's; its contrast is not
    measured. Done (October 2026): `tests/test_terminal_palette.py` measures
    all 16 colours in both themes; all but dark-theme black reach 4.5:1.
23. **Provisioning and pentest keep a Kunde field** by design (provisioning
    can run for a prospect). Revisit if they move onto the customer page.

## E. Maintenance and debt

24. [x] **UniFi firmware table is hand-maintained**; its 180-day window ends
    around 2027-04-02. Done when: a script refreshes it from Ubiquiti's
    public feed (`fw-update.ui.com/api/firmware-latest`), or a scheduled read
    uses the table as fallback. Power devices, SmartPower, LTE, Cloud Keys
    and AirWire are not in it and read unknown.
    Done (October 2026): `scripts/refresh_unifi_firmware.py` reads the feed
    for every model code in the table; tested on a fixture, so the feed's
    real shape still needs one live run.
25. [x] **Endpoints with no web caller**: `/api/setup/stream`, `/ws/dashboard`,
    `/api/dashboard/interval`, `/api/policy-backup/{id}/live`. Done when:
    removed with an UPGRADING note, or documented as API.
    Done (October 2026): all four removed. `/api/dashboard/assets` has no
    web caller either; it was fixed (it never listed network devices) and
    kept as API.
26. [x] **One import cycle in the frontend**: the shell (`app.js`) and every
    feature module import each other. It is safe only because
    `scripts/js-modules.cjs` forbids load-time reads inside the cycle. Done
    when: shared pieces move down a layer and the cycle is broken.
    Done by G41: `scripts/js-modules.cjs` rejects every import cycle.
27. **Ten exports exist only for specs** (listed in the ES-modules PR #22);
    drive those specs through the UI where reasonable.
28. **CSS**: a large utility layer (about 250 classes; 96 tags carry six or
    more); repeated patterns could become components. The 43 remaining
    `style="display:none"` attributes could become `hidden` with a small JS
    change each (several read `style.display` back).
29. **Service worker**: no navigation preload; a proxy 502 during a restart
    shows the proxy's page, not the offline page.
30. [x] **Tailscale on the Tilgang tab** makes two uncached API calls per open;
    the tag slug comes from the customer id with no override.
    Done (October 2026): one call per open, cached for a minute and
    cleared on any mapping change; a per-customer tag override (migration 31).
31. [x] **Old selection files** from the removed server-side active customer
    (`customers/.active/*`, `active.txt`) stay on disk; nothing reads them.
    Done (October 2026): migration 30 removes exactly those files.
32. **The xterm styling workaround** depends on xterm 5.5 creating its styles
    through `documentOverride.createElement`
    (`app/web/static/app-infra.js`). `tests/browser/terminal.spec.cjs` will
    catch a change; the workaround would then need redoing.


## F. Policy workspace

33. [x] **Coherent policy packages and service library** (October 2026).
    Four cross-service packages and 39 bilingual recommendations across
    Entra, Conditional Access, Intune, SharePoint, OneDrive, Teams, Purview,
    Exchange and Defender. Each includes proposed settings, rationale,
    licensing, dependencies, pilot impact, verification, rollback and
    Microsoft Learn sources. Customer plans and evidence are encrypted,
    scoped and revision checked; expired exceptions and changed guidance
    require reassessment. Name matches are explicitly not effective compliance.
34. **Evaluate effective settings and assignments across all services.**
    The workspace currently records human assessments and separately shows
    captured policy inventory. Broader automated verification and rollout
    need service-specific evidence, licence checks, previews and restore
    support. Done when: each supported recommendation is evaluated against
    actual settings and scope, with unknowns preserved and live pilot checks.

## G. Quality execution plan (October 2026)

Completed locally: 35–37 first, followed by 38–41. Customer scope and
capability checks are preserved. Deployment follows the existing release
procedure; live vendor validation remains in section A.

35. [x] **Isolate settings writes.** Storage and branding save only their
    own fields; integration cards send focused updates, never echo a full
    settings snapshot. Done when concurrent unrelated edits survive saves.
36. [x] **Preserve policy drafts.** Keep review text, status, due date and
    plan selections per customer across filters and navigation; show dirty
    state and provide an explicit discard action. Done when filtering and
    switching customers cannot silently lose or mix unsaved work.
37. [x] **Use stored IT Glue secrets correctly.** Masked and omitted keys
    use the encrypted stored key; an explicitly selected region remains the
    region tested. Done when reload, region changes and vendor failures are
    covered without a live vendor or exposing the secret.
38. [x] **Make integration status precise.** Separate configured, verified,
    failed and stale states; include the last check time. Saving credentials
    is not verification. Done when refresh preserves the same meaning and
    changes invalidate previous verification.
39. [x] **Guide policy work.** Connect package selection, customer evidence,
    prioritised gaps, pilot instructions and verification in one workflow.
    Compare captured settings where evidence supports a verdict; remaining
    recommendations stay explicitly unmeasured. Broad rollout and live
    service verification remain F34. Done when the next useful action is
    clear and captured evidence never implies effective scope by name alone.
40. [x] **Explain risk-score coverage.** Persist the scorer's missing-data
    reasons and show them beside the customer's score in both languages.
    Old runs without coverage evidence remain unknown. Done when the report
    and customer page agree, including a blocked or partial score.
41. [x] **Strengthen code boundaries.** Extend checked typing to the changed
    settings/auth/policy boundaries, remove the frontend import cycle and
    centralise shared settings-form behaviour. Done when module checks reject
    cycles, new code is lint clean and the wider type check passes.

For completion: targeted regression tests, full Python suite, three consecutive
full browser runs, JavaScript and vendor hash checks, architecture and typing
checks, lint budget, wheel build/asset verification, and desktop/mobile visual
inspection. Report unavailable external checks explicitly.


Validation on 2026-10-04: 6025 Python tests passed, 1 skipped (two inherited
TestClient deprecation warnings); 181 browser tests passed in three consecutive
full runs. JavaScript checks found 35 modules and no import cycles. Strict mypy
passed for 11 files; architecture, vendor hashes and the unchanged lint budget
(54 inherited findings) passed. The wheel was rebuilt and its new modules and
assets verified; desktop/mobile policy and risk-evidence screens were inspected.
OSV found no known vulnerabilities in either vendored JavaScript or the Python
lock file. PyPI-based auditing/hash validation could not complete because
pypi.org failed DNS resolution; OSV verifies vulnerability records and hash
presence, not package hash validity. No dependencies were changed.

## H. October live-log follow-up

42. [x] **Correct collector diagnostics and report coverage.** Risky users
    use `identityProtection/riskyUsers`; setup includes the separate
    `IdentityRiskEvent.Read.All` grant for risk detections. Explicit Graph
    licence errors, including PIM's licence-only HTTP 400, retain their
    cause. Exchange certificate login resolves the initial onmicrosoft.com
    domain without changing the customer's public report domain. Failed
    Exchange collection remains failed and its data gap survives historical
    report regeneration. PDF templates no longer request blocked remote
    fonts, emit duplicate named anchors or link to absent Exchange content.
    Regression tests and synthetic
    PDF rendering cover these changes.
43. **Complete tenant-side access and licence validation.** Fresh Graph
    tokens contain all required Graph roles, including IdentityRiskEvent.Read.All;
    risk-detection reads succeed. Exchange/Purview application permissions and
    supported directory roles still require administrator sign-in. Risky users
    explicitly refuse the tenant's licence; PIM requires Entra ID P2 or Governance.
    Done when a fresh audit measures those services after consent, or records
    them as deliberately unavailable. Successful Exchange/Purview collection has
    not yet been verified.
44. [x] **Active recovery verification and shared Graph read cooldown.** A copy
    of the active installation's protected key was opened in a private isolated
    directory. An authenticated encrypted archive was restored only into that
    directory; SQLite integrity and all restored customer configurations passed.
    The two older unreadable copies are byte-identical to the default installation's
    data-directory copy, rather than the active temporary installation's key
    backup. All original copies and both installations were left untouched.
    Recovering that older installation still requires its original wrapping
    secret or master key; no ownership is inferred beyond matching existing blobs.
    Graph JSON/paginated reads and CSV reports now share a per-tenant, per-process
    event-loop cooldown. Retry-After delta/date values and fallback backoff are
    supported; three attempts and a bounded wait preserve failure rather than
    returning false empty data. Parallel-client, tenant-isolation, cancellation,
    pagination-completeness and long-wait regressions passed. No new live 429
    experiment was forced against Microsoft.

H42 verification: full Python suite, three consecutive full browser suites,
JavaScript/module checks, vendor hashes, architecture, strict typing, lint
budget and wheel/asset checks passed. Collected and empty synthetic PDF
reports rendered successfully; contents and summary pages were inspected.
The local test service was restarted after verifying no audit was running;
health/database checks passed and the first active administrator retained
all three grants. Tenant consent and licences were not changed.

45. [x] **Recover manual customer sign-in after an undelivered request.** The
    October 5 failure began with server-side DNS resolution and then became
    invalid state because the verifier was deleted before delivery. A DNS,
    connection or connect-timeout failure now keeps the verifier until expiry
    for an explicit retry; uncertain delivery, rejection and success consume
    it. Attempts are bound to the Hub user and concurrent exchanges are
    refused. Setup disables duplicate submission, logs translated causes,
    offers a new sign-in and avoids API-only retries that omit registration
    and completion handling. Mocked transport, authenticated-route and
    Norwegian/English browser tests cover the recovery branches.

46. [x] **Complete and verify manual app consent.** PKCE setup now configures
    and grants Graph, Exchange Online and Purview application roles plus the
    Exchange Administrator for Exchange and Global Reader for Purview. Grant
    responses are checked;
    fresh secret/certificate tokens and an organization read gate completion.
    Known app IDs and valid credentials are reused; encrypted checkpoints
    resume partial setup without duplicate apps or repeated credential minting.
    Existing permissions, certificates, customer metadata and access boundaries
    are preserved. Renewal binds administrator sign-in to the selected tenant,
    issues a fresh pair after consent and retains current credentials until
    verification. Failed customer registration cannot report success. Tenant-side consent still requires administrator
    sign-in; live workload availability is verified by a subsequent audit.

47. [x] **Explain Backup Storage registration separately from consent.** A
    `403 AppNotRegistered` now records `not_registered` coverage and names the
    workload registration gap instead of claiming Graph permissions are missing.
    Licence and other service failures retain their own diagnostic detail.
    No backup billing/controller registration is performed by an audit.

H45–47 verification on 2026-10-05: 6082 Python tests passed, 1 skipped;
187 browser tests passed in three consecutive full runs. Targeted transport,
setup/renewal, workload-role, customer-scope and backup-diagnostic regressions
passed. JavaScript, strict typing, architecture, vendor hashes, lint budget
(54 inherited findings), wheel build and packaged assets passed. The setup
panel was inspected with an isolated test account. The local Hub was restarted
only after checking audits were idle; health/database and authenticated PKCE
start checks passed, and the administrator retained all three grants.
Fresh read-only Microsoft checks succeeded for Intune, Teams, SharePoint,
Conditional Access and other Graph sources. PIM/risky-user refusals named
licence requirements; Backup returned AppNotRegistered. Exchange/Purview
certificate token acquisition worked, but application permissions and the
supported directory roles still require administrator consent. No live tenant
grants were changed and a successful Exchange/Purview audit is not claimed.

C14/H44 verification on 2026-10-05: the full Python and browser suites passed,
along with JavaScript/module checks, vendor hashes/advisories, architecture,
strict typing (including both new modules), unchanged lint debt and wheel
assets. The active encrypted archive and key copy passed isolated restoration,
SQLite integrity and customer-configuration decryption. Original key backup
blobs were unchanged; no older installation was restored or overwritten.
The local Hub was restarted only after authenticated checks confirmed user
audits and setup were idle and scheduled audits were disabled. Public health
and database checks passed; the initial administrator retained all three
capabilities. No Microsoft tenant grants were changed. H43 and broader policy
service evaluation in F34 still require live verification.
