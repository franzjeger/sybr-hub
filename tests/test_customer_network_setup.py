"""A customer's FortiGate and UniFi, as the customer page's Nettverk tab sets them up.

The setup forms moved from Verktøy > Nettverk (technicians only) onto the
customer page, which every account with access to the customer opens. Three
things in the routes behind them had to change for that:

* ``GET /network-devices/{id}`` sent each UniFi direct device's SSH password
  to whoever asked, a viewer included, because the device buttons sent it
  back to log in. It sends ``has_password`` now, and a device action that
  names its customer and leaves the password out is looked up on the server.
* Saving the device list back must then keep the passwords it no longer
  carries.
* "Remove" needs routes of its own. Clearing the address through the save
  routes left the API token, the bootstrap admin password or the controller
  login stored for a customer with no device recorded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


RECORD = {
    "CustomerId": "acme",
    "CustomerName": "Acme AS",
    "FortiGateHost": "192.0.2.1",
    "FortiGatePort": 8443,
    "FortiGateVDOM": "root",
    "FortiGateVerifySSL": False,
    "FortiGateApiUser": "msp_api_admin",
    "UniFiMode": "direct",
    "UniFiHost": "",
    "UniFiSite": "default",
    "UniFiHostId": "console-1",
    "UniFiDirectDevices": [
        {"host": "192.0.2.10", "device_type": "ap", "username": "admin", "password": "ap-secret"},
        {"host": "192.0.2.11", "device_type": "switch", "username": "ubnt"},
    ],
}


@pytest.fixture()
def stored(monkeypatch):
    """CustomerManager and the keyring, in memory. ``other`` exists too."""
    from app.core.customer import CustomerManager

    records = {"acme": dict(RECORD), "other": {"CustomerId": "other", "CustomerName": "Other"}}
    secrets = {
        ("acme", "fortigate_api_token"): "fg-token",
        ("acme", "unifi_username"): "stored-user",
        ("acme", "unifi_password"): "stored-pass",
    }

    def get_customer(cid):
        record = records.get(cid)
        return dict(record, _id=cid) if record else None

    def save_customer(data):
        # The real one replaces the record kept under its CustomerId.
        records[data["CustomerId"]] = {k: v for k, v in data.items() if not k.startswith("_")}
        return data["CustomerId"]

    monkeypatch.setattr(CustomerManager, "get_customer", staticmethod(get_customer))
    monkeypatch.setattr(CustomerManager, "save_customer", staticmethod(save_customer))
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, n: secrets.get((cid, n)))
    monkeypatch.setattr(
        "app.core.credentials.store_secret", lambda cid, n, v: secrets.__setitem__((cid, n), v)
    )
    monkeypatch.setattr(
        "app.core.credentials.delete_secret", lambda cid, n: secrets.pop((cid, n), None)
    )
    monkeypatch.setattr("app.core.activity_log.log_activity", lambda *a, **k: None)
    return records, secrets


async def _headers(name: str, role: Role = Role.technician, *, only: str | None = None) -> dict:
    user = await create_user(name, "Test1234!network", name, role=role, all_customers=only is None)
    await set_can_write(user.id, True)
    if only:
        await grant_access(user.id, only)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


# ── The listing ──────────────────────────────────────────────────────────────


async def test_the_listing_sends_no_device_password_to_anyone(client, stored):
    """A viewer may list a customer's network; it may not read its SSH passwords."""
    r = client.get("/api/network-devices/acme", headers=await _headers("viewer", Role.viewer))

    assert r.status_code == 200, r.text
    assert "ap-secret" not in r.text
    devices = r.json()["unifi"]["direct_devices"]
    assert [d["host"] for d in devices] == ["192.0.2.10", "192.0.2.11"]
    assert [d["has_password"] for d in devices] == [True, False]
    assert all("password" not in d for d in devices)
    assert devices[0]["username"] == "admin"


