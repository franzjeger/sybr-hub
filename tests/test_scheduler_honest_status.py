"""A scheduled task that did nothing useful must not report success.

Before November 2026 a FortiGate backup where every device failed returned
"0 backed up, 12 errors", the ALSO refresh "0/25 scanned", and an alert check
whose engine crashed "ok — 0 alerts". None of them raised, so the failure
counter reset, the breaker never tripped and nobody was notified. A Uniweb
sync stuck in a hung browser left `running` set, and every later tick
returned "ok" without syncing anything.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import scheduler


async def test_a_fortigate_backup_where_every_device_failed_raises(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(
            lambda: [{"_id": "a", "FortiGateHost": "fw.a"}, {"_id": "b", "FortiGateHost": "fw.b"}]
        ),
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, name: "token")

    async def _fail(cust, token, cid):
        return {"ok": False, "error": "401"}

    monkeypatch.setattr("app.services.fortigate_api.backup_config", _fail)
    with pytest.raises(RuntimeError, match="0 backed up, 2 errors"):
        await scheduler._do_fortigate_backup()


async def test_a_partly_failed_fortigate_backup_still_reports(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(
            lambda: [{"_id": "a", "FortiGateHost": "fw.a"}, {"_id": "b", "FortiGateHost": "fw.b"}]
        ),
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda cid, name: "token")

    async def _one_fails(cust, token, cid):
        return {"ok": cid == "a", "error": "timeout"}

    monkeypatch.setattr("app.services.fortigate_api.backup_config", _one_fails)
    assert await scheduler._do_fortigate_backup() == "1 backed up, 1 errors"


async def test_an_alert_engine_failure_fails_the_task(monkeypatch):
    async def _crash(**kw):
        raise ValueError("engine broke")

    async def _fine():
        return None

    monkeypatch.setattr("app.services.alert_engine.run_alert_check", _crash)
    monkeypatch.setattr(
        "app.services.audit_scheduler.scheduler._check_credential_expiry", _fine, raising=False
    )
    with pytest.raises(RuntimeError, match="alert engine: engine broke"):
        await scheduler._do_alert_check()


async def test_a_uniweb_sync_still_running_at_the_next_tick_fails(monkeypatch):
    from app.services import uniweb_sync

    monkeypatch.setattr(
        uniweb_sync, "_get_uniweb_config", lambda: {"email": "e@example.com", "password": "pw"}
    )
    monkeypatch.setitem(uniweb_sync._sync_status, "running", True)
    monkeypatch.setitem(uniweb_sync._sync_status, "last_error", None)
    monkeypatch.setitem(uniweb_sync._sync_status, "sync_start_time", "2026-11-09T02:00:00")
    with pytest.raises(RuntimeError, match="still running since 2026-11-09T02:00:00"):
        await scheduler._do_uniweb_sync()


async def test_a_task_past_its_deadline_fails_instead_of_holding_its_lock(monkeypatch):
    monkeypatch.setattr(scheduler, "TASK_DEADLINE_SECONDS", 0.01)

    async def _hangs():
        await asyncio.sleep(10)
        return "never"

    with pytest.raises(RuntimeError, match="did not finish"):
        await scheduler._run_with_deadline("demo", _hangs)


def test_every_cdp_call_has_a_timeout():
    """pychrome waits forever by default; a hung renderer must not pin the sync."""
    import inspect
    import re

    from app.services import uniweb_client

    source = inspect.getsource(uniweb_client)
    calls = re.findall(r"self\._tab\.[A-Z]\w*\.\w+\(([^)]*)\)", source)
    assert calls, "no CDP calls found; the pattern is stale"
    assert all("_timeout=" in args for args in calls), calls
