"""The two routes that write a customer's integration settings.

``/fortigate/save`` and ``/unifi/save`` decide which address a customer's
stored firewall and controller credentials travel to. Three things were wrong
with how they did it:

* ``/fortigate/save`` sat behind ``get_current_user``, so a viewer could
  rewrite that address and store a new API token. Its sibling has always been
  technician.
* Both wrote every field unconditionally from the request body, so a request
  that omitted a field reset it. This is not hypothetical: the app's own
  "save direct devices" button sends ``{mode, devices}`` and nothing else, and
  therefore blanked the customer's controller host on every click while the
  stored username and password stayed behind.
* Both take the customer from ``CustomerManager.get_active()``. The active
  selection is now per-user, but the route still needs an access check so a
  later RBAC revocation fails closed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
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


CUSTOMER = {
    "_id": "acme",
    "CustomerName": "Acme AS",
    "FortiGateHost": "10.20.0.1",
    "FortiGatePort": 8443,
    "FortiGateVDOM": "root",
    "FortiGateVerifySSL": False,
    "UniFiHost": "unifi.acme.no",
    "UniFiSite": "acme-hq",
    "UniFiIsUniFiOS": True,
    "UniFiMode": "controller",
}


@pytest.fixture()
def stored(monkeypatch):
    """Stand in for CustomerManager with an in-memory record."""
    from app.core.customer import CustomerManager

    record = dict(CUSTOMER)
    monkeypatch.setattr(CustomerManager, "get_active", staticmethod(lambda: dict(record)))
    monkeypatch.setattr(CustomerManager, "get_customer", staticmethod(lambda _id: dict(record)))
    monkeypatch.setattr(
        CustomerManager, "save_customer", staticmethod(lambda data: record.update(data))
    )
    monkeypatch.setattr("app.core.credentials.store_secret", lambda *a, **k: None)
    return record


async def _token(
    role: Role = Role.technician, *, all_customers: bool = True, can_write: bool = True
) -> str:
    user = await create_user(
        username=f"user-{role.value}-{all_customers}-{can_write}",
        password="Test1234!xyz",
        display_name="User",
        role=role,
        all_customers=all_customers,
    )
    # These tests save integration settings, which is a write. The capability
    # defaults to off for every account, so a token that is going to POST has
    # to carry it.
    if can_write:
        from app.core.auth import get_user_by_id
        from app.core.rbac import set_can_write

        await set_can_write(user.id, True)
        user = await get_user_by_id(user.id)
    return await create_access_token(user)


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAPartialSaveDoesNotResetTheRest:
    """Absent must mean "leave alone", not "reset to the default"."""

    async def test_saving_only_the_unifi_device_list_keeps_the_controller_host(
        self, client, stored
    ):
        # Exactly what saveUniFiDirect() sends.
        resp = client.post(
            "/api/unifi/save",
            headers=_hdr(await _token()),
            json={"mode": "direct", "devices": [{"host": "10.0.0.5"}]},
        )
        assert resp.status_code == 200, resp.text
        assert stored["UniFiHost"] == "unifi.acme.no", "the controller address was blanked"
        assert stored["UniFiSite"] == "acme-hq", "a non-default site was reset"
        assert stored["UniFiIsUniFiOS"] is True
        assert stored["UniFiDirectDevices"] == [{"host": "10.0.0.5"}]

    async def test_saving_only_a_fortigate_token_keeps_the_address_and_port(
        self, client, stored
    ):
        resp = client.post(
            "/api/fortigate/save",
            headers=_hdr(await _token()),
            json={"api_token": "new-token"},
        )
        assert resp.status_code == 200, resp.text
        assert stored["FortiGateHost"] == "10.20.0.1"
        assert stored["FortiGatePort"] == 8443, "a hardened port fell back to 443"
        assert stored["FortiGateVerifySSL"] is False, "verify_ssl was silently turned on"

    async def test_a_field_that_is_present_is_still_written(self, client, stored):
        resp = client.post(
            "/api/fortigate/save",
            headers=_hdr(await _token()),
            json={"host": "10.20.0.9", "port": 443, "verify_ssl": True},
        )
        assert resp.status_code == 200, resp.text
        assert stored["FortiGateHost"] == "10.20.0.9"
        assert stored["FortiGatePort"] == 443
        assert stored["FortiGateVerifySSL"] is True

    async def test_clearing_a_field_on_purpose_still_works(self, client, stored):
        """Sending an explicit empty host is a deliberate clear, not an omission."""
        resp = client.post(
            "/api/fortigate/save", headers=_hdr(await _token()), json={"host": ""}
        )
        assert resp.status_code == 200, resp.text
        assert stored["FortiGateHost"] == ""


class TestTheInputIsValidatedBeforeItIsStored:
    @pytest.mark.parametrize("port", ["abc", 0, 70000, "0", "99999"])
    async def test_a_bad_port_is_a_400_not_a_500(self, client, stored, port):
        resp = client.post(
            "/api/fortigate/save", headers=_hdr(await _token()), json={"port": port}
        )
        assert resp.status_code == 400, resp.text
        assert stored["FortiGatePort"] == 8443

    @pytest.mark.parametrize("port", ["", None])
    async def test_an_empty_port_leaves_the_stored_one_alone(self, client, stored, port):
        """A form serialising every key must not reset the port just because
        the field was blank — that is how a hardened 8443 became 443."""
        resp = client.post(
            "/api/fortigate/save", headers=_hdr(await _token()), json={"port": port}
        )
        assert resp.status_code == 200, resp.text
        assert stored["FortiGatePort"] == 8443

    @pytest.mark.parametrize("host", ["10.0.0.1;reboot", "http://x/y", "a b"])
    async def test_a_host_that_is_not_a_host_is_refused(self, client, stored, host):
        resp = client.post(
            "/api/fortigate/save", headers=_hdr(await _token()), json={"host": host}
        )
        assert resp.status_code == 400, resp.text
        assert stored["FortiGateHost"] == "10.20.0.1", "the bad value was stored anyway"


class TestWhoMayWriteTheseSettings:
    async def test_a_viewer_cannot_save_fortigate_settings(self, client, stored):
        """It stores an API token and repoints the address the customer's own
        credentials are sent to — that is not a read-only operation."""
        resp = client.post(
            "/api/fortigate/save",
            headers=_hdr(await _token(Role.viewer)),
            json={"host": "10.0.0.9", "api_token": "t"},
        )
        assert resp.status_code == 403, resp.text
        assert stored["FortiGateHost"] == "10.20.0.1"

    @pytest.mark.parametrize("path", ["/api/fortigate/save", "/api/unifi/save"])
    async def test_a_technician_without_this_customer_is_refused(
        self, client, stored, path
    ):
        """A stale selection must not survive revocation as write access."""
        resp = client.post(
            path,
            headers=_hdr(await _token(all_customers=False)),
            json={"host": "10.0.0.9"},
        )
        assert resp.status_code == 403, resp.text
        assert stored["FortiGateHost"] == "10.20.0.1"
        assert stored["UniFiHost"] == "unifi.acme.no"


class TestTheChangeIsRecorded:
    async def test_repointing_the_address_is_logged_with_both_values(
        self, client, stored, monkeypatch
    ):
        entries = []
        monkeypatch.setattr(
            "app.core.activity_log.log_activity",
            lambda action, detail="", customer="", user="": entries.append(
                (action, detail, customer, user)
            ),
        )
        resp = client.post(
            "/api/fortigate/save", headers=_hdr(await _token()), json={"host": "10.20.0.9"}
        )
        assert resp.status_code == 200, resp.text
        assert entries, "nothing was recorded"
        action, detail, customer, _ = entries[-1]
        assert action == "fortigate_save"
        assert customer == "acme"
        assert "10.20.0.1" in detail and "10.20.0.9" in detail
