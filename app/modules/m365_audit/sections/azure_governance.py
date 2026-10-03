"""Section 50-61 — Azure Governance: Advisor, Backup, Log Analytics, Resource
Inventory, Orphaned Resources, and Cost Analysis.

Azure SDK clients are synchronous; dispatched to a thread-pool executor.
Cost data is fetched via the Azure Cost Management REST API.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path

import httpx

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthManager

_ARM_COST_API = (
    "https://management.azure.com/subscriptions/{sub_id}"
    "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
)
_ARM_SCOPE = "https://management.azure.com/.default"


def _run_sync(fn):
    return asyncio.get_event_loop().run_in_executor(None, fn)


def _rg(resource_id: str) -> str:
    parts = (resource_id or "").split("/")
    return parts[4] if len(parts) > 4 else "N/A"


def _enum_text(value) -> str | None:
    """An Azure SDK enum or string as its plain value."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _protected_item(item) -> dict:
    """One protected item, as the coverage check needs it."""
    p = item.properties
    last = getattr(p, "last_backup_time", None)
    return {
        "name": item.name,
        "friendly_name": getattr(p, "friendly_name", None) or item.name,
        "workload_type": _enum_text(getattr(p, "workload_type", None)),
        "protection_state": _enum_text(getattr(p, "protection_state", None)),
        "protection_status": _enum_text(getattr(p, "protection_status", None)),
        "health_status": _enum_text(getattr(p, "health_status", None)),
        "last_backup_time": last.isoformat() if hasattr(last, "isoformat") else last,
        # IaaS VM items carry the VM's resource id under one name or the other.
        "source_resource_id": getattr(p, "source_resource_id", None)
        or getattr(p, "virtual_machine_id", None),
    }


