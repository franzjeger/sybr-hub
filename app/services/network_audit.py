"""Quick network audit — combines FortiGate and UniFi audits for a customer.

Extracted from the inline route handler to keep routes thin.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def run_quick_network_audit(customer_config: dict, customer_id: str) -> dict:
    """Run a quick audit of FortiGate and/or UniFi for the given customer.

    Returns {"fortigate": {...} | None, "unifi": {...} | None}.
    """
    from app.core.credentials import get_secret

    results: dict = {"fortigate": None, "unifi": None}

    # ── FortiGate ──
    fg_host = customer_config.get("FortiGateHost")
    fg_token = get_secret(customer_id, "fortigate_api_token") if fg_host else None
    if fg_host and fg_token:
        from app.services.fortigate_api import _build_client, quick_audit_fortigate
        try:
            results["fortigate"] = await quick_audit_fortigate(customer_config, fg_token)
        except Exception as e:
            results["fortigate"] = {"error": str(e)}

    # ── UniFi ──
    uf_host = customer_config.get("UniFiHost")
    uf_mode = customer_config.get("UniFiMode", "controller")
    direct_devices = customer_config.get("UniFiDirectDevices", [])

    if uf_mode == "direct" and direct_devices:
        results["unifi"] = await _audit_unifi_direct(customer_id, direct_devices)
    elif uf_host and uf_mode == "controller":
        results["unifi"] = await _audit_unifi_controller(customer_id, customer_config)

    return results


async def _audit_unifi_direct(customer_id: str, direct_devices: list[dict]) -> dict | None:
    """Audit UniFi devices in direct mode (SSH/HTTP to each device)."""
    from app.core.credentials import get_secret
    from app.modules.unifi_audit.client import UniFiDirectDevice
    from app.modules.unifi_audit.firmware_db import check_firmware

    uf_user = get_secret(customer_id, "unifi_username") or "ubnt"
    uf_pass = get_secret(customer_id, "unifi_password") or "ubnt"

    async def _audit_one(dev_cfg: dict) -> dict:
        dev_host = dev_cfg.get("host", "").strip()
        if not dev_host:
            return {}
        username = dev_cfg.get("username") or uf_user
        password = dev_cfg.get("password") or uf_pass
        dev_type = dev_cfg.get("device_type", "ap")
        base: dict = {
            "host": dev_host,
            "label": dev_cfg.get("label", dev_host),
            "device_type": dev_type,
            "ok": False,
            "http": False,
            "ssh": False,
        }
        try:
            async with UniFiDirectDevice(dev_host, username=username, password=password, device_type=dev_type) as dev:
                http_info = await dev.get_device_info_http()
                if http_info and "error" not in http_info:
                    base["http"] = True
                    base["ok"] = True
                    base["model"] = http_info.get("model", "")
                    base["firmware"] = http_info.get("version", "")

                ssh_info = await dev.get_device_info_ssh()
                if ssh_info and "error" not in ssh_info:
                    base["ssh"] = True
                    base["ok"] = True
                    for key in ("hostname", "mac", "serial", "model_short",
                                "essid", "channel", "wifi_mode", "wifi_security",
                                "adoption_status", "inform_url", "cfgversion",
                                "https_port"):
                        base[key] = ssh_info.get(key, "")
                    base["ip"] = ssh_info.get("ip", dev_host)
                    base["model"] = base.get("model") or ssh_info.get("model", "")
                    base["firmware"] = base.get("firmware") or ssh_info.get("firmware", "")
                    base["uptime"] = ssh_info.get("uptime_str", "")
                    base["uptime_seconds"] = ssh_info.get("uptime_seconds")
                    base["client_count"] = ssh_info.get("client_count")
                    base["ssid_list"] = ssh_info.get("ssid_list", [])
                    base["adopted"] = ssh_info.get("adopted", False)
                    base["default_credentials"] = ssh_info.get("default_credentials", False)
                    base["is_default_config"] = ssh_info.get("is_default_config", False)
                    base["admin_users"] = ssh_info.get("admin_users", [])
                    base["ssh_enabled"] = ssh_info.get("ssh_enabled")
                elif "error" in ssh_info:
                    base["ssh_error"] = ssh_info["error"]

                if not base["ok"]:
                    base["error"] = ssh_info.get("error", http_info.get("error", "Connection failed"))
        except Exception as e:
            base["error"] = str(e)
        return base

    device_results = [r for r in await asyncio.gather(*[_audit_one(d) for d in direct_devices]) if r]

    outdated_count = 0
    eol_count = 0
    for d in device_results:
        if d.get("model") and d.get("firmware"):
            fw_check = check_firmware(d["model"], d["firmware"])
            d["fw_check"] = fw_check
            if fw_check.get("eol"):
                eol_count += 1
            elif fw_check.get("up_to_date") is False:
                outdated_count += 1

    return {
        "mode": "direct",
        "device_count": len(device_results),
        "devices": device_results,
        "reachable": sum(1 for d in device_results if d.get("ok")),
        "default_creds_count": sum(1 for d in device_results if d.get("default_credentials")),
        "outdated_firmware_count": outdated_count,
        "eol_count": eol_count,
    }


async def _audit_unifi_controller(customer_id: str, config: dict) -> dict | None:
    """Audit UniFi via controller API."""
    from app.core.credentials import get_secret
    from app.modules.unifi_audit.client import UniFiControllerClient
    from app.modules.unifi_audit.firmware_db import check_firmware
    from app.services.unifi_api import wlan_security_label

    uf_host = config.get("UniFiHost")
    uf_user = get_secret(customer_id, "unifi_username")
    uf_pass = get_secret(customer_id, "unifi_password")
    if not uf_user or not uf_pass:
        return None

    from app.modules.api_result import read_error, read_failed

    try:
        async with UniFiControllerClient(
            uf_host, uf_user, uf_pass,
            is_unifi_os=config.get("UniFiIsUniFiOS", False),
        ) as uf:
            site = config.get("UniFiSite", "default")
            sites = await uf.list_sites()
            devices = await uf.get_devices(site)
            wlans = await uf.get_wlans(site)
            networks = await uf.get_networks(site)
            fw_rules = await uf.get_firewall_rules(site)
            alarms = await uf.get_alarms(site)

            # The device read is load-bearing: device_count, the firmware
            # currency check and every per-device row derive from it. If it
            # refused, the whole section is unverifiable — reporting
            # "device_count: 0, eol_count: 0, outdated: 0" would be a clean
            # UniFi audit for a controller nobody could read, which is the
            # false-negative this pass exists to remove.
            if read_failed(devices):
                return {
                    "mode": "controller",
                    "unavailable": True,
                    "error": read_error(devices),
                    "device_count": None,
                    "wlan_count": None,
                    "outdated_firmware_count": None,
                    "eol_count": None,
                }

            device_summary = [{
                "name": d.get("name", d.get("hostname", d.get("mac", "?"))),
                "model": d.get("model_in_lts", d.get("model", "")),
                "type": d.get("type", ""),
                "firmware": d.get("version", ""),
                "upgrade": d.get("upgrade_to_firmware") or None,
                "clients": d.get("num_sta", 0),
                "uptime": d.get("uptime", 0),
                "status": "online" if d.get("state", 0) == 1 else "offline",
            } for d in devices]

            # Run the same firmware-currency check direct mode runs (above).
            # Without this, EOL and outdated firmware findings were missing
            # from every controller-mode customer's report — a 100% false
            # negative for that population. The controller already gives us
            # model + version, so the same firmware_db lookup applies.
            outdated_count = 0
            eol_count = 0
            for d in device_summary:
                if d.get("model") and d.get("firmware"):
                    fw_check = check_firmware(d["model"], d["firmware"])
                    d["fw_check"] = fw_check
                    if fw_check.get("eol"):
                        eol_count += 1
                    elif fw_check.get("up_to_date") is False:
                        outdated_count += 1

            # Never default `security` to "open". A WLAN whose security field
            # the controller did not return is unknown, and the report treats
            # "open" as a critical finding — that default manufactured one.
            # security_label carries the classification forward so consumers
            # (and the WLAN table) don't each have to re-derive it.
            wlan_summary = [{
                "name": w.get("name", ""),
                "security": w.get("security"),
                "security_label": wlan_security_label(w.get("security")),
                "vlan": w.get("networkconf_id", ""),
                "enabled": w.get("enabled", True),
                "guest": w.get("is_guest", False),
            } for w in wlans]

            # A secondary read that individually refused reports None, not a
            # clean 0: "0 active alarms" and "could not read alarms" are
            # different claims and the report must not conflate them. The
            # device-derived counts are trustworthy here — the guard above
            # already returned if the device read failed.
            def _count(value):
                return None if read_failed(value) else len(value)

            return {
                "mode": "controller",
                "unavailable": False,
                "sites": _count(sites),
                "device_count": len(devices),
                "devices": device_summary,
                "wlan_count": _count(wlans),
                "wlans": wlan_summary,
                "network_count": _count(networks),
                "firewall_rules": _count(fw_rules),
                "active_alarms": _count(alarms),
                "outdated_firmware_count": outdated_count,
                "eol_count": eol_count,
                # default_creds_count is not available in controller mode
                # (SSH is required to detect it); the recommendation logic
                # gates on whether the value is present, so leaving it out
                # is correct — it WILL surface in direct-mode audits.
            }
    except Exception as e:
        return {"error": str(e)}
