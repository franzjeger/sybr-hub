"""The host-connection path in ssh_manager.

This file exists because there was no coverage here at all, and the single
call that every host operation funnels through was passing an argument the
callee does not accept — so host test, batch exec, key push, key revoke and
health check raised TypeError on every host and reported it as a per-host
connection failure. A live-looking error message is a poor smoke alarm.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from app.models.ssh import AuthMethod, DeviceType, SshHost
from app.services import ssh_manager
from app.services.ssh_connection import SshSession


def _host(**over) -> SshHost:
    base = dict(
        id="h1",
        label="SRV-FILE01",
        hostname="10.20.1.10",
        port=22,
        username="root",
        group_name="",
        device_type=DeviceType.linux,
        auth_method=AuthMethod.password,
        auth_key_id=None,
        customer_id="acme",
        tags=[],
        notes="",
        last_seen=None,
        is_reachable=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        created_by=None,
    )
    base.update(over)
    return SshHost(**base)


def test_connect_passes_only_arguments_the_session_accepts():
    """The regression guard: bind the call against the real signature.

    ``private_key=`` is not a parameter of ``SshSession.connect`` and never
    was, so this would have failed from the day the call was written.
    """
    sig = inspect.signature(SshSession.connect)
    assert "client_keys" in sig.parameters
    assert "private_key" not in sig.parameters


async def test_a_password_host_connects(monkeypatch):
    """Password auth carried no key at all, yet still hit the TypeError."""
    seen = {}

    async def _fake_connect(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(SshSession, "connect", staticmethod(_fake_connect))
    monkeypatch.setattr(ssh_manager, "_load_host_password", lambda _id: "s3cret")

    await ssh_manager._connect_to_host(_host())

    assert seen["hostname"] == "10.20.1.10"
    assert seen["username"] == "root"
    assert seen["password"] == "s3cret"
    assert seen["client_keys"] is None
    assert "private_key" not in seen


async def test_a_key_host_sends_a_parsed_key_object(monkeypatch):
    """client_keys wants asyncssh key objects, so the PEM must be imported —
    the fix is not a rename of the keyword."""
    import asyncssh

    seen = {}

    async def _fake_connect(**kwargs):
        seen.update(kwargs)
        return object()

    key = asyncssh.generate_private_key("ssh-ed25519")
    pem = key.export_private_key().decode()

    monkeypatch.setattr(SshSession, "connect", staticmethod(_fake_connect))
    monkeypatch.setattr(ssh_manager, "_load_private_key", lambda _id: pem)

    await ssh_manager._connect_to_host(
        _host(auth_method=AuthMethod.key, auth_key_id="k1")
    )

    assert seen["password"] is None
    assert isinstance(seen["client_keys"], list) and len(seen["client_keys"]) == 1
    assert not isinstance(seen["client_keys"][0], str), "a PEM string is not a key object"


async def test_an_unparseable_key_does_not_take_the_connection_down(monkeypatch):
    """Degrade to no key rather than raising out of the connect helper."""
    seen = {}

    async def _fake_connect(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(SshSession, "connect", staticmethod(_fake_connect))
    monkeypatch.setattr(ssh_manager, "_load_private_key", lambda _id: "not a key")

    await ssh_manager._connect_to_host(
        _host(auth_method=AuthMethod.key, auth_key_id="k1")
    )
    assert seen["client_keys"] is None
