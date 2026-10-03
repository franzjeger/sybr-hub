"""Restricted proxy to a local Apache Guacamole instance.

The remote-access screens talk to Guacamole through this app rather than
reaching it directly, so the operator only has to expose one port. Static
client assets may be proxied, but Guacamole API and HTTP tunnel access are
blocked. The display runs over the WebSocket tunnel in
:func:`guac_ws_proxy`.

``AuthMiddleware`` is a ``BaseHTTPMiddleware``, which Starlette only runs for
the ``http`` scope, so it does not see the handshake below. Both routes
therefore declare their guard explicitly: ``get_current_user`` on the HTTP half
and ``get_current_user_ws`` on the tunnel.

The browser presents a Sybr HUB-owned opaque session token. After checking its
owner and connection identifier, the proxy substitutes the Guacamole token
server-side; backend administrator credentials never reach the browser.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import PurePosixPath
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.models.user import User
from app.web.middleware.auth import get_current_user, get_current_user_ws, require_module

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_module("remote"))])

_BACKEND = os.getenv("GUACAMOLE_URL", "http://localhost:8888")
_WS_BACKEND = _BACKEND.replace("https://", "wss://").replace("http://", "ws://")

# Only static client assets are proxied. The shipped UI loads guacamole.min.js
# from /static and needs nothing here but the WebSocket tunnel below; the REST
# API (including POST api/tokens, the login) and the HTTP tunnel stay closed.
_STATIC_SUFFIXES = frozenset(
    {
        ".css",
        ".gif",
        ".ico",
        ".jpg",
        ".js",
        ".json",
        ".map",
        ".png",
        ".svg",
        ".ttf",
        ".woff",
        ".woff2",
    }
)
# One path segment: no leading dot (so no "." or ".." and no hidden files), and
# none of the characters a backend could decode or split into a different path
# ("%", "\\", ";" for Tomcat path parameters, whitespace).
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_CLOSED_ROOTS = frozenset({"api", "tunnel", "websocket-tunnel"})

# Static files need no credentials. Authorization and the hub's own
# access_token/refresh_token cookies must never reach the backend, and
# Guacamole authenticates with its own token rather than a cookie, so request
# headers are allowlisted instead of filtered.
_FORWARD_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "accept-language",
        "cache-control",
        "if-modified-since",
        "if-none-match",
        "range",
        "user-agent",
    }
)
# set-cookie: the backend has no business setting cookies on the hub's origin.
_STRIP_FROM_RESPONSE = frozenset(
    {"transfer-encoding", "connection", "content-encoding", "content-length", "set-cookie"}
)


def _static_asset_path(path: str) -> str | None:
    """Return *path* if it names a plain static asset, otherwise None.

    *path* is already percent-decoded by Starlette. Anything that a later
    normalisation could turn into another path is refused here, because httpx
    resolves dot segments when it builds the backend URL: ``x/../api/tokens``
    would otherwise arrive at Guacamole as ``api/tokens``.
    """
    if not path or len(path) > 512:
        return None
    segments = path.split("/")
    if not all(_SAFE_SEGMENT.fullmatch(segment) for segment in segments):
        return None
    lowered = [segment.lower() for segment in segments]
    if lowered[0] in _CLOSED_ROOTS or any("tunnel" in segment for segment in lowered):
        return None
    if PurePosixPath(lowered[-1]).suffix not in _STATIC_SUFFIXES:
        return None
    return path


@router.api_route("/guacamole/{path:path}", methods=["GET"])
async def guac_proxy(
    request: Request, path: str, _user: User = Depends(get_current_user)
) -> Response:
    """Proxy one static Guacamole client asset."""
    asset = _static_asset_path(path)
    if asset is None:
        return JSONResponse({"error": "Guacamole API is not exposed"}, status_code=404)

    # The query string is dropped: a static file needs none.
    url = f"{_BACKEND}/guacamole/{asset}"
    headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST_HEADERS}
    timeout = httpx.Timeout(connect=10, read=30, write=30, pool=10)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)
    except httpx.ConnectError:
        return JSONResponse({"error": "Guacamole backend unreachable"}, status_code=502)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Guacamole backend timeout"}, status_code=504)

    response = Response(content=resp.content, status_code=resp.status_code)
    for k, v in resp.headers.multi_items():
        if k.lower() not in _STRIP_FROM_RESPONSE:
            response.headers.append(k, v)
    return response


@router.websocket("/guacamole/{path:path}")
async def guac_ws_proxy(
    websocket: WebSocket,
    path: str,
    user: User = Depends(get_current_user_ws),
) -> None:
    """Relay the Guacamole display tunnel in both directions."""
    if path != "websocket-tunnel":
        await websocket.close(code=4404, reason="Unknown Guacamole tunnel")
        return

    from app.web.routes.proxy import resolve_guacamole_tunnel

    params = {
        key: value
        for key, value in websocket.query_params.items()
        if key
        in {
            "token",
            "GUAC_DATA_SOURCE",
            "GUAC_ID",
            "GUAC_TYPE",
            "GUAC_WIDTH",
            "GUAC_HEIGHT",
            "GUAC_DPI",
        }
    }
    backend_token = resolve_guacamole_tunnel(
        user,
        params.get("token", ""),
        params.get("GUAC_ID", ""),
    )
    if not backend_token:
        await websocket.close(code=4403, reason="Guacamole session not owned by user")
        return

    # Substitute server-side. The browser only ever sees its random opaque
    # session token and cannot reuse it against Guacamole's REST API.
    params["token"] = backend_token
    await websocket.accept(subprotocol="guacamole")

    ws_url = f"{_WS_BACKEND}/guacamole/{path}"
    ws_url += "?" + urlencode(params)
    # Path only: the query string carries Guacamole's session token, and this
    # record is readable through /api/logs by any authenticated role.
    log.info("WS proxy connecting to %s/guacamole/%s", _WS_BACKEND, path)

    try:
        import websockets

        async with websockets.connect(
            ws_url,
            subprotocols=["guacamole"],
            max_size=10 * 1024 * 1024,
            ping_interval=None,
        ) as backend:

            async def client_to_backend() -> None:
                try:
                    while True:
                        await backend.send(await websocket.receive_text())
                except (WebSocketDisconnect, Exception):
                    pass

            async def backend_to_client() -> None:
                try:
                    async for msg in backend:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception:
                    # Client vanished mid-stream; the outer handler closes up.
                    log.debug("Guacamole client stream ended", exc_info=True)

            tasks = [
                asyncio.create_task(client_to_backend()),
                asyncio.create_task(backend_to_client()),
            ]
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

    except WebSocketDisconnect:
        pass
    except ImportError:
        log.error("'websockets' is not installed — the Guacamole tunnel is unavailable")
        await websocket.close(code=1011, reason="Server missing websockets library")
    except Exception as exc:
        log.warning("WS proxy error: %s", exc)
        try:
            await websocket.close(code=1011, reason=str(exc)[:120])
        except Exception:
            # Socket already gone — nothing left to tell the client.
            log.debug("Could not deliver WS close frame", exc_info=True)
