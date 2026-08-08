"""Guacamole connections must be unique, attributable and retry-cleanable."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.core.exceptions import IntegrationError
from app.web.routes import guacamole, proxy


class _Response:
    def __init__(self, status_code, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class _Client:
    response = _Response(500)
    posts: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response

    async def get(self, url, **kwargs):
        return self.response


def test_managed_connection_names_are_unique_and_contain_no_target():
    first = proxy._guac_connection_name("RDP")
    second = proxy._guac_connection_name("RDP")
    assert first.startswith(proxy._GUAC_BOOT_PREFIX)
    assert first != second
    assert "password" not in first.lower()


def test_opaque_client_token_is_bound_to_user_and_connection():
    user = SimpleNamespace(id="user-1")
    proxy._guac_sessions[str(user.id)] = {
        "token": "backend-admin-token",
        "client_token": "opaque-browser-token",
        "connection_id": "42",
    }
    try:
        assert proxy.resolve_guacamole_tunnel(user, "opaque-browser-token", "42") == (
            "backend-admin-token"
        )
        assert proxy.resolve_guacamole_tunnel(user, "backend-admin-token", "42") is None
        assert proxy.resolve_guacamole_tunnel(user, "opaque-browser-token", "99") is None
        assert proxy.resolve_guacamole_tunnel(
            SimpleNamespace(id="other"), "opaque-browser-token", "42",
        ) is None
    finally:
        proxy._guac_sessions.pop(str(user.id), None)


async def test_authenticated_users_cannot_reach_guacamole_admin_api():
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/guacamole/api/session/data/mysql/connections",
        "headers": [],
        "query_string": b"",
    })
    response = await guacamole.guac_proxy(
        request,
        "api/session/data/mysql/connections",
        SimpleNamespace(id="user-1"),
    )
    assert response.status_code == 404


async def test_create_never_reuses_or_overwrites_an_existing_connection(monkeypatch):
    _Client.posts = []
    _Client.response = _Response(409, text="duplicate")
    monkeypatch.setattr(proxy.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(proxy, "_guac_base", lambda: "http://guac/guacamole")

    result = await proxy._guac_create_connection(
        "token", "10.0.0.8", 3389, "alice", "secret",
    )

    assert result is None
    assert len(_Client.posts) == 1
    payload = _Client.posts[0][1]["json"]
    assert payload["name"].startswith(proxy._GUAC_BOOT_PREFIX)
    assert "10.0.0.8" not in payload["name"]


async def test_startup_sweep_deletes_only_previous_boot_connections(monkeypatch):
    previous = proxy._GUAC_MANAGED_PREFIX + "oldboot-RDP-a"
    current = proxy._GUAC_BOOT_PREFIX + "RDP-b"
    unrelated = "Administrator connection"
    _Client.response = _Response(200, {
        "1": {"name": previous},
        "2": {"name": current},
        "3": {"name": unrelated},
    })
    monkeypatch.setattr(proxy.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(proxy, "_guac_base", lambda: "http://guac/guacamole")

    async def login():
        return "token"

    deleted = []

    async def delete(token, connection_id):
        deleted.append((token, connection_id))
        return True

    monkeypatch.setattr(proxy, "_guac_login", login)
    monkeypatch.setattr(proxy, "_guac_delete_with_fresh_token", delete)

    assert await proxy.cleanup_stale_guacamole_connections() == 1
    assert deleted == [("token", "1")]


async def test_failed_rdp_delete_keeps_the_identifier_for_retry(monkeypatch):
    user = SimpleNamespace(id="user-1")
    session = {"token": "expired", "connection_id": "42"}
    proxy._guac_sessions[str(user.id)] = session

    async def refuse_delete(token, connection_id):
        return False

    monkeypatch.setattr(proxy, "_guac_delete_with_fresh_token", refuse_delete)
    try:
        with pytest.raises(IntegrationError):
            await proxy.rdp_stop(None, user)
        assert proxy._guac_sessions[str(user.id)] == session
    finally:
        proxy._guac_sessions.pop(str(user.id), None)


async def test_login_never_sends_admin_credentials_to_a_rejected_host(monkeypatch):
    monkeypatch.setattr(proxy, "_get_guac_config", lambda: {
        "url": "https://attacker.example/guacamole",
        "user": "admin",
        "pass": "secret",
    })

    class _MustNotConnect:
        def __init__(self, *args, **kwargs):
            raise AssertionError("unsafe Guacamole host was contacted")

    monkeypatch.setattr(proxy.httpx, "AsyncClient", _MustNotConnect)
    assert await proxy._guac_login() is None
