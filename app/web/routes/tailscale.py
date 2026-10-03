"""Tailscale integration routes — device inventory, auth keys, status."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.exceptions import (
    IntegrationError,
    ValidationError,
)
from app.models.tailscale import (
    TailscaleAuthorize,
    TailscaleKeyCreate,
    TailscaleKeyExpiry,
    TailscaleRename,
    TailscaleRoutes,
    TailscaleTags,
    TailscaleTest,
)
from app.models.user import Role, User
from app.web.i18n import refusal
from app.web.middleware.auth import require_feature, require_module, require_role

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
    from app.core.config import load_app_settings

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
    from app.core.config import load_app_settings

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
async def tailscale_test(body: TailscaleTest, user: User = _admin):
    """Test a Tailscale API key before saving (saving it is admin-only too)."""
    api_key = body.api_key.strip()
    tailnet = body.tailnet.strip() or "-"
    if api_key == "••••••":
        from app.core.config import load_app_settings

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
