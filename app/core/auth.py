"""Authentication core — password hashing, JWT tokens, user CRUD.

Uses argon2 for password hashing and PyJWT for JWT operations.
All user data lives in the SQLite database (see database.py).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast

import jwt  # PyJWT — import is `jwt`, package is `PyJWT`
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt import PyJWTError
from sqlalchemy import delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core import access_events
from app.core.messages import conflict
from app.core.orm import get_session
from app.core.password_work import run_password_work
from app.models.user import AppSecret, Role, TokenBlacklist, TokenPayload, User, UserSession

# ── Token blacklist (in-memory, survives until restart) ─────────────────────
# Access tokens are short-lived (60 min), so an in-memory set is sufficient.
# Capped to prevent unbounded growth.
_TOKEN_BLACKLIST: OrderedDict[str, datetime] = OrderedDict()
_BLACKLIST_MAX = 10000

logger = logging.getLogger(__name__)

# ── Password hashing ────────────────────────────────────────────────────────

# Argon2id parameters per OWASP 2024 recommendation:
#   time_cost (iterations) = 3
#   memory_cost            = 64 MiB
#   parallelism            = 4
# Explicit parameters keep the cost stable across library default changes.
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
)


# Turns off the breached-password lookup in validate_password(). See there.
ENV_DISABLE_HIBP = "SYBR_DISABLE_HIBP"

# Candidates that pass every rule above and are still the first thing anyone
# tries. The previous list was 8-9 character classics — "password", "welcome1",
# "qwerty123" — every one of which the length and character-class rules had
# already rejected several lines earlier, so not one entry could ever be
# reached. tests/test_password_policy.py fails if that happens again: an entry
# that another rule rejects first is dead weight pretending to be a control.
#
# Norwegian keyboard-walk and seasonal patterns are here because this is a
# Norwegian MSP: "Sommer2026!" is the local equivalent of "Summer2026!".
_COMMON_PASSWORDS = {
    "password1!",
    "password12!",
    "password123!",
    "passord123!",
    "passord12!",
    "welcome123!",
    "velkommen1!",
    "velkommen12!",
    "qwerty123!",
    "qwertyuiop1!",
    "admin1234!",
    "administrator1!",
    "changeme123!",
    "endremeg123!",
    "sommer2025!",
    "sommer2026!",
    "vinter2025!",
    "vinter2026!",
    "summer2025!",
    "summer2026!",
    "winter2025!",
    "winter2026!",
    "sybr2025!!",
    "sybr2026!!",
    "norge2026!",
    "oslo2026!!",
    "p@ssw0rd123",
    "p@ssword123",
    "l3tm31n123!",
    "1qaz2wsx3edc!",
}


async def validate_password(password: str) -> str | None:
    """Return an error message if password is too weak, else None."""
    if len(password) < 10:
        return "Passord må være minst 10 tegn"
    if len(password) > 128:
        return "Passord kan ikke være lengre enn 128 tegn"
    if not re.search(r"[a-zA-Z]", password):
        return "Passord må inneholde minst én bokstav"
    if not re.search(r"[0-9]", password):
        return "Passord må inneholde minst ett tall"
    if not re.search(r"[^a-zA-Z0-9]", password):
        return "Passord må inneholde minst ett spesialtegn"
    if password.lower() in _COMMON_PASSWORDS:
        return "Passordet er for vanlig — velg et sterkere passord"

    # Sjekk mot HaveIBeenPwned (k-anonymitet via k-Prefix).
    #
    # This is the one outbound call the toolkit makes without an integration
    # being configured, so it is opt-out rather than silent: an air-gapped
    # install, or one whose egress policy has to be declarable, sets
    # SYBR_DISABLE_HIBP=1 and keeps the rules above. Only the first five
    # characters of the SHA-1 leave the host — the password itself never does,
    # and the response is searched locally — but "a password is being set here,
    # now" is still an observable event, and an operator is entitled to decide
    # whether it leaves the building.
    if os.environ.get(ENV_DISABLE_HIBP) == "1":
        return None

    import hashlib

    import httpx

    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}")
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.startswith(suffix):
                        return (
                            "Passordet er funnet i en kjent datalekkasje. Vennligst velg et annet."
                        )
    except Exception as e:
        logger.warning("HIBP password check failed: %s", e)

    return None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hash: str) -> bool:
    try:
        return _ph.verify(hash, password)
    except VerifyMismatchError:
        return False


# ── JWT configuration ────────────────────────────────────────────────────────

# The secret is generated once per installation and persisted in the DB,
# encrypted with the master encryption key for protection at rest.
_JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
# How long the previous JWT secret stays valid after rotation. Bounds the
# window in which a leaked old secret could forge tokens; also gives in-
# flight tokens a soft landing instead of a hard cutover.
_JWT_SECRET_GRACE_SECONDS = 3600  # 1 hour


async def _get_secret_from_db(key: str) -> str | None:
    """Read a single secret from app_secrets, handling encryption/migration."""
    from app.core.encryption import decrypt_text, encrypt_text, is_encrypted

    async with get_session() as session:
        secret = await session.get(AppSecret, key)
        if not secret:
            return None

        stored = secret.value
        stored_bytes = stored.encode("utf-8") if isinstance(stored, str) else stored
        if is_encrypted(stored_bytes):
            return decrypt_text(stored_bytes)
        stored = stored_bytes.decode("utf-8")

        # Migrate plaintext to encrypted
        encrypted = encrypt_text(stored)
        secret.value = encrypted
        await session.commit()
        return stored


async def _put_secret_to_db(key: str, value: str) -> None:
    """Upsert a secret into app_secrets (encrypted).

    Two concurrent callers can both find no row (e.g. right after a fresh
    boot, when ``_get_jwt_secret()`` finds nothing and both create one), so
    this must be an atomic upsert rather than get-then-branch — the latter
    raises an unhandled IntegrityError on the second commit.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from app.core.encryption import encrypt_text

    encrypted = encrypt_text(value)
    async with get_session() as session:
        stmt = sqlite_insert(AppSecret).values(key=key, value=encrypted)
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": encrypted})
        await session.execute(stmt)
        await session.commit()
    _invalidate_secret_cache(key)


