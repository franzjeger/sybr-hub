# Critical review remediation checklist

This document is the source of truth for findings from the focused critical
review of areas that had received less attention in earlier hardening work.

- Review date: 2026-08-10
- Baseline: `main` at `0347771`
- Baseline verification: `1869 passed`, one third-party deprecation warning
- Lint baseline: debt budget passed with 932 existing findings

## How to use this checklist

- Leave a finding unchecked until every acceptance criterion and required test
  below it is complete.
- Record the implementing commit or PR and the verification date in the
  tracking table.
- Check a finding only after the focused tests and the full test suite pass.
- Do not weaken an acceptance criterion merely to make an existing
  implementation pass. Document an explicitly accepted exception instead.
- Do not include credentials, customer identifiers, or other production data
  in this document, commits, tests, or review notes.

`SR-001` through `SR-005` are release blockers for a multi-user production
deployment.

## Finding checklist

- [x] **SR-001:** Provisioning ownership and credential boundaries
- [x] **SR-002:** ALSO customer isolation
- [ ] **SR-003:** Backup and restore safety
- [x] **SR-004:** Scheduler lifecycle and single-flight
- [x] **SR-005:** Atomic, concurrency-safe settings storage
- [ ] **SR-006:** Pentest execution boundary and process cleanup
- [ ] **SR-007:** Security finding accuracy and data freshness

## Tracking table

Status verified 2026-08-14 against `main` at `221f4e5` (v1.0.0-46), by reading the
current code for each acceptance criterion and running an adversarial second pass
that tried to overturn every verdict in both directions. Nothing was overturned.
"Criteria" counts each acceptance criterion as met / partial / unmet.

| ID | Priority | Status | Criteria (met·partial·unmet) | Landed since baseline | Focused test |
|---|---:|---|---|---|---|
| SR-001 | P1 | **Complete** | 8·0·0 of 8 | #124 | present |
| SR-002 | P1 | **Complete** | 7·0·0 of 7 | #122 | present |
| SR-003 | P1 | Not started | 0·1·9 of 10 | none | absent |
| SR-004 | P1 | **Complete** | 7·0·0 of 7 | #125 | present |
| SR-005 | P1 | **Complete** | 5·0·0 of 5 | #123 | present |
| SR-006 | P2 | Not started | 0·1·4 of 5 | none | absent |
| SR-007 | P2 | Not started² | 0·1·6 of 7 | none | absent |

² SR-007's four named evidence files (`vuln_checker.py`, `cms_scanner.py`,
  `tls_auditor.py`, `firmware_db.py`) are byte-identical to baseline. PRs #118
  and #119 did accuracy/freshness work, but in *other* files (device clients,
  dashboard poller, m365 report sections), not in SR-007's defined scope.

### Correlation against landed work (2026-08-14)

