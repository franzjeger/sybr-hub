"""Cancellation must finish socket cleanup and retain its original cause."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anyio

from app.web.middleware import websocket_security as security


async def test_scope_cancellation_finishes_websocket_cleanup(monkeypatch):
    user = SimpleNamespace(id="synthetic-user")
    payload = SimpleNamespace(
        session_id="synthetic-session", exp=datetime.now(UTC) + timedelta(minutes=5)
    )
    monkeypatch.setattr(security, "get_current_user_ws", AsyncMock(return_value=user))
    monkeypatch.setattr(security, "_extract_ws_token", lambda _: "synthetic-token")
    monkeypatch.setattr(security, "decode_token", AsyncMock(return_value=payload))
    monkeypatch.setattr(security, "get_accessible_customer_ids", AsyncMock(return_value=None))
    monkeypatch.setattr("app.core.mfa.enabled", AsyncMock(return_value=False))
    monkeypatch.setattr("app.core.mfa.required_for", lambda _: False)
    cleaned = False

    with anyio.CancelScope() as cancel_scope:

        async def socket_app(scope, receive, send):
            nonlocal cleaned
            cancel_scope.cancel()
            try:
                await asyncio.Event().wait()
            finally:
                # Model asynchronous resource shutdown after a client disconnects.
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                cleaned = True

        await security.WebSocketSecurityMiddleware(socket_app)(
            {"type": "websocket", "path": "/api/ws/test-ping", "headers": []},
            AsyncMock(),
            AsyncMock(),
        )

    assert cancel_scope.cancelled_caught
    assert cleaned