class AzureGovernanceSection(BaseSection):
    name = "Azure Governance"

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
        self._sub_prefix = (
            "".join(c if c.isalnum() or c in "-_" else "_" for c in sub_name)[:20] if multi else ""
        )
        super().__init__(out_dir, progress_cb)
        if sub_name:
            self.name = f"Azure Governance ({sub_name})"
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

        failed = False
        for collector in [
            self._collect_advisor,
            self._collect_backup,
            self._collect_log_analytics,
            self._collect_resource_inventory,
            self._collect_orphaned_resources,
            self._collect_cost,
        ]:
            try:
                await collector()
            except Exception as e:
                self._warn(f"{collector.__name__} feilet: {e}")
                failed = True

        self._report(SectionStatus.FAILED if failed else SectionStatus.DONE)
        return self.result

    # ── Azure Advisor ─────────────────────────────────────────────────────────

    async def _collect_advisor(self) -> None:
        try:
            client = self.auth.advisor_client_for(self._sub_id)
            recs = await _run_sync(lambda: list(client.recommendations.list()))
        except Exception as ex:
            self._save(self._fname("51_azure_advisor.txt"), f"Error: {ex}\n")
            return

        by_cat: dict[str, list] = defaultdict(list)
        for r in recs:
            by_cat[r.category or "General"].append(r)

        lines = [
            "=" * 110,
            f"  AZURE ADVISOR RECOMMENDATIONS  ({len(recs)} total)",
            "=" * 110,
        ]
        record: list[dict] = []
        for cat, items in sorted(by_cat.items()):
            lines += [f"\n  [{cat}]  ({len(items)} recommendations)", "  " + "-" * 70]
            for r in items:
                impact = r.impact or "Medium"
                sd = getattr(r, "short_description", None)
                desc = (getattr(sd, "problem", "") or getattr(sd, "solution", "") or "N/A")[:80]
                res = (r.impacted_value or "N/A")[:50]
                lines.append(f"    [{impact:<8}]  {desc}")
                lines.append(f"               Resource: {res}")
                record.append(
                    {
                        "category": _enum_text(cat),
                        "impact": _enum_text(impact),
                        "description": getattr(sd, "problem", None)
                        or getattr(sd, "solution", None),
                        "resource": r.impacted_value,
                    }
                )
        lines += ["", "=" * 110, ""]
        self._save(self._fname("51_azure_advisor.txt"), "\n".join(lines))
        # The text cuts a description at 80 characters and a resource at 50.
        # The report groups recommendations by description, so two that share
        # their first 80 characters were counted as one.
        self._save_sidecar(
            self._fname("51_azure_advisor.txt"), {"count": len(recs), "recommendations": record}
        )

    # ── Recovery Services Vaults / Backup ─────────────────────────────────────

    async def _collect_backup(self) -> None:
        """Recovery Services vaults and every item each one protects.

        52_azure_backup.txt is for a person. 52_azure_backup.json carries the
        same items untrimmed, with the resource id of the VM each one protects,
        which is what the backup-coverage cross-reference matches on. The text
        listing used to stop at 15 items per vault and cut names at 40
        characters, so a VM past either limit read as unprotected.
        """
        try:
            client = self.auth.recovery_client_for(self._sub_id)
            vaults = await _run_sync(lambda: list(client.vaults.list_by_subscription_id()))
        except Exception as ex:
            self._save(self._fname("52_azure_backup.txt"), f"Error: {ex}\n")
            return

        if not vaults:
            self._save(self._fname("52_azure_backup.txt"), "No Recovery Services vaults found.\n")
            self._save(self._fname("52_azure_backup.json"), json.dumps({"vaults": []}))
            return

        lines = [
            "=" * 110,
            f"  AZURE BACKUP — RECOVERY SERVICES VAULTS  ({len(vaults)} vault(s))",
            "=" * 110,
        ]
        record: list[dict] = []
        for vault in vaults:
            vault_rg = _rg(vault.id or "")
            sku_name = vault.sku.name if vault.sku else "N/A"
            entry: dict = {
                "name": vault.name,
                "resource_group": vault_rg,
                "location": vault.location,
                "items": [],
                "items_error": None,
            }
            lines += [
                f"\n  Vault    : {vault.name}",
                f"    RG       : {vault_rg}",
                f"    Location : {vault.location}",
                f"    SKU      : {sku_name}",
            ]
            try:
                from azure.mgmt.recoveryservicesbackup import RecoveryServicesBackupClient

                bk_client = RecoveryServicesBackupClient(self.auth._az_credential(), self._sub_id)
                items = await _run_sync(
                    lambda rg=vault_rg, vn=vault.name, bk=bk_client: list(
                        bk.backup_protected_items.list(vn, rg)
                    )
                )
                lines.append(f"    Protected Items: {len(items)}")
                for item in items:
                    row = _protected_item(item)
                    entry["items"].append(row)
                    lines.append(
                        f"      - {row['friendly_name']}  Status:{row['protection_status']}"
                        f"  State:{row['protection_state']}"
                        f"  LastBK:{(row['last_backup_time'] or 'N/A')[:19]}"
                        f"  Health:{row['health_status']}"
                    )
            except Exception as ex:
                entry["items_error"] = str(ex)
                lines.append(f"    Protected Items: Error: {ex}")
            record.append(entry)

        lines += ["", "=" * 110, ""]
        self._save(self._fname("52_azure_backup.txt"), "\n".join(lines))
        self._save(self._fname("52_azure_backup.json"), json.dumps({"vaults": record}, indent=1))

    # ── Log Analytics Workspaces ──────────────────────────────────────────────

    async def _collect_log_analytics(self) -> None:
        try:
            client = self.auth.log_analytics_client_for(self._sub_id)
            workspaces = await _run_sync(lambda: list(client.workspaces.list()))
        except Exception as ex:
            self._save(self._fname("53_azure_log_analytics.txt"), f"Error: {ex}\n")
            return

        lines = [
            "=" * 100,
            f"  AZURE LOG ANALYTICS WORKSPACES  ({len(workspaces)} total)",
            "=" * 100,
            f"  {'Workspace Name':<40} {'RG':<25} {'Location':<18} {'SKU':<18} {'Retention':>12}",
            "  " + "-" * 96,
        ]
        for ws in workspaces:
            name = (ws.name or "")[:40]
            ws_rg = _rg(ws.id or "")[:25]
            loc = (ws.location or "")[:18]
            sku = (ws.sku.name if ws.sku else "N/A")[:18]
            retention = f"{ws.retention_in_days}d" if ws.retention_in_days else "N/A"
            lines.append(f"  {name:<40} {ws_rg:<25} {loc:<18} {sku:<18} {retention:>12}")
        lines += ["=" * 100, ""]
        self._save(self._fname("53_azure_log_analytics.txt"), "\n".join(lines))

    # ── Full Resource Inventory ───────────────────────────────────────────────

    async def _collect_resource_inventory(self) -> None:
        try:
            client = self.auth.resource_client_for(self._sub_id)
            resources = await _run_sync(lambda: list(client.resources.list()))
        except Exception as ex:
            self._save(self._fname("60_azure_resource_inventory_summary.txt"), f"Error: {ex}\n")
            self._save(self._fname("60b_azure_resource_inventory_full.txt"), f"Error: {ex}\n")
            return

        total = len(resources)
        by_type: dict[str, int] = defaultdict(int)
        by_rg: dict[str, int] = defaultdict(int)
        for r in resources:
            by_type[r.type or "Unknown"] += 1
            by_rg[_rg(r.id or "")] += 1

        # Summary
        summary = [
            "=" * 90,
            f"  AZURE RESOURCE INVENTORY SUMMARY  ({total} resources)",
            "=" * 90,
            "",
            "  By Type:",
            f"  {'Type':<60} {'Count':>6}",
            "  " + "-" * 68,
        ]
        for rtype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            summary.append(f"  {rtype:<60} {cnt:>6}")
        summary += [
            "",
            "  By Resource Group:",
            f"  {'Resource Group':<45} {'Count':>6}",
            "  " + "-" * 53,
        ]
        for grp, cnt in sorted(by_rg.items(), key=lambda x: -x[1]):
            summary.append(f"  {grp:<45} {cnt:>6}")
        summary += ["=" * 90, ""]
        self._save(self._fname("60_azure_resource_inventory_summary.txt"), "\n".join(summary))
        self._save_sidecar(
            self._fname("60_azure_resource_inventory_summary.txt"),
            {
                "total": total,
                "by_type": [
                    {"type": rtype, "count": cnt}
                    for rtype, cnt in sorted(by_type.items(), key=lambda x: -x[1])
                ],
                "by_resource_group": [
                    {"name": grp, "count": cnt}
                    for grp, cnt in sorted(by_rg.items(), key=lambda x: -x[1])
                ],
            },
        )

        # Full
        full = [
            "=" * 120,
            f"  AZURE RESOURCE INVENTORY — FULL  ({total} resources)",
            "=" * 120,
            f"  {'Name':<40} {'Type':<50} {'RG':<25} Location",
            "  " + "-" * 116,
        ]
        for r in sorted(resources, key=lambda x: (x.type or "", x.name or "")):
            name = (r.name or "")[:40]
            rtype = (r.type or "")[:50]
            grp = _rg(r.id or "")[:25]
            loc = r.location or "N/A"
            full.append(f"  {name:<40} {rtype:<50} {grp:<25} {loc}")
        full += ["=" * 120, ""]
        self._save(self._fname("60b_azure_resource_inventory_full.txt"), "\n".join(full))

    # ── Orphaned Resources ────────────────────────────────────────────────────

    async def _collect_orphaned_resources(self) -> None:
        orphans: list[str] = []
        found: list[dict] = []
        # A listing that failed is written among the orphans so a reader sees
        # it, but it is not one: counted in "(N found)", a refused disk
        # listing raised an orphaned-resource finding for a tenant with none.
        errors: list[dict] = []

        # Unattached managed disks
        try:
            compute = self.auth.compute_client_for(self._sub_id)
            disks = await _run_sync(lambda: list(compute.disks.list()))
            for d in disks:
                if not d.managed_by:
                    grp = _rg(d.id or "")
                    orphans.append(
                        f"  DISK (unattached)     : {(d.name or ''):<40}  "
                        f"{d.disk_size_gb or 0:>5} GB  {(d.sku.name if d.sku else 'N/A'):<20}  RG: {grp}"
                    )
                    found.append(
                        {
                            "type": "DISK",
                            "status": "unattached",
                            "name": d.name,
                            "resource_group": grp,
                            "size_gb": d.disk_size_gb or 0,
                            "sku": _enum_text(d.sku.name) if d.sku else None,
                        }
                    )
        except Exception as ex:
            orphans.append(f"  DISK (list error)     : {ex}")
            errors.append({"listing": "disks", "error": str(ex)})

        # Unattached NICs + Public IPs
        try:
            network = self.auth.network_client_for(self._sub_id)
            nics = await _run_sync(lambda: list(network.network_interfaces.list_all()))
            for nic in nics:
                if not nic.virtual_machine:
                    grp = _rg(nic.id or "")
                    orphans.append(f"  NIC (unattached)      : {(nic.name or ''):<40}  RG: {grp}")
                    found.append(
                        {
                            "type": "NIC",
                            "status": "unattached",
                            "name": nic.name,
                            "resource_group": grp,
                        }
                    )

            pips = await _run_sync(lambda: list(network.public_ip_addresses.list_all()))
            for pip in pips:
                if not pip.ip_configuration:
                    grp = _rg(pip.id or "")
                    orphans.append(
                        f"  PUBLIC IP (unattached): {(pip.name or ''):<40}  "
                        f"IP: {(pip.ip_address or 'unassigned'):<18}  RG: {grp}"
                    )
                    found.append(
                        {
                            "type": "PUBLIC IP",
                            "status": "unattached",
                            "name": pip.name,
                            "resource_group": grp,
                            "ip_address": pip.ip_address,
                        }
                    )
        except Exception as ex:
            orphans.append(f"  NETWORK (list error)  : {ex}")
            errors.append({"listing": "network", "error": str(ex)})

        lines = [
            "=" * 100,
            f"  AZURE ORPHANED RESOURCES  ({len(orphans) - len(errors)} found)",
            "=" * 100,
        ]
        lines += orphans if orphans else ["  No orphaned resources detected."]
        lines += ["=" * 100, ""]
        self._save(self._fname("61_azure_orphaned_resources.txt"), "\n".join(lines))
        # The orphans and the listings that failed, apart: a listing that
        # failed is no orphan, and leaves the count a lower bound.
        self._save_sidecar(
            self._fname("61_azure_orphaned_resources.txt"),
            {"count": len(found), "orphans": found, "errors": errors},
        )

    # ── Cost Analysis (ARM REST) ──────────────────────────────────────────────

    async def _collect_cost(self) -> None:
        sub_id = self._sub_id
        url = _ARM_COST_API.format(sub_id=sub_id)

        try:
            # Use sync credential for ARM token (async credential may not work for ARM)
            cred = self.auth._az_credential()
            token = cred.get_token(_ARM_SCOPE)
            headers = {
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
            }
        except Exception as ex:
            self._save(
                self._fname("50_azure_cost_by_service.txt"), f"Cost data unavailable: {ex}\n"
            )
            self._save(self._fname("50b_azure_cost_by_rg.txt"), f"Cost data unavailable: {ex}\n")
            return

        for base_filename, group_dim in [
            ("50_azure_cost_by_service.txt", "ServiceName"),
            ("50b_azure_cost_by_rg.txt", "ResourceGroupName"),
        ]:
            body = {
                "type": "ActualCost",
                "timeframe": "MonthToDate",
                "dataset": {
                    "granularity": "None",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": group_dim}],
                },
            }
            try:
                async with httpx.AsyncClient(timeout=60) as c:
                    resp = await c.post(url, headers=headers, json=body)
                lines = self._format_cost(resp, group_dim)
            except Exception as ex:
                lines = f"Cost data unavailable: {ex}\n"
            self._save(self._fname(base_filename), lines)

    @staticmethod
    def _format_cost(resp: httpx.Response, group_dim: str) -> str:
        title = f"AZURE COST — BY {group_dim.upper()}  (Month-to-Date)"
        hdr = ["=" * 80, f"  {title}", "=" * 80]
        try:
            resp.raise_for_status()
            props = resp.json().get("properties", {})
            columns = [c["name"] for c in props.get("columns", [])]
            rows = sorted(props.get("rows", []), key=lambda r: -float(r[0]))
            if not rows:
                return "\n".join([*hdr, "  No cost data available for this period.", ""])
            lines = [*hdr, f"  {'Name':<50} {'Cost':>14}  Currency", "  " + "-" * 70]
            for row in rows[:40]:
                row_d = dict(zip(columns, row, strict=False))
                cost = float(row_d.get("Cost", 0))
                currency = row_d.get("Currency", "USD")
                name_col = next((c for c in columns if c not in ("Cost", "Currency")), "Name")
                name = str(row_d.get(name_col, "N/A"))[:50]
                lines.append(f"  {name:<50} {cost:>14.2f}  {currency}")
            lines += ["=" * 80, ""]
            return "\n".join(lines)
        except Exception as ex:
            if resp.status_code in (400, 403, 404):
                return "\n".join(
                    [
                        *hdr,
                        "  Cost Management er ikke tilgjengelig for denne subscription.",
                        "  Dette kan skyldes manglende 'Cost Management Reader'-rolle",
                        "  eller at subscription ikke stotter Cost Management API.",
                        f"  (HTTP {resp.status_code})",
                        "",
                    ]
                )
            return "\n".join([*hdr, f"  Error: {ex}", f"  HTTP {resp.status_code}", ""])
