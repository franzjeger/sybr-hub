"""Azure connect must use the same guard, lock and state machine as every other.

/vpn/azure/connect-with-token called the Azure backend directly and wrote
vpn_manager._connections itself: no registry lock (two requests could both
start a tunnel) and no system-held-tunnel guard, although the backend ends
every other openvpn3 session before it starts its own.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import app.core.database as database_module
from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import set_can_write
from app.core.system_user import USERNAME as SYSTEM_USERNAME
from app.models.user import Role
from app.models.vpn import VpnProtocol, VpnState
from app.services import vpn_manager, vpn_privileges
from app.services.vpn_backends import azure
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

KEY_HEX = "ab" * 256


@pytest.fixture(autouse=True)
async def _isolated(tmp_path, monkeypatch):
    import app.web.middleware.rate_limit as rate_limit

    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    monkeypatch.setattr(vpn_privileges, "unavailable_reason", lambda _protocol: None)
    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()
    vpn_manager._connections.clear()
    await run_migrations()
    yield
    vpn_manager._connections.clear()
    _reset_users_exist_cache()


@pytest.fixture()
def azure_calls(monkeypatch):
    calls: list[tuple[dict, str]] = []

    async def _connect(config, token):
        calls.append((config, token))
        return {"ok": True, "interface": "tun0"}

    monkeypatch.setattr(azure, "connect", _connect)
    return calls


async def _profile():
    return await vpn_manager.create_profile(
        "AZ",
        VpnProtocol.azure,
        {"gateway_fqdn": "gw.example.com", "tenant_id": "t", "server_secret_hex": KEY_HEX},
    )


async def test_connect_with_a_token_registers_the_tunnel(azure_calls):
    profile = await _profile()

    result = await vpn_manager.connect(profile.id, owned_by="tech", access_token="tok")

    assert result["ok"] is True
    conn = vpn_manager._connections[profile.id]
    assert conn["state"] == VpnState.connected
    assert conn["interface"] == "tun0"
    assert conn["owned_by"] == "tech"
    config, token = azure_calls[0]
    assert token == "tok"
    assert config["server_secret_hex"] == KEY_HEX  # put back from the store


async def test_two_concurrent_connects_start_one_tunnel(monkeypatch):
    profile = await _profile()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def _slow_connect(config, token):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"ok": True, "interface": "tun0"}

    monkeypatch.setattr(azure, "connect", _slow_connect)

    first = asyncio.create_task(vpn_manager.connect(profile.id, access_token="a"))
    await started.wait()
    second = await vpn_manager.connect(profile.id, access_token="b")
    release.set()

    assert (await first)["ok"] is True
    assert second["ok"] is False
    assert calls == 1


async def test_azure_without_a_token_asks_for_sign_in(azure_calls):
    profile = await _profile()
    result = await vpn_manager.connect(profile.id)

    assert result["ok"] is False
    assert azure_calls == []
    assert profile.id not in vpn_manager._connections


async def test_the_route_refuses_while_the_system_holds_a_tunnel(azure_calls):
    profile = await _profile()
    user = await create_user(
        "tech", "Test1234!azure-connect", "tech", role=Role.technician, all_customers=True
    )
    await set_can_write(user.id, True)
    token = await create_access_token(await get_user_by_id(user.id))
    vpn_manager._connections["collector-tunnel"] = {
        "state": VpnState.connected,
        "interface": "wg-coll",
        "owned_by": SYSTEM_USERNAME,
    }

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/vpn/azure/connect-with-token",
            headers={"Authorization": f"Bearer {token}"},
            json={"profile_id": profile.id, "access_token": "tok"},
        )

    assert response.status_code == 403, response.text
    assert "Systemkontoen" in response.json()["error"]
    assert azure_calls == []
    assert profile.id not in vpn_manager._connections


async def test_the_route_connects_through_the_manager(azure_calls):
    profile = await _profile()
    user = await create_user(
        "tech", "Test1234!azure-connect", "tech", role=Role.technician, all_customers=True
    )
    await set_can_write(user.id, True)
    token = await create_access_token(await get_user_by_id(user.id))

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/vpn/azure/connect-with-token",
            headers={"Authorization": f"Bearer {token}"},
            json={"profile_id": profile.id, "access_token": "tok"},
        )
        again = client.post(
            "/api/vpn/azure/connect-with-token",
            headers={"Authorization": f"Bearer {token}"},
            json={"profile_id": profile.id, "access_token": "tok"},
        )

    assert response.json()["ok"] is True, response.text
    assert vpn_manager.owner_of(profile.id) == "tech"
    assert again.json()["ok"] is False  # already connected; not a second tunnel
    assert len(azure_calls) == 1
