"""Which process runs the schedule.

Scheduled work (audits, backups, syncs, alerts) must run in exactly one
process, or every job runs twice. The web process normally owns it; the
optional ``scripts/run_scheduler.py`` can stand by and take over. An exclusive
``flock`` on a file in the data directory decides, so the rule holds for any
deployment — a single container, a systemd unit, or both units at once.

The owner touches a heartbeat file and reconciles the running loops with the
saved configuration every ``_TICK_SECONDS``. That is how a settings change made
in a process that does not own the schedule reaches the one that does.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import time
from pathlib import Path

from app.core.config import DATA_DIR

log = logging.getLogger(__name__)

_LOCK_FILE = "scheduler.lock"
_HEARTBEAT_FILE = "scheduler.heartbeat"
_TICK_SECONDS = 30
# Three missed ticks: long enough to ride out a slow settings write, short
# enough that a dead owner shows up in /api/ready within minutes.
HEARTBEAT_STALE_SECONDS = 3 * _TICK_SECONDS

_lock_fd: int | None = None
_heartbeat_task: asyncio.Task | None = None


def _path(name: str) -> Path:
    return DATA_DIR / name


def owns() -> bool:
    """True when this process holds the schedule lock."""
    return _lock_fd is not None


def owned_elsewhere() -> bool:
    """True when another process holds the schedule lock right now."""
    if _lock_fd is not None:
        return False
    fd = os.open(_path(_LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def try_acquire() -> bool:
    """Take the schedule lock without waiting. Idempotent."""
    global _lock_fd
    if _lock_fd is not None:
        return True
    fd = os.open(_path(_LOCK_FILE), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    _lock_fd = fd
    return True


def release() -> None:
    global _lock_fd
    if _lock_fd is None:
        return
    with contextlib.suppress(OSError):
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
    os.close(_lock_fd)
    _lock_fd = None


def touch_heartbeat() -> None:
    _path(_HEARTBEAT_FILE).touch()


def heartbeat_age() -> float | None:
    """Seconds since the owning process last ticked, or None if it never has."""
    try:
        return max(time.time() - _path(_HEARTBEAT_FILE).stat().st_mtime, 0.0)
    except FileNotFoundError:
        return None


def _reconcile() -> None:
    """Start what the saved config enables; loops stop themselves when disabled."""
    from app.services import scheduler as task_scheduler
    from app.services.audit_scheduler import scheduler as audit_scheduler

    audit_scheduler.start()
    task_scheduler.start_all()


async def _tick_loop() -> None:
    while True:
        try:
            touch_heartbeat()
            _reconcile()
        except Exception:
            log.warning("Schedule reconcile failed", exc_info=True)
        await asyncio.sleep(_TICK_SECONDS)


async def start() -> bool:
    """Run the schedule here if no other process does. Returns ownership."""
    global _heartbeat_task
    if not try_acquire():
        log.info("Another process owns the schedule; serving requests only")
        return False
    log.info("This process owns the schedule")
    _reconcile()
    touch_heartbeat()
    _heartbeat_task = asyncio.create_task(_tick_loop())
    return True


async def wait_and_start(stop: asyncio.Event, poll_seconds: float = 5.0) -> bool:
    """Stand by until the lock frees, then take over. False if stopped first."""
    announced = False
    while not stop.is_set():
        if try_acquire():
            return await start()
        if not announced:
            log.info("Standing by: another process owns the schedule")
            announced = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
    return False


async def stop() -> None:
    """Stop the loops this process runs and hand the lock back."""
    global _heartbeat_task
    if not owns():
        return
    from app.services import scheduler as task_scheduler
    from app.services.audit_scheduler import scheduler as audit_scheduler

    task, _heartbeat_task = _heartbeat_task, None
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    try:
        await audit_scheduler.stop()
        await task_scheduler.stop_all()
    finally:
        release()
