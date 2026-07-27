"""Schema migration tests.

Migration 14 adds a column, which SQLite cannot express idempotently
(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` does not exist). The runner
re-attempts a migration whose version bump failed, so it has to be safe to
run twice — and it must not lock existing accounts out of their customers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

import app.core.database as db_mod
from app.core.database import _MIGRATIONS, SCHEMA_VERSION, get_db, run_migrations


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    db_mod.DB_PATH = tmp_path / "test.db"
    yield


async def _columns(table: str) -> set[str]:
    async with get_db() as conn:
        async with conn.execute(f"PRAGMA table_info({table})") as cur:
            return {row[1] for row in await cur.fetchall()}


async def _version() -> int:
    async with get_db() as conn:
        async with conn.execute("SELECT version FROM schema_version WHERE id = 1") as cur:
            return (await cur.fetchone())[0]


async def _apply_up_to(target: int) -> None:
    """Run migrations only up to *target*, simulating an older install."""
    async with get_db() as conn:
        for version, _desc, body in _MIGRATIONS:
            if version > target:
                break
            if callable(body):
                await body(conn)
            else:
                await conn.executescript(body)
            await conn.execute(
                "UPDATE schema_version SET version = ? WHERE id = 1", (version,)
            )
            await conn.commit()


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


async def test_fresh_database_reaches_current_version():
    await run_migrations()
    assert await _version() == SCHEMA_VERSION


async def test_migration_versions_are_unique_and_ordered():
    versions = [v for v, _, _ in _MIGRATIONS]
    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))
    assert versions[-1] == SCHEMA_VERSION, "SCHEMA_VERSION must match the last migration"


async def test_running_migrations_twice_is_a_no_op():
    await run_migrations()
    await run_migrations()  # must not raise
    assert await _version() == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Migration 14 — the upgrade path that matters
# ---------------------------------------------------------------------------


async def test_upgrade_from_v13_adds_the_column():
    await _apply_up_to(13)
    assert "all_customers" not in await _columns("users")
    assert await _version() == 13

    await run_migrations()

    assert "all_customers" in await _columns("users")
    assert await _version() == SCHEMA_VERSION


async def test_upgrade_from_v13_keeps_existing_accounts_unrestricted():
    """An account that predates the column must not lose access on upgrade.

    Before migration 14 an empty customer_access table meant 'all customers'.
    Defaulting the new column to 1 carries that forward, so upgrading does not
    silently cut every technician off from every customer.
    """
    await _apply_up_to(13)

    user_id = str(uuid.uuid4())
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO users (id, username, display_name, password_hash, role, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, "legacy", "Legacy", "hash", "technician",
             datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()

    await run_migrations()

    from app.core.auth import get_user_by_id
    from app.core.rbac import check_customer_access

    user = await get_user_by_id(user_id)
    assert user.all_customers is True
    assert await check_customer_access(user, "any-customer") is True


async def test_add_column_migration_is_rerunnable():
    """The runner retries a migration whose version bump failed."""
    from app.core.database import _add_all_customers_column

    await run_migrations()
    async with get_db() as conn:
        await _add_all_customers_column(conn)  # must not raise on second run
        await _add_all_customers_column(conn)
    assert "all_customers" in await _columns("users")


async def test_accounts_created_after_the_migration_are_scoped():
    """New accounts start with no blanket grant, unlike migrated ones."""
    from app.core.auth import create_user
    from app.core.rbac import check_customer_access
    from app.models.user import Role

    await run_migrations()
    user = await create_user("tech", "Test1234!xyz", "Tech", role=Role.technician)

    assert user.all_customers is False
    assert await check_customer_access(user, "any-customer") is False
