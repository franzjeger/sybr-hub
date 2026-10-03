"""Historikk lists the audit runs the customer page talks about.

The customer page said "Auditert 30. september" for a customer whose
Historikk said "Ingen tidligere kjøringer. Kjør en audit først". The page
counts a run folder holding metrics; the listing counted only folders holding
evidence (.txt) files. One rule now: evidence or metrics.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.customer import CustomerManager, customer_dir_name
from app.core.database import run_migrations
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!history-listing"


@pytest.fixture(autouse=True)
async def _isolated_state(tmp_path, monkeypatch):
    import app.core.config as config_module
    import app.core.customer as customer_module
    import app.core.database as database_module
    import app.web.middleware.rate_limit as rate_limit

    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()
    database_module.DB_PATH = tmp_path / "test.db"
    customer_root = tmp_path / "customers"
    customer_root.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customer_root)
    audit_root = tmp_path / "audits"
    audit_root.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
    await run_migrations()
    yield
    _reset_users_exist_cache()


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


async def _token() -> str:
    user = await create_user(
        "history-tech", PASSWORD, "History", role=Role.technician, all_customers=True
    )
    return await create_access_token(user)


async def test_a_run_with_metrics_and_no_evidence_is_listed(client):
    from app.core.config import get_audit_dir
    from app.core.encryption import encrypted_write_json

    customer_id = CustomerManager.save_customer({"CustomerName": "Example Beta", "TenantId": "t"})
    folder = get_audit_dir() / customer_dir_name("Example Beta")
    metrics_only = folder / "2026-09-30_120000"
    metrics_only.mkdir(parents=True)
    encrypted_write_json(
        metrics_only / "_audit_metrics.json", {"risk_grade": "C", "risk_score": 58}
    )
    with_evidence = folder / "2026-09-01_080000"
    with_evidence.mkdir()
    (with_evidence / "01_tenant.txt").write_text("evidence", encoding="utf-8")
    (folder / "2026-08-01_080000").mkdir()  # an empty folder is not a run

    token = await _token()
    runs = client.get("/api/history", headers={"Authorization": f"Bearer {token}"}).json()[
        "history"
    ]

    assert [r["timestamp"] for r in runs] == ["2026-09-30_120000", "2026-09-01_080000"]
    latest, older = runs
    assert latest["file_count"] == 0
    assert latest["has_metrics"] is True
    assert latest["metrics"]["risk_grade"] == "C"
    assert older["file_count"] == 1
    assert older["has_metrics"] is False
    # The interface offers the summary report for a run without evidence, and
    # that report is addressed by the customer's id, not the folder name.
    assert latest["customer_id"] == customer_id
