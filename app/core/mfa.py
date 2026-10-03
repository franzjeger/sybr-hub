"""Local TOTP with replay protection, bounded attempts and recovery codes.

Algorithm and vectors: https://www.rfc-editor.org/rfc/rfc6238
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from urllib.parse import quote

from sqlalchemy import text
from sqlmodel import select

from app.core.encryption import decrypt_bytes, encrypt_text
from app.core.exceptions import ConflictError
from app.core.messages import conflict
from app.core.orm import get_session
from app.models.user import MfaStepup, UserMfa, UserSession


def required_for(user) -> bool:
    from app.models.user import Role

    return os.environ.get("SYBR_REQUIRE_MFA") == "1" and user.role >= Role.technician


def totp(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret)
    digest = hmac.digest(key, struct.pack(">Q", counter), "sha1")
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


async def enabled(user_id: str) -> bool:
    async with get_session() as session:
        result = await session.execute(select(UserMfa.enabled).where(UserMfa.user_id == user_id))
        val = result.first()
        return bool(val and val[0])


async def begin_enrollment(user_id: str, username: str) -> dict:
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    async with get_session() as session:
        try:
            await session.commit()
            await session.execute(text("BEGIN IMMEDIATE"))
        except Exception as e:
            await session.rollback()
            raise conflict("err_try_again_shortly") from e

        try:
            mfa = await session.get(UserMfa, user_id)
            if mfa and mfa.enabled:
                raise ConflictError("MFA is already enabled")

            if not mfa:
                mfa = UserMfa(
                    user_id=user_id,
                    secret=encrypt_text(secret),
                    enabled=0,
                    expires_at=time.time() + 600,
                )
                session.add(mfa)
            else:
                mfa.secret = encrypt_text(secret)
                mfa.expires_at = time.time() + 600
                mfa.last_counter = -1
                mfa.failures = 0
                mfa.locked_until = 0.0

            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return {
        "secret": secret,
        "uri": "otpauth://totp/"
        + quote("Sybr HUB:" + username, safe="")
        + "?secret="
        + secret
        + "&issuer=Sybr%20HUB&algorithm=SHA1&digits=6&period=30",
        "expires_in": 600,
    }


async def verify(user_id: str, code: str, *, enroll: bool = False) -> tuple[bool, list[str]]:
    """Consume one TOTP step or recovery code in the same DB transaction."""
    now = time.time()
    async with get_session() as session:
        try:
            await session.commit()
            await session.execute(text("BEGIN IMMEDIATE"))
        except Exception as e:
            await session.rollback()
            raise conflict("err_try_again_shortly") from e

        try:
            mfa = await session.get(UserMfa, user_id)
            if not mfa or bool(mfa.enabled) == enroll or mfa.locked_until > now:
                await session.rollback()
                return False, []
            if enroll and mfa.expires_at < now:
                await session.rollback()
                return False, []

            secret = decrypt_bytes(mfa.secret).decode()
            counter = int(now // 30)
            matched = next(
                (
                    c
                    for c in range(counter - 1, counter + 2)
                    if c > mfa.last_counter and hmac.compare_digest(totp(secret, c), code)
                ),
                None,
            )
            hashes = json.loads(mfa.recovery_hashes)
            recovery_hash = hashlib.sha256(code.encode()).hexdigest()
            recovery = not enroll and recovery_hash in hashes

            if matched is None and not recovery:
                mfa.failures += 1
                if mfa.failures >= 5:
                    mfa.locked_until = now + 300
                await session.commit()
                return False, []

            codes = []
            if recovery:
                hashes.remove(recovery_hash)
            if enroll:
                codes = [secrets.token_hex(16) for _ in range(10)]
                hashes = [hashlib.sha256(c.encode()).hexdigest() for c in codes]

            mfa.enabled = 1
            mfa.last_counter = matched if matched is not None else mfa.last_counter
            mfa.recovery_hashes = json.dumps(hashes)
            mfa.failures = 0
            mfa.locked_until = 0.0

            await session.commit()
            return True, codes
        except BaseException:
            await session.rollback()
            raise


async def mark_recent(session_id: str | None) -> None:
    if session_id:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        verified_at = time.time()
        async with get_session() as session:
            stmt = sqlite_insert(MfaStepup).values(session_id=session_id, verified_at=verified_at)
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id"], set_={"verified_at": verified_at}
            )
            await session.execute(stmt)
            await session.commit()


async def session_verified(user_id: str, session_id: str | None) -> bool:
    """Require proof on the particular session, including after enrollment races."""
    if not session_id:
        return False
    async with get_session() as session:
        result = await session.execute(
            select(MfaStepup)
            .join(UserSession, UserSession.id == MfaStepup.session_id)
            .where(MfaStepup.session_id == session_id, UserSession.user_id == user_id)
        )
        return result.first() is not None


async def is_recent(user_id: str, session_id: str | None) -> bool:
    if not await enabled(user_id):
        return True
    if not session_id:
        return False
    async with get_session() as session:
        stepup = await session.get(MfaStepup, session_id)
        return bool(stepup and 0 <= time.time() - stepup.verified_at <= 300)
