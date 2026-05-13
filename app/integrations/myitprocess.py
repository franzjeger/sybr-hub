"""myITprocess client — STUB.

Workshop intent: audit findings that need planning (e.g. "DKIM
missing on 4 domains" — solvable but needs scheduling, not a 5-minute
ticket) get pushed to myITprocess as **Recommendations**, where they
flow through the customer's quarterly business review.

Separation from Autotask:
    Autotask ticket          = something to fix this week
    myITprocess recommendation = something to plan next quarter

The operator chooses which bucket each finding belongs in. This stub
defines the contract for the push.

API reference: https://app.myitprocess.com/developer/api
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class MyITProcessError(Exception):
    """myITprocess API call failed."""


class MyITProcessClient:
    """Async client for myITprocess Recommendations API."""

    def __init__(self, api_key: str, base_url: str = "https://api.myitprocess.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def __aenter__(self) -> "MyITProcessClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self._client.aclose()

    async def list_accounts(self) -> list[dict[str, Any]]:
        """List myITprocess accounts — used to bind Sybr HUB customers
        to their myITprocess counterpart."""
        raise NotImplementedError(
            "MyITProcessClient.list_accounts: implement in the integration PR."
        )

    async def create_recommendation(
        self,
        account_id: str,
        title: str,
        detail: str,
        *,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        source_finding_id: Optional[str] = None,
    ) -> str:
        """Push a Recommendation to myITprocess. Returns recommendation id.

        ``source_finding_id`` should be the originating audit finding
        identifier (e.g. ``"finding-mfa"``) so we can later avoid
        creating duplicates on re-runs.

        Manual operator action; never invoked from a scheduled audit.
        """
        raise NotImplementedError(
            "MyITProcessClient.create_recommendation: implement in the integration PR."
        )
