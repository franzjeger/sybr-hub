"""A controller that stops answering must not leave healthy device rows behind.

The dashboard poller writes one cache row per UniFi device on a good poll
(``uf_{cid}_{mac}``) and a single controller-error row (``uf_{cid}_ctrl``) on a
refused one. Those use different ids, so without an explicit eviction the
device rows from the last good poll survive — the dashboard keeps showing every
device "online" for a controller that is now refusing every read. This is the
same "a refusal is not a zero" defect, one layer up: a refusal must not read as
"still healthy". These pin the eviction in both directions.
"""

from __future__ import annotations

import pytest

from app.modules.api_result import ApiList
from app.services.dashboard_poller import DashboardPoller, DeviceStatus

pytestmark = pytest.mark.asyncio


def _online_row(cid: str, mac: str) -> DeviceStatus:
    return DeviceStatus(
        device_id=f"uf_{cid}_{mac}", customer_id=cid, vendor="unifi",
        name="AP1", model="U6-Pro", firmware="6.0", serial=mac,
        status="online", uptime="1d", last_poll="t0",
    )


class _FakeCtrl:
    """A UniFi controller client whose device read yields *result*."""

    is_unifi_os = False

    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_devices(self, site):
        return self._result


def _install(monkeypatch, result):
    monkeypatch.setattr(
        "app.modules.unifi_audit.client.UniFiControllerClient",
        lambda *a, **k: _FakeCtrl(result),
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, k: "x")


async def test_a_refused_poll_evicts_the_prior_online_device_rows(monkeypatch):
    poller = DashboardPoller()
    poller._cache["uf_acme_aabbcc"] = _online_row("acme", "aabbcc")

    _install(monkeypatch, ApiList(error="HTTP 403"))
    await poller._poll_unifi_controller("acme", {"UniFiHost": "https://ctrl"}, "t1")

    assert "uf_acme_aabbcc" not in poller._cache, "a stale online row survived a refused poll"
    ctrl = poller._cache["uf_acme_ctrl"]
    assert ctrl.status == "error"
    assert ctrl.error == "HTTP 403"


async def test_a_recovered_poll_clears_the_prior_controller_error_row(monkeypatch):
    poller = DashboardPoller()
    poller._cache["uf_acme_ctrl"] = DeviceStatus(
        device_id="uf_acme_ctrl", customer_id="acme", vendor="unifi",
        name="ctrl", model="Controller", firmware="", serial="",
        status="error", uptime="", error="HTTP 403", last_poll="t0",
    )

    devices = ApiList([{"mac": "aabbcc", "state": 1, "name": "AP1", "version": "6.0"}])
    _install(monkeypatch, devices)
    await poller._poll_unifi_controller("acme", {"UniFiHost": "https://ctrl"}, "t1")

    assert "uf_acme_ctrl" not in poller._cache, "a recovered controller kept its stale error row"
    assert poller._cache["uf_acme_aabbcc"].status == "online"


async def test_eviction_does_not_touch_another_customer(monkeypatch):
    poller = DashboardPoller()
    poller._cache["uf_other_ddeeff"] = _online_row("other", "ddeeff")

    _install(monkeypatch, ApiList(error="HTTP 403"))
    await poller._poll_unifi_controller("acme", {"UniFiHost": "https://ctrl"}, "t1")

    assert "uf_other_ddeeff" in poller._cache, "evicted a different customer's rows"
