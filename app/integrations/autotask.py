"""Autotask PSA REST API client — read side.

Workshop intent (do not deviate):
    READ : Account, Classification, Contract
    WRITE: CreateTicket — always manual, never automatic.

Automatic ticket creation was explicitly rejected in the workshop; operator
discretion is part of the workflow. The write side is still unimplemented and
raises, deliberately.

**Naming.** Autotask's UI and its old SOAP API say "Account". The REST API
calls the same record a **Company**, and every URL here uses that. The methods
keep the account_* names the rest of this codebase already uses, so a reader
following `hub.autotask.account_id` lands somewhere recognisable.

**Verification status.** This was written against Autotask's published REST
reference, not against a live instance — there were no Autotask credentials on
any customer when it was written, so nothing here has answered a real request.
The request shapes are pinned by tests, which proves this client sends what it
means to send and nothing about what Autotask replies. Run
``test_connection()`` once credentials exist: it performs zone discovery and a
single bounded query, and reports the field names that came back. Treat the
first real run as the verification, and expect to adjust field names.

API reference: https://ww1.autotask.net/help/Content/AdminSetup/2ExtensionsIntegrations/APIs/REST/REST_API_Home.htm
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry

logger = logging.getLogger(__name__)

# Zone discovery is unauthenticated and tells you which numbered zone the
# tenant lives in. Every other call goes to the URL it returns; sending them
# to this host answers 404 with no hint as to why.
_ZONE_URL = "https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation"

# Autotask caps a query page at 500 and rejects more with a 400.
_MAX_PAGE = 500


class AutotaskError(Exception):
    """Autotask API call failed."""


class AutotaskClient:
    """Async client for the Autotask PSA REST API.

    Auth is three headers: ApiIntegrationCode, UserName, Secret. Provision
    them under Admin → Resources (Users) → API user, and give that user a
    security level with read access to Companies and Contracts.
    """

    def __init__(
        self,
        api_integration_code: str,
        username: str,
        secret: str,
        zone_url: str = "",
    ):
        self.api_integration_code = api_integration_code
        self.username = username
        self.secret = secret
        self.zone_url = zone_url.rstrip("/")
        self._client = httpx.AsyncClient(
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
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Plumbing ──────────────────────────────────────────────────────────

    async def discover_zone(self) -> str:
        """Resolve and remember this tenant's zone URL.

        Unauthenticated by design — the username alone identifies the zone.
        """
        resp = await send_with_retry(
            lambda: self._client.get(_ZONE_URL, params={"user": self.username}),
            method="GET", target="Autotask zoneInformation",
        )
        if resp.status_code != 200:
            raise AutotaskError(
                f"Zone lookup failed with {resp.status_code}. The username must "
                f"be the API user's, not a person's login."
            )
        url = (resp.json() or {}).get("url", "")
        if not url:
            raise AutotaskError("Zone lookup returned no url — cannot reach the API.")
        self.zone_url = url.rstrip("/")
        return self.zone_url

    async def _query(
        self, entity: str, filters: list[dict], *, page_size: int = 50
    ) -> list[dict]:
        """POST an Autotask query filter and return the records.

        Autotask answers with {"items": [...], "pageDetails": {...}}. An empty
        `items` is a real answer — no records matched. A response without the
        key at all is not, and raises rather than becoming an empty list:
        "we could not ask" and "there are none" must not read alike.
        """
        if not self.zone_url:
            await self.discover_zone()

        url = f"{self.zone_url}/V1.0/{entity}/query"
        body = {"MaxRecords": min(page_size, _MAX_PAGE), "Filter": filters}
        try:
            resp = await send_with_retry(
                lambda: self._client.post(url, content=json.dumps(body)),
                method="POST", target=f"Autotask {entity} query",
            )
        except RetryExhausted as exc:
            raise AutotaskError(str(exc)) from exc

        if resp.status_code == 401:
            raise AutotaskError(
                "Autotask refused the credentials (401). Check the integration "
                "code, the API username and the secret."
            )
        if resp.status_code >= 400:
            raise AutotaskError(
                f"Autotask {entity} query failed with {resp.status_code}: "
                f"{resp.text[:300]}"
            )

        data = resp.json()
        if not isinstance(data, dict) or "items" not in data:
            raise AutotaskError(
                f"Autotask {entity} query returned an unexpected shape: "
                f"{str(data)[:200]}"
            )
        return data["items"] or []

    # ── READ ──────────────────────────────────────────────────────────────

    async def get_account(self, account_id: int) -> Optional[dict[str, Any]]:
        """One Company by id, or None when nothing matched.

        None means the query ran and found nothing. Anything that stopped the
        query from running raises.
        """
        items = await self._query(
            "Companies",
            [{"op": "eq", "field": "id", "value": account_id}],
            page_size=1,
        )
        return items[0] if items else None

    async def list_accounts(
        self, *, name_filter: str = "", limit: int = 50
    ) -> list[dict[str, Any]]:
        """Companies, optionally narrowed by name.

        Used to bind a Sybr HUB customer to its Autotask record. Active
        companies only: Autotask keeps archived ones forever and a technician
        binding a customer does not want to pick one of those by accident.
        """
        filters: list[dict] = [{"op": "eq", "field": "isActive", "value": True}]
        if name_filter:
            filters.append(
                {"op": "contains", "field": "companyName", "value": name_filter}
            )
        return await self._query("Companies", filters, page_size=limit)

    async def get_contract(self, contract_id: int) -> Optional[dict[str, Any]]:
        """One Contract by id, or None when nothing matched."""
        items = await self._query(
            "Contracts",
            [{"op": "eq", "field": "id", "value": contract_id}],
            page_size=1,
        )
        return items[0] if items else None

    async def list_contracts_for_account(
        self, account_id: int, *, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """Contracts attached to a company, active ones by default."""
        filters: list[dict] = [
            {"op": "eq", "field": "companyID", "value": account_id}
        ]
        if active_only:
            filters.append({"op": "eq", "field": "status", "value": 1})
        return await self._query("Contracts", filters)

    async def test_connection(self) -> dict[str, Any]:
        """Prove the credentials work, and report what came back.

        This is the verification this client has not had: it was written
        against the published reference, not a live instance. Run it once
        credentials exist and read `sample_fields` — if the names differ from
        what the read methods filter on, that is the thing to fix, and better
        found here than inside an audit.
        """
        result: dict[str, Any] = {"ok": False, "zone_url": "", "sample_fields": []}
        try:
            result["zone_url"] = await self.discover_zone()
            items = await self._query(
                "Companies",
                [{"op": "eq", "field": "isActive", "value": True}],
                page_size=1,
            )
            result["ok"] = True
            result["returned"] = len(items)
            if items:
                result["sample_fields"] = sorted(items[0].keys())
            else:
                result["note"] = "Connected, but no active companies came back."
        except (AutotaskError, RetryExhausted) as exc:
            result["error"] = str(exc)
        except httpx.HTTPError as exc:
            result["error"] = f"Could not reach Autotask: {exc}"
        return result

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
        """Create a ticket for a company. Not implemented.

        Left raising on purpose. The workshop put operator discretion in the
        loop, and the read side has not been confirmed against a live instance
        — writing into a customer's PSA on the strength of field names nobody
        has checked is not a thing to do quietly.
        """
        raise NotImplementedError(
            "AutotaskClient.create_ticket: implement in the write-side PR, "
            "after the read side has been confirmed against a live instance."
        )
