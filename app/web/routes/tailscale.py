"""Tailscale integration routes — device inventory, auth keys, status."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.exceptions import (
    ForbiddenError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.tailscale import (
    TailscaleAuthorize,
    TailscaleKeyCreate,
    TailscaleKeyExpiry,
    TailscaleNodeAssign,
    TailscaleRename,
    TailscaleRoutes,
    TailscaleTags,
    TailscaleTest,
)
from app.models.user import Role, User
from app.web.connection_checks import connection_check
from app.web.i18n import refusal
from app.web.middleware.auth import (
    require_customer_access,
    require_feature,
    require_module,
    require_role,
)

log = logging.getLogger(__name__)
# The whole module is the 'network' feature (app/core/features.py); per-route
# floors below only ever raise it.
router = APIRouter(
    tags=["tailscale"],
    dependencies=[Depends(require_module("tailscale")), Depends(require_feature("network"))],
)

# The hub is served on this tailnet, and the API key is tailnet-wide: minting
# a reusable pre-authorised key, approving a subnet route or authorising a
# device each changes who can reach the hub and every customer network behind
# it. Those are admin decisions. Reading the inventory is technician work.
_tech = Depends(require_role(Role.technician))
_admin = Depends(require_role(Role.admin))


def _ensure_configured() -> bool:
    """Check if Tailscale API is configured; return False if not."""
    from app.web.connection_checks import connection_settings as load_app_settings

    settings = load_app_settings()
    api_key = settings.get("tailscale_api_key", "")
    if not api_key:
        return False
    from app.services import tailscale_api

    tailscale_api.configure(api_key, settings.get("tailscale_tailnet", "-"))
    return True


# ── Status ───────────────────────────────────────────────────────────────────


@router.get("/tailscale/status")
async def tailscale_status(user: User = _tech):
    """Check if Tailscale is configured and reachable."""
    from app.web.connection_checks import connection_settings as load_app_settings

    settings = load_app_settings()
    has_key = bool(settings.get("tailscale_api_key"))
    tailnet = settings.get("tailscale_tailnet", "-")
    if not has_key:
        return {"configured": False, "tailnet": tailnet}

    # Quick test: try fetching devices
    try:
        if not _ensure_configured():
            return {"configured": False, "tailnet": tailnet}
        from app.services import tailscale_api

        devices = await tailscale_api.list_devices()
        return {
            "configured": True,
            "tailnet": tailnet,
            "device_count": len(devices),
            "online": sum(1 for d in devices if d["online"]),
        }
    except Exception as e:
        log.debug("Tailscale status check failed: %s", e)
        return {"configured": True, "tailnet": tailnet, "error": str(e)}


# ── Devices ──────────────────────────────────────────────────────────────────


@router.get("/tailscale/devices")
async def tailscale_devices(user: User = _tech):
    """List all devices in the tailnet.

    No key yet is the normal state of a fresh install, not a failed request:
    it answers ``configured: false`` with an empty list, and the view shows
    where to set the key. A 400 here made opening the page raise a red
    error toast.
    """
    if not _ensure_configured():
        return {
            "configured": False,
            "devices": [],
            "total": 0,
            "online": 0,
            "offline": 0,
            "stale": 0,
            "expiring_keys": 0,
        }
    try:
        from app.services import tailscale_api

        devices = await tailscale_api.list_devices()
        await _annotate_customers(devices, user)

        online = [d for d in devices if d["online"]]
        offline = [d for d in devices if not d["online"]]
        stale = [d for d in devices if d["stale_days"] is not None and d["stale_days"] > 7]
        expiring_keys = [
            d
            for d in devices
            if d["key_days_left"] is not None
            and d["key_days_left"] < 30
            and not d["key_expiry_disabled"]
        ]

        return {
            "configured": True,
            "devices": devices,
            "total": len(devices),
            "online": len(online),
            "offline": len(offline),
            "stale": len(stale),
            "expiring_keys": len(expiring_keys),
        }
    except Exception as e:
        log.exception("Tailscale device list failed")
        raise IntegrationError(str(e)) from e


async def _annotate_customers(devices: list[dict], user: User) -> None:
    """Mark each node with the customer it belongs to, as far as the caller may see.

    A node of a customer the caller cannot reach says only that it is taken
    (``customer_hidden``), never whose it is.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import get_accessible_customer_ids
    from app.services import tailscale_customers

    customers = {c["_id"]: c for c in CustomerManager.list_customers()}
    owners = tailscale_customers.resolve(
        devices, list(customers), await tailscale_customers.manual_assignments()
    )
    allowed = await get_accessible_customer_ids(user)
    for device in devices:
        owner = owners.get(str(device.get("id") or ""))
        device["customer_id"] = None
        device["customer_name"] = None
        device["customer_source"] = None
        device["customer_hidden"] = False
        if owner is None:
            continue
        cid, source = owner
        if allowed is not None and cid not in allowed:
            device["customer_hidden"] = True
            continue
        device["customer_id"] = cid
        device["customer_name"] = customers[cid].get("CustomerName", cid)
        device["customer_source"] = source


