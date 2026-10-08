"""A socket that only answers ping, for the tests of socket authentication.

Every socket the product serves does real work once it is open: the terminal
starts a shell, the Guacamole tunnel needs guacd. The tests of the handshake,
the origin check and revocation open this one instead. It takes the same
dependency as the product sockets (``get_current_user_ws``) and passes through
the same middleware, so what those tests measure is the authentication and not
a feature behind it.

They used /api/ws/dashboard until it was removed: a live device feed that
nothing in the app opened (TODO E25).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect

from app.models.user import User
from app.web.middleware.auth import get_current_user_ws

PING_PATH = "/api/ws/test-ping"


async def _ping_socket(websocket: WebSocket, user: User = Depends(get_current_user_ws)) -> None:
    await websocket.accept()
    try:
        while True:
            if (await websocket.receive_json()).get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass


def with_ping_socket(app: FastAPI) -> FastAPI:
    """*app*, with the ping socket served at ``PING_PATH``."""
    app.add_api_websocket_route(PING_PATH, _ping_socket)
    return app
