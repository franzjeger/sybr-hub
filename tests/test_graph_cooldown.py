"""Parallel reads honor a tenant's cooldown without hiding incomplete data."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from app.modules.m365_audit.graph_client import GraphClient
from app.modules.m365_audit.throttling import GraphThrottledError, ReadCooldown, retry_delay


class Credential:
    async def get_token(self, *_args, **_kwargs):
        return SimpleNamespace(token="synthetic-token")


@pytest.mark.parametrize(
    "header,attempt,expected",
    [("0", 0, 0), ("12", 1, 12), (None, 2, 4), ("bad", 1, 2), ("-8", 0, 1)],
)
def test_retry_after_parsing(header, attempt, expected):
    assert retry_delay(header, attempt) == expected


def test_http_date_retry_after():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    date = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    assert 28 <= retry_delay(date, 0) <= 30
    assert retry_delay("Wed, 01 Jan 2020 00:00:00 GMT", 2) == 0


async def test_cooldown_shared_only_with_same_tenant_and_live_event_loop():
    one, two, other = (
        GraphClient(Credential(), tenant_id=x) for x in ("tenant-a", "TENANT-A", "tenant-b")
    )
    assert one._read_cooldown() is two._read_cooldown()
    assert other._read_cooldown() is not one._read_cooldown()
    assert GraphClient(Credential())._read_cooldown() is not one._read_cooldown()
    one._read_cooldown().defer(30)
    until = one._read_cooldown().until
    two._read_cooldown().defer(2)
    assert two._read_cooldown().until == until


@pytest.mark.parametrize("second_is_report", [False, True])
async def test_other_collector_does_not_send_during_cooldown(monkeypatch, second_is_report):
    first = GraphClient(Credential(), tenant_id="parallel-test")
    second = GraphClient(Credential(), tenant_id="parallel-test")
    calls = []
    throttle_seen = asyncio.Event()
    first_calls = 0
    cooldown = first._read_cooldown()

    # Short real delay keeps the event ordering observable and exercises actual
    # cancellation/scheduling, without a global fake sleep changing asyncio.
    def defer(_response, _attempt):
        cooldown.defer(0.05)
        throttle_seen.set()

    monkeypatch.setattr(first, "_defer_read", defer)

    def handler(request):
        nonlocal first_calls
        calls.append((request.url.path, time.monotonic()))
        if request.url.path.endswith("users"):
            first_calls += 1
            if first_calls == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "first"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
                },
            )
        if request.url.path.endswith("next"):
            return httpx.Response(200, json={"value": [{"id": "second"}]})
        if "/reports/" in request.url.path:
            return httpx.Response(200, text="User Principal Name\nexample@example.test\n")
        return httpx.Response(200, json={"value": [{"id": "device"}]})

    first._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    second._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    task = asyncio.create_task(first.get_all("users"))
    try:
        await throttle_seen.wait()
        deferred_until = cooldown.until
        result = await (
            second.get_report("getOffice365ActiveUserDetail")
            if second_is_report
            else second.get_all("devices")
        )
        assert result
        assert await task == [{"id": "first"}, {"id": "second"}]
        assert all(at >= deferred_until for _path, at in calls[1:])
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await first._http.aclose()
        await second._http.aclose()


@pytest.mark.parametrize("report", [False, True])
async def test_long_cooldown_fails_without_early_retry_or_false_empty(report):
    graph = GraphClient(Credential())
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "86400"})

    graph._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GraphThrottledError):
            await (graph.get_report("test") if report else graph.get_all("users"))
        assert len(calls) == 1
    finally:
        await graph._http.aclose()


async def test_cancellation_does_not_clear_another_collectors_cooldown():
    cooldown = ReadCooldown()
    cooldown.defer(0.05)
    task = asyncio.create_task(cooldown.wait(time.monotonic() + 1))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cooldown.until > time.monotonic()
    await cooldown.wait(time.monotonic() + 1)


async def test_new_cooldown_during_token_acquisition_is_honored(monkeypatch):
    graph = GraphClient(Credential(), tenant_id="token-wait-test")
    obtaining = asyncio.Event()
    release = asyncio.Event()

    async def headers():
        obtaining.set()
        await release.wait()
        return {}

    monkeypatch.setattr(graph, "_headers", headers)
    requests_at = []

    def handler(request):
        requests_at.append(time.monotonic())
        return httpx.Response(200, json={"value": [{"id": "measured"}]})

    graph._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    task = asyncio.create_task(graph.get_all("users"))
    try:
        await obtaining.wait()
        graph._read_cooldown().defer(0.03)
        until = graph._read_cooldown().until
        release.set()
        assert await task == [{"id": "measured"}]
        assert requests_at[0] >= until
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await graph._http.aclose()
