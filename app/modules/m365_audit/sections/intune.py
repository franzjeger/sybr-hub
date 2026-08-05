"""Section 10–15 — Intune, plus the Entra device register it is measured against."""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError


class IntuneSection(BaseSection):
    name = "Intune"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self._failures: list[str] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_devices()
            await self._collect_compliance_policies()
            await self._collect_config_profiles()
            await self._collect_apps()
            await self._collect_autopilot()
            await self._collect_entra_devices()
            # Each collector needs its own DeviceManagement permission, so one
            # refusal says nothing about the other four — they all run, and
            # what was readable is still collected. But the section must not
            # end DONE when part of it could not be read: that is what let a
            # 403 reach the report as "no Intune devices found".
            if self._failures:
                self._report(SectionStatus.FAILED, "; ".join(self._failures)[:500])
            else:
                self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Managed Devices ───────────────────────────────────────────────────────

    # Endpoint → the permission that grants it, so a refusal names the consent
    # to check rather than leaving a reader to guess which of the four
    # DeviceManagement* roles this particular call needed.
    _TITLE = {
        "10_intune_devices.txt": "INTUNE MANAGED DEVICES",
        "11_intune_compliance_policies.txt": "INTUNE COMPLIANCE POLICIES",
        "12_intune_config_profiles.txt": "INTUNE CONFIGURATION PROFILES",
        "13_intune_apps.txt": "INTUNE MANAGED APPS",
        "14_intune_autopilot.txt": "INTUNE AUTOPILOT DEVICES",
        "15_entra_devices.txt": "ENTRA REGISTERED DEVICES",
    }

    _PERMISSION = {
        "10_intune_devices.txt": "DeviceManagementManagedDevices.Read.All",
        "11_intune_compliance_policies.txt": "DeviceManagementConfiguration.Read.All",
        "12_intune_config_profiles.txt": "DeviceManagementConfiguration.Read.All",
        "13_intune_apps.txt": "DeviceManagementApps.Read.All",
        "14_intune_autopilot.txt": "DeviceManagementServiceConfig.Read.All",
        "15_entra_devices.txt": "Device.Read.All",
    }

    def _reason(self, filename: str, err: Exception) -> str:
        """One line naming the cause, for the report to print verbatim."""
        if isinstance(err, GraphPermissionError):
            if err.is_licence_gap:
                return (f"Graph refused this collection with {err.status}, reporting a "
                        "licence gap: the tenant does not have the Intune SKU this "
                        "endpoint requires. Granting a permission will not change that.")
            perm = self._PERMISSION.get(filename, "the matching DeviceManagement permission")
            return (f"Graph refused this collection with {err.status}: the app "
                    f"registration is missing {perm} or its admin consent.")
        return f"The collection failed before it could be read: {err}"

    def _save_unavailable(self, filename: str, err: Exception) -> None:
        """Record why the data is missing, in a form the report can read back."""
        lines = [
            "=" * 80,
            f"  {self._TITLE[filename]}  (not available)",
            "=" * 80,
            "",
            f"  {self._reason(filename, err)}",
        ]
        if isinstance(err, GraphPermissionError) and (err.code or err.message):
            lines += ["", f"  Graph said: {err.code} — {err.message}"[:300]]
        lines += ["", "  Error details for troubleshooting:", f"    {err}", "", "=" * 80, ""]
        self._save(filename, "\n".join(lines))
        self._failures.append(self._reason(filename, err))

    async def _collect_devices(self) -> None:
        try:
            devices = await self.graph.get_all(
                "deviceManagement/managedDevices",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save_unavailable("10_intune_devices.txt", ex)
            self._warn(f"Intune managed devices fetch failed: {ex}")
            return

        total       = len(devices)
        compliant   = sum(1 for d in devices if d.get("complianceState") == "compliant")
        noncompliant = sum(1 for d in devices if d.get("complianceState") == "noncompliant")
        unknown     = total - compliant - noncompliant

        header = (
            f"  {'Device Name':<35} {'OS':<12} {'OS Ver':<15} "
            f"{'Owner':<10} {'Compliance':<15} {'Last Sync'}"
        )
        lines = [
            "=" * 120,
            f"  INTUNE MANAGED DEVICES  ({total} total)",
            "=" * 120,
            header,
            "  " + "-" * 116,
        ]

        for d in devices:
            dev_name   = (d.get("deviceName") or "")[:35]
            os_name    = (d.get("operatingSystem") or "")[:12]
            os_ver     = (d.get("osVersion") or "")[:15]
            owner      = (d.get("managedDeviceOwnerType") or "")[:10]
            compliance = d.get("complianceState", "unknown")[:15]
            last_sync  = (d.get("lastSyncDateTime") or "N/A")[:19]
            lines.append(
                f"  {dev_name:<35} {os_name:<12} {os_ver:<15} "
                f"{owner:<10} {compliance:<15} {last_sync}"
            )

        lines += ["=" * 120, ""]
        self._save("10_intune_devices.txt", "\n".join(lines))

        # Count file
        count_lines = [
            "=" * 40,
            "  INTUNE DEVICE COUNT SUMMARY",
            "=" * 40,
            f"  Total devices      : {total}",
            f"  Compliant          : {compliant}",
            f"  Non-compliant      : {noncompliant}",
            f"  Unknown/other      : {unknown}",
            "=" * 40,
            "",
        ]
        self._save("10_intune_devices_count.txt", "\n".join(count_lines))

        if noncompliant > 0:
            self._warn(
                f"{noncompliant} Intune device(s) are non-compliant"
            )

    # ── Compliance Policies ───────────────────────────────────────────────────

    async def _collect_compliance_policies(self) -> None:
        try:
            policies = await self.graph.get_all(
                "deviceManagement/deviceCompliancePolicies",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save_unavailable("11_intune_compliance_policies.txt", ex)
            self._warn(f"Intune compliance policies fetch failed: {ex}")
            return

        lines = [
            "=" * 80,
            f"  INTUNE COMPLIANCE POLICIES  ({len(policies)} total)",
            "=" * 80,
            f"  {'Policy Name':<50} {'Platform':<20} {'Created'}",
            "  " + "-" * 76,
        ]
        for p in policies:
            name     = (p.get("displayName") or "")[:50]
            platform = p.get("@odata.type", "").split(".")[-1].replace(
                "CompliancePolicy", ""
            )[:20]
            created  = (p.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {platform:<20} {created}")
        lines += ["=" * 80, ""]
        self._save("11_intune_compliance_policies.txt", "\n".join(lines))

    # ── Configuration Profiles ────────────────────────────────────────────────

    async def _collect_config_profiles(self) -> None:
        try:
            profiles = await self.graph.get_all(
                "deviceManagement/deviceConfigurations",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save_unavailable("12_intune_config_profiles.txt", ex)
            self._warn(f"Intune configuration profiles fetch failed: {ex}")
            return

        lines = [
            "=" * 80,
            f"  INTUNE CONFIGURATION PROFILES  ({len(profiles)} total)",
            "=" * 80,
            f"  {'Profile Name':<50} {'Platform':<25} {'Created'}",
            "  " + "-" * 76,
        ]
        for p in profiles:
            name     = (p.get("displayName") or "")[:50]
            platform = p.get("@odata.type", "").split(".")[-1].replace(
                "Configuration", ""
            )[:25]
            created  = (p.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {platform:<25} {created}")
        lines += ["=" * 80, ""]
        self._save("12_intune_config_profiles.txt", "\n".join(lines))

    # ── Mobile Apps ───────────────────────────────────────────────────────────

    async def _collect_apps(self) -> None:
        try:
            apps = await self.graph.get_all(
                "deviceAppManagement/mobileApps",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save_unavailable("13_intune_apps.txt", ex)
            self._warn(f"Intune mobile apps fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            f"  INTUNE MOBILE APPS  ({len(apps)} total)",
            "=" * 100,
            f"  {'App Name':<50} {'Type':<30} {'Publisher':<25} {'Created'}",
            "  " + "-" * 96,
        ]
        for a in apps:
            name      = (a.get("displayName") or "")[:50]
            app_type  = a.get("@odata.type", "").split(".")[-1][:30]
            publisher = (a.get("publisher") or "")[:25]
            created   = (a.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {app_type:<30} {publisher:<25} {created}")
        lines += ["=" * 100, ""]
        self._save("13_intune_apps.txt", "\n".join(lines))

    # ── Autopilot Devices ─────────────────────────────────────────────────────

    async def _collect_autopilot(self) -> None:
        try:
            devices = await self.graph.get_all(
                "deviceManagement/windowsAutopilotDeviceIdentities",
                params={"$top": "999"},
            )
        except Exception as ex:
            self._save_unavailable("14_intune_autopilot.txt", ex)
            self._warn(f"Intune Autopilot devices fetch failed: {ex}")
            return

        lines = [
            "=" * 100,
            f"  WINDOWS AUTOPILOT DEVICES  ({len(devices)} total)",
            "=" * 100,
            f"  {'Serial Number':<25} {'Model':<30} {'Manufacturer':<25} {'Group Tag':<15} {'Enrolled By'}",
            "  " + "-" * 96,
        ]
        for d in devices:
            serial   = (d.get("serialNumber") or "")[:25]
            model    = (d.get("model") or "")[:30]
            mfg      = (d.get("manufacturer") or "")[:25]
            tag      = (d.get("groupTag") or "")[:15]
            enrolled = (d.get("enrollmentState") or "")
            lines.append(
                f"  {serial:<25} {model:<30} {mfg:<25} {tag:<15} {enrolled}"
            )
        lines += ["=" * 100, ""]
        self._save("14_intune_autopilot.txt", "\n".join(lines))

    # ── Entra device register ─────────────────────────────────────────────────

    async def _collect_entra_devices(self) -> None:
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
