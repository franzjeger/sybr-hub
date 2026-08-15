"""Routes that leak one customer's data to another, and unsafe path handling.

Each test here pins a fix for a route that was reachable by any logged-in user
but reached every customer's data, or that judged a filesystem path with a
string prefix instead of a path-component boundary. The sibling routes in the
same module were already scoped; these were the ones that slipped past the
``{customer_id}``-shaped guard because their URLs never say "customer".
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.customer import CustomerManager, customer_dir_name
from app.core.database import run_migrations
from app.core.encryption import encrypted_write_json
from app.core.rbac import grant_access, set_can_write
from app.models.user import Role
from app.services.dashboard_poller import DeviceStatus
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!gap-fix"


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
    import app.core.customer as customer_module
    import app.core.database as database_module
    from app.web import state

    database_module.DB_PATH = tmp_path / "test.db"
    customer_root = tmp_path / "customers"
    customer_root.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customer_root)
    audit_root = tmp_path / "Audits"
    audit_root.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
    # compare_audits reads the module-level AUDIT_DIR, not get_audit_dir().
    monkeypatch.setattr(config_module, "AUDIT_DIR", audit_root)
    state.clear_user_audits()
    await run_migrations()
    yield
    state.clear_user_audits()


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _customer(name: str, domain: str = "") -> str:
    return CustomerManager.save_customer(
        {
            "CustomerName": name,
            "PrimaryDomain": domain,
            "TenantId": name.lower(),
            "ClientId": f"client-{name.lower()}",
        }
    )


def _seed_audit_metrics(audit_root, name: str, run: str = "2026-08-08_100000") -> None:
    run_dir = audit_root / customer_dir_name(name) / run
    run_dir.mkdir(parents=True, exist_ok=True)
    encrypted_write_json(
        run_dir / "_audit_metrics.json",
        {
            "risk_grade": "C",
            "risk_score": 55,
            "mfa_coverage_pct": 80,
            "secure_score_pct": 60,
            "total_users": 40,
            "total_warns": 7,
        },
    )


async def _token(username: str, role: Role, customers: list[str] | None = None) -> str:
    user = await create_user(username, PASSWORD, username.title(), role=role)
    for cid in customers or []:
        await grant_access(user.id, cid)
    return await create_access_token(user)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /dashboard/devices — the "all" endpoint must be scoped like its twin
# ---------------------------------------------------------------------------


async def test_all_devices_endpoint_is_scoped_to_the_caller(client, monkeypatch, tmp_path):
    from app.services.dashboard_poller import poller

    poller._cache = {
        "uf_acme_aabbcc": DeviceStatus(
            device_id="uf_acme_aabbcc", customer_id="acme", vendor="unifi",
            name="AP-Acme", model="U6", firmware="6.0", serial="aabbcc",
            status="online", uptime="1d", last_poll="t0",
        ),
        "uf_other_ddeeff": DeviceStatus(
            device_id="uf_other_ddeeff", customer_id="other", vendor="unifi",
            name="AP-Other", model="U6", firmware="6.0", serial="ddeeff",
            status="online", uptime="1d", last_poll="t0",
        ),
    }
    try:
        _customer("Acme")
        _customer("OtherCorp")
        token = await _token("tech", Role.technician, customers=["acme"])

        resp = client.get("/api/dashboard/devices", headers=_h(token))
        assert resp.status_code == 200, resp.text
        ids = {d["customer_id"] for d in resp.json()["devices"]}
        assert ids == {"acme"}, f"leaked other customers' devices: {ids}"
    finally:
        poller._cache = {}


async def test_all_devices_endpoint_is_scoped_even_for_viewer(client, monkeypatch):
    """A viewer — the lowest role — must not see another customer's devices."""
    from app.services.dashboard_poller import poller

    poller._cache = {
        "uf_acme_aabbcc": DeviceStatus(
            device_id="uf_acme_aabbcc", customer_id="acme", vendor="unifi",
            name="AP-Acme", model="U6", firmware="6.0", serial="aabbcc",
            status="online", uptime="1d", last_poll="t0",
        ),
        "uf_other_ddeeff": DeviceStatus(
            device_id="uf_other_ddeeff", customer_id="other", vendor="unifi",
            name="AP-Other", model="U6", firmware="6.0", serial="ddeeff",
            status="online", uptime="1d", last_poll="t0",
        ),
    }
    try:
        _customer("Acme")
        _customer("OtherCorp")
        token = await _token("viewer", Role.viewer, customers=["acme"])

        resp = client.get("/api/dashboard/devices", headers=_h(token))
        assert resp.status_code == 200, resp.text
        ids = {d["customer_id"] for d in resp.json()["devices"]}
        assert ids == {"acme"}, f"viewer leaked other customers' devices: {ids}"
    finally:
        poller._cache = {}


