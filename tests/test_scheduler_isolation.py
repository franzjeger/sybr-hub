"""The scheduler must not move the active customer under everybody else.

It used to. Each iteration wrote active.txt, copied that customer's config
into the one global slot and their certificate over the one global cert, then
restored the original at the end. For the length of a cycle — minutes per
tenant, hours in total — "which customer is active" was a shared variable
being rewritten while technicians worked against it.

Every route that reads the active customer read those same globals: notes,
tags, audit scope, the dashboard. A note saved during a cycle landed on
whichever customer the scheduler had reached. And because the audit read the
customer *name* and the customer *credentials* as two separate reads of that
global, a switch landing between them would file tenant B's findings under
customer A — the one failure this tool cannot afford.

Nothing downstream ever needed the globals. These tests hold that line.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.scheduler import AuditScheduler

CUSTOMERS = [
    {"_id": "acme", "CustomerName": "Acme", "TenantId": "t-acme", "ClientId": "c-acme"},
    {"_id": "beta", "CustomerName": "Beta", "TenantId": "t-beta", "ClientId": "c-beta"},
]


class _Collector:
    """Stands in for AuditCollector, recording which auth it was handed."""

    seen: list = []

    def __init__(self, auth, out_dir, **kw):
        self.auth = auth
        _Collector.seen.append((auth, out_dir))

    async def run(self):
        return []


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    """Wire the scheduler to fakes and make every global mutation explode."""
    import app.core.scheduler as sched

    _Collector.seen = []
    built: list[tuple] = []

    def _forbidden(name):
        def boom(*a, **kw):
            raise AssertionError(f"scheduler touched global state via {name}")
        return boom

    monkeypatch.setattr("app.core.customer.CustomerManager.set_active", _forbidden("set_active"))
    monkeypatch.setattr("app.core.credentials.save_config", _forbidden("save_config"))
    monkeypatch.setattr("shutil.copy2", _forbidden("shutil.copy2"))
    monkeypatch.setattr("app.modules.m365_audit.auth.AuthManager.from_config", _forbidden("from_config"))

    monkeypatch.setattr("app.core.customer.CustomerManager.list_customers", staticmethod(lambda: list(CUSTOMERS)))
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: next((c for c in CUSTOMERS if c["_id"] == cid), None)),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_cert_path",
        staticmethod(lambda cid: tmp_path / f"{cid}.pfx"),
    )

    def fake_auth(customer, cert_path):
        built.append((customer["_id"], cert_path))
        return f"auth-for-{customer['_id']}"

    monkeypatch.setattr("app.modules.m365_audit.auth.get_auth_for_customer", fake_auth)
    monkeypatch.setattr("app.modules.m365_audit.collector.AuditCollector", _Collector)
    monkeypatch.setattr("app.modules.m365_audit.collector.make_output_dir", lambda name: tmp_path / name)
    monkeypatch.setattr("app.reports.generator.build_report_context", lambda **kw: {})

    monkeypatch.setattr(AuditScheduler, "_check_and_alert", lambda self, ctx, name: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_notify_audit_completed", lambda self, name, ctx=None: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_auto_report_and_email", lambda self, *a: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_send_webhook", lambda self, msg: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_log_activity", staticmethod(lambda *a: None))

    yield sched, built

    from app.web import state
    state.audit_running = False


async def test_a_cycle_never_moves_the_active_customer(wired):
    """The fixture makes set_active, save_config and the cert copy raise."""
    _, built = wired

    await AuditScheduler()._run_all_customers_audit()

    assert [cid for cid, _ in built] == ["acme", "beta"]


async def test_each_customer_is_audited_with_its_own_credentials(wired):
    """The bug this replaces: name and credentials were two reads of one global.

    A switch landing between them filed one tenant's findings under another
    customer's name. Here the auth is built from the customer record and
    handed to that customer's collector, so there is no window to land in.
    """
    _, built = wired

    await AuditScheduler()._run_all_customers_audit()

    assert [auth for auth, _ in _Collector.seen] == ["auth-for-acme", "auth-for-beta"]
    assert [out.name for _, out in _Collector.seen] == ["Acme", "Beta"]
    assert [cert.name for _, cert in built] == ["acme.pfx", "beta.pfx"]


async def test_an_unconfigured_customer_is_skipped_not_attempted(wired, monkeypatch):
    """Bulk already filters these. Attempting them just yields a noisy failure."""
    _, built = wired
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [*CUSTOMERS, {"_id": "half", "CustomerName": "Half"}]),
    )

    await AuditScheduler()._run_all_customers_audit()

    assert [cid for cid, _ in built] == ["acme", "beta"], "the half-configured one was tried"


async def test_one_customer_failing_does_not_end_the_cycle(wired, monkeypatch):
    calls = {"n": 0}
    real_run = _Collector.run

    async def flaky(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Graph said no")
        return await real_run(self)

    monkeypatch.setattr(_Collector, "run", flaky)

    await AuditScheduler()._run_all_customers_audit()

    assert calls["n"] == 2, "the second customer was never reached"


# ── Serialisation against a manual audit ─────────────────────────────────────

async def test_a_manual_audit_in_progress_is_skipped_not_run_alongside(wired):
    from app.web import state

    state.audit_running = True
    try:
        await AuditScheduler()._run_all_customers_audit()
    finally:
        state.audit_running = False

    assert _Collector.seen == [], "the scheduler ran on top of a manual audit"


async def test_the_flag_is_released_even_when_an_audit_raises(wired, monkeypatch):
    """Otherwise one failed scheduled audit locks out every manual one after it."""
    from app.web import state

    async def always_fails(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(_Collector, "run", always_fails)

    await AuditScheduler()._run_all_customers_audit()

    assert state.audit_running is False


async def test_the_flag_is_claimed_per_customer_not_for_the_whole_cycle(wired):
    """Holding it across every tenant would lock a technician out for hours.

    A guard people have to work around is a guard that gets removed.
    """
    from app.web import state

    observed: list[bool] = []
    real_run = _Collector.run

    async def watch(self):
        observed.append(state.audit_running)
        return await real_run(self)

    _Collector.run = watch
    try:
        await AuditScheduler()._run_all_customers_audit()
    finally:
        _Collector.run = real_run

    assert observed == [True, True], "the flag was not held during each audit"
    assert state.audit_running is False, "the flag outlived the cycle"
