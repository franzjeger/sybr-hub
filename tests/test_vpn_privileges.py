"""VPN control must fail closed when the host boundary withholds privileges."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.vpn import VpnProtocol
from app.services import vpn_manager, vpn_privileges


@pytest.fixture(autouse=True)
def _clear_connections():
    vpn_manager._connections.clear()
    yield
    vpn_manager._connections.clear()


def test_capability_reads_effective_net_admin_bit(monkeypatch):
    values = {"CapEff": f"{1 << 12:x}", "NoNewPrivs": "1"}
    monkeypatch.setattr(vpn_privileges, "_linux_status_value", values.get)
    monkeypatch.setattr(vpn_privileges.os, "geteuid", lambda: 1000)

    capabilities = vpn_privileges.vpn_capabilities()
    assert capabilities["no_new_privileges"] is True
    assert capabilities["cap_net_admin"] is True
    assert capabilities["protocols"]["wireguard"]["available"] is True
    assert capabilities["protocols"]["openvpn"]["available"] is True
    assert capabilities["protocols"]["fortigate_ipsec"]["available"] is False


def test_capability_fails_closed_when_proc_status_is_unavailable(monkeypatch):
    monkeypatch.setattr(vpn_privileges, "_linux_status_value", lambda _name: None)
    monkeypatch.setattr(vpn_privileges.os, "geteuid", lambda: 1000)

    capability = vpn_privileges.protocol_capability(VpnProtocol.wireguard)
    assert capability["available"] is False
    assert capability["mode"] == "external"
    assert "vil ikke forsøke sudo" in capability["reason"]


async def test_manager_refuses_before_loading_secrets_or_starting_backend(monkeypatch):
    profile = SimpleNamespace(
        id="customer-vpn",
        name="Customer VPN",
        protocol=VpnProtocol.openvpn,
        config={"config_content": "client"},
    )

    async def _profile(_profile_id):
        return profile

    monkeypatch.setattr(vpn_manager, "get_profile", _profile)
    monkeypatch.setattr(
        vpn_privileges,
        "unavailable_reason",
        lambda _protocol: "external control only",
    )
    monkeypatch.setattr(
        vpn_manager,
        "_load_secrets",
        lambda _profile_id: pytest.fail("secrets were loaded after capability refusal"),
    )

    result = await vpn_manager.connect(profile.id, owned_by="tech")

    assert result == {
        "ok": False,
        "error": "external control only",
        "error_type": "vpn_control_unavailable",
    }
    assert profile.id not in vpn_manager._connections


async def test_status_filters_connections_before_serializing():
    vpn_manager._connections.update(
        {
            "visible": {
                "state": vpn_manager.VpnState.connected,
                "interface": "tun-visible",
            },
            "hidden": {
                "state": vpn_manager.VpnState.connected,
                "interface": "tun-hidden",
            },
        }
    )

    status = await vpn_manager.get_status({"visible"})

    assert [connection["profile_id"] for connection in status["connections"]] == ["visible"]
    assert status["profile_id"] == "visible"
