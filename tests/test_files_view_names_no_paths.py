"""Filer names files and dates, never the server's paths.

The view printed "/tmp/.../customers/<name>/cert.pfx" and the audit folder's
absolute path to every account. Nobody reading the screen can open a path on
the server, and the paths told them where the host keeps its data.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.customer import CustomerManager, customer_dir_name
from app.core.database import run_migrations
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!files-view-paths"


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


async def test_files_lists_names_and_runs_without_server_paths(tmp_path):
    from app.core.config import get_audit_dir

    customer_id = CustomerManager.save_customer({"CustomerName": "Example Gamma", "TenantId": "t"})
    run = get_audit_dir() / customer_dir_name("Example Gamma") / "2026-09-30_120000"
    run.mkdir(parents=True)
    (run / "report.html").write_text("<html></html>", encoding="utf-8")
    user = await create_user(
        "files-tech", PASSWORD, "Files", role=Role.technician, all_customers=True
    )
    headers = {"Authorization": f"Bearer {await create_access_token(user)}"}

    with TestClient(create_app()) as client:
        switched = client.post(
            "/api/customers/switch", headers=headers, json={"customer_id": customer_id}
        )
        assert switched.status_code == 200, switched.text
        body = client.get("/api/files", headers=headers).json()

    assert body["has_customer"] is True
    assert body["reports"] == [{"name": "report.html", "run": "2026-09-30_120000", "size": "0 KB"}]
    assert body["raw_data"]["runs"] == 1
    assert str(tmp_path) not in json.dumps(body), "a server path reached the Files view"
