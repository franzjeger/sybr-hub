"""Known key configuration failures stop startup without a router traceback."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from app.core.encryption import MasterKeyUnavailableError
from app.web.middleware.startup_config import StartupConfigMiddleware


async def test_a_known_configuration_error_never_enters_the_application(monkeypatch):
    def unavailable():
        raise MasterKeyUnavailableError("The original key-wrapping secret is missing.\nRestore it.")

    monkeypatch.setattr(
        "app.web.middleware.startup_config.verify_master_key_available", unavailable
    )
    inner = AsyncMock()
    receive = AsyncMock(return_value={"type": "lifespan.startup"})
    send = AsyncMock()

    await StartupConfigMiddleware(inner)({"type": "lifespan"}, receive, send)

    inner.assert_not_awaited()
    send.assert_awaited_once()
    message = send.call_args.args[0]
    assert message["type"] == "lifespan.startup.failed"
    assert "key-wrapping secret is missing" in message["message"]
    assert "SYBR_KEY_WRAP_SECRET_FILE" in message["message"]
    assert "\n" not in message["message"]


async def test_a_successful_preflight_preserves_the_lifespan_protocol(monkeypatch):
    checks = []
    monkeypatch.setattr(
        "app.web.middleware.startup_config.verify_master_key_available", lambda: checks.append(1)
    )
    queue = asyncio.Queue()
    for kind in ("lifespan.startup", "lifespan.shutdown"):
        queue.put_nowait({"type": kind})
    send = AsyncMock()
    received = []

    async def inner(scope, receive, send):
        received.append(await receive())
        await send({"type": "lifespan.startup.complete"})
        received.append(await receive())
        await send({"type": "lifespan.shutdown.complete"})

    await StartupConfigMiddleware(inner)({"type": "lifespan"}, queue.get, send)

    assert checks == [1]
    assert received == [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    assert [c.args[0]["type"] for c in send.await_args_list] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]


async def test_unexpected_preflight_errors_keep_their_diagnostics(monkeypatch):
    def broken():
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr("app.web.middleware.startup_config.verify_master_key_available", broken)
    send = AsyncMock()
    with pytest.raises(RuntimeError, match="unexpected bug"):
        await StartupConfigMiddleware(AsyncMock())(
            {"type": "lifespan"},
            AsyncMock(return_value={"type": "lifespan.startup"}),
            send,
        )
    message = send.call_args.args[0]
    assert message["type"] == "lifespan.startup.failed"
    assert "Traceback" in message["message"]
    assert "RuntimeError: unexpected bug" in message["message"]


@pytest.mark.parametrize("scope_type", ["http", "websocket"])
async def test_request_traffic_does_not_repeat_the_key_check(monkeypatch, scope_type):
    check = AsyncMock()
    monkeypatch.setattr("app.web.middleware.startup_config.verify_master_key_available", check)
    inner = AsyncMock()
    scope, receive, send = {"type": scope_type}, AsyncMock(), AsyncMock()

    await StartupConfigMiddleware(inner)(scope, receive, send)

    check.assert_not_called()
    inner.assert_awaited_once_with(scope, receive, send)


@pytest.mark.parametrize("entrypoint", ["main", "uvicorn-auto", "uvicorn-on"])
@pytest.mark.parametrize("missing_secret", ["master-key", "wrapping-secret"])
def test_real_server_exits_nonzero_with_a_concise_key_configuration_error(
    tmp_path, entrypoint, missing_secret
):
    # The operator-key file is consulted before the keyring or key backups.
    # A nonexistent file safely exercises the real entrypoints in isolation.
    env = dict(os.environ)
    env.pop("SYBR_MASTER_KEY", None)
    if missing_secret == "master-key":
        env["SYBR_MASTER_KEY_FILE"] = str(tmp_path / "missing-master-key")
    else:
        env.pop("SYBR_MASTER_KEY_FILE", None)
        env.pop("SYBR_KEY_WRAP_SECRET", None)
        env["SYBR_KEY_WRAP_SECRET_FILE"] = str(tmp_path / "missing-wrapping-secret")
        # An empty keyring and isolated home prevent the preflight from reading
        # the operator's real master key or backups while testing first startup.
        env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
        env["HOME"] = str(tmp_path)
    env["SYBR_HUB_HOST"] = "127.0.0.1"
    env["SYBR_HUB_PORT"] = "0"
    env.pop("SYBR_HUB_SSL_CERT", None)
    env.pop("SYBR_HUB_SSL_KEY", None)
    for name in ("MSP_DATA_DIR", "MSP_CONFIG_DIR", "MSP_AUDIT_DIR"):
        env[name] = str(tmp_path / name)
    command = [sys.executable, "main.py"]
    if entrypoint.startswith("uvicorn-"):
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.web.server:app",
            "--port",
            "0",
            "--lifespan",
            entrypoint.removeprefix("uvicorn-"),
        ]

    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Cannot start Sybr HUB:" in output
    assert "SYBR_MASTER_KEY_FILE" in output
    assert "before restarting" in output
    assert "Traceback" not in output
    assert "Application startup complete" not in output
    assert not list(tmp_path.rglob(".master_key_backup"))


@pytest.mark.parametrize("lifespan_mode", ["auto", "on"])
async def test_unexpected_preflight_failure_also_stops_uvicorn(monkeypatch, lifespan_mode, caplog):
    from uvicorn import Config
    from uvicorn.lifespan.on import LifespanOn

    def broken():
        raise RuntimeError("unexpected startup bug")

    monkeypatch.setattr("app.web.middleware.startup_config.verify_master_key_available", broken)
    inner = AsyncMock()
    lifespan = LifespanOn(
        Config(StartupConfigMiddleware(inner), lifespan=lifespan_mode, log_config=None)
    )

    await lifespan.startup()

    assert lifespan.startup_failed and lifespan.should_exit
    assert "RuntimeError: unexpected startup bug" in caplog.text
    inner.assert_not_awaited()
