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
