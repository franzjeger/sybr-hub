"""Section 16 — Microsoft Teams: Teams list, Settings, External Access."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class TeamsSection(BaseSection):
    name = "Microsoft Teams"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_teams()
            await self._collect_teamwork_settings()
            await self._collect_external_access()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Teams list ────────────────────────────────────────────────────────────

    async def _collect_teams(self) -> None:
        try:
            teams = await self.graph.get_all(
                "groups",
                params={
                    "$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')",
                    "$top":    "999",
                },
            )
        except Exception as ex:
            self._save("16_teams.txt", f"Error: {ex}\n")
            self._warn(f"Teams list fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            f"  MICROSOFT TEAMS  ({len(teams)} total)",
            "=" * 100,
            f"  {'Team Name':<50} {'Visibility':<15} {'Mail':<40} {'Created'}",
            "  " + "-" * 96,
        ]
        for t in teams:
            name       = (t.get("displayName") or "")[:50]
            visibility = (t.get("visibility") or "N/A")[:15]
            mail       = (t.get("mail") or "")[:40]
            created    = (t.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {visibility:<15} {mail:<40} {created}")
        lines += ["=" * 100, ""]
        self._save("16_teams.txt", "\n".join(lines))

    # ── Teamwork Settings (beta) ──────────────────────────────────────────────

    async def _collect_teamwork_settings(self) -> None:
        try:
            data = await self.graph.get("teamwork", beta=True)
        except Exception as ex:
            self._save("16b_teams_settings.txt", f"Error: {ex}\n")
            self._warn(f"Teamwork settings fetch failed: {ex}")
            return

        def fmt_bool(val) -> str:
            if val is None:
                return "N/A"
            return "Enabled" if val else "Disabled"

        msg_settings   = data.get("messagingSettings", {})
        calling        = data.get("isSkypeForBusinessInteropEnabled")

        lines = [
            "=" * 70,
            "  TEAMS SETTINGS (via teamwork endpoint)",
            "=" * 70,
            f"  SfB Interop Enabled             : {fmt_bool(calling)}",
            "",
            "  Messaging Settings:",
            f"    Allow User Edit Messages       : {fmt_bool(msg_settings.get('allowUserEditMessages'))}",
            f"    Allow User Delete Messages     : {fmt_bool(msg_settings.get('allowUserDeleteMessages'))}",
            f"    Allow Owner Delete Messages    : {fmt_bool(msg_settings.get('allowOwnerDeleteMessages'))}",
            f"    Allow Teams Mentions           : {fmt_bool(msg_settings.get('allowTeamMentions'))}",
            f"    Allow Channel Mentions         : {fmt_bool(msg_settings.get('allowChannelMentions'))}",
            "=" * 70,
            "",
        ]
        self._save("16b_teams_settings.txt", "\n".join(lines))

    # ── Cross-Tenant / External Access (beta) ────────────────────────────────

    async def _collect_external_access(self) -> None:
        try:
            data = await self.graph.get("policies/crossTenantAccessPolicy", beta=True)
        except Exception as ex:
            self._save("16c_teams_external_access.txt", f"Error: {ex}\n")
            self._warn(f"Cross-tenant access policy fetch failed: {ex}")
            return

        default   = data.get("default", {})
        b2b_collab  = default.get("b2bCollaborationInbound", {})
        b2b_direct  = default.get("b2bDirectConnectInbound", {})

        lines = [
            "=" * 70,
            "  TEAMS / CROSS-TENANT EXTERNAL ACCESS POLICY",
            "=" * 70,
            "  Default Inbound Settings:",
            f"    B2B Collaboration  : {b2b_collab.get('usersAndGroups', {}).get('accessType', 'N/A')}",
            f"    B2B Direct Connect : {b2b_direct.get('usersAndGroups', {}).get('accessType', 'N/A')}",
            "",
        ]

        partner_configs = data.get("partnerConfigurations", {}).get("value", [])
        if partner_configs:
            lines.append(f"  Partner Configurations ({len(partner_configs)}):")
            for pc in partner_configs:
                tenant_id = pc.get("tenantId", "N/A")
                in_type   = (
                    pc.get("b2bCollaborationInbound", {})
                    .get("usersAndGroups", {})
                    .get("accessType", "N/A")
                )
                lines.append(f"    Tenant {tenant_id} — inbound: {in_type}")
        else:
            lines.append("  Partner Configurations: (none)")

        lines += ["=" * 70, ""]
        self._save("16c_teams_external_access.txt", "\n".join(lines))