async def test_all_devices_endpoint_unrestricted_user_sees_everything(client, monkeypatch):
    from app.services.dashboard_poller import poller

    poller._cache = {
        "uf_acme_aabbcc": DeviceStatus(
            device_id="uf_acme_aabbcc", customer_id="acme", vendor="unifi",
            name="AP-Acme", model="U6", firmware="6.0", serial="aabbcc",
            status="online", uptime="1d", last_poll="t0",
        ),
        "uf_other_ddeeff": DeviceStatus(
            device_id="uf_other_ddeeff", customer_id="other", vendor="unifi",
            name="AP-Other", model="U6", firmware="6.0", serial="ddeeff",
            status="online", uptime="1d", last_poll="t0",
        ),
    }
    try:
        _customer("Acme")
        _customer("OtherCorp")
        token = await _token("admin", Role.admin)

        resp = client.get("/api/dashboard/devices", headers=_h(token))
        assert resp.status_code == 200, resp.text
        ids = {d["customer_id"] for d in resp.json()["devices"]}
        assert ids == {"acme", "other"}, f"admin lost devices: {ids}"
    finally:
        poller._cache = {}


# ---------------------------------------------------------------------------
# POST /reports/batch-summary — must be scoped like export_dashboard_excel
# ---------------------------------------------------------------------------


async def test_batch_summary_is_scoped_to_the_caller(client, tmp_path):
    audit_root = tmp_path / "Audits"
    _customer("Alpha")
    _customer("Beta")
    _seed_audit_metrics(audit_root, "Alpha")
    _seed_audit_metrics(audit_root, "Beta")

    token = await _token("tech", Role.technician, customers=["Alpha"])
    resp = client.post("/api/reports/batch-summary", json={}, headers=_h(token))
    assert resp.status_code == 200, resp.text
    assert "Alpha" in resp.text
    assert "Beta" not in resp.text, "batch-summary leaked another customer's metrics"


async def test_batch_summary_unrestricted_user_sees_all(client, tmp_path):
    audit_root = tmp_path / "Audits"
    _customer("Alpha")
    _customer("Beta")
    _seed_audit_metrics(audit_root, "Alpha")
    _seed_audit_metrics(audit_root, "Beta")

    token = await _token("admin", Role.admin)
    resp = client.post("/api/reports/batch-summary", json={}, headers=_h(token))
    assert resp.status_code == 200, resp.text
    assert "Alpha" in resp.text and "Beta" in resp.text


# ---------------------------------------------------------------------------
# batch-summary HTML — user-supplied name/domain must be escaped
# ---------------------------------------------------------------------------


