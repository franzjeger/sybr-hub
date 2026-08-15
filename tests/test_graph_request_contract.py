"""The Graph client's *request* side was never pinned.

Every other test in this repo stubs the response and asserts on it — what came
back. Nothing asserted what went out: the URL, the Authorization header, the
scope asked of the token, the Accept header, or that query params ride only the
first page. A client that silently asked for the wrong scope, dropped the
Accept header, or re-sent ``$top`` on every page of a 500-page walk would pass
the whole suite, because the fakes never looked at the request.

These tests pin the request. They use httpx.MockTransport — the same seam
test_graph_request_budget.py already uses — so no new dependency is added to
hold the wire contract they exist to hold.
"""

from __future__ import annotations

import httpx
import pytest

from app.modules.m365_audit.graph_client import GraphClient

_SCOPE = "https://graph.microsoft.com/.default"


class _Credential:
    """A token credential that records the scope it was asked for.

    The token is a distinct value so a test can tell the credential's token
    from any other string and prove it is the one that reached the wire."""

    def __init__(self) -> None:
        self.requested_scopes: list[str] = []

    async def get_token(self, scope: str):
        self.requested_scopes.append(scope)

        class _T:
            token = "the-token-the-credential-issued"

        return _T()


def _client(handler) -> tuple[GraphClient, _Credential, list[httpx.Request]]:
    """Wire a MockTransport in front of a real GraphClient and capture requests."""
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    cred = _Credential()
    graph = GraphClient(cred)
    graph._http = httpx.AsyncClient(transport=httpx.MockTransport(_record))
    return graph, cred, seen


async def _close(graph: GraphClient) -> None:
    await graph._http.aclose()


async def test_get_asks_for_the_default_scope_not_a_user_scope():
    """The client must ask the credential for the app's default scope.

    Asking for a user-delegated scope (``.default`` is the app's own) would
    make every call depend on a signed-in user and break the unattended audit
    path. The scope is the one thing a fake response cannot catch, because it
    is decided before any HTTP happens."""
    graph, cred, _ = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("users")
    finally:
        await _close(graph)

    assert cred.requested_scopes == [_SCOPE]


async def test_get_sends_the_issued_token_as_a_bearer_header():
    """The token the credential returned must be the one on the wire.

    A client that sent a stale or empty Authorization header would get a 401
    from every tenant and read it, through the refusal path, as "no data". The
    only way to know the right token went out is to look at the request."""
    graph, _, seen = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("users")
    finally:
        await _close(graph)

    assert seen[0].headers["Authorization"] == "Bearer the-token-the-credential-issued"


async def test_get_sends_json_accept_and_content_type():
    """Graph answers JSON only when asked for it.

    A missing Accept header is how a client ends up reading an HTML error page
    as a collection. These two headers are the difference between a parseable
    body and a silent misread, so they are part of the contract."""
    graph, _, seen = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("users")
    finally:
        await _close(graph)

    assert seen[0].headers["Accept"] == "application/json"
    assert seen[0].headers["Content-Type"] == "application/json"


async def test_get_targets_v1_by_default_and_beta_only_when_asked():
    """The base URL is a contract, not an implementation detail.

    beta and v1.0 answer the same path with different shapes; a client that
    always hit beta (or always v1.0) would read fields that are only in the
    other and report them as absent. Pin both the default and the opt-in."""
    graph, _, seen = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("users")
        await graph.get("users", beta=True)
    finally:
        await _close(graph)

    assert str(seen[0].url) == "https://graph.microsoft.com/v1.0/users"
    assert str(seen[1].url) == "https://graph.microsoft.com/beta/users"


async def test_get_normalises_a_leading_slash_in_the_path():
    """Callers pass both ``users`` and ``/users``.

    A client that did not strip the slash would request
    ``https://graph.microsoft.com/v1.0//users`` — a different resource that
    Graph answers with a 404, which reads as "no users"."""
    graph, _, seen = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("/users")
    finally:
        await _close(graph)

    assert str(seen[0].url) == "https://graph.microsoft.com/v1.0/users"


async def test_get_sends_query_params_on_the_wire():
    """$select and $top are how a caller narrows a collection.

    Dropping them silently widens the read — a caller asking for a bounded
    field set would get the full object and an unbounded page, and a caller
    relying on $top would walk the whole collection by hand."""
    graph, _, seen = _client(lambda r: httpx.Response(200, request=r, json={}))
    try:
        await graph.get("users", params={"$select": "id,displayName", "$top": "100"})
    finally:
        await _close(graph)

    assert seen[0].url.params["$select"] == "id,displayName"
    assert seen[0].url.params["$top"] == "100"


async def test_get_all_sends_params_on_the_first_page_only():
    """Query params ride the first request and are dropped after.

    Re-sending ``$top`` on every page of a long walk is wasted budget and, on
    the endpoints that reject it, a 400 on the second page that reads as a
    failed section. The first page carries the query; the follow-ups follow
    the server's nextLink verbatim."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, request=request, json={"value": [{"id": "b"}]})
        return httpx.Response(
            200,
            request=request,
            json={"value": [{"id": "a"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/sites?page=2"},
        )

    graph, _, seen = _client(handler)
    try:
        items = await graph.get_all("sites", params={"$top": "100"})
    finally:
        await _close(graph)

    assert items == [{"id": "a"}, {"id": "b"}]
    assert seen[0].url.params["$top"] == "100", "first page must carry the query"
    assert "$top" not in seen[1].url.params, "follow-up page must not re-send it"


async def test_get_all_follows_the_servers_next_link_verbatim():
    """Pagination is driven by @odata.nextLink, not by a guessed page number.

    A client that built page 2 itself would break the moment Graph changed the
    link shape. Following the link is the only contract that survives Graph
    changing its mind about how it paginates."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "token=opaque" in str(request.url):
            return httpx.Response(200, request=request, json={"value": [{"id": "b"}]})
        return httpx.Response(
            200,
            request=request,
            json={"value": [{"id": "a"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/sites?token=opaque"},
        )

    graph, _, seen = _client(handler)
    try:
        items = await graph.get_all("sites")
    finally:
        await _close(graph)

    assert items == [{"id": "a"}, {"id": "b"}]
    assert str(seen[1].url) == "https://graph.microsoft.com/v1.0/sites?token=opaque"


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_read_is_not_a_measured_zero(status):
    """A 401/403 must raise, not come back as an empty collection.

    This is the refusal-is-not-a-reading guarantee at the request layer: the
    client sends the request, Graph refuses it, and the client must surface
    the refusal rather than hand back {} that a caller reads as "the tenant
    has none of these". (test_data_quality pins _get; this pins get_all, the
    path the audit actually walks.)"""
    from app.modules.m365_audit.graph_client import GraphPermissionError

    graph, _, _ = _client(
        lambda r: httpx.Response(status, request=r, json={"error": {"code": "AccessDenied"}})
    )
    try:
        with pytest.raises(GraphPermissionError):
            await graph.get_all("users")
    finally:
        await _close(graph)
