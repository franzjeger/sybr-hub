"""FortiGate and UniFi: stored credentials, connection tests and fleet views.

The hub holds each customer's firewall API token and controller login and
sends them on the caller's behalf. Whoever can choose where they are sent, or
read what comes back from every customer at once, has the credentials in all
but name, so these tests pin who may do either.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app


@pytest.fixture(autouse=True)
def _reset_state():
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


async def _token(
    name: str,
    role: Role = Role.technician,
    *,
    customers: list[str] | None = None,
    all_customers: bool = False,
) -> dict[str, str]:
    user = await create_user(
        name, "Test1234!xyz", name.title(), role=role, all_customers=all_customers
    )
    for cid in customers or []:
        await grant_access(user.id, cid)
    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


@pytest.fixture()
def secrets(monkeypatch) -> dict[tuple[str, str], str]:
    """An in-memory credential store, so nothing reaches the OS keyring."""
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        "app.core.credentials.store_secret", lambda t, n, v: store.__setitem__((t, n), v)
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda t, n: store.get((t, n)))
    monkeypatch.setattr("app.core.credentials.delete_secret", lambda t, n: store.pop((t, n), None))
    return store


@pytest.fixture()
def acme(monkeypatch) -> dict:
    """The active customer, held in memory."""
    from app.core.customer import CustomerManager

    record = {
        "_id": "acme",
        "CustomerName": "Acme AS",
        "FortiGateHost": "10.20.0.1",
        "FortiGatePort": 8443,
        "FortiGateVerifySSL": True,
        "UniFiHost": "unifi.acme.no",
        "UniFiMode": "controller",
    }
    monkeypatch.setattr(CustomerManager, "get_customer", staticmethod(lambda _id: dict(record)))
    monkeypatch.setattr(
        CustomerManager, "save_customer", staticmethod(lambda data: record.update(data))
    )
    return record


# ── Repointing a firewall or controller ──────────────────────────────────────


class TestRepointingTheFortiGateClearsItsToken:
    @pytest.mark.parametrize(
        "change",
        [
            {"host": "203.0.113.66"},
            {"port": 443},
            {"host": "203.0.113.66", "verify_ssl": False},
        ],
    )
    async def test_a_new_address_without_a_token_drops_the_stored_one(
        self, client, acme, secrets, change
    ):
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json=change,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["token_cleared"] is True
        assert ("acme", "fortigate_api_token") not in secrets

    async def test_a_new_address_with_a_new_token_keeps_that_token(self, client, acme, secrets):
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"host": "10.20.0.9", "api_token": "fresh-token"},
        )
        assert resp.status_code == 200, resp.text
        assert secrets[("acme", "fortigate_api_token")] == "fresh-token"

    async def test_resaving_the_same_address_keeps_the_token(self, client, acme, secrets):
        """The settings form sends every field. Only a real change counts."""
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"host": "10.20.0.1", "port": 8443, "vdom": "root", "verify_ssl": True},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["token_cleared"] is False
        assert secrets[("acme", "fortigate_api_token")] == "stored-token"

    async def test_the_rule_applies_to_admins_as_well(self, client, acme, secrets):
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("admin", Role.admin),
            json={"host": "10.20.0.9", "verify_ssl": False},
        )
        assert resp.status_code == 200, resp.text
        assert ("acme", "fortigate_api_token") not in secrets

    async def test_a_technician_cannot_repoint_a_firewall_with_a_stored_admin_password(
        self, client, acme, secrets
    ):
        """It cannot be re-entered here, and deleting it would lose the only copy."""
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        secrets[("acme", "fortigate_admin_password")] = "bootstrap-pw"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"host": "10.20.0.9", "api_token": "fresh-token"},
        )
        assert resp.status_code == 403, resp.text
        assert acme["FortiGateHost"] == "10.20.0.1"
        assert secrets[("acme", "fortigate_api_token")] == "stored-token"
        assert secrets[("acme", "fortigate_admin_password")] == "bootstrap-pw"

    async def test_an_admin_may_repoint_it_and_keeps_the_admin_password(
        self, client, acme, secrets
    ):
        secrets[("acme", "fortigate_api_token")] = "stored-token"
        secrets[("acme", "fortigate_admin_password")] = "bootstrap-pw"
        resp = client.post(
            "/api/fortigate/save/acme",
            headers=await _token("admin", Role.admin),
            json={"host": "10.20.0.9"},
        )
        assert resp.status_code == 200, resp.text
        assert acme["FortiGateHost"] == "10.20.0.9"
        assert secrets[("acme", "fortigate_admin_password")] == "bootstrap-pw"
        assert ("acme", "fortigate_api_token") not in secrets


class TestRepointingUniFiClearsItsLogin:
    async def test_a_new_controller_without_a_password_drops_the_login(self, client, acme, secrets):
        secrets[("acme", "unifi_username")] = "admin"
        secrets[("acme", "unifi_password")] = "controller-pw"
        resp = client.post(
            "/api/unifi/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"host": "203.0.113.66"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["credentials_cleared"] is True
        assert ("acme", "unifi_password") not in secrets
        assert ("acme", "unifi_username") not in secrets

    async def test_a_new_controller_with_a_password_stores_it(self, client, acme, secrets):
        secrets[("acme", "unifi_username")] = "admin"
        secrets[("acme", "unifi_password")] = "controller-pw"
        resp = client.post(
            "/api/unifi/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"host": "unifi2.acme.no", "password": "new-pw"},
        )
        assert resp.status_code == 200, resp.text
        assert secrets[("acme", "unifi_password")] == "new-pw"
        assert secrets[("acme", "unifi_username")] == "admin"

    async def test_adding_a_direct_device_that_would_use_the_stored_login_drops_it(
        self, client, acme, secrets
    ):
        secrets[("acme", "unifi_username")] = "admin"
        secrets[("acme", "unifi_password")] = "controller-pw"
        resp = client.post(
            "/api/unifi/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"mode": "direct", "devices": [{"host": "203.0.113.66"}]},
        )
        assert resp.status_code == 200, resp.text
        assert ("acme", "unifi_password") not in secrets

    async def test_a_direct_device_with_its_own_password_does_not(self, client, acme, secrets):
        secrets[("acme", "unifi_username")] = "admin"
        secrets[("acme", "unifi_password")] = "controller-pw"
        resp = client.post(
            "/api/unifi/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={
                "mode": "direct",
                "devices": [{"host": "10.0.0.5", "username": "ubnt", "password": "ap-pw"}],
            },
        )
        assert resp.status_code == 200, resp.text
        assert secrets[("acme", "unifi_password")] == "controller-pw"

    async def test_a_direct_device_host_is_validated(self, client, acme, secrets):
        resp = client.post(
            "/api/unifi/save/acme",
            headers=await _token("tech", customers=["acme"]),
            json={"mode": "direct", "devices": [{"host": "10.0.0.5;reboot"}]},
        )
        assert resp.status_code == 400, resp.text


# ── Connection tests are not a port scanner ──────────────────────────────────


class _FakeFortiGate:
    """Stands in for FortiGateClient; answers test_connection with *result*."""

    result: ClassVar[dict] = {}
    opened: ClassVar[list[dict]] = []

    def __init__(self, host, token, **kwargs):
        _FakeFortiGate.opened.append({"host": host, **kwargs})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def test_connection(self):
        return _FakeFortiGate.result


class _FakeController:
    """Stands in for UniFiControllerClient; login fails with *error* if set."""

    error: Exception | None = None
    opened: ClassVar[list[str]] = []

    def __init__(self, host, username, password, **kwargs):
        _FakeController.opened.append(host)

    async def __aenter__(self):
        if _FakeController.error:
            raise _FakeController.error
        return self

    async def __aexit__(self, *_):
        return None

    async def test_connection(self):
        return {"ok": True, "mode": "controller", "sites": 1}


@pytest.fixture()
def fake_clients(monkeypatch):
    _FakeFortiGate.opened = []
    _FakeController.opened = []
    _FakeController.error = None
    monkeypatch.setattr("app.modules.fortigate_audit.client.FortiGateClient", _FakeFortiGate)
    monkeypatch.setattr("app.modules.unifi_audit.client.UniFiControllerClient", _FakeController)


_FG_BODY = {"host": "10.20.0.1", "port": 8443, "api_token": "t", "vdom": "root"}
_UF_BODY = {"host": "unifi.acme.no:8443", "username": "admin", "password": "pw"}


class TestConnectionTests:
    @pytest.mark.parametrize(
        ("path", "body"), [("/api/fortigate/test", _FG_BODY), ("/api/unifi/test", _UF_BODY)]
    )
    async def test_viewers_cannot_run_them(self, client, fake_clients, path, body):
        resp = client.post(path, headers=await _token("viewer", Role.viewer), json=body)
        assert resp.status_code == 403, resp.text
        assert _FakeFortiGate.opened == [] and _FakeController.opened == []

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/fortigate/test", {**_FG_BODY, "host": "10.0.0.1/admin"}),
            ("/api/fortigate/test", {**_FG_BODY, "port": 0}),
            ("/api/fortigate/test", {**_FG_BODY, "vdom": "root&x=1"}),
            ("/api/unifi/test", {**_UF_BODY, "host": "https://unifi.acme.no/x?y=1"}),
            ("/api/unifi/test", {**_UF_BODY, "host": "https://user@unifi.acme.no"}),
            ("/api/unifi/test", {**_UF_BODY, "host": "gopher://unifi.acme.no"}),
        ],
    )
    async def test_the_target_is_validated(self, client, fake_clients, path, body):
        resp = client.post(path, headers=await _token("tech"), json=body)
        assert resp.status_code == 400, resp.text
        assert _FakeFortiGate.opened == [] and _FakeController.opened == []

    async def test_a_fortigate_failure_is_a_category_not_the_exception_text(
        self, client, fake_clients, caplog
    ):
        _FakeFortiGate.result = {
            "ok": False,
            "error": "FortiGate /api/v2/monitor/system/status failed after 3 attempts "
            "(last status: None): [Errno 111] Connection refused",
        }
        resp = client.post("/api/fortigate/test", headers=await _token("tech"), json=_FG_BODY)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert body["error_key"] == "err_device_test_unreachable"
        assert "Errno" not in body["error"] and "attempts" not in body["error"]
        assert "Connection refused" in caplog.text, "the detail should reach the server log"

    async def test_a_rejected_fortigate_token_says_so(self, client, fake_clients):
        _FakeFortiGate.result = {"ok": False, "error": "HTTP 401"}
        resp = client.post("/api/fortigate/test", headers=await _token("tech"), json=_FG_BODY)
        assert resp.json()["error_key"] == "err_device_test_auth"

    async def test_a_unifi_failure_is_a_category_not_the_exception_text(self, client, fake_clients):
        _FakeController.error = ConnectionError(
            "UniFi controller unreachable: [SSL: CERTIFICATE_VERIFY_FAILED] self-signed"
        )
        resp = client.post("/api/unifi/test", headers=await _token("tech"), json=_UF_BODY)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert body["error_key"] == "err_device_test_unreachable"
        assert "SSL" not in body["error"]

    async def test_a_rejected_unifi_login_says_so(self, client, fake_clients):
        _FakeController.error = ConnectionError("UniFi login failed: HTTP 400")
        resp = client.post("/api/unifi/test", headers=await _token("tech"), json=_UF_BODY)
        assert resp.json()["error_key"] == "err_device_test_auth"

    async def test_the_controller_address_is_rebuilt_from_its_parts(self, client, fake_clients):
        resp = client.post("/api/unifi/test", headers=await _token("tech"), json=_UF_BODY)
        assert resp.json()["ok"] is True
        assert _FakeController.opened == ["https://unifi.acme.no:8443"]


# ── Fleet and Site Manager views stay inside the caller's customers ──────────


@pytest.fixture()
def two_firewalls(monkeypatch, secrets) -> list[str]:
    """Two customers with a FortiGate and a stored token; returns who was polled."""
    from app.core.customer import CustomerManager

    customers = [
        {"_id": "acme", "CustomerName": "Acme AS", "FortiGateHost": "10.20.0.1"},
        {"_id": "other", "CustomerName": "Other AS", "FortiGateHost": "10.30.0.1"},
    ]
    monkeypatch.setattr(CustomerManager, "list_customers", staticmethod(lambda: customers))
    secrets[("acme", "fortigate_api_token")] = "acme-token"
    secrets[("other", "fortigate_api_token")] = "other-token"

    polled: list[str] = []

    def _build_client(config, token):
        polled.append(config["_id"])
        raise ConnectionError("not polling from a test")

    monkeypatch.setattr("app.services.fortigate_api._build_client", _build_client)
    return polled


class TestFortiGateFleet:
    async def test_a_scoped_viewer_sees_and_polls_only_their_customers(self, client, two_firewalls):
        resp = client.get(
            "/api/fortigate/all", headers=await _token("viewer", Role.viewer, customers=["acme"])
        )
        assert resp.status_code == 200, resp.text
        assert [f["customer_id"] for f in resp.json()["fortigates"]] == ["acme"]
        assert two_firewalls == ["acme"], "another customer's token was used"

    async def test_an_unrestricted_user_sees_every_firewall(self, client, two_firewalls):
        resp = client.get("/api/fortigate/all", headers=await _token("admin", Role.admin))
        assert resp.status_code == 200, resp.text
        assert {f["customer_id"] for f in resp.json()["fortigates"]} == {"acme", "other"}


@pytest.fixture()
def site_manager(monkeypatch) -> list[str]:
    """Stub every Site Manager call; returns the names of those that ran."""
    from app.core.customer import CustomerManager

    monkeypatch.setattr(CustomerManager, "list_customers", staticmethod(lambda: []))
    called: list[str] = []

    def _stub(name, result):
        async def _fn(*_a, **_k):
            called.append(name)
            return result

        monkeypatch.setattr(f"app.services.unifi_api.{name}", _fn)

    _stub("get_all_devices", {"ok": True, "devices": [], "count": 0})
    _stub("get_isp_metrics", {"ok": True, "sites": []})
    _stub("get_site_overview", {"ok": True, "sites": []})
    _stub("get_site_wan_details", {"ok": True, "wans": [], "gateway": {}})
    _stub("get_hosts_with_names", {"ok": True, "hosts": []})
    _stub("site_manager_list_sites", {"ok": True, "sites": [{"id": "h1", "name": "Other-HQ"}]})
    _stub("site_manager_authenticate", {"ok": True, "method": "api_key"})
    return called


_SITE_MANAGER_VIEWS = [
    "/api/unifi/sm/devices",
    "/api/unifi/sm/isp-metrics",
    "/api/unifi/sm/sites-overview",
    "/api/unifi/sm/site/site-1/wan",
    "/api/unifi/site-matches",
]


class TestSiteManagerViews:
    @pytest.mark.parametrize("path", _SITE_MANAGER_VIEWS)
    async def test_a_customer_scoped_viewer_is_refused(self, client, site_manager, path):
        resp = client.get(path, headers=await _token("viewer", Role.viewer, customers=["acme"]))
        assert resp.status_code == 403, resp.text
        assert site_manager == [], "the MSP-wide account was queried anyway"

    @pytest.mark.parametrize("path", _SITE_MANAGER_VIEWS)
    async def test_an_all_customers_viewer_gets_them(self, client, site_manager, path):
        resp = client.get(path, headers=await _token("viewer", Role.viewer, all_customers=True))
        assert resp.status_code == 200, resp.text

    async def test_unifi_all_does_not_fall_back_to_the_msp_account_for_a_scoped_user(
        self, client, site_manager, monkeypatch
    ):
        from app.core.customer import CustomerManager

        monkeypatch.setattr(CustomerManager, "list_customers", staticmethod(lambda: []))
        monkeypatch.setattr(
            "app.core.config.load_app_settings",
            lambda: {"unifi_site_manager_api_key": "msp-key"},
        )
        scoped = await _token("viewer", Role.viewer, customers=["acme"])
        resp = client.get("/api/unifi/all", headers=scoped)
        assert resp.status_code == 200, resp.text
        assert resp.json()["devices"] == []
        assert site_manager == []

        resp = client.get("/api/unifi/all", headers=await _token("admin", Role.admin))
        assert [d.get("name") for d in resp.json()["devices"]] == ["Other-HQ"]

    async def test_listing_cloud_sites_needs_the_customers_own_token(
        self, client, site_manager, secrets
    ):
        tech = await _token("tech", customers=["acme", "beta"])
        assert client.get("/api/unifi/site-manager/sites", headers=tech).status_code == 403
        assert (
            client.get("/api/unifi/site-manager/sites?customer_id=other", headers=tech).status_code
            == 403
        )
        assert (
            client.get("/api/unifi/site-manager/sites?customer_id=beta", headers=tech).status_code
            == 403
        ), "without its own token the MSP-wide key answers"
        assert site_manager == []

        secrets[("acme", "ui_cloud_token")] = "acme-cloud-token"
        resp = client.get("/api/unifi/site-manager/sites?customer_id=acme", headers=tech)
        assert resp.status_code == 200, resp.text

    async def test_a_cloud_token_cannot_be_stored_for_another_customer(self, client, site_manager):
        resp = client.post(
            "/api/unifi/site-manager/auth",
            headers=await _token("tech", customers=["acme"]),
            json={"api_key": "k", "customer_id": "other"},
        )
        assert resp.status_code == 403, resp.text
        assert site_manager == []
