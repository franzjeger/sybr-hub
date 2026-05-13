"""Section 15 — SharePoint Sites, Settings, and Site Permissions."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient

_WIDE_SHARING = "ExternalUserAndGuestSharing"


class SharePointSection(BaseSection):
    name = "SharePoint"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            sites = await self._collect_sites()
            await self._collect_settings()
            await self._collect_site_permissions(sites)
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Sites ─────────────────────────────────────────────────────────────────

    async def _collect_sites(self) -> list[dict]:
        try:
            sites = await self.graph.get_all(
                "sites",
                params={"search": "*", "$top": "999"},
            )
        except Exception as ex:
            self._save("15_sharepoint_sites.txt", f"Error: {ex}\n")
            self._warn(f"SharePoint sites fetch failed: {ex}")
            return []

        lines = [
            "=" * 110,
            f"  SHAREPOINT SITES  ({len(sites)} total)",
            "=" * 110,
            f"  {'Site Name':<45} {'Web URL':<60} {'Created'}",
            "  " + "-" * 106,
        ]
        for s in sites:
            name    = (s.get("displayName") or s.get("name") or "")[:45]
            url     = (s.get("webUrl") or "")[:60]
            created = (s.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<45} {url:<60} {created}")
        lines += ["=" * 110, ""]
        self._save("15_sharepoint_sites.txt", "\n".join(lines))
        return sites

    # ── Settings ──────────────────────────────────────────────────────────────

    async def _collect_settings(self) -> None:
        try:
            data = await self.graph.get("admin/sharepoint/settings")
        except Exception as ex:
            self._save("15b_sharepoint_settings.txt", f"Error: {ex}\n")
            self._warn(f"SharePoint admin settings fetch failed: {ex}")
            return

        sharing_cap = data.get("sharingCapability", "N/A")
        lines = [
            "=" * 70,
            "  SHAREPOINT SETTINGS",
            "=" * 70,
            f"  Sharing Capability            : {sharing_cap}",
            f"  Default Sharing Link Type     : {data.get('defaultSharingLinkType', 'N/A')}",
            f"  Default Link Permission       : {data.get('defaultLinkPermission', 'N/A')}",
            f"  Require Accept. Agreement     : {data.get('isRequireAcceptingUserToMatchInvitedUser', 'N/A')}",
            f"  External Sharing Ext. Users   : {data.get('sharingAllowedDomainList', 'N/A')}",
            "=" * 70,
            "",
        ]
        self._save("15b_sharepoint_settings.txt", "\n".join(lines))

        if sharing_cap == _WIDE_SHARING:
            self._warn(
                f"SharePoint sharing capability is set to '{_WIDE_SHARING}' — "
                "external and guest sharing is broadly enabled"
            )

    # ── Site Permissions ──────────────────────────────────────────────────────

    async def _collect_site_permissions(self, sites: list[dict]) -> None:
        lines = [
            "=" * 110,
            "  SHAREPOINT SITE PERMISSIONS (App + Sharing)",
            "=" * 110,
        ]

        sem = asyncio.Semaphore(5)

        async def _fetch_site_data(site):
            site_id = site.get("id", "")

            async with sem:
                # Fetch all three in parallel
                async def _get_app_perms():
                    try:
                        return await self.graph.get_all(
                            f"sites/{site_id}/permissions",
                            params={"$top": "999"},
                        )
                    except Exception:
                        return None

                async def _get_sharing_perms():
                    try:
                        return await self.graph.get_all(
                            f"sites/{site_id}/drive/root/permissions",
                            params={"$top": "999"},
                        )
                    except Exception:
                        return None

                async def _get_sharing_cap():
                    try:
                        site_info = await self.graph.get(f"sites/{site_id}")
                        return site_info.get("sharingCapability")
                    except Exception:
                        return None

                return await asyncio.gather(
                    _get_app_perms(), _get_sharing_perms(), _get_sharing_cap()
                )

        # Fetch data for all sites concurrently (bounded by semaphore)
        site_results = await asyncio.gather(
            *[_fetch_site_data(site) for site in sites]
        )

        for site, (app_perms, sharing_perms, sharing_cap) in zip(sites, site_results):
            site_id   = site.get("id", "")
            site_name = site.get("displayName") or site.get("name") or site_id

            # --- Format output ---
            header = f"\n  Site: {site_name}"
            if sharing_cap:
                header += f"  [sharingCapability: {sharing_cap}]"
            lines.append(header)
            lines.append("  " + "-" * 70)

            # App permissions
            if app_perms is None:
                lines.append("    App permissions: N/A (could not fetch)")
            elif not app_perms:
                lines.append("    App permissions: (none)")
            else:
                lines.append(f"    App permissions ({len(app_perms)}):")
                for perm in app_perms:
                    roles      = ", ".join(perm.get("roles", []))
                    granted_to = perm.get("grantedToV2") or perm.get("grantedTo") or {}
                    app_disp   = (granted_to.get("application") or {}).get("displayName", "")
                    user_disp  = (granted_to.get("user") or {}).get("displayName", "")
                    entity     = app_disp or user_disp or "(group/other)"
                    lines.append(f"      [{roles}]  {entity}")

            # Sharing permissions
            if sharing_perms is None:
                lines.append("    Sharing permissions: N/A (site may not have a drive)")
            elif not sharing_perms:
                lines.append("    Sharing permissions: (none)")
            else:
                lines.append(f"    Sharing permissions ({len(sharing_perms)}):")
                for perm in sharing_perms:
                    roles = ", ".join(perm.get("roles", []))
                    granted_to = perm.get("grantedToV2") or perm.get("grantedTo") or {}
                    app_disp   = (granted_to.get("application") or {}).get("displayName", "")
                    user_disp  = (granted_to.get("user") or {}).get("displayName", "")
                    group_disp = (granted_to.get("group") or {}).get("displayName", "")
                    entity     = app_disp or user_disp or group_disp or "(group/other)"
                    link       = perm.get("link", {})
                    link_type  = link.get("type", "") if link else ""
                    link_scope = link.get("scope", "") if link else ""
                    suffix     = ""
                    if link_type or link_scope:
                        suffix = f"  (link: {link_type}, scope: {link_scope})"
                    lines.append(f"      [{roles}]  {entity}{suffix}")

        lines += ["", "=" * 110, ""]
        self._save("15c_sharepoint_site_access.txt", "\n".join(lines))
