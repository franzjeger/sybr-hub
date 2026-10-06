"""Tailscale nodes belong to customers: by hand, or by tag:customer-<slug>.

Before this, a node had no customer at all, so a customer page's Tilgang tab
could only link to Verktøy > Tailscale. The mapping has two sources and a
fixed order (a hand assignment wins over a tag), and it is customer-scoped
like everything else on that page: a technician sees, and assigns, only nodes
of customers they hold.
"""

from __future__ import annotations

import pytest

from app.models.user import Role
from app.services import tailscale_customers as tc
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)


def _device(device_id: str, *, tags=(), online=True, name=None, addresses=None) -> dict:
    return {
        "id": device_id,
        "name": name or f"{device_id}.tailnet.example",
        "hostname": device_id,
        "given_name": device_id,
        "os": "linux",
        "tags": list(tags),
        "online": online,
        "last_seen": None,
        "last_seen_ago": None,
        "stale_days": None,
        "addresses": addresses if addresses is not None else ["100.64.0.1", "fd7a::1"],
        "tailscale_ip": "100.64.0.1",
        "key_days_left": None,
        "key_expiry_disabled": False,
    }


# ── The mapping rules ────────────────────────────────────────────────────────


def test_a_customer_id_becomes_a_tag_safe_slug():
    assert tc.customer_slug("Kunde_A") == "kunde-a"
    assert tc.customer_slug("Acme  AS!!") == "acme-as"
    assert tc.customer_tag("cust-acme") == "tag:customer-cust-acme"


def test_a_hand_assignment_wins_over_a_tag():
    devices = [_device("n1", tags=[tc.customer_tag(ACME)])]
    owners = tc.resolve(devices, [ACME, BETA], {"n1": BETA})
    assert owners == {"n1": (BETA, tc.SOURCE_MANUAL)}


def test_a_tag_maps_a_node_nobody_assigned():
    devices = [_device("n1", tags=["tag:server", tc.customer_tag(ACME)]), _device("n2")]
    assert tc.resolve(devices, [ACME, BETA], {}) == {"n1": (ACME, tc.SOURCE_TAG)}


def test_a_tag_two_customers_share_names_neither():
    # "Kunde_A" and "Kunde-A" both slug to kunde-a.
    devices = [_device("n1", tags=["tag:customer-kunde-a"])]
    assert tc.resolve(devices, ["Kunde_A", "Kunde-A"], {}) == {}


def test_a_hand_assignment_to_a_customer_since_archived_is_ignored():
    devices = [_device("n1", tags=[tc.customer_tag(ACME)])]
    # The assignment names a customer that no longer exists; the tag still holds.
    assert tc.resolve(devices, [ACME], {"n1": "gone"}) == {"n1": (ACME, tc.SOURCE_TAG)}


def test_connect_info_prefers_the_ipv4_address():
    info = tc.connect_info(_device("n1", addresses=["fd7a::5", "100.64.0.5"]))
    assert info["ip"] == "100.64.0.5"
    assert info["dns_name"] == "n1.tailnet.example"


# ── The routes ───────────────────────────────────────────────────────────────


@pytest.fixture()
def tailnet(monkeypatch):
    """A configured tailnet with three nodes: one tagged for each customer, one bare."""
    from app.core import modules
    from app.services import tailscale_api
    from app.web.routes import tailscale as route

    devices = [
        _device("acme-fw", tags=[tc.customer_tag(ACME)]),
        _device("beta-fw", tags=[tc.customer_tag(BETA)], online=False),
        _device("spare"),
    ]

    async def _list():
        return [dict(d) for d in devices]

    monkeypatch.setattr(modules, "is_enabled", lambda key: True)
    monkeypatch.setattr(route, "_ensure_configured", lambda: True)
    monkeypatch.setattr(tailscale_api, "list_devices", _list)
    return devices


async def _tech(**kw):
    return await login("tech", role=Role.technician, customers=[ACME], write=True, **kw)


