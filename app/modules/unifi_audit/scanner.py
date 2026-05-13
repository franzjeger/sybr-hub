"""UniFi device subnet scanner — discover devices on a network range.

Performs a ping sweep followed by SSH probe to detect UniFi devices.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

# Ports that indicate a UniFi device
UNIFI_SSH_PORT = 22
UNIFI_HTTPS_PORTS = [443, 8443]
UNIFI_INFORM_PORT = 8080


async def _ping(host: str, timeout: float = 1.0) -> bool:
    """Ping a single host. Returns True if reachable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(int(timeout * 1000)), str(host),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=timeout + 1)
        return proc.returncode == 0
    except Exception:
        return False


async def _check_ssh_banner(host: str, port: int = 22, timeout: float = 3.0) -> Optional[str]:
    """Connect to SSH port and read banner. Returns banner string or None."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        banner = await asyncio.wait_for(reader.readline(), timeout=2.0)
        writer.close()
        await writer.wait_closed()
        return banner.decode("utf-8", errors="replace").strip()
    except Exception:
        return None


async def _check_https(host: str, port: int = 443, timeout: float = 3.0) -> Optional[str]:
    """Try HTTPS connection to detect UniFi web interface."""
    import httpx
    try:
        # SECURITY: verify=False is intentional — UniFi APs and controllers
        # ship with self-signed certs by default; device-discovery must
        # tolerate that. Connection is on the local management VLAN only.
        async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
            r = await client.get(f"https://{host}:{port}/")
            # UniFi devices typically return HTML with "ubnt" or "UniFi" in the response
            text = r.text[:2000].lower()
            if any(k in text for k in ("ubnt", "unifi", "ubiquiti", "ui.com")):
                return "unifi"
            return "other"
    except Exception:
        return None


async def scan_host(host: str) -> Optional[dict]:
    """Probe a single host for UniFi device indicators.

    Returns a dict with device info, or None if not a UniFi device.
    """
    result: dict = {"host": str(host), "is_unifi": False, "ssh": False, "https": False}

    # Check SSH banner
    banner = await _check_ssh_banner(str(host))
    if banner:
        result["ssh"] = True
        result["ssh_banner"] = banner
        # UniFi devices typically have "dropbear" or "OpenSSH" with specific patterns
        if "dropbear" in banner.lower():
            result["is_unifi"] = True
            result["device_hint"] = "UniFi (dropbear SSH)"

    # Check HTTPS
    https_result = await _check_https(str(host))
    if https_result:
        result["https"] = True
        if https_result == "unifi":
            result["is_unifi"] = True
            result["device_hint"] = result.get("device_hint", "UniFi (HTTPS)")

    if not result["ssh"] and not result["https"]:
        return None

    return result


async def scan_subnet(
    subnet: str,
    on_progress: Optional[callable] = None,
    max_concurrent: int = 50,
) -> list[dict]:
    """Scan a subnet for UniFi devices.

    Args:
        subnet: CIDR notation, e.g., "192.168.1.0/24"
        on_progress: Optional callback(scanned: int, total: int, found: int)
        max_concurrent: Max parallel probes

    Returns:
        List of dicts with device info for each discovered host.
    """
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        return [{"error": f"Ugyldig subnet: {e}"}]

    hosts = list(network.hosts())
    total = len(hosts)
    if total > 1024:
        return [{"error": f"Subnet for stort ({total} adresser). Maks /22 (1024)."}]

    log.info("Scanning %d hosts in %s", total, subnet)

    found: list[dict] = []
    scanned = 0
    sem = asyncio.Semaphore(max_concurrent)

    async def _probe(host: ipaddress.IPv4Address) -> None:
        nonlocal scanned
        async with sem:
            # Quick ping first
            alive = await _ping(str(host), timeout=0.5)
            scanned += 1
            if on_progress:
                on_progress(scanned, total, len(found))
            if not alive:
                return
            # Deeper probe
            info = await scan_host(str(host))
            if info and (info.get("is_unifi") or info.get("ssh")):
                found.append(info)
                if on_progress:
                    on_progress(scanned, total, len(found))

    await asyncio.gather(*[_probe(h) for h in hosts])

    log.info("Scan complete: %d/%d alive, %d UniFi devices", len(found), total, sum(1 for d in found if d.get("is_unifi")))
    return sorted(found, key=lambda d: ipaddress.ip_address(d["host"]))
