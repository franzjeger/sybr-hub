"""Section 32 — Privileged Identity Management (PIM): Eligible vs Active Roles."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

# Roles that are considered highly privileged
_CRITICAL_ROLES = {
    "Global Administrator",
    "Privileged Role Administrator",
    "Privileged Authentication Administrator",
    "Exchange Administrator",
    "SharePoint Administrator",
    "Security Administrator",
    "User Administrator",
    "Application Administrator",
    "Cloud Application Administrator",
    "Intune Administrator",
    "Conditional Access Administrator",
}

_PERMANENT_WARN_THRESHOLD = 3


class PIMSection(BaseSection):
    name = "Privileged Identity Management"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            eligible = await self._fetch_eligible()
            active   = await self._fetch_active()
            has_p2 = None
            if not eligible and not active:
                # Only when there is nothing to show: decide whether "no PIM
                # data" means the tenant has no P2 (not applicable) or the app
                # is missing a permission (a real gap). The report used to state
                # both causes at once (M365 review, F7).
                has_p2 = await self._has_entra_p2()
            self._build_report(eligible, active, has_p2)
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    async def _has_entra_p2(self) -> bool | None:
        """Whether the tenant is licensed for Entra ID P2 — PIM's prerequisite.

        True/False from subscribedSkus; None if that read failed, so the caller
        keeps the ambiguous wording instead of guessing.
        """
        try:
            skus = await self.graph.get_all("subscribedSkus")
        except Exception:
            return None
        for sku in skus or []:
            for plan in sku.get("servicePlans", []) or []:
                if (plan.get("servicePlanName") == "AAD_PREMIUM_P2"
                        and (plan.get("provisioningStatus") or "").lower() != "disabled"):
                    return True
        return False

    # ── Fetch eligible role assignments ────────────────────────────────────

    async def _fetch_eligible(self) -> list[dict]:
        try:
            return await self.graph.get_all(
                "roleManagement/directory/roleEligibilityScheduleInstances",
                params={"$expand": "principal,roleDefinition"},
            )
        except Exception as ex:
            err = str(ex)
            if any(k in err for k in ("400", "403", "404", "Forbidden", "Bad Request", "Not Found")):
                return []
            raise

    # ── Fetch active (permanent) role assignments ──────────────────────────

    async def _fetch_active(self) -> list[dict]:
        try:
            return await self.graph.get_all(
                "roleManagement/directory/roleAssignmentScheduleInstances",
                params={"$expand": "principal,roleDefinition"},
            )
        except Exception as ex:
            err = str(ex)
            if any(k in err for k in ("400", "403", "404", "Forbidden", "Bad Request", "Not Found")):
                return []
            raise

    # ── Build combined report ──────────────────────────────────────────────

    def _build_report(self, eligible: list[dict], active: list[dict],
                      has_p2: bool | None = None) -> None:
        lines = [
            "=" * 110,
            "  PRIVILEGED IDENTITY MANAGEMENT (PIM) — ROLE ASSIGNMENTS",
            "=" * 110,
        ]

        if not eligible and not active:
            if has_p2 is False:
                lines += [
                    "",
                    "  Not applicable — this tenant has no Microsoft Entra ID P2, which PIM",
                    "  requires. This is a licensing fact, not a finding and not a permission",
                    "  error. Without P2, admin role assignments are permanent by design;",
                    "  time-bound (just-in-time) elevation would need an Entra ID P2 license",
                    "  (e.g. via EMS E5).",
                    "",
                    "=" * 110,
                    "",
                ]
                self._warn(
                    "PIM is not available on this tenant (no Entra ID P2); admin roles are permanent",
                    level="info",
                )
            elif has_p2 is True:
                lines += [
                    "",
                    "  PIM is licensed (Entra ID P2 is present) but no eligible/active role",
                    "  data was returned. The most likely cause is a missing application",
                    "  permission (RoleManagement.Read.Directory), or PIM not being configured.",
                    "  Verify the app's Graph permissions.",
                    "",
                    "=" * 110,
                    "",
                ]
                self._warn("PIM is licensed but returned no data — verify RoleManagement.Read.Directory")
            else:
                lines += [
                    "",
                    "  PIM data not available. Possible reasons:",
                    "  - Tenant does not have Microsoft Entra ID P2 (formerly Azure AD Premium P2) — required for PIM",
                    "  - Service principal lacks RoleManagement.Read.Directory permission",
                    "  - PIM is not configured for this tenant",
                    "",
                    "  NOTE: Without PIM, all admin role assignments are permanent.",
                    "  This is a security risk — consider enabling PIM with Microsoft Entra ID P2.",
                    "",
                    "=" * 110,
                    "",
                ]
                self._warn("PIM data not available — all admin roles may be permanently assigned")
            self._save("32_pim_roles.txt", "\n".join(lines))
            return

        # ── Eligible Assignments ───────────────────────────────────────────

        lines += [
            "",
            f"  ELIGIBLE (Just-In-Time) ASSIGNMENTS  ({len(eligible)} total)",
            "  " + "-" * 106,
            f"  {'Role':<45} {'Principal':<40} {'Type':<15} {'Expiry'}",
            "  " + "-" * 106,
        ]
        for a in eligible:
            role_def  = a.get("roleDefinition") or {}
            principal = a.get("principal") or {}
            role_name = (role_def.get("displayName") or a.get("roleDefinitionId", ""))[:45]
            prin_name = (
                principal.get("displayName")
                or principal.get("userPrincipalName")
                or a.get("principalId", "")
            )[:40]
            prin_type = (principal.get("@odata.type") or "").split(".")[-1][:15]
            end_dt    = a.get("endDateTime") or "No expiry"
            if end_dt != "No expiry":
                end_dt = end_dt[:19]
            lines.append(f"  {role_name:<45} {prin_name:<40} {prin_type:<15} {end_dt}")

        # ── Active (Permanent) Assignments ─────────────────────────────────

        # Classify active assignments: permanent vs time-bound
        permanent = []
        time_bound = []
        for a in active:
            assignment_type = a.get("assignmentType", "")
            end_dt = a.get("endDateTime")
            if assignment_type == "Activated":
                # Currently activated from eligible — this is fine (JIT)
                time_bound.append(a)
            elif end_dt:
                time_bound.append(a)
            else:
                permanent.append(a)

        lines += [
            "",
            f"  ACTIVE ASSIGNMENTS  ({len(active)} total: {len(permanent)} permanent, {len(time_bound)} time-bound/activated)",
            "  " + "-" * 106,
            f"  {'Role':<45} {'Principal':<35} {'Type':<12} {'Assignment':<12} {'End'}",
            "  " + "-" * 106,
        ]
        for a in active:
            role_def  = a.get("roleDefinition") or {}
            principal = a.get("principal") or {}
            role_name = (role_def.get("displayName") or a.get("roleDefinitionId", ""))[:45]
            prin_name = (
                principal.get("displayName")
                or principal.get("userPrincipalName")
                or a.get("principalId", "")
            )[:35]
            prin_type = (principal.get("@odata.type") or "").split(".")[-1][:12]
            assign_type = a.get("assignmentType", "Direct")[:12]
            end_dt = a.get("endDateTime")
            end_str = end_dt[:19] if end_dt else "PERMANENT"
            lines.append(f"  {role_name:<45} {prin_name:<35} {prin_type:<12} {assign_type:<12} {end_str}")

        # ── Summary / Comparison ───────────────────────────────────────────

        lines += [
            "",
            "  " + "=" * 60,
            "  SUMMARY",
            "  " + "=" * 60,
            f"    Eligible (JIT) assignments   : {len(eligible)}",
            f"    Active assignments           : {len(active)}",
            f"      Permanent                  : {len(permanent)}",
            f"      Time-bound / Activated     : {len(time_bound)}",
            "",
        ]

        # Check for permanently assigned critical roles
        perm_critical = []
        for a in permanent:
            role_def = a.get("roleDefinition") or {}
            role_name = role_def.get("displayName") or ""
            if role_name in _CRITICAL_ROLES:
                principal = a.get("principal") or {}
                prin_name = (
                    principal.get("displayName")
                    or principal.get("userPrincipalName")
                    or a.get("principalId", "")
                )
                perm_critical.append((role_name, prin_name))

        if perm_critical:
            lines += [
                "  PERMANENT CRITICAL ROLE ASSIGNMENTS (should be eligible/JIT):",
            ]
            for role_name, prin_name in perm_critical:
                lines.append(f"    - {role_name}: {prin_name}")
            lines.append("")

        lines += ["=" * 110, ""]
        self._save("32_pim_roles.txt", "\n".join(lines))

        # ── Warnings ──────────────────────────────────────────────────────

        if len(permanent) >= _PERMANENT_WARN_THRESHOLD:
            self._warn(
                f"{len(permanent)} permanent role assignment(s) found — "
                f"consider converting to eligible (JIT) via PIM"
            )

        if perm_critical:
            self._warn(
                f"{len(perm_critical)} critical role(s) permanently assigned — "
                f"high-privilege roles should use just-in-time activation"
            )
