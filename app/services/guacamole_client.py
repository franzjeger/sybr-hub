"""Low-level Guacamole REST API client: config, auth and connection cleanup.

Split out of ``app/web/routes/proxy.py`` so the periodic stale-connection
sweep in ``app/services/scheduler.py`` can call it without a service module
reaching into the web layer (``scripts/check_architecture.py`` forbids
that). The route handlers that create/tear down live RDP sessions stay in
``proxy.py`` and import the pieces below.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def _get_guac_config() -> dict:
    """Load Guacamole config from encrypted app settings with env var fallback."""
    from app.core.config import load_app_settings

    settings = load_app_settings()
    return {
        "url": settings.get("guacamole_url") or os.environ.get("GUACAMOLE_URL", ""),
        "user": settings.get("guacamole_user") or os.environ.get("GUACAMOLE_USER", ""),
        "pass": settings.get("guacamole_pass") or os.environ.get("GUACAMOLE_PASS", ""),
    }


# Hosts permitted as Guacamole backend. Default to loopback only — the
# Docker compose stack the app installs runs Guacamole on localhost:8888.
# Operators that legitimately need a remote Guacamole can opt in via the
# MSP_GUACAMOLE_HOSTS env var (comma-separated). This stops a compromised
# settings.json from redirecting RDP/VNC sessions through an attacker-
# controlled Guacamole that captures credentials in transit.
_GUAC_DEFAULT_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
_GUAC_EXTRA_HOSTS = {
    h.strip().lower() for h in os.environ.get("MSP_GUACAMOLE_HOSTS", "").split(",") if h.strip()
}
_GUAC_ALLOWED_HOSTS = _GUAC_DEFAULT_ALLOWED_HOSTS | _GUAC_EXTRA_HOSTS


def _validate_guac_url(url: str) -> str | None:
    """Return an error message if the configured Guacamole URL isn't safe.

    Rules: only http/https schemes, only allowlisted hosts. Empty URL is
    fine (the feature is just disabled).
    """
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Guacamole URL scheme must be http or https, got {parsed.scheme!r}"
    host = (parsed.hostname or "").lower()
    if host not in _GUAC_ALLOWED_HOSTS:
        return (
            f"Guacamole host {host!r} is not in the allowlist. "
            f"Allowed: {sorted(_GUAC_ALLOWED_HOSTS)}. "
            f"Add to MSP_GUACAMOLE_HOSTS env var if intentional."
        )
    return None


def _guac_base() -> str:
    """Return the Guacamole base URL from config, validated against allowlist.

    Returns "" if the configured URL is unsafe — callers already handle
    empty URL as "Guacamole not configured" so RDP/VNC stays disabled
    rather than reaching out to an attacker host.
    """
    url = _get_guac_config()["url"]
    err = _validate_guac_url(url)
    if err:
        logger.error("Guacamole URL rejected: %s", err)
        return ""
    return url


# Connections created through the JDBC API persist their parameters (including
# passwords) in Guacamole's database. Give every connection a unique,
# instance-owned name so it is never reused and can be removed after a crash.
_GUAC_INSTANCE = re.sub(
    r"[^A-Za-z0-9_.-]",
    "_",
    os.environ.get("SYBR_GUAC_INSTANCE_ID") or socket.gethostname(),
)[:48]
_GUAC_MANAGED_PREFIX = f"Sybr-HUB-Ephemeral-{_GUAC_INSTANCE}-"
_GUAC_BOOT_PREFIX = f"{_GUAC_MANAGED_PREFIX}{secrets.token_hex(6)}-"


async def _guac_login() -> str | None:
    """Authenticate with Guacamole and return an auth token, or None."""
    cfg = _get_guac_config()
    base = _guac_base()
    if not base or not cfg["user"]:
        logger.warning("Guacamole login skipped — URL or user not configured")
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base}/api/tokens",
            data={"username": cfg["user"], "password": cfg["pass"]},
        )
        if resp.status_code == 200:
            return resp.json().get("authToken")
    return None


async def _guac_delete_connection(token: str, connection_id: str) -> bool:
    """Delete a Guacamole connection. Returns True on success."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.delete(
            f"{_guac_base()}/api/session/data/mysql/connections/{connection_id}",
            params={"token": token},
        )
        # 404 is already clean. Treat authentication failure as retryable by
        # callers, which can obtain a fresh Guacamole token.
        return resp.status_code in (200, 204, 404)


async def _guac_delete_with_fresh_token(token: str, connection_id: str) -> bool:
    """Delete a connection, retrying once with a fresh admin token."""
    if await _guac_delete_connection(token, connection_id):
        return True
    fresh = await _guac_login()
    return bool(fresh and await _guac_delete_connection(fresh, connection_id))


async def cleanup_stale_guacamole_connections() -> int:
    """Delete managed connections left by an earlier Sybr HUB process.

    The JDBC backend stores connection parameters as database name/value pairs,
    so a process crash otherwise leaves RDP/VNC passwords behind indefinitely.
    Current-boot names are excluded to avoid touching live sessions.
    """
    if not _guac_base():
        return 0
    token = await _guac_login()
    if not token:
        return 0
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{_guac_base()}/api/session/data/mysql/connections",
            params={"token": token},
        )
    if response.status_code != 200:
        logger.warning(
            "Could not enumerate stale Guacamole connections: HTTP %d", response.status_code
        )
        return 0

    stale = [
        str(connection_id)
        for connection_id, connection in response.json().items()
        if str(connection.get("name") or "").startswith(_GUAC_MANAGED_PREFIX)
        and not str(connection.get("name") or "").startswith(_GUAC_BOOT_PREFIX)
    ]
    deleted = 0
    for connection_id in stale:
        try:
            if await _guac_delete_with_fresh_token(token, connection_id):
                deleted += 1
            else:
                logger.warning("Could not delete stale Guacamole connection %s", connection_id)
        except Exception as exc:
            logger.warning("Could not delete stale Guacamole connection %s: %s", connection_id, exc)
    if deleted:
        logger.info("Deleted %d stale Sybr HUB Guacamole connection(s)", deleted)
    return deleted
