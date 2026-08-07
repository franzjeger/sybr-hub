"""Authentication core — password hashing, JWT tokens, user CRUD.

Uses argon2 for password hashing and PyJWT for JWT operations.
All user data lives in the SQLite database (see database.py).
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # PyJWT — import is `jwt`, package is `PyJWT`
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt import PyJWTError

from app.core.database import get_db
from app.models.user import Role, TokenPayload, User

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
# argon2-cffi defaults are weaker (t=2, m=64 MiB, p=1) for backwards compat
# but the explicit knobs here lock in a target hardness independent of the
# library's defaults moving forward.
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
)


_COMMON_PASSWORDS = {
    "password", "12345678", "123456789", "1234567890", "qwerty123",
    "admin123", "welcome1", "changeme", "letmein1", "master12",
    "password1", "iloveyou", "trustno1", "sunshine1", "princess1",
    "football1", "charlie1", "shadow12", "monkey12", "dragon12",
}


def validate_password(password: str) -> str | None:
    """Return an error message if password is too weak, else None."""
    if len(password) < 10:
        return "Passord må være minst 10 tegn"
    if len(password) > 128:
        return "Passord kan ikke være lengre enn 128 tegn"
    if not re.search(r'[a-zA-Z]', password):
        return "Passord må inneholde minst én bokstav"
    if not re.search(r'[0-9]', password):
        return "Passord må inneholde minst ett tall"
    if not re.search(r'[^a-zA-Z0-9]', password):
        return "Passord må inneholde minst ett spesialtegn"
    if password.lower() in _COMMON_PASSWORDS:
        return "Passordet er for vanlig — velg et sterkere passord"
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


async def _get_secret_from_db(key: str) -> Optional[str]:
    """Read a single secret from app_secrets, handling encryption/migration."""
    from app.core.encryption import decrypt_text, encrypt_text, is_encrypted
    async with get_db() as conn:
        async with conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            stored = row[0]
            if is_encrypted(stored.encode("utf-8") if isinstance(stored, str) else stored):
                return decrypt_text(stored)
            # Migrate plaintext to encrypted
            encrypted = encrypt_text(stored)
            await conn.execute(
                "UPDATE app_secrets SET value = ? WHERE key = ?",
                (encrypted, key),
            )
            await conn.commit()
            return stored


async def _put_secret_to_db(key: str, value: str) -> None:
    """Upsert a secret into app_secrets (encrypted)."""
    from app.core.encryption import encrypt_text
    encrypted = encrypt_text(value)
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO app_secrets (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, encrypted),
        )
        await conn.commit()
    _invalidate_secret_cache(key)


async def _delete_secret_from_db(key: str) -> None:
    """Remove a secret from app_secrets."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM app_secrets WHERE key = ?", (key,))
        await conn.commit()
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
        # Generate and store encrypted (this invalidates, so cache after).
        secret = secrets.token_urlsafe(64)
        await _put_secret_to_db("jwt_secret", secret)
    _secret_cache[cache_key] = secret
    return secret


async def _get_jwt_secret_previous() -> Optional[str]:
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
        grace_expires = datetime.now(timezone.utc) + timedelta(seconds=_JWT_SECRET_GRACE_SECONDS)
        await _put_secret_to_db("jwt_secret_previous_expires_at", grace_expires.isoformat())
        logger.info(
            "jwt_secret_previous had no expiry marker; backfilled grace to %s",
            grace_expires.isoformat(),
        )
        return previous
    try:
        expires_at = datetime.fromisoformat(expires_at_iso)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning(
            "jwt_secret_previous_expires_at unparseable (%r); purging previous secret",
            expires_at_iso,
        )
        await _delete_secret_from_db("jwt_secret_previous")
        await _delete_secret_from_db("jwt_secret_previous_expires_at")
        return None
    if expires_at <= datetime.now(timezone.utc):
        await _delete_secret_from_db("jwt_secret_previous")
        await _delete_secret_from_db("jwt_secret_previous_expires_at")
        logger.info("JWT previous secret grace period expired; purged")
        return None
    return previous


