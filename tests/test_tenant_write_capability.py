"""Writing into a customer's tenant is a capability, not a role.

Sybr HUB is read-mostly and every Graph permission it holds ends in
.Read.All, so until now "write" was impossible rather than forbidden. That
distinction stops being comforting the moment a write endpoint lands, and the
guard has to exist before the endpoint does — retrofitting a security
boundary means shipping the window in which it was absent.

The default is off for everyone, admins included. An admin runs this tool; a
tenant write reaches a customer's production, and those are different powers.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_all_customers, set_tenant_write
from app.models.user import Role, User
from app.web.middleware.auth import _reset_users_exist_cache, require_tenant_write
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


@pytest.fixture()
def app_with_write_route():
    """A throwaway route behind the guard, so the guard is what is tested."""
    app = create_app()

    @app.post("/api/_probe/{customer_id}/write")
    async def _probe(customer_id: str, user: User = Depends(require_tenant_write())):
        return {"ok": True, "by": user.username}

    return app


@pytest.fixture()
def client(app_with_write_route):
    with TestClient(app_with_write_route) as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _user(name: str, role: Role, *, write: bool, customers=("acme",)):
    u = await create_user(name, GOOD_PASSWORD, name.title(), role=role)
    for cid in customers:
        await grant_access(u.id, cid)
    if write:
        await set_tenant_write(u.id, True)
    return await create_access_token(u)


async def test_a_new_account_cannot_write(client):
    """The default, and the reason the column defaults to 0."""
    token = await _user("tech", Role.technician, write=False)
    resp = client.post("/api/_probe/acme/write", headers=_h(token))
    assert resp.status_code == 403
    assert "lesetilgang" in resp.json()["detail"]


async def test_an_admin_does_not_get_it_from_being_an_admin(client):
    """The distinction the whole design rests on.

    Administering this tool and changing settings in somebody else's tenant
    are different powers. Folding the second into the admin role would have
    handed it to every existing admin on the day it shipped.
    """
    token = await _user("boss", Role.admin, write=False, customers=())
    await set_all_customers((await _lookup("boss")).id, True)
    assert client.post("/api/_probe/acme/write", headers=_h(token)).status_code == 403


async def test_the_grant_is_what_opens_it(client):
    token = await _user("writer", Role.technician, write=True)
    resp = client.post("/api/_probe/acme/write", headers=_h(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["by"] == "writer"


async def test_the_capability_is_not_a_skeleton_key(client):
    """It does not widen which customers the holder can reach."""
    token = await _user("writer", Role.technician, write=True, customers=("acme",))
    assert client.post("/api/_probe/acme/write", headers=_h(token)).status_code == 200
    assert client.post("/api/_probe/other/write", headers=_h(token)).status_code == 403


async def test_a_viewer_is_refused_even_when_granted(client):
    """The role floor still applies underneath the capability."""
    token = await _user("looker", Role.viewer, write=True)
    assert client.post("/api/_probe/acme/write", headers=_h(token)).status_code == 403


async def test_revoking_takes_it_away(client):
    token = await _user("writer", Role.technician, write=True)
    assert client.post("/api/_probe/acme/write", headers=_h(token)).status_code == 200

    user = await _lookup("writer")
    await set_tenant_write(user.id, False)
    assert client.post("/api/_probe/acme/write", headers=_h(token)).status_code == 403, (
        "revocation must bite on the existing token, not only on the next login"
    )


async def _lookup(username: str):
    from app.core.auth import get_user_by_username

    return await get_user_by_username(username)


async def test_the_column_defaults_to_off_in_the_schema():
    """The thing that must never quietly change.

    A capability that arrives switched on for every existing account is not a
    capability — it is a change of blast radius announced in a release note.
    all_customers deliberately defaulted to 1 because installs already behaved
    that way; this one has no such history and must default to 0.
    """
    from app.core.database import get_db

    async with get_db() as conn:
        async with conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row[1]: row for row in await cur.fetchall()}

    assert "tenant_write" in columns, "migration 15 did not run"
    default = columns["tenant_write"][4]
    assert str(default) == "0", f"tenant_write defaults to {default!r}, not off"


async def test_an_account_created_normally_has_it_off():
    """Belt and braces: the default reaches the object, not just the column."""
    user = await create_user("fresh", GOOD_PASSWORD, "Fresh", role=Role.admin)
    assert user.tenant_write is False
    assert (await _lookup("fresh")).tenant_write is False
