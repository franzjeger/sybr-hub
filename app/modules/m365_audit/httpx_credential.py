"""azure-identity-compatible credential that uses httpx for token acquisition.

Replaces azure.identity.aio.ClientSecretCredential to eliminate the aiohttp
dependency inside azure-core's async pipeline transport.
"""

from __future__ import annotations

import time
from typing import Optional

import httpx
from azure.core.credentials import AccessToken

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class HttpxClientSecretCredential:
    """
    Async credential for client-credentials OAuth flow via httpx.
    API-compatible with azure.identity.aio.ClientSecretCredential.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self._tenant_id     = tenant_id
        self._client_id     = client_id
        self._client_secret = client_secret
        self._cache:  dict[str, AccessToken] = {}  # scope → token

    async def get_token(self, *scopes: str, **_kwargs) -> AccessToken:
        scope = scopes[0] if scopes else "https://graph.microsoft.com/.default"

        cached = self._cache.get(scope)
        if cached and time.time() < cached.expires_on - 60:
            return cached

        url = _TOKEN_URL.format(tenant=self._tenant_id)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, data={
                "grant_type":    "client_credentials",
                "client_id":     self._client_id,
                "client_secret": self._client_secret,
                "scope":         scope,
            })
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"Token acquisition failed: {data.get('error')} — "
                f"{data.get('error_description', '')}"
            )

        expires_on = int(time.time()) + int(data.get("expires_in", 3600))
        token = AccessToken(data["access_token"], expires_on)
        self._cache[scope] = token
        return token

    async def close(self) -> None:
        self._cache.clear()

    async def __aenter__(self) -> "HttpxClientSecretCredential":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
