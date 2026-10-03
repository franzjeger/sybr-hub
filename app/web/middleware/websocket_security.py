"""Origin checking and revocation for the entire lifetime of every socket."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from anyio import move_on_after
from fastapi import WebSocket, WebSocketException

from app.core import access_events
from app.core.auth import decode_token, get_user_by_id, validate_session
from app.core.rbac import get_accessible_customer_ids
from app.web.middleware.auth import _extract_ws_token, get_current_user_ws


def origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if origin is None:
        # Non-browser clients possess their own token. Browsers always supply
        # Origin; an opaque/null browser origin is explicitly refused below.
        return True
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    expected_scheme = "https" if websocket.url.scheme == "wss" else "http"
    allowed = {f"{expected_scheme}://{websocket.headers.get('host', '')}"}
    # A TLS terminator can forward ws on loopback. Secure origin + the same
    # Host is valid; this never admits a sibling origin or a cleartext downgrade.
    allowed.add(f"https://{websocket.headers.get('host', '')}")
    allowed.update(
        x.strip() for x in os.environ.get("SYBR_WS_ALLOWED_ORIGINS", "").split(",") if x.strip()
    )
    return origin in allowed


def _permissions(user):
    return (user.role, user.is_active, user.all_customers, user.can_write, user.tenant_write)


class WebSocketSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)
        websocket = WebSocket(scope, receive, send)
        if not origin_allowed(websocket):
            await send({"type": "websocket.close", "code": 1008, "reason": "Origin denied"})
            return
        try:
            user = await get_current_user_ws(websocket)
            token = _extract_ws_token(websocket)
            payload = await decode_token(token)
            if payload is None:
                raise WebSocketException(code=1008)
            from app.core import mfa

            if await mfa.enabled(user.id) and not await mfa.session_verified(
                user.id, payload.session_id
            ):
                raise WebSocketException(code=1008)

            if mfa.required_for(user) and not await mfa.enabled(user.id):
                raise WebSocketException(code=1008)
            if scope["path"].endswith("/ws/terminal"):
                from app.core.mfa import is_recent

                if not await is_recent(user.id, payload.session_id):
                    raise WebSocketException(code=1008)
            initial_scope = await get_accessible_customer_ids(user)
        except WebSocketException:
            await send({"type": "websocket.close", "code": 1008, "reason": "Not authenticated"})
            return

        closed = False
        with access_events.watch(
            user.id, payload.session_id, hashlib.sha256(token.encode()).hexdigest()
        ) as watch:

            def ensure_live():
                if watch.revoked or datetime.now(UTC) >= payload.exp:
                    raise asyncio.CancelledError

            async def guarded_receive():
                message = await receive()
                ensure_live()
                return message

            async def guarded_send(message):
                nonlocal closed
                if closed:
                    return
                if message["type"] != "websocket.close":
                    ensure_live()
                else:
                    closed = True
                await send(message)

            async def monitor():
                while True:
                    remaining = (payload.exp - datetime.now(UTC)).total_seconds()
                    if remaining <= 0 or watch.revoked:
                        return
                    try:
                        await asyncio.wait_for(watch.event.wait(), timeout=min(remaining, 15))
                        return
                    except TimeoutError:
                        pass
                    current = await get_user_by_id(user.id)
                    if current is None or _permissions(current) != _permissions(user):
                        return
                    if payload.session_id and not await validate_session(payload.session_id):
                        return
                    if await decode_token(token) is None:
                        return
                    if await get_accessible_customer_ids(current) != initial_scope:
                        return

            app_task = asyncio.create_task(self.app(scope, guarded_receive, guarded_send))
            monitor_task = asyncio.create_task(monitor())
            try:
                done, _ = await asyncio.wait(
                    {app_task, monitor_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if monitor_task in done or watch.revoked or app_task.cancelled():
                    watch.revoked = True
                    if not closed:
                        closed = True
                        await send(
                            {
                                "type": "websocket.close",
                                "code": 1008,
                                "reason": "Access revoked or expired",
                            }
                        )
                elif not app_task.cancelled():
                    await app_task
            finally:
                app_task.cancel()
                monitor_task.cancel()
                # AnyIO can cancel at every await. Shield resource cleanup so a
                # disconnect does not cancel it again or replace the original
                # cancellation cause; still bound shutdown for a stuck handler.
                with move_on_after(5, shield=True):
                    await asyncio.gather(app_task, monitor_task, return_exceptions=True)