Commits since the baseline `0347771` (= PR #116) — PRs #117–#120 plus five loose
commits — were a *different* hardening pass than these seven findings describe:
insecure-transport refusal, error/redaction handling, Autotask and MyITProcess
ticket write-side, device-client retry and "unavailable vs zero" semantics, m365
report accuracy, and application self-update (#120). Exactly one SR acceptance
criterion (SR-004 #3, `HH:MM`/interval validation via the `TaskSchedule` model in
`dbbc3d6`) was advanced. As found on 2026-08-14 all five P1 release-blockers were effectively open and
none of the seven required focused tests existed; they were closed in the PRs
noted below.

**SR-002 landed in #122** (2026-08-14): every ALSO route scoped to the
caller's accessible customers, `get_invoices` made admin-only, per-user
scan progress, 18 direct-object-reference tests, adversarially reviewed.
SR-001 landed in #124 (owner+customer authorization, 404 non-disclosure, secret redaction, the credential-target guard extended to the wizard origin and the UniFi leg, admin feature floor + tenant_write on deploy). SR-005 landed in #123 (atomic writes, a settings lock + update_app_settings, all 13 read-modify-write sites converted, webhook test no longer persists). SR-004 landed in #125 (both schedulers start from the lifespan and are awaited on shutdown, per-task single-flight, a failure breaker that survives restart, and the duplicated audit-loop maintenance removed). **All five P1 release-blockers are now closed.**

Most severe still-open gaps for a multi-user production deployment:

- **SR-006** — the web process runs `sudo nmap`/SMB inline (`scanner.py:116`,
  `smb_enum.py:44`), incompatible with the hardened `NoNewPrivileges=yes` unit;
  timeout/cancel does not kill the process group.

## SR-001 — Provisioning ownership and credential boundaries

**Risk:** A provisioning session records its owner, but session reads, writes,
generation, deployment, and deletion do not enforce that owner. Raw step data
can contain secrets. A target stored in wizard step 1 also bypasses the
configured-host check while stored FortiGate credentials may still be selected.
The API accepts a technician even though the feature matrix classifies
provisioning as admin functionality.

**Evidence:**

- `app/services/provisioning.py`: session lifecycle and `_resolve_fortigate_conn`
- `app/web/routes/provisioning.py`: session, generation, deployment, and delete routes
- `app/core/features.py`: provisioning role declaration

**Acceptance criteria:**

- [x] Bind every session to both `user_id` and `customer_id` at creation.
- [x] Enforce owner and current customer access on every session operation.
- [x] Return `404` rather than disclosing whether another user's session exists.
- [x] Never return or persist raw passwords, API tokens, generated private
      secrets, or equivalent values in client-visible session state.
- [x] When a stored credential is used, require the resolved target to match the
      customer's configured device, regardless of where the target originated.
- [x] Require explicit credential entry for replacement/bootstrap devices that
      do not match the configured target.
- [x] Align route authorization with the feature matrix and require the intended
      write capability for deployment.
- [x] Add two-user and two-customer isolation tests, secret-redaction tests, and
      an attacker-controlled target regression test.

**Required focused test:** `tests/test_provisioning_isolation.py`

## SR-002 — ALSO customer isolation

**Risk:** Authenticated users can list provider-wide companies, request
arbitrary provider account IDs, and read globally cached renewal, price, MRR,
invoice, report, and license-optimization data. A write-enabled authenticated
user can also update a renewal record by database ID without a customer access
check. Global progress dictionaries disclose cross-user job context and allow
concurrent jobs to overwrite each other.

**Evidence:** `app/web/routes/also.py`

**Acceptance criteria:**

- [x] Resolve the caller's accessible Sybr customer IDs for every ALSO request.
- [x] Map each provider `account_id`, subscription ID, and renewal ID to a Sybr
      customer before returning or mutating data.
- [x] Filter cached queries, aggregates, PDFs, invoices, renewals, and license
      optimization results to the authorized customer set.
- [x] Make genuinely provider-wide views admin-only when they cannot be safely
      customer-scoped.
- [x] Remove provider response samples from normal application logs or redact
      them to a documented allowlist.
- [x] Replace global progress dictionaries with per-user job state and enforce
      single-flight where appropriate.
- [x] Add direct-object-reference tests for company, subscription, renewal,
      invoice, report, and optimization endpoints.

**Required focused test:** `tests/test_also_customer_scope.py`

## SR-003 — Backup and restore safety

**Risk:** A custom backup destination may be placed inside a source tree and
cause the archive to include itself while it is being written. Restore imports
the master key before validating the complete archive, performs unbounded ZIP
reads, modifies live data incrementally, and overwrites the active SQLite
database without quiescing the application. Failure can leave a partial restore
or a key/data mismatch. The password-wrapped key does not encrypt or authenticate
the complete ZIP archive.

**Evidence:** `app/web/routes/backup.py`, `app/services/scheduler.py`

**Acceptance criteria:**

- [ ] Reject backup destinations inside every included source tree.
- [ ] Create backups under a temporary name and atomically rename on success.
- [ ] Serialize backup creation so scheduled and manual backups cannot collide.
- [ ] Add an authenticated manifest containing format version, file paths,
      sizes, and cryptographic hashes.
- [ ] Clearly distinguish key portability from whole-archive confidentiality;
      add archive-level authenticated encryption if confidential portable
      backups are promised.
- [ ] Enforce entry-count, per-entry size, total uncompressed size, and
      compression-ratio limits before extraction.
- [ ] Validate and stage the complete restore, including SQLite integrity,
      before modifying live state or importing a master key.
- [ ] Quiesce writers and close the database pool during commit.
- [ ] Commit atomically where possible and provide automatic rollback for every
      changed data class and the master key.
- [ ] Add corruption, wrong-password, ZIP bomb, self-inclusion, partial-write,
      rollback, and live-database regression tests.

**Required focused test:** `tests/test_backup_restore.py`

## SR-004 — Scheduler lifecycle and single-flight

**Risk:** Neither scheduler implementation starts from the application lifespan,
so enabled jobs silently stop after a service restart until settings are saved.
Unvalidated intervals can schedule work every five seconds, invalid times can
kill a loop, and manual runs can overlap scheduled runs. Two overlapping
scheduler implementations create a double-run risk if startup is added naively.

**Evidence:**

- `app/web/server.py`: application lifespan
- `app/core/scheduler.py`: audit scheduler
- `app/services/scheduler.py`: task scheduler
- `app/web/routes/settings.py`: scheduler configuration routes

**Acceptance criteria:**

- [x] Choose one scheduler or document and enforce non-overlapping ownership of
      every job.
- [x] Start enabled jobs in application lifespan and await cancellation on
      shutdown.
- [x] Validate schedule type, bounded positive interval, weekday, and strict
      `HH:MM` input before saving configuration.
- [x] Add a per-task single-flight lock shared by scheduled and manual runs.
- [x] Persist circuit-breaker/disabled state when repeated failures disable a
      task, or define an explicit recovery policy.
- [x] Prevent duplicate execution across processes with a leader or lease before
      multi-worker deployment is supported.
- [x] Add lifespan, invalid-configuration, overlap, cancellation, restart, and
      repeated-failure tests.

**Required focused test:** `tests/test_scheduler_lifecycle.py`

## SR-005 — Atomic, concurrency-safe settings storage

**Risk:** General encrypted file helpers write directly to their final path even
though an atomic private-write helper already exists. Multiple request and
background paths perform whole-file read/modify/write cycles, allowing crashes
to corrupt settings and concurrent updates to lose unrelated changes. The
webhook test temporarily persists a value and later restores a stale snapshot.

**Evidence:**

- `app/core/encryption.py`: encrypted file writers
- `app/core/config.py`: settings load/save API
- `app/web/routes/settings.py`: webhook test and scheduler updates

**Acceptance criteria:**

- [x] Use temporary-file, flush, `fsync`, and atomic replace semantics for every
      encrypted settings/customer write.
- [x] Serialize settings transactions and detect stale revisions, or move
      settings into transactional SQLite storage.
- [x] Change focused settings updates to mutate only their owned fields.
- [x] Send a test webhook to the supplied URL without persisting that URL.
- [x] Add concurrent-update, interrupted-write, stale-revision, and rollback
      tests.

**Required focused test:** `tests/test_settings_concurrency.py`

## SR-006 — Pentest execution boundary and process cleanup

**Risk:** Nmap and SMB enumeration invoke `sudo`, while the production systemd
unit deliberately uses `NoNewPrivileges=yes`. The feature therefore cannot work
under the documented hardened deployment. Timeout and cancellation paths return
without terminating and awaiting the subprocess, which can leave a scan running.

**Evidence:**

- `app/modules/pentest/scanner.py`
- `app/modules/pentest/smb_enum.py`
- `scripts/sybr-hub.service`

**Acceptance criteria:**

- [ ] Remove `sudo` and privileged scanning from the web process.
- [ ] Run privileged scanning through a separately authenticated, narrowly
      scoped worker/helper with target and option allowlists.
- [ ] Detect unavailable capability and disable the UI/API with a clear reason.
- [ ] On timeout, cancellation, or shutdown, terminate the entire process group
      and await exit.
- [ ] Add hardened-service capability and long-running fake-process tests.

**Required focused test:** `tests/test_pentest_runtime.py`

## SR-007 — Security finding accuracy and data freshness

**Risk:** Several security conclusions are produced from static or incomplete
knowledge while being presented as definitive. The vulnerability checker has no
implemented NVD query, WordPress versions at or above a fixed threshold are
treated as current indefinitely, TLS checks do not fully validate trust or weak
algorithms, and the manually maintained UniFi firmware table has no stale-data
failure mode.

**Evidence:**

- `app/modules/pentest/vuln_checker.py`
- `app/modules/pentest/cms_scanner.py`
- `app/modules/pentest/tls_auditor.py`
- `app/modules/unifi_audit/firmware_db.py`

**Acceptance criteria:**

- [ ] Separate internal reachability from verified internet exposure.
- [ ] Attach evidence, source, confidence, and `as_of` metadata to findings.
- [ ] Return `unknown`/`stale` rather than `safe` when the knowledge source is
      unavailable or older than its supported freshness window.
- [ ] Replace banner-only CVE claims with a maintained source and
      package/vendor-aware version logic, or label them as unverified leads.
- [ ] Validate TLS chain/hostname, IP SANs, signature algorithms, protocol
      support, and weak supported ciphers with explicit test fixtures.
- [ ] Replace fixed CMS and firmware thresholds with maintained feeds or a
      documented, tested manual update process that fails closed on staleness.
- [ ] Add correctness tests for version edge cases, stale feeds, internal scan
      context, TLS fixtures, and unsupported models.

**Required focused test:** `tests/test_security_data_freshness.py`

## Final verification gate

- [ ] Every row in the tracking table has a commit or PR reference.
- [ ] Every acceptance criterion is checked or has an explicitly approved,
      documented exception.
- [ ] All focused tests named above pass.
- [ ] Full `pytest -q` passes.
- [ ] `scripts/lint_budget.py` passes without increasing the debt budget.
- [ ] Security-sensitive changes receive an adversarial review before release.
