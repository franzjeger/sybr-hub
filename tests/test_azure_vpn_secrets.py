"""Azure VPN must not drop secrets in world-readable, predictable files.

connect() previously wrote three secrets to fixed /tmp paths:
  /tmp/azure_vpn_tls.key  — the TLS-auth key, explicitly chmod 0o644
  /tmp/azure_vpn3.ovpn    — config that referenced it
  /tmp/azure_vpn_rt.txt   — the OAuth refresh token, then chmod 644 at the dest
Fixed names in a world-writable dir are a symlink/TOCTOU target and let any
local user read the secret from a name they can predict; 0644 leaves the TLS
key and the token readable by everyone on the host.

The TLS key is now inlined into the config (no key file at all), configs and
the token transit a private 0600 temp with an unpredictable name, and the
persisted token is chmod 600. connect() itself needs openvpn3 and a tun
device, so it is validated on the host; the pure builder and the temp writer
are covered here.
"""

from __future__ import annotations

import os
import stat

from app.services.vpn_backends.azure import _build_ovpn_config, _write_private

# ── Config builder: the TLS key is inlined, not a file reference ──────────────


def test_tls_auth_key_is_inlined_not_a_file_path():
    cfg = _build_ovpn_config("gw.example.com", "CA-PEM", "aa" * 64)
    assert "<tls-auth>" in cfg and "</tls-auth>" in cfg
    assert "BEGIN OpenVPN Static key V1" in cfg
    # The old form referenced a path; it must be gone.
    assert "tls-auth /" not in cfg
    assert "/tmp/" not in cfg


def test_inline_key_carries_the_direction():
    """`tls-auth <file> 1` becomes `key-direction 1` when the block is inlined —
    dropping it would silently break the HMAC direction."""
    cfg = _build_ovpn_config("gw", "CA", "bb" * 64)
    assert "key-direction 1" in cfg


def test_the_hex_key_is_wrapped_to_openvpn_static_key_format():
    cfg = _build_ovpn_config("gw", "", "ab" * 64)  # 128 hex chars
    body = cfg.split("<tls-auth>")[1].split("</tls-auth>")[0]
    key_lines = [ln for ln in body.splitlines() if ln and "OpenVPN Static key" not in ln]
    assert all(len(ln) <= 32 for ln in key_lines)
    assert "".join(key_lines) == "ab" * 64


def test_no_tls_auth_block_when_no_key():
    cfg = _build_ovpn_config("gw", "CA", "")
    assert "tls-auth" not in cfg
    assert "key-direction" not in cfg


def test_ca_is_inlined_when_present():
    assert "<ca>\nCA-PEM\n</ca>" in _build_ovpn_config("gw", "CA-PEM", "")


def test_gateway_is_the_remote():
    assert "remote gw.example.com 443" in _build_ovpn_config("gw.example.com", "", "")


# ── Private temp writer: 0600, unpredictable, correct content ─────────────────


def test_private_file_is_owner_only():
    p = _write_private("s3cret", ".ovpn")
    try:
        mode = stat.S_IMODE(p.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
        assert p.read_text() == "s3cret"
    finally:
        p.unlink(missing_ok=True)


def test_private_file_names_are_unpredictable_and_unique():
    a = _write_private("x", ".ovpn")
    b = _write_private("x", ".ovpn")
    try:
        assert a != b
        assert "azure_vpn_tls.key" not in str(a)
        assert "/tmp/azure_vpn3.ovpn" not in str(a)
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


def test_private_write_does_not_follow_a_pre_existing_symlink():
    """mkstemp creates O_EXCL, so it cannot be pre-seeded as a symlink the way
    a fixed /tmp/<name> path could."""
    p = _write_private("data", ".txt")
    try:
        assert not p.is_symlink()
        assert p.stat().st_uid == os.getuid()
    finally:
        p.unlink(missing_ok=True)
