"""Live dashboard poller — polls FortiGate and UniFi devices at configurable intervals.

Maintains an in-memory cache of device status and broadcasts updates via
registered WebSocket callbacks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceStatus:
    device_id: str
    customer_id: str
    vendor: str  # "fortigate" | "unifi"
    name: str
    model: str
    firmware: str
    serial: str
    status: str  # "online" | "offline" | "error"
    uptime: str
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    wan_ip: Optional[str] = None
    sessions: Optional[int] = None
    vpn_tunnels: Optional[int] = None
    clients: Optional[int] = None
    ha_mode: Optional[str] = None
    upgrade_available: Optional[str] = None
    last_poll: Optional[str] = None
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "device_id": self.device_id,
            "customer_id": self.customer_id,
            "vendor": self.vendor,
            "name": self.name,
            "model": self.model,
            "firmware": self.firmware,
            "serial": self.serial,
            "status": self.status,
            "uptime": self.uptime,
            "last_poll": self.last_poll,
        }
        for attr in ("cpu_pct", "mem_pct", "wan_ip", "sessions", "vpn_tunnels",
                      "clients", "ha_mode", "upgrade_available", "error"):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        if self.extra:
            d["extra"] = self.extra
        return d


# Callback type: async function that receives a list of DeviceStatus dicts
BroadcastFn = Callable[[list[dict]], Coroutine[Any, Any, None]]


class DashboardPoller:
    """Polls network devices and broadcasts status updates."""

    def __init__(self) -> None:
        self._cache: dict[str, DeviceStatus] = {}  # device_id -> latest status
        self._subscriptions: dict[str, set[str]] = {}  # ws_id -> set of customer_ids
        self._broadcast_fns: dict[str, BroadcastFn] = {}  # ws_id -> callback
        self._poll_task: Optional[asyncio.Task] = None
        self._interval: int = 60  # seconds
        self._running = False

    # ── Subscription management ──────────────────────────────────────────

    def subscribe(self, ws_id: str, customer_ids: list[str], callback: BroadcastFn) -> None:
        self._subscriptions[ws_id] = set(customer_ids)
        self._broadcast_fns[ws_id] = callback
        # Start polling if not running
        if not self._running and self._subscriptions:
            self.start()

    def unsubscribe(self, ws_id: str) -> None:
        self._subscriptions.pop(ws_id, None)
        self._broadcast_fns.pop(ws_id, None)
        # Stop if no subscribers
        if not self._subscriptions and self._running:
            self.stop()

    def update_subscription(self, ws_id: str, customer_ids: list[str]) -> None:
        if ws_id in self._subscriptions:
            self._subscriptions[ws_id] = set(customer_ids)

    def set_interval(self, seconds: int) -> None:
        self._interval = max(10, min(300, seconds))

    # ── Cache access ─────────────────────────────────────────────────────

    def get_devices(self, customer_id: Optional[str] = None) -> list[dict]:
        """Return cached device statuses, optionally filtered by customer."""
        devices = self._cache.values()
        if customer_id:
            devices = [d for d in devices if d.customer_id == customer_id]
        # Sort: offline first, then by name
        return sorted(
            [d.to_dict() for d in devices],
            key=lambda x: (0 if x["status"] == "offline" else 1, x["name"].lower()),
        )

    # ── Polling lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Dashboard poller started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        logger.info("Dashboard poller stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._poll_all()
                await self._broadcast_updates()
            except Exception as e:
                logger.error("Dashboard poll error: %s", e, exc_info=True)
            await asyncio.sleep(self._interval)

    async def poll_now(self, customer_id: Optional[str] = None) -> list[dict]:
        """Force an immediate poll and return results."""
        await self._poll_all(customer_id_filter=customer_id)
        return self.get_devices(customer_id)

    # ── Polling implementation ───────────────────────────────────────────

    async def _poll_all(self, customer_id_filter: Optional[str] = None) -> None:
        """Poll all subscribed customers' devices."""
        # Determine which customers to poll
        customer_ids: set[str] = set()
        if customer_id_filter:
            customer_ids.add(customer_id_filter)
        else:
            for cids in self._subscriptions.values():
                customer_ids.update(cids)

        if not customer_ids:
            return

        tasks = [self._poll_customer(cid) for cid in customer_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Poll failed for a customer: %s", result)

    async def _poll_customer(self, customer_id: str) -> None:
        """Poll all devices for a single customer."""
        from app.core.credentials import get_secret
        from app.core.customer import CustomerManager

        customer = CustomerManager.get_customer(customer_id)
        if not customer:
            return

        now = datetime.now(timezone.utc).isoformat()

        # ── FortiGate ──
        fg_host = customer.get("FortiGateHost")
        fg_token = get_secret(customer_id, "fortigate_api_token") if fg_host else None
        if fg_host and fg_token:
            await self._poll_fortigate(customer_id, customer, fg_host, fg_token, now)

        # ── UniFi ──
        uf_host = customer.get("UniFiHost")
        uf_mode = customer.get("UniFiMode", "controller")
        if uf_host and uf_mode == "controller":
            await self._poll_unifi_controller(customer_id, customer, now)
        elif customer.get("UniFiDirectDevices"):
            await self._poll_unifi_direct(customer_id, customer, now)

    async def _poll_fortigate(
        self, customer_id: str, customer: dict, host: str, token: str, now: str
    ) -> None:
        from app.modules.fortigate_audit.client import FortiGateClient

        device_id = f"fg_{customer_id}"
        try:
            async with FortiGateClient(
                host, token,
                port=int(customer.get("FortiGatePort", 443)),
                vdom=customer.get("FortiGateVDOM", "root"),
                verify_ssl=customer.get("FortiGateVerifySSL", False),
            ) as fg:
                # Fetch multiple endpoints in parallel
                import asyncio as _aio
                status, perf, firmware, interfaces, license_info, vpn_tunnels, policies, ha_status, csf, vdom_res = await _aio.gather(
                    fg.get_system_status(),
                    fg.get_monitor("system/performance/status"),
                    fg.get_monitor("system/firmware"),
                    fg.get_monitor("system/interface"),
                    fg.get_monitor("license/status"),
                    fg.get_monitor("vpn/ipsec"),
                    fg.get_cmdb("firewall/policy"),
                    fg.get_cmdb("system/ha"),
                    fg.get_monitor("system/csf"),
                    fg.get_monitor("system/vdom-resource"),
                    return_exceptions=True,
                )

                # The status read establishes reachability. If it refused, the
                # firewall is not online — recording it as such put a green row
                # in the dashboard for a device that answered nothing, because
                # the sentinel is not an exception and the cache write below
                # hard-codes "online".
                from app.modules.api_result import read_error, read_failed
                if isinstance(status, Exception) or read_failed(status):
                    reason = str(status) if isinstance(status, Exception) else read_error(status)
                    self._cache[device_id] = DeviceStatus(
                        device_id=device_id, customer_id=customer_id,
                        vendor="fortigate", name=host, model="", firmware="",
                        serial="", status="error", uptime="",
                        error=reason, last_poll=now,
                    )
                    return

                # Parse CPU — use top-level user+system, or calc from cores
                cpu = None
                if isinstance(perf, dict):
                    cpu_data = perf.get("cpu", {})
                    if isinstance(cpu_data, dict):
                        user = cpu_data.get("user", 0)
                        system = cpu_data.get("system", 0)
                        cpu = user + system if (user or system) else None
                        if cpu is None and "cores" in cpu_data:
                            cores = cpu_data["cores"]
                            if isinstance(cores, list) and cores:
                                cpu = round(sum(100 - c.get("idle", 100) for c in cores) / len(cores), 1)

                # Parse memory — calc percent from total/used
                mem = None
                if isinstance(perf, dict):
                    mem_data = perf.get("mem", {})
                    if isinstance(mem_data, dict):
                        total = mem_data.get("total", 0)
                        used = mem_data.get("used", 0)
                        if total > 0:
                            mem = round((used / total) * 100, 1)

                # Firmware version from system/firmware
                fw_version = ""
                if isinstance(firmware, dict):
                    current = firmware.get("current", {})
                    fw_version = current.get("version", "")

                # Serial — try CSF first (most reliable), then status
                serial = ""
                if isinstance(csf, dict):
                    fg_devices = csf.get("devices", {}).get("fortigate", [])
                    if isinstance(fg_devices, list) and fg_devices:
                        serial = fg_devices[0].get("serial", "")
                if not serial and isinstance(status, dict):
                    serial = status.get("serial", "")

                # WAN IP — from interfaces dict (key = interface name)
                wan_ip = None
                if isinstance(interfaces, dict):
                    for iface_name in ("wan", "wan1", "port1"):
                        iface = interfaces.get(iface_name)
                        if isinstance(iface, dict) and iface.get("ip") and iface["ip"] != "0.0.0.0":
                            wan_ip = iface["ip"]
                            break
                # Fallback from license/status
                if not wan_ip and isinstance(license_info, dict):
                    fg_info = license_info.get("fortiguard", {})
                    if isinstance(fg_info, dict):
                        wan_ip = fg_info.get("fortigate_wan_ip")

                # Count VPN tunnels — vpn/ipsec returns a list directly. None on
                # a refused read (a failed ApiList is still a list, so the
                # read_failed check must come first), rather than a 0 that reads
                # as "no tunnels configured" on an otherwise-online firewall.
                if isinstance(vpn_tunnels, Exception) or read_failed(vpn_tunnels):
                    vpn_count = None
                elif isinstance(vpn_tunnels, list):
                    vpn_count = len(vpn_tunnels)
                elif isinstance(vpn_tunnels, dict):
                    vpn_list = vpn_tunnels.get("results", vpn_tunnels.get("data", []))
                    vpn_count = len(vpn_list) if isinstance(vpn_list, list) else 0
                else:
                    vpn_count = None

                # Count policies — None on a refused read, not a misleading 0
                # (which reads as an unconfigured firewall).
                if isinstance(policies, Exception) or read_failed(policies):
                    policy_count = None
                elif isinstance(policies, list):
                    policy_count = len(policies)
                else:
                    policy_count = None

                # HA mode
                ha_mode = "Standalone"
                if isinstance(ha_status, list) and ha_status:
                    ha_mode = ha_status[0].get("mode", "standalone").capitalize()
                elif isinstance(ha_status, dict):
                    ha_mode = ha_status.get("mode", "standalone").capitalize()

                # Session count — try perf, then vdom-resource
                sessions = None
                if isinstance(perf, dict):
                    sess = perf.get("session", {})
                    if isinstance(sess, dict):
                        sessions = sess.get("current")
                if sessions is None and isinstance(vdom_res, dict):
                    sess = vdom_res.get("session", {})
                    if isinstance(sess, dict):
                        sessions = sess.get("current_usage")

                # Memory fallback from vdom-resource
                if mem is None and isinstance(vdom_res, dict):
                    vdom_mem = vdom_res.get("memory")
                    if isinstance(vdom_mem, (int, float)) and vdom_mem > 0:
                        mem = float(vdom_mem)

                # Uptime — calculate from CSF state.utc_last_reboot (ms timestamp)
                uptime_str = ""
                if isinstance(csf, dict):
                    fg_devices = csf.get("devices", {}).get("fortigate", [])
                    if isinstance(fg_devices, list) and fg_devices:
                        state = fg_devices[0].get("state", {})
                        reboot_ms = state.get("utc_last_reboot", 0) if isinstance(state, dict) else 0
                        if reboot_ms > 0:
                            import time as _time

                            from app.core.utils import format_uptime
                            secs = int(_time.time()) - (reboot_ms // 1000)
                            if secs > 0:
                                uptime_str = format_uptime(secs)
                if not uptime_str and isinstance(status, dict) and status.get("uptime"):
                    uptime_str = str(status["uptime"])
                if not uptime_str and isinstance(perf, dict) and perf.get("uptime"):
                    from app.core.utils import format_uptime
                    uptime_str = format_uptime(int(perf["uptime"]))

                # Build rich extra data for detail view
                # Interfaces
                iface_list = []
                if isinstance(interfaces, dict):
                    for iname, idata in interfaces.items():
                        if isinstance(idata, dict):
                            iface_list.append({
                                "name": iname,
                                "ip": idata.get("ip", ""),
                                "link": idata.get("link", False),
                                "speed": idata.get("speed", 0),
                            })

                # VPN tunnels detail
                vpn_detail = []
                if isinstance(vpn_tunnels, list):
                    for v in vpn_tunnels:
                        vpn_detail.append({
                            "name": v.get("name", ""),
                            "remote_gw": v.get("rgwy", ""),
                            "status": "up" if v.get("wizard-type") else "down",
                        })

                # Policies — all rules with security profile info
                policy_summary = []
                if isinstance(policies, list):
                    for p in policies:
                        src = [s.get("name", "") for s in p.get("srcaddr", [])]
                        dst = [d.get("name", "") for d in p.get("dstaddr", [])]
                        svc = [s.get("name", "") for s in p.get("service", [])]
                        # Security profiles attached to this rule
                        profiles = []
                        for prof_key in ("av-profile", "webfilter-profile", "ips-sensor",
                                         "application-list", "ssl-ssh-profile", "dnsfilter-profile"):
                            pval = p.get(prof_key, "")
                            if pval:
                                profiles.append(prof_key.replace("-profile", "").replace("-sensor", "").replace("-list", ""))
                        policy_summary.append({
                            "id": p.get("policyid"),
                            "name": p.get("name", ""),
                            "action": p.get("action", ""),
                            "enabled": p.get("status", "enable") == "enable",
                            "src": ", ".join(src),
                            "dst": ", ".join(dst),
                            "svc": ", ".join(svc),
                            "log": p.get("logtraffic", ""),
                            "srcintf": ", ".join(s.get("name", "") for s in p.get("srcintf", [])),
                            "dstintf": ", ".join(s.get("name", "") for s in p.get("dstintf", [])),
                            "nat": p.get("nat", "") == "enable",
                            "profiles": profiles,
                        })

                # Fetch additional data in parallel
                dhcp_raw, dns_raw, admins, ssl_vpn, static_routes, sdwan, iface_cmdb, log_stats = await _aio.gather(
                    fg.get_cmdb("system.dhcp/server"),
                    fg.get_cmdb("system/dns"),
                    fg.get_cmdb("system/admin"),
                    fg.get_monitor("vpn/ssl"),
                    fg.get_cmdb("router/static"),
                    fg.get_monitor("system/sd-wan/status"),
                    fg.get_cmdb("system/interface"),
                    fg.get_monitor("log/stats"),
                    return_exceptions=True,
                )

                # DHCP
                dhcp_list = []
                if isinstance(dhcp_raw, list):
                    for d in dhcp_raw:
                        ranges = d.get("ip-range", [])
                        r_str = f"{ranges[0].get('start-ip','')}-{ranges[0].get('end-ip','')}" if ranges else ""
                        dhcp_list.append({"interface": d.get("interface", ""), "range": r_str})

                # DNS
                dns_info = {}
                if isinstance(dns_raw, dict):
                    dns_info = {"primary": dns_raw.get("primary", ""), "secondary": dns_raw.get("secondary", "")}

                # Admins
                from app.services.fortigate_api import admin_trusthost_is_open
                admin_list = []
                if isinstance(admins, list):
                    for a in admins:
                        admin_list.append({
                            "name": a.get("name", ""),
                            "profile": a.get("accprofile", ""),
                            "two_factor": a.get("two-factor", "disable") != "disable",
                            # True == a real trust-host restriction. trusthost1 is
                            # a native "address mask" string; the FortiGate default
                            # "0.0.0.0 0.0.0.0" means unrestricted and must not read
                            # as restricted (which showed a green tile for an open
                            # admin). See admin_trusthost_is_open.
                            "trusthost": not admin_trusthost_is_open(a.get("trusthost1", "0.0.0.0 0.0.0.0")),
                        })

                # SSL VPN active users
                ssl_vpn_users = []
                if isinstance(ssl_vpn, dict):
                    ssl_vpn_list = ssl_vpn.get("results", ssl_vpn.get("data", []))
                    for u in (ssl_vpn_list if isinstance(ssl_vpn_list, list) else []):
                        ssl_vpn_users.append({
                            "user": u.get("user_name", u.get("common_name", "")),
                            "remote_ip": u.get("remote_host", ""),
                            "tunnel_ip": u.get("tunnel_ip", ""),
                            "duration": u.get("duration", 0),
                            "bytes_in": u.get("stats", {}).get("bytes_in", 0) if isinstance(u.get("stats"), dict) else 0,
                            "bytes_out": u.get("stats", {}).get("bytes_out", 0) if isinstance(u.get("stats"), dict) else 0,
                        })

                # Static routes
                routes_list = []
                if isinstance(static_routes, list):
                    for r in static_routes:
                        dst = r.get("dst", "")
                        if isinstance(dst, list):
                            dst = dst[0] if dst else ""
                        routes_list.append({
                            "dst": dst,
                            "gateway": r.get("gateway", ""),
                            "device": r.get("device", ""),
                            "distance": r.get("distance", 10),
                            "status": "enabled" if r.get("status", "enable") == "enable" else "disabled",
                        })

                # SD-WAN status
                sdwan_info = {}
                if isinstance(sdwan, dict) and sdwan.get("results"):
                    sdwan_members = sdwan.get("results", {}).get("members", [])
                    if isinstance(sdwan_members, list):
                        sdwan_info = {
                            "members": [{
                                "interface": m.get("interface", ""),
                                "status": m.get("status", ""),
                                "latency": m.get("latency", 0),
                                "jitter": m.get("jitter", 0),
                                "packet_loss": m.get("packet_loss", 0),
                            } for m in sdwan_members],
                        }

                # CMDB interfaces (VLAN details, roles, aliases)
                if isinstance(iface_cmdb, list) and iface_cmdb and isinstance(iface_cmdb[0], dict):
                    for ifc in iface_cmdb:
                        iname = ifc.get("name", "")
                        # Enrich existing interface entries
                        for existing in iface_list:
                            if existing["name"] == iname:
                                existing["type"] = ifc.get("type", "")
                                existing["alias"] = ifc.get("alias", "")
                                existing["vlanid"] = ifc.get("vlanid", 0)
                                existing["role"] = ifc.get("role", "")
                                existing["mask"] = ifc.get("ip", ["", ""])[1] if isinstance(ifc.get("ip"), list) and len(ifc.get("ip", [])) > 1 else ""
                                break
                        else:
                            # Interface only in CMDB (e.g. VLAN not in monitor)
                            ip_field = ifc.get("ip", ["0.0.0.0", ""])
                            ip_addr = ip_field[0] if isinstance(ip_field, list) else str(ip_field)
                            if ip_addr and ip_addr != "0.0.0.0":
                                iface_list.append({
                                    "name": iname,
                                    "ip": ip_addr,
                                    "mask": ip_field[1] if isinstance(ip_field, list) and len(ip_field) > 1 else "",
                                    "link": True,
                                    "speed": 0,
                                    "type": ifc.get("type", ""),
                                    "alias": ifc.get("alias", ""),
                                    "vlanid": ifc.get("vlanid", 0),
                                    "role": ifc.get("role", ""),
                                })

                # FortiGuard license expiry
                license_expiry = {}
                if isinstance(license_info, dict) and not isinstance(license_info, list):
                    for svc_key, svc_data in license_info.items():
                        if isinstance(svc_data, dict) and svc_data.get("expires"):
                            license_expiry[svc_key] = {
                                "status": svc_data.get("status", ""),
                                "expires": svc_data.get("expires", 0),
                                "type": svc_data.get("type", ""),
                            }

                # Log stats
                log_info = {}
                if isinstance(log_stats, dict) and "used" in log_stats:
                    log_info = {
                        "used_bytes": log_stats.get("used", 0),
                        "total_bytes": log_stats.get("total", 0),
                        "used_pct": round(log_stats.get("used", 0) / max(log_stats.get("total", 1), 1) * 100, 1),
                    }

                extra_data = {
                    "policy_count": policy_count,
                    "host": host,
                    "port": int(customer.get("FortiGatePort", 443)),
                    "interfaces": iface_list,
                    "vpn_tunnels": vpn_detail,
                    "policies": policy_summary,
                    "dhcp": dhcp_list,
                    "dns": dns_info,
                    "admins": admin_list,
                    "ssl_vpn_users": ssl_vpn_users,
                    "static_routes": routes_list,
                    "sdwan": sdwan_info,
                    "license_expiry": license_expiry,
                    "log_stats": log_info,
                }

                self._cache[device_id] = DeviceStatus(
                    device_id=device_id,
                    customer_id=customer_id,
                    vendor="fortigate",
                    name=status.get("hostname", host) if isinstance(status, dict) else host,
                    model=status.get("model-name", status.get("model", "")) if isinstance(status, dict) else "",
                    firmware=fw_version or (status.get("version", "") if isinstance(status, dict) else ""),
                    serial=serial,
                    status="online",
                    uptime=uptime_str or (status.get("uptime", "") if isinstance(status, dict) else ""),
                    cpu_pct=cpu,
                    mem_pct=mem,
                    wan_ip=wan_ip,
                    sessions=sessions,
                    vpn_tunnels=vpn_count,
                    ha_mode=ha_mode,
                    last_poll=now,
                    extra=extra_data,
                )
        except Exception as e:
            self._cache[device_id] = DeviceStatus(
                device_id=device_id, customer_id=customer_id,
                vendor="fortigate", name=host, model="", firmware="",
                serial="", status="error", uptime="",
                error=str(e), last_poll=now,
            )

    async def _poll_unifi_controller(
        self, customer_id: str, customer: dict, now: str
    ) -> None:
        from app.core.credentials import get_secret
        from app.modules.unifi_audit.client import UniFiControllerClient

        uf_user = get_secret(customer_id, "unifi_username")
        uf_pass = get_secret(customer_id, "unifi_password")
        if not uf_user or not uf_pass:
            return

        try:
            async with UniFiControllerClient(
                customer.get("UniFiHost", ""), uf_user, uf_pass,
                is_unifi_os=customer.get("UniFiIsUniFiOS", False),
            ) as uf:
                site = customer.get("UniFiSite", "default")
                devices = await uf.get_devices(site)

                # A refused device read used to write nothing — leaving the last
                # poll's rows in the cache, so the dashboard kept showing a
                # controller as healthy long after it stopped answering. Record
                # a controller-error indicator instead, the same as the except
                # path does for a connection that failed to open.
                from app.modules.api_result import read_error, read_failed
                if read_failed(devices):
                    # Evict this customer's per-device rows first. A prior good
                    # poll wrote uf_{cid}_{mac} rows as "online"; the error row
                    # below uses a different id (_ctrl), so without this the
                    # healthy rows survive and the dashboard keeps showing every
                    # device online for a controller that has stopped answering.
                    stale_prefix = f"uf_{customer_id}_"
                    for stale_id in [k for k in self._cache if k.startswith(stale_prefix)]:
                        del self._cache[stale_id]
                    device_id = f"uf_{customer_id}_ctrl"
                    self._cache[device_id] = DeviceStatus(
                        device_id=device_id, customer_id=customer_id,
                        vendor="unifi", name=customer.get("UniFiHost", "?"),
                        model="Controller", firmware="", serial="",
                        status="error", uptime="", error=read_error(devices),
                        last_poll=now,
                    )
                    return

                # The controller answered: drop any error row a prior refused
                # poll left behind, so a recovered controller does not keep
                # showing a stale "error" tile beside its live devices.
                self._cache.pop(f"uf_{customer_id}_ctrl", None)

                for d in (devices if isinstance(devices, list) else []):
                    mac = d.get("mac", "unknown")
                    device_id = f"uf_{customer_id}_{mac}"
                    is_online = d.get("state", 0) == 1
                    self._cache[device_id] = DeviceStatus(
                        device_id=device_id,
                        customer_id=customer_id,
                        vendor="unifi",
                        name=d.get("name", d.get("hostname", mac)),
                        model=d.get("model_in_lts", d.get("model", "")),
                        firmware=d.get("version", ""),
                        serial=mac,
                        status="online" if is_online else "offline",
                        uptime=str(d.get("uptime", 0)),
                        clients=d.get("num_sta", 0),
                        upgrade_available=d.get("upgrade_to_firmware"),
                        last_poll=now,
                    )
        except Exception as e:
            device_id = f"uf_{customer_id}_ctrl"
            self._cache[device_id] = DeviceStatus(
                device_id=device_id, customer_id=customer_id,
                vendor="unifi", name=customer.get("UniFiHost", "?"),
                model="Controller", firmware="", serial="",
                status="error", uptime="", error=str(e), last_poll=now,
            )

    async def _poll_unifi_direct(
        self, customer_id: str, customer: dict, now: str
    ) -> None:
        from app.core.credentials import get_secret
        from app.modules.unifi_audit.client import UniFiDirectDevice

        uf_user = get_secret(customer_id, "unifi_username") or "ubnt"
        uf_pass = get_secret(customer_id, "unifi_password") or "ubnt"

        for dev_cfg in customer.get("UniFiDirectDevices", []):
            dev_host = dev_cfg.get("host", "").strip()
            if not dev_host:
                continue
            device_id = f"uf_{customer_id}_{dev_host.replace('.', '_')}"
            try:
                async with UniFiDirectDevice(
                    dev_host,
                    username=dev_cfg.get("username") or uf_user,
                    password=dev_cfg.get("password") or uf_pass,
                    device_type=dev_cfg.get("device_type", "ap"),
                ) as dev:
                    info = await dev.get_device_info_ssh()
                    if info and "error" not in info:
                        self._cache[device_id] = DeviceStatus(
                            device_id=device_id,
                            customer_id=customer_id,
                            vendor="unifi",
                            name=info.get("hostname", dev_host),
                            model=info.get("model", ""),
                            firmware=info.get("firmware", ""),
                            serial=info.get("mac", ""),
                            status="online",
                            uptime=info.get("uptime_str", ""),
                            clients=info.get("client_count"),
                            last_poll=now,
                        )
                    else:
                        raise RuntimeError(info.get("error", "Unknown"))
            except Exception as e:
                self._cache[device_id] = DeviceStatus(
                    device_id=device_id, customer_id=customer_id,
                    vendor="unifi", name=dev_cfg.get("label", dev_host),
                    model="", firmware="", serial="",
                    status="offline", uptime="", error=str(e), last_poll=now,
                )

    # ── Broadcasting ─────────────────────────────────────────────────────

    async def _broadcast_updates(self) -> None:
        """Send current device status to all subscribers."""
        for ws_id, customer_ids in list(self._subscriptions.items()):
            callback = self._broadcast_fns.get(ws_id)
            if not callback:
                continue
            devices = []
            for cid in customer_ids:
                devices.extend(self.get_devices(cid))
            try:
                await callback(devices)
            except Exception as e:
                # Connection closed
                logger.debug("WebSocket broadcast failed for %s: %s", ws_id, e)
                self.unsubscribe(ws_id)


# Singleton instance
poller = DashboardPoller()
