"""Section 31–34 — Azure Network: VNets, NSGs, Public IPs, VPN Gateways, Orphans.

Azure SDK clients are synchronous; dispatched to a thread-pool executor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.modules.base import BaseSection, SectionResult, SectionStatus
from app.modules.m365_audit.auth import AuthManager


def _run_sync(fn):
    return asyncio.get_event_loop().run_in_executor(None, fn)


class AzureNetworkSection(BaseSection):
    name = "Azure Network"

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
            self.name = f"Azure Network ({sub_name})"
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
            orphan_lines: list[str] = []
            await self._collect_vnets()
            await self._collect_nsgs()
            orphan_lines += await self._collect_public_ips()
            await self._collect_vpn_gateways()
            orphan_lines += await self._collect_orphaned_nics()
            await self._save_orphans(orphan_lines)
            self._report(SectionStatus.DONE)
        except Exception as e:
            self._report(SectionStatus.FAILED, str(e))
        return self.result

    # ── VNets ─────────────────────────────────────────────────────────────────

    async def _collect_vnets(self) -> None:
        try:
            client = self.auth.network_client_for(self._sub_id)
            vnets  = await _run_sync(lambda: list(client.virtual_networks.list_all()))
        except Exception as ex:
            self._save(self._fname("31_azure_vnets.txt"), f"Error: {ex}\n")
            return

        sub_label = f"  [{self._sub_name}]" if self._multi else ""
        lines = [
            "=" * 110,
            f"  AZURE VIRTUAL NETWORKS  ({len(vnets)} total){sub_label}",
            "=" * 110,
        ]
        for vnet in vnets:
            rg      = ((vnet.id or "").split("/")[4] if vnet.id else "N/A")
            prefixes = ", ".join(vnet.address_space.address_prefixes) if vnet.address_space else "N/A"
            lines += [
                f"\n  VNet: {vnet.name}  (RG: {rg})",
                f"    Address Space : {prefixes}",
                f"    Location      : {vnet.location}",
                f"    Subnets ({len(vnet.subnets or [])}):",
            ]
            for sub in vnet.subnets or []:
                nsg = "YES" if sub.network_security_group else "no"
                lines.append(
                    f"      - {(sub.name or ''):<35} {sub.address_prefix:<20} NSG: {nsg}"
                )
        lines += ["", "=" * 110, ""]
        self._save(self._fname("31_azure_vnets.txt"), "\n".join(lines))

    # ── NSGs ──────────────────────────────────────────────────────────────────

    async def _collect_nsgs(self) -> None:
        try:
            client = self.auth.network_client_for(self._sub_id)
            nsgs   = await _run_sync(
                lambda: list(client.network_security_groups.list_all())
            )
        except Exception as ex:
            self._save(self._fname("32_azure_nsgs.txt"), f"Error: {ex}\n")
            return

        lines = [
            "=" * 110,
            f"  AZURE NETWORK SECURITY GROUPS  ({len(nsgs)} total)",
            "=" * 110,
        ]
        for nsg in nsgs:
            rg    = ((nsg.id or "").split("/")[4] if nsg.id else "N/A")
            rules = sorted(nsg.security_rules or [], key=lambda r: r.priority)
            lines += [
                f"\n  NSG: {nsg.name}  (RG: {rg}  Location: {nsg.location})",
                f"    Rules ({len(rules)}):",
            ]
            for r in rules:
                dst_ports = r.destination_port_range or ", ".join(
                    r.destination_port_ranges or []
                )
                flag = ""
                if r.access == "Allow" and dst_ports == "*":
                    flag = "  *** WILDCARD ALLOW ***"
                    self._warn(
                        f"NSG '{nsg.name}' rule '{r.name}' allows all ports inbound/outbound"
                    )
                lines.append(
                    f"      [{r.access:<6}] P:{r.priority:<6} {(r.name or ''):<40} "
                    f"{r.direction:<10} "
                    f"Src:{r.source_address_prefix or '*':<18} "
                    f"-> Dst:{r.destination_address_prefix or '*':<18} "
                    f"Port:{dst_ports}{flag}"
                )
        lines += ["", "=" * 110, ""]
        self._save(self._fname("32_azure_nsgs.txt"), "\n".join(lines))

        # ── Analyse risky inbound rules ──────────────────────────────────────
        HIGH_RISK_PORTS = {"22", "3389", "445", "1433", "3306", "5432"}
        OPEN_SOURCES = {"*", "0.0.0.0/0", "Internet"}
        risky_lines: list[str] = []

        for nsg in nsgs:
            for r in nsg.security_rules or []:
                if r.access != "Allow" or r.direction != "Inbound":
                    continue
                src = r.source_address_prefix or ""
                if src not in OPEN_SOURCES:
                    continue

                dst_ports = r.destination_port_range or ""
                dst_port_list = r.destination_port_ranges or []
                all_ports = [dst_ports] + list(dst_port_list) if dst_ports else list(dst_port_list)

                is_risky = False
                matched_ports: list[str] = []

                for port_spec in all_ports:
                    if port_spec == "*":
                        is_risky = True
                        matched_ports.append("*")
                        continue
                    # Check for high-risk ports (single port or range)
                    if "-" in port_spec:
                        try:
                            lo, hi = port_spec.split("-", 1)
                            lo_int, hi_int = int(lo), int(hi)
                            for hp in HIGH_RISK_PORTS:
                                if lo_int <= int(hp) <= hi_int:
                                    is_risky = True
                                    matched_ports.append(hp)
                        except ValueError:
                            pass
                    elif port_spec in HIGH_RISK_PORTS:
                        is_risky = True
                        matched_ports.append(port_spec)

                if is_risky:
                    ports_str = ", ".join(sorted(set(matched_ports)))
                    detail = (
                        f"NSG '{nsg.name}' rule '{r.name}' (priority {r.priority}): "
                        f"allows inbound from {src} to port(s) {ports_str}"
                    )
                    risky_lines.append(f"  ⚠ {detail}")
                    self._warn(detail)

        if risky_lines:
            warn_content = [
                "=" * 110,
                "  RISKY NSG INBOUND RULES — Allow from Internet/Any",
                "=" * 110,
                "",
            ] + risky_lines + ["", "=" * 110, ""]
            self._save(
                self._fname("32b_azure_nsg_risky_rules_WARN.txt"),
                "\n".join(warn_content),
            )

    # ── Public IPs ────────────────────────────────────────────────────────────

    async def _collect_public_ips(self) -> list[str]:
        orphans: list[str] = []
        try:
            client = self.auth.network_client_for(self._sub_id)
            pips   = await _run_sync(
                lambda: list(client.public_ip_addresses.list_all())
            )
        except Exception as ex:
            self._save(self._fname("33_azure_public_ips.txt"), f"Error: {ex}\n")
            return orphans

        lines = [
            "=" * 110,
            f"  AZURE PUBLIC IP ADDRESSES  ({len(pips)} total)",
            "=" * 110,
            f"  {'Name':<35} {'IP Address':<20} {'SKU':<10} {'Alloc':<12} {'Attached':>9}  DNS",
            "  " + "-" * 106,
        ]
        for pip in pips:
            name      = (pip.name or "")[:35]
            ip_addr   = (pip.ip_address or "unassigned")[:20]
            sku       = (pip.sku.name if pip.sku else "N/A")[:10]
            alloc     = (pip.public_ip_allocation_method or "N/A")[:12]
            attached  = "Yes" if pip.ip_configuration else "No"
            fqdn      = (pip.dns_settings.fqdn if pip.dns_settings else "") or ""
            lines.append(
                f"  {name:<35} {ip_addr:<20} {sku:<10} {alloc:<12} {attached:>9}  {fqdn}"
            )
            if not pip.ip_configuration:
                rg = ((pip.id or "").split("/")[4] if pip.id else "N/A")
                orphans.append(
                    f"  Unattached Public IP : {pip.name:<35}  IP: {ip_addr:<20}  RG: {rg}"
                )
        lines += ["=" * 110, ""]
        self._save(self._fname("33_azure_public_ips.txt"), "\n".join(lines))
        return orphans

    # ── VPN Gateways ──────────────────────────────────────────────────────────

    async def _collect_vpn_gateways(self) -> None:
        try:
            client = self.auth.network_client_for(self._sub_id)
            gws    = await _run_sync(
                lambda: list(client.virtual_network_gateways.list_all())
            )
        except Exception as ex:
            self._save(self._fname("34_azure_vpn_gateways.txt"), f"Error: {ex}\n")
            return

        if not gws:
            self._save(self._fname("34_azure_vpn_gateways.txt"), "No VPN Gateways found.\n")
            return

        lines = [
            "=" * 100,
            f"  AZURE VPN GATEWAYS  ({len(gws)} total)",
            "=" * 100,
        ]
        for gw in gws:
            rg  = ((gw.id or "").split("/")[4] if gw.id else "N/A")
            sku = gw.sku.name if gw.sku else "N/A"
            lines += [
                f"\n  Gateway : {gw.name}  (RG: {rg})",
                f"    SKU       : {sku}",
                f"    BGP       : {gw.enable_bgp}",
                f"    Location  : {gw.location}",
                f"    VPN Type  : {gw.vpn_type}",
            ]
            try:
                conns = await _run_sync(
                    lambda rg=rg: list(
                        client.virtual_network_gateway_connections.list(rg)
                    )
                )
                lines.append(f"    Connections ({len(conns)}):")
                for c in conns:
                    lines.append(
                        f"      - {(c.name or ''):<40}  Status: {c.connection_status:<20}  "
                        f"Type: {c.connection_type}"
                    )
            except Exception as ex:
                lines.append(f"    Connections: Error — {ex}")

        lines += ["", "=" * 100, ""]
        self._save(self._fname("34_azure_vpn_gateways.txt"), "\n".join(lines))

    # ── Orphaned NICs ─────────────────────────────────────────────────────────

    async def _collect_orphaned_nics(self) -> list[str]:
        orphans: list[str] = []
        try:
            client = self.auth.network_client_for(self._sub_id)
            nics   = await _run_sync(
                lambda: list(client.network_interfaces.list_all())
            )
            for nic in nics:
                if not nic.virtual_machine:
                    rg = ((nic.id or "").split("/")[4] if nic.id else "N/A")
                    orphans.append(
                        f"  Unattached NIC       : {(nic.name or ''):<35}  RG: {rg}"
                    )
        except Exception:
            pass
        return orphans

    # ── Save orphan list ──────────────────────────────────────────────────────

    async def _save_orphans(self, lines: list[str]) -> None:
        # This file may be appended to by azure_governance as well.
        # If governance hasn't run yet, write our portion here.
        if lines:
            header = [
                "=" * 90,
                "  AZURE ORPHANED RESOURCES (from Network section)",
                "=" * 90,
            ]
            self._save(self._fname("61_azure_orphaned_resources.txt"), "\n".join(header + lines) + "\n")