async def test_the_listing_says_whether_removal_needs_an_admin(client, stored):
    _, secrets = stored
    headers = await _headers("tech")
    assert (
        client.get("/api/network-devices/acme", headers=headers).json()["fortigate"][
            "has_admin_password"
        ]
        is False
    )

    secrets[("acme", "fortigate_admin_password")] = "admin-pass"

    fg = client.get("/api/network-devices/acme", headers=headers).json()["fortigate"]
    assert fg["has_admin_password"] is True
    assert "admin-pass" not in str(fg)


# ── Saving the device list back ──────────────────────────────────────────────


async def test_a_device_saved_back_without_its_password_keeps_the_stored_one(client, stored):
    """The page holds no passwords; saving its list must not wipe them."""
    records, _ = stored
    listed = client.get("/api/network-devices/acme", headers=await _headers("lister")).json()
    # What the page sends back: the listing, which holds no passwords.
    listing = [
        {k: v for k, v in d.items() if k != "password"} for d in listed["unifi"]["direct_devices"]
    ]
    devices = [
        *listing,
        {"host": "192.0.2.12", "device_type": "gateway", "username": "root", "password": "gw-pass"},
    ]

    r = client.post(
        "/api/unifi/save/acme",
        headers=await _headers("saver"),
        json={"mode": "direct", "devices": devices},
    )

    assert r.status_code == 200, r.text
    saved = {d["host"]: d for d in records["acme"]["UniFiDirectDevices"]}
    assert saved["192.0.2.10"]["password"] == "ap-secret", "the stored password was wiped"
    assert "password" not in saved["192.0.2.11"], "a device without one got one"
    assert saved["192.0.2.12"]["password"] == "gw-pass"
    assert all("has_password" not in d for d in saved.values()), "a listing field was stored"


async def test_a_typed_password_replaces_the_stored_one(client, stored):
    records, _ = stored
    r = client.post(
        "/api/unifi/save/acme",
        headers=await _headers("retyper"),
        json={"mode": "direct", "devices": [{"host": "192.0.2.10", "password": "new-pass"}]},
    )

    assert r.status_code == 200, r.text
    assert records["acme"]["UniFiDirectDevices"] == [{"host": "192.0.2.10", "password": "new-pass"}]


# ── Device actions name the customer instead of carrying the password ────────


@pytest.fixture()
def device_logins(monkeypatch):
    """Stand in for UniFiDirectDevice, recording the login each action used."""
    used: list[tuple[str, str, str]] = []

    class _Device:
        def __init__(self, host, username, password, **kw):
            used.append((host, username, password))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def test_connection(self):
            return {"ok": True}

        async def get_config_dump(self):
            return {"ok": True, "config": "x"}

        async def reboot(self):
            return {"ok": True}

        async def set_inform(self, url):
            return {"ok": True}

    monkeypatch.setattr("app.modules.unifi_audit.client.UniFiDirectDevice", _Device)
    return used


@pytest.mark.parametrize(
    ("path", "extra"),
    [
        ("/api/unifi/test-device", {}),
        ("/api/unifi/device-config", {}),
        ("/api/unifi/reboot-device", {}),
        ("/api/unifi/set-inform", {"controller_url": "http://198.51.100.5:8080/inform"}),
    ],
)
async def test_a_listed_device_connects_with_its_stored_login(
    client, stored, device_logins, path, extra
):
    r = client.post(
        path,
        headers=await _headers("actor"),
        json={"host": "192.0.2.10", "customer_id": "acme", **extra},
    )

    assert r.status_code == 200, r.text
    assert device_logins == [("192.0.2.10", "admin", "ap-secret")]


async def test_a_listed_device_without_a_password_uses_the_customers_login(
    client, stored, device_logins
):
    """The poller and the network audit fall back the same way."""
    r = client.post(
        "/api/unifi/device-config",
        headers=await _headers("fallback"),
        json={"host": "192.0.2.11", "customer_id": "acme"},
    )

    assert r.status_code == 200, r.text
    assert device_logins == [("192.0.2.11", "ubnt", "stored-pass")]


