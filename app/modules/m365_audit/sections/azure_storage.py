"""Section 35–36 — Azure Storage: Storage Accounts and Managed Disks.

Azure SDK clients are synchronous; dispatched to a thread-pool executor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthManager


def _run_sync(fn):
    return asyncio.get_event_loop().run_in_executor(None, fn)


class AzureStorageSection(BaseSection):
    name = "Azure Storage"

    def __init__(
        self,
        out_dir: Path,
        auth_manager: AuthManager,
        progress_cb=None,
        sub_id: str = "",
        sub_name: str = "",
        multi: bool = False,
    ):
        self.auth = auth_manager
        self._sub_id = sub_id
        self._sub_name = sub_name
        self._multi = multi
        self._sub_prefix = "".join(c if c.isalnum() or c in "-_" else "_" for c in sub_name)[:20] if multi else ""
        super().__init__(out_dir, progress_cb)
        if sub_name:
            self.name = f"Azure Storage ({sub_name})"
            self.result.name = self.name

    def _fname(self, base: str) -> str:
        if not self._sub_prefix:
            return base
        name, ext = base.rsplit(".", 1)
        return f"{name}_{self._sub_prefix}.{ext}"

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)

        if not self._sub_id:
            self._report(SectionStatus.SKIPPED, "No subscription_id configured")
            return self.result

        try:
            await self._collect_storage_accounts()
            await self._collect_managed_disks()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Storage Accounts ──────────────────────────────────────────────────────

    async def _collect_storage_accounts(self) -> None:
        try:
            client   = self.auth.storage_client_for(self._sub_id)
            accounts = await _run_sync(lambda: list(client.storage_accounts.list()))
        except Exception as ex:
            self._save(self._fname("35_azure_storage.txt"), f"Error: {ex}\n")
            return

        sub_label = f"  [{self._sub_name}]" if self._multi else ""
        lines = [
            "=" * 120,
            f"  AZURE STORAGE ACCOUNTS  ({len(accounts)} total){sub_label}",
            "=" * 120,
            f"  {'Account Name':<30} {'SKU':<18} {'Kind':<15} {'Min TLS':<10} "
            f"{'HTTPS Only':>11} {'Pub Blob':>9}  Flags",
            "  " + "-" * 116,
        ]

        for sa in accounts:
            name       = (sa.name or "")[:30]
            sku        = (sa.sku.name if sa.sku else "N/A")[:18]
            kind       = (sa.kind or "N/A")[:15]
            tls        = getattr(sa, "minimum_tls_version", "TLS1_0") or "TLS1_0"
            https_only = getattr(sa, "enable_https_traffic_only", True)
            pub_blob   = getattr(sa, "allow_blob_public_access", False)

            flags: list[str] = []
            if tls < "TLS1_2":
                flags.append("OLD-TLS")
                self._warn(f"Storage '{sa.name}': minimum TLS version is {tls} (below TLS1_2)")
            if not https_only:
                flags.append("HTTP-ALLOWED")
                self._warn(f"Storage '{sa.name}': HTTP traffic is allowed (not HTTPS-only)")
            if pub_blob:
                flags.append("PUBLIC-BLOB")
                self._warn(f"Storage '{sa.name}': public blob access is enabled")

            flag_str   = ", ".join(flags) if flags else "OK"
            https_str  = "Yes" if https_only else "No"
            blob_str   = "Yes" if pub_blob else "No"
            lines.append(
                f"  {name:<30} {sku:<18} {kind:<15} {tls:<10} "
                f"{https_str:>11} {blob_str:>9}  {flag_str}"
            )

        lines += ["=" * 120, ""]
        self._save(self._fname("35_azure_storage.txt"), "\n".join(lines))

    # ── Managed Disks ─────────────────────────────────────────────────────────

    async def _collect_managed_disks(self) -> None:
        try:
            client = self.auth.compute_client_for(self._sub_id)
            disks  = await _run_sync(lambda: list(client.disks.list()))
        except Exception as ex:
            self._save(self._fname("36_azure_disks.txt"), f"Error: {ex}\n")
            return

        unattached: list[str] = []
        lines = [
            "=" * 110,
            f"  AZURE MANAGED DISKS  ({len(disks)} total)",
            "=" * 110,
            f"  {'Disk Name':<40} {'Size (GB)':>10} {'SKU':<20} {'RG':<25} Status",
            "  " + "-" * 106,
        ]

        for disk in disks:
            name     = (disk.name or "")[:40]
            size_gb  = disk.disk_size_gb or 0
            sku      = (disk.sku.name if disk.sku else "N/A")[:20]
            rg       = ((disk.id or "").split("/")[4] if disk.id else "N/A")[:25]
            attached = "Attached" if disk.managed_by else "UNATTACHED"
            flag     = "  ***" if not disk.managed_by else ""
            lines.append(
                f"  {name:<40} {size_gb:>10} {sku:<20} {rg:<25} {attached}{flag}"
            )
            if not disk.managed_by:
                unattached.append(
                    f"  {name:<40} {size_gb:>6} GB  {sku:<20}  RG: {rg}"
                )
                self._warn(f"Unattached managed disk: '{disk.name}' ({size_gb} GB, {sku})")

        lines += ["=" * 110, ""]
        self._save(self._fname("36_azure_disks.txt"), "\n".join(lines))

        if unattached:
            unattached_header = [
                "=" * 90,
                f"  UNATTACHED MANAGED DISKS  ({len(unattached)} found)",
                "=" * 90,
                f"  {'Disk Name':<40} {'Size':>8}  {'SKU':<20}  Resource Group",
                "  " + "-" * 86,
            ]
            self._save(
                self._fname("36b_azure_unattached_disks.txt"),
                "\n".join(unattached_header + unattached) + "\n",
            )
