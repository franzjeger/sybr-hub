"""A VPN peer must not be able to inject arguments into root ip/resolvectl.

parse_push_reply reads ifconfig/route/DNS values straight from the server's
PUSH_REPLY — a customer gateway we do not control, and which could be
compromised. Those values reach `sudo ip addr add`, `sudo ip route add`, and
`sudo resolvectl dns` as arguments; a value beginning with "-" is a flag to a
root command, and a malformed one misconfigures routing or crashes setup.

Every such value is validated as a real IP now. These tests assert the parse
drops hostile/malformed tokens, keeps legitimate ones, and that a hostile peer
cannot crash the parse with a non-numeric field.
"""

from __future__ import annotations

import pytest

from app.services.vpn_backends.ovpn_tunnel import parse_push_reply


def test_legitimate_reply_parses():
    r = parse_push_reply(
        "PUSH_REPLY,ifconfig 10.8.0.2 10.8.0.1,route 192.168.1.0 255.255.255.0,"
        "dhcp-option DNS 10.8.0.1,peer-id 3,ping 10,ping-restart 60"
    )
    assert r["ifconfig_local"] == "10.8.0.2"
    assert r["ifconfig_remote"] == "10.8.0.1"
    assert r["routes"] == [("192.168.1.0", "255.255.255.0")]
    assert r["dns_servers"] == ["10.8.0.1"]
    assert r["peer_id"] == 3
    assert r["ping_restart"] == 60


def test_option_shaped_ifconfig_is_dropped():
    r = parse_push_reply("PUSH_REPLY,ifconfig --script=/x 10.8.0.1")
    assert r["ifconfig_local"] == ""
    assert r["ifconfig_remote"] == ""


def test_option_shaped_dns_is_dropped():
    r = parse_push_reply("PUSH_REPLY,dhcp-option DNS -X")
    assert r["dns_servers"] == []


def test_option_shaped_route_network_is_dropped():
    r = parse_push_reply("PUSH_REPLY,route -foo 255.255.255.0")
    assert r["routes"] == []


def test_garbage_route_mask_is_dropped():
    r = parse_push_reply("PUSH_REPLY,route 10.0.0.0 not-a-mask")
    assert r["routes"] == []


def test_hostname_where_an_ip_is_required_is_dropped():
    """Only bare IPs are accepted — a name could resolve anywhere, and it is
    not what OpenVPN's ifconfig line carries."""
    r = parse_push_reply("PUSH_REPLY,ifconfig evil.example.com 10.8.0.1")
    assert r["ifconfig_local"] == ""


def test_a_non_numeric_ping_does_not_crash_and_keeps_the_default():
    """int(tokens[1]) used to raise, killing tunnel setup on a hostile reply."""
    r = parse_push_reply("PUSH_REPLY,ifconfig 10.8.0.2 10.8.0.1,ping-restart pwned")
    assert r["ping_restart"] == 120          # default preserved
    assert r["ifconfig_local"] == "10.8.0.2"  # parsing continued past it


def test_valid_ipv6_dns_is_kept():
    r = parse_push_reply("PUSH_REPLY,dhcp-option DNS 2001:4860:4860::8888")
    assert r["dns_servers"] == ["2001:4860:4860::8888"]


@pytest.mark.asyncio
async def test_add_route_refuses_a_flag_shaped_network(monkeypatch):
    """Belt-and-suspenders: the method that builds the sudo command guards too,
    so operator-config routes (not just PUSH_REPLY) are covered."""
    from app.services.vpn_backends.ovpn_tunnel import TunDevice

    def _boom(*a, **k):
        raise AssertionError("spawned sudo ip with an injected argument")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _boom)
    tun = TunDevice("tun0")
    await tun.add_route("-batch/tmp/x", "24")   # must return without spawning


@pytest.mark.asyncio
async def test_configure_refuses_a_flag_shaped_local_ip(monkeypatch):
    from app.services.vpn_backends.ovpn_tunnel import TunDevice

    def _boom(*a, **k):
        raise AssertionError("spawned sudo ip with an injected argument")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _boom)
    tun = TunDevice("tun0")
    await tun.configure("-foo", "255.255.255.0")   # must return without spawning
