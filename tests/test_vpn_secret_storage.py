"""VPN secrets live only in the encrypted store, and edits cannot redirect them.

Three defects, all in how a profile's secrets were kept:

* An imported .ovpn was stored whole in vpn_profiles.config, inline <key>,
  <tls-auth>, <tls-crypt> and friends included, in plaintext.
* update_profile wrote an edited config straight into the row, so a changed
  password or PSK landed there unencrypted. At connect the *old* encrypted
  value was merged over it, so the change silently never took effect.
* An edit could point a profile at a new host while the stored PSK or
  password was merged back in at connect, sending a credential the editor
  never knew to a server of their choosing.

These tests drive create, import, update, the lazy migration and connect, and
look at what is actually on disk.
"""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest

import app.core.database as database_module
from app.core.database import run_migrations
from app.core.exceptions import ValidationError
from app.core.orm import get_session
from app.models.vpn import VpnProfile, VpnProtocol
from app.services import vpn_manager, vpn_privileges
from app.services.vpn_backends import fortigate_ipsec, openvpn, wireguard

KEY_BODY = (
    "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----"
)
TLS_BODY = (
    "-----BEGIN OpenVPN Static key V1-----\n0123456789abcdef0123456789abcdef\n"
    "-----END OpenVPN Static key V1-----"
)
CA_BODY = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUQ0FQVUJMSUM=\n-----END CERTIFICATE-----"

OVPN = (
    "client\n"
    "dev tun\n"
    "remote vpn.example.com 1194\n"
    f"<ca>\n{CA_BODY}\n</ca>\n"
    f"<key>\n{KEY_BODY}\n</key>\n"
    f"<tls-auth>\n{TLS_BODY}\n</tls-auth>\n"
    "key-direction 1\n"
)

WG_PRIV = base64.b64encode(bytes(range(32))).decode()
WG_PRIV2 = base64.b64encode(bytes(range(1, 33))).decode()
WG_PEER_A = base64.b64encode(bytes(range(32, 64))).decode()
WG_PEER_B = base64.b64encode(bytes(range(64, 96))).decode()
WG_PSK_A = base64.b64encode(bytes(range(96, 128))).decode()
WG_PSK_B = base64.b64encode(bytes(range(128, 160))).decode()


@pytest.fixture(autouse=True)
async def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(vpn_manager, "VPN_SECRETS_DIR", tmp_path / "vpn_secrets")
    monkeypatch.setattr(vpn_privileges, "unavailable_reason", lambda _protocol: None)
    vpn_manager._connections.clear()
    await run_migrations()
    yield
    vpn_manager._connections.clear()


@pytest.fixture()
def backend_calls(monkeypatch):
    """Capture the config each backend would have been started with."""
    calls: list[dict] = []

    async def _capture(config, **_kw):
        calls.append(config)
        return {"ok": True, "interface": "tun-test"}

    monkeypatch.setattr(openvpn, "connect", _capture)
    monkeypatch.setattr(fortigate_ipsec, "connect", _capture)
    monkeypatch.setattr(wireguard, "connect", _capture)
    return calls


def _raw_row(profile_id: str) -> str:
    """The config column exactly as SQLite holds it."""
    with sqlite3.connect(database_module.DB_PATH) as db:
        return db.execute("SELECT config FROM vpn_profiles WHERE id = ?", (profile_id,)).fetchone()[
            0
        ]


def _raw_store(profile_id: str) -> bytes:
    path = vpn_manager.VPN_SECRETS_DIR / profile_id / "secrets.json"
    return path.read_bytes() if path.exists() else b""


async def _connect(profile_id: str) -> dict:
    result = await vpn_manager.connect(profile_id)
    vpn_manager._connections.pop(profile_id, None)
    return result


async def _fortigate(**overrides) -> VpnProfile:
    config = {
        "host": "fw.example.com",
        "username": "tech",
        "password": "old-password",
        "psk": "old-psk",
        "routes": ["10.0.0.0/24"],
    }
    config.update(overrides)
    return await vpn_manager.create_profile("FG", VpnProtocol.fortigate_ipsec, config)


# ── OpenVPN inline key blocks ─────────────────────────────────────────────────


