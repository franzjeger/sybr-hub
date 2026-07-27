"""Section 30 — Azure Compute: VMs, CPU Metrics, AVD.

Azure SDK clients are synchronous; each call is dispatched to a thread-pool
executor so as not to block the asyncio event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthManager


def _run_sync(fn):
    """Run a synchronous callable in the default thread-pool executor."""
    return asyncio.get_event_loop().run_in_executor(None, fn)


class AzureComputeSection(BaseSection):
    name = "Azure Compute"

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
            self.name = f"Azure Compute ({sub_name})"
            self.result.name = self.name

    def _fname(self, base: str) -> str:
        """Return filename with optional subscription prefix for multi-sub mode."""
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
            vms = await self._collect_vms()
            await self._collect_vm_metrics(vms)
            await self._collect_avd()
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── Virtual Machines ──────────────────────────────────────────────────────

    async def _collect_vms(self) -> list[Any]:
        try:
            client = self.auth.compute_client_for(self._sub_id)
            vms    = await _run_sync(lambda: list(client.virtual_machines.list_all()))
        except Exception as ex:
            self._save(self._fname("30_azure_vms.txt"), f"Error listing VMs: {ex}\n")
            # Surface it in the section result too — an enumeration that
            # failed must not read as "this subscription has no VMs".
            self._warn(f"Could not list VMs for {self._sub_name or self._sub_id}: {ex}")
            return []

        sub_label = f"  [{self._sub_name}]" if self._multi else ""
        lines = [
            "=" * 120,
            f"  AZURE VIRTUAL MACHINES  ({len(vms)} total){sub_label}",
            "=" * 120,
            f"  {'VM Name':<35} {'Resource Group':<28} {'Location':<15} {'OS':<10} {'Size':<22} Status",
            "  " + "-" * 116,
        ]
        for vm in vms:
            name   = (vm.name or "")[:35]
            rg     = ((vm.id or "").split("/")[4] if vm.id else "N/A")[:28]
            loc    = (vm.location or "")[:15]
            os_type = str(
                vm.storage_profile.os_disk.os_type
                if vm.storage_profile and vm.storage_profile.os_disk
                else "N/A"
            )[:10]
            size   = (
                vm.hardware_profile.vm_size if vm.hardware_profile else "N/A"
            )
            size   = (size or "N/A")[:22]
            status = "N/A"
            if vm.instance_view and vm.instance_view.statuses:
                for s in vm.instance_view.statuses:
                    if s.code and s.code.startswith("PowerState/"):
                        status = s.code.replace("PowerState/", "")
                        break
            lines.append(
                f"  {name:<35} {rg:<28} {loc:<15} {os_type:<10} {size:<22} {status}"
            )

        lines += ["=" * 120, ""]
        self._save(self._fname("30_azure_vms.txt"), "\n".join(lines))
        return vms

    # ── VM CPU Metrics ────────────────────────────────────────────────────────

    async def _collect_vm_metrics(self, vms: list[Any]) -> None:
        if not vms:
            self._save(self._fname("30b_azure_vm_cpu_metrics.txt"), "No VMs found.\n")
            return

        try:
            mon_client = self.auth.monitor_client_for(self._sub_id)
        except Exception as ex:
            self._save(self._fname("30b_azure_vm_cpu_metrics.txt"), f"Error creating monitor client: {ex}\n")
            return

        end_time   = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)
        timespan   = f"{start_time.isoformat()}/{end_time.isoformat()}"

        lines = [
            "=" * 100,
            "  AZURE VM CPU METRICS  (last 7 days — daily average %)",
            "=" * 100,
            f"  {'VM Name':<40} {'7d Avg CPU':>12}  Daily Breakdown",
            "  " + "-" * 96,
        ]

        for vm in vms:
            vm_name = (vm.name or "")[:40]
            try:
                metrics_resp = await _run_sync(lambda vm=vm: mon_client.metrics.list(
                    vm.id,
                    timespan=timespan,
                    interval="P1D",
                    metricnames="Percentage CPU",
                    aggregation="Average",
                ))
                values: list[float] = []
                for metric in metrics_resp.value:
                    for ts in metric.timeseries:
                        for dp in ts.data:
                            if dp.average is not None:
                                values.append(dp.average)
                avg   = sum(values) / len(values) if values else 0.0
                daily = ", ".join(f"{v:.1f}%" for v in values[-7:])
            except Exception as ex:
                avg   = -1.0
                daily = f"Error: {ex}"

            avg_str = f"{avg:.1f}%" if avg >= 0 else "N/A"
            lines.append(f"  {vm_name:<40} {avg_str:>12}  {daily}")

        lines += ["=" * 100, ""]
        self._save(self._fname("30b_azure_vm_cpu_metrics.txt"), "\n".join(lines))

    # ── Azure Virtual Desktop ─────────────────────────────────────────────────

    async def _collect_avd(self) -> None:
        try:
            avd_client = self.auth.avd_client_for(self._sub_id)
            host_pools = await _run_sync(
                lambda: list(avd_client.host_pools.list())
            )
        except Exception as ex:
            self._save(self._fname("40_avd.txt"), f"Error listing AVD host pools: {ex}\n")
            self._warn(f"Could not list AVD host pools for {self._sub_name or self._sub_id}: {ex}")
            return

        if not host_pools:
            self._save(self._fname("40_avd.txt"), "No AVD host pools found in this subscription.\n")
            return

        lines = [
            "=" * 110,
            f"  AZURE VIRTUAL DESKTOP  ({len(host_pools)} host pool(s))",
            "=" * 110,
        ]

        for hp in host_pools:
            hp_name = hp.name or "N/A"
            rg      = ((hp.id or "").split("/")[4] if hp.id else "N/A")
            lines += [
                f"\n  Host Pool  : {hp_name}",
                f"  Resource Grp: {rg}",
                f"    Pool Type          : {hp.host_pool_type}",
                f"    Load Balancer Type : {hp.load_balancer_type}",
                f"    Max Session Limit  : {hp.max_session_limit}",
                f"    Personal Desktop   : {hp.personal_desktop_assignment_type or 'N/A'}",
            ]

            try:
                session_hosts = await _run_sync(
                    lambda rg=rg, hp_name=hp_name: list(
                        avd_client.session_hosts.list(rg, hp_name)
                    )
                )
                lines.append(f"    Session Hosts      : {len(session_hosts)}")
                for sh in session_hosts:
                    sh_short = (sh.name or "").split("/")[-1]
                    sessions = sh.sessions or 0
                    agent    = sh.agent_version or "N/A"
                    status   = sh.status or "N/A"
                    lines.append(
                        f"      - {sh_short:<35}  Status:{status:<15} "
                        f"Sessions:{sessions}  Agent:{agent}"
                    )
            except Exception as ex:
                lines.append(f"    Session Hosts      : Error — {ex}")

        lines += ["", "=" * 110, ""]
        self._save(self._fname("40_avd.txt"), "\n".join(lines))