async def test_an_address_not_on_the_list_never_gets_the_stored_login(
    client, stored, device_logins
):
    """Naming a customer must not send its login to an address of the caller's."""
    r = client.post(
        "/api/unifi/device-config",
        headers=await _headers("prober"),
        json={"host": "203.0.113.66", "customer_id": "acme"},
    )

    assert r.status_code == 200, r.text
    assert device_logins == [("203.0.113.66", "ubnt", "ubnt")]


async def test_a_password_in_the_request_wins(client, stored, device_logins):
    r = client.post(
        "/api/unifi/test-device",
        headers=await _headers("typer"),
        json={"host": "192.0.2.10", "customer_id": "acme", "username": "u", "password": "typed"},
    )

    assert r.status_code == 200, r.text
    assert device_logins == [("192.0.2.10", "u", "typed")]


async def test_a_customer_the_caller_cannot_see_lends_no_login(client, stored, device_logins):
    r = client.post(
        "/api/unifi/device-config",
        headers=await _headers("scoped", only="other"),
        json={"host": "192.0.2.10", "customer_id": "acme"},
    )

    assert r.status_code == 403, r.text
    assert device_logins == []


# ── Removing a FortiGate ─────────────────────────────────────────────────────


async def test_removing_a_fortigate_forgets_its_address_settings_and_token(client, stored):
    records, secrets = stored

    r = client.delete("/api/fortigate/acme", headers=await _headers("remover"))

    assert r.status_code == 200, r.text
    assert not [k for k in records["acme"] if k.startswith("FortiGate")]
    assert ("acme", "fortigate_api_token") not in secrets
    # The rest of the customer is untouched.
    assert records["acme"]["UniFiDirectDevices"] == RECORD["UniFiDirectDevices"]
    assert ("acme", "unifi_password") in secrets


async def test_a_bootstrap_admin_password_makes_removal_an_admins_call(client, stored):
    """It is the hub's only copy of the firewall's admin login."""
    records, secrets = stored
    secrets[("acme", "fortigate_admin_password")] = "admin-pass"
    secrets[("acme", "fortigate_admin_user")] = "admin"

    refused = client.delete("/api/fortigate/acme", headers=await _headers("tech-remover"))
    assert refused.status_code == 403, refused.text
    assert records["acme"]["FortiGateHost"] == "192.0.2.1"
    assert secrets[("acme", "fortigate_api_token")] == "fg-token"

    done = client.delete("/api/fortigate/acme", headers=await _headers("adm", Role.admin))
    assert done.status_code == 200, done.text
    assert not [k for (cid, k) in secrets if cid == "acme" and k.startswith("fortigate")]


async def test_removal_takes_the_devices_firmware_readings_with_it(client, stored):
    """Nobody reads a removed device again, so its last reading, or the
    failed read standing in for it, would stay in Varsler for good."""
    from app.core.database import get_db
    from app.services import firmware_inventory

    await firmware_inventory.record_read_failure(
        "acme", "fortigate", "unreachable", key="192.0.2.1", name="192.0.2.1"
    )
    await firmware_inventory.record_read_failure(
        "acme", "unifi", "unreachable", key="controller", name="controller"
    )
    await firmware_inventory.record_read_failure(
        "other", "fortigate", "unreachable", key="198.51.100.1", name="fw"
    )

    async def readings():
        async with (
            get_db() as db,
            db.execute(
                "SELECT customer_id, vendor FROM device_firmware ORDER BY customer_id, vendor"
            ) as cur,
        ):
            return [tuple(r) for r in await cur.fetchall()]

    headers = await _headers("firmware-remover")
    assert client.delete("/api/fortigate/acme", headers=headers).status_code == 200
    assert await readings() == [("acme", "unifi"), ("other", "fortigate")]
    assert client.delete("/api/unifi/acme", headers=headers).status_code == 200
    assert await readings() == [("other", "fortigate")]


