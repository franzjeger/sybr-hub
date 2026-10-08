"""Tailscale nodes belong to customers: by hand, or by the customer's tag.

Before this, a node had no customer at all, so a customer page's Tilgang tab
could only link to Verktøy > Tailscale. The mapping has two sources and a
fixed order (a hand assignment wins over a tag), and it is customer-scoped
like everything else on that page: a technician sees, and assigns, only nodes
of customers they hold.

The tag is tag:customer-<slug> unless an administrator gave the customer one
of its own (TODO E30), and the tab's node list is cached for a minute and
emptied by every change to a mapping.
"""

from __future__ import annotations

from types import SimpleNamespace

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


@pytest.fixture(autouse=True)
def _no_cached_nodes():
    """The node cache is process-wide; each test starts without one."""
    tc.invalidate_nodes()
    yield
    tc.invalidate_nodes()


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
    owners = tc.resolve(devices, [ACME, BETA], {"n1": BETA}, {})
    assert owners == {"n1": (BETA, tc.SOURCE_MANUAL)}


def test_a_tag_maps_a_node_nobody_assigned():
    devices = [_device("n1", tags=["tag:server", tc.customer_tag(ACME)]), _device("n2")]
    assert tc.resolve(devices, [ACME, BETA], {}, {}) == {"n1": (ACME, tc.SOURCE_TAG)}


def test_a_tag_two_customers_share_names_neither():
    # "Kunde_A" and "Kunde-A" both slug to kunde-a.
    devices = [_device("n1", tags=["tag:customer-kunde-a"])]
    assert tc.resolve(devices, ["Kunde_A", "Kunde-A"], {}, {}) == {}


def test_a_hand_assignment_to_a_customer_since_archived_is_ignored():
    devices = [_device("n1", tags=[tc.customer_tag(ACME)])]
    # The assignment names a customer that no longer exists; the tag still holds.
    assert tc.resolve(devices, [ACME], {"n1": "gone"}, {}) == {"n1": (ACME, tc.SOURCE_TAG)}


def test_a_customers_own_tag_replaces_the_one_from_its_id():
    devices = [
        _device("n1", tags=["tag:acme-oslo"]),
        _device("n2", tags=[tc.customer_tag(ACME)]),
    ]
    owners = tc.resolve(devices, [ACME, BETA], {}, {ACME: "tag:acme-oslo"})
    assert owners == {"n1": (ACME, tc.SOURCE_TAG)}


def test_without_an_own_tag_the_mapping_is_unchanged():
    devices = [_device("n1", tags=[tc.customer_tag(ACME)]), _device("n2", tags=["tag:acme-oslo"])]
    assert tc.resolve(devices, [ACME, BETA], {}, {BETA: "tag:beta"}) == {
        "n1": (ACME, tc.SOURCE_TAG)
    }


def test_an_own_tag_that_is_another_customers_tag_names_neither():
    devices = [_device("n1", tags=[tc.customer_tag(BETA)])]
    assert tc.resolve(devices, [ACME, BETA], {}, {ACME: tc.customer_tag(BETA)}) == {}


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("tag:acme", "tag:acme"),
        ("  Tag:Acme-Oslo-2 ", "tag:acme-oslo-2"),  # Tailscale reads tags in lower case
        ("tag:a", "tag:a"),
        ("acme", None),  # no prefix
        ("tag:", None),  # empty name
        ("tag:2acme", None),  # must start with a letter
        ("tag:-acme", None),
        ("tag:acme_oslo", None),  # only letters, digits and "-"
        ("tag:acme.oslo", None),
        ("tag:acme oslo", None),
        ("tag:åsane", None),  # ASCII only
        ("tag:acme,tag:beta", None),
    ],
)
def test_a_tag_is_held_to_tailscales_own_syntax(given, kept):
    """tailcfg.CheckTag: "tag:", a letter, then letters, digits and "-"."""
    assert tc.normalize_tag(given) == kept


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

    net = SimpleNamespace(
        devices=[
            _device("acme-fw", tags=[tc.customer_tag(ACME)]),
            _device("beta-fw", tags=[tc.customer_tag(BETA)], online=False),
            _device("spare"),
        ],
        calls=0,
        fail=False,
    )

    async def _list():
        net.calls += 1
        if net.fail:
            raise RuntimeError("tailnet unreachable")
        return [dict(d) for d in net.devices]

    monkeypatch.setattr(modules, "is_enabled", lambda key: True)
    monkeypatch.setattr(route, "_ensure_configured", lambda: True)
    monkeypatch.setattr(tailscale_api, "list_devices", _list)
    return net


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
        "default_tag": tc.customer_tag(ACME),
        "tag_override": None,
        "nodes": [],
        "unassigned": [],
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


# ── One request per open, cached for a minute ────────────────────────────────
# The Tilgang tab asked Tailscale for the whole tailnet twice every time it was
# opened: once for the customer's nodes, once for the assign list.


async def test_the_tab_gets_its_assign_list_in_the_same_answer(client, tailnet):
    headers = await _tech()
    body = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).json()
    assert body["unassigned"] == [{"id": "spare", "name": "spare", "ip": "100.64.0.1"}]
    assert tailnet.calls == 1


async def test_opening_the_tab_again_within_the_minute_asks_tailscale_once(client, tailnet):
    headers = await _tech()
    first = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).json()
    second = client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers).json()
    assert first == second
    assert tailnet.calls == 1


