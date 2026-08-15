"""Section 18/19 — Identity Security: Risky Users, PIM, Audit Logs, Defender,
Break-Glass Checks, and Access Reviews.

Purview sensitivity labels (19c) used to be collected here too; they now live
in exchange.py alongside the other two Purview outputs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

_HIGH_SEVERITY = {"high", "critical"}

# Audit-log failure analysis (F12): audit results that count as a failure, and
# how many repeats of one (activity, actor) in the window make it a finding.
_FAILURE_RESULTS = {"failure", "timeout"}
_FAILURE_GROUP_THRESHOLD = 5


def _audit_actor(entry: dict) -> str:
    """Who initiated an audit event — a user OR an app/service principal.

    Directory-audit events raised by an application (a stuck integration, an OAuth
    consent flow, the auditor's own tooling — precisely what the repeated-failure
    analysis targets) carry initiatedBy.app with a null initiatedBy.user. Reading
    only .user collapses every app to "(system)", which both mis-attributes the
    culprit and lets unrelated apps' failures aggregate under one bucket and cross
    the repeat threshold (M365 review follow-up).
    """
    init_by = entry.get("initiatedBy") or {}
    user = init_by.get("user") or {}
    actor = user.get("userPrincipalName") or user.get("displayName")
    if actor:
        return actor
    app = init_by.get("app") or {}
    return (app.get("displayName") or app.get("servicePrincipalName")
            or app.get("appId") or "(system)")


def _unavailable_reason(ex: Exception, tier: str) -> str:
    """Explain a refused premium-gated collection, without guessing.

    These endpoints are gated on the tenant's Entra ID tier *and* on a Graph
    permission, and Graph answers both with 403. The previous text hedged
    across the two — "may not have the license, or the API permissions may be
    insufficient" — which leaves the technician to try both and tells the
    customer nothing. GraphPermissionError now reads the error code out of the
    response, so when the tenant has said which it is, say it.
    """
    if isinstance(ex, GraphPermissionError) and ex.is_licence_gap:
        return (
            f"  Graph reported a licence gap: this tenant does not have {tier},\n"
            f"  which this data requires."
        )
    if isinstance(ex, GraphPermissionError):
        return (
            f"  Graph refused the request with {ex.status} without citing a licence,\n"
            "  so the app registration is missing a permission or its admin consent.\n"
            f"  Note that the endpoint also requires {tier}."
        )
    return (
        f"  The request failed. This data requires {tier}; the tenant may not have\n"
        "  it, or the app registration may be missing a permission."
    )


class IdentitySecuritySection(BaseSection):
    name = "Identity Security"

    def __init__(
        self,
        out_dir: Path,
        graph: GraphClient,
        *,
        global_admin_ids: Optional[list[str]] = None,
        mfa_users: Optional[dict[str, list[str]]] = None,
        ca_exclusions: Optional[set[str]] = None,
        users_ref: list[dict] | None = None,
        ca_section=None,
        mfa_analysis_ran=None,
        progress_cb=None,
    ):
        # Keyword-only past graph. The collector used to pass progress_cb third,
        # which landed it in global_admin_ids: a function is truthy, so the
        # "no admin ids, skip" guard let it through and the loop below raised
        # "'function' object is not iterable" — the break-glass check had never
        # once run, and the section reported no progress either. A positional
        # slip here is silent; making it a TypeError is the point.
        super().__init__(out_dir, progress_cb)
        self.graph             = graph
        # `is not None`, not `or`: the collector passes AdminRolesSection's
        # global_admin_ids list by reference, and it is *empty* at construction
        # (AdminRolesSection populates it in place when it runs, earlier in the
        # sequence). `global_admin_ids or []` replaced that shared, soon-to-be-
        # filled list with a fresh empty one, so the break-glass check read zero
        # admins and skipped itself — a tool bug wearing the clothes of a data
        # gap. Keep the reference so the later appends are visible here.
        self.global_admin_ids  = global_admin_ids if global_admin_ids is not None else []
        self.mfa_users         = mfa_users if mfa_users is not None else {}   # upn -> methods
        self.ca_exclusions     = ca_exclusions if ca_exclusions is not None else set()
        # Shared by reference (both empty at construction, filled when their
        # owning sections run earlier): a directory user list for GUID→UPN
        # display, and the CA section so "were exclusions collected?" is a real
        # question (CA has policies) rather than "is the set empty?" (F8).
        self._users_ref        = users_ref if users_ref is not None else []
        self._ca_section       = ca_section
        # The CA-exclusion SET is derived and populated by the MFA section, not
        # by the CA section — so "policies were collected" is not enough to trust
        # an empty exclusion set as "nobody is excluded". This callable, read at
        # break-glass time, reports whether the MFA section actually ran its
        # exclusion analysis; without it (e.g. MFA Methods deselected, or the MFA
        # section raised) the set is a stale empty and exclusions are UNKNOWN, not
        # clean. None means "assume it ran" for direct construction in tests.
        self._mfa_analysis_ran = mfa_analysis_ran

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)

        async def _safe(coro):
            try:
                await coro
            except Exception as e:
                self._warn(f"Feil ved datainnhenting: {e}")

        try:
            await asyncio.gather(
                _safe(self._collect_risky_users()),
                _safe(self._collect_risk_detections()),
                _safe(self._collect_external_collaboration()),
                _safe(self._collect_cross_tenant_policy()),
                _safe(self._collect_pim_eligible()),
                _safe(self._collect_directory_audits()),
                _safe(self._collect_defender_alerts()),
                _safe(self._collect_break_glass()),
                _safe(self._collect_access_reviews()),
            )
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Risky Users ───────────────────────────────────────────────────────────

    async def _collect_risky_users(self) -> None:
        try:
            users = await self.graph.get_all("riskyUsers")
        except Exception as ex:
            err_str = str(ex)
            if isinstance(ex, GraphPermissionError) or any(
                k in err_str for k in ("400", "403", "Bad Request", "Forbidden")
            ):
                lines = [
                    "=" * 90,
                    "  RISKY USERS  (not available)",
                    "=" * 90,
                    "",
                    "  Risky Users requires Microsoft Entra ID P2 (formerly Azure AD Premium P2).",
                    _unavailable_reason(ex, "Microsoft Entra ID P2"),
                    "",
                    "  Error details for troubleshooting:",
                    f"    {err_str}",
                    "",
                    "=" * 90,
                    "",
                ]
                self._save("18_risky_users.txt", "\n".join(lines))
            else:
                self._save("18_risky_users.txt", f"Error: {ex}\n")
                self._warn(f"Risky users fetch failed (unexpected): {ex}")
            return

        lines = [
            "=" * 90,
            f"  RISKY USERS  ({len(users)} total)",
            "=" * 90,
            f"  {'UPN':<50} {'Risk Level':<15} {'Risk State':<20} {'Last Updated'}",
            "  " + "-" * 86,
        ]
        for u in users:
            upn     = (u.get("userPrincipalName") or "")[:50]
            level   = (u.get("riskLevel") or "none")[:15]
            state   = (u.get("riskState") or "none")[:20]
            updated = (u.get("riskLastUpdatedDateTime") or "N/A")[:19]
            lines.append(f"  {upn:<50} {level:<15} {state:<20} {updated}")
        lines += ["=" * 90, ""]
        self._save("18_risky_users.txt", "\n".join(lines))

    # ── Risk Detections ─────────────────────────────────────────────────────

    async def _collect_risk_detections(self) -> None:
        """Fetch risk detection events showing WHY users are flagged."""
        try:
            detections = await self.graph.get_all(
                "identityProtection/riskDetections",
                params={
                    "$top": "100",
                    "$orderby": "detectedDateTime desc",
                },
            )
        except Exception as ex:
            err = str(ex)
            if isinstance(ex, GraphPermissionError) or any(
                k in err for k in ("400", "403", "Forbidden", "Bad Request")
            ):
                self._save(
                    "18d_risk_detections.txt",
                    "RISK DETECTIONS  (not available)\n"
                    "Risk detections krever Microsoft Entra ID P2 (tidligere Azure AD Premium P2).\n"
                    f"{_unavailable_reason(ex, 'Microsoft Entra ID P2')}\n"
                    f"Teknisk detalj: {err}\n",
                )
            else:
                self._save("18d_risk_detections.txt", f"Error: {ex}\n")
                self._warn(f"Risk detections fetch failed (unexpected): {ex}")
            return

        lines = [
            "=" * 120,
            f"  RISK DETECTIONS  ({len(detections)} events)",
            "=" * 120,
            f"  {'User':<40} {'Risk Type':<35} {'Level':<10} {'State':<15} {'Detected'}",
            "  " + "-" * 116,
        ]

        for d in detections:
            user = (d.get("userDisplayName") or d.get("userPrincipalName") or "")[:40]
            risk_type = (d.get("riskEventType") or d.get("riskType") or "")[:35]
            level = (d.get("riskLevel") or "")[:10]
            state = (d.get("riskState") or "")[:15]
            detected = (d.get("detectedDateTime") or "")[:19]
            lines.append(f"  {user:<40} {risk_type:<35} {level:<10} {state:<15} {detected}")

        lines += ["=" * 120, ""]
        self._save("18d_risk_detections.txt", "\n".join(lines))

        # Warn on high/critical detections
        high = [d for d in detections if d.get("riskLevel") in ("high", "critical")]
        if high:
            self._warn(f"{len(high)} high/critical risk detection(s) found",
                       level="critical")

    # ── External Collaboration ────────────────────────────────────────────────

    async def _collect_external_collaboration(self) -> None:
        try:
            data = await self.graph.get("policies/authorizationPolicy")
        except Exception as ex:
            self._save("18b_external_collaboration_settings.txt", f"Error: {ex}\n")
            self._warn(f"Authorization policy fetch failed: {ex}")
            return

        guest_invite = data.get("allowInvitesFrom", "N/A")
        guest_access = data.get("guestUserRoleId", "N/A")

        lines = [
            "=" * 70,
            "  EXTERNAL COLLABORATION SETTINGS (Authorization Policy)",
            "=" * 70,
            f"  Allow Invites From       : {guest_invite}",
            f"  Guest User Role ID       : {guest_access}",
            f"  Default User Role        : {data.get('defaultUserRolePermissions', {}).get('allowedToCreateApps', 'N/A')}",
            f"  Allow User Consent       : {data.get('allowedToSignUpEmailBasedSubscriptions', 'N/A')}",
            "=" * 70,
            "",
        ]
        self._save("18b_external_collaboration_settings.txt", "\n".join(lines))

    # ── Cross-Tenant Access Policy ────────────────────────────────────────────

    async def _collect_cross_tenant_policy(self) -> None:
        # "default" is a relationship on crossTenantAccessPolicy, not a
        # property of it: a GET on the policy itself returns only displayName
        # and allowedCloudEndpoints. Reading data["default"] therefore found
        # nothing on every tenant, and both settings below have been "N/A"
        # since they were written — which reads as "not configured" rather than
        # "never fetched". The configuration lives on its own endpoint.
        try:
            default = await self.graph.get("policies/crossTenantAccessPolicy/default")
        except Exception as ex:
            self._save("18c_cross_tenant_access_policy.txt", f"Error: {ex}\n")
            self._warn(f"Cross-tenant access policy fetch failed: {ex}")
            return

        b2b_in  = default.get("b2bCollaborationInbound") or {}
        b2b_out = default.get("b2bCollaborationOutbound") or {}
        dc_in   = default.get("b2bDirectConnectInbound") or {}

        def access(setting: dict) -> str:
            value = (setting.get("usersAndGroups") or {}).get("accessType")
            return "N/A" if value is None else str(value)

        is_default = default.get("isServiceDefault")
        lines = [
            "=" * 70,
            "  CROSS-TENANT ACCESS POLICY",
            "=" * 70,
            "  Default Settings:",
            f"    B2B Collab Inbound     : {access(b2b_in)}",
            f"    B2B Collab Outbound    : {access(b2b_out)}",
            f"    B2B Direct Connect In  : {access(dc_in)}",
            f"    System Default         : "
            f"{'N/A' if is_default is None else str(is_default).lower()}",
            "=" * 70,
            "",
        ]
        self._save("18c_cross_tenant_access_policy.txt", "\n".join(lines))

    # ── PIM Eligible Assignments ──────────────────────────────────────────────

    async def _collect_pim_eligible(self) -> None:
        try:
            assignments = await self.graph.get_all(
                "roleManagement/directory/roleEligibilitySchedules",
                params={"$expand": "principal,roleDefinition"},
            )
        except Exception as ex:
            self._save("07b_pim_eligible_assignments.txt", f"Error: {ex}\n")
            self._warn(f"PIM eligible assignments fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            f"  PIM ELIGIBLE ROLE ASSIGNMENTS  ({len(assignments)} total)",
            "=" * 100,
            f"  {'Role':<45} {'Principal':<40} {'Type':<15} Expiry",
            "  " + "-" * 96,
        ]
        for a in assignments:
            role_def  = a.get("roleDefinition") or {}
            principal = a.get("principal") or {}
            role_name = (role_def.get("displayName") or "")[:45]
            prin_name = (
                principal.get("displayName")
                or principal.get("userPrincipalName")
                or ""
            )[:40]
            prin_type = (principal.get("@odata.type") or "").split(".")[-1][:15]
            schedule  = a.get("scheduleInfo") or {}
            expiry    = (schedule.get("expiration") or {}).get("endDateTime") or "Permanent"
            lines.append(f"  {role_name:<45} {prin_name:<40} {prin_type:<15} {expiry}")
        lines += ["=" * 100, ""]
        self._save("07b_pim_eligible_assignments.txt", "\n".join(lines))

    # ── Directory Audits ──────────────────────────────────────────────────────

    async def _collect_directory_audits(self) -> None:
        since = (
            datetime.now(timezone.utc) - timedelta(days=14)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            audits = await self.graph.get_all(
                "auditLogs/directoryAudits",
                params={
                    "$filter": f"activityDateTime ge {since}",
                    "$top":    "999",
                },
            )
        except Exception as ex:
            self._save("19_entra_audit_log_admin_activity.txt", f"Error: {ex}\n")
            self._warn(f"Entra directory audit log fetch failed: {ex}")
            return

        lines = [
            "=" * 110,
            f"  ENTRA DIRECTORY AUDIT LOG  (last 14 days — {len(audits)} events)",
            "=" * 110,
            f"  {'Timestamp':<22} {'Activity':<45} {'Result':<12} {'Initiated By'}",
            "  " + "-" * 106,
        ]
        for a in audits:
            ts       = (a.get("activityDateTime") or "")[:19]
            activity = (a.get("activityDisplayName") or "")[:45]
            result   = (a.get("result") or "")[:12]
            actor    = _audit_actor(a)
            lines.append(f"  {ts:<22} {activity:<45} {result:<12} {actor}")
        lines += ["=" * 110, ""]
        self._save("19_entra_audit_log_admin_activity.txt", "\n".join(lines))

        # A dump nobody scrolls hides a pattern that is itself a finding: the
        # same operation failing repeatedly from one actor all week — a stuck
        # integration, a misconfigured app, or a technician's tool failing
        # against this tenant (e.g. repeated delegated-permission-grant failures
        # = our own tooling failing OAuth consent). Surface it (M365 review, F12).
        self._analyse_audit_failures(audits)

    def _analyse_audit_failures(self, audits: list[dict]) -> None:
        from collections import Counter

        groups: Counter = Counter()
        for a in audits:
            if (a.get("result") or "").strip().lower() not in _FAILURE_RESULTS:
                continue
            activity = (a.get("activityDisplayName") or "").strip()
            actor = _audit_actor(a)
            groups[(activity, actor)] += 1

        repeated = sorted(
            ((n, act, actor) for (act, actor), n in groups.items()
             if n >= _FAILURE_GROUP_THRESHOLD),
            reverse=True,
        )
        if not repeated:
            return

        lines = [
            "=" * 110,
            "  REPEATED AUDIT-LOG FAILURES (last 14 days)",
            "=" * 110,
            "  The same operation failing repeatedly from one actor is a signal in",
            "  its own right — a stuck integration, a misconfigured app, or a",
            "  technician's tool failing against this tenant.",
            "",
            f"  {'Count':>6}  {'Activity':<50} {'Actor'}",
            "  " + "-" * 100,
        ]
        lines += [f"  {n:>6}  {act[:50]:<50} {actor}" for n, act, actor in repeated]
        lines += ["=" * 110, ""]
        self._save("19b_entra_audit_log_failures_WARN.txt", "\n".join(lines))

        top_n, top_act, top_actor = repeated[0]
        self._warn(
            f"{len(repeated)} operation(s) failed repeatedly in the audit log "
            f"(e.g. '{top_act}' x{top_n} by {top_actor}) — investigate a stuck "
            "integration or a tool failing against this tenant",
        )

    # ── Defender Alerts ───────────────────────────────────────────────────────

    async def _collect_defender_alerts(self) -> None:
        try:
            alerts = await self.graph.get_all(
                "security/alerts_v2",
                params={
                    "$filter": "status ne 'resolved'",
                    "$top":    "100",
                },
            )
        except Exception as ex:
            self._save("19b_defender_active_alerts.txt", f"Error: {ex}\n")
            self._save("19b_defender_alert_count.txt", f"Error: {ex}\n")
            self._warn(f"Defender alerts fetch failed: {ex}")
            return

        sev_counts: dict[str, int] = {}
        lines = [
            "=" * 110,
            f"  DEFENDER ACTIVE ALERTS  ({len(alerts)} unresolved)",
            "=" * 110,
            f"  {'Alert Title':<50} {'Severity':<12} {'Status':<15} {'Created'}",
            "  " + "-" * 106,
        ]
        for a in alerts:
            title    = (a.get("title") or "")[:50]
            severity = (a.get("severity") or "unknown")
            status   = (a.get("status") or "")[:15]
            created  = (a.get("createdDateTime") or "N/A")[:19]
            sev_counts[severity] = sev_counts.get(severity, 0) + 1
            lines.append(f"  {title:<50} {severity:<12} {status:<15} {created}")
        lines += ["=" * 110, ""]
        self._save("19b_defender_active_alerts.txt", "\n".join(lines))

        # Count summary
        count_lines = ["=" * 40, "  DEFENDER ALERT COUNT BY SEVERITY", "=" * 40]
        for sev, cnt in sorted(sev_counts.items()):
            count_lines.append(f"  {sev:<15} : {cnt}")
        count_lines += ["=" * 40, ""]
        self._save("19b_defender_alert_count.txt", "\n".join(count_lines))

        for sev in _HIGH_SEVERITY:
            if sev_counts.get(sev, 0) > 0:
                self._warn(
                    f"{sev_counts[sev]} {sev}-severity Defender alert(s) are unresolved"
                )

    # ── Break-Glass / Emergency Access Check ──────────────────────────────────

    async def _collect_break_glass(self) -> None:
        """
        Check Global Admins to see if any are:
          - not registered for MFA, OR
          - excluded from all CA policies (i.e. present in self.ca_exclusions)
        """
        lines = [
            "=" * 90,
            "  EMERGENCY / BREAK-GLASS ACCOUNT CHECK",
            "=" * 90,
        ]

        if not self.global_admin_ids:
            lines += [
                "  No Global Admin IDs provided — skipping check.",
                "  (Pass global_admin_ids when constructing this section for full check.)",
                "=" * 90,
                "",
            ]
            self._save("07c_emergency_access_check.txt", "\n".join(lines))
            return

        lines += [
            f"  {'User (UPN)':<45} {'MFA Registered':>15} {'CA Excluded':>12}  Notes",
            "  " + "-" * 90,
        ]

        by_id = {u.get("id"): u for u in self._users_ref if u.get("id")}
        # CA exclusions are *known* only when we actually have the exclusion data:
        # the CA section collected policies AND the MFA section ran the analysis
        # that derives the exclusion set (it owns self.ca_exclusions). An empty
        # set on a tenant with CA policies means "no admin is excluded" — a clean
        # answer — ONLY if that analysis ran; if it did not (MFA Methods
        # deselected, or the MFA section raised), the set is a stale empty and
        # "excluded: No" would assert a clean negative over data never gathered.
        mfa_ran = self._mfa_analysis_ran is None or bool(self._mfa_analysis_ran())
        ca_known = bool(getattr(self._ca_section, "policies", None)) and mfa_ran

        candidates = 0
        for uid in self.global_admin_ids:
            # Try to look up MFA methods
            try:
                meth_data = await self.graph.get(
                    f"users/{uid}/authentication/methods"
                )
                if isinstance(meth_data, dict) and meth_data.get("error") in (401, 403):
                    # A permission refusal is not "no MFA". Counting it as NO
                    # would flag a break-glass account we never actually read.
                    has_mfa = None  # unknown
                else:
                    methods = [
                        m for m in meth_data.get("value", [])
                        if m.get("@odata.type")
                        != "#microsoft.graph.passwordAuthenticationMethod"
                    ]
                    has_mfa = bool(methods)
            except Exception:
                has_mfa = None  # unknown

            ca_excluded = ca_known and uid in self.ca_exclusions
            if ca_excluded:
                candidates += 1
            mfa_str     = "Yes" if has_mfa else ("Unknown" if has_mfa is None else "NO")
            ca_str      = ("Yes" if ca_excluded else "No") if ca_known else "Unknown"
            notes       = []
            if not has_mfa and has_mfa is not None:
                notes.append("No MFA — potential break-glass")
            if ca_excluded:
                notes.append("Excluded from CA — confirmed break-glass candidate")
            if not ca_known:
                notes.append("CA policies not collected — cannot confirm exclusion")
            user  = by_id.get(uid) or {}
            label = user.get("userPrincipalName") or user.get("displayName") or uid
            lines.append(
                f"  {label[:45]:<45} {mfa_str:>15} {ca_str:>12}  {'; '.join(notes)}"
            )

        # Machine-readable summary for CIS 1.1.6. A genuine break-glass account is
        # a Global Admin *intentionally excluded from Conditional Access* so it
        # survives an MFA/CA outage; that is the count that matters, not "any admin
        # row". ca_exclusions_known tells the report whether to trust a zero as
        # "none configured" (warn) or as "could not verify" (info) — the report
        # must never scrape admin rows and PASS every tenant (M365 review follow-up).
        lines.append(
            f"  SUMMARY: break_glass_candidates={candidates} "
            f"ca_exclusions_known={'yes' if ca_known else 'no'} "
            f"global_admins={len(self.global_admin_ids)}"
        )
        lines += ["=" * 90, ""]
        self._save("07c_emergency_access_check.txt", "\n".join(lines))

    # ── Access Reviews ────────────────────────────────────────────────────────

    async def _collect_access_reviews(self) -> None:
        try:
            reviews = await self.graph.get_all(
                "identityGovernance/accessReviews/definitions",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save("07d_access_reviews.txt", f"Error: {ex}\n")
            self._warn(f"Access review definitions fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            f"  ACCESS REVIEW DEFINITIONS  ({len(reviews)} total)",
            "=" * 100,
            f"  {'Review Name':<50} {'Status':<15} {'Recurrence':<20} {'Created'}",
            "  " + "-" * 96,
        ]
        for r in reviews:
            name   = (r.get("displayName") or "")[:50]
            status = (r.get("status") or "")[:15]
            sched  = r.get("settings", {}).get("recurrence", {})
            pat    = sched.get("pattern", {}).get("type", "once")[:20]
            created = (r.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {status:<15} {pat:<20} {created}")
        lines += ["=" * 100, ""]
        self._save("07d_access_reviews.txt", "\n".join(lines))