async def test_import_keeps_inline_keys_out_of_the_row(backend_calls):
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")

    row = _raw_row(profile.id)
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in row
    assert "0123456789abcdef" not in row
    assert "MIIBszCCAVmgAwIBAgIUQ0FQVUJMSUM=" in row  # the CA is public and stays
    store = _raw_store(profile.id)
    assert store and b"MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in store  # encrypted

    result = await _connect(profile.id)
    assert result["ok"] is True
    assert backend_calls[-1]["config_content"] == OVPN


@pytest.mark.parametrize(
    "tag", ["tls-crypt", "tls-crypt-v2", "pkcs12", "secret", "auth-user-pass", "KEY"]
)
async def test_every_secret_block_kind_is_moved_out(tag, backend_calls):
    content = f"client\nremote vpn.example.com 1194\n<{tag}>\nSECRET-{tag}-MATERIAL\n</{tag}>\n"
    profile = await vpn_manager.create_profile(
        "OVPN", VpnProtocol.openvpn, {"config_content": content}
    )

    assert f"SECRET-{tag}-MATERIAL" not in _raw_row(profile.id)
    await _connect(profile.id)
    assert backend_calls[-1]["config_content"] == content


async def test_an_edit_that_keeps_the_placeholders_keeps_the_keys(backend_calls):
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")
    stored = vpn_manager.stored_config(await vpn_manager.get_profile(profile.id))

    edited = stored["config_content"].replace("dev tun", "dev tun\nverb 4")
    _, wiped = await vpn_manager.update_profile(profile.id, config={"config_content": edited})

    assert wiped == []
    await _connect(profile.id)
    assert backend_calls[-1]["config_content"] == OVPN.replace("dev tun", "dev tun\nverb 4")


async def test_a_placeholder_cannot_move_a_key_into_another_kind_of_block():
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")
    stored = vpn_manager.stored_config(await vpn_manager.get_profile(profile.id))
    placeholder = stored["config_content"].split("<key>\n")[1].split("\n</key>")[0]

    moved = stored["config_content"].replace(
        "key-direction 1",
        f"key-direction 1\n<http-proxy-user-pass>\n{placeholder}\n</http-proxy-user-pass>",
    )
    with pytest.raises(ValidationError):
        await vpn_manager.update_profile(profile.id, config={"config_content": moved})


async def test_a_new_remote_wipes_the_inline_keys(backend_calls):
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")
    stored = vpn_manager.stored_config(await vpn_manager.get_profile(profile.id))

    moved = stored["config_content"].replace("vpn.example.com", "attacker.example.net")
    _, wiped = await vpn_manager.update_profile(profile.id, config={"config_content": moved})

    assert {vpn_manager._secret_label(s) for s in wiped} == {"<key>", "<tls-auth>"}
    result = await _connect(profile.id)
    assert result["ok"] is False
    assert result["error_key"] == "err_vpn_secret_reentry"
    assert set(result["missing_secrets"]) == {"<key>", "<tls-auth>"}
    assert backend_calls == []


async def test_openvpn_config_file_paths_are_refused():
    with pytest.raises(ValidationError):
        await vpn_manager.create_profile(
            "OVPN", VpnProtocol.openvpn, {"config_file": "/etc/shadow", "config_content": "client"}
        )


async def test_openvpn_script_hooks_are_refused_when_saved():
    with pytest.raises(ValidationError):
        await vpn_manager.import_profile("OVPN", OVPN + "up /bin/sh\n", "openvpn")


# ── Edited secrets ────────────────────────────────────────────────────────────


async def test_an_edited_password_is_encrypted_and_actually_used(backend_calls):
    profile = await vpn_manager.create_profile(
        "OVPN",
        VpnProtocol.openvpn,
        {"config_content": "client\nremote vpn.example.com 1194\n", "password": "first"},
    )
    _, wiped = await vpn_manager.update_profile(
        profile.id,
        config={"config_content": "client\nremote vpn.example.com 1194\n", "password": "second"},
    )

    assert wiped == []
    assert "second" not in _raw_row(profile.id)
    await _connect(profile.id)
    assert backend_calls[-1]["password"] == "second"


async def test_an_edit_without_secrets_keeps_them_when_the_target_is_unchanged(backend_calls):
    profile = await _fortigate()
    _, wiped = await vpn_manager.update_profile(
        profile.id,
        config={"host": "fw.example.com", "username": "tech", "routes": ["10.1.0.0/24"]},
    )

    assert wiped == []
    await _connect(profile.id)
    assert backend_calls[-1]["psk"] == "old-psk"
    assert backend_calls[-1]["password"] == "old-password"


