"""Tests for auth session management and token revocation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.auth import (
    _TOKEN_BLACKLIST,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_session,
    create_user,
    decode_token,
    delete_session,
    delete_user_sessions,
    validate_session,
)
from app.core.database import get_db, run_migrations
from app.models.user import Role, User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    """Create a fresh in-memory-style SQLite DB for each test."""
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture()
async def test_user() -> User:
    """Create a test user in the DB and return it."""
    return await create_user(
        username="testuser",
        password="Test1234!xyz",
        display_name="Test User",
        role=Role.technician,
    )


# ---------------------------------------------------------------------------
# Token creation & decoding
# ---------------------------------------------------------------------------

async def test_create_and_decode_access_token(test_user):
    token = await create_access_token(test_user, session_id="sess-123")
    payload = await decode_token(token)
    assert payload is not None
    assert payload.sub == test_user.id
    assert payload.session_id == "sess-123"
    assert payload.token_type == "access"


async def test_create_and_decode_refresh_token(test_user):
    token = await create_refresh_token(test_user, session_id="sess-456")
    payload = await decode_token(token)
    assert payload is not None
    assert payload.token_type == "refresh"
    assert payload.session_id == "sess-456"


async def test_token_without_session_id(test_user):
    token = await create_access_token(test_user)
    payload = await decode_token(token)
    assert payload is not None
    assert payload.session_id is None


# ---------------------------------------------------------------------------
# Token blacklisting
# ---------------------------------------------------------------------------

async def test_blacklist_token(test_user):
    token = await create_access_token(test_user)
    # Should decode fine before blacklisting
    assert await decode_token(token) is not None

    await blacklist_token(token)

    # Should return None after blacklisting
    assert await decode_token(token) is None

    # Cleanup
    _TOKEN_BLACKLIST.clear()


async def test_blacklist_token_persists_to_the_database(test_user):
    """The revocation must be durable, not fire-and-forget.

    It previously scheduled the write as a background task, so the caller
    returned before the row existed — and if the event loop shut down while
    that task was still connecting, aiosqlite's non-daemon worker thread was
    orphaned and hung interpreter exit.
    """
    import hashlib

    from app.core.database import get_db

    token = await create_access_token(test_user)
    await blacklist_token(token)
    _TOKEN_BLACKLIST.clear()  # force the lookup to hit the database

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    async with get_db() as conn:
        async with conn.execute(
            "SELECT 1 FROM token_blacklist WHERE token_hash = ?", (token_hash,)
        ) as cur:
            assert await cur.fetchone() is not None

    # And the revocation still holds when served from the database.
    assert await decode_token(token) is None
    _TOKEN_BLACKLIST.clear()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

async def test_create_and_validate_session(test_user):
    refresh = await create_refresh_token(test_user)
    sid = await create_session(test_user.id, refresh, ip_address="127.0.0.1")
    assert sid

    assert await validate_session(sid) is True


async def test_delete_session_invalidates(test_user):
    refresh = await create_refresh_token(test_user)
    sid = await create_session(test_user.id, refresh)

    await delete_session(sid)
    assert await validate_session(sid) is False


async def test_delete_user_sessions(test_user):
    r1 = await create_refresh_token(test_user)
    r2 = await create_refresh_token(test_user)
    sid1 = await create_session(test_user.id, r1)
    sid2 = await create_session(test_user.id, r2)

    count = await delete_user_sessions(test_user.id)
    assert count == 2
    assert await validate_session(sid1) is False
    assert await validate_session(sid2) is False


async def test_validate_nonexistent_session():
    assert await validate_session("nonexistent-id") is False


# ---------------------------------------------------------------------------
# JWT secret rotation + grace period
# ---------------------------------------------------------------------------

async def test_rotate_jwt_secret_keeps_old_tokens_within_grace(test_user):
    """Tokens signed with the old secret must verify for the grace window."""
    from app.core.auth import rotate_jwt_secret

    old_token = await create_access_token(test_user)
    assert await decode_token(old_token) is not None

    await rotate_jwt_secret()

    # Old token still verifies via the previous-secret fallback
    assert await decode_token(old_token) is not None
    # New tokens use the new secret and verify as well
    new_token = await create_access_token(test_user)
    assert await decode_token(new_token) is not None


async def test_rotate_jwt_secret_rejects_old_tokens_after_grace(test_user):
    """Past the grace window, previous secret is purged and old tokens fail."""
    from datetime import datetime, timedelta, timezone

    from app.core.auth import _put_secret_to_db, rotate_jwt_secret

    old_token = await create_access_token(test_user)
    await rotate_jwt_secret()

    # Simulate the grace period expiring by rewinding the marker
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    await _put_secret_to_db("jwt_secret_previous_expires_at", expired)

    assert await decode_token(old_token) is None
    # Current secret still works
    assert await decode_token(await create_access_token(test_user)) is not None


async def test_rotate_jwt_secret_backfills_legacy_previous(test_user):
    """Legacy previous-secret rows (no expiry marker) get a grace window on read."""
    from app.core.auth import (
        _delete_secret_from_db,
        _get_jwt_secret,
        _get_secret_from_db,
        _put_secret_to_db,
    )

    # Simulate pre-upgrade state: previous exists, expiry marker does not
    current = await _get_jwt_secret()
    await _put_secret_to_db("jwt_secret_previous", current)
    await _delete_secret_from_db("jwt_secret_previous_expires_at")

    old_token = await create_access_token(test_user)
    # Forcibly rotate jwt_secret to ensure old_token is only verifiable via previous
    import secrets as _secrets
    await _put_secret_to_db("jwt_secret", _secrets.token_urlsafe(64))

    # First decode should succeed AND backfill the expiry marker
    assert await decode_token(old_token) is not None
    backfilled = await _get_secret_from_db("jwt_secret_previous_expires_at")
    assert backfilled is not None
