"""An authenticated user's active customer must never be process-global."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.customer import CustomerManager
from app.core.database import run_migrations
from app.core.rbac import grant_access, revoke_access, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Test1234!customer-context"


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
    from app.web import state

    database_module.DB_PATH = tmp_path / "test.db"
    customer_root = tmp_path / "customers"
    customer_root.mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customer_root)
    monkeypatch.setattr(credentials_module, "_DEFAULT_CONFIG_PATH", tmp_path / "audit_config.json")
    monkeypatch.setattr(credentials_module, "_LEGACY_CONFIG_PATH", tmp_path / "legacy_config.json")
    monkeypatch.setattr(credentials_module, "_DEFAULT_CERT_PATH", tmp_path / "audit_cert.pfx")
    monkeypatch.setattr(credentials_module, "_LEGACY_CERT_PATH", tmp_path / "legacy_cert.pfx")
    audit_root = tmp_path / "audits"
    audit_root.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "_DEFAULT_AUDIT_DIR", audit_root)
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
        }
    )


async def _auth(
    username: str,
    *,
    all_customers: bool = True,
    role: Role = Role.technician,
) -> tuple[str, str]:
    user = await create_user(
        username,
        PASSWORD,
        username,
        role=role,
        all_customers=all_customers,
    )
    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    assert user is not None
    token = await create_access_token(user)
    return user.id, token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_two_users_keep_independent_active_customers(client):
    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    _, alpha_token = await _auth("alpha-tech")
    _, beta_token = await _auth("beta-tech")

    response = client.post(
        "/api/customers/switch",
        headers=_headers(alpha_token),
        json={"customer_id": alpha},
    )
    assert response.status_code == 200, response.text

    # A second user starts with no selection. The old process-global active.txt
    # value must never leak into their request as a convenient fallback.
    second_before = client.get("/api/customers", headers=_headers(beta_token)).json()
    assert second_before["active_id"] is None

    response = client.post(
        "/api/customers/switch",
        headers=_headers(beta_token),
        json={"customer_id": beta},
    )
    assert response.status_code == 200, response.text

    alpha_list = client.get("/api/customers", headers=_headers(alpha_token)).json()
    beta_list = client.get("/api/customers", headers=_headers(beta_token)).json()
    assert alpha_list["active_id"] == alpha
    assert beta_list["active_id"] == beta
    assert [c["_id"] for c in alpha_list["customers"] if c["is_active"]] == [alpha]
    assert [c["_id"] for c in beta_list["customers"] if c["is_active"]] == [beta]

    alpha_status = client.get("/api/status", headers=_headers(alpha_token)).json()
    beta_status = client.get("/api/status", headers=_headers(beta_token)).json()
    assert alpha_status["customer"]["name"] == "Alpha"
    assert beta_status["customer"]["name"] == "Beta"

    # The middleware must reset its ContextVar after every request, and web
    # selections must not recreate the legacy process-wide pointer.
    assert CustomerManager.get_active_id() is None
    assert not (CustomerManager.get_customer_dir("") / "active.txt").exists()
    selections = list((CustomerManager.get_customer_dir("") / ".active").glob("*.txt"))
    assert len(selections) == 2
    assert all(len(path.stem) == 64 and path.stem.isalnum() for path in selections)


async def test_audit_progress_and_cancellation_are_isolated_per_user(client):
    from app.web import state

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    alpha_user, alpha_token = await _auth("alpha-auditor")
    beta_user, beta_token = await _auth("beta-auditor")

    for token, customer_id in ((alpha_token, alpha), (beta_token, beta)):
        response = client.post(
            "/api/customers/switch",
            headers=_headers(token),
            json={"customer_id": customer_id},
        )
        assert response.status_code == 200, response.text

    alpha_run = state.begin_user_audit(alpha_user, alpha)
    beta_run = state.begin_user_audit(beta_user, beta)
    alpha_run.progress = {
        "progress": 25,
        "current_section": "Alpha users",
        "total_sections": 4,
        "completed": 1,
    }
    beta_run.progress = {
        "progress": 75,
        "current_section": "Beta devices",
        "total_sections": 4,
        "completed": 3,
    }

    alpha_progress = client.get("/api/audit/progress", headers=_headers(alpha_token)).json()
    beta_progress = client.get("/api/audit/progress", headers=_headers(beta_token)).json()
    assert alpha_progress["current_section"] == "Alpha users"
    assert beta_progress["current_section"] == "Beta devices"
    assert alpha_progress["run_id"] != beta_progress["run_id"]

    # Changing the view must not strand the user's collector, and cancellation
    # still follows ownership rather than whichever customer is now visible.
    response = client.post(
        "/api/customers/switch",
        headers=_headers(alpha_token),
        json={"customer_id": beta},
    )
    assert response.status_code == 200, response.text

    response = client.post("/api/audit/cancel", headers=_headers(alpha_token))
    assert response.status_code == 200, response.text
    assert alpha_run.cancel_requested is True
    assert beta_run.cancel_requested is False


async def test_reattach_to_a_finished_run_replays_the_outcome_without_restarting(client):
    """A reconnect (?attach=1) must re-attach, never launch a duplicate audit.

    When the run has already ended, it replays the stored outcome and starts
    nothing — the exact hazard the old "every reopen starts a new audit" code
    had, now closed by attach-only.
    """
    from app.web import state

    alpha = _customer("Alpha", "alpha")
    user_id, token = await _auth("alpha-reattach")
    resp = client.post("/api/customers/switch", headers=_headers(token), json={"customer_id": alpha})
    assert resp.status_code == 200, resp.text

    state.audit_running = False
    run = state.begin_user_audit(user_id, alpha)
    run.running = False  # finished
    run.terminal = {"type": "done", "results": []}

    body = client.get("/api/audit/stream?attach=1", headers=_headers(token)).text
    assert '"reattached": true' in body
    assert '"type": "done"' in body
    assert state.audit_running is False, "re-attach must not start a new audit"


async def test_reattach_with_no_active_run_reports_ended_and_starts_nothing(client):
    from app.web import state

    alpha = _customer("Alpha", "alpha")
    _, token = await _auth("alpha-noreattach")
    resp = client.post("/api/customers/switch", headers=_headers(token), json={"customer_id": alpha})
    assert resp.status_code == 200, resp.text

    state.audit_running = False
    body = client.get("/api/audit/stream?attach=1", headers=_headers(token)).text
    assert '"type": "ended"' in body
    assert state.audit_running is False, "attach-only must never start an audit"


async def test_history_load_cannot_select_another_customers_run(client):
    from app.core.config import get_audit_dir
    from app.core.customer import customer_dir_name
    from app.web import state

    alpha = _customer("Alpha", "alpha")
    _customer("Beta", "beta")
    user_id, token = await _auth("alpha-history", all_customers=False)
    await grant_access(user_id, alpha)

    response = client.post(
        "/api/customers/switch",
        headers=_headers(token),
        json={"customer_id": alpha},
    )
    assert response.status_code == 200, response.text

    alpha_run = get_audit_dir() / customer_dir_name("Alpha") / "2026-08-08_100000"
    beta_run = get_audit_dir() / customer_dir_name("Beta") / "2026-08-08_110000"
    for run in (alpha_run, beta_run):
        run.mkdir(parents=True)
        (run / "01_tenant.txt").write_text("test", encoding="utf-8")

    denied = client.post("/api/history/load", headers=_headers(token), json={"path": str(beta_run)})
    assert denied.status_code == 403, denied.text
    assert state.get_user_audit(user_id) is None

    allowed = client.post(
        "/api/history/load", headers=_headers(token), json={"path": str(alpha_run)}
    )
    assert allowed.status_code == 200, allowed.text
    selected = state.get_user_audit(user_id, alpha)
    assert selected is not None
    assert selected.out_dir == alpha_run


async def test_switching_customer_invalidates_the_selected_report_context(client):
    from app.core.config import get_audit_dir
    from app.core.customer import customer_dir_name
    from app.web import state

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    user_id, token = await _auth("report-switcher")
    headers = _headers(token)

    response = client.post("/api/customers/switch", headers=headers, json={"customer_id": alpha})
    assert response.status_code == 200, response.text

    alpha_run = get_audit_dir() / customer_dir_name("Alpha") / "2026-08-08_120000"
    alpha_run.mkdir(parents=True)
    state.select_user_audit(
        user_id,
        alpha,
        out_dir=alpha_run,
        results=[
            {
                "name": "Tenant Info",
                "status": "done",
                "warns": [],
                "files": [],
                "error": None,
            }
        ],
    )

    response = client.post("/api/customers/switch", headers=headers, json={"customer_id": beta})
    assert response.status_code == 200, response.text

    export = client.post("/api/report/csv", headers=headers)
    assert export.status_code == 400, export.text


async def test_host_actions_and_bulk_audit_require_admin(client):
    _, tech_token = await _auth("restricted-tech")

    for method, path, body in (
        ("post", "/api/open-folder", {}),
        ("post", "/api/email/test", {"to": "test@example.invalid"}),
        ("get", "/api/audit/bulk", None),
        ("post", "/api/vpn/force-disconnect", None),
    ):
        response = client.request(method, path, headers=_headers(tech_token), json=body)
        assert response.status_code == 403, (path, response.text)


async def test_vpn_profiles_connections_and_mutations_are_customer_scoped(client, monkeypatch):
    from app.models.vpn import VpnProtocol, VpnState
    from app.services import vpn_manager

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    user_id, token = await _auth("alpha-vpn", all_customers=False)
    await grant_access(user_id, alpha)

    alpha_profile = await vpn_manager.create_profile(
        "Alpha VPN",
        VpnProtocol.openvpn,
        {"config_content": "client"},
        customer_id=alpha,
    )
    beta_profile = await vpn_manager.create_profile(
        "Beta VPN",
        VpnProtocol.openvpn,
        {"config_content": "client"},
        customer_id=beta,
    )
    vpn_manager._connections.update(
        {
            alpha_profile.id: {
                "state": VpnState.connected,
                "interface": "tun-alpha",
                "owned_by": "alpha-vpn",
            },
            beta_profile.id: {
                "state": VpnState.connected,
                "interface": "tun-beta",
                "owned_by": "beta-vpn",
            },
        }
    )

    async def _stats(profile_id=None):
        return {"selected_profile": profile_id}

    monkeypatch.setattr(vpn_manager, "get_stats", _stats)
    try:
        headers = _headers(token)
        profiles = client.get("/api/vpn/profiles", headers=headers)
        assert profiles.status_code == 200, profiles.text
        assert [profile["id"] for profile in profiles.json()["profiles"]] == [alpha_profile.id]

        status = client.get("/api/vpn/status", headers=headers)
        assert status.status_code == 200, status.text
        assert [connection["profile_id"] for connection in status.json()["connections"]] == [
            alpha_profile.id
        ]
        assert status.json()["stats"]["selected_profile"] == alpha_profile.id

        for method, path, body in (
            ("get", f"/api/vpn/profiles/{beta_profile.id}", None),
            ("post", "/api/vpn/disconnect", {"profile_id": beta_profile.id}),
            ("delete", f"/api/vpn/profiles/{beta_profile.id}", None),
        ):
            denied = client.request(method, path, headers=headers, json=body)
            assert denied.status_code == 403, (path, denied.text)

        shared = client.post(
            "/api/vpn/profiles",
            headers=headers,
            json={"name": "Shared", "protocol": "openvpn", "config": {}},
        )
        other_customer = client.post(
            "/api/vpn/profiles",
            headers=headers,
            json={
                "name": "Beta",
                "protocol": "openvpn",
                "config": {},
                "customer_id": beta,
            },
        )
        assert shared.status_code == 403, shared.text
        assert other_customer.status_code == 403, other_customer.text
    finally:
        vpn_manager._connections.clear()


async def test_revoked_customer_selection_fails_closed(client):
    alpha = _customer("Alpha", "alpha")
    user_id, token = await _auth("scoped-tech", all_customers=False)
    await grant_access(user_id, alpha)

    response = client.post(
        "/api/customers/switch",
        headers=_headers(token),
        json={"customer_id": alpha},
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/status", headers=_headers(token)).json()["has_config"] is True

    await revoke_access(user_id, alpha)

    customers = client.get("/api/customers", headers=_headers(token)).json()
    status = client.get("/api/status", headers=_headers(token)).json()
    assert customers["customers"] == []
    assert customers["active_id"] is None
    assert status["has_config"] is False


async def test_explicit_customer_id_cannot_bypass_active_scope(client):
    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    user_id, token = await _auth("scoped-writer", all_customers=False)
    await grant_access(user_id, alpha)

    response = client.post(
        "/api/customer/tags",
        headers=_headers(token),
        json={"customer_id": beta, "tags": ["should-not-land"]},
    )
    assert response.status_code == 403, response.text
    assert CustomerManager.get_tags(beta) == []


async def test_concurrent_tasks_do_not_share_customer_context():
    from app.core.customer import (
        bind_request_customer_scope,
        reset_request_customer_scope,
    )

    alpha = _customer("Alpha", "alpha")
    beta = _customer("Beta", "beta")
    both_ready = asyncio.Event()
    ready_count = 0
    ready_lock = asyncio.Lock()

    async def choose(user_id: str, customer_id: str) -> str | None:
        nonlocal ready_count
        token = bind_request_customer_scope(user_id, None)
        try:
            CustomerManager.set_active(customer_id)
            async with ready_lock:
                ready_count += 1
                if ready_count == 2:
                    both_ready.set()
            await both_ready.wait()
            await asyncio.sleep(0)
            return CustomerManager.get_active_id()
        finally:
            reset_request_customer_scope(token)

    selected = await asyncio.gather(
        choose("user-alpha", alpha),
        choose("user-beta", beta),
    )
    assert selected == [alpha, beta]


def test_legacy_migration_is_explicit_without_becoming_a_web_fallback():
    from app.core.credentials import load_config, save_config
    from app.core.customer import (
        bind_request_customer_scope,
        reset_request_customer_scope,
    )

    save_config(
        {
            "CustomerName": "Legacy Customer",
            "TenantId": "legacy",
            "ClientId": "legacy-client",
        }
    )
    token = bind_request_customer_scope("web-user", None)
    try:
        assert load_config() is None
        migrated = CustomerManager.migrate_legacy()
        assert migrated == "Legacy_Customer"
        assert CustomerManager.get_active_id() is None
    finally:
        reset_request_customer_scope(token)

    assert CustomerManager.get_active_id() == "Legacy_Customer"


async def test_register_uses_setup_staging_not_active_customer(client):
    from app.core.credentials import save_cert, save_config
    from app.core.encryption import encrypted_read_bytes, encrypted_write_bytes

    alpha = _customer("Alpha", "alpha")
    _, token = await _auth("setup-tech")
    encrypted_write_bytes(CustomerManager.get_cert_path(alpha), b"alpha-cert")

    response = client.post(
        "/api/customers/switch",
        headers=_headers(token),
        json={"customer_id": alpha},
    )
    assert response.status_code == 200, response.text

    save_config(
        {
            "CustomerName": "Beta",
            "PrimaryDomain": "beta.example",
            "TenantId": "beta",
            "ClientId": "client-beta",
        }
    )
    save_cert(b"beta-cert")

    response = client.post("/api/customers/register", headers=_headers(token))
    assert response.status_code == 200, response.text
    beta = response.json()["customer_id"]
    assert CustomerManager.get_customer(alpha)["TenantId"] == "alpha"
    assert CustomerManager.get_customer(beta)["TenantId"] == "beta"
    assert encrypted_read_bytes(CustomerManager.get_cert_path(beta)) == b"beta-cert"


@pytest.mark.parametrize("endpoint", ["/api/customer/wipe", "/api/customer/renew"])
async def test_setup_reset_never_deletes_active_customer_secrets(client, monkeypatch, endpoint):
    import app.core.credentials as credentials_module

    alpha = _customer("Alpha", "alpha")
    _, token = await _auth(f"reset-tech-{endpoint.rsplit('/', 1)[-1]}")
    response = client.post(
        "/api/customers/switch",
        headers=_headers(token),
        json={"customer_id": alpha},
    )
    assert response.status_code == 200, response.text

    credentials_module.save_config(
        {
            "CustomerName": "Beta staging",
            "TenantId": "beta",
            "ClientId": "client-beta",
        }
    )
    deleted_tenants: list[str] = []
    monkeypatch.setattr(credentials_module, "delete_all_secrets", deleted_tenants.append)

    response = client.post(endpoint, headers=_headers(token))
    assert response.status_code == 200, response.text
    assert deleted_tenants == ["beta"]
    assert credentials_module.load_global_config() is None
    assert CustomerManager.get_customer(alpha)["TenantId"] == "alpha"
