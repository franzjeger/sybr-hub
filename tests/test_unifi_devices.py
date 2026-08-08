"""Every device is listed, especially the ones that are down.

``result.append`` sat inside ``if startup:``, so a device with no
``startupTime`` never reached the list. A device has no startupTime precisely
because it is not running — so the filter dropped exactly the devices a
technician is looking for. Five of 260 in a live account, all of them offline,
while the sort immediately below promised "offline first".
"""

from __future__ import annotations

from app.services.unifi_api import summarise_devices


def _host(devices, host_id="host-1", host_name="Kontoret"):
    return {"hostId": host_id, "hostName": host_name, "devices": devices}


def _device(**overrides):
    device = {
        "id": "d1",
        "name": "Switch",
        "shortname": "USW24",
        "model": "USW-24-PoE",
        "mac": "00:00:5e:00:53:00",
        "ip": "198.51.100.10",
        "status": "online",
        "version": "7.0.50",
        "firmwareStatus": "upToDate",
        "updateAvailable": "",
        "startupTime": "2026-08-01T00:00:00Z",
        "isConsole": False,
        "isManaged": True,
        "productLine": "network",
    }
    device.update(overrides)
    return device


def test_a_device_without_a_startup_time_is_still_listed():
    rows = summarise_devices([_host([_device(status="offline", startupTime="")])])
    assert len(rows) == 1
    assert rows[0]["status"] == "offline"
    assert rows[0]["uptime"] == ""


def test_offline_devices_sort_before_online_ones():
    rows = summarise_devices([_host([
        _device(id="up", name="A-online"),
        _device(id="down", name="Z-offline", status="offline", startupTime=""),
    ])])
    assert [r["id"] for r in rows] == ["down", "up"]


def test_firmware_waiting_outranks_a_healthy_device():
    rows = summarise_devices([_host([
        _device(id="ok", name="A"),
        _device(id="pending", name="Z", firmwareStatus="updateAvailable"),
    ])])
    assert [r["id"] for r in rows] == ["pending", "ok"]


def test_firmware_status_is_carried_even_though_update_available_is_empty():
    # Live accounts return updateAvailable="" on every device, including the
    # ones with an update waiting. Reading it as "the version on offer" shows
    # nothing; firmwareStatus is the field with the signal.
    [row] = summarise_devices([_host([_device(firmwareStatus="updateAvailable")])])
    assert row["firmware_status"] == "updateAvailable"
    assert row["update_available"] == ""


def test_devices_from_several_hosts_are_flattened_with_their_host():
    rows = summarise_devices([
        _host([_device(id="a", name="A")], host_id="h1", host_name="Alfa"),
        _host([_device(id="b", name="B")], host_id="h2", host_name="Beta"),
    ])
    assert {(r["id"], r["host_name"]) for r in rows} == {("a", "Alfa"), ("b", "Beta")}


def test_an_unparseable_startup_time_does_not_lose_the_device():
    [row] = summarise_devices([_host([_device(startupTime="not-a-timestamp")])])
    assert row["uptime"] == ""
    assert row["id"] == "d1"


def test_a_host_with_no_devices_contributes_nothing():
    assert summarise_devices([_host([]), {"hostId": "h", "hostName": "n"}]) == []
