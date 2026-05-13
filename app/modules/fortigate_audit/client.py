"""FortiGate REST API client for audit data collection.

Supports API token authentication against FortiOS REST API v2.
Handles self-signed TLS certificates, VDOM selection, and pagination.

Usage:
    async with FortiGateClient("192.168.1.1", api_token="...") as fg:
        status = await fg.get_monitor("system/status")
        policies = await fg.get_cmdb("firewall/policy")
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class FortiGateClient:
    """Async FortiGate REST API client."""

    def __init__(
        self,
        host: str,
        api_token: str,
        port: int = 443,
        vdom: str = "root",
        verify_ssl: bool = False,
        timeout: float = 30.0,
    ):
        self.host = host.rstrip("/")
        self.port = port
        self.vdom = vdom
        self.base_url = f"https://{self.host}:{self.port}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            verify=verify_ssl,
            timeout=timeout,
        )

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ── Core request methods ──────────────────────────────────────────────

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Raw GET request. Returns parsed JSON."""
        try:
            r = await self._client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            log.warning("FortiGate API %s: HTTP %d", path, e.response.status_code)
            return {"error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            log.warning("FortiGate API %s: %s", path, e)
            return {"error": str(e)}

    async def get_cmdb(self, path: str, params: dict | None = None) -> list | dict:
        """GET from /api/v2/cmdb/ — returns configuration data.

        Most cmdb endpoints return {"results": [...]}. This method
        returns the results list directly.
        """
        p = params or {}
        p.setdefault("vdom", self.vdom)
        data = await self._get(f"/api/v2/cmdb/{path}", p)
        if isinstance(data, dict):
            return data.get("results", data)
        return data  # Already a list or unexpected type

    async def get_monitor(self, path: str, params: dict | None = None) -> dict:
        """GET from /api/v2/monitor/ — returns runtime/status data.

        Always returns a dict. If the API returns a list or errors,
        wraps it so callers can safely use .get().
        """
        p = params or {}
        p.setdefault("vdom", self.vdom)
        data = await self._get(f"/api/v2/monitor/{path}", p)
        if isinstance(data, dict):
            results = data.get("results", data)
            # results can be a list for some endpoints — wrap it
            if isinstance(results, dict):
                return results
            return data  # Return the outer dict which has "error" key etc.
        return {}  # Non-dict response (shouldn't happen) — return empty dict

    # ── Convenience methods ───────────────────────────────────────────────

    async def get_system_status(self) -> dict:
        """Get system status (firmware, hostname, serial, uptime)."""
        return await self.get_monitor("system/status")

    async def test_connection(self) -> dict:
        """Test API connectivity. Returns {ok, hostname, firmware, serial} or {ok, error}."""
        try:
            status = await self.get_system_status()
            if "error" in status:
                return {"ok": False, "error": status["error"]}
            return {
                "ok": True,
                "hostname": status.get("hostname", ""),
                "firmware": status.get("version", ""),
                "serial": status.get("serial", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