async def test_a_viewer_cannot_remove_a_fortigate(client, stored):
    records, _ = stored
    r = client.delete("/api/fortigate/acme", headers=await _headers("v", Role.viewer))
    assert r.status_code == 403, r.text
    assert records["acme"]["FortiGateHost"] == "192.0.2.1"


# ── Unlinking UniFi ──────────────────────────────────────────────────────────


async def test_unlinking_unifi_clears_the_link_and_its_login(client, stored):
    records, secrets = stored

    r = client.delete("/api/unifi/acme", headers=await _headers("unlinker"))

    assert r.status_code == 200, r.text
    left = records["acme"]
    assert not {"UniFiHost", "UniFiSite", "UniFiMode", "UniFiDirectDevices"} & set(left)
    assert ("acme", "unifi_username") not in secrets and ("acme", "unifi_password") not in secrets
    # The Site Manager console match is a separate link, and the FortiGate stays.
    assert left["UniFiHostId"] == "console-1"
    assert left["FortiGateHost"] == "192.0.2.1"
    listed = client.get("/api/network-devices/acme", headers=await _headers("after")).json()
    assert listed["unifi"] is None


# ── Testing a saved device from its edit form ────────────────────────────────
# The form holds no stored secret. "Test tilkobling" names the customer, and
# the stored token or login is used only against the address it was stored for.


@pytest.fixture()
def fortigate_tokens(monkeypatch):
    used: list[tuple[str, int, str]] = []

    class _Client:
        def __init__(self, host, token, port=443, **kw):
            used.append((host, port, token))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def test_connection(self):
            return {"ok": True, "hostname": "fw"}

    monkeypatch.setattr("app.modules.fortigate_audit.client.FortiGateClient", _Client)
    return used


async def test_a_saved_fortigate_is_tested_with_its_stored_token(client, stored, fortigate_tokens):
    r = client.post(
        "/api/fortigate/test",
        headers=await _headers("fg-tester"),
        json={"host": "192.0.2.1", "port": 8443, "customer_id": "acme"},
    )

    assert r.status_code == 200, r.text
    assert fortigate_tokens == [("192.0.2.1", 8443, "fg-token")]


@pytest.mark.parametrize(("host", "port"), [("203.0.113.66", 8443), ("192.0.2.1", 443)])
async def test_another_address_does_not_get_the_stored_token(
    client, stored, fortigate_tokens, host, port
):
    r = client.post(
        "/api/fortigate/test",
        headers=await _headers("fg-prober"),
        json={"host": host, "port": port, "customer_id": "acme"},
    )

    assert r.status_code == 400, r.text
    assert fortigate_tokens == []


async def test_a_saved_controller_is_tested_with_its_stored_login(client, stored, monkeypatch):
    records, _ = stored
    records["acme"]["UniFiHost"] = "https://unifi.acme.example:8443"
    used: list[tuple[str, str, str]] = []

    class _Controller:
        def __init__(self, base_url, username, password, **kw):
            used.append((base_url, username, password))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def test_connection(self):
            return {"ok": True, "sites": 1}

    monkeypatch.setattr("app.modules.unifi_audit.client.UniFiControllerClient", _Controller)
    headers = await _headers("uf-tester")

    same = client.post(
        "/api/unifi/test",
        headers=headers,
        json={"host": "unifi.acme.example:8443", "customer_id": "acme"},
    )
    other = client.post(
        "/api/unifi/test",
        headers=headers,
        json={"host": "https://203.0.113.66:8443", "customer_id": "acme"},
    )

    assert same.status_code == 200, same.text
    assert other.status_code == 400, other.text
    assert used == [("https://unifi.acme.example:8443", "stored-user", "stored-pass")]
