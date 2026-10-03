"""Provider sign-in failures must never revoke or impersonate a Hub session."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.exceptions import IntegrationError
from app.core.rbac import set_can_write
from app.integrations.also_cloud import AlsoCloudAuthError, AlsoCloudClient, AlsoCloudError
from app.models.user import Role
from app.services.uniweb_client import UniwebClient, UniwebScrapeError, _classify_login_outcome
from app.services.uniweb_partner import UniwebAuthError
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


@pytest.fixture
async def admin(tmp_path, monkeypatch):
    import app.core.database as db
    import app.web.middleware.rate_limit as rl

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "hub.db")
    await run_migrations()
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    user = await create_user("integration-admin", "Synthetic-Test123!", "Admin", role=Role.admin)
    await set_can_write(user.id, True)
    yield {"Authorization": "Bearer " + await create_access_token(user)}
    _reset_users_exist_cache()


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("lang,fragment", [("en", "Tailscale"), ("nb-NO", "Tailscale")])
async def test_tailscale_credential_failure_preserves_hub_session(
    admin, monkeypatch, status, lang, fragment
):
    # Patch only the vendor HTTP operation, while exercising the real route,
    # authentication middleware and exception handler.
    async def vendor_get(self, url, **kwargs):
        assert str(self.base_url).startswith("https://api.tailscale.com/")
        return httpx.Response(status, request=httpx.Request("GET", str(self.base_url)))

    monkeypatch.setattr(httpx.AsyncClient, "get", vendor_get)
    with TestClient(create_app()) as client:
        headers = {**admin, "Accept-Language": lang}
        r = client.post("/api/tailscale/test", headers=headers, json={"api_key": "synthetic"})
        assert r.status_code == 400
        assert fragment in r.json()["error"]
        assert r.json()["error_key"] == (
            "err_tailscale_credentials" if status == 401 else "err_tailscale_scope"
        )
        assert "www-authenticate" not in r.headers
        assert client.get("/api/auth/me", headers=admin).status_code == 200


async def test_masked_tailscale_field_uses_the_stored_token(admin, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.load_app_settings", lambda: {"tailscale_api_key": "stored-synthetic-token"}
    )

    async def vendor_get(self, url, **kwargs):
        assert self.headers["Authorization"] == "Bearer stored-synthetic-token"
        return httpx.Response(200, json={"devices": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", vendor_get)
    with TestClient(create_app()) as client:
        r = client.post("/api/tailscale/test", headers=admin, json={"api_key": "••••••"})
        assert r.status_code == 200
        assert "stored-synthetic-token" not in r.text


async def test_masked_also_field_uses_saved_password_and_closes_client(admin, monkeypatch):
    monkeypatch.setattr(
        "app.web.routes.also._get_also_config",
        lambda: {"username": "saved", "password": "stored-secret", "country": "no"},
    )
    closed = []

    async def authenticate(self):
        assert self.username == "saved" and self.password == "stored-secret"

    async def close(self):
        closed.append(True)
        await self._client.aclose()

    monkeypatch.setattr(AlsoCloudClient, "authenticate", authenticate)
    monkeypatch.setattr(AlsoCloudClient, "ping", AsyncMock(return_value=True))
    monkeypatch.setattr(AlsoCloudClient, "close", close)
    with TestClient(create_app()) as client:
        r = client.post(
            "/api/also/test",
            headers=admin,
            json={"username": "saved", "password": "••••••", "country": "no"},
        )
        assert r.status_code == 200
        assert "stored-secret" not in r.text
        assert closed == [True]
        r = client.post(
            "/api/also/test",
            headers=admin,
            json={"username": "another", "password": "••••••", "country": "no"},
        )
        assert r.status_code == 400
        assert r.json()["error_key"] == "err_reenter_provider_password"
        assert closed == [True]  # No credentials were sent for a different account.


@pytest.mark.parametrize(
    "lang,fragment",
    [("en", "MFA is enabled on the ALSO account"), ("nb-NO", "ALSO-kontoen har MFA aktivert")],
)
async def test_also_mfa_fault_is_actionable_and_preserves_hub_session(
    admin, monkeypatch, lang, fragment
):
    calls = []

    async def vendor_post(self, url, **kwargs):
        calls.append(str(url))
        assert str(url).endswith("/GetSessionToken")
        return httpx.Response(
            500,
            text="""<s:Fault xmlns:s="http://www.w3.org/2003/05/soap-envelope">
              <s:Reason><s:Text>Unable to get session token. Users with enabled MFA are not supported.</s:Text></s:Reason>
              <s:Detail><ServiceException><Message>Unable to get session token. Users with enabled MFA are not supported.</Message>
              <IssueToken>must-not-escape</IssueToken></ServiceException></s:Detail>
            </s:Fault>""",
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", vendor_post)
    with TestClient(create_app()) as client:
        r = client.post(
            "/api/also/test",
            headers={**admin, "Accept-Language": lang},
            json={"username": "synthetic", "password": "synthetic-password", "country": "no"},
        )
        assert r.status_code == 400
        assert r.json()["error_key"] == "err_also_mfa_unsupported"
        assert fragment in r.json()["error"]
        assert "must-not-escape" not in r.text
        assert "synthetic-password" not in r.text
        assert len(calls) == 1
        assert client.get("/api/auth/me", headers=admin).status_code == 200


async def test_also_xml_500_is_a_credential_error_without_leaking_the_fault():
    client = AlsoCloudClient("synthetic-user", "synthetic-password")
    await client._client.aclose()
    body = """<Fault><Detail><ServiceException><Message>We could not sign you in.
    Check your username and password and try again.</Message><Secret>must-not-escape</Secret>
    </ServiceException></Detail></Fault>"""
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, text=body, headers={"Content-Type": "application/xml"})
        )
    )
    try:
        with pytest.raises(AlsoCloudAuthError) as error:
            await client.authenticate()
        assert error.value.message_key == "err_also_credentials"
        assert "must-not-escape" not in str(error.value)
        assert client._session_token is None
    finally:
        await client.close()


async def test_also_outage_is_not_misreported_as_wrong_password():
    client = AlsoCloudClient("u", "p")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503, text="maintenance"))
    )
    try:
        with pytest.raises(AlsoCloudError) as error:
            await client.authenticate()
        assert not isinstance(error.value, AlsoCloudAuthError)
        assert error.value.message_key == "err_also_unavailable"
    finally:
        await client.close()


@pytest.fixture
def partner(monkeypatch):
    import app.web.routes.uniweb as route

    cfg = {"email": "synthetic@example.invalid", "password": "synthetic"}
    monkeypatch.setattr(route, "_get_uniweb_config", lambda: dict(cfg))
    monkeypatch.setattr(route, "_partner_cfg", dict(cfg))
    monkeypatch.setattr(route, "_partner_cookies", None)
    monkeypatch.setattr(route, "_partner_retry_after", 0.0)
    monkeypatch.setattr(route, "_partner_lock", asyncio.Lock())
    harvest = AsyncMock(return_value={"session": "fresh", "grant": "partner"})
    monkeypatch.setattr(route, "_harvest_partner_cookies", harvest)
    return route, harvest, cfg


async def test_parallel_expired_partner_requests_share_one_login(partner):
    route, harvest, _ = partner
    route._partner_cookies = {"session": "stale", "grant": "partner"}

    async def read(client):
        if "stale" in client._client.headers["cookie"]:
            raise UniwebAuthError("expired")
        return ["record"]

    result = await asyncio.gather(*(route._partner_call(read) for _ in range(5)))
    assert result == [["record"]] * 5
    harvest.assert_awaited_once()


async def test_rejected_fresh_session_cools_down_and_credentials_reset_it(partner):
    route, harvest, cfg = partner
    read = AsyncMock(side_effect=UniwebAuthError("rejected"))
    for _ in range(3):
        with pytest.raises(IntegrationError) as error:
            await route._partner_call(read)
        assert error.value.status_code == 502
        assert error.value.message_key == "err_uniweb_auth"
    harvest.assert_awaited_once()
    assert read.await_count == 1
    cfg["password"] = "corrected"
    assert await route._partner_call(AsyncMock(return_value=["recovered"])) == ["recovered"]
    assert harvest.await_count == 2


async def test_failed_relogin_after_expiry_also_cools_down(partner):
    route, harvest, _ = partner
    route._partner_cookies = {"session": "stale", "grant": "partner"}
    harvest.side_effect = IntegrationError("Login rejected", message_key="err_uniweb_auth")
    read = AsyncMock(side_effect=UniwebAuthError("expired"))
    for _ in range(2):
        with pytest.raises(IntegrationError):
            await route._partner_call(read)
    assert route._partner_cookies is None
    harvest.assert_awaited_once()
    read.assert_awaited_once()


def test_unknown_login_page_is_not_a_success():
    for probe in (
        {},
        {"url": "about:blank", "form_present": False},
        {"url": "https://another.invalid/", "form_present": False},
    ):
        assert _classify_login_outcome(probe)[0] is False


def test_partner_context_is_selected_before_accepting_a_grant(monkeypatch):
    client = UniwebClient()
    client._logged_in = True
    monkeypatch.setattr(client, "_nav", lambda *args, **kwargs: None)
    calls = iter(["Synthetic Partner", True])
    monkeypatch.setattr(client, "_js", lambda _: next(calls))
    monkeypatch.setattr(client, "harvest_cookies", lambda: {"session": "s", "grant": "g"})
    client.select_partner_context()


def test_ambiguous_partner_context_fails_closed(monkeypatch):
    client = UniwebClient()
    client._logged_in = True
    monkeypatch.setattr(client, "_nav", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "_js", lambda _: False)
    with pytest.raises(UniwebScrapeError, match="unique"):
        client.select_partner_context()
