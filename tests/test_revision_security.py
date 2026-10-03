"""Behavioral regression tests for the September technical review."""

import asyncio
import base64
import hashlib
import io
import json
import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.core import mfa
from app.core.audit_results import credential_expiry_counts, new_run_directory
from app.core.auth import create_user
from app.core.backup_crypto import decrypt_member, encrypt_member
from app.core.database import run_migrations
from app.core.exceptions import ConflictError
from app.services.finding_tickets import finish_operation, reserve_operation


@pytest.fixture
async def user(tmp_path, monkeypatch):
    import app.core.database as database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "database.db")
    await run_migrations()
    return await create_user("review-test", "Review-test123!", "Review Test")


def test_totp_matches_rfc6238_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode()
    for timestamp, expected in [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ]:
        assert mfa.totp(secret, timestamp // 30, 8) == expected


async def test_mfa_replay_recovery_and_wrong_user(user, monkeypatch):
    timestamp = time.time()
    monkeypatch.setattr(mfa.time, "time", lambda: timestamp)
    enrollment = await mfa.begin_enrollment(user.id, user.username)
    valid, recovery = await mfa.verify(
        user.id, mfa.totp(enrollment["secret"], int(timestamp // 30)), enroll=True
    )
    assert valid and len(recovery) == 10
    assert await mfa.enabled(user.id)
    assert not (await mfa.verify(user.id, mfa.totp(enrollment["secret"], int(timestamp // 30))))[0]
    assert not (await mfa.verify("someone-else", recovery[0]))[0]
    assert (await mfa.verify(user.id, recovery[0]))[0]
    assert not (await mfa.verify(user.id, recovery[0]))[0]
    results = await asyncio.gather(*(mfa.verify(user.id, recovery[1]) for _ in range(2)))
    assert sum(r[0] for r in results) == 1


async def test_mfa_locks_repeated_guesses(user, monkeypatch):
    timestamp = time.time()
    enrollment = await mfa.begin_enrollment(user.id, user.username)
    valid, _ = await mfa.verify(
        user.id, mfa.totp(enrollment["secret"], int(timestamp // 30)), enroll=True
    )
    assert valid
    for _ in range(5):
        assert not (await mfa.verify(user.id, "invalid"))[0]
    monkeypatch.setattr(mfa.time, "time", lambda: timestamp + 60)
    assert not (
        await mfa.verify(user.id, mfa.totp(enrollment["secret"], int((timestamp + 60) // 30)))
    )[0]
    monkeypatch.setattr(mfa.time, "time", lambda: timestamp + 360)
    assert (
        await mfa.verify(user.id, mfa.totp(enrollment["secret"], int((timestamp + 360) // 30)))
    )[0]


async def test_parallel_remote_writes_have_one_durable_reservation(user):
    results = await asyncio.gather(
        *(reserve_operation("c", "r", "autotask", user.username) for _ in range(8)),
        return_exceptions=True,
    )
    winners = [r for r in results if isinstance(r, str)]
    assert len(winners) == 1
    assert all(isinstance(r, (str, ConflictError)) for r in results)
    await finish_operation(winners[0], succeeded=False)
    with pytest.raises(ConflictError, match="unknown"):
        await reserve_operation("c", "r", "autotask", user.username)


def test_backup_stream_confidentiality_path_binding_and_authentication(tmp_path):
    from cryptography.exceptions import InvalidTag

    source = tmp_path / "source"
    plaintext = b"SQLite format 3\x00 private@example.invalid " * 100000
    source.write_bytes(plaintext)
    destination = io.BytesIO()
    key = os.urandom(32)
    metadata = encrypt_member(source, destination, key, "database/store.db")
    blob = destination.getvalue()
    assert b"private@example.invalid" not in blob
    assert metadata["size"] == len(blob)
    assert metadata["sha256"] == hashlib.sha256(blob).hexdigest()
    staged = tmp_path / "member"
    for bad_key, bad_path in [(os.urandom(32), "database/store.db"), (key, "other.db")]:
        staged.write_bytes(blob)
        with pytest.raises(InvalidTag):
            decrypt_member(staged, bad_key, bad_path)
        assert staged.read_bytes() == blob
    staged.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        decrypt_member(staged, key, "database/store.db")
    staged.write_bytes(blob)
    decrypt_member(staged, key, "database/store.db")
    assert staged.read_bytes() == plaintext


async def test_idle_terminal_resumes_when_output_arrives():
    from app.core.async_fd import read_fd

    read, write = os.pipe2(os.O_NONBLOCK)
    try:
        task = asyncio.create_task(read_fd(read))
        await asyncio.sleep(0.02)
        assert not task.done()
        os.write(write, b"output after idle")
        assert await asyncio.wait_for(task, 1) == b"output after idle"
    finally:
        os.close(read)
        os.close(write)


def test_expiry_summary_and_unique_runs(tmp_path):
    assert credential_expiry_counts(
        "WARNING: EXPIRED OR SOON-EXPIRING\n  0 expired, 1 expiring within 7 days."
    ) == (0, 1)
    assert credential_expiry_counts("  2 expired, 3 expiring within 7 days.") == (2, 3)
    assert credential_expiry_counts("An app called Expired") is None
    runs = {new_run_directory(tmp_path) for _ in range(20)}
    assert len(runs) == 20
