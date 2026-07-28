"""Tailscale integration routes — device inventory, auth keys, status."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user, require_role

log = logging.getLogger(__name__)
router = APIRouter(tags=["tailscale"])

_auth = Depends(get_current_user)
_tech = Depends(require_role(Role.technician))


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
async def tailscale_status(user: User = _auth):
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
async def tailscale_devices(user: User = _auth):
    """List all devices in the tailnet."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        from app.services import tailscale_api
        devices = await tailscale_api.list_devices()

        online = [d for d in devices if d["online"]]
        offline = [d for d in devices if not d["online"]]
        stale = [d for d in devices if d["stale_days"] is not None and d["stale_days"] > 7]
        expiring_keys = [d for d in devices if d["key_days_left"] is not None and d["key_days_left"] < 30 and not d["key_expiry_disabled"]]

        return {
            "devices": devices,
            "total": len(devices),
            "online": len(online),
            "offline": len(offline),
            "stale": len(stale),
            "expiring_keys": len(expiring_keys),
        }
    except Exception as e:
        log.exception("Tailscale device list failed")
        raise IntegrationError(str(e))


@router.delete("/tailscale/device/{device_id}")
async def tailscale_remove_device(device_id: str, user: User = _tech):
    """Remove a device from the tailnet."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        from app.services import tailscale_api
        ok = await tailscale_api.delete_device(device_id)
        if ok:
            return {"ok": True}
        raise IntegrationError("Kunne ikke fjerne enhet")
    except (IntegrationError, ValidationError):
        raise
    except Exception as e:
        log.warning("Tailscale delete device failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/device/{device_id}/tags")
async def tailscale_update_tags(device_id: str, request: Request, user: User = _tech):
    """Update tags on a device."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        tags = body.get("tags", [])
        from app.services import tailscale_api
        device = await tailscale_api.update_device_tags(device_id, tags)
        return {"ok": True, "device": device}
    except Exception as e:
        log.warning("Tailscale update tags failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/device/{device_id}/authorize")
async def tailscale_authorize(device_id: str, request: Request, user: User = _tech):
    """Authorize or deauthorize a device."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        from app.services import tailscale_api
        ok = await tailscale_api.authorize_device(device_id, body.get("authorized", True))
        return {"ok": ok}
    except Exception as e:
        log.warning("Tailscale authorize device failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/device/{device_id}/name")
async def tailscale_rename(device_id: str, request: Request, user: User = _tech):
    """Rename a device (set givenName)."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            raise ValidationError("Navn er påkrevd")
        from app.services import tailscale_api
        ok = await tailscale_api.rename_device(device_id, name)
        return {"ok": ok}
    except (IntegrationError, ValidationError):
        raise
    except Exception as e:
        log.warning("Tailscale rename device failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/device/{device_id}/key")
async def tailscale_set_key_expiry(device_id: str, request: Request, user: User = _tech):
    """Enable or disable key expiry on a device."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        from app.services import tailscale_api
        ok = await tailscale_api.set_key_expiry(device_id, body.get("disabled", False))
        return {"ok": ok}
    except Exception as e:
        log.warning("Tailscale set key expiry failed: %s", e)
        raise IntegrationError(str(e))


# ── Subnet Routes ────────────────────────────────────────────────────────────

@router.get("/tailscale/device/{device_id}/routes")
async def tailscale_get_routes(device_id: str, user: User = _auth):
    """Get advertised and enabled routes for a device."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        from app.services import tailscale_api
        routes = await tailscale_api.get_device_routes(device_id)
        return routes
    except Exception as e:
        log.warning("Tailscale get routes failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/device/{device_id}/routes")
async def tailscale_set_routes(device_id: str, request: Request, user: User = _tech):
    """Approve/set enabled routes for a device."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        routes = body.get("routes", [])
        from app.services import tailscale_api
        result = await tailscale_api.set_device_routes(device_id, routes)
        return {"ok": True, "routes": result}
    except Exception as e:
        log.warning("Tailscale set routes failed: %s", e)
        raise IntegrationError(str(e))


# ── Auth Keys ────────────────────────────────────────────────────────────────

@router.get("/tailscale/keys")
async def tailscale_list_keys(user: User = _auth):
    """List auth keys."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        from app.services import tailscale_api
        keys = await tailscale_api.list_keys()
        return {"keys": keys}
    except Exception as e:
        log.warning("Tailscale list keys failed: %s", e)
        raise IntegrationError(str(e))


@router.post("/tailscale/keys")
async def tailscale_create_key(request: Request, user: User = _tech):
    """Create an auth key."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        body = await request.json()
        from app.services import tailscale_api
        result = await tailscale_api.create_key(
            reusable=body.get("reusable", False),
            ephemeral=body.get("ephemeral", False),
            preauthorized=body.get("preauthorized", True),
            tags=body.get("tags", []),
            expiry_seconds=int(body.get("expiry_seconds", 86400)),
            description=body.get("description", ""),
        )
        return {"ok": True, "key": result}
    except Exception as e:
        log.warning("Tailscale create key failed: %s", e)
        raise IntegrationError(str(e))


@router.delete("/tailscale/keys/{key_id}")
async def tailscale_revoke_key(key_id: str, user: User = _tech):
    """Revoke an auth key."""
    if not _ensure_configured():
        raise ValidationError("Tailscale API-nøkkel er ikke konfigurert")
    try:
        from app.services import tailscale_api
        ok = await tailscale_api.delete_key(key_id)
        if ok:
            return {"ok": True}
        raise IntegrationError("Kunne ikke tilbakekalle nøkkel")
    except IntegrationError:
        raise
    except Exception as e:
        log.warning("Tailscale revoke key failed: %s", e)
        raise IntegrationError(str(e))


# ── Test connection ──────────────────────────────────────────────────────────

@router.post("/tailscale/test")
async def tailscale_test(request: Request, user: User = _auth):
    """Test a Tailscale API key before saving."""
    body = await request.json()
    api_key = body.get("api_key", "").strip()
    tailnet = body.get("tailnet", "-").strip() or "-"
    if not api_key:
        raise ValidationError("API-nøkkel er påkrevd")

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
                raise AuthError("Ugyldig API-nøkkel")
            elif resp.status_code == 403:
                raise AuthError("API-nøkkel mangler device:read-tilgang")
            else:
                raise IntegrationError(f"Tailscale API returnerte {resp.status_code}")
    except (IntegrationError, AuthError):
        raise
    except Exception as e:
        log.warning("Tailscale API test failed: %s", e)
        raise IntegrationError(str(e))
