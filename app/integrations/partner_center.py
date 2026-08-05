"""Microsoft Partner Center REST API client.

Provides async access to customer lists and GDAP relationship management
for MSP partners using Granular Delegated Admin Privileges.

Auth: Client credentials OAuth2 against the partner tenant, with scope
``https://api.partnercenter.microsoft.com/.default``.

Docs: https://learn.microsoft.com/en-us/partner-center/developer/
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.integrations.http_retry import send_with_retry

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_PC_SCOPE = "https://api.partnercenter.microsoft.com/.default"
_PC_BASE = "https://api.partnercenter.microsoft.com"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class PartnerCenterError(Exception):
    """Raised on Partner Center API errors."""
    pass


class PartnerCenterClient:
    """Async client for the Microsoft Partner Center REST API."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._pc_token: Optional[str] = None
        self._pc_token_expires: float = 0
        self._graph_token: Optional[str] = None
        self._graph_token_expires: float = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self._client.aclose()

    # ── Token acquisition ────────────────────────────────────────────────

    async def _acquire_token(self, scope: str) -> str:
        """Acquire an OAuth2 client_credentials token for the given scope."""
        url = _TOKEN_URL.format(tenant=self._tenant_id)
        # Token endpoint: a 429 here takes the whole client down.
        resp = await send_with_retry(
            lambda: self._client.post(url, data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                }),
            method="POST", target="Partner Center token",
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise PartnerCenterError(
                f"Token error: {data.get('error')} — {data.get('error_description', '')}"
            )

        return data["access_token"]

    async def _ensure_pc_token(self) -> str:
        """Get (or refresh) the Partner Center access token."""
        if self._pc_token and time.time() < self._pc_token_expires - 60:
            return self._pc_token

        self._pc_token = await self._acquire_token(_PC_SCOPE)
        self._pc_token_expires = time.time() + 3500  # ~1 hour
        return self._pc_token

    async def _ensure_graph_token(self) -> str:
        """Get (or refresh) a Graph token for GDAP relationship queries."""
        if self._graph_token and time.time() < self._graph_token_expires - 60:
            return self._graph_token

        self._graph_token = await self._acquire_token(_GRAPH_SCOPE)
        self._graph_token_expires = time.time() + 3500
        return self._graph_token

    # ── HTTP helpers ─────────────────────────────────────────────────────

    async def _pc_get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET from Partner Center API with auto-auth and retry on 429."""
        token = await self._ensure_pc_token()
        url = f"{_PC_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        for attempt in range(3):
            resp = await send_with_retry(
                lambda: self._client.get(url, headers=headers, params=params),
                method="GET", target=f"Partner Center {url}",
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning("Partner Center 429 — retrying in %ds", retry_after)
                import asyncio
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 401:
                # Force token refresh
                self._pc_token = None
                token = await self._ensure_pc_token()
                headers["Authorization"] = f"Bearer {token}"
                continue

            resp.raise_for_status()
            return resp.json()

        raise PartnerCenterError(f"Failed after 3 attempts: {path}")

    async def _graph_get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET from Microsoft Graph API (partner tenant context)."""
        token = await self._ensure_graph_token()
        url = f"{_GRAPH_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        for attempt in range(3):
            resp = await send_with_retry(
                lambda: self._client.get(url, headers=headers, params=params),
                method="GET", target=f"Partner Center {url}",
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                import asyncio
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 401:
                self._graph_token = None
                token = await self._ensure_graph_token()
                headers["Authorization"] = f"Bearer {token}"
                continue

            resp.raise_for_status()
            return resp.json()

        raise PartnerCenterError(f"Graph request failed after 3 attempts: {path}")

    # ── Customer operations ──────────────────────────────────────────────

    async def list_customers(self) -> list[dict]:
        """List all customers visible to this partner.

        Returns a list of customer objects with companyProfile containing
        tenantId, domain, and companyName.
        """
        result = await self._pc_get("/v1/customers", params={"size": 999})
        items = result.get("items", [])
        logger.info("Partner Center: %d customers found", len(items))
        return items

    async def get_customer(self, customer_tenant_id: str) -> dict:
        """Get details for a specific customer."""
        return await self._pc_get(f"/v1/customers/{customer_tenant_id}")

    async def get_customer_subscriptions(self, customer_tenant_id: str) -> list[dict]:
        """List subscriptions for a specific customer."""
        result = await self._pc_get(
            f"/v1/customers/{customer_tenant_id}/subscriptions"
        )
        return result.get("items", [])

    # ── GDAP relationship operations ─────────────────────────────────────

    async def list_gdap_relationships(self) -> list[dict]:
        """List all GDAP (delegatedAdminRelationships) via Graph API.

        Returns relationships with status, customer info, and role assignments.
        """
        all_rels: list[dict] = []
        url = "/tenantRelationships/delegatedAdminRelationships"
        params = {"$top": "100"}

        while url:
            data = await self._graph_get(url, params=params)
            all_rels.extend(data.get("value", []))

            # Handle pagination
            next_link = data.get("@odata.nextLink", "")
            if next_link:
                # Strip the base URL — _graph_get will add it back
                url = next_link.replace(_GRAPH_BASE, "")
                params = None  # params are in the nextLink
            else:
                url = ""

        logger.info("GDAP: %d relationships found", len(all_rels))
        return all_rels

    async def get_gdap_relationship(self, relationship_id: str) -> dict:
        """Get a specific GDAP relationship."""
        return await self._graph_get(
            f"/tenantRelationships/delegatedAdminRelationships/{relationship_id}"
        )