async def test_secrets_never_reach_the_row_on_create():
    profile = await _fortigate()
    row = _raw_row(profile.id)
    assert "old-psk" not in row and "old-password" not in row


# ── Retargeting ───────────────────────────────────────────────────────────────


async def test_a_new_host_without_secrets_wipes_them(backend_calls):
    profile = await _fortigate()
    _, wiped = await vpn_manager.update_profile(
        profile.id, config={"host": "attacker.example.net", "username": "tech"}
    )

    assert wiped == ["password", "psk"]
    assert b"old-psk" not in _raw_store(profile.id)
    result = await _connect(profile.id)
    assert result["ok"] is False
    assert result["missing_secrets"] == ["password", "psk"]
    assert backend_calls == []
    assert profile.id not in vpn_manager._connections

    _, wiped = await vpn_manager.update_profile(
        profile.id,
        config={
            "host": "attacker.example.net",
            "username": "tech",
            "password": "new-password",
            "psk": "new-psk",
        },
    )
    assert wiped == []
    assert (await _connect(profile.id))["ok"] is True
    assert backend_calls[-1]["psk"] == "new-psk"


async def test_a_secret_resupplied_with_the_new_host_replaces_only_itself(backend_calls):
    profile = await _fortigate()
    _, wiped = await vpn_manager.update_profile(
        profile.id, config={"host": "fw2.example.com", "username": "tech", "psk": "new-psk"}
    )

    assert wiped == ["password"]
    result = await _connect(profile.id)
    assert result["missing_secrets"] == ["password"]

    # Entering the password later clears the requirement; the new PSK stays.
    await vpn_manager.update_profile(
        profile.id,
        config={"host": "fw2.example.com", "username": "tech", "password": "pw2"},
    )
    assert (await _connect(profile.id))["ok"] is True
    assert backend_calls[-1]["psk"] == "new-psk"
    assert backend_calls[-1]["password"] == "pw2"


def _wg(endpoint="vpn.example.com:51820", **overrides) -> dict:
    config = {
        "addresses": ["10.0.0.2/24"],
        "private_key": WG_PRIV,
        "peers": [
            {
                "public_key": WG_PEER_A,
                "endpoint": endpoint,
                "allowed_ips": ["10.0.0.0/24"],
                "preshared_key": WG_PSK_A,
            }
        ],
    }
    config.update(overrides)
    return config


def _without_secrets(config: dict) -> dict:
    clean = json.loads(json.dumps(config))
    clean.pop("private_key", None)
    for peer in clean["peers"]:
        peer.pop("preshared_key", None)
    return clean


async def test_a_new_wireguard_endpoint_wipes_the_private_key(backend_calls):
    profile = await vpn_manager.create_profile("WG", VpnProtocol.wireguard, _wg())
    _, wiped = await vpn_manager.update_profile(
        profile.id, config=_without_secrets(_wg(endpoint="attacker.example.net:51820"))
    )

    assert {vpn_manager._secret_label(s) for s in wiped} == {"private_key", "preshared_key"}
    result = await _connect(profile.id)
    assert result["ok"] is False
    assert "private_key" in result["missing_secrets"]


async def test_a_wireguard_edit_that_keeps_the_peer_keeps_the_keys(backend_calls):
    profile = await vpn_manager.create_profile("WG", VpnProtocol.wireguard, _wg())
    config = _without_secrets(_wg())
    config["peers"][0]["allowed_ips"] = ["0.0.0.0/0"]
    _, wiped = await vpn_manager.update_profile(profile.id, config=config)

    assert wiped == []
    await _connect(profile.id)
    assert backend_calls[-1]["private_key"] == WG_PRIV
    assert backend_calls[-1]["peers"][0]["preshared_key"] == WG_PSK_A


async def test_a_new_private_key_with_the_new_endpoint_is_accepted(backend_calls):
    profile = await vpn_manager.create_profile("WG", VpnProtocol.wireguard, _wg())
    config = _without_secrets(_wg(endpoint="vpn2.example.com:51820"))
    config["private_key"] = WG_PRIV2
    _, wiped = await vpn_manager.update_profile(profile.id, config=config)

    assert [vpn_manager._secret_label(s) for s in wiped] == ["preshared_key"]
    assert (await _connect(profile.id))["ok"] is False  # the PSK still has to be re-entered


# ── Lazy migration of rows written by older versions ──────────────────────────


