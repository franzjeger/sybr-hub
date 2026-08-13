"""myITprocess client — Recommendations.

Workshop intent: audit findings that need planning (e.g. "DKIM missing on 4
domains" — solvable but needs scheduling, not a 5-minute ticket) get pushed to
myITprocess as **Recommendations**, where they flow through the customer's
quarterly business review.

Separation from Autotask:
    Autotask ticket            = something to fix this week
    myITprocess recommendation = something to plan next quarter

The operator chooses which bucket each finding belongs in. Nothing here decides
it, and nothing scheduled calls this — see the endpoint in ``web/routes/hub.py``
and ``tests/test_myitprocess_write_side.py``.

**Verification status — read this before trusting a field name.**

Weaker than Autotask's, and the difference matters. The Autotask client was
written against a published REST reference somebody had read. This one was not:
``app.myitprocess.com`` is unreachable from the environment this was built in,
so the request shapes below come from the contract the previous stub declared
and from how the rest of this file's peers behave. No call here has met a real
server.

So the code is written to be *diagnosable* rather than confident:

* the base URL is a setting, so a wrong host is a settings change;
* the id is pulled from a small list of candidate keys rather than one
  hard-coded guess, and an unrecognised response says what it actually got;
* a list response is accepted as a bare array or wrapped, because both are
  common and neither is worth being wrong about;
* ``test_connection()`` reports the keys that came back, which is how the
  field names get confirmed.

Treat the first real run as the verification. Expect to change something, and
expect this docstring to be wrong somewhere.

API reference: https://app.myitprocess.com/developer/api
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.integrations.http_retry import RetryExhausted, send_with_retry

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.myitprocess.com"

# myITprocess recommendation text limits are not documented anywhere reachable
# from here. These are conservative: a report paragraph runs long, and losing
# the tail beats losing the push to a 400 nobody can read.
_MAX_TITLE = 200
_MAX_DETAIL = 8000

# Candidate keys for the id of a newly created recommendation. Ordered by how
# specific they are, so a response carrying both `id` and `recommendationId`
# yields the one that unambiguously names this object.
_ID_KEYS = ("recommendationId", "recommendation_id", "itemId", "id")

# Candidate keys for a wrapped collection.
_LIST_KEYS = ("data", "items", "results", "value")


class MyITProcessError(Exception):
    """myITprocess API call failed."""


def _extract_id(payload: Any) -> str | None:
    """The id of the thing just created, or None if the shape is unfamiliar.

    None rather than a guess: the caller records this against a finding, and a
    plausible-looking wrong value means a recommendation nobody can open and a
    second push that never happens.
    """
    if isinstance(payload, int):
        return str(payload)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if not isinstance(payload, dict):
        return None
    for wrapper in _LIST_KEYS:
        inner = payload.get(wrapper)
        if isinstance(inner, dict):
            found = _extract_id(inner)
            if found:
                return found
    for key in _ID_KEYS:
        value = payload.get(key)
        if isinstance(value, (int, str)) and str(value).strip():
            return str(value).strip()
    return None


def _extract_list(payload: Any) -> list[dict] | None:
    """Records from a bare array or a wrapped one. None if neither."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in _LIST_KEYS:
            inner = payload.get(key)
            if isinstance(inner, list):
                return [r for r in inner if isinstance(r, dict)]
    return None


