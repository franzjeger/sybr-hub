"""Tailnet changes are admin-only; reading the inventory is technician work.

The hub is served on the tailnet its Tailscale key manages. Any technician
could mint a reusable, pre-authorised auth key with arbitrary tags, approve a
device's subnet routes, or authorise, rename and delete devices — each of
which changes who can reach the hub and the customer networks behind it.
Viewers could read the device and key inventory.
"""

from __future__ import annotations

import pytest

from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)

READS = [
    "/api/tailscale/status",
    "/api/tailscale/devices",
    "/api/tailscale/keys",
    "/api/tailscale/device/d1/routes",
]

MUTATIONS = [
    ("post", "/api/tailscale/keys", {"reusable": True, "preauthorized": True, "tags": ["tag:x"]}),
    ("delete", "/api/tailscale/keys/k1", None),
    ("post", "/api/tailscale/device/d1/routes", {"routes": ["10.0.0.0/8"]}),
    ("post", "/api/tailscale/device/d1/authorize", {"authorized": True}),
    ("post", "/api/tailscale/device/d1/name", {"name": "renamed"}),
    ("post", "/api/tailscale/device/d1/tags", {"tags": ["tag:x"]}),
    ("post", "/api/tailscale/device/d1/key", {"disabled": True}),
    ("delete", "/api/tailscale/device/d1", None),
]


@pytest.fixture(autouse=True)
def tailnet(monkeypatch) -> list[str]:
    """A stand-in for the Tailscale API that records every call made to it."""
    from app.services import tailscale_api

    calls: list[str] = []

    def _stub(name, result):
        async def _call(*args, **kwargs):
            calls.append(name)
            return result

        monkeypatch.setattr(tailscale_api, name, _call)

    device = {"online": True, "stale_days": None, "key_days_left": None}
    _stub("list_devices", [device])
    _stub("list_keys", [])
    _stub("get_device_routes", {"advertised": [], "enabled": []})
    _stub("create_key", {"id": "k2"})
    _stub("delete_key", True)
    _stub("set_device_routes", [])
    _stub("authorize_device", True)
    _stub("rename_device", True)
    _stub("update_device_tags", {})
    _stub("set_key_expiry", True)
    _stub("delete_device", True)
    monkeypatch.setattr("app.web.routes.tailscale._ensure_configured", lambda: True)
    monkeypatch.setattr(
        "app.core.config.load_app_settings", lambda: {"tailscale_api_key": "synthetic"}
    )
    return calls


def _send(client, headers, method, path, body):
    return client.request(method.upper(), path, headers=headers, json=body)


@pytest.mark.parametrize("path", READS)
async def test_a_viewer_cannot_read_the_tailnet(client, path):
    headers = await login("viewer", role=Role.viewer, all_customers=True)
    assert client.get(path, headers=headers).status_code == 403


@pytest.mark.parametrize("path", READS)
async def test_a_technician_can_read_the_tailnet(client, path):
    headers = await login("tech", role=Role.technician)
    assert client.get(path, headers=headers).status_code == 200


@pytest.mark.parametrize("method,path,body", MUTATIONS)
async def test_a_technician_cannot_change_the_tailnet(client, tailnet, method, path, body):
    # Write capability and every customer: the role is the only thing missing.
    headers = await login("tech", role=Role.technician, all_customers=True)
    assert _send(client, headers, method, path, body).status_code == 403
    assert tailnet == [], "the Tailscale API was called for a refused request"


@pytest.mark.parametrize("method,path,body", MUTATIONS)
async def test_an_admin_can_change_the_tailnet(client, tailnet, method, path, body):
    headers = await login("boss", role=Role.admin)
    r = _send(client, headers, method, path, body)
    assert r.status_code == 200, r.text
    assert len(tailnet) == 1


async def test_testing_a_tailscale_key_is_admin_only(client):
    headers = await login("tech", role=Role.technician, all_customers=True)
    r = client.post("/api/tailscale/test", headers=headers, json={"api_key": "••••••"})
    assert r.status_code == 403


# ── The request bodies ───────────────────────────────────────────────────────


async def test_the_key_form_still_creates_a_key(client, tailnet, monkeypatch):
    """tsDoCreateKey() sends description, the three switches and an expiry."""
    from app.services import tailscale_api

    seen = {}

    async def _create(**kwargs):
        seen.update(kwargs)
        return {"id": "k2"}

    monkeypatch.setattr(tailscale_api, "create_key", _create)
    headers = await login("boss", role=Role.admin)

    r = client.post(
        "/api/tailscale/keys",
        headers=headers,
        json={
            "description": "office",
            "reusable": False,
            "ephemeral": True,
            "preauthorized": True,
            "expiry_seconds": 7200,
        },
    )

    assert r.status_code == 200, r.text
    assert seen == {
        "reusable": False,
        "ephemeral": True,
        "preauthorized": True,
        "tags": [],
        "expiry_seconds": 7200,
        "description": "office",
    }


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/tailscale/keys", {"expiry_seconds": "a day"}),
        ("post", "/api/tailscale/keys", {"tags": "tag:x"}),
        ("post", "/api/tailscale/keys", {"reuseable": True}),
        ("post", "/api/tailscale/device/d1/routes", {"routes": "10.0.0.0/8"}),
        ("post", "/api/tailscale/device/d1/authorize", {"authorized": "perhaps"}),
        ("post", "/api/tailscale/device/d1/name", {"name": 5}),
        ("post", "/api/tailscale/device/d1/tags", {"tags": [1]}),
        ("post", "/api/tailscale/device/d1/key", {"disable": True}),
        ("post", "/api/tailscale/test", {"api_key": ["k"]}),
    ],
)
async def test_a_malformed_body_is_a_422_not_a_502(client, tailnet, method, path, body):
    """A parse failure used to land in the blanket except and read as Tailscale's fault."""
    headers = await login("boss", role=Role.admin)

    r = _send(client, headers, method, path, body)

    assert r.status_code == 422, r.text
    assert r.json()["error_type"] == "validation_error"
    assert tailnet == [], "the Tailscale API was called for a refused request"


async def test_an_empty_device_name_keeps_its_message(client, tailnet):
    headers = await login("boss", role=Role.admin)

    r = client.post("/api/tailscale/device/d1/name", headers=headers, json={"name": " "})

    assert r.status_code == 400
    assert r.json()["error"] == "Navn er påkrevd"
