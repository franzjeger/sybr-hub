"""Refuse known configuration failures before entering the router's lifespan."""

from __future__ import annotations

import traceback

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.encryption import MasterKeyUnavailableError, verify_master_key_available


class StartupConfigMiddleware:
    """Send a concise ASGI startup failure instead of a nested router traceback.

    Uvicorn treats lifespan.startup.failed as a failed startup and exits nonzero.
    Unexpected errors still propagate through the normal lifespan diagnostics.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "lifespan":
            await self.app(scope, receive, send)
            return

        first = await receive()
        if first["type"] == "lifespan.startup":
            try:
                verify_master_key_available()
            except MasterKeyUnavailableError as exc:
                detail = " ".join(str(exc).splitlines()).rstrip(".")
                await send(
                    {
                        "type": "lifespan.startup.failed",
                        "message": (
                            f"Cannot start Sybr HUB: {detail}. Check SYBR_KEY_WRAP_SECRET_FILE "
                            "/ SYBR_KEY_WRAP_SECRET or SYBR_MASTER_KEY_FILE / SYBR_MASTER_KEY "
                            "and restore the original secret or key before restarting."
                        ),
                    }
                )
                return
            except BaseException:
                # Like the router, signal failure before propagating the error.
                # Otherwise Uvicorn's lifespan="auto" interprets an exception
                # here as unsupported lifespan and serves without startup.
                await send({"type": "lifespan.startup.failed", "message": traceback.format_exc()})
                raise

        # The router must receive the startup message we consumed, then the
        # original channel for shutdown. HTTP and WebSocket traffic bypass this.
        pending = True

        async def replay() -> Message:
            nonlocal pending
            if pending:
                pending = False
                return first
            return await receive()

        await self.app(scope, replay, send)
