"""Request models on the VPN router: disconnect and the Azure sign-in steps.

``/vpn/disconnect`` swallowed every body error and carried on as if no profile
had been named, so a malformed request quietly stopped whichever tunnel was
active. The Azure steps indexed the raw body and answered a non-object with a
500.
"""

from __future__ import annotations

import pytest

from app.services import vpn_manager
from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    assert_refused,
    tech_client,
)


@pytest.fixture(autouse=True)
def _no_tunnels(tmp_path, monkeypatch):
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    vpn_manager._connections.clear()
    yield
    vpn_manager._connections.clear()


async def test_disconnect_with_no_body_still_means_the_active_tunnel(tech_client):
    r = tech_client.post("/api/vpn/disconnect")

    assert r.status_code == 200, r.text
    assert r.json()["msg"] == "Already disconnected"


async def test_disconnect_with_what_the_spa_sends_still_works(tech_client):
    """vpnDisconnect() sends ``{}`` or ``{profile_id}``."""
    assert tech_client.post("/api/vpn/disconnect", json={}).status_code == 200
    # A profile the caller cannot see is refused, not silently ignored.
    assert_refused(tech_client.post("/api/vpn/disconnect", json={"profile_id": "nope"}), 403)


async def test_a_malformed_disconnect_is_refused_rather_than_stopping_the_active_one(
    tech_client,
):
    for body in ({"profile_id": 5}, ["p1"], {"profileId": "p1"}):
        assert_refused(tech_client.post("/api/vpn/disconnect", json=body), 422)


@pytest.mark.parametrize("path", ["/api/vpn/azure/try-silent", "/api/vpn/azure/pkce-start"])
async def test_azure_steps_still_answer_an_unknown_profile_with_404(tech_client, path):
    assert_refused(tech_client.post(path, json={"profile_id": "nope"}), 404)
    assert_refused(tech_client.post(path, json={"profile_id": ["nope"]}), 422)
    assert_refused(tech_client.post(path, json={"profile": "nope"}), 422)


async def test_device_code_still_takes_the_profile_from_the_query(tech_client):
    """The body is optional there; it used to be a 500 when left out."""
    assert_refused(tech_client.post("/api/vpn/azure/device-code?profile_id=nope"), 404)
    assert_refused(tech_client.post("/api/vpn/azure/device-code", json={"profile_id": 1}), 422)


async def test_pkce_complete_keeps_its_message_for_a_url_without_a_code(tech_client):
    body = assert_refused(
        tech_client.post(
            "/api/vpn/azure/pkce-complete", json={"callback_url": "http://localhost:2023/"}
        ),
        400,
    )
    assert "auth-kode" in body["error"]
    assert_refused(tech_client.post("/api/vpn/azure/pkce-complete", json={"callback_url": 1}), 422)


async def test_connect_with_token_keeps_its_message_for_a_missing_token(tech_client):
    body = assert_refused(
        tech_client.post("/api/vpn/azure/connect-with-token", json={"profile_id": "p1"}), 400
    )
    assert body["error"] == "Ingen access token"
    assert_refused(
        tech_client.post(
            "/api/vpn/azure/connect-with-token",
            json={"profile_id": "p1", "access_token": {"token": "x"}},
        ),
        422,
    )
