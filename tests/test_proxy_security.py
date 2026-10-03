"""Regression tests for the remote-session boundaries.

The server-side web proxy these tests also covered is gone — see the module
docstring in ``app.web.routes.proxy``. ``test_the_web_proxy_stays_removed``
below is what stops it coming back by accident: the endpoints had no caller,
and the SSRF machinery that guarded them is a maintenance surface nobody was
using.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

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


def test_the_web_proxy_stays_removed():
    """No route, and none of the machinery that only existed to serve one.

    A reintroduced ``/api/proxy/fetch`` would arrive without the DNS pinning,
    redirect re-validation and body cap the deleted one had, so this fails
    loudly rather than letting a thinner version take its place quietly.
    """
    paths = {getattr(r, "path", "") for r in proxy.router.routes}
    assert "/proxy/fetch" not in paths
    assert "/proxy/raw" not in paths
    for gone in ("_safe_fetch", "_validate_url", "_is_private_host", "_rewrite_html"):
        assert not hasattr(proxy, gone), f"{gone} came back without its endpoint"


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
