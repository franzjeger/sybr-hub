# Sybr HUB — TODO / backlog

Actionable follow-ups, newest thread first. Each item says **what**, **why**,
**where** (files), and **done when** (the test or check that proves it). Pick
from the top; items are roughly ordered by value.

Context — recently merged:
- #166 console cross-tenant RBAC fix · #167 capability UX gating · #168 service
  principal attribution · #169 write-route role floors · #170 hide write menus +
  remove Workshop · #171 shared customer pool · #172 policies-in-production ·
  #173→#174 tiered CA baseline library · #175 friendly names in the report.

---

## 1. Assessment library — "Assess" pillar (Fase B)

Copy the best of Inforcer's *Assess*, cleaner: a browsable library of **named,
scored frameworks** run per customer, each check explained.

The engine already exists — don't rebuild it:
- `app/core/baseline.py::evaluate` runs each **check** against the audit
  context and returns `passed / failed / not_measured` + conformance %.
- Check shape: `{id, title{no,en}, why{no,en}, severity, path (dotted into the
  report context), op (eq/gte/lte/…), value, measured_when (guard)}`.
- `list_baselines()` auto-loads every `app/baselines/*.json`.
- Routes: `GET /api/baselines`, `GET /api/baselines/{id}/evaluate/{customer}/{run}`.
- Today there is one standard, `app/baselines/sybr-standard.json` (9 checks),
  already surfaced on the customer card.

Work items:
1. **Enumerate the available context keys first.** A check whose `path` misses
   a real key is `not_measured` — dead weight. Dump the keys `build_report_context`
   produces (`app/reports/generator.py`), and the paths `sybr-standard.json`
   already uses, into a short reference. *Done when: a listing of measurable
   paths exists (a test or a doc), so new checks can be authored against real data.*
2. **Author Essential 8 — Maturity Level 1** as `app/baselines/essential-8-l1.json`.
   Well-known, bounded (~40 checks at Inforcer). Map each E8 mitigation to a
   measurable context path; leave genuinely unmeasurable ones out rather than
   faking them. *Done when: `/api/baselines` lists it and it scores a real run
   with mostly-measured checks.*
3. **Author CIS Microsoft 365 Foundations (subset)** — the checks we can
   actually measure from the audit (MFA, CA, legacy auth, admin count, secure
   score, external sharing, audit logging). Name it honestly as a subset.
4. **Author NIS2 hardening** — reuse the CIS→NIS2 mapping idea; a curated set of
   the M365 checks that back NIS2 Article 21 measures. State scope limits (it is
   hardening guidance, not a certification).
5. **Library UI**: a browsable list (name, #checks, description, tags), run
   per-customer, results with per-check status + `why` + what to fix. Model on
   the existing customer-card baseline panel (`app.js::_loadCustomerBaselineCard`).
   *Done when: a technician can pick a framework, run it on a customer, and read
   named results — not ids.*

Guardrail: every check must be **measurable or explicitly not** — do not chase a
100% score on advisory frameworks; the engine already quotes conformance over
*assessed* checks and reports the rest as not_measured. Keep that honesty.

---

## 2. Deploy library polish (Fase A follow-through)

The tiered CA library (#174) is a dropdown + description + per-policy checklist.
Inforcer presents baselines as **cards**. Optional polish:
- Render the standard picker as cards (name, tier, #policies, licence, description)
  instead of a `<select>`. `app/web/static/app-policy-deploy.js::_pdForm`.
- *Done when: the deploy view shows a browsable card grid; per-policy selection
  and the plan→apply fingerprint flow are unchanged.*

---

## 3. Policies-in-production — capture more workloads (Fase 2 of #172)

Today the customer card / report capture CA, named locations, Intune compliance
+ config. Extend to the rest — each is one entry in `_WORKLOADS` plus a describe
function in `app/core/policy_inventory.py`:
- **SharePoint sharing settings** — clean Graph read `admin/sharepoint/settings`.
- **External collaboration / guest** — `policies/authorizationPolicy` (the audit
  reads it as text today; capture it as a structured snapshot in
  `app/modules/m365_audit/sections/identity_security.py`).
- **Cross-tenant access** — `policies/crossTenantAccessPolicy/default` (same).
- **Teams** (messaging/meeting/external) and **Viva Engage** — need Teams
  APIs / PowerShell; some not in Graph. Flag as a larger, separate lift; do not
  half-implement.
- *Done when: the new workloads appear in `policies_live.json` and the card/report
  with a plain-language line each.*

---

## 4. Non-CA best-practice deploy (Fase C)

The deploy template format and per-policy selection are workload-agnostic. Add
new baselines as their deploy APIs land:
- **Intune baselines** (compliance + config) — deployable via Graph `POST
  deviceManagement/...`. Natural next step after CA.
- **SharePoint / Teams** — different APIs, higher risk; later.
- **Golden baseline + multi-tenant score board** — a reference tenant/baseline
  and a table scoring every customer against it (Inforcer's Tenants dashboard).
  Builds on the assessment engine (§1).

---

## 5. Residuals flagged during the security / RBAC work

- **Role floor on ~30 `auth-only` write routes** — a *decision*, not a bug.
  `can_write` is granted independently of role (`scripts/grant_write.py`), so a
  **viewer granted `can_write`** can reach `uniweb/*`, `itglue/upload/*`,
  `customers/add-manual|register`, `customer/notes|tags`, `history/delete`,
  `audit/scope|presets`, `workshop/notes`(removed), `ssh/config/generate`, etc.
  If viewers must never hold `can_write`, this is moot; otherwise add
  `require_role(Role.technician)`. *Decide, then act.*
- **`customer_status` console tool** reads the process-global active customer,
  not the caller's scope (`app/services/claude_console.py`). Pre-existing
  active-customer pattern; low risk with the shared pool. Revisit if per-user
  scoping ever matters.
- **`redact.py`** excludes `/` and `+` from the secret-shape regex on purpose
  (so it does not shred file paths in logs). A standard-base64 secret passed
  without a `known` value leaks its tail. Documented tradeoff — leave unless a
  concrete leak shows up.
- **WeasyPrint `default_url_fetcher` deprecation** — the PDF url_fetcher
  (`app/reports/generator.py::_pdf_url_fetcher`) calls `default_url_fetcher`,
  deprecated in WeasyPrint 69. Move to the `URLFetcher` API when WeasyPrint is
  upgraded. Not urgent.

---

## Deploy reminders (for whoever runs Settings → Update now)

- **Migration 19** (shared customer pool) runs at startup and grants
  `all_customers` to every existing account. New accounts default to it.
- **`policies_live.json`** on the customer card fills on the customer's **next
  audit** — it is captured at audit completion, not backfilled.
- The new CA baselines (IAM Core / Device & session / Risk-based) appear in the
  Policy deployment → Standard picker.
