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

from app.integrations.http_retry import RetryExhausted, send_with_retry
from app.modules.api_result import ApiDict, ApiList, read_failed

log = logging.getLogger(__name__)


class FortiGateClient:
    """Async FortiGate REST API client."""

    def __init__(
        self,
        host: str,
        api_token: str,
        port: int = 443,
        vdom: str = "root",
        verify_ssl: bool = True,
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

    async def _get(self, path: str, params: dict | None = None) -> ApiDict:
        """Raw GET request. Returns an :class:`ApiDict` carrying ``.error``.

        Retried through the shared layer rather than tried once. A FortiGate
        sits at the far end of a VPN tunnel to a customer site, so a transient
        connection failure is routine in a way it is not for a SaaS API — and
        the audit that gives up on the first one reports a firewall as
        unreadable when a second attempt two seconds later would have worked.

        A read is always safe to repeat, so this asks for no special handling
        beyond naming its method.

        The failure return is an *empty* ApiDict carrying the reason, not the
        old ``{"error": ...}`` sentinel. That sentinel was indistinguishable
        from a real read to every caller that only did ``.get(...)``, so a
        firewall the audit could not reach scored as one with nothing to flag.
        ``.error`` is how ``get_cmdb`` / ``get_monitor`` and every audit above
        them tell "refused" from "clean".
        """
        try:
            r = await send_with_retry(
                lambda: self._client.get(path, params=params),
                method="GET", target=f"FortiGate {path}",
            )
            r.raise_for_status()
            body = r.json()
            return ApiDict(body if isinstance(body, dict) else {"results": body})
        except RetryExhausted as e:
            log.warning("FortiGate API %s: %s", path, e)
            return ApiDict(error=str(e))
        except httpx.HTTPStatusError as e:
            log.warning("FortiGate API %s: HTTP %d", path, e.response.status_code)
            return ApiDict(error=f"HTTP {e.response.status_code}")
        except Exception as e:
            log.warning("FortiGate API %s: %s", path, e)
            return ApiDict(error=str(e))

    async def get_cmdb(self, path: str, params: dict | None = None) -> ApiList | ApiDict:
        """GET from /api/v2/cmdb/ — returns configuration data.

        Most cmdb endpoints return ``{"results": [...]}``; this returns the
        results directly — an :class:`ApiList` for the collection endpoints, an
        :class:`ApiDict` for the single-object ones.

        On a failed read it returns an empty ``ApiList`` carrying ``.error``.
        That is safe at every existing call site — they iterate it (empty),
        ``len`` it (0, not the 1 the old ``{"error":...}`` dict gave), or
        ``isinstance``-guard it (it is a list) — while ``read_failed(result)``
        lets an audit tell a firewall it could not read from one with no
        findings. Collection semantics because that is the common case; the
        handful of single-object callers already guard on shape and treat a
        non-dict as absent.
        """
        p = params or {}
        p.setdefault("vdom", self.vdom)
        data = await self._get(f"/api/v2/cmdb/{path}", p)
        if read_failed(data):
            return ApiList(error=data.error)
        results = data.get("results", data)
        if isinstance(results, list):
            return ApiList(results)
        return ApiDict(results if isinstance(results, dict) else {})

    async def get_monitor(self, path: str, params: dict | None = None) -> ApiDict:
        """GET from /api/v2/monitor/ — returns runtime/status data.

        Always an :class:`ApiDict`, so ``.get(...)`` is safe. On a failed read
        it is empty and carries ``.error``; ``.get(field, default)`` returns the
        default exactly as the old sentinel did, but ``read_failed(result)`` now
        distinguishes "the field was absent" from "the device could not be read"
        — the difference between a real 0% CPU and a firewall that refused.
        """
        p = params or {}
        p.setdefault("vdom", self.vdom)
        data = await self._get(f"/api/v2/monitor/{path}", p)
        if read_failed(data):
            return ApiDict(error=data.error)
        results = data.get("results", data)
        # Some monitor endpoints return a list under "results"; the outer dict
        # is what callers expect (they read .get("results") or iterate it), so
        # hand back the outer object rather than the bare list.
        if isinstance(results, dict):
            return ApiDict(results)
        return ApiDict(data)

    # ── Convenience methods ───────────────────────────────────────────────

    async def get_system_status(self) -> dict:
        """Get system status (firmware, hostname, serial, uptime)."""
        return await self.get_monitor("system/status")

    async def test_connection(self) -> dict:
        """Test API connectivity. Returns {ok, hostname, firmware, serial} or {ok, error}."""
        try:
            status = await self.get_system_status()
            if read_failed(status):
                return {"ok": False, "error": status.error}
            return {
                "ok": True,
                "hostname": status.get("hostname", ""),
                "firmware": status.get("version", ""),
                "serial": status.get("serial", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
