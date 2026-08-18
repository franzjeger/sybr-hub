"""First-run setup is a server-owned job, not a coroutine in the SSE stream.

FirstRunSetup writes the cert and — at the end, on the PowerShell [RESULT] —
saves the config and secrets. Run inside the stream, a client disconnect
mid-sign-in tore that down before the write, and the credentials were lost. As a
server-owned job it runs to completion and persists regardless of the browser,
publishing progress + the device code to whoever is attached and remembering
both so a reconnecting client is replayed them.
"""

from __future__ import annotations

import pytest

from app.web import state
from app.web.routes import audit as audit_route

pytestmark = pytest.mark.asyncio


async def test_setup_publish_stores_device_code_and_terminal_and_fans_out():
    run = state.SetupRunContext(running=True)
    q = run.subscribe()
    run.publish({"type": "device_code", "code": "ABC", "url": "u"})
    assert run.device_code == {"type": "device_code", "code": "ABC", "url": "u"}
    assert (await q.get())["type"] == "device_code"
    run.publish({"type": "done", "success": True})
    assert run.terminal == {"type": "done", "success": True}


async def test_setup_job_completes_and_persists_with_no_subscriber(monkeypatch):
    """The load-bearing property: the job runs to the end (where FirstRunSetup
    saves config + secrets) even with no stream attached, remembers the device
    code for replay, and resets setup_running in its finally."""
    import app.modules.m365_audit.setup as setup_mod

    class _FakeSetup:
        def __init__(self, on_device_code=None):
            self._cb = on_device_code

        async def run(self):
            yield {"step": "Cert", "status": "ok", "msg": "cert"}
            if self._cb:
                self._cb("ABC123", "https://login.microsoft.com/device")
            yield {"step": "Auth", "status": "ok", "msg": "sign in"}
            # In the real flow the [RESULT] handler saves config + secrets here.
            yield {"step": "Save", "status": "ok", "msg": "Configuration saved"}

    monkeypatch.setattr(setup_mod, "FirstRunSetup", _FakeSetup)

    run = state.SetupRunContext(running=True)
    state.setup_running = True
    try:
        # No subscriber — exactly the disconnected-client case.
        await audit_route._run_setup_job(run)
        assert run.terminal == {"type": "done", "success": True}
        assert run.device_code is not None and run.device_code["code"] == "ABC123"
        assert run.running is False, "the job must clear its own running flag"
        assert state.setup_running is False, "the job must release the global flag"
    finally:
        state.setup_running = False


async def test_setup_job_reports_failure_and_releases_the_flag(monkeypatch):
    import app.modules.m365_audit.setup as setup_mod

    class _FailSetup:
        def __init__(self, on_device_code=None):
            pass

        async def run(self):
            yield {"step": "Cert", "status": "ok", "msg": "cert"}
            yield {"step": "PS", "status": "error", "msg": "auth failed"}

    monkeypatch.setattr(setup_mod, "FirstRunSetup", _FailSetup)

    run = state.SetupRunContext(running=True)
    state.setup_running = True
    try:
        await audit_route._run_setup_job(run)
        assert run.terminal == {"type": "done", "success": False}
        assert run.running is False
        assert state.setup_running is False, "a failed setup must still release the flag"
    finally:
        state.setup_running = False


async def test_setup_job_publishes_events_to_an_attached_subscriber(monkeypatch):
    import app.modules.m365_audit.setup as setup_mod

    class _FakeSetup:
        def __init__(self, on_device_code=None):
            self._cb = on_device_code

        async def run(self):
            if self._cb:
                self._cb("ZZZ", "https://login.microsoft.com/device")
            yield {"step": "Auth", "status": "ok", "msg": "sign in"}

    monkeypatch.setattr(setup_mod, "FirstRunSetup", _FakeSetup)

    run = state.SetupRunContext(running=True)
    state.setup_running = True
    try:
        q = run.subscribe()
        await audit_route._run_setup_job(run)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        types = [e["type"] for e in events]
        assert "device_code" in types
        assert types[-1] == "done"
    finally:
        state.setup_running = False
