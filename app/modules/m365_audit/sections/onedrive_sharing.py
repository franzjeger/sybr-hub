"""Section 25 — OneDrive External Sharing: Shared files, anonymous links."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class OneDriveSharingSection(BaseSection):
    name = "OneDrive Sharing"

    # ── Scan budget ──────────────────────────────────────────────────────────
    #
    # A recursive walk over every drive in a tenant is unbounded work against
    # someone's live service, so it is bounded here and the bounds are stated
    # in the output. The shape that makes it affordable is $expand=permissions
    # on a folder's children: one request returns every child *with* its
    # permissions, so the cost is one call per folder rather than per item.
    _MAX_DEPTH = 3                  # root = 0; how far down to recurse
    _MAX_FOLDERS_PER_DRIVE = 40     # folders opened in any one drive
    _MAX_REQUESTS = 1500            # whole-section ceiling
    _CONCURRENCY = 5                # matches the SharePoint section

    def __init__(
        self,
        out_dir: Path,
        graph: GraphClient,
        progress_cb=None,
        users_ref: list[dict] | None = None,
        *,
        max_depth: int | None = None,
        max_folders_per_drive: int | None = None,
        max_requests: int | None = None,
    ):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        # Shared by reference with UsersSection, which runs first — the same
        # arrangement MFASection and AdminRolesSection use. Without it, finding
        # every user's OneDrive would mean fetching the directory a second time.
        self._users_ref = users_ref if users_ref is not None else []
        self._max_depth = self._MAX_DEPTH if max_depth is None else max_depth
        self._max_folders = (
            self._MAX_FOLDERS_PER_DRIVE
            if max_folders_per_drive is None
            else max_folders_per_drive
        )
        self._max_requests = self._MAX_REQUESTS if max_requests is None else max_requests

        # Coverage bookkeeping. Every number the report publishes is only as
        # broad as the scan behind it, so the scan has to say how broad it was.
        self._requests = 0
        self._drives_seen = 0
        self._drives_refused = 0
        self._folders_visited = 0
        self._items_examined = 0
        self._truncated: list[str] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_sharing()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Budget ───────────────────────────────────────────────────────────────

    def _spend(self) -> bool:
        """Claim one request from the budget. False when it is exhausted."""
        if self._requests >= self._max_requests:
            if "request budget" not in " ".join(self._truncated):
                self._truncated.append(
                    f"request budget of {self._max_requests} reached"
                )
            return False
        self._requests += 1
        return True

    # ── Drive discovery ──────────────────────────────────────────────────────

    async def _discover_drives(self) -> list[tuple[str, str]]:
        """Return (drive_id, label) for every drive this audit can see.

        The previous implementation asked for ``sites/root/drives`` — the
        document libraries of the *root site* and nothing else. That is not
        OneDrive at all (a user's OneDrive lives under ``users/{id}/drive``)
        and it is not the other site collections either, so a file headed
        "ONEDRIVE / SHAREPOINT EXTERNAL SHARING AUDIT" reporting "Drives
        scanned: 12" was describing one site's libraries.
        """
        drives: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _add(drive: dict, label: str) -> None:
            did = drive.get("id")
            if did and did not in seen:
                seen.add(did)
                drives.append((did, label))

        # Every site collection, the same list the SharePoint section builds.
        sites: list[dict] = []
        if self._spend():
            try:
                sites = await self.graph.get_all(
                    "sites", params={"search": "*", "$top": "999"}
                )
            except Exception as ex:
                self._warn(f"Site enumeration failed, falling back to the root site: {ex}")
        if not sites:
            sites = [{"id": "root", "displayName": "Root site"}]

        sem = asyncio.Semaphore(self._CONCURRENCY)

        async def _site_drives(site: dict) -> tuple[dict, list[dict] | None]:
            site_id = site.get("id") or "root"
            async with sem:
                if not self._spend():
                    return site, None
                try:
                    return site, await self.graph.get_all(
                        f"sites/{site_id}/drives", params={"$top": "999"}
                    )
                except Exception:
                    return site, None

        for site, site_drives in await asyncio.gather(
            *[_site_drives(s) for s in sites]
        ):
            if site_drives is None:
                self._drives_refused += 1
                continue
            label = site.get("displayName") or site.get("name") or site.get("id", "")
            for d in site_drives:
                _add(d, f"{label}/{d.get('name') or d.get('id', '')}")

        # Every user's OneDrive.
        async def _user_drive(user: dict) -> tuple[dict, dict | None]:
            uid = user.get("id")
            if not uid:
                return user, None
            async with sem:
                if not self._spend():
                    return user, None
                try:
                    return user, await self.graph.get(f"users/{uid}/drive")
                except Exception:
                    # A user with no provisioned OneDrive answers 404. That is
                    # not a refusal, and counting it as one would make every
                    # tenant look partially unreadable.
                    return user, None

        users = list(self._users_ref)
        for user, drive in await asyncio.gather(*[_user_drive(u) for u in users]):
            if drive:
                _add(drive, f"OneDrive/{user.get('userPrincipalName') or user.get('id')}")

        if users and self._requests >= self._max_requests:
            self._truncated.append("not every user's OneDrive was located")
        return drives

    # ── Permission walk ──────────────────────────────────────────────────────

    async def _permissions_of_root(self, drive_id: str) -> list[dict] | None:
        if not self._spend():
            return None
        try:
            return await self.graph.get_all(
                f"drives/{drive_id}/root/permissions", params={"$top": "999"}
            )
        except Exception:
            return None

    async def _walk(self, drive_id: str, label: str, collect) -> bool:
        """Walk the drive breadth-first, collecting permissions. False if refused."""
        root_perms = await self._permissions_of_root(drive_id)
        if root_perms is None:
            return False
        for perm in root_perms:
            collect(label, "/", perm)
        self._items_examined += 1

        # (item_id, path, depth); root's children are depth 1.
        queue: list[tuple[str, str, int]] = [("root", "/", 1)]
        folders_opened = 0

        while queue:
            item_id, path, depth = queue.pop(0)
            if depth > self._max_depth:
                self._truncated.append(f"{label}: depth limit {self._max_depth}")
                break
            if folders_opened >= self._max_folders:
                self._truncated.append(f"{label}: folder limit {self._max_folders}")
                break
            if not self._spend():
                break

            try:
                # One request returns every child *with* its permissions, which
                # is what makes walking affordable at all.
                children = await self.graph.get_all(
                    f"drives/{drive_id}/items/{item_id}/children",
                    params={"$top": "200", "$expand": "permissions"},
                )
            except Exception:
                # A single unreadable folder is not an unreadable drive.
                continue

            folders_opened += 1
            self._folders_visited += 1
            for child in children:
                name = child.get("name") or child.get("id", "")
                child_path = f"{path.rstrip('/')}/{name}"
                self._items_examined += 1
                for perm in child.get("permissions") or []:
                    collect(label, child_path, perm)
                if "folder" in child:
                    queue.append((child.get("id", ""), child_path, depth + 1))

        return True

    # ── OneDrive / SharePoint Sharing ────────────────────────────────────────

    async def _collect_sharing(self) -> None:
        try:
            drives = await self._discover_drives()
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

        def collect(drive_name: str, path: str, perm: dict) -> None:
            link_info  = perm.get("link", {}) or {}
            scope      = link_info.get("scope", "") or ""
            perm_type  = link_info.get("type", "") or ""
            granted_to = perm.get("grantedToV2") or perm.get("grantedTo") or {}

            item = {
                "drive_name": drive_name,
                "path":       path,
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

        sem = asyncio.Semaphore(self._CONCURRENCY)

        async def _one(drive_id: str, label: str) -> bool:
            async with sem:
                return await self._walk(drive_id, label, collect)

        for reached in await asyncio.gather(
            *[_one(did, label) for did, label in drives]
        ):
            self._drives_seen += 1
            if not reached:
                self._drives_refused += 1

        complete = not self._truncated and self._drives_refused == 0
        readable = self._drives_seen - self._drives_refused

        # Build output
        lines = [
            "=" * 100,
            "  ONEDRIVE / SHAREPOINT EXTERNAL SHARING AUDIT",
            "=" * 100,
            f"  Drives scanned       : {readable}",
            f"  Total shared items   : {len(all_shared_items)}",
            f"  'Anyone' links       : {len(anyone_links)}",
            f"  External user shares : {len(external_shares)}",
            # State the coverage, because every number above is only as broad
            # as the scan behind it. The compliance control reads these rather
            # than attesting to a clean tenant on a scan that stopped early:
            # "we found none where we looked" is not "this tenant has none".
            f"  Drives refused       : {self._drives_refused}",
            f"  Folders examined     : {self._folders_visited}",
            f"  Items examined       : {self._items_examined}",
            f"  Graph requests used  : {self._requests} of {self._max_requests}",
            f"  Scan scope           : {'complete' if complete else 'partial'} "
            f"(depth {self._max_depth}, max {self._max_folders} folders per drive)",
            "",
        ]
        if self._truncated:
            # Deduplicate but keep order: one line per distinct limit hit.
            seen_notes: list[str] = []
            for note in self._truncated:
                if note not in seen_notes:
                    seen_notes.append(note)
            lines.append("  ── Scan did not complete ──")
            lines += [f"    {n}" for n in seen_notes[:20]]
            if len(seen_notes) > 20:
                lines.append(f"    ... and {len(seen_notes) - 20} more")
            lines.append("")

        if anyone_links:
            lines += [
                "  ── 'Anyone' (Anonymous) Links ──",
                f"  {'Drive':<30} {'Path':<30} {'Type':<12} {'Roles':<12} {'URL'}",
                "  " + "-" * 96,
            ]
            for item in anyone_links:
                lines.append(
                    f"  {item['drive_name'][:30]:<30} {item['path'][:30]:<30} "
                    f"{item['type'][:12]:<12} {', '.join(item['roles'])[:12]:<12} "
                    f"{item['link'][:40]}"
                )
            lines.append("")

        if external_shares:
            lines += [
                "  ── External User Shares ──",
                f"  {'Drive':<30} {'Path':<30} {'Type':<12} {'Roles':<12} {'Granted To'}",
                "  " + "-" * 96,
            ]
            for item in external_shares:
                lines.append(
                    f"  {item['drive_name'][:30]:<30} {item['path'][:30]:<30} "
                    f"{item['type'][:12]:<12} {', '.join(item['roles'])[:12]:<12} "
                    f"{str(item['granted_to'])[:40]}"
                )
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
        if self._drives_refused:
            self._warn(
                f"{self._drives_refused} drive(s) could not be read — the sharing "
                "figures above do not cover them",
                level="info",
            )
        if self._truncated:
            self._warn(
                "The sharing scan hit its limits before finishing, so absence of "
                "anonymous links is not established for the whole tenant",
                level="info",
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
