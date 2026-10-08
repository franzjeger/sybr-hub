"""Live sockets must stop on access changes, not just the next handshake."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import create_access_token, create_user, update_user
from app.core.database import run_migrations
from app.core.rbac import set_user_customers
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app
from tests.ws_ping import PING_PATH, with_ping_socket


@pytest.fixture(autouse=True)
async def db(tmp_path, monkeypatch):
    import app.core.database as database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "ws.db")
    _reset_users_exist_cache()
    await run_migrations()
    yield
    _reset_users_exist_cache()


@pytest.mark.parametrize("change", ["disabled", "customer_scope"])
async def test_an_open_socket_is_closed_when_permissions_change(change):
    user = await create_user("socketuser", "Socket-Test!1234", "Socket User", Role.technician)
    token = await create_access_token(user)
    with (
        TestClient(with_ping_socket(create_app())) as client,
        client.websocket_connect(
            PING_PATH + "?token=" + token, headers={"origin": "http://testserver"}
        ) as ws,
    ):
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        if change == "disabled":
            await update_user(user.id, is_active=False)
        else:
            await set_user_customers(user.id, [])
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


async def test_sibling_origin_cannot_use_an_authenticated_socket():
    user = await create_user("originuser", "Socket-Test!1234", "Origin User")
    token = await create_access_token(user)
    with (
        TestClient(with_ping_socket(create_app())) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            PING_PATH + "?token=" + token,
            headers={"origin": "https://sibling.example.invalid"},
        ),
    ):
        pytest.fail("Cross-origin socket accepted")