async def _delete_secret_from_db(key: str) -> None:
    """Remove a secret from app_secrets."""
    async with get_session() as session:
        secret = await session.get(AppSecret, key)
        if secret:
            await session.delete(secret)
            await session.commit()
    _invalidate_secret_cache(key)


# The signing secret is read for every token operation — i.e. on every
# authenticated request — and each read is a database round-trip plus an
# AES-GCM decrypt. It changes only when it is written, so cache it in-process
# and invalidate from the two write helpers above rather than from their
# callers: anything that stores or deletes a secret then cannot leave a stale
# entry behind, whether or not it went through rotate_jwt_secret().
#
# Keyed by database path so a test (or an MSP_DATA_DIR change) pointing at a
# different database never inherits the previous one's secret.
_secret_cache: dict[str, str] = {}


def _secret_cache_key(name: str) -> str:
    from app.core import database

    return f"{database.DB_PATH}|{name}"


def _invalidate_secret_cache(name: str) -> None:
    _secret_cache.pop(_secret_cache_key(name), None)


async def _get_jwt_secret() -> str:
    """Retrieve or generate the JWT signing secret (encrypted in DB)."""
    cache_key = _secret_cache_key("jwt_secret")
    cached = _secret_cache.get(cache_key)
    if cached:
        return cached

    secret = await _get_secret_from_db("jwt_secret")
    if not secret:
        # Insert only if absent, then read back whatever won. Two first
        # requests racing on a fresh database used to each store their own
        # secret; the loser kept signing with one the database no longer
        # held, and every token it issued answered 401.
        await _insert_secret_if_absent("jwt_secret", secrets.token_urlsafe(64))
        secret = await _get_secret_from_db("jwt_secret")
    if secret is None:
        raise RuntimeError("JWT signing secret was not persisted")
    _secret_cache[cache_key] = secret
    return secret


