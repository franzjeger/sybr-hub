"""Tests for per-customer RBAC."""

from __future__ import annotations

import pytest

import app.core.database as db_mod
from app.core.auth import create_user
from app.core.database import run_migrations
from app.core.rbac import (
    check_customer_access,
    filter_customers,
    get_accessible_customer_ids,
    get_user_customer_ids,
    grant_access,
    revoke_access,
    set_user_customers,
)
from app.models.user import Role, User


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
async def admin_user() -> User:
    return await create_user(
        username="admin", password="Admin123!xyz", display_name="Admin", role=Role.admin,
    )


@pytest.fixture()
async def tech_user() -> User:
    return await create_user(
        username="tech", password="Tech1234!xyz", display_name="Tech", role=Role.technician,
    )


# ---------------------------------------------------------------------------
# Admin bypass
# ---------------------------------------------------------------------------

async def test_admin_always_has_access(admin_user):
    assert await check_customer_access(admin_user, "any-customer") is True


async def test_admin_accessible_returns_none(admin_user):
    result = await get_accessible_customer_ids(admin_user)
    assert result is None  # None = no restrictions


# ---------------------------------------------------------------------------
# Unassigned technician — fails closed
# ---------------------------------------------------------------------------

async def test_unassigned_tech_has_no_access(tech_user):
    """A technician with no assignments sees nothing.

    This previously asserted the opposite: an empty customer_access table meant
    "unrestricted", so forgetting to assign customers granted access to every
    one of them. Access is now an explicit grant (users.all_customers or a
    customer_access row), so a mis-configuration fails closed.
    """
    assert await check_customer_access(tech_user, "any-customer") is False
    assert await get_accessible_customer_ids(tech_user) == set()


async def test_all_customers_grant_restores_unrestricted_access(tech_user):
    """The explicit grant is what existing installs are migrated onto."""
    from app.core.auth import get_user_by_id
    from app.core.rbac import set_all_customers

    await set_all_customers(tech_user.id, True)
    reloaded = await get_user_by_id(tech_user.id)

    assert reloaded.all_customers is True
    assert await check_customer_access(reloaded, "any-customer") is True
    assert await get_accessible_customer_ids(reloaded) is None


async def test_all_customers_grant_is_revocable(tech_user):
    from app.core.auth import get_user_by_id
    from app.core.rbac import set_all_customers

    await set_all_customers(tech_user.id, True)
    await set_all_customers(tech_user.id, False)
    reloaded = await get_user_by_id(tech_user.id)

    assert reloaded.all_customers is False
    assert await check_customer_access(reloaded, "any-customer") is False


async def test_migration_defaults_existing_accounts_to_unrestricted():
    """Migration 14 must not lock out accounts created before it ran.

    Rows that predate the column get all_customers = 1, preserving exactly the
    access they had under the old "no rows means everything" rule.
    """
    import uuid
    from datetime import datetime, timezone

    from app.core.auth import get_user_by_id
    from app.core.database import get_db

    # Insert without the new column, as a pre-migration row would have been.
    user_id = str(uuid.uuid4())
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO users (id, username, display_name, password_hash, role, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, "legacy", "Legacy", "x", "technician",
             datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()

    legacy = await get_user_by_id(user_id)
    assert legacy.all_customers is True
    assert await check_customer_access(legacy, "any-customer") is True


async def test_new_accounts_are_scoped_by_default(tech_user):
    """create_user() defaults all_customers to False."""
    assert tech_user.all_customers is False


# ---------------------------------------------------------------------------
# Technician with RBAC configured
# ---------------------------------------------------------------------------

async def test_grant_and_check_access(tech_user):
    await grant_access(tech_user.id, "cust-1")
    assert await check_customer_access(tech_user, "cust-1") is True
    assert await check_customer_access(tech_user, "cust-2") is False


async def test_revoke_access(tech_user):
    await grant_access(tech_user.id, "cust-1")
    await grant_access(tech_user.id, "cust-2")
    await revoke_access(tech_user.id, "cust-1")

    assert await check_customer_access(tech_user, "cust-1") is False
    assert await check_customer_access(tech_user, "cust-2") is True


async def test_set_user_customers(tech_user):
    await set_user_customers(tech_user.id, ["a", "b", "c"])
    ids = await get_user_customer_ids(tech_user.id)
    assert set(ids) == {"a", "b", "c"}

    # Replace
    await set_user_customers(tech_user.id, ["x"])
    ids = await get_user_customer_ids(tech_user.id)
    assert ids == ["x"]


async def test_get_accessible_customer_ids(tech_user):
    await grant_access(tech_user.id, "cust-a")
    await grant_access(tech_user.id, "cust-b")
    result = await get_accessible_customer_ids(tech_user)
    assert result == {"cust-a", "cust-b"}


# ---------------------------------------------------------------------------
# filter_customers helper
# ---------------------------------------------------------------------------

def test_filter_customers_none_returns_all():
    customers = [{"_id": "a"}, {"_id": "b"}]
    assert filter_customers(customers, None) == customers


def test_filter_customers_with_set():
    customers = [{"_id": "a"}, {"_id": "b"}, {"_id": "c"}]
    result = filter_customers(customers, {"a", "c"})
    assert len(result) == 2
    assert result[0]["_id"] == "a"
    assert result[1]["_id"] == "c"


def test_filter_customers_empty_set():
    customers = [{"_id": "a"}, {"_id": "b"}]
    assert filter_customers(customers, set()) == []
