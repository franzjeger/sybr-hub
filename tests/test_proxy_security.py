"""Regression tests for the web proxy and remote-session boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.models.user import Role, User
from app.web.routes import proxy


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        username=user_id,
        display_name=user_id,
        role=Role.technician,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "http://user:pass@example.com/",
    ],
)
def test_proxy_rejects_non_public_targets(url):
    assert proxy._validate_url(url) is not None


def test_dns_failure_is_blocked(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("no resolver")

    monkeypatch.setattr(proxy.socket, "getaddrinfo", fail)
    assert proxy._is_private_host("unresolvable.invalid") is True


@pytest.mark.asyncio
async def test_redirect_to_loopback_is_never_requested(monkeypatch):
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(proxy, "_http_client", client)
    monkeypatch.setattr(
        proxy,
        "_is_private_host",
        lambda hostname: hostname in {"127.0.0.1", "::1"},
    )
    monkeypatch.setattr(proxy, "_resolve_public_address", lambda _hostname: "203.0.113.10")
    try:
        with pytest.raises(ValidationError):
            await proxy._safe_fetch("https://public.example/start")
    finally:
        await client.aclose()

    assert requested == ["https://203.0.113.10/start"]


@pytest.mark.asyncio
async def test_proxy_stops_reading_at_body_limit(monkeypatch):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"12345")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(proxy, "_http_client", client)
    monkeypatch.setattr(proxy, "_MAX_BODY", 4)
    monkeypatch.setattr(proxy, "_is_private_host", lambda _hostname: False)
    monkeypatch.setattr(proxy, "_resolve_public_address", lambda _hostname: "203.0.113.10")
    try:
        with pytest.raises(proxy._ResponseTooLarge):
            await proxy._safe_fetch("https://public.example/file")
    finally:
        await client.aclose()


def test_remote_browser_session_is_private_to_owner(monkeypatch):
    monkeypatch.setattr(proxy, "_browser_session", {"owner_user_id": "alice"})
    proxy._require_browser_owner(_user("alice"))
    with pytest.raises(ForbiddenError):
        proxy._require_browser_owner(_user("bob"))


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "data:text/html,boom", "chrome://settings"],
)
def test_remote_browser_rejects_active_non_web_schemes(url):
    with pytest.raises(ValidationError):
        proxy._validate_browser_target(url)


def test_third_party_html_is_sanitized_before_rewrite():
    dirty = '<script>alert(1)</script><img src="/a.png" onerror="steal()">'
    cleaned = proxy.nh3.clean(dirty, link_rel=None)
    rewritten = proxy._rewrite_html(cleaned, "https://example.com/page")
    assert "alert(1)" not in rewritten
    assert "onerror" not in rewritten
    assert "/api/proxy/raw" in rewritten


@pytest.mark.asyncio
async def test_rdp_requires_an_inventory_host():
    with pytest.raises(ValidationError):
        await proxy._get_authorized_rdp_host(_user("alice"), "")


@pytest.mark.asyncio
async def test_rdp_enforces_the_hosts_customer_scope(monkeypatch):
    import app.core.rbac as rbac
    import app.services.ssh_manager as ssh_manager

    host = SimpleNamespace(id="host-1", hostname="10.0.0.8", customer_id="customer-b")

    async def get_host(_host_id):
        return host

    async def deny(_user, _customer_id):
        return False

    monkeypatch.setattr(ssh_manager, "get_host", get_host)
    monkeypatch.setattr(rbac, "check_customer_access", deny)

    with pytest.raises(ForbiddenError):
        await proxy._get_authorized_rdp_host(_user("alice"), "host-1")