async def _insert_secret_if_absent(key: str, value: str) -> None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from app.core.encryption import encrypt_text

    async with get_session() as session:
        stmt = sqlite_insert(AppSecret).values(key=key, value=encrypt_text(value))
        await session.execute(stmt.on_conflict_do_nothing(index_elements=["key"]))
        await session.commit()
    _invalidate_secret_cache(key)


async def _get_jwt_secret_previous() -> str | None:
    """Retrieve the previous JWT secret if it's still within the grace window.

    After rotation, the old secret lingers for ``_JWT_SECRET_GRACE_SECONDS``
    so in-flight tokens keep verifying. Past that window, the old secret
    and its expiry marker are purged from the DB and ``None`` is returned —
    which causes ``decode_token()`` to reject tokens signed with it.

    For deployments that rotated before this grace-period mechanism existed
    (``jwt_secret_previous`` present but no expiry marker), a fresh grace
    window is backfilled so existing sessions get a smooth upgrade rather
    than a forced re-login on deploy.
    """
    previous = await _get_secret_from_db("jwt_secret_previous")
    if previous is None:
        return None
    expires_at_iso = await _get_secret_from_db("jwt_secret_previous_expires_at")
    if not expires_at_iso:
        # Legacy row from before grace period was enforced — backfill.
        grace_expires = datetime.now(UTC) + timedelta(seconds=_JWT_SECRET_GRACE_SECONDS)
        await _put_secret_to_db("jwt_secret_previous_expires_at", grace_expires.isoformat())
        logger.info(
            "jwt_secret_previous had no expiry marker; backfilled grace to %s",
            grace_expires.isoformat(),
        )
        return previous
    try:
        expires_at = datetime.fromisoformat(expires_at_iso)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
    except ValueError:
        logger.warning(
            "jwt_secret_previous_expires_at unparseable (%r); purging previous secret",
            expires_at_iso,
        )
        await _delete_secret_from_db("jwt_secret_previous")
        await _delete_secret_from_db("jwt_secret_previous_expires_at")
        return None
    if expires_at <= datetime.now(UTC):
        await _delete_secret_from_db("jwt_secret_previous")
        await _delete_secret_from_db("jwt_secret_previous_expires_at")
        logger.info("JWT previous secret grace period expired; purged")
        return None
    return previous


async def create_access_token(user: User, session_id: str | None = None) -> str:
    secret = await _get_jwt_secret()
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "token_type": "access",
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)


async def create_refresh_token(user: User, session_id: str | None = None) -> str:
    secret = await _get_jwt_secret()
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "token_type": "refresh",
        # Without it, two refresh tokens minted for one session in the same
        # second are byte-identical, so rotating would not retire the old one.
        "jti": secrets.token_urlsafe(16),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)


async def decode_token(token: str) -> TokenPayload | None:
    """Decode and validate a JWT token.  Returns None on failure.

    Tries the current secret first; if that fails and a previous secret
    exists (from key rotation), falls back to that.
    Checks the in-memory blacklist for revoked tokens.
    """
    # Blacklist check (hash the token to avoid storing raw JWTs).
    # Hits the in-memory cache first, then the persisted table so revocations
    # survive a server restart.
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if await _is_blacklisted(token_hash):
        return None

    for secret_coro in (_get_jwt_secret, _get_jwt_secret_previous):
        try:
            secret = await secret_coro()
            if secret is None:
                continue
            data = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
            return TokenPayload(
                sub=data["sub"],
                username=data["username"],
                role=Role(data["role"]),
                exp=datetime.fromtimestamp(data["exp"], tz=UTC),
                iat=datetime.fromtimestamp(data["iat"], tz=UTC),
                token_type=data.get("token_type", "access"),
                session_id=data.get("sid"),
            )
        except (PyJWTError, KeyError, ValueError):
            continue
    logger.debug("Token decode failed with all available secrets")
    return None


