"""The write-side clients had no retry at all.

GraphClient has waited on Retry-After since it was written and earns it on
every audit. IT Glue, ALSO and Partner Center had nothing, so a throttled
upload returned an empty result and the run carried on — which reads exactly
like "there was nothing to upload".

The distinction that matters is between what is safe to repeat and what is
not. 429 means the request was refused before it was processed. A 5xx may
mean the server applied a write and failed on the way out, and an IT Glue
upload repeated that way leaves two documents behind.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

_real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    """Skip the backoff. Patching asyncio.sleep with something that calls
    asyncio.sleep recurses into the patch — hold the original."""
    async def _instant(_seconds):
        await _real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _instant)

from app.integrations.http_retry import RetryExhausted, send_with_retry


def _resp(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status, headers=headers or {},
        request=httpx.Request("GET", "https://example.test/x"),
    )


def _sender(statuses):
    """A send() that walks the given statuses, counting its calls."""
    calls = {"n": 0}

    async def send():
        i = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        item = statuses[i]
        if isinstance(item, Exception):
            raise item
        return _resp(*item) if isinstance(item, tuple) else _resp(item)

    return send, calls


def test_a_throttled_write_is_retried():
    """429 was refused, not processed — safe to repeat whatever the method."""
    send, calls = _sender([429, 429, 200])
    resp = asyncio.run(send_with_retry(send, method="POST", target="t"))
    assert resp.status_code == 200
    assert calls["n"] == 3


def test_a_failed_write_is_not_retried():
    """The server may have applied it. Repeating creates a second document."""
    send, calls = _sender([500, 200])
    resp = asyncio.run(send_with_retry(send, method="POST", target="t"))
    assert resp.status_code == 500, "a 5xx write must be handed back, not repeated"
    assert calls["n"] == 1


def test_a_failed_read_is_retried():
    send, calls = _sender([500, 200])
    resp = asyncio.run(send_with_retry(send, method="GET", target="t"))
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_running_out_of_attempts_raises_rather_than_returning():
    """The whole point. An exhausted call must not look like an empty one."""
    send, calls = _sender([429])
    with pytest.raises(RetryExhausted) as excinfo:
        asyncio.run(send_with_retry(send, method="POST", target="IT Glue upload"))
    assert excinfo.value.last_status == 429
    assert "IT Glue upload" in str(excinfo.value)
    assert calls["n"] == 3


def test_the_servers_own_retry_after_is_used(monkeypatch):
    """Guessing while being told the number gets you throttled twice."""
    waits: list[float] = []

    async def _record(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _record)
    send, _ = _sender([(429, {"Retry-After": "7"}), (200, {})])
    asyncio.run(send_with_retry(send, method="GET", target="t"))
    assert waits == [7.0]


def test_a_connection_that_never_opened_is_retried_for_any_method():
    """No request reached the server, so there is no half-applied write."""
    send, calls = _sender([httpx.ConnectError("refused"), 200])
    resp = asyncio.run(send_with_retry(send, method="POST", target="t"))
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_a_4xx_is_handed_straight_back():
    """Not retryable and not this layer's business — the caller checks it."""
    send, calls = _sender([404])
    resp = asyncio.run(send_with_retry(send, method="GET", target="t"))
    assert resp.status_code == 404
    assert calls["n"] == 1


@pytest.mark.parametrize("module,name", [
    ("app.integrations.itglue", "IT Glue"),
    ("app.integrations.also_cloud", "ALSO"),
    ("app.integrations.partner_center", "Partner Center"),
])
def test_every_write_side_client_goes_through_the_layer(module, name):
    """A client added later must not quietly reintroduce the bare call."""
    import importlib
    import pathlib

    mod = importlib.import_module(module)
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "send_with_retry" in src, f"{name} does not retry anything"
    bare = [
        line.strip() for line in src.splitlines()
        if "await self._client." in line
        and not any(k in line for k in ("aclose", "send_with_retry"))
    ]
    assert not bare, f"{name} still calls the transport directly: {bare}"
