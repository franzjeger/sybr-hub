"""The HTTP half of the Guacamole proxy serves static assets and nothing else.

``guac_proxy`` refused only paths that *started* with ``api/``. Starlette hands
the route a percent-decoded path, and httpx resolves dot segments when it
builds the backend URL, so ``/guacamole/x/%2e%2e/api/tokens`` arrived at
Guacamole as ``/guacamole/api/tokens``: any signed-in viewer could reach the
REST API, login included. Every client header was forwarded as well, so the
hub's own ``access_token`` / ``refresh_token`` cookies and ``Authorization``
went to the backend with each request.

These tests drive the route through TestClient with a mocked backend transport
and assert what the backend actually receives.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.middleware.auth import get_current_user
from app.web.routes import guacamole


@pytest.fixture
def backend(monkeypatch):
    """Record every request the proxy sends to Guacamole."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=b"console.log('guac');",
            headers={
                "content-type": "application/javascript",
                "set-cookie": "access_token=from-backend; Path=/",
            },
        )

    real_client = httpx.AsyncClient

    def client_with_mock_transport(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(guacamole.httpx, "AsyncClient", client_with_mock_transport)
    return seen


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(guacamole.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="viewer-1")
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "path",
    [
        "/guacamole/x/%2e%2e/api/tokens",
        "/guacamole/x/%2E%2E/api/tokens",
        "/guacamole/x/%252e%252e/api/tokens",
        "/guacamole/x/%2e%2e%2fapi/tokens",
        "/guacamole/x/..%5capi/tokens",
        "/guacamole/x/..;/api/tokens",
        "/guacamole/api;jsessionid=1/tokens",
        "/guacamole/%2e/api/session/data/mysql/connections.json",
        "/guacamole/API/tokens",
        "/guacamole/api/session/data/mysql/connections",
        "/guacamole/tunnel",
        "/guacamole/websocket-tunnel",
        "/guacamole/x//app.js",
        "/guacamole/.hidden.js",
        "/guacamole/",
        "/guacamole/index.html",
    ],
)
def test_paths_that_could_reach_the_rest_api_never_leave_the_hub(client, backend, path):
    response = client.get(path)

    assert response.status_code == 404
    assert backend == [], f"{path} reached the backend as {backend[0].url}"


def test_the_rest_api_login_cannot_be_posted(client, backend):
    response = client.post(
        "/guacamole/x/%2e%2e/api/tokens", data={"username": "guacadmin", "password": "x"}
    )

    assert response.status_code == 405
    assert backend == []


def test_a_static_asset_is_proxied_without_hub_credentials(client, backend):
    client.cookies.set("access_token", "hub-access-jwt")
    client.cookies.set("refresh_token", "hub-refresh-jwt")
    client.cookies.set("theme", "dark")

    response = client.get(
        "/guacamole/app/client/client.js?token=opaque&v=1",
        headers={"Authorization": "Bearer hub-access-jwt", "Accept": "application/javascript"},
    )

    assert response.status_code == 200
    assert response.content == b"console.log('guac');"
    assert len(backend) == 1
    sent = backend[0]
    assert str(sent.url) == f"{guacamole._BACKEND}/guacamole/app/client/client.js"
    assert sent.method == "GET"
    assert "authorization" not in sent.headers
    assert "cookie" not in sent.headers
    assert sent.headers["accept"] == "application/javascript"
    # Nor may the backend set cookies on the hub's origin.
    assert "set-cookie" not in response.headers
