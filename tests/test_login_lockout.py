"""Sign-in lockout, and the migration that has to survive being retried.

Before this existed, the only brake on password guessing was a per-IP rate
limit — and ``client_ip`` decides what "per IP" means, so a caller that could
influence X-Forwarded-For had no brake at all. The lockout is the half that
does not depend on getting the network attribution right.
"""

from __future__ import annotations

import time

import pytest

from app.core import auth
from app.core.database import get_db, run_migrations


@pytest.fixture
async def account(tmp_path, monkeypatch):
    """A real account in a throwaway database."""
    from app.core import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lockout.db")
    await database.close_pool()
    await run_migrations()
    user = await auth.create_user(
        username="tech",
        password="Korrekt-Hestebatteri-9!",
        display_name="Tech",
        role=auth.Role.technician,
    )
    yield user
    await database.close_pool()


async def test_the_right_password_signs_in(account):
    assert await auth.authenticate("tech", "Korrekt-Hestebatteri-9!") is not None


async def test_five_wrong_passwords_lock_the_account(account):
    for _ in range(auth._MAX_LOGIN_FAILURES):
        assert await auth.authenticate("tech", "feil-passord-1!") is None

    # The lock is the point: the *correct* password is now refused too.
    assert await auth.authenticate("tech", "Korrekt-Hestebatteri-9!") is None

    refreshed = await auth.get_user_by_id(account.id)
    assert refreshed.locked_until > time.time()


async def test_four_failures_do_not_lock(account):
    for _ in range(auth._MAX_LOGIN_FAILURES - 1):
        await auth.authenticate("tech", "feil-passord-1!")
    assert await auth.authenticate("tech", "Korrekt-Hestebatteri-9!") is not None


async def test_a_successful_sign_in_clears_the_counter(account):
    for _ in range(auth._MAX_LOGIN_FAILURES - 1):
        await auth.authenticate("tech", "feil-passord-1!")
    await auth.authenticate("tech", "Korrekt-Hestebatteri-9!")

    refreshed = await auth.get_user_by_id(account.id)
    assert refreshed.failures == 0
    assert refreshed.locked_until == 0


async def test_an_expired_lock_does_not_hand_back_another_free_five(account):
    """The counter is not reset by the lock expiring, only by signing in.

    Otherwise the lockout is a rate limit of five guesses per five minutes
    forever, rather than something an attacker has to stop at.
    """
    for _ in range(auth._MAX_LOGIN_FAILURES):
        await auth.authenticate("tech", "feil-passord-1!")

    async with get_db() as conn:
        await conn.execute(
            "UPDATE users SET locked_until = ? WHERE id = ?",
            (time.time() - 1, account.id),
        )
        await conn.commit()

    # One more wrong password re-locks immediately rather than starting over.
    assert await auth.authenticate("tech", "feil-passord-2!") is None
    refreshed = await auth.get_user_by_id(account.id)
    assert refreshed.failures == auth._MAX_LOGIN_FAILURES + 1
    assert refreshed.locked_until > time.time()


async def test_the_lockout_migration_can_be_run_twice(tmp_path, monkeypatch):
    """The runner retries a migration whose version bump failed.

    SQLite has no ``ADD COLUMN IF NOT EXISTS``, so a raw-SQL version of this
    migration raised "duplicate column name" on every subsequent boot and left
    the database stuck below the current schema version.
    """
    from app.core import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "twice.db")
    await database.close_pool()
    await run_migrations()

    async with get_db() as conn:
        await conn.execute("UPDATE schema_version SET version = 21")
        await conn.commit()

    await run_migrations()  # must not raise

    async with get_db() as conn, conn.execute("PRAGMA table_info(users)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    assert {"failures", "locked_until"} <= columns
    await database.close_pool()