async def create_access_token(user: User, session_id: str | None = None) -> str:
    secret = await _get_jwt_secret()
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "token_type": "refresh",
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)


async def decode_token(token: str) -> Optional[TokenPayload]:
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
                exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
                iat=datetime.fromtimestamp(data["iat"], tz=timezone.utc),
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
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, user_id, refresh_token_hash, created_at, expires_at, ip_address, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, token_hash, now.isoformat(), expires.isoformat(), ip_address, user_agent),
        )
        await conn.commit()
    return session_id


async def delete_session(session_id: str) -> None:
    """Delete a session (logout)."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await conn.commit()


async def delete_user_sessions(user_id: str) -> int:
    """Delete all sessions for a user (force logout everywhere). Returns count."""
    async with get_db() as conn:
        cur = await conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await conn.commit()
        return cur.rowcount


async def validate_session(session_id: str) -> bool:
    """Check if a session exists and hasn't expired."""
    async with get_db() as conn:
        async with conn.execute(
            "SELECT expires_at FROM sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return False
            expires = datetime.fromisoformat(row[0])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return expires > datetime.now(timezone.utc)


def _blacklist_in_memory(token: str) -> tuple[str, datetime]:
    """Record the revocation in the hot cache. Returns (token_hash, expires).

    Token expiry is computed by decoding the token (without verifying — we
    only need the exp claim, not authenticity, since this is a defensive
    record of "operator chose to log out"). Falls back to ACCESS_TOKEN_EXPIRE
    if the claim isn't readable.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    try:
        # options={"verify_signature": False} — we already trust the caller,
        # we just want the exp timestamp.
        claims = jwt.decode(token, options={"verify_signature": False})
        exp_ts = claims.get("exp")
        if exp_ts:
            expires = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    except Exception:
        pass

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
    await _persist_blacklist_entry(token_hash, expires)


def blacklist_token_sync(token: str) -> None:
    """Revoke a token from synchronous code.

    Runs the persist to completion on a private event loop, so no task
    outlives this call. Prefer the async ``blacklist_token`` where possible.
    """
    import asyncio

    token_hash, expires = _blacklist_in_memory(token)
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
        async with get_db() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO token_blacklist (token_hash, expires_at) VALUES (?, ?)",
                (token_hash, expires.isoformat()),
            )
            await conn.commit()
    except Exception as e:
        logger.warning("token_blacklist persist failed for %s...: %s", token_hash[:8], e)


async def _is_blacklisted(token_hash: str) -> bool:
    """Check both the in-memory cache and the persisted table."""
    if token_hash in _TOKEN_BLACKLIST:
        return True
    try:
        async with get_db() as conn:
            async with conn.execute(
                "SELECT expires_at FROM token_blacklist WHERE token_hash = ? AND expires_at > ?",
                (token_hash, datetime.now(timezone.utc).isoformat()),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    # Hot-cache so subsequent lookups don't hit the DB
                    try:
                        _TOKEN_BLACKLIST[token_hash] = datetime.fromisoformat(row[0])
                    except Exception:
                        pass
                    return True
    except Exception as e:
        logger.debug("token_blacklist lookup failed: %s", e)
    return False


async def cleanup_expired_sessions() -> int:
    """Remove expired sessions. Called periodically."""
    async with get_db() as conn:
        cur = await conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        await conn.commit()
        return cur.rowcount


async def rotate_jwt_secret() -> None:
    """Rotate the JWT signing secret.

    Moves the current secret to ``jwt_secret_previous`` with a bounded
    ``_JWT_SECRET_GRACE_SECONDS`` grace window, then generates a fresh
    current secret. Tokens signed with the old secret keep verifying until
    the grace window elapses, after which the old secret is purged and
    those tokens stop verifying.
    """
    current = await _get_jwt_secret()
    grace_expires = datetime.now(timezone.utc) + timedelta(seconds=_JWT_SECRET_GRACE_SECONDS)
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
    async with get_db() as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0]


async def get_user_by_id(user_id: str) -> Optional[User]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return _row_to_user(row)


async def get_user_by_username(username: str) -> Optional[User]:
    async with get_db() as conn:
        async with conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return _row_to_user(row)


async def get_password_hash(username: str) -> Optional[str]:
    async with get_db() as conn:
        async with conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def create_user(
    username: str,
    password: str,
    display_name: str,
    role: Role = Role.technician,
    email: Optional[str] = None,
    all_customers: bool = False,
) -> User:
    """Create a user.

    ``all_customers`` defaults to False, so a new account starts scoped to
    whatever customers an admin assigns it. (Admins bypass the check outright,
    so the flag is irrelevant for them.)
    """
    from app.core.exceptions import ValidationError
    pw_err = validate_password(password)
    if pw_err:
        raise ValidationError(pw_err)
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password(password)
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO users (id, username, display_name, email, password_hash, role, created_at, is_active, all_customers)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (user_id, username, display_name, email, pw_hash, role.value, now, int(all_customers)),
        )
        await conn.commit()
    return User(
        id=user_id,
        username=username,
        display_name=display_name,
        email=email,
        role=role,
        created_at=datetime.fromisoformat(now),
        is_active=True,
        all_customers=all_customers,
    )


ALLOWED_USER_FIELDS = {"display_name", "email", "role", "is_active"}


async def update_user(
    user_id: str,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[Role] = None,
    is_active: Optional[bool] = None,
) -> Optional[User]:
    fields = []
    values = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name)
    if email is not None:
        fields.append("email = ?")
        values.append(email)
    if role is not None:
        fields.append("role = ?")
        values.append(role.value)
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(int(is_active))
    if not fields:
        return await get_user_by_id(user_id)
    values.append(user_id)
    async with get_db() as conn:
        await conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values
        )
        await conn.commit()
    return await get_user_by_id(user_id)


async def change_password(user_id: str, new_password: str) -> None:
    from app.core.exceptions import ValidationError
    pw_err = validate_password(new_password)
    if pw_err:
        raise ValidationError(pw_err)
    pw_hash = hash_password(new_password)
    async with get_db() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id)
        )
        await conn.commit()


async def delete_user(user_id: str) -> bool:
    async with get_db() as conn:
        cursor = await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def list_users() -> list[User]:
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM users ORDER BY created_at") as cur:
            rows = await cur.fetchall()
            return [_row_to_user(r) for r in rows]


async def update_last_login(user_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as conn:
        await conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?", (now, user_id)
        )
        await conn.commit()


# ── Authenticate ─────────────────────────────────────────────────────────────

# A pre-computed hash of a random value, verified against when the username
# doesn't exist. Without it, a missing user returns in microseconds while a
# real one costs a full Argon2 verify — a timing oracle for enumerating
# usernames. The password is never known, so this always fails.
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(32))


async def authenticate(username: str, password: str) -> Optional[User]:
    """Verify credentials and return the user, or None."""
    pw_hash = await get_password_hash(username)
    if not pw_hash:
        verify_password(password, _DUMMY_HASH)  # equalise timing
        return None
    if not verify_password(password, pw_hash):
        return None
    user = await get_user_by_username(username)
    if user and not user.is_active:
        return None
    if user and user.is_system:
        # An account with no human behind it is an identity for attribution and
        # locking, not a second way through the front door. Refused after the
        # password check so this reveals nothing a wrong password would not.
        logger.warning("Refused interactive sign-in for system account %r", username)
        return None
    if user:
        await update_last_login(user.id)
    return user


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_user(row) -> User:
    keys = row.keys()
    return User(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        email=row["email"],
        role=Role(row["role"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        last_login=datetime.fromisoformat(row["last_login"]) if row["last_login"] else None,
        is_active=bool(row["is_active"]),
        # Tolerate a row read before migration 14 has run.
        all_customers=bool(row["all_customers"]) if "all_customers" in keys else False,
        is_system=bool(row["is_system"]) if "is_system" in keys else False,
        can_write=bool(row["can_write"]) if "can_write" in keys else False,
        tenant_write=bool(row["tenant_write"]) if "tenant_write" in keys else False,
    )
