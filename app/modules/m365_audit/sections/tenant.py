"""Section 01 — Tenant Information."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.graph_client import GraphClient


class TenantSection(BaseSection):
    name = "Tenant Information"

    def __init__(self, out_dir: Path, graph: GraphClient, progress_cb=None):
        super().__init__(out_dir, progress_cb)
        self.graph = graph
        self.verified_domains: list[str] = []

    async def collect(self) -> SectionResult:
        self._report(SectionStatus.RUNNING)
        try:
            data = await self.graph.get("organization")
            orgs = data.get("value", [])
            if not orgs:
                self._warn("No organization data returned")
                self._save("01_tenant.txt", "No organization data returned.\n")
                self._report(SectionStatus.DONE)
                return self.result

            org = orgs[0]

            # Collect verified domains for use by other sections
            self.verified_domains = [
                d["name"]
                for d in org.get("verifiedDomains", [])
                if d.get("isVerified")
            ]

            # Fallback: if verifiedDomains is empty, try the /domains endpoint
            if not self.verified_domains:
                try:
                    domains_list = await self.graph.get_all(
                        "domains",
                        params={"$top": "999"},
                    )
                    self.verified_domains = [
                        d["id"] for d in domains_list if d.get("isVerified")
                    ]
                except Exception as ex:
                    # Without verified domains the DNS section cannot run —
                    # surface it so the report flags the gap rather than
                    # silently skipping email-security checks.
                    self._warn(
                        f"Tenant domains fallback failed: {ex} — DNS/email "
                        "security audit will have nothing to check"
                    )
            # Store on result metadata
            self.result.error = None  # clear

            tech_contacts = ", ".join(org.get("technicalNotificationMails", [])) or "N/A"
            domains_str = "\n".join(f"  - {d}" for d in self.verified_domains) or "  (none)"

            lines = [
                "=" * 60,
                "  TENANT INFORMATION",
                "=" * 60,
                f"  Name          : {org.get('displayName', 'N/A')}",
                f"  Tenant ID     : {org.get('id', 'N/A')}",
                f"  Created       : {org.get('createdDateTime', 'N/A')}",
                f"  Country       : {org.get('countryLetterCode', 'N/A')}",
                f"  Tech Contact  : {tech_contacts}",
                "",
                "  Verified Domains:",
                domains_str,
                "=" * 60,
            ]
            self._save("01_tenant.txt", "\n".join(lines) + "\n")
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result
