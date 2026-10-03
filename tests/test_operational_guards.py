import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import password_work


async def test_audit_start_log_failure_releases_start_lock(monkeypatch):
    from datetime import UTC, datetime

    from starlette.requests import Request

    from app.core import job_state as state
    from app.models.user import Role, User
    from app.web.routes import audit

    user = User(
        id="log-failure-user",
        username="tester",
        display_name="Tester",
        created_at=datetime.now(UTC),
        role=Role.admin,
        can_write=True,
    )
    monkeypatch.setattr("app.core.customer.CustomerManager.get_active_id", lambda: "c1")
    monkeypatch.setattr(
        audit,
        "_prepare_audit",
        lambda request: (None, {"customer_name": "Example", "out_dir": None, "cfg": {}}),
    )

    def broken_log(*args, **kwargs):
        raise OSError("simulated disk-full activity log")

    monkeypatch.setattr("app.core.activity_log.log_activity", broken_log)
    monkeypatch.setattr(state, "audit_running", False)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/audit/stream",
            "query_string": b"",
            "headers": [],
        }
    )
    for _ in range(2):
        with pytest.raises(OSError, match="disk-full"):
            await audit.audit_stream(request, user)
        assert not state.audit_running
        assert not state.get_user_audit(user.id, "c1").running


async def test_password_work_does_not_block_loop_or_release_running_cancelled_work(monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def work():
        started.set()
        assert release.wait(3)

    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(password_work, "_executor", executor)
        monkeypatch.setattr(password_work, "_admission", threading.BoundedSemaphore(1))
        task = asyncio.create_task(password_work.run_password_work(work))
        try:
            await asyncio.wait_for(asyncio.to_thread(started.wait, 1), 2)
            assert started.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(password_work.PasswordServiceBusy):
                await password_work.run_password_work(lambda: None)
        finally:
            release.set()
    assert password_work._admission.acquire(blocking=False)
    password_work._admission.release()
