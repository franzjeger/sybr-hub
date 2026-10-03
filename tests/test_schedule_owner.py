"""Exactly one process runs the schedule, and readiness says which.

The schedule once moved to a separate process that neither the container nor
the installer started, so in both deployments no job ever ran and /api/ready
answered 503 for good. These pin the rule that replaced it: the web process
runs the schedule unless another process already holds the lock, a standby
takes over when the lock frees, and readiness reports a schedule nobody runs.
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.core import config
from app.core.database import run_migrations
from app.services import audit_scheduler as audit_mod
from app.services import schedule_owner
from app.services.health import component_health


@pytest.fixture(autouse=True)
def _isolated_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule_owner, "DATA_DIR", tmp_path)
    schedule_owner.release()
    yield tmp_path
    schedule_owner.release()


def _hold_lock_as_another_process(directory):
    """A second open file description on the lock behaves like a second process."""
    fd = os.open(directory / "scheduler.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def test_only_one_holder_at_a_time(_isolated_lock):
    other = _hold_lock_as_another_process(_isolated_lock)
    try:
        assert schedule_owner.owned_elsewhere()
        assert not schedule_owner.try_acquire()
    finally:
        os.close(other)
    assert not schedule_owner.owned_elsewhere()
    assert schedule_owner.try_acquire()
    assert schedule_owner.owns()
    assert not schedule_owner.owned_elsewhere()


async def test_a_standby_takes_over_when_the_lock_frees(_isolated_lock, monkeypatch):
    monkeypatch.setattr(schedule_owner, "_reconcile", lambda: None)
    other = _hold_lock_as_another_process(_isolated_lock)
    stop = asyncio.Event()
    standby = asyncio.create_task(schedule_owner.wait_and_start(stop, poll_seconds=0.01))
    await asyncio.sleep(0.05)
    assert not standby.done() and not schedule_owner.owns()

    os.close(other)
    assert await asyncio.wait_for(standby, timeout=2)
    assert schedule_owner.owns()
    await schedule_owner.stop()
    assert not schedule_owner.owns()


async def test_a_stopped_standby_never_takes_the_lock(_isolated_lock):
    other = _hold_lock_as_another_process(_isolated_lock)
    try:
        stop = asyncio.Event()
        stop.set()
        assert not await schedule_owner.wait_and_start(stop, poll_seconds=0.01)
    finally:
        os.close(other)


async def _health_with_one_task(tmp_path, monkeypatch, status):
    from app.core import database
    from app.services import scheduler

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "health.db")
    await run_migrations()
    monkeypatch.setattr(config, "get_scheduler_config", lambda: {"enabled": False})
    monkeypatch.setattr(scheduler, "get_status", lambda: [status])
    return await component_health()


def _status(**overrides):
    status = {
        "id": "example",
        "enabled": True,
        "consecutive_failures": 0,
        "last_run": None,
        "last_success": None,
        "next_run": None,
    }
    status.update(overrides)
    return status


async def test_readiness_fails_when_no_process_runs_the_schedule(_isolated_lock, monkeypatch):
    health = await _health_with_one_task(_isolated_lock, monkeypatch, _status())
    assert health["components"]["schedule"] == {"owner": None, "ready": False}
    assert not health["ready"]


async def test_no_owner_is_fine_when_nothing_is_scheduled(_isolated_lock, monkeypatch):
    health = await _health_with_one_task(_isolated_lock, monkeypatch, _status(enabled=False))
    assert health["components"]["schedule"]["ready"]
    assert health["ready"]


async def test_readiness_trusts_a_live_external_owner(_isolated_lock, monkeypatch):
    other = _hold_lock_as_another_process(_isolated_lock)
    try:
        schedule_owner.touch_heartbeat()
        health = await _health_with_one_task(_isolated_lock, monkeypatch, _status())
        assert health["components"]["schedule"]["owner"] == "external"
        assert health["ready"]

        stale = time.time() - schedule_owner.HEARTBEAT_STALE_SECONDS - 5
        os.utime(_isolated_lock / "scheduler.heartbeat", (stale, stale))
        assert not (await component_health())["ready"]
    finally:
        os.close(other)


async def test_readiness_reports_an_external_owners_failing_task(_isolated_lock, monkeypatch):
    other = _hold_lock_as_another_process(_isolated_lock)
    try:
        schedule_owner.touch_heartbeat()
        health = await _health_with_one_task(
            _isolated_lock, monkeypatch, _status(consecutive_failures=2)
        )
        assert not health["components"]["example"]["ready"]
        assert not health["ready"]
    finally:
        os.close(other)


async def test_readiness_detects_dead_or_failing_jobs_in_the_owner(_isolated_lock, monkeypatch):
    from app.services import scheduler

    assert schedule_owner.try_acquire()
    status = _status()
    handles = {}
    monkeypatch.setattr(scheduler, "_running_tasks", handles)
    assert not (await _health_with_one_task(_isolated_lock, monkeypatch, status))["ready"]
    task = asyncio.create_task(asyncio.Event().wait())
    handles["example"] = task
    try:
        assert (await component_health())["ready"]
        status["consecutive_failures"] = 1
        assert not (await component_health())["ready"]
        status["enabled"] = False
        assert (await component_health())["ready"]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# ── The audit loop measures from a persisted anchor ──────────────────────────


def _audit_config(monkeypatch, **cfg):
    monkeypatch.setattr(audit_mod, "get_scheduler_config", lambda: {"interval_hours": 24, **cfg})


def test_first_enable_anchors_now_and_waits_a_full_interval(monkeypatch):
    _audit_config(monkeypatch, enabled=True)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert not audit_mod.AuditScheduler._due(now)
    assert audit_mod._load_anchor() == now
    assert not audit_mod.AuditScheduler._due(now + timedelta(hours=23))
    assert audit_mod.AuditScheduler._due(now + timedelta(hours=24))


def test_a_restart_does_not_push_the_next_run_out(monkeypatch):
    _audit_config(monkeypatch, enabled=True)
    anchor = datetime(2026, 10, 1, 12, tzinfo=UTC)
    audit_mod._save_anchor(anchor)
    # A fresh scheduler object (a new process) reads the same anchor.
    assert audit_mod.AuditScheduler()._due(anchor + timedelta(hours=25))


def test_disabling_clears_the_anchor_so_re_enabling_starts_fresh(monkeypatch):
    audit_mod._save_anchor(datetime(2026, 1, 1, tzinfo=UTC))
    _audit_config(monkeypatch, enabled=False)
    assert not audit_mod.AuditScheduler._due(datetime(2026, 10, 1, tzinfo=UTC))
    assert audit_mod._load_anchor() is None


async def test_a_due_cycle_runs_the_audit_and_the_opt_in_backup_only(monkeypatch):
    calls = []
    s = audit_mod.AuditScheduler()

    async def record(name):
        calls.append(name)

    monkeypatch.setattr(s, "_run_scheduled_audit", lambda: record("audit"))
    monkeypatch.setattr(s, "_maybe_create_backup", lambda: record("backup"))
    # Owned by the task scheduler; running them here would run them twice.
    monkeypatch.setattr(s, "_check_credential_expiry", lambda: record("cred"), raising=False)
    monkeypatch.setattr(s, "_scan_also_renewals", lambda: record("also"))
    due = iter([True])
    monkeypatch.setattr(s, "_due", lambda now: next(due, False))
    monkeypatch.setattr(audit_mod, "_TICK_SECONDS", 0.01)

    s.start()
    await asyncio.sleep(0.1)
    await s.stop()
    assert calls == ["audit", "backup"]
    assert audit_mod._load_anchor() is not None


def test_the_web_process_owns_the_schedule_while_it_serves(_isolated_lock, monkeypatch):
    from fastapi.testclient import TestClient

    from app.web.server import create_app

    monkeypatch.setattr(schedule_owner, "_reconcile", lambda: None)
    with TestClient(create_app()):
        assert schedule_owner.owns()
    assert not schedule_owner.owns()
    assert not schedule_owner.owned_elsewhere()