async def test_after_the_minute_the_tab_reads_tailscale_again(client, tailnet, monkeypatch):
    headers = await _tech()
    client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers)
    monkeypatch.setattr(tc, "NODES_TTL_SECONDS", -1.0)
    client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers)
    assert tailnet.calls == 2


async def test_a_failed_read_is_not_cached(client, tailnet):
    headers = await _tech()
    tailnet.fail = True
    url = f"/api/tailscale/customer/{ACME}/nodes"
    assert client.get(url, headers=headers).status_code == 502
    tailnet.fail = False
    assert client.get(url, headers=headers).status_code == 200
    assert tailnet.calls == 2


async def test_an_assignment_shows_at_once_on_both_customers_and_the_assign_list(client, tailnet):
    """Every list is dropped, not only the customer's: the node also leaves the
    assign list another customer's tab is holding."""
    headers = await login("boss", role=Role.admin, write=True)
    acme = f"/api/tailscale/customer/{ACME}/nodes"
    beta = f"/api/tailscale/customer/{BETA}/nodes"
    client.get(acme, headers=headers)
    client.get(beta, headers=headers)

    put = client.put(
        "/api/tailscale/device/spare/customer", headers=headers, json={"customer_id": ACME}
    )
    assert put.status_code == 200, put.text

    assert "spare" in {n["id"] for n in client.get(acme, headers=headers).json()["nodes"]}
    assert client.get(beta, headers=headers).json()["unassigned"] == []


# ── A customer's own tag ─────────────────────────────────────────────────────


async def test_an_admin_gives_a_customer_its_own_tag(client, tailnet):
    tailnet.devices.append(_device("oslo-fw", tags=["tag:acme-oslo"]))
    headers = await login("boss", role=Role.admin, write=True)
    url = f"/api/tailscale/customer/{ACME}/nodes"
    client.get(url, headers=headers)  # cached before the change

    put = client.put(
        f"/api/tailscale/customer/{ACME}/tag", headers=headers, json={"tag": " Tag:Acme-Oslo "}
    )
    assert put.status_code == 200, put.text
    assert put.json()["tag"] == put.json()["tag_override"] == "tag:acme-oslo"
    assert await tc.tag_overrides() == {ACME: "tag:acme-oslo"}

    body = client.get(url, headers=headers).json()
    assert {n["id"] for n in body["nodes"]} == {"oslo-fw"}  # the old tag no longer maps
    assert body["tag"] == "tag:acme-oslo"
    assert body["default_tag"] == tc.customer_tag(ACME)
    assert "acme-fw" in {n["id"] for n in body["unassigned"]}


async def test_an_empty_tag_goes_back_to_the_one_from_the_id(client, tailnet):
    headers = await login("boss", role=Role.admin, write=True)
    url = f"/api/tailscale/customer/{ACME}/tag"
    client.put(url, headers=headers, json={"tag": "tag:acme-oslo"})

    for empty in (None, "", "  "):
        client.put(url, headers=headers, json={"tag": "tag:acme-oslo"})
        put = client.put(url, headers=headers, json={"tag": empty})
        assert put.status_code == 200, put.text
        assert put.json()["tag"] == tc.customer_tag(ACME)
        assert await tc.tag_overrides() == {}
    # The tag from the id itself needs no row either.
    put = client.put(url, headers=headers, json={"tag": tc.customer_tag(ACME)})
    assert put.status_code == 200 and await tc.tag_overrides() == {}


async def test_only_an_administrator_sets_a_tag(client, tailnet):
    for headers in (
        await _tech(),
        await login("reader", role=Role.admin, write=False),
    ):
        put = client.put(
            f"/api/tailscale/customer/{ACME}/tag", headers=headers, json={"tag": "tag:acme-oslo"}
        )
        assert put.status_code == 403, put.text
    assert await tc.tag_overrides() == {}


@pytest.mark.parametrize("bad", ["acme", "tag:2acme", "tag:acme_oslo", "tag:"])
async def test_a_tag_tailscale_would_refuse_is_refused(client, tailnet, bad):
    headers = await login("boss", role=Role.admin, write=True)
    put = client.put(f"/api/tailscale/customer/{ACME}/tag", headers=headers, json={"tag": bad})
    assert put.status_code == 400
    assert put.json()["error_key"] == "err_tailscale_tag_invalid"
    assert await tc.tag_overrides() == {}


async def test_a_tag_another_customer_has_is_refused(client, tailnet):
    headers = await login("boss", role=Role.admin, write=True)
    url = f"/api/tailscale/customer/{ACME}/tag"
    taken = client.put(url, headers=headers, json={"tag": tc.customer_tag(BETA)})
    assert taken.status_code == 409
    assert taken.json()["error_key"] == "err_tailscale_tag_taken"

    client.put(f"/api/tailscale/customer/{BETA}/tag", headers=headers, json={"tag": "tag:beta"})
    assert client.put(url, headers=headers, json={"tag": "tag:beta"}).status_code == 409
    assert await tc.tag_overrides() == {BETA: "tag:beta"}


async def test_a_new_tailnet_key_drops_the_cached_lists(client, tailnet):
    headers = await login("boss", role=Role.admin, write=True)
    client.get(f"/api/tailscale/customer/{ACME}/nodes", headers=headers)
    assert tc.cached_nodes(ACME) is not None

    saved = client.post("/api/settings", headers=headers, json={"tailscale_tailnet": "other"})
    assert saved.status_code == 200, saved.text
    assert tc.cached_nodes(ACME) is None
