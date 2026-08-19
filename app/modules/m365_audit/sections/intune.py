"""Section 10–14 — Intune.

The Entra device register moved to its own section. It reads /devices, a
directory endpoint, while everything here reads deviceManagement — a separate
service with a separate subscription. On a tenant without Intune the directory
call succeeds and every Intune call returns 401, so sharing a status meant the
overview reported "Failed" for a section whose most useful finding had arrived
intact: 126 devices known, 125 of them managed by nobody.
"""

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
            await self._collect_settings_catalog()
            await self._collect_admin_templates()
            await self._collect_apps()
            await self._collect_app_protection()
            await self._collect_autopilot()
            await self._collect_endpoint_security()
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
        "12b_intune_settings_catalog.txt": "INTUNE SETTINGS CATALOG POLICIES",
        "12c_intune_admin_templates.txt": "INTUNE ADMINISTRATIVE TEMPLATES (ADMX)",
        "13_intune_apps.txt": "INTUNE MANAGED APPS",
        "13b_intune_app_protection.txt": "INTUNE APP PROTECTION POLICIES (MAM)",
        "14_intune_autopilot.txt": "INTUNE AUTOPILOT DEVICES",
        "14b_intune_endpoint_security.txt": "INTUNE ENDPOINT SECURITY POLICIES",
    }

    _PERMISSION = {
        "10_intune_devices.txt": "DeviceManagementManagedDevices.Read.All",
        "11_intune_compliance_policies.txt": "DeviceManagementConfiguration.Read.All",
        "12_intune_config_profiles.txt": "DeviceManagementConfiguration.Read.All",
        "12b_intune_settings_catalog.txt": "DeviceManagementConfiguration.Read.All",
        "12c_intune_admin_templates.txt": "DeviceManagementConfiguration.Read.All",
        "13_intune_apps.txt": "DeviceManagementApps.Read.All",
        "13b_intune_app_protection.txt": "DeviceManagementApps.Read.All",
        "14_intune_autopilot.txt": "DeviceManagementServiceConfig.Read.All",
        "14b_intune_endpoint_security.txt": "DeviceManagementConfiguration.Read.All",
    }

    def _reason(self, filename: str, err: Exception) -> str:
        """One line naming the cause, for the report to print verbatim."""
        if isinstance(err, GraphPermissionError):
            if err.is_licence_gap:
                return (f"Graph refused this collection with {err.status}, reporting a "
                        "licence gap: the tenant does not have the Intune SKU this "
                        "endpoint requires. Granting a permission will not change that.")
            if err.is_service_refusal:
                return (f"The Intune service refused this collection ({err.status}). "
                        "The DeviceManagement permission is not the problem — check "
                        "whether this tenant has an Intune subscription at all.")
            perm = self._PERMISSION.get(filename, "the matching DeviceManagement permission")
            return (f"Graph refused this collection with {err.status}: the app "
                    f"registration is missing {perm} or its admin consent.")
        return f"The collection failed before it could be read: {err}"

    def _save_unavailable(self, filename: str, err: Exception, *, critical: bool = True) -> None:
        """Record why the data is missing, in a form the report can read back.

        ``critical`` controls whether the gap fails the whole section. The five
        classic collectors are core — a refusal there means the report would
        otherwise claim "no Intune devices" for a tenant that has them, so they
        fail the section (default). The modern-surface collectors below are
        additive: a tenant that does not use App Protection, or a beta endpoint
        that answers 404, must not turn a healthy Intune section red. Those
        pass ``critical=False`` — the gap is written to its evidence file but
        the section still reports DONE on the strength of the core reads.
        """
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
        if critical:
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
            self._save_snapshot(
                "intune_compliance_policies", policies, source="deviceManagement/deviceCompliancePolicies",
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
            self._save_snapshot(
                "intune_configuration_profiles", profiles, source="deviceManagement/deviceConfigurations",
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

    # ── Modern Endpoint Manager surface (Fase 2 of #172) ───────────────────────
    # The classic collectors above read only deviceCompliancePolicies and the
    # legacy deviceConfigurations endpoint. Most of a modern tenant's config
    # lives elsewhere — the Settings Catalog, administrative templates, app
    # protection and endpoint-security policies — so a tenant full of policies
    # looked almost empty. These read those surfaces. They are additive and use
    # the same already-granted DeviceManagement* scopes; each fails soft
    # (critical=False) so a tenant that does not use a surface, or a beta
    # endpoint that 404s, never turns a healthy Intune section red.

    async def _collect_settings_catalog(self) -> None:
        try:
            policies = await self.graph.get_all(
                "deviceManagement/configurationPolicies",
                params={"$top": "999"},
            )
            self._save_snapshot(
                "intune_settings_catalog", policies,
                source="deviceManagement/configurationPolicies",
            )
        except Exception as ex:
            self._save_unavailable("12b_intune_settings_catalog.txt", ex, critical=False)
            self._warn(f"Intune Settings Catalog fetch failed: {ex}", level="info")
            return

        lines = [
            "=" * 90,
            f"  INTUNE SETTINGS CATALOG POLICIES  ({len(policies)} total)",
            "=" * 90,
            f"  {'Policy Name':<55} {'Platform':<16} {'Technologies'}",
            "  " + "-" * 86,
        ]
        for p in policies:
            # Settings Catalog policies carry their name in `name`, not
            # `displayName` like every other Intune object.
            name     = (p.get("name") or p.get("displayName") or "")[:55]
            platform = str(p.get("platforms") or "")[:16]
            tech     = str(p.get("technologies") or "")
            lines.append(f"  {name:<55} {platform:<16} {tech}")
        lines += ["=" * 90, ""]
        self._save("12b_intune_settings_catalog.txt", "\n".join(lines))

    async def _collect_admin_templates(self) -> None:
        try:
            policies = await self.graph.get_all(
                "deviceManagement/groupPolicyConfigurations",
                params={"$top": "999"},
            )
            self._save_snapshot(
                "intune_admin_templates", policies,
                source="deviceManagement/groupPolicyConfigurations",
            )
        except Exception as ex:
            self._save_unavailable("12c_intune_admin_templates.txt", ex, critical=False)
            self._warn(f"Intune administrative templates fetch failed: {ex}", level="info")
            return

        lines = [
            "=" * 80,
            f"  INTUNE ADMINISTRATIVE TEMPLATES (ADMX)  ({len(policies)} total)",
            "=" * 80,
            f"  {'Template Name':<55} {'Created'}",
            "  " + "-" * 76,
        ]
        for p in policies:
            name    = (p.get("displayName") or "")[:55]
            created = (p.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<55} {created}")
        lines += ["=" * 80, ""]
        self._save("12c_intune_admin_templates.txt", "\n".join(lines))

    async def _collect_app_protection(self) -> None:
        try:
            policies = await self.graph.get_all(
                "deviceAppManagement/managedAppPolicies",
                params={"$top": "999"},
            )
            self._save_snapshot(
                "intune_app_protection", policies,
                source="deviceAppManagement/managedAppPolicies",
            )
        except Exception as ex:
            self._save_unavailable("13b_intune_app_protection.txt", ex, critical=False)
            self._warn(f"Intune app protection fetch failed: {ex}", level="info")
            return

        lines = [
            "=" * 90,
            f"  INTUNE APP PROTECTION POLICIES (MAM)  ({len(policies)} total)",
            "=" * 90,
            f"  {'Policy Name':<55} {'Type'}",
            "  " + "-" * 86,
        ]
        for p in policies:
            name = (p.get("displayName") or "")[:55]
            typ  = p.get("@odata.type", "").split(".")[-1][:35]
            lines.append(f"  {name:<55} {typ}")
        lines += ["=" * 90, ""]
        self._save("13b_intune_app_protection.txt", "\n".join(lines))

    async def _collect_endpoint_security(self) -> None:
        # Security baselines and endpoint-security policies (antivirus, disk
        # encryption, firewall, EDR, ASR) live under deviceManagement/intents,
        # which is a beta-only endpoint — hence beta=True and the soft failure.
        try:
            intents = await self.graph.get_all(
                "deviceManagement/intents",
                params={"$top": "999"},
                beta=True,
            )
            self._save_snapshot(
                "intune_endpoint_security", intents,
                source="deviceManagement/intents (beta)",
            )
        except Exception as ex:
            self._save_unavailable("14b_intune_endpoint_security.txt", ex, critical=False)
            self._warn(f"Intune endpoint security fetch failed: {ex}", level="info")
            return

        lines = [
            "=" * 80,
            f"  INTUNE ENDPOINT SECURITY POLICIES  ({len(intents)} total)",
            "=" * 80,
            f"  {'Policy Name':<55} {'Last Modified'}",
            "  " + "-" * 76,
        ]
        for it in intents:
            name     = (it.get("displayName") or "")[:55]
            modified = (it.get("lastModifiedDateTime") or "N/A")[:19]
            lines.append(f"  {name:<55} {modified}")
        lines += ["=" * 80, ""]
        self._save("14b_intune_endpoint_security.txt", "\n".join(lines))