async def test_a_customers_nodes_are_its_tagged_and_assigned_ones(client, tailnet):
    headers = await login("boss", role=Role.admin, write=True)
    assigned = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": ACME}
    )
    assert assigned.status_code == 200, assigned.text

    body = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).json()

    assert body["configured"] is True
    assert body["tag"] == tc.customer_tag(ACME)
    nodes = {n["id"]: n for n in body["nodes"]}
    assert set(nodes) == {"acme-fw", "spare"}
    assert nodes["acme-fw"]["source"] == "tag"
    assert nodes["spare"]["source"] == "manual"
    assert nodes["acme-fw"]["ip"] == "100.64.0.1"
    assert nodes["acme-fw"]["dns_name"] == "acme-fw.tailnet.example"
    assert nodes["acme-fw"]["online"] is True


async def test_a_scoped_technician_cannot_read_another_customers_nodes(client, tailnet):
    headers = await _tech()
    assert client.get(f"/api/tailscale/customer/{BETA}/nodes", headers=headers).status_code == 403
    mine = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers)
    assert mine.status_code == 200
    assert "beta-fw" not in mine.text


async def test_a_viewer_does_not_get_the_nodes(client, tailnet):
    headers = await login("viewer", role=Role.viewer, customers=[ACME])
    assert client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).status_code == 403


async def test_without_a_key_the_page_is_told_so(client, monkeypatch):
    from app.core import modules
    from app.web.routes import tailscale as route

    monkeypatch.setattr(modules, "is_enabled", lambda key: True)
    monkeypatch.setattr(route, "_ensure_configured", lambda: False)
    headers = await login("boss", role=Role.admin)

    body = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).json()

    assert body == {
        "configured": False,
        "customer_id": ACME,
        "tag": tc.customer_tag(ACME),
        "nodes": [],
    }


async def test_with_the_module_off_the_route_does_not_exist(client, monkeypatch):
    from app.core import modules

    monkeypatch.setattr(modules, "is_enabled", lambda key: key != "tailscale")
    headers = await login("boss", role=Role.admin)
    assert client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).status_code == 404


async def test_a_technician_assigns_and_releases_a_node_of_their_customer(client, tailnet):
    headers = await _tech()

    put = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": ACME}
    )
    assert put.status_code == 200, put.text
    assert await tc.manual_assignments() == {"spare": ACME}

    put = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": None}
    )
    assert put.status_code == 200, put.text
    assert await tc.manual_assignments() == {}


async def test_a_node_cannot_be_given_to_a_customer_the_caller_cannot_see(client, tailnet):
    headers = await _tech()
    put = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": BETA}
    )
    assert put.status_code == 403
    assert await tc.manual_assignments() == {}


async def test_a_node_cannot_be_taken_from_a_customer_the_caller_cannot_see(client, tailnet):
    await tc.assign("spare", BETA, "someone")
    headers = await _tech()

    for target in (ACME, None):
        put = client.put(
            "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": target}
        )
        assert put.status_code == 403, target
    assert await tc.manual_assignments() == {"spare": BETA}


async def test_assigning_needs_write(client, tailnet):
    headers = await login("reader", role=Role.technician, customers=[ACME], write=False)
    put = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": ACME}
    )
    assert put.status_code == 403
    assert await tc.manual_assignments() == {}


async def test_the_node_list_names_only_customers_the_caller_holds(client, tailnet):
    headers = await _tech()

    devices = {
        d["id"]: d for d in client.get("/api/tailscale/devices", headers=headers).json()["devices"]
    }

    assert devices["acme-fw"]["customer_id"] == ACME
    assert devices["acme-fw"]["customer_name"] == "Acme AS"
    assert devices["beta-fw"]["customer_id"] is None
    assert devices["beta-fw"]["customer_hidden"] is True
    assert devices["spare"]["customer_id"] is None and devices["spare"]["customer_hidden"] is False
    assert "Beta AS" not in str(devices)


async def test_a_technician_cannot_take_another_customers_tagged_node(client, tailnet):
    headers = await _tech()
    response = client.put(
        "/api/tailscale/device/beta-fw/customer", headers=headers, json={"customer_id": ACME}
    )
    assert response.status_code == 403, response.text
    assert "beta-fw" not in await tc.manual_assignments()
