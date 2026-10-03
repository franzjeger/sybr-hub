"""Every route a customer page uses names its customer, and checks access to it.

These routes used to act on the caller's "active customer", a selection the
server kept per user and every browser tab of that user shared. Now the id is
in the path, a required query parameter or the body. Two things are pinned
per route: a customer the caller cannot see is refused by its id, and the
answer is about the customer named, not another one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.customer import CustomerManager
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!explicit-customer"


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rate_limit

    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rate_limit._hits.clear()
    rate_limit._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _isolated_state(tmp_path, monkeypatch):
    import app.core.config as config_module
    import app.core.credentials as credentials_module
    import app.core.customer as customer_module
    import app.core.database as database_module
    from app.core import job_state as state
    from app.core import modules

    database_module.DB_PATH = tmp_path / "test.db"
    customer_root = tmp_path / "customers"
    customer_root.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customer_root)
    monkeypatch.setattr(credentials_module, "_DEFAULT_CONFIG_PATH", tmp_path / "audit_config.json")
    monkeypatch.setattr(credentials_module, "_DEFAULT_CERT_PATH", tmp_path / "audit_cert.pfx")
    audit_root = tmp_path / "audits"
    audit_root.mkdir()
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
    modules.set_enabled({"tailscale": True})
    state.clear_user_audits()
    await run_migrations()
    yield
    state.clear_user_audits()


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _customer(name: str, tenant: str) -> str:
    return CustomerManager.save_customer(
        {
            "CustomerName": name,
            "PrimaryDomain": f"{tenant}.example",
            "TenantId": tenant,
            "ClientId": f"client-{tenant}",
            # Both linked to IT Glue org 1, so an upload is refused only for
            # the customer, never for the organization.
            "ITGlueOrgId": "1",
        }
    )


async def _headers(username: str, *, grants: list[str] | None = None) -> dict[str, str]:
    """A technician with write; scoped to ``grants`` when given."""
    user = await create_user(
        username, PASSWORD, username, role=Role.technician, all_customers=grants is None
    )
    await set_can_write(user.id, True)
    for cid in grants or []:
        await grant_access(user.id, cid)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


# Each route a customer page (or one of its tabs, or a tool acting on one
# customer) calls, with the customer in the place the route takes it.
ROUTES = [
    ("get", "/api/customer/{cid}/notes", None),
    ("post", "/api/customer/{cid}/notes", {"notes": "x"}),
    ("get", "/api/customer/{cid}/tags", None),
    ("post", "/api/customer/{cid}/tags", {"tags": ["x"]}),
    ("get", "/api/customer/{cid}/status", None),
    ("get", "/api/customer/{cid}/files", None),
    ("post", "/api/customer/renew", {"customer_id": "{cid}"}),
    ("post", "/api/customer/wipe", {"customer_id": "{cid}"}),
    ("get", "/api/audit/scope?customer_id={cid}", None),
    ("post", "/api/audit/scope?customer_id={cid}", {"enabled_sections": []}),
    ("get", "/api/audit/sections?customer_id={cid}", None),
    ("post", "/api/audit/validate-permissions?customer_id={cid}", None),
    ("post", "/api/audit/stream?customer_id={cid}", None),
    ("get", "/api/audit/progress/{cid}", None),
    ("get", "/api/dashboard?customer_id={cid}", None),
    ("post", "/api/history/load", {"customer_id": "{cid}", "path": "/nowhere"}),
    ("post", "/api/report/generate", {"customer_id": "{cid}"}),
    ("post", "/api/report/csv", {"customer_id": "{cid}"}),
    ("post", "/api/email/send-report", {"customer_id": "{cid}", "to": "a@example.invalid"}),
    ("get", "/api/remediation/{cid}", None),
    ("post", "/api/remediation/{cid}", {"rec_id": "r1", "status": "done"}),
    ("get", "/api/remediation/{cid}/summary", None),
    ("get", "/api/network-devices/{cid}", None),
    ("post", "/api/unifi/save/{cid}", {"site": "default"}),
    ("post", "/api/fortigate/save/{cid}", {"vdom": "root"}),
    ("get", "/api/network/config-backups/{cid}", None),
    ("post", "/api/network/save-config-backup/{cid}", {"host": "192.0.2.1", "config": "x"}),
    ("post", "/api/network/quick-audit/{cid}", None),
    ("get", "/api/itglue/available-reports?customer_id={cid}", None),
    ("post", "/api/itglue/upload/audit", {"customer_id": "{cid}", "org_id": "1"}),
    ("get", "/api/tailscale/customer/{cid}/nodes", None),
]


def _fill(value, cid: str):
    if isinstance(value, str):
        return value.replace("{cid}", cid)
    if isinstance(value, dict):
        return {k: _fill(v, cid) for k, v in value.items()}
    return value


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
async def test_a_customer_the_caller_cannot_see_is_refused_by_its_id(client, method, path, body):
    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    headers = await _headers("alpha-only", grants=[alpha])

    refused = client.request(method, _fill(path, beta), headers=headers, json=_fill(body, beta))
    assert refused.status_code == 403, (path, refused.status_code, refused.text)

    # The same call for the caller's own customer gets past the check.
    allowed = client.request(method, _fill(path, alpha), headers=headers, json=_fill(body, alpha))
    assert allowed.status_code != 403, (path, allowed.text)


async def test_notes_go_to_the_customer_named_and_only_there(client):
    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    headers = await _headers("notes-tech")

    for cid, text in ((alpha, "alpha gate code"), (beta, "beta alarm")):
        saved = client.post(f"/api/customer/{cid}/notes", headers=headers, json={"notes": text})
        assert saved.status_code == 200, saved.text
        assert saved.json()["customer_id"] == cid

    assert client.get(f"/api/customer/{alpha}/notes", headers=headers).json()["notes"] == (
        "alpha gate code"
    )
    assert client.get(f"/api/customer/{beta}/notes", headers=headers).json()["notes"] == (
        "beta alarm"
    )


async def test_the_audit_scope_is_kept_per_customer(client):
    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    headers = await _headers("scope-tech")

    client.post(
        f"/api/audit/scope?customer_id={alpha}",
        headers=headers,
        json={"enabled_sections": ["MFA Methods"]},
    )

    a = client.get(f"/api/audit/scope?customer_id={alpha}", headers=headers).json()
    b = client.get(f"/api/audit/scope?customer_id={beta}", headers=headers).json()
    assert a["scope"] == {"enabled_sections": ["MFA Methods"]}
    assert b["scope"] is None


async def test_files_and_status_answer_for_the_customer_named(client):
    from app.core.config import get_audit_dir
    from app.core.customer import customer_dir_name

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    run = get_audit_dir() / customer_dir_name("Beta") / "2026-09-30_120000"
    run.mkdir(parents=True)
    (run / "beta_report.html").write_text("<html></html>", encoding="utf-8")
    headers = await _headers("files-tech")

    alpha_files = client.get(f"/api/customer/{alpha}/files", headers=headers).json()
    beta_files = client.get(f"/api/customer/{beta}/files", headers=headers).json()
    assert alpha_files["credentials"]["customer_name"] == "Alpha"
    assert alpha_files["reports"] == []
    assert [r["name"] for r in beta_files["reports"]] == ["beta_report.html"]
    status = client.get(f"/api/customer/{beta}/status", headers=headers).json()
    assert status["customer"]["name"] == "Beta"
    assert status["customer"]["tenant_id"] == "beta"


async def test_an_audit_starts_with_the_named_customers_own_credentials(monkeypatch):
    """The job reads the customer once, from the request, and audits that one.

    It resolved "the active customer" inside the job, so a switch in another
    tab between the click and that line audited the other tenant into this
    customer's folder.
    """
    from starlette.requests import Request

    from app.core.credentials import save_config
    from app.web.routes import audit

    alpha = _customer("Alpha", "alpha")
    _customer("Beta", "beta")
    # The staging slot names another tenant; it must not be read either.
    save_config({"CustomerName": "Staged", "TenantId": "staged", "ClientId": "c"})
    monkeypatch.setattr("app.core.credentials.get_secret", lambda tenant, key: "secret")
    monkeypatch.setattr("app.modules.m365_audit.collector.make_output_dir", lambda name: None)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

    error, spec = audit._prepare_audit(request, alpha)

    assert error is None
    assert spec["customer_id"] == alpha
    assert spec["cfg"]["TenantId"] == "alpha"
    assert spec["cert_path"] == CustomerManager.get_cert_path(alpha)


async def test_a_delegated_customer_can_start_an_audit_without_an_app_secret(monkeypatch):
    """The customer page offers to audit a GDAP customer; the start agreed only
    when it also held an app id and secret it does not use."""
    from starlette.requests import Request

    from app.web.routes import audit

    gdap = CustomerManager.save_customer(
        {"CustomerName": "Delegated", "TenantId": "delegated", "AuthMode": "gdap"}
    )
    monkeypatch.setattr("app.core.credentials.get_secret", lambda tenant, key: None)
    monkeypatch.setattr("app.modules.m365_audit.collector.make_output_dir", lambda name: None)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

    error, spec = audit._prepare_audit(request, gdap)

    assert error is None, error
    assert spec["cfg"]["AuthMode"] == "gdap"


async def test_the_running_audit_is_reported_with_its_customer(client):
    from app.core import job_state as state

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    headers = await _headers("progress-tech")
    me = client.get("/api/auth/me", headers=headers).json()["user"]["id"]
    run = state.begin_user_audit(me, alpha)
    run.customer_name = "Alpha"

    own = client.get("/api/audit/progress", headers=headers).json()
    assert own["running"] is True
    assert own["customer_id"] == alpha and own["customer_name"] == "Alpha"
    # The page of another customer asks for that customer: nothing running.
    assert client.get(f"/api/audit/progress/{beta}", headers=headers).json()["running"] is False


async def test_a_baseline_deploy_reads_the_customer_it_names(monkeypatch):
    """BaselineEngine called CustomerManager.set_active_id, which never existed:
    every plan and apply failed before reaching the tenant."""
    from app.services import baseline_engine

    alpha = _customer("Alpha", "alpha")
    monkeypatch.setattr(baseline_engine, "get_secret", lambda tenant, key: "secret")
    monkeypatch.setattr(baseline_engine, "GraphClient", lambda credential: object())

    engine = baseline_engine.BaselineEngine(alpha)

    assert engine.tenant_id == "alpha"
    assert engine.client_id == "client-alpha"
