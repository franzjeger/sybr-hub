"""Section 15 — the devices the directory knows about.

Split from Intune deliberately. This reads ``/devices``, a directory endpoint
that answers on every tenant; Intune reads ``deviceManagement``, a separate
service behind a separate subscription. Fonnafly has no Intune subscription, so
every call there returns 401 while this one returns 126 devices — and while the
two shared a section, the overview said "Failed" and the most useful finding in
it was invisible.

Intune answers "which devices do we manage". It cannot answer "does this tenant
have devices at all", and the gap between the two counts is the finding:
endpoints the directory knows and nobody governs.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class EntraDevicesSection(BaseSection):
    name = "Entra Devices"

    _TITLE: ClassVar[dict[str, str]] = {"15_entra_devices.txt": "ENTRA REGISTERED DEVICES"}
    _PERMISSION: ClassVar[dict[str, str]] = {"15_entra_devices.txt": "Device.Read.All"}

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self._failed = ""

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect()
            if self._failed:
                self._report(SectionStatus.FAILED, self._failed[:500])
            else:
                self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    async def _collect(self) -> None:
        """Every device the directory knows, enrolled in Intune or not.

        Intune answers "which devices do we manage". It cannot answer "does
        this tenant have devices at all", and the two were being conflated: a
        tenant with forty machines joined to Entra and none enrolled read as
        "Ingen Intune-enheter funnet", which is true and sends a technician
        looking for the wrong thing. The gap between these two counts is the
        finding — unmanaged endpoints — and it was invisible.
        """
        try:
            devices = await self.graph.get_all(
                "devices",
                params={
                    "$top": "999",
                    "$select": (
                        "displayName,operatingSystem,operatingSystemVersion,trustType,"
                        "isCompliant,isManaged,accountEnabled,"
                        "approximateLastSignInDateTime"
                    ),
                },
            )
        except Exception as ex:
            self._save_unavailable("15_entra_devices.txt", ex)
            self._warn(f"Entra devices fetch failed: {ex}")
            return

        total = len(devices)
        managed = sum(1 for d in devices if d.get("isManaged") is True)
        unmanaged = sum(1 for d in devices if d.get("isManaged") is not True)
        enabled = sum(1 for d in devices if d.get("accountEnabled") is not False)

        by_trust: dict[str, int] = {}
        for d in devices:
            by_trust[d.get("trustType") or "Unknown"] = (
                by_trust.get(d.get("trustType") or "Unknown", 0) + 1
            )

        header = (
            f"  {'Device Name':<35} {'OS':<14} {'OS Ver':<14} "
            f"{'Trust':<12} {'Managed':<8} {'Enabled':<8} Last Sign-in"
        )
        lines = [
            "=" * 120,
            f"  ENTRA REGISTERED DEVICES  ({total} total)",
            "=" * 120,
            header,
            "  " + "-" * 116,
        ]
        for d in sorted(devices, key=lambda x: (x.get("displayName") or "").lower()):
            lines.append(
                f"  {(d.get('displayName') or '')[:35]:<35} "
                f"{(d.get('operatingSystem') or '')[:14]:<14} "
                f"{(d.get('operatingSystemVersion') or '')[:14]:<14} "
                f"{(d.get('trustType') or '')[:12]:<12} "
                f"{('yes' if d.get('isManaged') else 'no'):<8} "
                f"{('yes' if d.get('accountEnabled') is not False else 'no'):<8} "
                f"{(d.get('approximateLastSignInDateTime') or 'N/A')[:19]}"
            )
        lines += ["=" * 120, ""]
        self._save("15_entra_devices.txt", "\n".join(lines))

        count_lines = [
            "ENTRA DEVICE COUNT SUMMARY",
            f"Total: {total}",
            f"Managed: {managed}",
            f"Unmanaged: {unmanaged}",
            f"Enabled: {enabled}",
        ]
        for trust, n in sorted(by_trust.items()):
            count_lines.append(f"Trust {trust}: {n}")
        self._save("15_entra_devices_count.txt", "\n".join(count_lines))

        if unmanaged:
            self._warn(
                f"{unmanaged} of {total} Entra-registered devices are not "
                f"managed by Intune"
            )
