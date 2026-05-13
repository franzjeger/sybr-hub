"""Section 30 — Teams Policies: Meeting Policies, Guest Access, External Chat."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class TeamsPoliciesSection(BaseSection):
    name = "Teams Policies"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_meeting_policies()
            await self._collect_guest_access()
            await self._collect_messaging_policies()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Meeting Policies ───────────────────────────────────────────────────

    async def _collect_meeting_policies(self) -> None:
        try:
            data = await self.graph.get(
                "teamwork/teamTemplates",
                beta=True,
            )
        except Exception as e:
            logger.debug("Failed to fetch Teams templates: %s", e)
            data = None

        # Try the primary meeting policy endpoint
        try:
            policies_data = await self.graph.get(
                "teamwork/teamsAppSettings",
                beta=True,
            )
        except Exception as e:
            logger.debug("Failed to fetch Teams app settings: %s", e)
            policies_data = None

        lines = [
            "=" * 90,
            "  TEAMS MEETING POLICIES",
            "=" * 90,
        ]

        if policies_data:
            allow_user_override = policies_data.get("allowUserRequestsForAppAccess", "N/A")
            lines += [
                f"  Allow User App Access Requests  : {allow_user_override}",
                "",
            ]

        # Fetch Teams app permission policies (beta)
        try:
            perm_data = await self.graph.get(
                "teamwork/teamsAppSettings",
                beta=True,
            )
            is_catalog_apps_only = perm_data.get("isChatResourceSpecificConsentEnabled", "N/A")
            lines.append(f"  Chat Resource-Specific Consent  : {is_catalog_apps_only}")
        except Exception as e:
            logger.debug("Failed to fetch Teams app permission policies: %s", e)
            lines.append("  Teams App Settings              : Not available (missing license or permissions)")

        lines += ["=" * 90, ""]
        self._save("30_teams_policies.txt", "\n".join(lines))

    # ── Guest Access Settings ──────────────────────────────────────────────

    async def _collect_guest_access(self) -> None:
        # Check authorization policy for guest settings
        try:
            auth_policy = await self.graph.get("policies/authorizationPolicy")
        except Exception as ex:
            self._save("30b_teams_guest_access.txt", f"Error: {ex}\n")
            self._warn(f"Authorization policy fetch failed: {ex}")
            return

        guest_invite = auth_policy.get("allowInvitesFrom", "N/A")
        guest_role   = auth_policy.get("guestUserRoleId", "N/A")

        # Map known guest role GUIDs to readable names
        _GUEST_ROLES = {
            "a0b1b346-4d3e-4e8b-98f8-753987be4970": "Same as member users",
            "10dae51f-b6af-4016-8d66-8c2a99b929b3": "Limited access (default)",
            "2af84b1e-32c8-42b7-82bc-daa82404023b": "Restricted access (most restrictive)",
        }
        guest_role_name = _GUEST_ROLES.get(guest_role, guest_role)

        # Map invite settings to readable names
        _INVITE_SETTINGS = {
            "everyone":                        "Everyone (most open)",
            "adminsAndGuestInviters":          "Admins and Guest Inviters",
            "adminsGuestInvitersAndAllMembers": "Admins, Guest Inviters, and Members",
            "none":                            "No one (most restrictive)",
        }
        guest_invite_name = _INVITE_SETTINGS.get(guest_invite, guest_invite)

        lines = [
            "=" * 90,
            "  TEAMS / ENTRA ID GUEST ACCESS SETTINGS",
            "=" * 90,
            f"  Allow Invites From       : {guest_invite_name}",
            f"  Guest User Role          : {guest_role_name}",
            "",
        ]

        # Fetch external collaboration settings (cross-tenant)
        try:
            cross_tenant = await self.graph.get(
                "policies/crossTenantAccessPolicy/default", beta=True
            )
            b2b_in  = cross_tenant.get("b2bCollaborationInbound", {})
            b2b_out = cross_tenant.get("b2bCollaborationOutbound", {})
            b2b_direct_in = cross_tenant.get("b2bDirectConnectInbound", {})

            lines += [
                "  Cross-Tenant Defaults:",
                f"    B2B Collab Inbound     : {b2b_in.get('usersAndGroups', {}).get('accessType', 'N/A')}",
                f"    B2B Collab Outbound    : {b2b_out.get('usersAndGroups', {}).get('accessType', 'N/A')}",
                f"    B2B Direct Inbound     : {b2b_direct_in.get('usersAndGroups', {}).get('accessType', 'N/A')}",
                "",
            ]
        except Exception as e:
            logger.debug("Failed to fetch cross-tenant access policy: %s", e)
            lines.append("  Cross-Tenant Defaults    : Not available")
            lines.append("")

        lines += ["=" * 90, ""]
        self._save("30b_teams_guest_access.txt", "\n".join(lines))

        # Warn if guest access is too open
        if guest_invite == "everyone":
            self._warn("Guest invitation policy is set to 'Everyone' — any user can invite guests")
        if guest_role == "a0b1b346-4d3e-4e8b-98f8-753987be4970":
            self._warn("Guest users have same access as member users — consider restricting")

    # ── External / Messaging Policies ──────────────────────────────────────

    async def _collect_messaging_policies(self) -> None:
        try:
            data = await self.graph.get("teamwork", beta=True)
        except Exception as ex:
            self._save("30c_teams_messaging_policies.txt", f"Error: {ex}\n")
            self._warn(f"Teamwork messaging settings fetch failed: {ex}")
            return

        msg = data.get("messagingSettings", {})

        lines = [
            "=" * 90,
            "  TEAMS MESSAGING / COMMUNICATION POLICIES",
            "=" * 90,
        ]

        def fmt(val) -> str:
            if val is None:
                return "N/A"
            return "Enabled" if val else "Disabled"

        lines += [
            f"  Allow User Edit Messages        : {fmt(msg.get('allowUserEditMessages'))}",
            f"  Allow User Delete Messages      : {fmt(msg.get('allowUserDeleteMessages'))}",
            f"  Allow Owner Delete Messages     : {fmt(msg.get('allowOwnerDeleteMessages'))}",
            f"  Allow Team Mentions             : {fmt(msg.get('allowTeamMentions'))}",
            f"  Allow Channel Mentions          : {fmt(msg.get('allowChannelMentions'))}",
            "",
        ]

        # External access / federation
        try:
            fed = await self.graph.get(
                "policies/crossTenantAccessPolicy", beta=True
            )
            partners = fed.get("partners", [])
            if isinstance(partners, dict):
                partners = partners.get("value", [])
            lines += [
                f"  External Federation Partners    : {len(partners)} configured",
            ]
        except Exception as e:
            logger.debug("Failed to fetch external federation partners: %s", e)
            lines.append("  External Federation             : Not available")

        lines += ["=" * 90, ""]
        self._save("30c_teams_messaging_policies.txt", "\n".join(lines))