@router.get("/tailscale/customer/{customer_id}/nodes")
async def tailscale_customer_nodes(
    customer_id: str, user: User = Depends(require_customer_access(Role.technician))
):
    """This customer's nodes: assigned by hand, or tagged for it in the tailnet.

    Each with its status and what to connect to. ``tag`` is the tag that would
    map a node here without anyone assigning it.
    """
    from app.core.customer import CustomerManager
    from app.services import tailscale_customers

    if CustomerManager.get_customer(customer_id) is None:
        raise refusal(NotFoundError, "err_customer_not_found")
    tag = tailscale_customers.customer_tag(customer_id)
    if not _ensure_configured():
        return {"configured": False, "customer_id": customer_id, "tag": tag, "nodes": []}
    try:
        from app.services import tailscale_api

        devices = await tailscale_api.list_devices()
    except Exception as e:
        log.warning("Tailscale device list failed: %s", e)
        raise refusal(IntegrationError, "err_tailscale_unreachable") from e

    owners = tailscale_customers.resolve(
        devices,
        [c["_id"] for c in CustomerManager.list_customers()],
        await tailscale_customers.manual_assignments(),
    )
    nodes = []
    for device in devices:
        owner = owners.get(str(device.get("id") or ""))
        if owner is None or owner[0] != customer_id:
            continue
        nodes.append(
            {
                "id": device.get("id"),
                "name": device.get("given_name") or device.get("hostname") or device.get("name"),
                "hostname": device.get("hostname", ""),
                "os": device.get("os", ""),
                "online": bool(device.get("online")),
                "last_seen": device.get("last_seen"),
                "last_seen_ago": device.get("last_seen_ago"),
                "tags": device.get("tags", []),
                "source": owner[1],
                "key_days_left": device.get("key_days_left"),
                "key_expiry_disabled": device.get("key_expiry_disabled", False),
                **tailscale_customers.connect_info(device),
            }
        )
    nodes.sort(key=lambda n: (not n["online"], (n["name"] or "").lower()))
    return {"configured": True, "customer_id": customer_id, "tag": tag, "nodes": nodes}


@router.put("/tailscale/device/{device_id}/customer")
async def tailscale_assign_customer(device_id: str, body: TailscaleNodeAssign, user: User = _tech):
    """Assign a node to a customer by hand, or drop its hand assignment (null).

    The caller needs access to the customer it is given to and, when it is
    being moved, to the customer it is taken from: otherwise a scoped
    technician could pull another customer's node onto one they can see.
    The tag in the tailnet is not touched; a hand assignment wins over it.
    """
    from app.core.customer import CustomerManager
    from app.core.rbac import check_customer_access
    from app.services import tailscale_customers

    target = body.customer_id or None
    if target is not None:
        if not await check_customer_access(user, target):
            raise refusal(ForbiddenError, "err_customer_no_access")
        if CustomerManager.get_customer(target) is None:
            raise refusal(NotFoundError, "err_customer_not_found")
    from app.services import tailscale_api

    manual = await tailscale_customers.manual_assignments()
    try:
        devices = await tailscale_api.list_devices()
    except Exception as exc:
        raise refusal(IntegrationError, "err_tailscale_unreachable") from exc
    ids = [c["_id"] for c in CustomerManager.list_customers()]
    owners = tailscale_customers.resolve(devices, ids, manual)
    tag_owners = tailscale_customers.resolve(devices, ids, {})
    current = manual.get(device_id)
    for owner in (owners.get(device_id), tag_owners.get(device_id)):
        if owner and not await check_customer_access(user, owner[0]):
            raise refusal(ForbiddenError, "err_customer_no_access")
    if current and not await check_customer_access(user, current):
        raise refusal(ForbiddenError, "err_customer_no_access")
    await tailscale_customers.assign(device_id, target, user.username)

    from app.core.activity_log import log_activity

    log_activity(
        "tailscale_node_assigned",
        detail=f"{device_id} -> {target or '-'}",
        customer=target or current or "",
        user=user.username,
    )
    return {"ok": True, "device_id": device_id, "customer_id": target}


@router.delete("/tailscale/device/{device_id}")
async def tailscale_remove_device(device_id: str, user: User = _admin):
    """Remove a device from the tailnet."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        ok = await tailscale_api.delete_device(device_id)
        if ok:
            return {"ok": True}
        raise refusal(IntegrationError, "err_tailscale_remove_failed")
    except (IntegrationError, ValidationError):
        raise
    except Exception as e:
        log.warning("Tailscale delete device failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/device/{device_id}/tags")
async def tailscale_update_tags(device_id: str, body: TailscaleTags, user: User = _admin):
    """Update tags on a device."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        tags = body.tags
        from app.services import tailscale_api

        device = await tailscale_api.update_device_tags(device_id, tags)
        return {"ok": True, "device": device}
    except Exception as e:
        log.warning("Tailscale update tags failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/device/{device_id}/authorize")
