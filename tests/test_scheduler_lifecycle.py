"""The schedulers must start on boot, run one job at a time, and stay disabled.

Before SR-004 neither scheduler started from the application lifespan — a task
began only when its config was next written, so a restart silently stopped
every scheduled job until an operator happened to reopen Settings. A manual run
could overlap the scheduled run of the same task. An unvalidated schedule type
or weekday fell through to the wrong branch. And an auto-disabled task restarted
itself on the next boot, failing all over again.

These pin: enabled tasks start (and disabled ones do not), a per-task
single-flight so a manual and a scheduled run cannot overlap, a failure breaker
that survives a restart until explicitly cleared, awaited cancellation on
shutdown, config validation, and that the audit loop no longer bundles the
maintenance jobs the task scheduler owns.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from pydantic import ValidationError

from app.models.settings import SchedulerConfig, TaskSchedule
from app.services import scheduler as sch


@pytest.fixture(autouse=True)
def _reset():
    sch._running_tasks.clear()
    sch._task_status.clear()
    sch._task_locks.clear()
    yield
    for t in list(sch._running_tasks.values()):
        t.cancel()
    sch._running_tasks.clear()
    sch._task_status.clear()
    sch._task_locks.clear()


def _cfg(monkeypatch, tasks: dict):
    monkeypatch.setattr(sch, "get_task_scheduler_config", lambda: {k: dict(v) for k, v in tasks.items()})
    monkeypatch.setattr(sch, "_load_task_status", lambda: None)
    monkeypatch.setattr(sch, "_persist_task_status", lambda: None)


# ── Config validation (criterion 3) ─────────────────────────────────────────

def test_a_bad_task_type_is_rejected():
    with pytest.raises(ValidationError):
        TaskSchedule.model_validate({"type": "weekley"})


def test_a_bad_weekday_is_rejected():
    with pytest.raises(ValidationError):
        TaskSchedule.model_validate({"day": "funday"})


def test_type_and_day_are_normalized_to_lowercase():
    m = TaskSchedule.model_validate({"type": "WEEKLY", "day": "Sunday"})
    assert m.type == "weekly"
    assert m.day == "sunday"


def test_a_bad_time_is_rejected():
    with pytest.raises(ValidationError):
        TaskSchedule.model_validate({"time": "25:61"})


@pytest.mark.parametrize("bad", [0, -1, 100000])
def test_an_out_of_range_interval_is_rejected(bad):
    with pytest.raises(ValidationError):
        TaskSchedule.model_validate({"interval_hours": bad})


def test_the_audit_scheduler_config_bounds_its_interval():
    with pytest.raises(ValidationError):
        SchedulerConfig(interval_hours=0)
    with pytest.raises(ValidationError):
        SchedulerConfig(interval_hours=99999)
    assert SchedulerConfig(interval_hours=168).interval_hours == 168


# ── Startup / shutdown (criterion 2) ─────────────────────────────────────────

async def test_start_all_starts_enabled_tasks_and_skips_disabled(monkeypatch):
    _cfg(monkeypatch, {
        "on": {"enabled": True, "type": "interval", "interval_hours": 6},
        "off": {"enabled": False, "type": "daily", "time": "02:00"},
    })
    sch.start_all()
    assert "on" in sch._running_tasks and not sch._running_tasks["on"].done()
    assert "off" not in sch._running_tasks
    await sch.stop_all()


async def test_stop_all_awaits_cancellation(monkeypatch):
    _cfg(monkeypatch, {"on": {"enabled": True, "type": "interval", "interval_hours": 6}})
    sch.start_all()
    task = sch._running_tasks["on"]
    await sch.stop_all()
    assert task.done(), "stop_all returned before the loop was actually cancelled"
    assert not sch._running_tasks


async def test_the_audit_scheduler_stop_awaits_its_loop(monkeypatch):
    from app.core import scheduler as core_sch

    monkeypatch.setattr(core_sch, "get_scheduler_config",
                        lambda: {"enabled": True, "interval_hours": 168})
    s = core_sch.AuditScheduler()
    s.start()
    assert s._task is not None
    task = s._task
    await s.stop()
    assert task.done()
    assert s._task is None


# ── Single-flight (criterion 4) ──────────────────────────────────────────────

async def test_a_manual_run_and_a_second_run_cannot_overlap(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow():
        started.set()
        await release.wait()
        return "done"

    monkeypatch.setitem(sch._TASK_RUNNERS, "t", slow)

    first = asyncio.create_task(sch.run_now("t"))
    await asyncio.wait_for(started.wait(), timeout=2)

    # Second run while the first holds the lock is refused, not run concurrently.
    second = await sch.run_now("t")
    assert second["ok"] is False and second.get("running") is True

    release.set()
    result = await asyncio.wait_for(first, timeout=2)
    assert result["ok"] is True and result["result"] == "done"


async def test_the_lock_frees_after_a_run(monkeypatch):
    async def quick():
        return "ok"

    monkeypatch.setitem(sch._TASK_RUNNERS, "t", quick)
    assert (await sch.run_now("t"))["ok"] is True
    # A second run afterwards succeeds — the lock was released.
    assert (await sch.run_now("t"))["ok"] is True


# ── Failure breaker survives a restart (criterion 5) ─────────────────────────

def test_start_all_does_not_restart_a_tripped_task(monkeypatch):
    _cfg(monkeypatch, {"t": {"enabled": True, "type": "daily", "time": "02:00"}})
    sch._task_status["t"] = {"consecutive_failures": sch._MAX_CONSECUTIVE_FAILURES}
    sch.start_all()
    assert "t" not in sch._running_tasks, "an auto-disabled task was restarted on boot"


async def test_a_task_below_the_threshold_still_starts(monkeypatch):
    _cfg(monkeypatch, {"t": {"enabled": True, "type": "interval", "interval_hours": 6}})
    sch._task_status["t"] = {"consecutive_failures": sch._MAX_CONSECUTIVE_FAILURES - 1}
    sch.start_all()
    assert "t" in sch._running_tasks
    await sch.stop_all()


async def test_reconfiguring_clears_the_breaker_and_restarts(monkeypatch):
    _cfg(monkeypatch, {"t": {"enabled": True, "type": "interval", "interval_hours": 6}})
    sch._task_status["t"] = {"consecutive_failures": sch._MAX_CONSECUTIVE_FAILURES}
    sch.restart_task("t")
    assert sch._task_status["t"]["consecutive_failures"] == 0
    assert "t" in sch._running_tasks
    await sch.stop_all()


async def test_a_successful_manual_run_clears_the_breaker(monkeypatch):
    # Found by review: run_now used to report OK without resetting the counter,
    # so a manual "recovery" left the scheduled loop auto-disabled.
    monkeypatch.setattr(sch, "_persist_task_status", lambda: None)

    async def quick():
        return "ok"

    monkeypatch.setitem(sch._TASK_RUNNERS, "t", quick)
    sch._task_status["t"] = {"consecutive_failures": sch._MAX_CONSECUTIVE_FAILURES}
    result = await sch.run_now("t")
    assert result["ok"] is True
    assert sch._task_status["t"]["consecutive_failures"] == 0


# ── Non-overlapping ownership (criterion 1) ──────────────────────────────────

def test_the_audit_loop_drops_the_duplicated_maintenance_jobs():
    from app.core.scheduler import AuditScheduler

    src = inspect.getsource(AuditScheduler._loop)
    # Owned by the task scheduler (alert_check delegates credential-expiry;
    # also_price_refresh runs the renewal scan) — must not run from here too.
    for duplicated in ("_check_credential_expiry", "_scan_also_renewals"):
        assert f"await self.{duplicated}" not in src, (
            f"{duplicated} still runs from the audit loop — it would run twice"
        )
    assert "_run_scheduled_audit" in src, "the audit loop must still run audits"
    # The post-audit backup is a distinct, opt-in job (gated on
    # backup_after_audit), not a duplicate of the weekly app_backup task, so it
    # stays — removing it silently drops backups for operators who set it.
    assert "await self._maybe_create_backup" in src


def test_the_cert_task_still_delegates_to_the_shared_method():
    # Removing it from the loop must not lose the logic: the cert task reuses it.
    src = inspect.getsource(sch)
    assert "_check_credential_expiry" in src
