"""Section 25 — OneDrive External Sharing: Shared files, anonymous links."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class OneDriveSharingSection(BaseSection):
    name = "OneDrive Sharing"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_sharing()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── OneDrive / SharePoint Sharing ────────────────────────────────────────

    async def _collect_sharing(self) -> None:
        # Get drives via SharePoint root site
        try:
            drives = await self.graph.get_all(
                "sites/root/drives",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save(
                "25_onedrive_sharing.txt",
                f"Error fetching drives: {ex}\n"
                "Note: This endpoint requires Sites.Read.All or Files.Read.All permissions.\n",
            )
            self._warn(f"OneDrive/SharePoint drives fetch failed: {ex}")
            return

        if not drives:
            self._save("25_onedrive_sharing.txt", "No drives found.\n")
            return

        all_shared_items: list[dict] = []
        anyone_links: list[dict] = []
        external_shares: list[dict] = []

        for drive in drives:
            drive_id   = drive.get("id")
            drive_name = drive.get("name") or drive.get("id", "Unknown")
            if not drive_id:
                continue

            try:
                permissions = await self.graph.get_all(
                    f"drives/{drive_id}/root/permissions",
                    params={"$top": "999"},
                )
            except Exception:
                # 403/404 is expected for drives we don't have access to
                continue

            for perm in permissions:
                link_info  = perm.get("link", {})
                scope      = link_info.get("scope", "")
                perm_type  = link_info.get("type", "")
                granted_to = perm.get("grantedToV2") or perm.get("grantedTo") or {}

                item = {
                    "drive_name": drive_name,
                    "scope":      scope,
                    "type":       perm_type,
                    "roles":      perm.get("roles", []),
                    "granted_to": granted_to,
                    "link":       link_info.get("webUrl", ""),
                }
                all_shared_items.append(item)

                if scope.lower() == "anonymous":
                    anyone_links.append(item)
                elif scope.lower() == "users" and self._is_external(granted_to):
                    external_shares.append(item)

        # Build output
        lines = [
            "=" * 100,
            f"  ONEDRIVE / SHAREPOINT EXTERNAL SHARING AUDIT",
            "=" * 100,
            f"  Drives scanned       : {len(drives)}",
            f"  Total shared items   : {len(all_shared_items)}",
            f"  'Anyone' links       : {len(anyone_links)}",
            f"  External user shares : {len(external_shares)}",
            # State the scope in the file, because the number above is only as
            # broad as the query behind it. This reads drives/{id}/root/
            # permissions — the permissions on the drive root itself. A link
            # shared on a file inside a folder is not visible here, so a zero
            # is "none at the root", not "none in the tenant". The compliance
            # control keys off this line rather than attesting to a clean
            # tenant on a scan that never looked.
            "  Scan scope           : drive roots only (items within folders not enumerated)",
            "",
        ]

        if anyone_links:
            lines += [
                "  ── 'Anyone' (Anonymous) Links ──",
                f"  {'Drive':<30} {'Type':<15} {'Roles':<20} {'URL'}",
                "  " + "-" * 96,
            ]
            for item in anyone_links:
                drive_name = item["drive_name"][:30]
                ptype      = item["type"][:15]
                roles      = ", ".join(item["roles"])[:20]
                url        = item["link"][:40]
                lines.append(f"  {drive_name:<30} {ptype:<15} {roles:<20} {url}")
            lines.append("")

        if external_shares:
            lines += [
                "  ── External User Shares ──",
                f"  {'Drive':<30} {'Type':<15} {'Roles':<20} {'Granted To'}",
                "  " + "-" * 96,
            ]
            for item in external_shares:
                drive_name = item["drive_name"][:30]
                ptype      = item["type"][:15]
                roles      = ", ".join(item["roles"])[:20]
                granted    = str(item["granted_to"])[:40]
                lines.append(f"  {drive_name:<30} {ptype:<15} {roles:<20} {granted}")
            lines.append("")

        if not anyone_links and not external_shares:
            lines.append("  No external sharing or anonymous links detected.")
            lines.append("")

        lines += ["=" * 100, ""]
        self._save("25_onedrive_sharing.txt", "\n".join(lines))

        # Warnings
        if anyone_links:
            self._warn(
                f"{len(anyone_links)} file(s)/folder(s) shared via 'Anyone' (anonymous) links"
            )
        if external_shares:
            self._warn(
                f"{len(external_shares)} file(s)/folder(s) shared with external users"
            )

    @staticmethod
    def _is_external(granted_to: dict) -> bool:
        """Heuristic: check if grantedTo contains an external user."""
        user = granted_to.get("user", {})
        # External users typically have a '#EXT#' in their UPN
        upn = user.get("userPrincipalName", "") or ""
        if "#EXT#" in upn:
            return True
        # Or if the user dict has no id (link shared externally)
        if not user.get("id") and user.get("email"):
            return True
        return False
