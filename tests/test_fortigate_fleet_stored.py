"""Verktøy > Nettverk opens on what the hub last read, not on a live poll.

The FortiGate tab opened on /fortigate/all, which signs in to every
customer's FortiGate (ten seconds each at worst) before it answers, so the
page took as long as the slowest firewall and opening it again polled them
all again. /fortigate/fleet answers from the customers' stored addresses and
the readings the firmware inventory keeps, and contacts nothing.
"""

from __future__ import annotations

import pytest

from app.models.user import Role
from app.services import firmware_inventory
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    CUSTOMERS,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)

HOSTS = {ACME: "FW.acme.example", BETA: "192.0.2.2"}


@pytest.fixture(autouse=True)
def _fortigates(monkeypatch, _scope_env):
    """Both customers have a FortiGate; only Acme's API token is stored."""
    records = [dict(c, FortiGateHost=HOSTS[c["_id"]]) for c in CUSTOMERS]
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers", staticmethod(lambda: records)
    )
    monkeypatch.setattr(
        "app.core.credentials.get_secret",
        lambda cid, name: "token" if (cid, name) == (ACME, "fortigate_api_token") else None,
    )

    def no_firewall(*args, **kwargs):
        raise AssertionError("the stored fleet contacted a firewall")

    monkeypatch.setattr("app.services.fortigate_api._build_client", no_firewall)
    monkeypatch.setattr("app.services.fortigate_api.poll_all_fortigates", no_firewall)


async def _read_acme() -> dict:
    reading = firmware_inventory.fortigate_reading(
        key=HOSTS[ACME], name="FW-ACME", model="FortiGate-60F", version="v7.4.8", available=[]
    )
    await firmware_inventory.record(ACME, "fortigate", [reading])
    return reading


async def test_the_fleet_is_what_was_last_read_and_reaches_no_firewall(client):
    reading = await _read_acme()
    headers = await login("tech-all", all_customers=True)

    r = client.get("/api/fortigate/fleet", headers=headers)

    assert r.status_code == 200, r.text
    fleet = {f["customer_id"]: f for f in r.json()["fortigates"]}
    assert r.json()["count"] == 2
    acme = fleet[ACME]
    assert (acme["host"], acme["hostname"], acme["model"], acme["firmware"]) == (
        "FW.acme.example",
        "FW-ACME",
        "FortiGate-60F",
        "v7.4.8",
    )
    assert acme["firmware_status"] == reading["status"]
    assert acme["read_at"], "when it was read"
    assert acme["has_token"] is True
    # Never read: the address and nothing it would have to make up.
    beta = fleet[BETA]
    assert (beta["host"], beta["hostname"], beta["firmware"], beta["read_at"]) == (
        "192.0.2.2",
        "",
        "",
        None,
    )
    assert beta["has_token"] is False


async def test_a_read_that_failed_says_so(client):
    await _read_acme()
    await firmware_inventory.record_read_failure(
        ACME, "fortigate", "timed out", key=HOSTS[ACME], name=HOSTS[ACME]
    )
    headers = await login("tech-all", all_customers=True)
    acme = next(
        f
        for f in client.get("/api/fortigate/fleet", headers=headers).json()["fortigates"]
        if f["customer_id"] == ACME
    )
    # The version it last ran stays, with why it could not be read now.
    assert (acme["firmware"], acme["read_error"]) == ("v7.4.8", "timed out")
    assert acme["firmware_status"] != "current"


async def test_the_fleet_is_scoped_to_the_callers_customers(client):
    await _read_acme()
    headers = await login("tech-acme", customers=(ACME,))
    r = client.get("/api/fortigate/fleet", headers=headers)
    assert [f["customer_id"] for f in r.json()["fortigates"]] == [ACME]
    assert_no_foreign(r.text)


async def test_a_viewer_does_not_reach_it(client):
    headers = await login("viewer", role=Role.viewer, all_customers=True)
    assert client.get("/api/fortigate/fleet", headers=headers).status_code == 403
