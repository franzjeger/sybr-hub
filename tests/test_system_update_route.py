"""POST /api/system/update is admin + can_write, and re-execs only on success.

The self-update is the most powerful button in the app — it rewrites and
restarts the running code — so the gates matter more than the happy path. These
pin both, with the git work and the re-exec mocked so the test neither pulls nor
replaces its own process.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import set_can_write
from app.models.user import Role
from app.web.server import create_app

_PW = "Test1234!xyz"


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


async def _token(username: str, role: Role, *, can_write: bool) -> dict[str, str]:
    user = await create_user(username, _PW, username, role=role)
    if can_write:
        await set_can_write(user.id, True)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


async def test_update_requires_admin(client):
    """A technician with can_write is still refused — this is admin-only."""
    hdr = await _token("tech", Role.technician, can_write=True)
    r = client.post("/api/system/update", json={}, headers=hdr)
    assert r.status_code == 403


async def test_update_requires_can_write(client):
    """An admin without the write grant is refused by WriteGuardMiddleware."""
    hdr = await _token("adm_ro", Role.admin, can_write=False)
    r = client.post("/api/system/update", json={}, headers=hdr)
    assert r.status_code == 403


async def test_admin_with_write_updates_and_schedules_reexec(client, monkeypatch):
    import app.web.routes.system as sysroute

    async def _fake_update():
        return {"updated": True, "already_current": False,
                "from": "aaaaaaaaaaaa", "to": "bbbbbbbbbbbb",
                "branch": "main", "deps_changed": False}

    calls = {"reexec": 0}

    async def _fake_reexec(*_a, **_k):
        calls["reexec"] += 1

    monkeypatch.setattr(sysroute, "perform_self_update", _fake_update)
    monkeypatch.setattr(sysroute, "schedule_reexec", _fake_reexec)

    hdr = await _token("adm", Role.admin, can_write=True)
    r = client.post("/api/system/update", json={}, headers=hdr)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["restarting"] is True
    assert body["to"] == "bbbbbbbbbbbb"
    # BackgroundTasks run after the response; the TestClient drives them, so a
    # successful update must have scheduled exactly one re-exec.
    assert calls["reexec"] == 1, "re-exec was not scheduled after a successful update"


async def test_already_current_does_not_reexec(client, monkeypatch):
    import app.web.routes.system as sysroute

    async def _fake_update():
        return {"updated": False, "already_current": True,
                "from": "aaaaaaaaaaaa", "to": "aaaaaaaaaaaa",
                "branch": "main", "deps_changed": False}

    calls = {"reexec": 0}

    async def _fake_reexec(*_a, **_k):
        calls["reexec"] += 1

    monkeypatch.setattr(sysroute, "perform_self_update", _fake_update)
    monkeypatch.setattr(sysroute, "schedule_reexec", _fake_reexec)

    hdr = await _token("adm2", Role.admin, can_write=True)
    r = client.post("/api/system/update", json={}, headers=hdr)

    assert r.status_code == 200
    assert r.json()["restarting"] is False
    assert calls["reexec"] == 0, "nothing to pull must not restart the service"
