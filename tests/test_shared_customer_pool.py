"""Customer access is explicit, atomic, and preserved across upgrades."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    create_access_token,
    create_user,
    get_user_by_id,
    get_user_by_username,
)
from app.core.database import get_db, run_migrations
from app.core.rbac import check_customer_access, set_can_write
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


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


async def _admin_headers() -> dict:
    user = await create_user("boss", GOOD_PASSWORD, "Boss", role=Role.admin)
    await set_can_write(user.id, True)  # /auth/users is a mutating route
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


# ── Migration 19: existing accounts join the pool ─────────────────────────────


async def test_migration_preserves_an_existing_scoped_account():
    # A user created through the fail-closed primitive starts scoped.
    scoped = await create_user("legacy", GOOD_PASSWORD, "Legacy", role=Role.technician)
    assert scoped.all_customers is False
    assert await check_customer_access(scoped, "any-customer") is False

    # Migration 19's statement, applied to a store that predates it.
    async with get_db() as conn:
        await conn.execute("DROP TABLE IF EXISTS finding_operations")
        await conn.execute("DROP TABLE IF EXISTS mfa_stepup")
        await conn.execute("DROP TABLE IF EXISTS user_mfa")
        await conn.execute("UPDATE schema_version SET version = 18 WHERE id = 1")
        await conn.commit()

    await run_migrations()
    reloaded = await get_user_by_id(scoped.id)
    assert reloaded.all_customers is False
    assert await check_customer_access(reloaded, "any-customer") is False


# ── New accounts join the pool by default ─────────────────────────────────────


async def test_a_new_account_has_no_customers_by_default(client):
    headers = await _admin_headers()
    r = client.post(
        "/api/auth/users",
        headers=headers,
        json={
            "username": "tech",
            "password": GOOD_PASSWORD,
            "display_name": "Tech",
            "role": "technician",
        },
    )
    assert r.status_code == 200, r.text
    created = await get_user_by_username("tech")
    assert created.all_customers is False
    assert await check_customer_access(created, "any-customer") is False


async def test_an_admin_can_still_create_a_restricted_account(client):
    headers = await _admin_headers()
    r = client.post(
        "/api/auth/users",
        headers=headers,
        json={
            "username": "scoped",
            "password": GOOD_PASSWORD,
            "display_name": "Scoped",
            "role": "technician",
            "all_customers": False,
        },
    )
    assert r.status_code == 200, r.text
    created = await get_user_by_username("scoped")
    assert created.all_customers is False
    # Restriction still works: no grant, no access.
    assert await check_customer_access(created, "any-customer") is False


# ── The primitive is unchanged (fail-closed for programmatic callers) ─────────


async def test_the_create_user_primitive_is_still_fail_closed():
    u = await create_user("prog", GOOD_PASSWORD, "Prog", role=Role.technician)
    assert u.all_customers is False, (
        "the create_user primitive must stay fail-closed; the pool default lives "
        "in the route, not here"
    )


async def test_http_customer_selection_replaces_the_global_grant(client):
    headers = await _admin_headers()
    response = client.post(
        "/api/auth/users",
        headers=headers,
        json={
            "username": "scopeme",
            "password": GOOD_PASSWORD,
            "display_name": "Scope me",
            "all_customers": True,
        },
    )
    assert response.status_code == 200
    user = await get_user_by_username("scopeme")
    url = f"/api/auth/users/{user.id}/customers"
    response = client.put(
        url,
        headers=headers,
        json={
            "access_mode": "scoped",
            "customer_ids": ["customer_a", "customer_a"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1
    user = await get_user_by_id(user.id)
    assert await check_customer_access(user, "customer_a")
    assert not await check_customer_access(user, "customer_b")
    assert client.get(url, headers=headers).json()["effective_access_mode"] == "scoped"

    response = client.put(url, headers=headers, json={"customer_ids": []})
    assert response.status_code == 200
    user = await get_user_by_id(user.id)
    assert not await check_customer_access(user, "customer_a")
    response = client.put(url, headers=headers, json={"access_mode": "all"})
    assert response.status_code == 200
    user = await get_user_by_id(user.id)
    assert await check_customer_access(user, "customer_b")


async def test_invalid_customer_access_body_does_not_change_grants(client):
    headers = await _admin_headers()
    user = await create_user("unchanged", GOOD_PASSWORD, "Unchanged", all_customers=True)
    response = client.put(
        f"/api/auth/users/{user.id}/customers",
        headers=headers,
        json={"access_mode": "all", "customer_ids": ["customer_a"]},
    )
    assert response.status_code == 400
    assert (await get_user_by_id(user.id)).all_customers
