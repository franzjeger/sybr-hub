"""The bulk audit runs every customer set up for an audit, delegated ones too.

Its filter asked for a TenantId and a ClientId. A GDAP customer has a tenant
and no app id, so every delegated customer was counted as unconfigured and
skipped, though the same customer audited from its own page was fine. The
filter is now the rule the customer page shows (credentials.m365_ready).
"""

from __future__ import annotations

import json

import pytest

from app.core import job_state as state
from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)

TENANT_APP = "00000000-0000-0000-0000-00000000000a"
TENANT_GDAP = "00000000-0000-0000-0000-00000000000b"
TENANT_NO_SECRET = "00000000-0000-0000-0000-00000000000c"

CUSTOMERS = [
    {"_id": "app", "CustomerName": "Kunde App", "TenantId": TENANT_APP, "ClientId": "app-id"},
    {"_id": "gdap", "CustomerName": "Kunde GDAP", "TenantId": TENANT_GDAP, "AuthMode": "gdap"},
    # An app id whose secret is gone: the customer page says it is not set up.
    {
        "_id": "nosecret",
        "CustomerName": "Kunde Uten Hemmelighet",
        "TenantId": TENANT_NO_SECRET,
        "ClientId": "app-id-2",
    },
    {"_id": "bare", "CustomerName": "Kunde Uten Oppsett"},
]


@pytest.fixture
def bulk(monkeypatch):
    """The bulk route with each audit stopped at its sign-in."""
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS]),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: next((dict(c) for c in CUSTOMERS if c["_id"] == cid), None)),
    )
    monkeypatch.setattr(
        "app.core.credentials.get_secret",
        lambda name, kind: "s3cret" if (name, kind) == (TENANT_APP, "client_secret") else None,
    )

    def _stop(customer, cert):
        raise RuntimeError(f"stopped before signing in to {customer['CustomerName']}")

    async def _quiet(*a, **kw):
        return None

    from app.services.audit_scheduler import scheduler

    monkeypatch.setattr("app.modules.m365_audit.auth.get_auth_for_customer", _stop)
    monkeypatch.setattr(scheduler, "_send_webhook", _quiet)
    yield
    state.bulk_audit_running = False
    state.audit_running = False


def _events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


async def test_a_delegated_customer_is_audited_and_an_unready_one_is_not(client, bulk):
    headers = await login("bulk-admin", role=Role.admin, all_customers=True)

    response = client.post("/api/audit/bulk", headers=headers)

    assert response.status_code == 200, response.text
    events = _events(response.text)
    started = next(e for e in events if e["type"] == "bulk_started")
    assert started["customers"] == ["Kunde App", "Kunde GDAP"], (
        "the delegated customer was skipped as unconfigured"
    )
    assert started["skipped_unconfigured"] == 2
    attempted = {e["customer"] for e in events if e["type"] == "customer_error"}
    assert attempted == {"Kunde App", "Kunde GDAP"}
    assert events[-1]["type"] == "bulk_done"


def test_delegated_access_still_needs_a_tenant(bulk):
    from app.core.credentials import m365_ready
    from app.web.routes.audit import _bulk_targets

    customer = {"_id": "incomplete", "AuthMode": "gdap"}
    assert not m365_ready(customer)
    assert _bulk_targets([customer]) == []


@pytest.mark.parametrize("language", ["no", "en", "de", None])
async def test_bulk_reports_and_summary_follow_the_hub_language(
    client, bulk, monkeypatch, tmp_path, language
):
    from app.core.config import save_app_settings

    save_app_settings({"ui_language": language})
    monkeypatch.setattr("app.modules.m365_audit.auth.get_auth_for_customer", lambda *a: object())
    monkeypatch.setattr(
        "app.modules.m365_audit.collector.make_output_dir", lambda name: tmp_path / name
    )

    class Collector:
        def __init__(self, **kwargs):
            pass

        async def run(self):
            return []

    generated = []
    contexts = []
    monkeypatch.setattr("app.modules.m365_audit.collector.AuditCollector", Collector)
    monkeypatch.setattr(
        "app.reports.generator.generate_reports", lambda **kwargs: generated.append(kwargs)
    )

    def build(*args, **kwargs):
        contexts.append(kwargs)
        return {"risk_grade": "B", "risk_score": 71}

    monkeypatch.setattr("app.reports.generator.build_report_context", build)
    headers = await login("bulk-language", role=Role.admin, all_customers=True)

    response = client.post("/api/audit/bulk", headers=headers)

    assert response.status_code == 200, response.text
    events = _events(response.text)
    assert [e["status"] for e in events if e["type"] == "customer_done"] == ["done", "done"]
    expected = language if language in ("no", "en") else "no"
    assert [g["lang"] for g in generated] == [expected, expected]
    assert [c["lang"] for c in contexts] == [expected, expected]
