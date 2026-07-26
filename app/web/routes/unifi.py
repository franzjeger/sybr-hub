"""UniFi and network route handlers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/unifi/test")
async def unifi_test(request: Request, user: User = Depends(get_current_user)):
    """Test UniFi Controller connectivity."""
    from app.modules.unifi_audit.client import UniFiControllerClient

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    is_unifi_os = body.get("is_unifi_os", False)

    if not host or not username or not password:
        raise ValidationError("Host, brukernavn og passord er påkrevd")

    # Ensure host has protocol prefix
    if not host.startswith("http://") and not host.startswith("https://"):
        host = "https://" + host

    try:
        async with UniFiControllerClient(host, username, password, is_unifi_os=is_unifi_os) as uf:
            result = await uf.test_connection()
            return result
    except Exception as e:
        raise ValidationError(str(e))


@router.post("/unifi/test-device")
async def unifi_test_device(request: Request, user: User = Depends(get_current_user)):
    """Test direct connectivity to a standalone UniFi device."""
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()
    device_type = body.get("device_type", "ap")

    if not host:
        raise ValidationError("Host/IP er påkrevd")

    async with UniFiDirectDevice(host, username, password, device_type=device_type) as dev:
        result = await dev.test_connection()
        return result


@router.post("/unifi/set-inform")
async def unifi_set_inform(request: Request, user: User = Depends(get_current_user)):
    """Set inform URL on a direct UniFi device to adopt it to a controller."""
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()
    controller_url = body.get("controller_url", "").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")
    if not controller_url:
        raise ValidationError("Controller URL er påkrevd")

    # Ensure the URL ends with /inform
    if not controller_url.endswith("/inform"):
        controller_url = controller_url.rstrip("/") + "/inform"
    if not controller_url.startswith("http"):
        controller_url = "http://" + controller_url

    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.set_inform(controller_url)


@router.post("/unifi/reboot-device")
async def unifi_reboot_device(request: Request, user: User = Depends(get_current_user)):
    """Reboot a direct UniFi device."""
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")

    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.reboot()


@router.post("/unifi/device-config")
async def unifi_device_config(request: Request, user: User = Depends(get_current_user)):
    """Dump running config from a direct UniFi device."""
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")

    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.get_config_dump()


@router.post("/network/scan")
async def network_scan_subnet(request: Request, user: User = Depends(get_current_user)):
    """Scan a subnet for UniFi devices."""
    from app.modules.unifi_audit.scanner import scan_subnet

    body = await request.json()
    subnet = body.get("subnet", "").strip()
    if not subnet:
        raise ValidationError("Subnet er påkrevd (f.eks. 192.168.1.0/24)")

    results = await scan_subnet(subnet, max_concurrent=body.get("max_concurrent", 50))
    if results and "error" in results[0]:
        raise ValidationError(results[0]["error"])

    return {"subnet": subnet, "found": results, "count": len(results)}


@router.post("/network/save-config-backup")
async def network_save_config_backup(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Save a device config dump to the customer's audit directory."""
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_write_text

    body = await request.json()
    host = body.get("host", "").strip()
    config_text = body.get("config", "")
    if not host or not config_text:
        raise ValidationError("Host og konfigurasjon er påkrevd")

    active = CustomerManager.get_active()
    if not active:
        raise ValidationError("Ingen aktiv kunde")

    # Save to customer audit dir under network_configs/
    from datetime import datetime
    safe_name = active.get("CustomerName", "unknown").replace(" ", "_")
    audit_dir = get_audit_dir() / safe_name / "network_configs"
    audit_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    safe_host = host.replace(".", "_").replace(":", "_")
    filename = f"{timestamp}_{safe_host}.cfg"
    filepath = audit_dir / filename

    encrypted_write_text(filepath, config_text)

    return {"ok": True, "path": str(filepath), "filename": filename}


@router.get("/network/config-backups")
async def network_list_config_backups(user: User = Depends(get_current_user)):
    """List saved network config backups for the active customer."""
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager

    active = CustomerManager.get_active()
    if not active:
        return {"backups": []}

    safe_name = active.get("CustomerName", "unknown").replace(" ", "_")
    backup_dir = get_audit_dir() / safe_name / "network_configs"
    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for f in sorted(backup_dir.glob("*.cfg"), reverse=True):
        parts = f.stem.split("_", 2)
        backups.append({
            "filename": f.name,
            "path": str(f),
            "timestamp": parts[0] + " " + parts[1] if len(parts) >= 2 else f.stem,
            "host": parts[2].replace("_", ".") if len(parts) >= 3 else "",
            "size": f.stat().st_size,
        })

    return {"backups": backups}


