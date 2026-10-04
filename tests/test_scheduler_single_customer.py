"""The scheduler's one-customer mode audits the customer the settings name.

It used to audit whatever the setup staging slot held (``load_config()``): the
customer somebody set up last, with that slot's credentials and the staging
certificate. Nobody chose that customer for the schedule, and the settings
hint called it "the active customer", a thing the server no longer has.

Now the settings name the customer by id, and the job does what the audit
route does: the customer's record and certificate path are read once and the
auth is built from them. Settings without an id audit nothing and say so in
the log; the staging slot is never a fallback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

import pytest

from app.services.audit_scheduler import AuditScheduler

CUSTOMERS = {
    "acme": {"_id": "acme", "CustomerName": "Acme", "TenantId": "t-acme", "ClientId": "c-acme"},
    "beta": {"_id": "beta", "CustomerName": "Beta", "TenantId": "t-beta", "ClientId": "c-beta"},
    # Delegated access: a tenant and no app registration of its own.
    "gdap": {"_id": "gdap", "CustomerName": "Delegated", "TenantId": "t-gdap", "AuthMode": "gdap"},
    "half": {"_id": "half", "CustomerName": "Half"},
}


class _Collector:
    seen: ClassVar[list] = []

    def __init__(self, auth, out_dir, **kw):
        _Collector.seen.append((auth, out_dir))

    async def run(self):
        return []


@pytest.fixture()
def wired(monkeypatch, tmp_path):
    """The scheduler on fakes, with every read of the staging slot made to fail."""
    import app.services.audit_scheduler as sched

    _Collector.seen = []
    record_reads: list[str] = []
    built: list[tuple] = []
    contexts: list[dict] = []
    settings: dict = {"audit_all_customers": False, "customer_id": None}

    def _forbidden(name):
        def boom(*a, **kw):
            raise AssertionError(f"the scheduler read the staging slot via {name}")

        return boom

    monkeypatch.setattr("app.core.credentials.load_config", _forbidden("load_config"))
    monkeypatch.setattr("app.core.credentials.load_global_config", _forbidden("load_global_config"))
    monkeypatch.setattr("app.core.credentials.cert_path", _forbidden("cert_path"))
    monkeypatch.setattr(
        "app.modules.m365_audit.auth.AuthManager.from_config", _forbidden("from_config")
    )
    monkeypatch.setattr(sched, "get_scheduler_config", lambda: dict(settings))

    def get_customer(cid):
        record_reads.append(cid)
        record = CUSTOMERS.get(cid)
        return dict(record) if record else None

    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer", staticmethod(get_customer)
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS.values()]),
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
    monkeypatch.setattr(
        "app.modules.m365_audit.collector.make_output_dir", lambda name: tmp_path / name
    )

    def build_context(**kw):
        contexts.append(kw)
        return {}

    monkeypatch.setattr("app.reports.generator.build_report_context", build_context)
    monkeypatch.setattr(
        AuditScheduler, "_check_and_alert", lambda self, ctx, name: asyncio.sleep(0)
    )
    monkeypatch.setattr(
        AuditScheduler, "_notify_audit_completed", lambda self, name, ctx=None: asyncio.sleep(0)
    )
    monkeypatch.setattr(AuditScheduler, "_auto_report_and_email", lambda self, *a: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_send_webhook", lambda self, msg: asyncio.sleep(0))
    monkeypatch.setattr(AuditScheduler, "_log_activity", staticmethod(lambda *a: None))

    yield settings, built, contexts, record_reads

    from app.core import job_state as state

    state.audit_running = False


async def test_the_named_customer_is_audited_with_its_own_record_and_certificate(wired):
    settings, built, contexts, record_reads = wired
    settings["customer_id"] = "beta"

    await AuditScheduler()._run_scheduled_audit()

    assert record_reads == ["beta"], "the record was read more than once, or another one"
    assert [(cid, cert.name) for cid, cert in built] == [("beta", "beta.pfx")]
    assert [(auth, out.name) for auth, out in _Collector.seen] == [("auth-for-beta", "Beta")]
    assert [c["customer_id"] for c in contexts] == ["beta"]


async def test_a_delegated_customer_is_audited_without_an_app_registration(wired):
    """The audit route starts a GDAP customer's audit; so does the schedule."""
    settings, built, _, _ = wired
    settings["customer_id"] = "gdap"

    await AuditScheduler()._run_scheduled_audit()

    assert [cid for cid, _ in built] == ["gdap"]


@pytest.mark.parametrize("customer_id", [None, ""])
async def test_settings_that_name_no_customer_audit_nothing_and_say_so(wired, caplog, customer_id):
    """Settings saved before the id existed. The fixture makes the staging
    slot raise, so a fallback to it fails this test rather than passing it."""
    settings, built, _, record_reads = wired
    settings["customer_id"] = customer_id

    with caplog.at_level(logging.WARNING, logger="app.services.audit_scheduler"):
        await AuditScheduler()._run_scheduled_audit()

    assert built == [] and _Collector.seen == [] and record_reads == []
    assert "names none" in caplog.text


async def test_a_customer_that_is_gone_audits_nothing_and_says_so(wired, caplog):
    settings, built, _, _ = wired
    settings["customer_id"] = "deleted-since"

    with caplog.at_level(logging.WARNING, logger="app.services.audit_scheduler"):
        await AuditScheduler()._run_scheduled_audit()

    assert built == [] and _Collector.seen == []
    assert "deleted-since no longer exists" in caplog.text


async def test_a_customer_without_a_microsoft_setup_is_not_attempted(wired, caplog):
    settings, built, _, _ = wired
    settings["customer_id"] = "half"

    with caplog.at_level(logging.WARNING, logger="app.services.audit_scheduler"):
        await AuditScheduler()._run_scheduled_audit()

    assert built == [] and _Collector.seen == []
    assert "Half has no Microsoft 365 setup" in caplog.text


async def test_a_manual_audit_in_progress_is_not_run_over(wired):
    from app.core import job_state as state

    settings, _, _, _ = wired
    settings["customer_id"] = "beta"
    state.audit_running = True
    try:
        await AuditScheduler()._run_scheduled_audit()
    finally:
        state.audit_running = False

    assert _Collector.seen == [], "the scheduler ran on top of a manual audit"


async def test_the_flag_is_released_when_the_audit_fails(wired, monkeypatch):
    from app.core import job_state as state

    settings, _, _, _ = wired
    settings["customer_id"] = "beta"

    async def fails(self):
        raise RuntimeError("Graph said no")

    monkeypatch.setattr(_Collector, "run", fails)

    await AuditScheduler()._run_scheduled_audit()

    assert state.audit_running is False


async def test_every_customer_mode_audits_every_configured_customer_delegated_ones_too(wired):
    """A GDAP customer has a tenant and no app id. The cycle's filter asked
    for an app id, so the docstring's "GDAP customers now work" never held:
    they were skipped as unconfigured. The one without a tenant still is."""
    settings, built, _, _ = wired
    settings.update(audit_all_customers=True, customer_id="beta")

    await AuditScheduler()._run_scheduled_audit()

    assert [cid for cid, _ in built] == ["acme", "beta", "gdap"]
