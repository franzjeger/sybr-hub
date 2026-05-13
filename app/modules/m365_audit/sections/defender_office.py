"""Section 24 — Defender for Office 365: Security Alerts & Incidents.

Required Graph API permissions:
- SecurityAlert.Read.All (for security/alerts_v2)
- SecurityIncident.Read.All (for security/incidents)

Both endpoints gracefully handle 403/404 with informative error messages.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class DefenderOfficeSection(BaseSection):
    name = "Defender for Office 365"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            await self._collect_security_alerts()
            await self._collect_security_incidents()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Security Alerts ──────────────────────────────────────────────────────

    async def _collect_security_alerts(self) -> None:
        _CAP = 100
        try:
            data   = await self.graph.get(
                "security/alerts_v2",
                params={
                    "$top": str(_CAP),
                    "$orderby": "createdDateTime desc",
                    "$count": "true",
                },
                extra_headers={"ConsistencyLevel": "eventual"},
            )
            alerts = data.get("value", [])
            total_in_tenant = data.get("@odata.count")
        except Exception as ex:
            self._save(
                "24_defender_office365.txt",
                f"Error fetching security alerts: {ex}\n"
                "Note: This endpoint requires SecurityAlert.Read.All permissions.\n",
            )
            self._warn(f"Defender alerts fetch failed: {ex}")
            return

        # Count by severity (within the fetched window)
        high   = [a for a in alerts if a.get("severity", "").lower() == "high"]
        medium = [a for a in alerts if a.get("severity", "").lower() == "medium"]
        low    = [a for a in alerts if a.get("severity", "").lower() == "low"]

        if isinstance(total_in_tenant, int) and total_in_tenant > len(alerts):
            count_line = (
                f"  DEFENDER FOR OFFICE 365 — SECURITY ALERTS  "
                f"(showing most recent {len(alerts)} of {total_in_tenant})"
            )
        else:
            count_line = (
                f"  DEFENDER FOR OFFICE 365 — SECURITY ALERTS  ({len(alerts)} total)"
            )

        header = (
            f"  {'Title':<50} {'Severity':<10} {'Status':<15} {'Created'}"
        )
        lines = [
            "=" * 100,
            count_line,
            "=" * 100,
            f"  High: {len(high)}  |  Medium: {len(medium)}  |  Low: {len(low)}"
            + (
                "    (severity counts limited to fetched window)"
                if isinstance(total_in_tenant, int) and total_in_tenant > len(alerts)
                else ""
            ),
            "",
            header,
            "  " + "-" * 96,
        ]

        for a in alerts:
            title    = (a.get("title") or "")[:50]
            severity = (a.get("severity") or "unknown")[:10]
            status   = (a.get("status") or "unknown")[:15]
            created  = (a.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {title:<50} {severity:<10} {status:<15} {created}")

        lines += ["=" * 100, ""]
        self._save("24_defender_office365.txt", "\n".join(lines))

        # Warnings for active high-severity alerts
        active_high = [
            a for a in high
            if a.get("status", "").lower() not in ("resolved", "closed")
        ]
        if active_high:
            self._warn(
                f"{len(active_high)} active high-severity security alert(s) detected"
            )

    # ── Security Incidents ───────────────────────────────────────────────────

    async def _collect_security_incidents(self) -> None:
        _CAP = 50
        try:
            data      = await self.graph.get(
                "security/incidents",
                params={
                    "$top": str(_CAP),
                    "$orderby": "createdDateTime desc",
                    "$count": "true",
                },
                extra_headers={"ConsistencyLevel": "eventual"},
            )
            incidents = data.get("value", [])
            total_in_tenant = data.get("@odata.count")
        except Exception as ex:
            self._save(
                "24b_defender_incidents.txt",
                f"Error fetching security incidents: {ex}\n"
                "Note: This endpoint requires SecurityIncident.Read.All permissions.\n",
            )
            self._warn(f"Defender incidents fetch failed: {ex}")
            return

        if isinstance(total_in_tenant, int) and total_in_tenant > len(incidents):
            count_line = (
                f"  DEFENDER FOR OFFICE 365 — SECURITY INCIDENTS  "
                f"(showing most recent {len(incidents)} of {total_in_tenant})"
            )
        else:
            count_line = (
                f"  DEFENDER FOR OFFICE 365 — SECURITY INCIDENTS  "
                f"({len(incidents)} total)"
            )

        header = (
            f"  {'Incident Name':<50} {'Severity':<10} {'Status':<15} {'Created'}"
        )
        lines = [
            "=" * 100,
            count_line,
            "=" * 100,
            header,
            "  " + "-" * 96,
        ]

        for inc in incidents:
            name     = (inc.get("displayName") or inc.get("incidentName") or "")[:50]
            severity = (inc.get("severity") or "unknown")[:10]
            status   = (inc.get("status") or "unknown")[:15]
            created  = (inc.get("createdDateTime") or "N/A")[:19]
            lines.append(f"  {name:<50} {severity:<10} {status:<15} {created}")

        lines += ["=" * 100, ""]
        self._save("24b_defender_incidents.txt", "\n".join(lines))

        # Warnings for unresolved incidents
        unresolved = [
            i for i in incidents
            if i.get("status", "").lower() not in ("resolved", "closed")
        ]
        if unresolved:
            self._warn(
                f"{len(unresolved)} unresolved security incident(s)"
            )
