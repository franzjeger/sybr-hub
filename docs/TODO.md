# Sybr HUB: backlog

The actionable follow-ups as of October 2026, after the overhaul that ended
with PR #33. Each item says **what**, **where** and **done when**. ROADMAP.md
holds the product scope and the decisions; this file holds the work. Anyone
picking an item up, person or agent, should read CONTRIBUTING.md first: it
lists the checks every change must pass and the conventions that keep them
green.

Items are grouped, then roughly ordered by value within each group.

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

6. **Start-up failures print a wall of traceback.** A missing key-wrapping
   secret (`MasterKeyUnavailableError`, raised from
   `app/core/encryption.py` in `app/web/server.py::_lifespan`) ends in
   several hundred lines of nested lifespan frames before the one clear
   sentence. Done when: known start-up configuration errors log one line
   saying what is wrong and how to fix it, and exit non-zero, with a test.
7. **Two rules for "ready to audit".** The scheduler's all-customer cycle
   uses `_is_configured_for_audit` (`app/services/audit_scheduler.py`: tenant plus
   app id or GDAP, no secret check); the bulk audit uses
   `credentials.m365_ready` (`app/web/routes/audit.py::_bulk_targets`). They
   disagree for a customer whose secret is missing. Done when: both use one
   rule (likely `m365_ready`), with tests for both callers.
8. **The alert engine's firmware rule ignores the lifecycle table.**
   `firmware_outdated` in `app/services/alert_engine.py` is a hard-coded
   "FortiOS below 7.4"; Varsler uses `app/services/firmware_inventory.py` and
   `app/modules/fortigate_audit/firmware_lifecycle.py` (7.2 is end of life
   there, and a 7.4 device behind on patches is outdated). Done when: the
   alert reads the stored verdicts, so the two never disagree.
9. **Excel export prints invented zeros.** `/export/excel` reads persisted
   metrics where an unmeasured section is stored as 0 (the CSV export
   already writes "ikke målt"). Done when: unmeasured values are empty and
   marked, with a test.
10. **Bulk audit renders reports in Norwegian only** (`lang="no"` in the
    bulk route; the scheduler uses the hub's `ui_language`). Done when: it
    follows `ui_language`.
11. **Weekly report e-mail often has no PDF**: the scheduled audit renders
    HTML only, and the e-mail says so. Done when: the scheduled run also
    renders the PDF, or the e-mail links to the report in the hub.
12. **Two tabs on the same customer share one selected-run slot**
    (`app/core/job_state.py`, `get_user_audit`, per user and customer). Done when: the selection is
    per tab or carried in the request.
13. **Integrasjoner: a value typed before the cards finish loading is
    overwritten** when they load. Done when: loading never replaces a field
    the user has edited.

## C. Language

14. **Norwegian-only server texts**: the alert sweep's activity-log detail
    ("Fant N varsler…"), the scheduler's and bulk audit's webhook messages
    ("Audit feilet for …", "Bulk-audit fullført …") sent through
    `send_simple_message`, which also passes exception text unescaped into
    markdown, and `_notify_task_failure`'s card (English, with ⚠ and an em
    dash). Done when: keyed in the hub's language and escaped.
15. **Collectors' own English text reaches Norwegian reports** (Teams guest
    labels such as "Admins and Guest Inviters", FortiGate's "is an allow-all
    rule", the break-glass notes). `tests/test_norwegian_reports.py` treats
    anything in a run's files as data, so it passes them. Done when: the
    collectors store codes and the reports word them.
16. **Smaller copy**: `SOURCE` labels ("manuell tabell") and the history
    timestamp's fixed `nb-NO` locale in `app-integrations.js`; alert dates
    shown as ISO in sentences. Done when: keyed and formatted for the reader.

## D. Product

17. **Customer page KPI tiles do not show the score's gaps.** The reports
    list what the score could not measure; `_audit_metrics.json` does not
    store the gaps, so the page cannot. Done when: the metrics carry the
    gap keys and values, and the tiles show the same note.
18. **Microsoft 365 data backup**: native Microsoft 365 Backup is unproven
    live (A1), and third-party apps are found by display name only, so a
    renamed app is missed and nothing reads the last successful backup.
    Done when: a vendor API or a heuristic beyond the name is in place, or
    the limit stays documented.
19. **RMM deep-link** (ROADMAP v0.5.0, not started): an `RMMProvider`
    interface, a Datto RMM driver and per-device "Open WebRemote" buttons.
20. **Fleet and status cards**: Verktøy › Nettverk shows "Ikke lest ennå"
    on a fresh install until "Oppdater nå" or the daily firmware job; the
    FortiGate integration card's status is yes/no, not a count; the card
    dot means "last read OK", not "online now".
21. **Expiry banners**: expired and critical now look almost alike; only
    the title and dot differ.
22. **Terminal light palette** is modelled on GitHub's; its contrast is not
    measured.
23. **Provisioning and pentest keep a Kunde field** by design (provisioning
    can run for a prospect). Revisit if they move onto the customer page.

## E. Maintenance and debt

24. **UniFi firmware table is hand-maintained**; its 180-day window ends
    around 2027-04-02. Done when: a script refreshes it from Ubiquiti's
    public feed (`fw-update.ui.com/api/firmware-latest`), or a scheduled read
    uses the table as fallback. Power devices, SmartPower, LTE, Cloud Keys
    and AirWire are not in it and read unknown.
25. **Endpoints with no web caller**: `/api/setup/stream`, `/ws/dashboard`,
    `/api/dashboard/interval`, `/api/policy-backup/{id}/live`. Done when:
    removed with an UPGRADING note, or documented as API.
26. **One import cycle in the frontend**: the shell (`app.js`) and every
    feature module import each other. It is safe only because
    `scripts/js-modules.cjs` forbids load-time reads inside the cycle. Done
    when: shared pieces move down a layer and the cycle is broken.
27. **Ten exports exist only for specs** (listed in the ES-modules PR #22);
    drive those specs through the UI where reasonable.
28. **CSS**: a large utility layer (about 250 classes; 96 tags carry six or
    more); repeated patterns could become components. The 43 remaining
    `style="display:none"` attributes could become `hidden` with a small JS
    change each (several read `style.display` back).
29. **Service worker**: no navigation preload; a proxy 502 during a restart
    shows the proxy's page, not the offline page.
30. **Tailscale on the Tilgang tab** makes two uncached API calls per open;
    the tag slug comes from the customer id with no override.
31. **Old selection files** from the removed server-side active customer
    (`customers/.active/*`, `active.txt`) stay on disk; nothing reads them.
32. **The xterm styling workaround** depends on xterm 5.5 creating its styles
    through `documentOverride.createElement`
    (`app/web/static/app-infra.js`). `tests/browser/terminal.spec.cjs` will
    catch a change; the workaround would then need redoing.
