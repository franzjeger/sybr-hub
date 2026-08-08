"""The shipped systemd unit has to actually work on a hardened host.

Every setting here was found by something failing on a real deployment, and
each is easy to "tidy up" later by someone who reads the hardening list and
not the history. The installer writes this file verbatim apart from the port,
so a regression here ships straight to production.
"""

from __future__ import annotations

from pathlib import Path

import pytest

UNIT = Path("scripts/sybr-hub.service").read_text(encoding="utf-8")


def _settings(key: str) -> list[str]:
    return [
        line.split("=", 1)[1].strip()
        for line in UNIT.splitlines()
        if line.strip().startswith(f"{key}=")
    ]


def test_memory_deny_write_execute_is_off():
    """pwsh is .NET; the JIT needs W-then-X. With yes it dies in libcoreclr.so
    with SIGSEGV and no legible error, taking the setup wizard with it."""
    assert _settings("MemoryDenyWriteExecute") == ["no"]


def test_home_is_set_and_writable():
    """systemd defaults HOME to WorkingDirectory (/opt/sybr-hub), which
    ProtectSystem=strict makes read-only. PowerShell creates ~/.cache/powershell
    before it parses its arguments, so the wizard died at exit code -6 long
    before any script ran. Install-Module -Scope CurrentUser needs it too.
    """
    home = _settings("Environment")
    home = [v.split("=", 1)[1] for v in home if v.startswith("HOME=")]
    assert home, "HOME not set — pwsh will fail on a read-only home"

    writable = _settings("ReadWritePaths")[0].split()
    assert any(home[0].startswith(p) for p in writable), (
        f"HOME={home[0]} is not under any ReadWritePaths entry {writable}"
    )


def test_the_null_keyring_backend_is_not_shipped():
    """It does not raise, it discards. Every stored secret vanished at restart
    with no error until credentials.py started verifying its writes."""
    envs = _settings("Environment")
    assert not [v for v in envs if v.startswith("PYTHON_KEYRING_BACKEND=")], (
        "the null keyring backend silently drops secrets — never ship it"
    )


@pytest.mark.parametrize(
    "directive",
    ["NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes",
     "PrivateTmp=yes", "RestrictSUIDSGID=yes"],
)
def test_the_rest_of_the_hardening_survived(directive):
    """Loosening MemoryDenyWriteExecute was necessary; loosening the rest was
    not, and this is where that would quietly happen."""
    assert directive in UNIT


def test_the_service_still_binds_to_loopback():
    """Tailscale serve fronts it. Binding 0.0.0.0 would expose it on every
    interface, with no TLS unless SYBR_HUB_SSL_CERT is set."""
    assert "Environment=SYBR_HUB_HOST=127.0.0.1" in UNIT


def test_master_key_wrap_secret_uses_a_systemd_credential():
    assert _settings("LoadCredential") == [
        "key-wrap.secret:/etc/sybr-hub-secrets/key-wrap.secret"
    ]
    assert "SYBR_KEY_WRAP_SECRET_FILE=%d/key-wrap.secret" in _settings("Environment")
    assert not any(
        value.startswith("SYBR_KEY_WRAP_SECRET=") for value in _settings("Environment")
    ), "the secret value itself must never be stored in the unit environment"


def test_service_created_files_are_private_by_default():
    assert _settings("UMask") == ["0077"]


def test_unit_does_not_promise_sudo_that_no_new_privileges_blocks():
    assert "Cmnd_Alias" not in UNIT
    assert "ALL=(root)" not in UNIT
