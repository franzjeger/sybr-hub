"""Section 18/19 — Identity Security: Risky Users, PIM, Audit Logs, Defender,
Purview Labels, Break-Glass Checks, and Access Reviews."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

_HIGH_SEVERITY = {"high", "critical"}


class IdentitySecuritySection(BaseSection):
    name = "Identity Security"

    def __init__(
        self,
        out_dir: Path,
        graph: GraphClient,
        global_admin_ids: Optional[list[str]] = None,
        mfa_users: Optional[dict[str, list[str]]] = None,
        ca_exclusions: Optional[set[str]] = None,
        progress_cb=None,
    ):
        super().__init__(out_dir, progress_cb)
        self.graph             = graph
        self.global_admin_ids  = global_admin_ids or []
        self.mfa_users         = mfa_users or {}         # upn -> methods list
        self.ca_exclusions     = ca_exclusions or set()  # user IDs excluded from ALL CA

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
                _safe(self._collect_sensitivity_labels()),
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
            if any(k in err_str for k in ("400", "403", "Bad Request", "Forbidden")):
                lines = [
                    "=" * 90,
                    "  RISKY USERS  (not available)",
                    "=" * 90,
                    "",
                    "  Risky Users requires Microsoft Entra ID P2 (formerly Azure AD Premium P2).",
                    "  This tenant may not have the required license, or the API permissions",
                    "  may be insufficient.",
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
            if any(k in err for k in ("400", "403", "Forbidden", "Bad Request")):
                self._save(
                    "18d_risk_detections.txt",
                    "Risk detections krever Microsoft Entra ID P2 (tidligere Azure AD Premium P2).\n"
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
            self._warn(f"{len(high)} high/critical risk detection(s) found")

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
        try:
            data = await self.graph.get("policies/crossTenantAccessPolicy")
        except Exception as ex:
            self._save("18c_cross_tenant_access_policy.txt", f"Error: {ex}\n")
            self._warn(f"Cross-tenant access policy fetch failed: {ex}")
            return

        default = data.get("default", {})
        b2b_in  = default.get("b2bCollaborationInbound", {})
        b2b_out = default.get("b2bCollaborationOutbound", {})

        lines = [
            "=" * 70,
            "  CROSS-TENANT ACCESS POLICY",
            "=" * 70,
            "  Default Settings:",
            f"    B2B Collab Inbound  : {b2b_in.get('usersAndGroups', {}).get('accessType', 'N/A')}",
            f"    B2B Collab Outbound : {b2b_out.get('usersAndGroups', {}).get('accessType', 'N/A')}",
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
            init_by  = a.get("initiatedBy") or {}
            user     = init_by.get("user") or {}
            actor    = user.get("userPrincipalName") or user.get("displayName") or "(system)"
            lines.append(f"  {ts:<22} {activity:<45} {result:<12} {actor}")
        lines += ["=" * 110, ""]
        self._save("19_entra_audit_log_admin_activity.txt", "\n".join(lines))

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

    # ── Sensitivity Labels ────────────────────────────────────────────────────

    async def _collect_sensitivity_labels(self) -> None:
        try:
            labels = await self.graph.get_all(
                "security/informationProtection/sensitivityLabels",
                beta=True,
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save("19c_purview_sensitivity_labels.txt", f"Error: {ex}\n")
            self._warn(f"Sensitivity labels fetch failed: {ex}")
            return

        lines = [
            "=" * 90,
            f"  PURVIEW SENSITIVITY LABELS  ({len(labels)} total)",
            "=" * 90,
            f"  {'Label Name':<45} {'Priority':>9} {'Enabled':>8} {'Parent ID'}",
            "  " + "-" * 86,
        ]
        for lbl in labels:
            name     = (lbl.get("name") or "")[:45]
            priority = lbl.get("priority", 0)
            enabled  = "Yes" if lbl.get("isActive") else "No"
            parent   = lbl.get("parent", {}).get("id") or "(top-level)"
            lines.append(f"  {name:<45} {priority:>9} {enabled:>8}  {parent}")
        lines += ["=" * 90, ""]
        self._save("19c_purview_sensitivity_labels.txt", "\n".join(lines))

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
            f"  {'User ID':<40} {'MFA Registered':>15} {'CA Excluded':>12}  Notes",
            "  " + "-" * 86,
        ]

        for uid in self.global_admin_ids:
            # Try to look up MFA methods
            try:
                meth_data = await self.graph.get(
                    f"users/{uid}/authentication/methods"
                )
                methods = [
                    m for m in meth_data.get("value", [])
                    if m.get("@odata.type")
                    != "#microsoft.graph.passwordAuthenticationMethod"
                ]
                has_mfa = bool(methods)
            except Exception:
                has_mfa = None  # unknown

            ca_excluded = uid in self.ca_exclusions
            mfa_str     = "Yes" if has_mfa else ("Unknown" if has_mfa is None else "NO")
            ca_str      = "Yes" if ca_excluded else "No"
            notes       = []
            if not has_mfa and has_mfa is not None:
                notes.append("No MFA — potential break-glass")
            if ca_excluded:
                notes.append("Excluded from CA — confirmed break-glass candidate")
            lines.append(
                f"  {uid:<40} {mfa_str:>15} {ca_str:>12}  {'; '.join(notes)}"
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
