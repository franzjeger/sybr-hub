"""Outbound Graph budgets count HTTP attempts, not high-level method calls."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.modules.m365_audit.graph_client import (
    GraphClient,
    GraphRequestBudgetExceeded,
)


class _Credential:
    async def get_token(self, *_args, **_kwargs):
        return SimpleNamespace(token="test-token")


async def test_pagination_cannot_escape_the_callers_request_budget():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            request=request,
            json={
                "value": [{"id": "first"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/sites?page=2",
            },
        )

    graph = GraphClient(_Credential())
    graph._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    remaining = 1

    def claim() -> bool:
        nonlocal remaining
        if remaining == 0:
            return False
        remaining -= 1
        return True

    try:
        with pytest.raises(GraphRequestBudgetExceeded):
            await graph.get_all("sites", before_request=claim)
    finally:
        await graph._http.aclose()

    assert attempts == 1


async def test_throttle_retries_each_consume_request_budget():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, request=request, headers={"Retry-After": "0"})

    graph = GraphClient(_Credential())
    graph._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    claims = 0

    def claim() -> bool:
        nonlocal claims
        if claims == 2:
            return False
        claims += 1
        return True

    try:
        with pytest.raises(GraphRequestBudgetExceeded):
            await graph.get_all("sites", before_request=claim)
    finally:
        await graph._http.aclose()

    assert attempts == claims == 2