# ── Session management ──────────────────────────────────────────────────────


async def create_session(
    user_id: str,
    refresh_token: str,
    ip_address: str = "",
    user_agent: str = "",
    session_id: str | None = None,
) -> str:
    """Create a new session record. Returns the session ID.

    Pass *session_id* when the caller has already embedded it in the token
    being stored, so the record's hash matches the token the client holds.
    """
    session_id = session_id or str(uuid.uuid4())
    token_hash = _token_hash(refresh_token)
    now = datetime.now(UTC)
    expires = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    db_session = UserSession(
        id=session_id,
        user_id=user_id,
        refresh_token_hash=token_hash,
        created_at=now,
        expires_at=expires,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    async with get_session() as session:
        session.add(db_session)
        await session.commit()
    return session_id


async def delete_session(session_id: str) -> None:
    """Delete a session (logout)."""
    async with get_session() as session:
        db_session = await session.get(UserSession, session_id)
        if db_session:
            await session.delete(db_session)
            await session.commit()
            access_events.invalidate(session_id=session_id)


async def delete_user_sessions(user_id: str, *, except_session_id: str | None = None) -> int:
    """Delete a user's sessions (force logout everywhere). Returns count.

    *except_session_id* survives, so a user acting on their own account is not
    signed out of the tab they did it from.
    """
    async with get_session() as session:
        revoked = await _delete_sessions_of(session, user_id, except_session_id)
        await session.commit()
    _announce_revoked(user_id, revoked, except_session_id)
    return len(revoked)


async def _delete_sessions_of(
    session: AsyncSession, user_id: str, except_session_id: str | None
) -> list[str]:
    stmt = delete(UserSession).where(col(UserSession.user_id) == user_id)
    if except_session_id:
        stmt = stmt.where(col(UserSession.id) != except_session_id)
    result = await session.execute(stmt.returning(col(UserSession.id)))
    return list(result.scalars().all())


def _announce_revoked(user_id: str, revoked: list[str], kept_session_id: str | None) -> None:
    if kept_session_id is None:
        access_events.invalidate(user_id=user_id)
        return
    # Per session, or the sockets of the session being kept would close too.
    for session_id in revoked:
        access_events.invalidate(session_id=session_id)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def validate_session(session_id: str) -> bool:
    """Check if a session exists and hasn't expired."""
    async with get_session() as session:
        result = await session.execute(
            select(col(UserSession.expires_at)).where(col(UserSession.id) == session_id)
        )
        expires = result.scalar_one_or_none()
        if not expires:
            return False
        return _as_utc(expires) > datetime.now(UTC)


# ── Refresh-token rotation ──────────────────────────────────────────────────

# How long the refresh token a rotation replaced is still honoured. Two
# requests from one browser can carry the same cookie before the first
# response's Set-Cookie lands (two tabs, or the keepalive timer racing a 401
# recovery); without this the second looks like a replay and signs the user
# out. A late request gets an access token only, never a new refresh token.
REFRESH_REUSE_GRACE_SECONDS = 30

# session id -> (hash of the refresh token the latest rotation replaced, when).
# In-process is enough: the supported deployment runs one worker, and losing
# this on restart can only cost a late duplicate its grace, never grant one.
_replaced_refresh: dict[str, tuple[str, float]] = {}


class RefreshResult(StrEnum):
    ROTATED = "rotated"  # the presented token was current and has been replaced
    GRACE = "grace"  # the token the last rotation replaced, inside the grace window
    INVALID = "invalid"  # no such live session for this user
    REUSED = "reused"  # a retired token: the session has been revoked


def _remember_replaced(session_id: str, token_hash: str) -> None:
    now = time.monotonic()
    for stale in [
        sid for sid, (_, at) in _replaced_refresh.items() if now - at >= REFRESH_REUSE_GRACE_SECONDS
    ]:
        del _replaced_refresh[stale]
    _replaced_refresh[session_id] = (token_hash, now)


def _within_grace(session_id: str, token_hash: str) -> bool:
    entry = _replaced_refresh.get(session_id)
    if entry is None or time.monotonic() - entry[1] >= REFRESH_REUSE_GRACE_SECONDS:
        return False
    return hmac.compare_digest(entry[0], token_hash)


async def rotate_refresh_token(
    session_id: str, user_id: str, presented: str, replacement: str
) -> RefreshResult:
    """Replace the session's refresh token with *replacement* if *presented* is current.

    A session accepts exactly one refresh token: the one whose hash it stores.
    Anything else that still carries a valid signature is a token an earlier
    refresh retired. Inside the grace window that is a duplicate request from
    the same browser; past it, two parties hold the session's tokens and there
    is no telling which one is legitimate, so the session is revoked for both.
    """
    presented_hash = _token_hash(presented)
    async with get_session() as session:
        row = (
            await session.execute(
                select(
                    UserSession.user_id,
                    UserSession.expires_at,
                    UserSession.refresh_token_hash,
                ).where(col(UserSession.id) == session_id)
            )
        ).first()
        if row is None or row.user_id != user_id or _as_utc(row.expires_at) <= datetime.now(UTC):
            return RefreshResult.INVALID

        if hmac.compare_digest(row.refresh_token_hash, presented_hash):
            # Recorded before the write, so a concurrent refresh with the same
            # token that loses the compare-and-swap below finds it whichever
            # of the two coroutines resumes first.
            _remember_replaced(session_id, presented_hash)
            swapped = await session.execute(
                update(UserSession)
                .where(
                    col(UserSession.id) == session_id,
                    col(UserSession.refresh_token_hash) == presented_hash,
                )
                .values(refresh_token_hash=_token_hash(replacement))
            )
            await session.commit()
            if cast(CursorResult[Any], swapped).rowcount == 1:
                return RefreshResult.ROTATED

    if _within_grace(session_id, presented_hash):
        # Re-checked because the request that won may have been a logout.
        return RefreshResult.GRACE if await validate_session(session_id) else RefreshResult.INVALID

    logger.warning("Retired refresh token presented for session %s; revoking it", session_id)
    await delete_session(session_id)
    return RefreshResult.REUSED


def _blacklist_in_memory(token: str) -> tuple[str, datetime]:
    """Record the revocation in the hot cache. Returns (token_hash, expires).

    Token expiry is computed by decoding the token (without verifying — we
    only need the exp claim, not authenticity, since this is a defensive
    record of "operator chose to log out"). Falls back to ACCESS_TOKEN_EXPIRE
    if the claim isn't readable.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(UTC)

    expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    try:
        # options={"verify_signature": False} — we already trust the caller,
        # we just want the exp timestamp.
        claims = jwt.decode(token, options={"verify_signature": False})
        exp_ts = claims.get("exp")
        if exp_ts:
            expires = datetime.fromtimestamp(exp_ts, tz=UTC)
    except Exception:
        # Unreadable exp just means the blacklist entry gets the default TTL.
        logger.debug("Could not read exp claim from token being blacklisted", exc_info=True)

    _TOKEN_BLACKLIST[token_hash] = expires
    while len(_TOKEN_BLACKLIST) > _BLACKLIST_MAX:
        _TOKEN_BLACKLIST.popitem(last=False)
    return token_hash, expires


async def blacklist_token(token: str) -> None:
    """Revoke a token in the hot cache and persist it so the revocation
    survives a process restart.

    The persist is awaited rather than fired into the background. Two reasons:
    a revocation that is only *probably* written is not a revocation, and an
    un-awaited database write outlives the caller — if the event loop shuts
    down while that task is still connecting, aiosqlite's worker thread is
    orphaned and, being non-daemon, hangs interpreter exit indefinitely. That
    is what wedged the test suite here.
    """
    token_hash, expires = _blacklist_in_memory(token)
    access_events.invalidate(token_hash=token_hash)
    await _persist_blacklist_entry(token_hash, expires)


def blacklist_token_sync(token: str) -> None:
    """Revoke a token from synchronous code.

    Runs the persist to completion on a private event loop, so no task
    outlives this call. Prefer the async ``blacklist_token`` where possible.
    """
    import asyncio

    token_hash, expires = _blacklist_in_memory(token)
    access_events.invalidate(token_hash=token_hash)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(_persist_blacklist_entry(token_hash, expires))
        except Exception as e:
            logger.warning("Failed to persist token blacklist entry: %s", e)
        return

    # Called from inside a running loop: asyncio.run() would fail and
    # scheduling a background task is what caused the orphaned-thread hang.
    # The in-memory revocation already applies to this process; the caller
    # should await blacklist_token() to make it durable.
    logger.warning(
        "blacklist_token_sync() called from a running event loop — revocation "
        "applied in memory only. Await blacklist_token() instead to persist it."
    )


async def _persist_blacklist_entry(token_hash: str, expires: datetime) -> None:
    try:
        async with get_session() as session:
            entry = await session.get(TokenBlacklist, token_hash)
            if entry:
                entry.expires_at = expires
            else:
                entry = TokenBlacklist(token_hash=token_hash, expires_at=expires)
                session.add(entry)
            await session.commit()
    except Exception as e:
        logger.warning("token_blacklist persist failed for %s...: %s", token_hash[:8], e)


async def _is_blacklisted(token_hash: str) -> bool:
    """Check both the in-memory cache and the persisted table."""
    if token_hash in _TOKEN_BLACKLIST:
        return True
    try:
        async with get_session() as session:
            now = datetime.now(UTC)
            # In SQLite, dates are strings, but SQLModel/SQLAlchemy can handle comparisons if correctly typed.
            # We'll just fetch the expires_at and check it.
            result = await session.execute(
                select(TokenBlacklist.expires_at).where(TokenBlacklist.token_hash == token_hash)
            )
            expires = result.scalar_one_or_none()
            if expires:
                if isinstance(expires, str):
                    expires = datetime.fromisoformat(expires)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires > now:
                    with __import__("contextlib").suppress(Exception):
                        _TOKEN_BLACKLIST[token_hash] = expires
                    return True
    except Exception as e:
        logger.debug("token_blacklist lookup failed: %s", e)
    return False


async def cleanup_expired_sessions() -> int:
    """Remove expired sessions. Called periodically."""
    async with get_session() as session:
        # Note: SQLite stores datetime as ISO strings. We can query by formatted string.
        result = await session.execute(
            delete(UserSession).where(col(UserSession.expires_at) < datetime.now(UTC))
        )
        await session.commit()
        return cast(CursorResult[Any], result).rowcount


async def rotate_jwt_secret() -> None:
    """Rotate the JWT signing secret.

    Moves the current secret to ``jwt_secret_previous`` with a bounded
    ``_JWT_SECRET_GRACE_SECONDS`` grace window, then generates a fresh
    current secret. Tokens signed with the old secret keep verifying until
    the grace window elapses, after which the old secret is purged and
    those tokens stop verifying.
    """
    current = await _get_jwt_secret()
    grace_expires = datetime.now(UTC) + timedelta(seconds=_JWT_SECRET_GRACE_SECONDS)
    await _put_secret_to_db("jwt_secret_previous", current)
    await _put_secret_to_db("jwt_secret_previous_expires_at", grace_expires.isoformat())
    new_secret = secrets.token_urlsafe(64)
    await _put_secret_to_db("jwt_secret", new_secret)
    logger.info(
        "JWT signing secret rotated; previous secret valid until %s",
        grace_expires.isoformat(),
    )


# ── User CRUD ────────────────────────────────────────────────────────────────


async def get_user_count() -> int:
    """Number of *human* accounts. Used only for first-run detection.

    Excludes the non-interactive system account: it is created at startup, so
    counting it would make a fresh install look already set up — closing the
    setup endpoints before the first human admin exists, and refusing the very
    request that creates that admin. First-run means "no human has set the hub
    up", not "the users table is empty".
    """
    from sqlalchemy import func

    async with get_session() as session:
        result = await session.execute(
            select(func.count(col(User.id))).where(col(User.is_system).is_(False))
        )
        return result.scalar() or 0


async def get_user_by_id(user_id: str) -> User | None:
    async with get_session() as session:
        return await session.get(User, user_id)


async def get_user_by_username(username: str) -> User | None:
    async with get_session() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


async def get_password_hash(username: str) -> str | None:
    async with get_session() as session:
        result = await session.execute(select(User.password_hash).where(User.username == username))
        return result.scalar_one_or_none()


async def create_user(
    username: str,
    password: str,
    display_name: str,
    role: Role = Role.technician,
    email: str | None = None,
    all_customers: bool = False,
) -> User:
    """Create a user.

    ``all_customers`` defaults to False, so a new account starts scoped to
    whatever customers an admin assigns it. (Admins bypass the check outright,
    so the flag is irrelevant for them.)
    """
    from app.core.exceptions import ValidationError

    pw_err = await validate_password(password)
    if pw_err:
        raise ValidationError(pw_err)
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    pw_hash = await run_password_work(hash_password, password)
    user = User(
        id=user_id,
        username=username,
        display_name=display_name,
        email=email,
        password_hash=pw_hash,
        role=role,
        created_at=datetime.fromisoformat(now),
        is_active=True,
        all_customers=all_customers,
    )
    async with get_session() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def create_initial_admin(
    username: str,
    password: str,
    display_name: str,
    email: str | None = None,
) -> User:
    """Atomically create the first-run administrator with full access."""
    from app.core.exceptions import ValidationError

    pw_err = await validate_password(password)
    if pw_err:
        raise ValidationError(pw_err)
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    pw_hash = await run_password_work(hash_password, password)

    user = User(
        id=user_id,
        username=username,
        display_name=display_name,
        email=email,
        password_hash=pw_hash,
        role=Role.admin,
        created_at=datetime.fromisoformat(now),
        is_active=True,
        all_customers=True,
        can_write=True,
        tenant_write=True,
    )

    async with get_session() as session:
        # Check if setup is already done. We use BEGIN IMMEDIATE to serialize this check
        # across processes and prevent race conditions.
        from sqlalchemy import text

        try:
            # SQLAlchemy already began a transaction, we can't emit BEGIN directly without errors.
            # Instead we commit the default implicit transaction, then begin immediate.
            await session.commit()
            await session.execute(text("BEGIN IMMEDIATE"))
        except Exception as e:
            await session.rollback()
            raise conflict("err_setup_in_progress") from e

        from sqlalchemy import func

        result = await session.execute(
            select(func.count(col(User.id))).where(col(User.is_system).is_(False))
        )
        count = result.scalar() or 0
        if count > 0:
            await session.rollback()
            raise conflict("err_setup_already_done")

        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


ALLOWED_USER_FIELDS = {"display_name", "email", "role", "is_active"}


async def update_user(
    user_id: str,
    display_name: str | None = None,
    email: str | None = None,
    role: Role | None = None,
    is_active: bool | None = None,
) -> User | None:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None

        if display_name is not None:
            user.display_name = display_name
        if email is not None:
            user.email = email
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active

        await session.commit()
        await session.refresh(user)
        access_events.invalidate(user_id=user_id)
        return user


async def change_password(
    user_id: str, new_password: str, *, keep_session_id: str | None = None
) -> int:
    """Set a new password and sign the account out everywhere else.

    Changing a password is how somebody evicts whoever else knows the old one,
    and a 30-day refresh token outlives the password it was issued against.
    Every session except *keep_session_id* is deleted in the same transaction.
    That retires its refresh token, and every access token bound to it, since
    the auth middleware and the WebSocket guard both refuse a token whose
    session is gone. With no session to keep (an administrator resetting
    someone else's password) all of them go.

    Returns the number of sessions revoked.
    """
    from app.core.exceptions import ValidationError

    pw_err = await validate_password(new_password)
    if pw_err:
        raise ValidationError(pw_err)
    pw_hash = await run_password_work(hash_password, new_password)
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return 0
        user.password_hash = pw_hash
        revoked = await _delete_sessions_of(session, user_id, keep_session_id)
        await session.commit()
    _announce_revoked(user_id, revoked, keep_session_id)
    return len(revoked)


async def delete_user(user_id: str) -> bool:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
            await session.commit()
            access_events.invalidate(user_id=user_id)
            return True
        return False


async def list_users() -> list[User]:
    async with get_session() as session:
        result = await session.execute(select(User).order_by(col(User.created_at)))
        return list(result.scalars().all())


async def update_last_login(user_id: str) -> None:
    now = datetime.now(UTC)
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.last_login = now
            await session.commit()


# ── Authenticate ─────────────────────────────────────────────────────────────

# A pre-computed hash of a random value, verified against when the username
# doesn't exist. Without it, a missing user returns in microseconds while a
# real one costs a full Argon2 verify — a timing oracle for enumerating
# usernames. The password is never known, so this always fails.
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(32))

# Five wrong passwords, then five minutes. ``failures`` is deliberately not
# reset when the lock expires, so the sixth attempt locks again immediately
# rather than handing back another free run of five — the same shape
# ``app.core.mfa`` uses for one-time codes.
_MAX_LOGIN_FAILURES = 5
_LOGIN_LOCK_SECONDS = 300


async def _record_login_failure(user_id: str) -> None:
    now = time.time()
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return
        failures = user.failures + 1
        user.failures = failures
        user.locked_until = now + _LOGIN_LOCK_SECONDS if failures >= _MAX_LOGIN_FAILURES else 0
        await session.commit()


async def _reset_login_failures(user_id: str) -> None:
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.failures = 0
            user.locked_until = 0
            await session.commit()


async def authenticate(username: str, password: str) -> User | None:
    """Verify credentials and return the user, or None."""
    user = await get_user_by_username(username)
    pw_hash = await get_password_hash(username)

    if user and user.locked_until > time.time():
        # Equalise timing even if locked, though not strictly required
        await run_password_work(verify_password, password, _DUMMY_HASH)
        logger.warning("Refused sign-in for locked account %r", username)
        return None

    if not pw_hash:
        await run_password_work(verify_password, password, _DUMMY_HASH)  # equalise timing
        return None

    if not await run_password_work(verify_password, password, pw_hash):
        if user:
            await _record_login_failure(user.id)
        return None

    if user and not user.is_active:
        return None
    if user and user.is_system:
        # An account with no human behind it is an identity for attribution and
        # locking, not a second way through the front door. Refused after the
        # password check so this reveals nothing a wrong password would not.
        logger.warning("Refused interactive sign-in for system account %r", username)
        return None
    if user:
        await _reset_login_failures(user.id)
        await update_last_login(user.id)
    return user


# ── Helpers ──────────────────────────────────────────────────────────────────
#
# No _row_to_user() here: the ORM (app.core.orm.get_session) constructs User
# instances directly from SQLModel queries, so there's no raw row to convert.
