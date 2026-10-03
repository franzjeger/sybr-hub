"""Oversikt leads with who needs attention: open findings per customer.

The dashboard sorted customers by Sikkerhetsscore and counted "needs
attention" from the score, MFA and the audit's age; the findings a
technician works through, and what has been decided about them, were only
on each customer's page. The overview now carries each customer's open
findings per severity, from the newest run less the ones someone closed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.customer import CustomerManager, customer_dir_name
from app.core.database import run_migrations
from app.core.encryption import encrypted_write_json
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.services.remediation import open_finding_counts, set_remediation
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Str0ng-Passphrase-For-Overview!"
RECS = [
    {"rec_id": "r-low", "title": "Rydd gamle kontoer", "priority": "low"},
    {"rec_id": "r-crit", "title": "Admin uten MFA", "priority": "critical"},
    {"rec_id": "r-med", "title": "DMARC mangler", "priority": "medium"},
    {"rec_id": "r-high", "title": "Gjester uten MFA", "priority": "high"},
]


@pytest.fixture(autouse=True)
async def _isolated(tmp_path, monkeypatch):
    import app.core.config as config_module
    import app.core.customer as customer_module
    import app.core.database as database_module
    import app.web.middleware.rate_limit as rate_limit

    _reset_users_exist_cache()
    rate_limit._hits.clear()
    database_module.DB_PATH = tmp_path / "test.db"
    (tmp_path / "customers").mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", tmp_path / "Audits")
    await run_migrations()
    yield
    _reset_users_exist_cache()


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _customer(name: str, recs=None) -> str:
    cid = CustomerManager.save_customer({"CustomerName": name, "TenantId": name.lower()})
    if recs is not None:
        from app.core.config import get_audit_dir

        run = get_audit_dir() / customer_dir_name(name) / "2026-09-30_120000"
        run.mkdir(parents=True)
        encrypted_write_json(run / "_audit_metrics.json", {"recommendations": recs})
    return cid


async def _headers(customers: list[str]) -> dict:
    user = await create_user("tech", PASSWORD, "tech", role=Role.technician)
    await set_can_write(user.id, True)
    for cid in customers:
        await grant_access(user.id, cid)
    token = await create_access_token(await get_user_by_id(user.id))
    return {"Authorization": f"Bearer {token}"}


async def test_the_overview_counts_open_findings_per_severity(client):
    acme = _customer("Acme AS", RECS)
    never = _customer("Ingen Audit AS")
    h = await _headers([acme, never])
    # Closed (done or ignored) leaves the count; in progress is still open.
    for rec_id, status in (("r-crit", "done"), ("r-high", "in_progress"), ("r-low", "ignored")):
        r = client.post(
            f"/api/hub/{acme}/findings/status", headers=h, json={"rec_id": rec_id, "status": status}
        )
        assert r.status_code == 200, r.text

    customers = {
        c["customer_id"]: c
        for c in client.get("/api/dashboard/overview", headers=h).json()["customers"]
    }
    assert customers[acme]["open_findings"] == {"critical": 0, "high": 1, "medium": 1, "low": 0}
    # Never audited: no count at all, which the page shows as unknown, not as none.
    assert customers[never]["open_findings"] is None


async def test_a_title_keyed_decision_and_an_unknown_priority_count_as_the_page_counts_them():
    """Runs from before ids existed were tracked by title, and a finding with
    no or an unknown priority shows as medium on the customer page."""
    recs = [
        {"title": "Gammel anbefaling", "priority": "critical"},
        {"rec_id": "r-x", "title": "Uten prioritet"},
        {"rec_id": "r-y", "title": "Rar prioritet", "priority": "urgent"},
        "not a recommendation",
    ]
    await set_remediation("cust-1", "Gammel anbefaling", "done")
    counts = await open_finding_counts({"cust-1": recs, "cust-2": []})
    assert counts["cust-1"] == {"critical": 0, "high": 0, "medium": 2, "low": 0}
    assert counts["cust-2"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert await open_finding_counts({}) == {}