@router.post("/unifi/save")
async def unifi_save(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Save UniFi config for the active customer."""
    from app.core.credentials import store_secret
    from app.core.customer import CustomerManager

    body = await request.json()
    active = CustomerManager.get_active()
    if not active:
        raise ValidationError("Ingen aktiv kunde")

    cust_id = active["_id"]
    config = CustomerManager.get_customer(cust_id)
    if not config:
        raise NotFoundError("Kunde ikke funnet")

    config["UniFiMode"] = body.get("mode", "controller")  # "controller" or "direct"
    config["UniFiHost"] = body.get("host", "").strip()
    config["UniFiIsUniFiOS"] = body.get("is_unifi_os", False)
    config["UniFiSite"] = body.get("site", "default")

    # Save direct devices list (always update when mode is direct)
    devices = body.get("devices", [])
    if body.get("mode") == "direct" or devices:
        config["UniFiDirectDevices"] = devices

    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if username:
        store_secret(cust_id, "unifi_username", username)
    if password:
        store_secret(cust_id, "unifi_password", password)

    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    CustomerManager.save_customer(save_data)

    return {"ok": True}


@router.post("/network/quick-audit")
async def network_quick_audit(user: User = Depends(require_role(Role.technician))):
    """Run a quick network audit — gathers key data from FortiGate and/or UniFi."""
    import json as _json

    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.services.network_audit import run_quick_network_audit

    active = CustomerManager.get_active()
    if not active:
        raise ValidationError("Ingen aktiv kunde")

    cust_id = active.get("_id", "")
    results = await run_quick_network_audit(active, cust_id)

    if not results["fortigate"] and not results["unifi"]:
        raise ValidationError("Ingen nettverksenheter konfigurert for denne kunden")

    # Clean results for JSON serialization
    try:
        clean = _json.loads(_json.dumps(results, default=str))
    except (TypeError, ValueError):
        clean = results

    # Persist results to audit directory
    try:
        from datetime import datetime as _dt

        from app.core.config import get_audit_dir
        from app.core.encryption import encrypted_write_text

        safe_name = active.get("CustomerName", "unknown").replace(" ", "_")
        audit_base = get_audit_dir() / safe_name
        runs = sorted(audit_base.glob("20*_*"), reverse=True) if audit_base.exists() else []
        if runs:
            net_dir = runs[0]
        else:
            ts = _dt.now().strftime("%Y-%m-%d_%H%M")
            net_dir = audit_base / ts
            net_dir.mkdir(parents=True, exist_ok=True)

        if clean.get("fortigate") and "error" not in clean["fortigate"]:
            encrypted_write_text(net_dir / "60_fortigate_audit.txt",
                                 _json.dumps(clean["fortigate"], indent=2, default=str))
        if clean.get("unifi") and "error" not in clean["unifi"]:
            encrypted_write_text(net_dir / "61_unifi_audit.txt",
                                 _json.dumps(clean["unifi"], indent=2, default=str))
        logger.info("Network audit results saved to %s", net_dir)
    except Exception as e:
        logger.warning("Failed to save network audit results: %s", e)

    return JSONResponse(content=clean)


@router.get("/network-devices")
async def get_network_devices(user: User = Depends(get_current_user)):
    """Return configured network devices for the active customer."""
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    active = CustomerManager.get_active()
    if not active:
        return {"fortigate": None, "unifi": None}

    cust_id = active.get("_id", "")
    fg = None
    if active.get("FortiGateHost"):
        fg = {
            "host": active["FortiGateHost"],
            "port": active.get("FortiGatePort", 443),
            "vdom": active.get("FortiGateVDOM", "root"),
            "verify_ssl": active.get("FortiGateVerifySSL", False),
            "has_token": bool(get_secret(cust_id, "fortigate_api_token")),
        }

    uf = None
    unifi_mode = active.get("UniFiMode", "controller")
    if active.get("UniFiHost") or active.get("UniFiDirectDevices"):
        uf = {
            "mode": unifi_mode,
            "host": active.get("UniFiHost", ""),
            "is_unifi_os": active.get("UniFiIsUniFiOS", False),
            "site": active.get("UniFiSite", "default"),
            "has_credentials": bool(get_secret(cust_id, "unifi_username")),
            "direct_devices": active.get("UniFiDirectDevices", []),
        }

    return {"fortigate": fg, "unifi": uf}


# ═══════════════════════════════════════════════════════════════════════════════
# Enhanced UniFi API endpoints (require technician role)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/unifi/clients/{customer_id}")
async def unifi_clients(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Get all connected clients for a customer's UniFi site."""
    from app.services.unifi_api import get_client_inventory

    try:
        clients = await get_client_inventory(customer_id)
        wireless = sum(1 for c in clients if c["type"] == "wireless")
        wired = len(clients) - wireless
        return {"ok": True, "clients": clients, "count": len(clients),
                "wireless": wireless, "wired": wired}
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.exception("unifi_clients failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/unifi/wifi-health/{customer_id}")
async def unifi_wifi_health(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Get WiFi health overview for a customer's UniFi site."""
    from app.services.unifi_api import get_wifi_health

    try:
        data = await get_wifi_health(customer_id)
        return {"ok": True, **data}
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.exception("unifi_wifi_health failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/unifi/dashboard/{customer_id}")
async def unifi_dashboard(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Enhanced device stats for all devices on the customer's controller."""
    from app.services.unifi_api import get_enhanced_device_stats

    try:
        devices = await get_enhanced_device_stats(customer_id)
        return {"ok": True, "devices": devices, "count": len(devices)}
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.exception("unifi_dashboard failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.post("/unifi/site-manager/auth")
async def unifi_site_manager_auth(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Authenticate with UniFi Site Manager via API key or SSO credentials."""
    from app.services.unifi_api import site_manager_authenticate

    body = await request.json()
    api_key = body.get("api_key", "").strip()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    customer_id = body.get("customer_id")

    if not api_key and (not username or not password):
        raise ValidationError("API-nøkkel eller brukernavn/passord er påkrevd")

    result = await site_manager_authenticate(
        username=username or None,
        password=password or None,
        api_key=api_key or None,
        store_for_customer=customer_id,
    )
    if result.get("ok"):
        return {"ok": True, "method": result.get("method", "unknown")}
    # 2FA required — pass session token back to client for the second step
    if result.get("requires_2fa"):
        return JSONResponse({
            "ok": False,
            "requires_2fa": True,
            "session_token": result.get("session_token", ""),
            "error": result.get("error", "2FA-kode påkrevd"),
            # Echo back customer_id so the frontend can pass it to verify
            "customer_id": customer_id or "",
        }, status_code=200)
    # Use 400 (not 401!) — 401 would trigger JWT refresh/logout in the frontend
    raise ValidationError(result.get("error", "Ukjent feil"))


@router.post("/unifi/site-manager/verify-2fa")
async def unifi_site_manager_verify_2fa(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Complete UniFi Site Manager SSO 2FA verification."""
    from app.services.unifi_api import site_manager_verify_2fa

    body = await request.json()
    session_token = body.get("session_token", "").strip()
    code = body.get("code", "").strip()
    customer_id = body.get("customer_id")

    if not session_token or not code:
        raise ValidationError("Session-token og 2FA-kode er påkrevd")

    result = await site_manager_verify_2fa(
        session_token=session_token,
        totp_code=code,
        store_for_customer=customer_id,
    )
    if result.get("ok"):
        return {"ok": True, "method": result.get("method", "sso")}
    raise ValidationError(result.get("error", "Ukjent feil"))


@router.get("/unifi/site-manager/sites")
async def unifi_site_manager_sites(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """List cloud-managed sites from ui.com Site Manager."""
    from app.services.unifi_api import site_manager_list_sites

    customer_id = request.query_params.get("customer_id")
    result = await site_manager_list_sites(customer_id=customer_id)

    if not result.get("ok"):
        error_msg = result.get("error", "Unknown error")
        if "expired" in error_msg.lower():
            raise AuthError(error_msg)
        raise ValidationError(error_msg)
    return result


@router.get("/unifi/firmware-check/{customer_id}")
async def unifi_firmware_check(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Check all devices against the firmware database for outdated/EOL firmware."""
    from app.services.unifi_api import firmware_check_all

    try:
        result = await firmware_check_all(customer_id)
        return {"ok": True, **result}
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.exception("firmware_check failed for %s", customer_id)
        raise IntegrationError(str(e))


@router.get("/unifi/controller-summary/{customer_id}")
async def unifi_controller_summary(
    customer_id: str,
    user: User = Depends(require_role(Role.technician)),
):
    """Aggregate controller view: sites, devices, clients, WLANs, alarms."""
    from app.services.unifi_api import get_controller_summary

    try:
        summary = await get_controller_summary(customer_id)
        return {"ok": True, **summary}
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.exception("controller_summary failed for %s", customer_id)
        raise IntegrationError(str(e))


# ── Site Manager: all devices ────────────────────────────────────────────────

@router.get("/unifi/sm/devices")
async def unifi_sm_devices(
    host_id: str = "",
    user: User = Depends(get_current_user),
):
    """Get all devices across all sites from Site Manager API."""
    from app.services.unifi_api import get_all_devices
    result = await get_all_devices(host_id or None)
    if not result.get("ok"):
        raise ValidationError(result.get("error", "Failed to fetch devices"))
    return result


# ── Site Manager: ISP metrics ────────────────────────────────────────────────

@router.get("/unifi/sm/isp-metrics")
async def unifi_sm_isp_metrics(
    metric_type: str = "1h",
    duration: str = "24h",
    user: User = Depends(get_current_user),
):
    """Get ISP performance metrics (bandwidth, latency, packet loss)."""
    from app.services.unifi_api import get_isp_metrics
    result = await get_isp_metrics(metric_type, duration)
    if not result.get("ok"):
        raise ValidationError(result.get("error", "Failed to fetch ISP metrics"))
    return result


# ── Site Manager: WAN details per site ───────────────────────────────────────

@router.get("/unifi/sm/site/{site_id}/wan")
async def unifi_sm_site_wan(
    site_id: str,
    user: User = Depends(get_current_user),
):
    """Get WAN/ISP details and gateway info for a specific site."""
    from app.services.unifi_api import get_site_wan_details
    result = await get_site_wan_details(site_id)
    if not result.get("ok"):
        raise ValidationError(result.get("error", "Failed to fetch WAN details"))
    return result


# ── Unified UniFi view (all customers) ──────────────────────────────────────


@router.get("/unifi/all")
async def unifi_all(request: Request, user: User = Depends(get_current_user)):
    """Get UniFi device status for ALL customers that have UniFi configured."""
    from app.core.customer import CustomerManager
    from app.core.rbac import filter_customers, get_accessible_customer_ids

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    unifi_customers = []
    for c in customers:
        if c.get("UniFiHost"):
            unifi_customers.append({
                "customer_id": c.get("_id", ""),
                "customer_name": c.get("CustomerName", ""),
                "host": c.get("UniFiHost", ""),
                "mode": c.get("UniFiMode", "controller"),
            })

    # Get cached device data from dashboard poller
    try:
        from app.services.dashboard_poller import poller as _poller
    except ImportError:
        _poller = None
    all_devices = []
    if _poller:
        for dev in _poller.get_devices():
            if dev.get("vendor") == "unifi":
                # Find customer name
                cust_name = ""
                for uc in unifi_customers:
                    if uc["customer_id"] == dev.get("customer_id"):
                        cust_name = uc["customer_name"]
                        break
                dev["customer_name"] = cust_name
                all_devices.append(dev)

    # If no per-customer UniFi config but global Site Manager API key is set,
    # fetch sites from cloud API so the UniFi tab isn't empty.
    # v1 API allows 10,000 req/min — no caching needed.
    sm_sites = []
    if not unifi_customers and not all_devices:
        from app.core.config import load_app_settings
        api_key = load_app_settings().get("unifi_site_manager_api_key", "")
        if api_key:
            try:
                from app.services.unifi_api import site_manager_list_sites
                sm_result = await site_manager_list_sites(token=api_key)
                if sm_result.get("ok"):
                    sm_sites = sm_result.get("sites", [])
            except Exception as e:
                logger.warning("Site Manager fetch for /unifi/all failed: %s", e)

            for host in sm_sites:
                # Host/console entry — full detail for the detail panel
                entry = {k: v for k, v in host.items()}
                entry["ip"] = entry.pop("wan_ip", "")
                entry["clients"] = entry.pop("client_count", 0)
                entry["vendor"] = "unifi"
                entry["customer_name"] = ""
                entry["source"] = "site_manager"
                entry["entry_type"] = "host"
                all_devices.append(entry)

    online = sum(1 for d in all_devices if d.get("status") == "online")
    total_clients = sum(d.get("clients", 0) or 0 for d in all_devices)
    total_sub_devices = sum(d.get("device_count", 0) or 0 for d in all_devices)

    return {
        "devices": all_devices,
        "customers": unifi_customers,
        "summary": {
            "total_devices": total_sub_devices or len(all_devices),
            "online": online,
            "offline": len(all_devices) - online,
            "total_clients": total_clients,
            "configured_customers": len(unifi_customers) or len(sm_sites),
        },
    }
