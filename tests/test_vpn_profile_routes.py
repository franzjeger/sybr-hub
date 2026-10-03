"""The VPN profile routes must not hand out secrets or move profiles freely.

GET /vpn/profiles/{id} returned the stored config to any signed-in viewer of
the customer, which (with the storage defects fixed elsewhere) included
OpenVPN private keys and edited passwords. The vpn feature's floor is
technician, and the config now carries flags instead of secret material.

PUT reports which secrets a retarget wiped, and moving a profile to another
customer needs access to that customer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.customer import CustomerManager
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.models.vpn import VpnProtocol
from app.services import vpn_manager, vpn_privileges
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!vpn-profile-routes"
KEY_MATERIAL = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
OVPN = (
    "client\nremote vpn.example.com 1194\n"
    f"<key>\n-----BEGIN PRIVATE KEY-----\n{KEY_MATERIAL}\n-----END PRIVATE KEY-----\n</key>\n"
)


@pytest.fixture(autouse=True)
async def _isolated_state(tmp_path, monkeypatch):
    import app.core.customer as customer_module
    import app.core.database as database_module
    import app.web.middleware.rate_limit as rate_limit

    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "test.db")
    customers = tmp_path / "customers"
    customers.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customers)
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()
    vpn_manager._connections.clear()
    await run_migrations()
    yield
    vpn_manager._connections.clear()
    _reset_users_exist_cache()


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _customer(name: str) -> str:
    tenant = name.lower()
    return CustomerManager.save_customer(
        {
            "CustomerName": name,
            "PrimaryDomain": f"{tenant}.example",
            "TenantId": tenant,
            "ClientId": f"client-{tenant}",
        }
    )


async def _headers(
    username: str, role: Role = Role.technician, *, all_customers: bool = True
) -> tuple[str, dict]:
    user = await create_user(username, PASSWORD, username, role=role, all_customers=all_customers)
    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    token = await create_access_token(user)
    return user.id, {"Authorization": f"Bearer {token}"}


async def _fortigate(customer_id: str | None = None):
    return await vpn_manager.create_profile(
        "FG",
        VpnProtocol.fortigate_ipsec,
        {
            "host": "fw.example.com",
            "username": "tech",
            "password": "pw-secret",
            "psk": "psk-secret",
        },
        customer_id=customer_id,
    )


async def test_a_viewer_cannot_read_a_profile(client):
    profile = await _fortigate()
    _, headers = await _headers("viewer", Role.viewer, all_customers=True)

    response = client.get(f"/api/vpn/profiles/{profile.id}", headers=headers)
    assert response.status_code == 403, response.text


async def test_a_technician_sees_flags_not_secrets(client):
    profile = await _fortigate()
    _, headers = await _headers("tech")

    response = client.get(f"/api/vpn/profiles/{profile.id}", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()["profile"]
    assert "pw-secret" not in response.text and "psk-secret" not in response.text
    assert body["config"]["host"] == "fw.example.com"
    assert body["secrets"] == {"has_password": True, "has_psk": True, "needs_reentry": []}


async def test_inline_openvpn_keys_are_not_returned(client):
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")
    _, headers = await _headers("tech")

    response = client.get(f"/api/vpn/profiles/{profile.id}", headers=headers)

    assert response.status_code == 200, response.text
    assert KEY_MATERIAL not in response.text
    assert "{{sybr-secret:" in response.json()["profile"]["config"]["config_content"]


async def test_a_retarget_reports_the_wiped_secrets(client, monkeypatch):
    profile = await _fortigate()
    _, headers = await _headers("tech")

    response = client.put(
        f"/api/vpn/profiles/{profile.id}",
        headers=headers,
        json={"config": {"host": "fw2.example.com", "username": "tech"}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["secrets_cleared"] == ["password", "psk"]
    assert body["message"].startswith("Profilen er lagret, men målet ble endret")

    english = client.put(
        f"/api/vpn/profiles/{profile.id}",
        headers={**headers, "Accept-Language": "en"},
        json={"config": {"host": "fw3.example.com", "username": "tech", "psk": "new"}},
    )
    assert english.json() == {"ok": True}  # nothing stored was left to wipe

    # Connecting now names what is missing, in the caller's language.
    monkeypatch.setattr(vpn_privileges, "unavailable_reason", lambda _protocol: None)
    connect = client.post(
        f"/api/vpn/connect/{profile.id}", headers={**headers, "Accept-Language": "en"}
    )
    assert connect.json()["ok"] is False
    assert connect.json()["error"] == "Enter these secrets again before connecting: password"


async def test_moving_a_profile_needs_access_to_the_new_customer(client):
    alpha = _customer("Alpha")
    beta = _customer("Beta")
    user_id, headers = await _headers("alpha-tech", all_customers=False)
    await grant_access(user_id, alpha)
    profile = await _fortigate(customer_id=alpha)

    response = client.put(
        f"/api/vpn/profiles/{profile.id}", headers=headers, json={"customer_id": beta}
    )

    assert response.status_code == 403, response.text
    assert (await vpn_manager.get_profile(profile.id)).customer_id == alpha


async def test_an_administrator_can_make_a_profile_shared(client):
    alpha = _customer("Alpha")
    profile = await _fortigate(customer_id=alpha)
    _, headers = await _headers("admin", Role.admin)

    response = client.put(
        f"/api/vpn/profiles/{profile.id}", headers=headers, json={"customer_id": None}
    )

    assert response.status_code == 200, response.text
    assert (await vpn_manager.get_profile(profile.id)).customer_id is None


async def test_a_hostile_config_is_a_400_not_a_stored_profile(client):
    _, headers = await _headers("admin", Role.admin)
    response = client.post(
        "/api/vpn/profiles",
        headers=headers,
        json={
            "name": "WG",
            "protocol": "wireguard",
            "config": {
                "private_key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
                "addresses": ["10.0.0.2/24\nPostUp = touch /tmp/pwned"],
                "peers": [],
            },
        },
    )
    assert response.status_code == 400, response.text
    assert await vpn_manager.list_profiles() == []
