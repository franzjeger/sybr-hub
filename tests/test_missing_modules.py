"""Tests for modules that were imported but did not exist.

``app.core.pwsh`` was a *top-level* import in the M365 audit's auth and setup
modules, so the whole audit subsystem — the project's headline feature — raised
ImportError on import. The other three were function-local imports that failed
only when the feature was used.
"""

from __future__ import annotations

import importlib

import pytest

from app.core.database import run_migrations


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "app.core.pwsh",
        "app.services.ssh_connection",
        "app.services.remediation",
    ],
)
def test_module_imports(module):
    assert importlib.import_module(module) is not None


def test_m365_audit_modules_import():
    """Regression: `from app.core.pwsh import find_pwsh` broke the whole audit."""
    pytest.importorskip("azure.identity", reason="azure SDK not installed")
    assert importlib.import_module("app.modules.m365_audit.auth") is not None
    assert importlib.import_module("app.modules.m365_audit.setup") is not None


def test_pwsh_call_sites_resolve():
    """The names the audit modules import must actually exist."""
    from app.core.pwsh import ensure_pwsh, find_pwsh

    assert callable(find_pwsh)
    assert callable(ensure_pwsh)


def test_ssh_and_remediation_call_sites_resolve():
    from app.services.remediation import load_remediation_sync
    from app.services.ssh_connection import SshSession

    assert callable(load_remediation_sync)
    assert callable(SshSession.connect)


# ---------------------------------------------------------------------------
# pwsh discovery
# ---------------------------------------------------------------------------


def test_find_pwsh_returns_none_when_absent(monkeypatch):
    import app.core.pwsh as pwsh

    monkeypatch.delenv("PWSH_PATH", raising=False)
    monkeypatch.setattr(pwsh.shutil, "which", lambda _: None)
    monkeypatch.setattr(pwsh, "_CANDIDATES", {})
    assert pwsh.find_pwsh() is None


def test_find_pwsh_uses_path(monkeypatch):
    import app.core.pwsh as pwsh

    monkeypatch.delenv("PWSH_PATH", raising=False)
    monkeypatch.setattr(pwsh.shutil, "which", lambda _: "/usr/bin/pwsh")
    assert pwsh.find_pwsh() == "/usr/bin/pwsh"


def test_find_pwsh_honours_override(monkeypatch, tmp_path):
    import app.core.pwsh as pwsh

    fake = tmp_path / "pwsh"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PWSH_PATH", str(fake))
    assert pwsh.find_pwsh() == str(fake)


async def test_ensure_pwsh_reports_error_when_missing(monkeypatch):
    import app.core.pwsh as pwsh

    monkeypatch.setattr(pwsh, "find_pwsh", lambda: None)
    events = [e async for e in pwsh.ensure_pwsh()]
    assert len(events) == 1
    assert events[0]["status"] == "error"
    # The caller shows this to the operator — it must say what to do.
    assert "install-powershell" in events[0]["msg"]


async def test_ensure_pwsh_reports_ok_when_present(monkeypatch):
    import app.core.pwsh as pwsh

    monkeypatch.setattr(pwsh, "find_pwsh", lambda: "/usr/bin/pwsh")
    events = [e async for e in pwsh.ensure_pwsh()]
    assert [e["status"] for e in events] == ["ok"]


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------


async def test_remediation_round_trip():
    from app.services.remediation import (
        clear_remediation,
        load_remediation,
        set_remediation,
    )

    await set_remediation("acme", "CIS-1.1", "done", notes="Fixed", assigned_to="tech")
    data = await load_remediation("acme")
    assert data["CIS-1.1"]["status"] == "done"
    assert data["CIS-1.1"]["notes"] == "Fixed"
    assert data["CIS-1.1"]["updated_by"] == "tech"

    assert await clear_remediation("acme", "CIS-1.1") is True
    assert await load_remediation("acme") == {}


async def test_remediation_upsert_overwrites():
    from app.services.remediation import load_remediation, set_remediation

    await set_remediation("acme", "CIS-1.1", "open")
    await set_remediation("acme", "CIS-1.1", "ignored", notes="Accepted risk")
    data = await load_remediation("acme")
    assert len(data) == 1
    assert data["CIS-1.1"]["status"] == "ignored"


async def test_remediation_rejects_unknown_status():
    from app.core.exceptions import ValidationError
    from app.services.remediation import set_remediation

    with pytest.raises(ValidationError):
        await set_remediation("acme", "CIS-1.1", "probably-fine")


async def test_load_remediation_sync_matches_async():
    """The report generator uses the sync accessor from non-async code."""
    from app.services.remediation import load_remediation_sync, set_remediation

    await set_remediation("acme", "CIS-2.4", "in_progress", notes="Scheduled")
    data = load_remediation_sync("acme")
    assert data["CIS-2.4"]["status"] == "in_progress"
    assert data["CIS-2.4"]["notes"] == "Scheduled"


def test_load_remediation_sync_is_safe_on_a_missing_database(tmp_path):
    import app.core.database as db_mod
    from app.services.remediation import load_remediation_sync

    db_mod.DB_PATH = tmp_path / "does-not-exist.db"
    assert load_remediation_sync("acme") == {}


def test_load_remediation_sync_handles_empty_customer():
    from app.services.remediation import load_remediation_sync

    assert load_remediation_sync("") == {}


# ---------------------------------------------------------------------------
# SSH known-hosts store
# ---------------------------------------------------------------------------


def test_known_hosts_entry_format():
    from app.services.ssh_connection import _host_entry

    assert _host_entry("10.0.0.1", 22) == "10.0.0.1"
    assert _host_entry("10.0.0.1", 2222) == "[10.0.0.1]:2222"


def test_known_hosts_round_trip(tmp_path, monkeypatch):
    import app.services.ssh_connection as sshmod

    monkeypatch.setattr(sshmod, "KNOWN_HOSTS_PATH", tmp_path / "known_hosts")
    sshmod._append_known_host("10.0.0.1", "ssh-ed25519 AAAAKEY")
    assert sshmod._read_known_hosts()["10.0.0.1"] == "ssh-ed25519 AAAAKEY"

    assert sshmod.forget_host("10.0.0.1") is True
    assert sshmod._read_known_hosts() == {}
    assert sshmod.forget_host("10.0.0.1") is False


def test_known_hosts_file_is_not_world_readable(tmp_path, monkeypatch):
    import app.services.ssh_connection as sshmod

    path = tmp_path / "known_hosts"
    monkeypatch.setattr(sshmod, "KNOWN_HOSTS_PATH", path)
    sshmod._append_known_host("10.0.0.1", "ssh-ed25519 AAAAKEY")
    assert path.stat().st_mode & 0o077 == 0
