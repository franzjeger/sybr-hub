"""Reverse proxy to a local Apache Guacamole instance.

The remote-access screens talk to Guacamole through this app rather than
reaching it directly, so the operator only has to expose one port. HTTP
requests are proxied in :func:`guac_proxy`; the display itself runs over the
WebSocket tunnel in :func:`guac_ws_proxy`.

``AuthMiddleware`` is a ``BaseHTTPMiddleware``, which Starlette only runs for
the ``http`` scope, so it does not see the handshake below. Both routes
therefore declare their guard explicitly: ``get_current_user`` on the HTTP half
and ``get_current_user_ws`` on the tunnel.

Note that the ``token`` in the forwarded query string is Guacamole's own
session token, not ours — it must reach the backend intact or the tunnel cannot
authenticate. Our token comes from the cookie or the subprotocol.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.models.user import User
from app.web.middleware.auth import get_current_user, get_current_user_ws

log = logging.getLogger(__name__)
router = APIRouter()

_BACKEND = os.getenv("GUACAMOLE_URL", "http://localhost:8888")
_WS_BACKEND = _BACKEND.replace("https://", "wss://").replace("http://", "ws://")

# Hop-by-hop headers must not be forwarded across a proxy boundary.
_HOP_BY_HOP = {"host", "transfer-encoding", "connection", "upgrade"}
_STRIP_FROM_RESPONSE = {"transfer-encoding", "connection", "content-encoding"}


@router.api_route(
    "/guacamole/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def guac_proxy(
    request: Request, path: str, _user: User = Depends(get_current_user)
) -> Response:
    """Reverse-proxy one HTTP request to Guacamole."""
    url = f"{_BACKEND}/guacamole/{path}"
    if request.query_params:
        url += "?" + str(request.query_params)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    body = await request.body()
    timeout = httpx.Timeout(connect=10, read=300, write=30, pool=10)

    # Tunnel requests are long-lived, so they stream; the client is closed by
    # the generator once the body is exhausted.
    if "tunnel" in path:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        try:
            req = client.build_request(
                method=request.method, url=url, headers=headers, content=body
            )
            resp = await client.send(req, stream=True)
        except httpx.ConnectError:
            await client.aclose()
            return JSONResponse({"error": "Guacamole backend unreachable"}, status_code=502)
        except httpx.TimeoutException:
            await client.aclose()
            return JSONResponse({"error": "Guacamole backend timeout"}, status_code=504)

        async def stream_body():
            try:
                async for chunk in resp.aiter_bytes(4096):
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_body(),
            status_code=resp.status_code,
            headers={
                k: v
                for k, v in resp.headers.items()
                if k.lower() not in _STRIP_FROM_RESPONSE
            },
        )

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(
                method=request.method, url=url, headers=headers, content=body
            )
    except httpx.ConnectError:
        return JSONResponse({"error": "Guacamole backend unreachable"}, status_code=502)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Guacamole backend timeout"}, status_code=504)

    # Rebuild rather than pass headers= so repeated Set-Cookie survives.
    response = Response(content=resp.content, status_code=resp.status_code)
    skip = _STRIP_FROM_RESPONSE | {"content-length"}
    for k, v in resp.headers.multi_items():
        if k.lower() not in skip:
            response.headers.append(k, v)
    return response


@router.websocket("/guacamole/{path:path}")
async def guac_ws_proxy(
    websocket: WebSocket,
    path: str,
    _user: User = Depends(get_current_user_ws),
) -> None:
    """Relay the Guacamole display tunnel in both directions."""
    await websocket.accept(subprotocol="guacamole")

    ws_url = f"{_WS_BACKEND}/guacamole/{path}"
    if websocket.query_params:
        ws_url += "?" + str(websocket.query_params)
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
                    pass

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
            pass
