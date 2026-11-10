"""UniFi devices nobody reached are not a clean UniFi audit.

In direct mode each access point is read over HTTP and SSH. When none of them
answered, the summary still came back in the shape of a completed audit: zero
default passwords, zero outdated firmware, zero end-of-life devices, no error.
The risk score, the recommendations and the stored metrics all read that as a
verified clean network. The controller path already refuses to say so.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.reports.risk import _network_penalty
from app.services import network_audit


class _Device:
    """Stands in for UniFiDirectDevice; answers per host from ``ANSWERS``."""

    ANSWERS: ClassVar[dict[str, tuple[dict, dict]]] = {}

    def __init__(self, host, **_kwargs):
        self.host = host

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_device_info_http(self):
        return self.ANSWERS[self.host][0]

    async def get_device_info_ssh(self):
        return self.ANSWERS[self.host][1]


@pytest.fixture(autouse=True)
def _rig(monkeypatch):
    async def _quiet(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.modules.unifi_audit.client.UniFiDirectDevice", _Device)
    monkeypatch.setattr("app.core.credentials.get_secret", lambda *_a, **_k: "x")
    monkeypatch.setattr("app.services.firmware_inventory.record_quietly", _quiet)


DEVICES = [{"host": "10.0.0.11", "label": "AP 1"}, {"host": "10.0.0.12", "label": "AP 2"}]
DOWN = ({"error": "connect timeout"}, {"error": "connect timeout"})
UP_WITH_DEFAULT_PASSWORD = (
    {"model": "U6-Lite", "version": "6.6.77"},
    {"model": "U6-Lite", "firmware": "6.6.77", "default_credentials": True},
)


async def test_no_device_answering_is_unavailable_not_clean():
    _Device.ANSWERS = {"10.0.0.11": DOWN, "10.0.0.12": DOWN}

    result = await network_audit._audit_unifi_direct("acme", DEVICES)

    assert result["unavailable"] is True
    assert "connect timeout" in result["error"]
    assert result["reachable"] == 0
    # Not zero: nobody looked.
    assert result["default_creds_count"] is None
    assert result["outdated_firmware_count"] is None
    assert result["eol_count"] is None
    # The devices that were tried are still named.
    assert [d["host"] for d in result["devices"]] == ["10.0.0.11", "10.0.0.12"]


async def test_one_device_answering_is_still_an_audit():
    _Device.ANSWERS = {"10.0.0.11": DOWN, "10.0.0.12": UP_WITH_DEFAULT_PASSWORD}

    result = await network_audit._audit_unifi_direct("acme", DEVICES)

    assert "error" not in result
    assert result["reachable"] == 1
    assert result["device_count"] == 2
    assert result["default_creds_count"] == 1
    assert _network_penalty({"unifi": result}) > 0
