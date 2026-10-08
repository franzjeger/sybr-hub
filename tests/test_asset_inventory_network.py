"""The asset inventory lists the network devices the hub has read.

/dashboard/assets imported ``_poller`` from a routes module that never had
one. The ImportError was caught and logged at debug, so the inventory always
said zero network devices, however many firewalls and access points the hub
had read. It now lists the stored readings (device_firmware), which the daily
firmware check keeps for every FortiGate and UniFi controller the hub reaches
and which survive a restart, unlike the dashboard poller's in-memory cache.

Zero devices and "could not read them" are different answers: the second is
logged as an error and said in the response (count None, ``unavailable``),
never shown as an empty list.
"""

from __future__ import annotations

import logging

from app.models.user import Role
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


async def _read_devices():
    await firmware_inventory.record(
        ACME,
        "fortigate",
        [
            firmware_inventory.fortigate_reading(
                key="FGT60F0000000001",
                name="fw-acme",
                model="FortiGate-60F",
                version="v7.4.8",
                available=[],
            )
        ],
    )
    await firmware_inventory.record(
        ACME,
        "unifi",
        [
            firmware_inventory.unifi_reading(
                key="aa:bb:cc:00:00:01", name="ap-acme", model="U7PG2", version="6.8.2"
            )
        ],
    )
    await firmware_inventory.record(
        BETA,
        "unifi",
        [
            firmware_inventory.unifi_reading(
                key="aa:bb:cc:00:00:02", name="sw-beta", model="USL24P", version="7.5.15"
            )
        ],
    )


async def test_the_inventory_lists_the_devices_the_hub_has_read(client):
    await _read_devices()
    headers = await login("boss", role=Role.admin)

    body = client.get("/api/dashboard/assets", headers=headers).json()

    devices = {d["name"]: d for d in body["assets"]["network_devices"]}
    assert set(devices) == {"fw-acme", "ap-acme", "sw-beta"}
    assert body["counts"]["network"] == 3
    assert body["unavailable"] == []
    ap = devices["ap-acme"]
    assert (ap["vendor"], ap["model"], ap["firmware"]) == ("unifi", "UAP-AC-Pro", "6.8.2")
    assert ap["customer_id"] == ACME and ap["customer_name"] == "Acme AS"
    assert devices["fw-acme"]["device_key"] == "fgt60f0000000001"


async def test_a_scoped_caller_sees_only_its_customers_devices(client):
    await _read_devices()
    headers = await login("viewer-acme", role=Role.viewer, customers=(ACME,), write=False)

    r = client.get("/api/dashboard/assets", headers=headers)

    assert {d["name"] for d in r.json()["assets"]["network_devices"]} == {"fw-acme", "ap-acme"}
    assert_no_foreign(r.text)


async def test_no_device_read_yet_is_an_empty_list_not_a_failure(client):
    headers = await login("boss", role=Role.admin)

    body = client.get("/api/dashboard/assets", headers=headers).json()

    assert body["assets"]["network_devices"] == []
    assert body["counts"]["network"] == 0
    assert body["unavailable"] == []


async def test_a_store_that_cannot_be_read_is_said_and_logged(client, monkeypatch, caplog):
    async def _broken(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(firmware_inventory, "list_devices", _broken)
    headers = await login("boss", role=Role.admin)

    with caplog.at_level(logging.ERROR, logger="app.web.routes.dashboard_infra"):
        body = client.get("/api/dashboard/assets", headers=headers).json()

    assert body["assets"]["network_devices"] == []
    assert body["counts"]["network"] is None  # not 0: nothing was counted
    assert body["unavailable"] == ["network_devices"]
    assert any("stored device readings" in r.getMessage() for r in caplog.records)
    # The rest of the inventory still answers.
    assert body["counts"]["customers"] == 2
