"""Audit collector — orchestrates all sections for one audit run."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.modules.base import BaseSection, ProgressCallback, SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthManager
from app.modules.m365_audit.graph_client import GraphClient

logger = logging.getLogger(__name__)


class AuditCollector:
    """
    Runs all audit sections sequentially (Graph rate-limits disfavour heavy
    concurrency), reports progress via callback, and returns all results.
    """

    # Canonical section names for the sections endpoint
    GRAPH_SECTION_NAMES = [
        "Tenant Information",
        "Licenses",
        "Users",
        "Conditional Access",
        "MFA Methods",
        "Sign-in Activity",
        "Groups",
        "Admin Roles",
        "Secure Score",
        "Intune",
        "Entra Devices",
        "SharePoint",
        "Microsoft Teams",
        "App Registrations & OAuth",
        "Identity Security",
        "Teams Policies",
        "Password Protection",
        "Privileged Identity Management",
        "DNS / Email Security",
        "Exchange Online",
        "Defender for Office 365",
        "OneDrive Sharing",
        "Compliance Score",
        "Usage Reports",
    ]

    AZURE_SECTION_NAMES = [
        "Azure Compute",
        "Azure Network",
        "Azure Storage",
        "Azure Governance",
    ]

    @classmethod
    def get_all_sections(cls) -> list[dict]:
        """Return list of all section descriptors for the scope selector."""
        sections = []
        for name in cls.GRAPH_SECTION_NAMES:
            sections.append({"name": name, "category": "M365", "enabled": True})
        for name in cls.AZURE_SECTION_NAMES:
            sections.append({"name": name, "category": "Azure", "enabled": True})
        return sections

    def __init__(
        self,
        auth:        AuthManager,
        out_dir:     Path,
        progress_cb: Optional[ProgressCallback] = None,
        sections_filter: Optional[set[str]] = None,
    ):
        self.auth        = auth
        self.out_dir     = out_dir
        self.progress_cb = progress_cb
        self.sections_filter = sections_filter  # None means run all
        self.results:    list[SectionResult] = []

    def _is_enabled(self, name: str) -> bool:
        """Check if a section is enabled by the scope filter."""
        if self.sections_filter is None:
            return True
        return name in self.sections_filter

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run(self) -> list[SectionResult]:
        """Run full audit. Returns list of SectionResults."""
        self.out_dir.mkdir(parents=True, exist_ok=True)

        async with self.auth as auth:
            async with GraphClient(auth.credential) as graph:

                # ── 1. Collect EXO data via PS helper (async subprocess) ─────
                exo_enabled = self._is_enabled("Exchange Online")
                exo_task = asyncio.create_task(
                    auth.collect_exo_data(self.out_dir)
                ) if exo_enabled else None

                # ── 2. Collect tenant info first (other sections may need it) ─
                from app.modules.m365_audit.sections.tenant import TenantSection
                tenant_enabled = self._is_enabled("Tenant Information")
                # When the section is deselected it still has to run, because
                # every later section needs verified_domains. It must then run
                # without the progress callback: the caller sizes the progress
                # bar from the selected sections only, so a report from an
                # unselected section pushes the numerator past the denominator.
                # That is where "21/18" came from.
                tenant_sec = TenantSection(
                    self.out_dir, graph, self.progress_cb if tenant_enabled else None
                )
                if tenant_enabled:
                    await self._run(tenant_sec)
                else:
                    try:
                        await tenant_sec.collect()
                    except Exception as e:
                        logger.warning("Tenant info pre-collection failed: %s", e)
                verified_domains = tenant_sec.verified_domains

                # ── 3. Run remaining Graph/Azure sections ─────────────────────
                graph_sections = self._build_graph_sections(graph, verified_domains)
                for section in graph_sections:
                    if self._is_enabled(section.name):
                        await self._run(section)

                # ── 4. Azure sections (multi-subscription) ────────────────────
                any_azure = any(self._is_enabled(n) for n in self.AZURE_SECTION_NAMES)
                if any_azure:
                    sub_enum_error = ""
                    try:
                        subs = await asyncio.get_event_loop().run_in_executor(
                            None, auth.list_subscriptions
                        )
                    except Exception as e:
                        sub_enum_error = str(e)
                        subs = []
                        if auth.subscription_id:
                            subs = [{"id": auth.subscription_id, "name": "Primary", "state": "Enabled"}]

                    if subs:
                        # Save subscription overview
                        sub_lines = ["=" * 90, f"  AZURE SUBSCRIPTIONS  ({len(subs)} found)", "=" * 90]
                        if sub_enum_error:
                            sub_lines.append(f"  NOTE: Subscription enumeration failed: {sub_enum_error}")
                            sub_lines.append(f"  Falling back to configured subscription.")
                            sub_lines.append(f"  To audit ALL subscriptions, grant the service principal")
                            sub_lines.append(f"  'Reader' role on each subscription via Azure Portal.")
                            sub_lines.append("")
                        for s in subs:
                            sub_lines.append(f"  {s['name']:<40} {s['id']}  [{s['state']}]")
                        sub_lines += ["=" * 90, ""]
                        from app.core.encryption import encrypted_write_text
                        encrypted_write_text(self.out_dir / "45_azure_subscriptions.txt", "\n".join(sub_lines))

                        multi = len(subs) > 1
                        for sub in subs:
                            azure_sections = self._build_azure_sections(sub["id"], sub["name"], multi)
                            for section in azure_sections:
                                if self._is_enabled(section.name):
                                    await self._run(section)
                    else:
                        for name in self.AZURE_SECTION_NAMES:
                            if self._is_enabled(name):
                                self._skip(name, "No Azure subscriptions found")

                # ── 5. Wait for EXO data, then process Exchange section ───────
                if exo_enabled and exo_task:
                    self._report_progress("Exchange Online", SectionStatus.RUNNING, "Waiting for EXO helper...")
                    exo_data = await exo_task
                    from app.modules.m365_audit.sections.exchange import ExchangeSection
                    exo_sec = ExchangeSection(
                        self.out_dir, exo_data, verified_domains, self.progress_cb,
                        graph=graph,
                    )
                    await self._run(exo_sec)

        return self.results

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_graph_sections(self, graph: GraphClient, verified_domains: list[str]) -> list[BaseSection]:
        from app.modules.m365_audit.sections.apps_oauth import AppsOAuthSection
        from app.modules.m365_audit.sections.usage_reports import UsageReportsSection
        from app.modules.m365_audit.sections.compliance_score import ComplianceScoreSection
        from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
        from app.modules.m365_audit.sections.defender_office import DefenderOfficeSection
        from app.modules.m365_audit.sections.dns import DnsSection
        from app.modules.m365_audit.sections.groups_roles import AdminRolesSection, GroupsSection
        from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
        from app.modules.m365_audit.sections.entra_devices import EntraDevicesSection
        from app.modules.m365_audit.sections.intune import IntuneSection
        from app.modules.m365_audit.sections.licenses import LicensesSection
        from app.modules.m365_audit.sections.onedrive_sharing import OneDriveSharingSection
        from app.modules.m365_audit.sections.password_protection import PasswordProtectionSection
        from app.modules.m365_audit.sections.pim import PIMSection
        from app.modules.m365_audit.sections.secure_score import SecureScoreSection
        from app.modules.m365_audit.sections.sharepoint import SharePointSection
        from app.modules.m365_audit.sections.signins import SignInsSection
        from app.modules.m365_audit.sections.teams import TeamsSection
        from app.modules.m365_audit.sections.teams_policies import TeamsPoliciesSection
        from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection

        users_sec = UsersSection(self.out_dir, graph, self.progress_cb)
        ca_sec    = ConditionalAccessSection(self.out_dir, graph, self.progress_cb)
        # Built here so its global_admin_ids list exists before the section
        # list is assembled; the break-glass check below shares that list by
        # reference and reads it after this section has run.
        admin_sec = AdminRolesSection(self.out_dir, graph, self.progress_cb,
                                      users_ref=users_sec.users)
        # Hoisted so the break-glass check can share its computed CA-exclusion
        # set (populated in place when MFA runs, earlier in the sequence) — F8.
        mfa_sec = MFASection(self.out_dir, graph, users_sec.users, self.progress_cb,
                             ca_section=ca_sec)

        return [
            LicensesSection(self.out_dir, graph, self.progress_cb),
            users_sec,
            # CA runs before MFA so its policies are available for cross-reference
            ca_sec,
            mfa_sec,
            SignInsSection(self.out_dir, graph, self.progress_cb),
            GroupsSection(self.out_dir, graph, self.progress_cb),
            admin_sec,
            SecureScoreSection(self.out_dir, graph, self.progress_cb),
            IntuneSection(self.out_dir, graph, self.progress_cb),
            EntraDevicesSection(self.out_dir, graph, self.progress_cb),
            SharePointSection(self.out_dir, graph, self.progress_cb),
            TeamsSection(self.out_dir, graph, self.progress_cb),
            AppsOAuthSection(self.out_dir, graph, self.progress_cb),
            # AdminRoles runs earlier in this list, so its ids are populated
            # by the time the break-glass check reads them.
            IdentitySecuritySection(self.out_dir, graph,
                                    global_admin_ids=admin_sec.global_admin_ids,
                                    ca_exclusions=mfa_sec.mfa_excluded_ids,
                                    users_ref=users_sec.users,
                                    ca_section=ca_sec,
                                    # Read at break-glass time: did the MFA
                                    # section actually compute exclusions? An
                                    # empty ca_exclusions is only trustworthy
                                    # when it did (F8 fail-open follow-up).
                                    mfa_analysis_ran=lambda: mfa_sec.mfa_analysis_ran,
                                    progress_cb=self.progress_cb),
            TeamsPoliciesSection(self.out_dir, graph, self.progress_cb),
            PasswordProtectionSection(self.out_dir, graph, self.progress_cb),
            PIMSection(self.out_dir, graph, self.progress_cb),
            DnsSection(self.out_dir, verified_domains, self.progress_cb),
            DefenderOfficeSection(self.out_dir, graph, self.progress_cb),
            # UsersSection runs first and shares the populated list by
            # reference. This lets the sharing audit enumerate every user's
            # OneDrive without fetching the directory again.
            OneDriveSharingSection(
                self.out_dir,
                graph,
                self.progress_cb,
                users_ref=users_sec.users,
                users_complete=lambda: users_sec.result.status == SectionStatus.DONE,
            ),
            ComplianceScoreSection(self.out_dir, graph, self.progress_cb),
            UsageReportsSection(self.out_dir, graph, self.progress_cb),
        ]

    def _build_azure_sections(self, sub_id: str, sub_name: str, multi: bool = False) -> list[BaseSection]:
        from app.modules.m365_audit.sections.azure_compute import AzureComputeSection
        from app.modules.m365_audit.sections.azure_governance import AzureGovernanceSection
        from app.modules.m365_audit.sections.azure_network import AzureNetworkSection
        from app.modules.m365_audit.sections.azure_storage import AzureStorageSection
        return [
            AzureComputeSection(self.out_dir, self.auth, self.progress_cb, sub_id, sub_name, multi),
            AzureNetworkSection(self.out_dir, self.auth, self.progress_cb, sub_id, sub_name, multi),
            AzureStorageSection(self.out_dir, self.auth, self.progress_cb, sub_id, sub_name, multi),
            AzureGovernanceSection(self.out_dir, self.auth, self.progress_cb, sub_id, sub_name, multi),
        ]

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run(self, section: BaseSection) -> None:
        try:
            result = await section.collect()
        except Exception as e:
            result = section.result
            result.status = SectionStatus.FAILED
            result.error  = str(e)
        self.results.append(result)

    def _skip(self, name: str, reason: str) -> None:
        result = SectionResult(name=name, status=SectionStatus.SKIPPED, error=reason)
        self._report_progress(name, SectionStatus.SKIPPED, reason)
        self.results.append(result)

    def _report_progress(self, name: str, status: SectionStatus, detail: Optional[str] = None) -> None:
        if self.progress_cb:
            self.progress_cb(name, status, detail)


# ── Output directory builder ───────────────────────────────────────────────────

def make_output_dir(customer_name: str) -> Path:
    """Create timestamped output directory for this audit run."""
    # get_audit_dir() rather than the AUDIT_DIR constant: the constant is
    # resolved once at import, so an operator who changes the audit directory
    # in Settings would keep writing to the old one until a restart.
    from app.core.config import get_audit_dir
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in customer_name)
    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out        = get_audit_dir() / safe_name / timestamp
    out.mkdir(parents=True, exist_ok=True)
    return out
