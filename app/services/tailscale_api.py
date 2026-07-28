"""Tailscale API client — device inventory, auth keys, status monitoring.

Uses httpx with a shared cached client.  Requires an API access token
generated from the Tailscale admin console (Settings → Keys → API access tokens).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_BASE = "https://api.tailscale.com/api/v2"
_client: Optional[httpx.AsyncClient] = None
_api_key: Optional[str] = None
_tailnet: Optional[str] = None


def configure(api_key: str, tailnet: str = "-") -> None:
    """Set credentials and reset the shared client."""
    global _api_key, _tailnet, _client
    _api_key = api_key
    _tailnet = tailnet
    if _client:
        # Will be lazily recreated
        _client = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        if not _api_key:
            raise RuntimeError("Tailscale API key not configured")
        _client = httpx.AsyncClient(
            base_url=_BASE,
            headers={"Authorization": f"Bearer {_api_key}"},
            timeout=15.0,
        )
    return _client


def _tailnet_id() -> str:
    return _tailnet or "-"


# ── Devices ──────────────────────────────────────────────────────────────────

async def list_devices() -> list[dict]:
    """Fetch all devices in the tailnet."""
    c = _get_client()
    resp = await c.get(f"/tailnet/{_tailnet_id()}/devices?fields=all")
    resp.raise_for_status()
    data = resp.json()
    devices = data.get("devices", [])
    return [_normalize_device(d) for d in devices]


async def get_device(device_id: str) -> dict:
    """Fetch a single device by ID."""
    c = _get_client()
    resp = await c.get(f"/device/{device_id}")
    resp.raise_for_status()
    return _normalize_device(resp.json())


async def delete_device(device_id: str) -> bool:
    """Remove a device from the tailnet."""
    c = _get_client()
    resp = await c.delete(f"/device/{device_id}")
    return resp.status_code in (200, 204)


async def update_device_tags(device_id: str, tags: list[str]) -> dict:
    """Update tags on a device."""
    c = _get_client()
    resp = await c.post(f"/device/{device_id}/tags", json={"tags": tags})
    resp.raise_for_status()
    return _normalize_device(resp.json())


async def authorize_device(device_id: str, authorized: bool = True) -> bool:
    """Authorize or deauthorize a device."""
    c = _get_client()
    resp = await c.post(f"/device/{device_id}/authorized", json={"authorized": authorized})
    return resp.status_code in (200, 204)


async def rename_device(device_id: str, name: str) -> bool:
    """Set a device's display name (givenName)."""
    c = _get_client()
    resp = await c.post(f"/device/{device_id}/name", json={"name": name})
    return resp.status_code in (200, 204)


async def set_key_expiry(device_id: str, disabled: bool) -> bool:
    """Enable or disable key expiry on a device."""
    c = _get_client()
    resp = await c.post(f"/device/{device_id}/key", json={"keyExpiryDisabled": disabled})
    return resp.status_code in (200, 204)


# ── Subnet Routes ────────────────────────────────────────────────────────────

async def get_device_routes(device_id: str) -> dict:
    """Get advertised and enabled routes for a device."""
    c = _get_client()
    resp = await c.get(f"/device/{device_id}/routes")
    resp.raise_for_status()
    data = resp.json()
    advertised = data.get("advertisedRoutes", [])
    enabled = data.get("enabledRoutes", [])
    return {
        "advertised": advertised,
        "enabled": enabled,
        "routes": [
            {"route": r, "enabled": r in enabled, "is_exit_node": r in ("0.0.0.0/0", "::/0")}
            for r in advertised
        ],
    }


async def set_device_routes(device_id: str, routes: list[str]) -> dict:
    """Approve/set enabled routes for a device."""
    c = _get_client()
    resp = await c.post(f"/device/{device_id}/routes", json={"routes": routes})
    resp.raise_for_status()
    return resp.json()


