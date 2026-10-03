"""The context the AI console hands the model is limited to the caller's customers.

It used to report the state of whichever tunnel was up, so a technician scoped
to one customer could ask the console and learn whether another customer's
tunnel was connected.
"""

from __future__ import annotations

import pytest

from app.models.vpn import VpnProfile, VpnProtocol, VpnState
from app.services import vpn_manager
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)


@pytest.fixture()
def captured(monkeypatch):
    seen: dict = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs["context"])
        yield {"type": "done"}

    monkeypatch.setattr("app.services.claude_console.stream_message", fake_stream)
    return seen


@pytest.fixture()
def beta_tunnel_up(monkeypatch):
    profiles = [
        VpnProfile(id="p-acme", name="Acme", protocol=VpnProtocol.wireguard, customer_id=ACME),
        VpnProfile(id="p-beta", name="Beta", protocol=VpnProtocol.wireguard, customer_id=BETA),
    ]

    async def fake_profiles():
        return profiles

    monkeypatch.setattr(vpn_manager, "list_profiles", fake_profiles)
    monkeypatch.setitem(
        vpn_manager._connections, "p-beta", {"state": VpnState.connected, "interface": "wg0"}
    )


def _ask(client, headers):
    r = client.post(
        "/api/claude/message",
        headers=headers,
        json={"message": "status?", "external_processing_consent": True},
    )
    assert r.status_code == 200, r.text


async def test_a_scoped_caller_does_not_see_another_customers_tunnel(
    client, captured, beta_tunnel_up
):
    _ask(client, await login("acme-tech", customers=(ACME,)))
    assert captured["vpn_state"] == "disconnected"


async def test_an_unrestricted_caller_sees_every_tunnel(client, captured, beta_tunnel_up):
    _ask(client, await login("all-tech", all_customers=True))
    assert captured["vpn_state"] == "connected"
