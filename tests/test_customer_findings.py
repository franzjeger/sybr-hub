"""The customer page's findings: worst first, for the customer it names.

Findings used to come from the per-user "active customer" on the server, so a
second tab could make one customer's page show another's list, and a freshly
audited customer showed "no recommendations yet" because the panel listed only
findings someone had already given a status.
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
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Str0ng-Passphrase-For-Findings!"
RECS = [
    {"rec_id": "r-low", "title": "Rydd gamle kontoer", "priority": "low", "detail": "3 kontoer"},
    {"rec_id": "r-crit", "title": "Admin uten MFA", "priority": "critical", "detail": "1 admin"},
    {"rec_id": "r-med", "title": "DMARC mangler", "priority": "medium", "detail": "acme.example"},
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
    monkeypatch.setattr(
        "app.reports.recommendations.relocalise_recommendations", lambda metrics, lang: metrics
    )
    await run_migrations()
    yield tmp_path / "Audits"
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


async def _headers(username: str, customers: list[str], role=Role.technician) -> dict:
    user = await create_user(username, PASSWORD, username, role=role)
    await set_can_write(user.id, True)
    for cid in customers:
        await grant_access(user.id, cid)
    token = await create_access_token(await get_user_by_id(user.id))
    return {"Authorization": f"Bearer {token}"}


async def test_findings_come_worst_first_with_their_state(client):
    acme = _customer("Acme AS", RECS)
    h = await _headers("tech", [acme])
    r = client.get(f"/api/hub/{acme}/findings", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [f["rec_id"] for f in body["findings"]] == ["r-crit", "r-med", "r-low"]
    assert all(f["status"] == "open" and f["ticket"] is None for f in body["findings"])
    assert body["audit_date"] == "2026-09-30_120000"
    assert body["m365_ready"] is False
    assert body["integrations"]["autotask"] == {"configured": False, "linked": False}


async def test_a_status_set_on_the_page_comes_back_for_that_customer_only(client):
    acme = _customer("Acme AS", RECS)
    beta = _customer("Beta AS", RECS)
    h = await _headers("tech", [acme, beta])
    r = client.post(
        f"/api/hub/{acme}/findings/status",
        headers=h,
        json={"rec_id": "r-crit", "status": "in_progress", "notes": "Ringt kunden"},
    )
    assert r.status_code == 200, r.text

    acme_findings = client.get(f"/api/hub/{acme}/findings", headers=h).json()["findings"]
    crit = next(f for f in acme_findings if f["rec_id"] == "r-crit")
    assert (crit["status"], crit["notes"]) == ("in_progress", "Ringt kunden")
    beta_findings = client.get(f"/api/hub/{beta}/findings", headers=h).json()["findings"]
    assert all(f["status"] == "open" for f in beta_findings)


async def test_a_customer_never_audited_has_no_findings_and_no_date(client):
    acme = _customer("Acme AS")
    h = await _headers("tech", [acme])
    body = client.get(f"/api/hub/{acme}/findings", headers=h).json()
    assert body["findings"] == [] and body["audit_date"] is None


async def test_another_customers_findings_are_refused(client):
    acme = _customer("Acme AS", RECS)
    beta = _customer("Beta AS", RECS)
    h = await _headers("tech", [acme])
    assert client.get(f"/api/hub/{beta}/findings", headers=h).status_code == 403
    r = client.post(
        f"/api/hub/{beta}/findings/status", headers=h, json={"rec_id": "r-crit", "status": "done"}
    )
    assert r.status_code == 403


async def test_a_viewer_may_read_but_not_set_status(client):
    acme = _customer("Acme AS", RECS)
    h = await _headers("viewer", [acme], role=Role.viewer)
    assert client.get(f"/api/hub/{acme}/findings", headers=h).status_code == 200
    r = client.post(
        f"/api/hub/{acme}/findings/status", headers=h, json={"rec_id": "r-crit", "status": "done"}
    )
    assert r.status_code == 403


async def test_an_unknown_status_is_refused(client):
    acme = _customer("Acme AS", RECS)
    h = await _headers("tech", [acme])
    r = client.post(
        f"/api/hub/{acme}/findings/status", headers=h, json={"rec_id": "r-crit", "status": "maybe"}
    )
    assert r.status_code in (400, 422)