def _normalize_device(d: dict) -> dict:
    """Flatten a Tailscale device object into our standard shape."""
    now = datetime.now(timezone.utc)

    # Parse lastSeen / created timestamps
    last_seen_str = d.get("lastSeen", "")
    created_str = d.get("created", "")
    last_seen = _parse_ts(last_seen_str)
    created = _parse_ts(created_str)

    # Online detection — Tailscale uses "connectedToControl", not "online"
    is_online = d.get("connectedToControl", d.get("online", False))

    # Stale detection (not seen in >7 days)
    stale_days = None
    if last_seen:
        stale_days = (now - last_seen).days

    # Key expiry
    key_expiry_str = d.get("keyExpiryDisabled") if d.get("keyExpiryDisabled") else d.get("expires", "")
    key_expiry = _parse_ts(key_expiry_str) if isinstance(key_expiry_str, str) else None
    key_days_left = (key_expiry - now).days if key_expiry else None
    key_expiry_disabled = d.get("keyExpiryDisabled", False)

    # IP addresses
    addresses = d.get("addresses", [])
    tailscale_ip = addresses[0] if addresses else None

    return {
        "id": d.get("id") or d.get("nodeId", ""),
        "node_id": d.get("nodeId", ""),
        "name": d.get("name", ""),
        "hostname": d.get("hostname", ""),
        "given_name": d.get("givenName", ""),
        "os": d.get("os", ""),
        "client_version": d.get("clientVersion", ""),
        "tailscale_ip": tailscale_ip,
        "addresses": addresses,
        "tags": d.get("tags", []),
        "user": d.get("user", ""),
        "online": is_online,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "last_seen_ago": _human_ago(stale_days) if stale_days is not None else None,
        "stale_days": stale_days,
        "created": created.isoformat() if created else None,
        "authorized": d.get("authorized", False),
        "is_external": d.get("isExternal", False),
        "update_available": d.get("updateAvailable", False),
        "key_expiry": key_expiry.isoformat() if key_expiry else None,
        "key_days_left": key_days_left,
        "key_expiry_disabled": key_expiry_disabled,
        "blocks_incoming": d.get("blocksIncomingConnections", False),
        "machine_key": d.get("machineKey", ""),
        "node_key": d.get("nodeKey", ""),
        "advertised_routes": d.get("advertisedRoutes", []),
        "enabled_routes": d.get("enabledRoutes", []),
        "is_exit_node": "0.0.0.0/0" in d.get("enabledRoutes", []),
        "client_connectivity": d.get("clientConnectivity", {}),
    }


# ── Auth Keys ────────────────────────────────────────────────────────────────

async def list_keys() -> list[dict]:
    """List auth keys in the tailnet."""
    c = _get_client()
    resp = await c.get(f"/tailnet/{_tailnet_id()}/keys")
    resp.raise_for_status()
    data = resp.json()
    keys = data.get("keys", data) if isinstance(data, dict) else data
    if not isinstance(keys, list):
        keys = []
    return [_normalize_key(k) for k in keys]


async def create_key(
    reusable: bool = False,
    ephemeral: bool = False,
    preauthorized: bool = True,
    tags: list[str] | None = None,
    expiry_seconds: int = 86400,
    description: str = "",
) -> dict:
    """Create an auth key."""
    c = _get_client()
    body: dict = {
        "capabilities": {
            "devices": {
                "create": {
                    "reusable": reusable,
                    "ephemeral": ephemeral,
                    "preauthorized": preauthorized,
                    "tags": tags or [],
                }
            }
        },
        "expirySeconds": expiry_seconds,
    }
    if description:
        body["description"] = description
    resp = await c.post(f"/tailnet/{_tailnet_id()}/keys", json=body)
    resp.raise_for_status()
    return resp.json()


async def delete_key(key_id: str) -> bool:
    """Revoke/delete an auth key."""
    c = _get_client()
    resp = await c.delete(f"/tailnet/{_tailnet_id()}/keys/{key_id}")
    return resp.status_code in (200, 204)


def _normalize_key(k: dict) -> dict:
    created = _parse_ts(k.get("created", ""))
    expires = _parse_ts(k.get("expires", ""))
    now = datetime.now(timezone.utc)
    return {
        "id": k.get("id", ""),
        "description": k.get("description", ""),
        "created": created.isoformat() if created else None,
        "expires": expires.isoformat() if expires else None,
        "days_left": (expires - now).days if expires else None,
        "revoked": k.get("revoked", False),
        "capabilities": k.get("capabilities", {}),
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(s: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string (Tailscale format)."""
    if not s:
        return None
    try:
        # Handle Tailscale's format: 2024-01-15T10:30:00Z or with offset
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _human_ago(days: int) -> str:
    """Convert days-ago into a human-readable string."""
    if days == 0:
        return "i dag"
    if days == 1:
        return "1 dag siden"
    if days < 7:
        return f"{days} dager siden"
    if days < 30:
        weeks = days // 7
        return f"{weeks} uke{'r' if weeks > 1 else ''} siden"
    if days < 365:
        months = days // 30
        return f"{months} måned{'er' if months > 1 else ''} siden"
    years = days // 365
    return f"{years} år siden"
