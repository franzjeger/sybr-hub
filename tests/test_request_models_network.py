"""Request models on the FortiGate and UniFi routers.

These bodies decide where a customer's stored device credentials travel. A
number where a host or token was expected used to reach ``.strip()`` or
``str()`` and either answer 500 or be stored as text; a misspelt key was
dropped, so the setting it carried simply never changed.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
    tech_client,
)


class _FakeFortiGate:
    opened: ClassVar[list[str]] = []

    def __init__(self, host, token, **kwargs):
        _FakeFortiGate.opened.append(host)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def test_connection(self):
        return {"ok": True, "hostname": "fg01"}


@pytest.fixture()
def fake_fortigate(monkeypatch):
    _FakeFortiGate.opened = []
    monkeypatch.setattr("app.modules.fortigate_audit.client.FortiGateClient", _FakeFortiGate)


def _active_customer(client) -> str:
    """Register Customer A; the routes below name it in their path."""
    from app.core.customer import CustomerManager

    return CustomerManager.save_customer({"CustomerName": "Customer A", "TenantId": "a"})


CID = "Customer_A"


# ── FortiGate ────────────────────────────────────────────────────────────────

# What app-network.js testFortiGate()/saveFortiGate() send.
FG_FORM = {
    "host": "10.20.0.1",
    "port": 8443,
    "api_token": "token-value",
    "vdom": "root",
    "verify_ssl": False,
}


async def test_the_fortigate_test_form_still_works(tech_client, fake_fortigate):
    r = tech_client.post("/api/fortigate/test", json=FG_FORM)

    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert _FakeFortiGate.opened == ["10.20.0.1"]


@pytest.mark.parametrize(
    "over", [{"host": 10}, {"api_token": ["t"]}, {"verify_ssl": "perhaps"}, {"token": "t"}]
)
async def test_a_bad_fortigate_test_body_is_refused_before_any_connection(
    tech_client, fake_fortigate, over
):
    assert_refused(tech_client.post("/api/fortigate/test", json={**FG_FORM, **over}), 422)
    assert _FakeFortiGate.opened == []


async def test_the_fortigate_save_form_still_saves(tech_client):
    from app.core.credentials import get_secret
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)

    r = tech_client.post(f"/api/fortigate/save/{CID}", json=FG_FORM)

    assert r.status_code == 200, r.text
    stored = CustomerManager.get_customer(cid)
    assert stored["FortiGateHost"] == "10.20.0.1"
    assert stored["FortiGatePort"] == 8443
    assert stored["FortiGateVerifySSL"] is False
    assert get_secret(cid, "fortigate_api_token") == "token-value"


async def test_a_null_port_from_the_form_still_leaves_the_port_alone(tech_client):
    """parseInt('') is NaN, which JSON.stringify sends as null."""
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)
    tech_client.post(f"/api/fortigate/save/{CID}", json=FG_FORM)

    r = tech_client.post(f"/api/fortigate/save/{CID}", json={**FG_FORM, "port": None})

    assert r.status_code == 200, r.text
    assert CustomerManager.get_customer(cid)["FortiGatePort"] == 8443


@pytest.mark.parametrize("over", [{"host": 10}, {"port": [443]}, {"vdom": 1}, {"hostname": "x"}])
async def test_a_bad_fortigate_save_body_changes_nothing(tech_client, over):
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)

    assert_refused(tech_client.post(f"/api/fortigate/save/{CID}", json={**FG_FORM, **over}), 422)
    assert "FortiGateHost" not in CustomerManager.get_customer(cid)


async def test_a_bad_fortigate_port_keeps_its_own_message(tech_client):
    _active_customer(tech_client)

    body = assert_refused(
        tech_client.post(f"/api/fortigate/save/{CID}", json={**FG_FORM, "port": "https"}), 400
    )
    assert "Ugyldig port" in body["error"]


async def test_deploy_key_and_generate_token_keep_their_required_field_messages(admin_client):
    cid = _active_customer(admin_client)

    body = assert_refused(admin_client.post(f"/api/fortigate/deploy-key/{cid}", json={}), 400)
    assert "admin_user" in body["error"]
    body = assert_refused(admin_client.post(f"/api/fortigate/generate-token/{cid}", json={}), 400)
    assert "ssh_host" in body["error"]


async def test_deploy_key_and_generate_token_refuse_a_wrong_type(admin_client):
    cid = _active_customer(admin_client)

    for path, body in (
        (f"/api/fortigate/deploy-key/{cid}", {"admin_user": 1, "public_key": "k"}),
        (f"/api/fortigate/deploy-key/{cid}", {"admin_user": "a", "key": "k"}),
        # int("ssh") used to be a 500 here.
        (f"/api/fortigate/generate-token/{cid}", {"ssh_host": "h", "ssh_port": "ssh"}),
        (f"/api/fortigate/generate-token/{cid}", {"ssh_host": "h", "accprofile": ["x"]}),
    ):
        assert_refused(admin_client.post(path, json=body), 422)


async def test_bootstrap_keeps_its_messages_and_refuses_a_wrong_type(tech_client):
    body = assert_refused(tech_client.post("/api/fortigate/bootstrap", json={"host": ""}), 400)
    assert "host" in body["error"]
    body = assert_refused(
        tech_client.post("/api/fortigate/bootstrap", json={"host": "10.0.0.1", "ssh_port": "x"}),
        400,
    )
    assert "ssh_port" in body["error"]
    assert_refused(tech_client.post("/api/fortigate/bootstrap", json={"host": 10}), 422)
    assert_refused(
        tech_client.post("/api/fortigate/bootstrap", json={"host": "10.0.0.1", "password": ""}),
        422,
    )


# ── UniFi ────────────────────────────────────────────────────────────────────


class _FakeDevice:
    calls: ClassVar[list[tuple]] = []

    def __init__(self, host, username, password, **kwargs):
        _FakeDevice.calls.append((host, username, password, kwargs.get("device_type")))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def test_connection(self):
        return {"ok": True}

    async def reboot(self):
        return {"ok": True}

    async def get_config_dump(self):
        return {"ok": True, "config": "..."}

    async def set_inform(self, url):
        return {"ok": True, "output": url}


@pytest.fixture()
def fake_device(monkeypatch):
    _FakeDevice.calls = []
    monkeypatch.setattr("app.modules.unifi_audit.client.UniFiDirectDevice", _FakeDevice)


async def test_device_actions_still_take_what_the_spa_sends(tech_client, fake_device):
    creds = {"host": "10.0.0.5", "username": "admin", "password": "pw"}

    for path, extra in (
        ("/api/unifi/reboot-device", {}),
        ("/api/unifi/device-config", {}),
        ("/api/unifi/set-inform", {"controller_url": "http://10.0.0.1:8080/inform"}),
    ):
        r = tech_client.post(path, json={**creds, **extra})
        assert r.status_code == 200, (path, r.text)
    # testUniFiDevice() sends each entry's ``type``, which may be missing.
    r = tech_client.post("/api/unifi/test-device", json={"host": "10.0.0.5"})
    assert r.status_code == 200, r.text
    assert _FakeDevice.calls[-1] == ("10.0.0.5", "ubnt", "ubnt", "ap")


@pytest.mark.parametrize(
    "path",
    [
        "/api/unifi/test-device",
        "/api/unifi/reboot-device",
        "/api/unifi/device-config",
        "/api/unifi/set-inform",
    ],
)
async def test_a_bad_device_body_is_refused_before_any_connection(tech_client, fake_device, path):
    for body in ({"host": 5}, {"host": "10.0.0.5", "password": None}, {"ip": "10.0.0.5"}):
        assert_refused(tech_client.post(path, json=body), 422)
    assert _FakeDevice.calls == []


async def test_a_missing_device_host_keeps_its_own_message(tech_client, fake_device):
    body = assert_refused(tech_client.post("/api/unifi/reboot-device", json={}), 400)
    assert "Host" in body["error"]


async def test_a_network_scan_refuses_a_concurrency_that_would_hang(tech_client):
    """Semaphore(0) waited forever; a negative value was a 500."""
    for value in (0, -1, "many"):
        assert_refused(
            tech_client.post(
                "/api/network/scan", json={"subnet": "10.0.0.0/30", "max_concurrent": value}
            ),
            422,
        )
    body = assert_refused(tech_client.post("/api/network/scan", json={"subnet": " "}), 400)
    assert "Subnet" in body["error"]


async def test_a_config_backup_must_be_text(tech_client):
    _active_customer(tech_client)

    r = tech_client.post(
        f"/api/network/save-config-backup/{CID}", json={"host": "10.0.0.5", "config": "set x"}
    )
    assert r.status_code == 200, r.text
    assert_refused(
        tech_client.post(
            f"/api/network/save-config-backup/{CID}", json={"host": "10.0.0.5", "config": {"x": 1}}
        ),
        422,
    )


async def test_the_unifi_save_forms_still_save(tech_client):
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)
    # saveUniFi(), then saveUniFiDirect()
    r = tech_client.post(
        f"/api/unifi/save/{CID}",
        json={
            "host": "unifi.customer-a.example",
            "username": "admin",
            "password": "pw",
            "site": "default",
            "is_unifi_os": True,
        },
    )
    assert r.status_code == 200, r.text
    r = tech_client.post(
        f"/api/unifi/save/{CID}",
        json={"mode": "direct", "devices": [{"host": "10.0.0.5", "label": "AP", "type": None}]},
    )
    assert r.status_code == 200, r.text

    stored = CustomerManager.get_customer(cid)
    assert stored["UniFiHost"] == "unifi.customer-a.example"
    assert stored["UniFiMode"] == "direct"
    assert stored["UniFiDirectDevices"] == [{"host": "10.0.0.5", "label": "AP", "type": None}]


@pytest.mark.parametrize(
    "body",
    [
        {"host": 5},
        {"devices": "10.0.0.5"},
        {"devices": ["10.0.0.5"]},
        {"is_unifi_os": "sometimes"},
        {"controller": "x"},
    ],
)
async def test_a_bad_unifi_save_body_changes_nothing(tech_client, body):
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)

    assert_refused(tech_client.post(f"/api/unifi/save/{CID}", json=body), 422)
    assert "UniFiHost" not in CustomerManager.get_customer(cid)


async def test_site_manager_sign_in_keeps_its_messages(tech_client):
    body = assert_refused(tech_client.post("/api/unifi/site-manager/auth", json={}), 400)
    assert "API-nøkkel" in body["error"]
    body = assert_refused(tech_client.post("/api/unifi/site-manager/verify-2fa", json={}), 400)
    assert "2FA" in body["error"]
    for path, bad in (
        ("/api/unifi/site-manager/auth", {"api_key": 123}),
        ("/api/unifi/site-manager/auth", {"apikey": "k"}),
        ("/api/unifi/site-manager/verify-2fa", {"session_token": "s", "code": 123456}),
    ):
        assert_refused(tech_client.post(path, json=bad), 422)


async def test_site_matches_accept_the_proposals_as_they_came(tech_client):
    """Only the two ids are read; the names and score beside them are ignored."""
    from app.core.customer import CustomerManager

    cid = _active_customer(tech_client)
    proposal = {
        "host_id": "host-1",
        "host_name": "Customer A HQ",
        "customer_id": cid,
        "customer_name": "Customer A",
        "score": 0.93,
        "confidence": "high",
    }

    r = tech_client.post("/api/unifi/site-matches/apply", json={"matches": [proposal]})

    assert r.status_code == 200, r.text
    assert CustomerManager.get_customer(cid)["UniFiHostId"] == "host-1"
    body = assert_refused(tech_client.post("/api/unifi/site-matches/apply", json={}), 400)
    assert "koblinger" in body["error"]
    for bad in ({"matches": "host-1"}, {"matches": [{"host_id": 1}]}, {"pairs": []}):
        assert_refused(tech_client.post("/api/unifi/site-matches/apply", json=bad), 422)


# ── TLS and DNS checks ───────────────────────────────────────────────────────


async def test_tls_and_dns_checks_keep_their_messages(tech_client):
    for path, body, message in (
        ("/api/tls/check", {"host": "", "port": 443}, "Host er påkrevd"),
        ("/api/tls/scan", {"endpoints": []}, "Ingen endepunkter oppgitt"),
        ("/api/dns/check", {"domain": " "}, "Domene er påkrevd"),
        ("/api/dns/check-bulk", {"domains": []}, "Ingen domener oppgitt"),
    ):
        assert assert_refused(tech_client.post(path, json=body), 400)["error"] == message


async def test_a_tls_scan_takes_the_discovered_endpoints_as_they_came(tech_client, monkeypatch):
    """tlsScanAll() sends GET /tls/auto-discover's list straight back."""
    seen = []

    async def _scan(endpoints):
        seen.extend(endpoints)
        return {"results": []}

    monkeypatch.setattr("app.web.routes.tls.scan_customer_endpoints", _scan)
    discovered = {"host": "fw.example", "port": 8443, "label": "FW", "source": "fortigate"}

    r = tech_client.post("/api/tls/scan", json={"endpoints": [discovered]})

    assert r.status_code == 200, r.text
    assert seen == [discovered]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/tls/check", {"host": "a.example", "port": "https"}),
        ("/api/tls/check", {"hostname": "a.example"}),
        ("/api/tls/scan", {"endpoints": ["a.example"]}),
        ("/api/tls/scan", {"endpoints": [{"host": "a.example", "sni": "x"}]}),
        ("/api/dns/check", {"domain": 5}),
        ("/api/dns/check-bulk", {"domains": "a.example"}),
    ],
)
async def test_a_malformed_tls_or_dns_check_is_a_422(tech_client, path, body):
    assert_refused(tech_client.post(path, json=body), 422)
