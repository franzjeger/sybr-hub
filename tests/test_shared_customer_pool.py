"""This deployment runs a shared customer pool.

Customers are pulled from IT Glue and matched to Tenant / GDAP / ALSO / Uniweb,
and the synergy only works if every user can see every customer. So a human
account joins the pool by default: it sees every customer, while can_write /
tenant_write still decide what it may *do*.

The fail-closed primitive is deliberately left alone — create_user() still
defaults all_customers to False for programmatic and system callers (see
test_rbac). The pool is a product decision applied at two explicit points: the
admin create-user route (new accounts) and migration 19 (existing accounts).
Per-customer restriction stays available as an opt-in.
"""

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

async def test_migration_grants_the_pool_to_an_existing_scoped_account():
    # A user created through the fail-closed primitive starts scoped.
    scoped = await create_user("legacy", GOOD_PASSWORD, "Legacy", role=Role.technician)
    assert scoped.all_customers is False
    assert await check_customer_access(scoped, "any-customer") is False

    # Migration 19's statement, applied to a store that predates it.
    async with get_db() as conn:
        await conn.execute("UPDATE users SET all_customers = 1;")
        await conn.commit()

    reloaded = await get_user_by_id(scoped.id)
    assert reloaded.all_customers is True
    assert await check_customer_access(reloaded, "any-customer") is True


# ── New accounts join the pool by default ─────────────────────────────────────

async def test_a_new_account_sees_every_customer_by_default(client):
    headers = await _admin_headers()
    r = client.post("/api/auth/users", headers=headers, json={
        "username": "tech", "password": GOOD_PASSWORD, "display_name": "Tech",
        "role": "technician",
    })
    assert r.status_code == 200, r.text
    created = await get_user_by_username("tech")
    assert created.all_customers is True
    assert await check_customer_access(created, "any-customer") is True


async def test_an_admin_can_still_create_a_restricted_account(client):
    headers = await _admin_headers()
    r = client.post("/api/auth/users", headers=headers, json={
        "username": "scoped", "password": GOOD_PASSWORD, "display_name": "Scoped",
        "role": "technician", "all_customers": False,
    })
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
