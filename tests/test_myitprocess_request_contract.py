"""The myITprocess client's *request* side was never pinned.

The write-side tests pin the POST **body** (accountId, title, description,
externalReferenceId) and the id-extraction shapes — what the client sends as
the payload and what it reads back. But their fake handler answers the same
thing to *any* GET and records only the POST body: it never looked at the URL,
the Authorization header, the ``limit`` param, or the base URL. A client that
hit the wrong path, dropped the API key, ignored ``limit`` on the connectivity
check, or kept a trailing slash in a custom base URL would pass the whole suite.

This matters more here than for any other integration in the repo: the
ROADMAP records that nothing in this client has ever spoken to a real server,
so the request shape is the one thing that must be locked down by the tests
rather than by a document somebody read.

Same seam as the Graph contract tests — httpx.MockTransport, no new dependency.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.myitprocess import MyITProcessClient

_API_KEY = "the-api-key-from-settings"


def _client(base_url: str | None = None, *, seen: list[httpx.Request] | None = None):
    """A real client (so it builds its real headers + base URL) with a
    MockTransport swapped in to capture the requests it sends."""
    client = MyITProcessClient(_API_KEY, base_url=base_url) if base_url else MyITProcessClient(_API_KEY)
    captured = seen if seen is not None else []

    def _record(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "GET":
            return httpx.Response(200, request=request, json=[{"id": "1", "name": "Acme"}])
        return httpx.Response(200, request=request, json={"recommendationId": "1"})

    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_record),
        headers=client._client.headers,
        base_url=client.base_url,
    )
    return client, captured


async def _close(client: MyITProcessClient) -> None:
    await client.close()


async def test_accounts_read_targets_the_default_host_and_path():
    """The default base URL and the /v1/accounts path are a contract.

    A client that hit the wrong host or path would talk to the wrong API and
    read the answer as its own. The default is a setting, but the default is
    also the thing a fresh install ships with — so it is pinned, not assumed."""
    client, seen = _client()
    try:
        await client.list_accounts()
    finally:
        await _close(client)

    assert seen[0].method == "GET"
    assert seen[0].url.host == "api.myitprocess.com"
    assert seen[0].url.path == "/v1/accounts"


async def test_accounts_read_sends_the_limit_on_the_wire():
    """The limit is how the connectivity check stays bounded.

    test_connection asks for one account to confirm the key works. A client
    that dropped the param would pull the whole account list for a handshake,
    and a client that hardcoded it would ignore the caller's choice."""
    client, seen = _client()
    try:
        await client.list_accounts(limit=1)
    finally:
        await _close(client)

    assert seen[0].url.params["limit"] == "1"


async def test_the_api_key_travels_as_a_bearer_header():
    """The key from settings must be the one on the wire.

    A missing or wrong Authorization header is a 401 on every call, which the
    client reports as "check the key" — a technician then chases a key that
    was never actually sent. The only way to know it went out is to look at
    the request."""
    client, seen = _client()
    try:
        await client.list_accounts()
    finally:
        await _close(client)

    assert seen[0].headers["Authorization"] == f"Bearer {_API_KEY}"


async def test_json_accept_and_content_type_are_sent():
    """myITprocess answers JSON only when asked for it.

    A missing Accept header is how a client ends up reading an HTML error page
    as a collection — and this client's _check raises on a non-JSON body, so
    the symptom is a spurious "returned a non-JSON body" on a call that was
    fine. Both headers are part of the contract."""
    client, seen = _client()
    try:
        await client.list_accounts()
    finally:
        await _close(client)

    assert seen[0].headers["Accept"] == "application/json"
    assert seen[0].headers["Content-Type"] == "application/json"


async def test_create_posts_to_the_recommendations_path():
    """The write must hit the recommendations resource, not a guess.

    A wrong path is a 404 (read as a failed push) or, worse, a different
    object created. The body is already pinned by the write-side tests; this
    pins where it goes."""
    client, seen = _client()
    try:
        await client.create_recommendation("1", "title", "detail")
    finally:
        await _close(client)

    assert seen[0].method == "POST"
    assert str(seen[0].url) == "https://api.myitprocess.com/v1/recommendations"
    body = json.loads(seen[0].content)
    assert body["accountId"] == "1"


async def test_a_custom_base_url_is_honored_and_trimmed():
    """The base URL is a setting precisely so a wrong host is a settings change.

    A client that ignored it would talk to the public API when the operator
    pointed it at an internal one; a client that kept the trailing slash would
    build a double-slash URL. Both are pinned: the host is honored and the
    slash is stripped."""
    client, seen = _client(base_url="https://mip.internal/")
    try:
        await client.list_accounts()
    finally:
        await _close(client)

    # The host is honored (not the default) and the trailing slash is trimmed,
    # so the path is a single /v1/accounts rather than //v1/accounts.
    assert seen[0].url.host == "mip.internal"
    assert seen[0].url.path == "/v1/accounts"


@pytest.mark.parametrize("status,expected", [
    (401, "refused the API key"),
    (403, "refused this call"),
])
async def test_a_refused_read_is_named_not_swallowed(status, expected):
    """A 401 and a 403 need opposite responses, so they are named differently.

    401 is a key problem; 403 is a grant problem (write access to
    Recommendations is separate from read). Collapsing them into one
    "it failed" sends a technician looking for the wrong cause."""
    from app.integrations.myitprocess import MyITProcessError

    client = MyITProcessClient(_API_KEY)
    captured: list[httpx.Request] = []

    def _refuse(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, request=request, text="no")

    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_refuse),
        headers=client._client.headers,
        base_url=client.base_url,
    )
    try:
        with pytest.raises(MyITProcessError) as exc:
            await client.list_accounts()
    finally:
        await client.close()

    assert expected in str(exc.value)