async def tailscale_authorize(device_id: str, body: TailscaleAuthorize, user: User = _admin):
    """Authorize or deauthorize a device."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        ok = await tailscale_api.authorize_device(device_id, body.authorized)
        return {"ok": ok}
    except Exception as e:
        log.warning("Tailscale authorize device failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/device/{device_id}/name")
async def tailscale_rename(device_id: str, body: TailscaleRename, user: User = _admin):
    """Rename a device (set givenName)."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        name = body.name.strip()
        if not name:
            raise refusal(ValidationError, "err_name_required")
        from app.services import tailscale_api

        ok = await tailscale_api.rename_device(device_id, name)
        return {"ok": ok}
    except (IntegrationError, ValidationError):
        raise
    except Exception as e:
        log.warning("Tailscale rename device failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/device/{device_id}/key")
async def tailscale_set_key_expiry(device_id: str, body: TailscaleKeyExpiry, user: User = _admin):
    """Enable or disable key expiry on a device."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        ok = await tailscale_api.set_key_expiry(device_id, body.disabled)
        return {"ok": ok}
    except Exception as e:
        log.warning("Tailscale set key expiry failed: %s", e)
        raise IntegrationError(str(e)) from e


# ── Subnet Routes ────────────────────────────────────────────────────────────


@router.get("/tailscale/device/{device_id}/routes")
async def tailscale_get_routes(device_id: str, user: User = _tech):
    """Get advertised and enabled routes for a device."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        routes = await tailscale_api.get_device_routes(device_id)
        return routes
    except Exception as e:
        log.warning("Tailscale get routes failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/device/{device_id}/routes")
async def tailscale_set_routes(device_id: str, body: TailscaleRoutes, user: User = _admin):
    """Approve/set enabled routes for a device."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        routes = body.routes
        from app.services import tailscale_api

        result = await tailscale_api.set_device_routes(device_id, routes)
        return {"ok": True, "routes": result}
    except Exception as e:
        log.warning("Tailscale set routes failed: %s", e)
        raise IntegrationError(str(e)) from e


# ── Auth Keys ────────────────────────────────────────────────────────────────


@router.get("/tailscale/keys")
async def tailscale_list_keys(user: User = _tech):
    """List auth keys."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        keys = await tailscale_api.list_keys()
        return {"keys": keys}
    except Exception as e:
        log.warning("Tailscale list keys failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.post("/tailscale/keys")
async def tailscale_create_key(body: TailscaleKeyCreate, user: User = _admin):
    """Create an auth key."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        result = await tailscale_api.create_key(
            reusable=body.reusable,
            ephemeral=body.ephemeral,
            preauthorized=body.preauthorized,
            tags=body.tags,
            expiry_seconds=body.expiry_seconds,
            description=body.description,
        )
        return {"ok": True, "key": result}
    except Exception as e:
        log.warning("Tailscale create key failed: %s", e)
        raise IntegrationError(str(e)) from e


@router.delete("/tailscale/keys/{key_id}")
async def tailscale_revoke_key(key_id: str, user: User = _admin):
    """Revoke an auth key."""
    if not _ensure_configured():
        raise refusal(ValidationError, "err_tailscale_not_configured")
    try:
        from app.services import tailscale_api

        ok = await tailscale_api.delete_key(key_id)
        if ok:
            return {"ok": True}
        raise refusal(IntegrationError, "err_tailscale_revoke_failed")
    except IntegrationError:
        raise
    except Exception as e:
        log.warning("Tailscale revoke key failed: %s", e)
        raise IntegrationError(str(e)) from e


# ── Test connection ──────────────────────────────────────────────────────────


@router.post("/tailscale/test")
@connection_check("tailscale", {"api_key": "tailscale_api_key", "tailnet": "tailscale_tailnet"})
async def tailscale_test(body: TailscaleTest, user: User = _admin):
    """Test a Tailscale API key before saving (saving it is admin-only too)."""
    api_key = body.api_key.strip()
    tailnet = body.tailnet.strip() or "-"
    if api_key == "••••••":
        from app.web.connection_checks import connection_settings as load_app_settings

        api_key = load_app_settings().get("tailscale_api_key", "")
    if not api_key:
        raise ValidationError("API-nøkkel er påkrevd", message_key="err_no_api_key")

    import httpx as _httpx

    try:
        async with _httpx.AsyncClient(
            base_url="https://api.tailscale.com/api/v2",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        ) as c:
            resp = await c.get(f"/tailnet/{tailnet}/devices")
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("devices", []))
                return {"ok": True, "device_count": count, "tailnet": tailnet}
            elif resp.status_code == 401:
                raise ValidationError(
                    "Tailscale avviste API-nøkkelen. Bruk et gyldig API access token, "
                    "ikke en auth key for å koble til enheter.",
                    message_key="err_tailscale_credentials",
                )
            elif resp.status_code == 403:
                raise ValidationError(
                    "Tailscale-tokenet mangler tilgang til å lese enheter",
                    message_key="err_tailscale_scope",
                )
            else:
                raise refusal(IntegrationError, "err_tailscale_api_status", status=resp.status_code)
    except (IntegrationError, ValidationError):
        raise
    except Exception as e:
        log.warning("Tailscale API test failed: %s", e)
        raise IntegrationError(str(e)) from e