class MyITProcessClient:
    """Async client for the myITprocess Recommendations API."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL):
        self.api_key = api_key
        self.base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def __aenter__(self) -> MyITProcessClient:
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Plumbing ──────────────────────────────────────────────────────────

    def _check(self, resp: httpx.Response, what: str) -> Any:
        """Raise on anything that is not a usable answer, then decode."""
        if resp.status_code == 401:
            raise MyITProcessError(
                "myITprocess refused the API key (401). Check the key and that "
                "it has access to Recommendations."
            )
        if resp.status_code == 403:
            raise MyITProcessError(
                "myITprocess accepted the key but refused this call (403). The "
                "key needs write access to Recommendations, which is a separate "
                "grant from read."
            )
        if resp.status_code >= 400:
            raise MyITProcessError(
                f"myITprocess {what} failed with {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise MyITProcessError(
                f"myITprocess {what} returned a non-JSON body: {resp.text[:200]}"
            ) from exc

    # ── READ ──────────────────────────────────────────────────────────────

    async def list_accounts(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Accounts, for binding a Sybr HUB customer to its counterpart.

        An empty list is a real answer — the key is valid and there are none.
        A shape this cannot read raises, because "we could not ask" and "there
        are none" must not look alike to the caller.
        """
        try:
            resp = await send_with_retry(
                lambda: self._client.get("/v1/accounts", params={"limit": limit}),
                method="GET", target="myITprocess accounts",
            )
        except RetryExhausted as exc:
            raise MyITProcessError(str(exc)) from exc

        data = self._check(resp, "accounts")
        records = _extract_list(data)
        if records is None:
            raise MyITProcessError(
                f"myITprocess accounts returned an unexpected shape: "
                f"{str(data)[:200]}"
            )
        return records

    async def test_connection(self) -> dict[str, Any]:
        """One bounded call, reporting what came back.

        This matters more here than for any other integration in this repo:
        nothing in this client has spoken to a real server, so the field names
        it filters on are unconfirmed. The point of this method is to print
        the keys myITprocess actually sends so they can be compared.
        """
        try:
            accounts = await self.list_accounts(limit=1)
        except MyITProcessError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "account_count": len(accounts),
            # The thing to compare against what the code above reads.
            "sample_fields": sorted(accounts[0].keys()) if accounts else [],
        }

    # ── WRITE ─────────────────────────────────────────────────────────────

    async def create_recommendation(
        self,
        account_id: str,
        title: str,
        detail: str,
        *,
        category: str | None = None,
        priority: str | None = None,
        source_finding_id: str | None = None,
    ) -> str:
        """Push a Recommendation. Returns its id.

        ``source_finding_id`` is the originating ``rec_id``, sent so the record
        carries its own provenance on the myITprocess side too. The duplicate
        check does not depend on it — that is a uniqueness constraint in this
        install's database, not a query against someone else's API.

        **Never retried on a 5xx**, for the same reason as the Autotask ticket
        create: a POST that applied the write and failed on the way out would,
        on retry, become a second recommendation in the customer's quarterly
        review. 429 is still retried; it was refused before it was processed.
        """
        body: dict[str, Any] = {
            "accountId": account_id,
            "title": title[:_MAX_TITLE],
            "description": detail[:_MAX_DETAIL],
        }
        if category:
            body["category"] = category
        if priority:
            body["priority"] = priority
        if source_finding_id:
            body["externalReferenceId"] = source_finding_id

        try:
            resp = await send_with_retry(
                lambda: self._client.post(
                    "/v1/recommendations", content=json.dumps(body)
                ),
                method="POST", target="myITprocess recommendation create",
            )
        except RetryExhausted as exc:
            raise MyITProcessError(str(exc)) from exc

        data = self._check(resp, "recommendation create")
        rec_id = _extract_id(data)
        if rec_id is None:
            # Accepting a made-up id would record a recommendation that may not
            # exist and block every later push for this finding.
            raise MyITProcessError(
                "myITprocess accepted the recommendation but returned no id "
                f"this client recognises (looked for {', '.join(_ID_KEYS)}); "
                f"got: {str(data)[:200]}"
            )
        return rec_id

    def recommendation_url(self, recommendation_id: str) -> str:
        """Best-effort deep link. Empty when the host is not the known one.

        Guessing a path against a host somebody configured themselves would
        produce a link that goes somewhere wrong, which is worse than no link.
        """
        if _DEFAULT_BASE_URL not in self.base_url:
            return ""
        return f"https://app.myitprocess.com/recommendations/{recommendation_id}"