async def _legacy_row(protocol: VpnProtocol, config: dict) -> str:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    row = VpnProfile(
        id="legacy-" + protocol.value,
        name="Legacy",
        protocol=protocol,
        config=config,
        created_at=now,
        updated_at=now,
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return row.id


async def test_listing_moves_plaintext_out_of_legacy_rows(backend_calls):
    pid = await _legacy_row(VpnProtocol.openvpn, {"config_content": OVPN, "password": "legacy"})
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" in _raw_row(pid)

    await vpn_manager.list_profiles()

    row = _raw_row(pid)
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in row
    assert "password" not in json.loads(row)
    await _connect(pid)
    assert backend_calls[-1]["config_content"] == OVPN
    assert backend_calls[-1]["password"] == "legacy"


async def test_migration_prefers_the_row_over_a_stale_store(backend_calls):
    """update_profile used to write the edit to the row and leave the store stale."""
    pid = await _legacy_row(
        VpnProtocol.fortigate_ipsec,
        {"host": "fw.example.com", "username": "tech", "psk": "edited-psk"},
    )
    vpn_manager._store_secrets(pid, {"psk": "original-psk", "password": "pw"})

    await vpn_manager.get_profile(pid)

    assert "edited-psk" not in _raw_row(pid)
    await _connect(pid)
    assert backend_calls[-1]["psk"] == "edited-psk"
    assert backend_calls[-1]["password"] == "pw"


async def test_migration_is_idempotent():
    pid = await _legacy_row(VpnProtocol.openvpn, {"config_content": OVPN})
    await vpn_manager.get_profile(pid)
    first = (_raw_row(pid), vpn_manager._read_secrets(pid))
    await vpn_manager.get_profile(pid)
    await vpn_manager.list_profiles()
    assert (_raw_row(pid), vpn_manager._read_secrets(pid)) == first


async def test_an_unreadable_store_is_never_overwritten(monkeypatch, backend_calls):
    pid = await _legacy_row(
        VpnProtocol.fortigate_ipsec, {"host": "fw.example.com", "username": "t", "psk": "p"}
    )
    vpn_manager._store_secrets(pid, {"password": "keep-me"})
    before = _raw_store(pid)

    def _unreadable(_profile_id):
        raise ValueError("decryption failed")

    monkeypatch.setattr(vpn_manager, "_read_secrets", _unreadable)
    await vpn_manager.get_profile(pid)

    assert _raw_store(pid) == before


async def test_position_keyed_wireguard_psks_still_reach_their_peer(backend_calls):
    config = _without_secrets(_wg())
    pid = await _legacy_row(VpnProtocol.wireguard, config)
    vpn_manager._store_secrets(pid, {"private_key": WG_PRIV, "peer_0_psk": WG_PSK_A})

    await _connect(pid)
    assert backend_calls[-1]["peers"][0]["preshared_key"] == WG_PSK_A


async def test_wireguard_psks_follow_their_peer_when_peers_are_reordered(backend_calls):
    config = _wg()
    config["peers"].append(
        {
            "public_key": WG_PEER_B,
            "endpoint": "vpn.example.com:51820",
            "allowed_ips": ["10.1.0.0/24"],
            "preshared_key": WG_PSK_B,
        }
    )
    profile = await vpn_manager.create_profile("WG", VpnProtocol.wireguard, config)
    reordered = _without_secrets(config)
    reordered["peers"].reverse()
    await vpn_manager.update_profile(profile.id, config=reordered)

    await _connect(profile.id)
    peers = {p["public_key"]: p["preshared_key"] for p in backend_calls[-1]["peers"]}
    assert peers == {WG_PEER_A: WG_PSK_A, WG_PEER_B: WG_PSK_B}


# ── What callers may see ──────────────────────────────────────────────────────


async def test_the_description_holds_flags_not_secrets():
    profile = await vpn_manager.import_profile("OVPN", OVPN, "openvpn")
    profile = await vpn_manager.get_profile(profile.id)
    flags = vpn_manager.describe_secrets(profile)
    visible = json.dumps([vpn_manager.stored_config(profile), flags])

    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" not in visible
    assert flags == {"has_password": False, "needs_reentry": []}

    fg = await _fortigate()
    fg_flags = vpn_manager.describe_secrets(await vpn_manager.get_profile(fg.id))
    assert fg_flags == {"has_password": True, "has_psk": True, "needs_reentry": []}
    assert "old-psk" not in json.dumps([vpn_manager.stored_config(fg), fg_flags])
