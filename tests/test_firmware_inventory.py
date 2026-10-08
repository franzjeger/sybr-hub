"""Every firmware read leaves its reading behind, and never claims more than it saw.

The FortiGate poller, the UniFi firmware check and the network audit judged
each device's firmware and threw the answer away; Varsler could only show what
the alert engine had sent. These pin the judgement (FortiOS life cycle, the
UniFi table), the store (app/services/firmware_inventory.py) with its one hard
rule, that a device whose read failed is never "current", the readers that
fill it, and the routes that list it.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.models.user import Role
from app.modules.fortigate_audit import firmware_lifecycle
from app.modules.fortigate_audit.firmware_lifecycle import check_fortios
from app.services import firmware_inventory
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)

TODAY = date(2026, 10, 3)
NAMES = {ACME: "Acme AS", BETA: "Beta AS"}


# ── FortiOS: end of life from the table, outdated from FortiGuard ──────────


@pytest.mark.parametrize(
    "version",
    ["v5.6.14", "v6.4.15", "v7.0.17", "v7.2.11"],
)
def test_a_branch_past_end_of_support_is_end_of_life(version):
    # 7.2 reached End of Support on 2026-09-30, three days before TODAY.
    assert check_fortios(version, [], today=TODAY)["status"] == "eol"


def test_a_newer_patch_on_the_same_branch_is_outdated():
    verdict = check_fortios(
        "v7.4.3", [{"version": "v7.4.8"}, {"version": "v7.6.2"}, {"version": "v7.4.5"}], TODAY
    )
    assert verdict["status"] == "outdated"
    assert verdict["latest"] == "7.4.8"


def test_newer_branches_alone_do_not_make_a_device_outdated():
    assert check_fortios("v7.4.8", [{"version": "v7.6.2"}], TODAY)["status"] == "current"


@pytest.mark.parametrize("available", [None, []])
def test_no_list_from_fortiguard_is_not_a_confirmation(available):
    """An unlicensed unit, or one that cannot reach FortiGuard, sends the same
    empty list a unit on the newest release does."""
    verdict = check_fortios("v7.4.8", available, TODAY)
    assert verdict["status"] == "unknown"
    assert verdict["reason"] == "no_firmware_list"


def test_an_unparseable_version_is_unknown():
    assert check_fortios("", [{"version": "v7.4.8"}], TODAY)["reason"] == "version_unparsed"


def test_a_stale_table_does_not_declare_a_branch_dead_whose_date_may_have_moved():
    """7.4's End of Support was extended once already. A table nobody updated
    for two years cannot tell whether its 2028 date still stands."""
    later = date(2029, 1, 1)
    assert firmware_lifecycle.is_stale(later)
    verdict = check_fortios("v7.4.8", [], later)
    assert verdict["status"] == "unknown" and verdict["reason"] == "table_stale"
    # A date that had passed when the table was written stays durable.
    assert check_fortios("v7.0.1", [], later)["status"] == "eol"


# ── UniFi: the firmware table, and the controller's own offer ──────────────


def test_unifi_readings_follow_the_table():
    eol = firmware_inventory.unifi_reading(key="a", name="AP", model="UAP-LR", version="4.3.28")
    assert eol["status"] == "eol"
    unknown_model = firmware_inventory.unifi_reading(
        key="b", name="X", model="NOT-A-MODEL", version="1.0.0"
    )
    assert unknown_model["status"] == "unknown" and unknown_model["reason"] == "model_unknown"
    missing = firmware_inventory.unifi_reading(key="c", name="Y", model="U6-Pro", version="")
    assert missing["status"] == "unknown"


def test_the_controller_offering_an_upgrade_means_outdated():
    reading = firmware_inventory.unifi_reading(
        key="d", name="Z", model="NOT-A-MODEL", version="1.0.0", upgrade_to="1.2.0"
    )
    assert reading["status"] == "outdated" and reading["latest"] == "1.2.0"


# ── The store ───────────────────────────────────────────────────────────────


def _current(key: str, name: str) -> dict:
    return {
        "key": key,
        "name": name,
        "model": "FGT60F",
        "version": "v7.4.8",
        "status": "current",
        "reason": "",
        "latest": "",
        "source": "test",
    }


async def _rows(customer_id: str = ACME) -> dict[str, dict]:
    devices = await firmware_inventory.list_devices(None, customer_id, names=NAMES)
    return {d["device_key"]: d for d in devices}


async def test_a_device_whose_read_failed_is_never_current():
    await firmware_inventory.record(
        ACME,
        "unifi",
        [
            _current("ok-ap", "AP 1"),
            firmware_inventory.unifi_reading(
                key="old-ap", name="AP 2", model="UAP-LR", version="4.3.28"
            ),
        ],
    )
    await firmware_inventory.record_read_failure(ACME, "unifi", "HTTP 403", key="controller")

    rows = await _rows()
    assert rows["ok-ap"]["status"] == "unknown", "an unread device must not stay current"
    assert rows["ok-ap"]["version"] == "v7.4.8", "the last version seen is kept"
    assert rows["ok-ap"]["read_error"] == "HTTP 403"
    # End of life is a property of the model; it does not lapse with one failed read.
    assert rows["old-ap"]["status"] == "eol"
    assert rows["old-ap"]["read_error"] == "HTTP 403"
    assert "controller" not in rows


async def test_a_controller_never_read_shows_as_one_unknown_row_until_it_answers():
    await firmware_inventory.record_read_failure(
        ACME, "unifi", "login refused", key="controller", name="ctrl.acme.example"
    )
    rows = await _rows()
    assert list(rows) == ["controller"]
    assert rows["controller"]["status"] == "unknown"
    assert rows["controller"]["read_at"] is None

    await firmware_inventory.record(ACME, "unifi", [_current("ap-1", "AP 1")])
    assert list(await _rows()) == ["ap-1"], "a complete read replaces the placeholder"


async def test_a_device_gone_from_a_complete_read_is_dropped():
    await firmware_inventory.record(ACME, "unifi", [_current("a", "A"), _current("b", "B")])
    await firmware_inventory.record(ACME, "unifi", [_current("a", "A")])
    assert set(await _rows()) == {"a"}


async def test_one_unreachable_direct_device_is_unknown_and_the_rest_are_read():
    await firmware_inventory.record(ACME, "unifi", [_current("a", "A"), _current("b", "B")])
    await firmware_inventory.record(
        ACME,
        "unifi",
        [_current("a", "A"), firmware_inventory.unread(key="b", name="B", error="timed out")],
    )
    rows = await _rows()
    assert rows["a"]["status"] == "current"
    assert rows["b"]["status"] == "unknown"


async def test_automatic_firmware_alerts_match_the_stored_attention_list(monkeypatch):
    from app.services.alert_engine import (
        _alert_fingerprint,
        _check_firmware_outdated,
        render_detail,
    )

    monkeypatch.setattr(firmware_inventory, "_customer_names", lambda: NAMES)

    def no_poll(*args, **kwargs):
        raise AssertionError("the alert must use stored readings, not poll the fleet")

    monkeypatch.setattr("app.services.fortigate_api.poll_all_fortigates", no_poll)
    await firmware_inventory.record(
        ACME,
        "fortigate",
        [
            {**_current("old", "Firewall"), "version": "v7.2.11", "status": "eol"},
            {
                **_current("patch", "Firewall"),
                "version": "v7.4.3",
                "status": "outdated",
                "latest": "7.4.8",
            },
            _current("ok", "Current firewall"),
            {**_current("unread", "Unread firewall"), "status": "unknown"},
        ],
    )
    await firmware_inventory.record_read_failure(ACME, "fortigate", "HTTP 403", key="controller")
    await firmware_inventory.record(
        BETA,
        "unifi",
        [{**_current("ap", "AP"), "status": "outdated", "latest": "6.7.0"}],
    )
    await firmware_inventory.record(
        "deleted-customer", "fortigate", [{**_current("gone", "Gone"), "status": "eol"}]
    )

    attention = await firmware_inventory.attention(None)
    alerts = await _check_firmware_outdated()

    assert len(alerts) == len(attention) == 3
    assert [a["severity"] for a in alerts] == [d["category"] for d in attention]
    assert [a["customer"] for a in alerts] == [d["customer_name"] for d in attention]
    assert alerts[0]["detail_key"] == "alert_detail_firmware_eol"
    assert "end of support" in render_detail(alerts[0], "en")
    assert "7.4.8" in render_detail(alerts[1], "no")
    assert "7.4 or newer" not in render_detail(alerts[1], "en")
    assert len({_alert_fingerprint(a) for a in alerts}) == 3


async def test_an_unreadable_firmware_store_reports_a_failed_check(monkeypatch):
    from app.services.alert_engine import AlertCheckFailed, _check_firmware_outdated

    async def broken(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(firmware_inventory, "attention", broken)
    with pytest.raises(AlertCheckFailed) as exc:
        await _check_firmware_outdated()
    assert exc.value.check == "firmware_outdated"


# ── The readers fill it ─────────────────────────────────────────────────────


def _fg_client(handler):
    from app.modules.fortigate_audit.client import FortiGateClient

    fg = FortiGateClient("192.0.2.10", api_token="t", verify_ssl=False)
    fg._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=fg.base_url, headers=fg._client.headers
    )
    return fg


@pytest.fixture()
def acme_fortigate(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(
            lambda: [{"_id": ACME, "CustomerName": "Acme AS", "FortiGateHost": "fw.acme.example"}]
        ),
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, key: "token")

    def _install(handler):
        monkeypatch.setattr(
            "app.services.fortigate_api._build_client", lambda config, token: _fg_client(handler)
        )

    return _install


async def test_the_fleet_poll_stores_each_firewalls_firmware(acme_fortigate):
    from app.services.fortigate_api import poll_all_fortigates

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1", "model": "FGT60F"}})
        if path.endswith("system/firmware"):
            return httpx.Response(
                200,
                json={
                    "results": {
                        "current": {"version": "v7.4.3"},
                        "available": [{"version": "v7.4.8"}],
                    }
                },
            )
        return httpx.Response(200, json={"results": []})

    acme_fortigate(handler)
    await poll_all_fortigates()

    row = (await _rows())["fw.acme.example"]
    assert row["vendor"] == "fortigate"
    assert (row["status"], row["version"], row["latest"]) == ("outdated", "v7.4.3", "7.4.8")
    assert row["device_name"] == "fw1"


async def test_an_unreachable_firewall_is_stored_as_unknown(acme_fortigate):
    from app.services.fortigate_api import poll_all_fortigates

    acme_fortigate(lambda request: httpx.Response(403, text="nope"))
    await poll_all_fortigates()

    row = (await _rows())["fw.acme.example"]
    assert row["status"] == "unknown"
    assert row["read_error"]


async def test_a_failed_read_after_the_address_changed_is_kept_under_the_new_one():
    """It landed on the old address's row: the configured firewall showed as
    never read, so Nettverk's first read would read it on every visit, and the
    old address stayed in Varsler."""
    await firmware_inventory.record(
        ACME, "fortigate", [{**_current("fw-old.acme.example", "FW"), "status": "eol"}]
    )
    await firmware_inventory.record_fortigate_poll(
        [
            {
                "customer_id": ACME,
                "host": "FW-New.acme.example",
                "status": "error",
                "error": "timed out",
            }
        ]
    )
    rows = await _rows()
    assert list(rows) == ["fw-new.acme.example"]
    assert rows["fw-new.acme.example"]["read_error"] == "timed out"
    assert rows["fw-new.acme.example"]["read_at"] is None


async def test_the_unifi_firmware_check_stores_what_it_judged(monkeypatch):
    from app.modules.unifi_audit.client import UniFiControllerClient
    from app.services.unifi_api import firmware_check_all

    devices = [
        {"mac": "02:00:00:00:00:01", "name": "Lager", "model": "UAP-LR", "version": "4.3.28"},
        {"mac": "02:00:00:00:00:02", "name": "Kontor", "model": "NOT-A-MODEL", "version": "1.0"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": devices, "meta": {"rc": "ok"}})

    class _Controller(UniFiControllerClient):
        def __init__(self):
            super().__init__("https://ctrl", "u", "p")
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.host
            )
            self._logged_in = True

    async def _controller(customer_id):
        return _Controller()

    monkeypatch.setattr("app.services.unifi_api._controller_for_customer", _controller)
    monkeypatch.setattr("app.services.unifi_api._default_site", lambda cid: "default")

    await firmware_check_all(ACME)

    rows = await _rows()
    assert rows["02:00:00:00:00:01"]["status"] == "eol"
    assert rows["02:00:00:00:00:02"]["status"] == "unknown"


async def test_a_refused_unifi_login_is_stored_as_unread(monkeypatch):
    from app.services.unifi_api import firmware_check_all

    async def _refused(customer_id):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr("app.services.unifi_api._controller_for_customer", _refused)
    with pytest.raises(httpx.ConnectError):
        await firmware_check_all(ACME)
    assert (await _rows())["controller"]["status"] == "unknown"


@pytest.mark.parametrize("model_in_lts", [False, True])
async def test_the_network_audit_stores_the_controllers_devices(monkeypatch, model_in_lts):
    """The site collector runs this over VPN, so it is how a customer the hub
    cannot reach directly gets a firmware reading at all."""
    import app.modules.unifi_audit.client as client_mod
    from app.modules.unifi_audit.client import UniFiControllerClient
    from app.services.network_audit import _audit_unifi_controller

    devices = [
        {
            "mac": "02:00:00:00:00:09",
            "name": "Lager",
            "model": "UAP-LR",
            "version": "4.3.28",
            "model_in_lts": model_in_lts,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": devices, "meta": {"rc": "ok"}})

    class _Controller(UniFiControllerClient):
        def __init__(self, *a, **k):
            super().__init__("https://ctrl", "u", "p")
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url=self.host
            )

        async def _login(self):
            self._logged_in = True

    monkeypatch.setattr(client_mod, "UniFiControllerClient", _Controller)
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, k: "x")

    result = await _audit_unifi_controller(ACME, {"UniFiHost": "https://ctrl"})

    assert result["eol_count"] == 1
    assert (await _rows())["02:00:00:00:00:09"]["status"] == "eol"


async def test_the_quick_network_audit_stores_the_firewalls_firmware(acme_fortigate):
    from app.services.network_audit import run_quick_network_audit

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("system/status"):
            return httpx.Response(200, json={"results": {"hostname": "fw1", "model": "FGT60F"}})
        if path.endswith("system/firmware"):
            return httpx.Response(
                200,
                json={"results": {"current": {"version": "v7.0.15"}, "available": []}},
            )
        return httpx.Response(200, json={"results": []})

    acme_fortigate(handler)
    result = await run_quick_network_audit({"FortiGateHost": "fw.acme.example"}, ACME)

    assert result["fortigate"]["firmware"] == "v7.0.15", "read from system/firmware"
    row = (await _rows())["fw.acme.example"]
    assert (row["status"], row["version"]) == ("eol", "v7.0.15")


# ── The routes ──────────────────────────────────────────────────────────────


async def test_the_list_is_scoped_to_the_callers_customers(client):
    await firmware_inventory.record(ACME, "unifi", [_current("acme-ap", "Acme AP")])
    await firmware_inventory.record(BETA, "unifi", [_current("beta-ap", "Beta AP")])

    scoped = await login("tech-acme", customers=(ACME,))
    r = client.get("/api/firmware/devices", headers=scoped)
    assert r.status_code == 200, r.text
    assert [d["device_key"] for d in r.json()["devices"]] == ["acme-ap"]
    assert r.json()["summary"]["current"] == 1
    assert_no_foreign(r.text)
    assert client.get(f"/api/firmware/devices/{BETA}", headers=scoped).status_code == 403
    own = client.get(f"/api/firmware/devices/{ACME}", headers=scoped).json()
    assert own["devices"][0]["customer_name"] == "Acme AS"


async def test_a_viewer_does_not_reach_the_firmware_list(client):
    headers = await login("viewer", role=Role.viewer, all_customers=True)
    assert client.get("/api/firmware/devices", headers=headers).status_code == 403


async def test_the_daily_firmware_check_reads_fortigates_and_controllers(monkeypatch):
    from app.services import scheduler

    polled: list[str] = []
    checked: list[str] = []

    async def _poll(customer_ids=None):
        polled.append("all")
        return [{"customer_id": ACME, "status": "online"}]

    async def _check(customer_id):
        checked.append(customer_id)
        return {"devices": [], "total": 0}

    monkeypatch.setattr("app.services.fortigate_api.poll_all_fortigates", _poll)
    monkeypatch.setattr("app.services.unifi_api.firmware_check_all", _check)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(
            lambda: [
                {"_id": ACME, "UniFiHost": "ctrl.acme.example"},
                {"_id": BETA, "UniFiHost": "ap.beta.example", "UniFiMode": "direct"},
            ]
        ),
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, key: "x")

    result = await scheduler._do_firmware_check()

    assert polled == ["all"]
    assert checked == [ACME], "direct-mode customers are left to the network audit"
    assert result.startswith("1 FortiGate(s), 1 UniFi controller(s) read")
