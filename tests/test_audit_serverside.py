"""The audit is a server-owned job, not a coroutine living in the SSE stream.

The property that matters: a dropped client connection is a lost *view*, not a
lost run. The job runs to completion and saves its results whether or not any
stream is still attached, publishes progress to whoever is, and remembers its
outcome so a reconnecting client is replayed it. These pin that so the old
bug — completion work stranded in a dying stream, "running" reset on teardown —
cannot come back.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.web import state
from app.web.routes import audit as audit_route

pytestmark = pytest.mark.asyncio


def _ctx() -> state.AuditRunContext:
    return state.AuditRunContext(owner_user_id="u1", customer_id="c1", running=True)


async def test_publish_fans_out_to_every_subscriber():
    run = _ctx()
    q1 = run.subscribe()
    q2 = run.subscribe()
    run.publish({"type": "progress", "name": "MFA", "status": "done"})
    assert (await q1.get())["name"] == "MFA"
    assert (await q2.get())["name"] == "MFA"


async def test_publish_records_a_terminal_event_for_replay():
    run = _ctx()
    assert run.terminal is None
    run.publish({"type": "progress", "name": "MFA", "status": "running"})
    assert run.terminal is None  # progress is not terminal
    done = {"type": "done", "results": []}
    run.publish(done)
    assert run.terminal == done


async def test_publish_with_no_subscribers_still_records_terminal():
    """A finished run with nobody watching must still remember its outcome — a
    client that reconnects afterwards reads run.terminal (the attach path)."""
    run = _ctx()
    run.publish({"type": "error", "msg": "boom"})  # nobody listening
    assert run.terminal == {"type": "error", "msg": "boom"}


async def test_unsubscribe_stops_delivery():
    run = _ctx()
    q = run.subscribe()
    run.unsubscribe(q)
    run.publish({"type": "progress", "name": "MFA"})
    assert q.empty()


async def test_the_job_completes_and_saves_with_no_subscriber(monkeypatch):
    """The load-bearing property: with no stream attached (a disconnected
    client), the job still finishes, saves its results, records the terminal
    event, and resets the running flags in its own finally."""
    import app.core.activity_log as activity_mod
    import app.modules.m365_audit.auth as auth_mod
    import app.modules.m365_audit.collector as collector_mod
    from app.modules.base import SectionResult, SectionStatus

    class _FakeCollector:
        GRAPH_SECTION_NAMES: ClassVar[list[str]] = ["MFA Methods"]
        AZURE_SECTION_NAMES: ClassVar[list[str]] = []

        def __init__(self, *_a, **kw):
            self._cb = kw.get("progress_cb")

        async def run(self):
            if self._cb:
                self._cb("MFA Methods", SectionStatus.DONE, None)
            return [
                SectionResult(
                    name="MFA Methods", status=SectionStatus.DONE,
                    warns=[], warn_levels=[], files=[], error=None,
                )
            ]

    monkeypatch.setattr(collector_mod, "AuditCollector", _FakeCollector)
    monkeypatch.setattr(auth_mod.AuthManager, "from_config", classmethod(lambda cls: object()))
    monkeypatch.setattr(activity_mod, "log_activity", lambda *a, **k: None)

    async def _no_side_effects(cfg, results, out_dir, customer_name):
        return None

    monkeypatch.setattr(audit_route, "_post_audit_side_effects", _no_side_effects)

    run = state.AuditRunContext(owner_user_id="u1", customer_id="c1", running=True)
    state.audit_running = True
    try:
        spec = {"cfg": {}, "customer_name": "Acme", "out_dir": None}
        # No subscriber — exactly the disconnected-client case.
        await audit_route._run_audit_job(run, spec, None, "tester")

        assert run.results and run.results[0]["name"] == "MFA Methods"
        assert run.terminal is not None and run.terminal["type"] == "done"
        assert run.running is False, "the job must clear its own running flag"
        assert state.audit_running is False, "the job must release the global lock"
    finally:
        state.audit_running = False


async def test_the_job_publishes_progress_and_done_to_an_attached_subscriber(monkeypatch):
    """A client that *is* attached receives the live progress and the terminal
    event — this is what a re-attached stream drains."""
    import app.core.activity_log as activity_mod
    import app.modules.m365_audit.auth as auth_mod
    import app.modules.m365_audit.collector as collector_mod
    from app.modules.base import SectionResult, SectionStatus

    class _FakeCollector:
        GRAPH_SECTION_NAMES: ClassVar[list[str]] = ["MFA Methods"]
        AZURE_SECTION_NAMES: ClassVar[list[str]] = []

        def __init__(self, *_a, **kw):
            self._cb = kw.get("progress_cb")

        async def run(self):
            if self._cb:
                self._cb("MFA Methods", SectionStatus.DONE, None)
            return [
                SectionResult(
                    name="MFA Methods", status=SectionStatus.DONE,
                    warns=[], warn_levels=[], files=[], error=None,
                )
            ]

    monkeypatch.setattr(collector_mod, "AuditCollector", _FakeCollector)
    monkeypatch.setattr(auth_mod.AuthManager, "from_config", classmethod(lambda cls: object()))
    monkeypatch.setattr(activity_mod, "log_activity", lambda *a, **k: None)

    async def _no_side_effects(cfg, results, out_dir, customer_name):
        return None

    monkeypatch.setattr(audit_route, "_post_audit_side_effects", _no_side_effects)

    run = state.AuditRunContext(owner_user_id="u1", customer_id="c1", running=True)
    state.audit_running = True
    try:
        q = run.subscribe()
        await audit_route._run_audit_job(run, {"cfg": {}, "customer_name": "Acme", "out_dir": None}, None, "t")

        events = []
        while not q.empty():
            events.append(q.get_nowait())
        types = [e["type"] for e in events]
        assert "progress" in types
        assert types[-1] == "done"
    finally:
        state.audit_running = False


async def test_a_collector_failure_publishes_error_and_releases_the_lock(monkeypatch):
    import app.core.activity_log as activity_mod
    import app.modules.m365_audit.auth as auth_mod
    import app.modules.m365_audit.collector as collector_mod

    class _BoomCollector:
        GRAPH_SECTION_NAMES: ClassVar[list[str]] = ["MFA Methods"]
        AZURE_SECTION_NAMES: ClassVar[list[str]] = []

        def __init__(self, *_a, **_kw):
            pass

        async def run(self):
            raise RuntimeError("graph exploded")

    monkeypatch.setattr(collector_mod, "AuditCollector", _BoomCollector)
    monkeypatch.setattr(auth_mod.AuthManager, "from_config", classmethod(lambda cls: object()))
    monkeypatch.setattr(activity_mod, "log_activity", lambda *a, **k: None)

    run = state.AuditRunContext(owner_user_id="u1", customer_id="c1", running=True)
    state.audit_running = True
    try:
        await audit_route._run_audit_job(run, {"cfg": {}, "customer_name": "Acme", "out_dir": None}, None, "t")
        assert run.terminal is not None and run.terminal["type"] == "error"
        assert run.running is False
        assert state.audit_running is False, "a failed run must still release the lock"
    finally:
        state.audit_running = False
