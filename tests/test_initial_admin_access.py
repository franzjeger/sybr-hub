"""Upgrade repairs only the initial human admin, once, never every admin."""

from __future__ import annotations

import pytest

from app.core import database


@pytest.fixture(autouse=True)
async def _database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "upgrade.db")
    await database.run_migrations()


async def _seed(*, first_role="admin", first_active=1, tied_timestamps=False):
    async with database.get_db() as conn:
        # System account precedes the humans. UUID ordering deliberately
        # disagrees with insertion order, including when timestamps tie.
        for user_id, role, active, system, created in [
            ("system", "technician", 1, 1, "2026-01-01T00:00:00+00:00"),
            ("z-first", first_role, first_active, 0, "2026-02-01T00:00:00+00:00"),
            (
                "a-second",
                "admin",
                1,
                0,
                "2026-02-01T00:00:00+00:00" if tied_timestamps else "2026-03-01T00:00:00+00:00",
            ),
        ]:
            await conn.execute(
                "INSERT INTO users (id, username, display_name, password_hash, role, "
                "created_at, is_active, is_system, all_customers, can_write, tenant_write) "
                "VALUES (?, ?, ?, 'synthetic-hash', ?, ?, ?, ?, 0, 0, 0)",
                (user_id, user_id, user_id, role, created, active, system),
            )
        await conn.execute("UPDATE schema_version SET version = 28 WHERE id = 1")
        await conn.commit()


async def _grants():
    async with (
        database.get_db() as conn,
        conn.execute("SELECT id, all_customers, can_write, tenant_write FROM users") as cur,
    ):
        return {row[0]: tuple(row[1:]) for row in await cur.fetchall()}


@pytest.mark.parametrize("tied_timestamps", [False, True])
async def test_upgrade_restores_only_the_initial_human_admin(tied_timestamps):
    await _seed(tied_timestamps=tied_timestamps)
    await database.run_migrations()
    assert await _grants() == {
        "system": (0, 0, 0),
        "z-first": (1, 1, 1),
        "a-second": (0, 0, 0),
    }


@pytest.mark.parametrize("role,active", [("admin", 0), ("technician", 1), ("viewer", 1)])
async def test_upgrade_does_not_promote_a_disabled_or_demoted_first_user(role, active):
    await _seed(first_role=role, first_active=active)
    await database.run_migrations()
    assert all(grants == (0, 0, 0) for grants in (await _grants()).values())


async def test_repair_is_not_repeated_after_capabilities_are_revoked():
    await _seed()
    await database.run_migrations()
    async with database.get_db() as conn:
        await conn.execute("UPDATE users SET can_write = 0, tenant_write = 0 WHERE id = 'z-first'")
        await conn.commit()
    await database.run_migrations()
    assert (await _grants())["z-first"] == (1, 0, 0)


async def test_a_fresh_database_has_no_account_to_promote():
    assert await _grants() == {}