async def test_batch_summary_escapes_customer_name_and_domain(client, tmp_path):
    audit_root = tmp_path / "Audits"
    evil_name = "Acme<img src=x onerror=alert(1)>"
    evil_domain = "evil<script>alert(1)</script>"
    _customer(evil_name, evil_domain)
    _seed_audit_metrics(audit_root, evil_name)

    token = await _token("admin", Role.admin)
    resp = client.post("/api/reports/batch-summary", json={}, headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "<img src=x onerror=alert(1)>" not in body, "raw HTML injected via customer name"
    assert "<script>alert(1)</script>" not in body, "raw script injected via domain"
    assert "&lt;img" in body, "customer name was not HTML-escaped"
    assert "&lt;script&gt;" in body, "domain was not HTML-escaped"


# ---------------------------------------------------------------------------
# GET /audit/compare — must call check_audit_path_access like its siblings
# ---------------------------------------------------------------------------


async def test_compare_audits_refuses_an_unassigned_customer(client, tmp_path):
    audit_root = tmp_path / "Audits"
    _customer("Alpha")
    _customer("Beta")
    _seed_audit_metrics(audit_root, "Alpha", "2026-08-08_100000")
    _seed_audit_metrics(audit_root, "Beta", "2026-08-08_110000")

    alpha_run = str(audit_root / customer_dir_name("Alpha") / "2026-08-08_100000")
    beta_run = str(audit_root / customer_dir_name("Beta") / "2026-08-08_110000")

    token = await _token("tech", Role.technician, customers=["Alpha"])
    resp = client.get(
        "/api/audit/compare",
        params={"run1": alpha_run, "run2": beta_run},
        headers=_h(token),
    )
    assert resp.status_code == 403, (
        f"compare_audits leaked another customer's metrics (got {resp.status_code})"
    )


async def test_compare_audits_allows_an_assigned_customer(client, tmp_path):
    audit_root = tmp_path / "Audits"
    _customer("Alpha")
    _seed_audit_metrics(audit_root, "Alpha", "2026-08-08_100000")
    _seed_audit_metrics(audit_root, "Alpha", "2026-08-08_110000")

    run1 = str(audit_root / customer_dir_name("Alpha") / "2026-08-08_100000")
    run2 = str(audit_root / customer_dir_name("Alpha") / "2026-08-08_110000")

    token = await _token("tech", Role.technician, customers=["Alpha"])
    resp = client.get(
        "/api/audit/compare",
        params={"run1": run1, "run2": run2},
        headers=_h(token),
    )
    assert resp.status_code == 200, (
        f"compare_audits refused an assigned customer (got {resp.status_code}): {resp.text}"
    )


# ---------------------------------------------------------------------------
# POST /reports/archive/delete — path check must be a component boundary
# ---------------------------------------------------------------------------


async def test_archive_delete_refuses_a_sibling_directory(client, tmp_path, monkeypatch):
    """A sibling sharing the audit dir's prefix must not be deletable.

    The old check was ``str(target).startswith(str(audit_dir))``; a directory
    like ``Audits_evil`` next to ``Audits`` passed it and was rmtree'd.
    """
    import app.core.config as config_module

    audit_root = tmp_path / "Audits"
    audit_root.mkdir(parents=True, exist_ok=True)
    evil_sibling = tmp_path / "Audits_evil"
    evil_sibling.mkdir(parents=True, exist_ok=True)
    (evil_sibling / "victim.txt").write_text("do not delete me")

    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
    monkeypatch.setattr(config_module, "AUDIT_DIR", audit_root)

    admin = await create_user("admin", PASSWORD, "Admin", role=Role.admin)
    await set_can_write(admin.id, True)
    token = await create_access_token(admin)
    resp = client.post(
        "/api/reports/archive/delete",
        json={"path": "../Audits_evil"},
        headers=_h(token),
    )
    assert resp.status_code in (401, 403), (
        f"sibling directory was not refused (got {resp.status_code})"
    )
    assert (evil_sibling / "victim.txt").exists(), "sibling directory contents were deleted"


async def test_archive_delete_still_allows_a_real_run(client, tmp_path, monkeypatch):
    import app.core.config as config_module

    audit_root = tmp_path / "Audits"
    run_dir = audit_root / "Alpha" / "2026-08-08_100000"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.txt").write_text("old run")

    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
    monkeypatch.setattr(config_module, "AUDIT_DIR", audit_root)

    admin = await create_user("admin", PASSWORD, "Admin", role=Role.admin)
    await set_can_write(admin.id, True)
    token = await create_access_token(admin)
    resp = client.post(
        "/api/reports/archive/delete",
        json={"path": "Alpha/2026-08-08_100000"},
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    assert not run_dir.exists(), "a legitimate run directory was not deleted"
