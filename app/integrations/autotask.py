"""Autotask PSA REST API client — STUB.

The Autotask integration is the keystone of the Sybr HUB vision: read
customer Classification + contract details, and provide a manual
'Create Ticket' action from audit findings. This stub establishes the
client surface; real endpoints are wired in as features land.

Workshop intent (do not deviate):
    READ : Account, Classification, Contract
    WRITE: CreateTicket — always manual, never automatic.

Why this matters: an MSP technician reviewing a customer's audit
findings should be able to convert a finding into an Autotask ticket
with one click and the right context pre-filled. Automatic ticket
creation was *explicitly rejected* in the workshop — operator
discretion is part of the workflow.

API reference: https://ww1.autotask.net/help/Content/AdminSetup/2ExtensionsIntegrations/APIs/REST/REST_API_Home.htm
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class AutotaskError(Exception):
    """Autotask API call failed."""


class AutotaskClient:
    """Async client for the Autotask PSA REST API.

    Auth is via three headers: ApiIntegrationCode, UserName, Secret.
    See Autotask's "Create an API user" docs for provisioning credentials.

    This stub returns NotImplementedError on every endpoint; real
    implementations are added per feature.
    """

    def __init__(
        self,
        api_integration_code: str,
        username: str,
        secret: str,
        zone_url: str,
    ):
        self.api_integration_code = api_integration_code
        self.username = username
        self.secret = secret
        # Each Autotask tenant has a numbered zone URL (e.g.
        # https://webservices12.autotask.net/atservicesrest/v1.0/).
        # Fetched from /atservicesrest/v1.0/zoneInformation at setup.
        self.zone_url = zone_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.zone_url,
            headers={
                "ApiIntegrationCode": api_integration_code,
                "UserName": username,
                "Secret": secret,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def __aenter__(self) -> "AutotaskClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self._client.aclose()

    # ── READ ──────────────────────────────────────────────────────────────

    async def get_account(self, account_id: int) -> dict[str, Any]:
        """Fetch a single Account by id. Returns dict with at least
        ``id``, ``accountName``, ``classification``."""
        raise NotImplementedError(
            "AutotaskClient.get_account: implement in the read-side PR."
        )

    async def list_accounts(self, *, name_filter: str = "") -> list[dict[str, Any]]:
        """Search accounts by name. Used to bind a Sybr HUB customer to
        the corresponding Autotask Account record."""
        raise NotImplementedError(
            "AutotaskClient.list_accounts: implement in the read-side PR."
        )

    async def get_contract(self, contract_id: int) -> dict[str, Any]:
        """Fetch contract details for the per-customer view."""
        raise NotImplementedError(
            "AutotaskClient.get_contract: implement in the read-side PR."
        )

    async def list_contracts_for_account(self, account_id: int) -> list[dict[str, Any]]:
        """Active contracts attached to an account."""
        raise NotImplementedError(
            "AutotaskClient.list_contracts_for_account: implement in the read-side PR."
        )

    # ── WRITE (manual, operator-initiated) ────────────────────────────────

    async def create_ticket(
        self,
        account_id: int,
        title: str,
        description: str,
        *,
        priority: int = 2,
        queue_id: Optional[int] = None,
        contract_id: Optional[int] = None,
    ) -> int:
        """Create a ticket for an account.

        Returns the new ticket id. Caller is responsible for pre-filling
        title/description from the originating audit finding — this
        client doesn't infer them. Manual operator action only; never
        invoked from a scheduled audit run.

        priority: 1=Critical, 2=High, 3=Medium, 4=Low (Autotask
        defaults; adjust to your instance's picklist if customised).
        """
        raise NotImplementedError(
            "AutotaskClient.create_ticket: implement in the write-side PR."
        )
