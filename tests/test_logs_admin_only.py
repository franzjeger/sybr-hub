"""The debug-log buffer is operator diagnostics, not viewer data.

`_BufferHandler` sits on the root logger at DEBUG, so `/api/logs` returns every
DEBUG+ record from every subsystem and customer, unredacted — cross-customer
names, hosts, integration diagnostics, and anything debug-logged that shape-based
redaction missed. Reading it, and wiping it (anti-forensics on the diagnostic
trail), are therefore admin-only, matching /ssh/audit-log and /system/*.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


@pytest.fixture(autouse=True)
def _reset_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


async def _token(username, role, write=False):
    u = await create_user(username, GOOD_PASSWORD, username.title(), role=role)
    if write:
        # POST /clear is a mutation, so the write-capability guard applies on top
        # of the role gate. Grant it here to isolate the role check.
        await set_can_write(u.id, True)
    return await create_access_token(u)


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_a_technician_cannot_read_the_debug_buffer(client):
    token = await _token("tech", Role.technician)
    assert client.get("/api/logs", headers=_h(token)).status_code == 403


async def test_a_technician_cannot_wipe_the_debug_buffer(client):
    # Write-capable but not admin: proves the role gate blocks it, not merely
    # the write-capability guard.
    token = await _token("tech", Role.technician, write=True)
    assert client.post("/api/logs/clear", headers=_h(token)).status_code == 403


async def test_an_admin_can_read_the_debug_buffer(client):
    token = await _token("boss", Role.admin)
    r = client.get("/api/logs", headers=_h(token))
    assert r.status_code == 200, r.text
    assert "logs" in r.json()


async def test_an_admin_can_clear_the_debug_buffer(client):
    token = await _token("boss", Role.admin, write=True)
    r = client.post("/api/logs/clear", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


async def test_the_buffer_is_unreachable_without_authentication(client):
    assert client.get("/api/logs").status_code == 401
    assert client.post("/api/logs/clear").status_code == 401
