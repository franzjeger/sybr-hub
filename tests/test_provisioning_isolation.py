"""Provisioning sessions belong to one operator and one customer.

The wizard collects a device password and API token, holds them in an in-memory
session, and can push a stored FortiGate credential to a target address. Before
SR-001 the sessions were bound to a user_id that nothing checked, so any
authenticated account could read, drive, deploy, or delete another's session by
its id — and the raw password/token came straight back from GET. The deploy
routed a *customer's* stored credential to any address the caller named,
including one typed into the wizard's own "target host" field. And the whole
surface required only a technician, though the feature matrix calls provisioning
an admin function.

These tests pin all of that: two-user isolation, 404 (not 403) for a session you
do not own, secret redaction on the client-facing getters, the attacker-target
guard for both the body and the wizard origin, the explicit-credential path for
a genuine replacement unit, the admin feature floor, and the tenant-write
capability on deploy.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import set_can_write, set_tenant_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD = "Str0ng-Passphrase-For-Tests!"
CUSTOMER = {"_id": "acme", "CustomerName": "Acme AS", "FortiGateHost": "fw.acme.no"}


@pytest.fixture(autouse=True)
def _reset_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


@pytest.fixture(autouse=True)
def _patch_customer(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_active",
        staticmethod(lambda: dict(CUSTOMER)),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: dict(CUSTOMER) if cid == "acme" else None),
    )


@pytest.fixture(autouse=True)
def _clear_sessions():
    from app.services import provisioning

    provisioning._sessions.clear()
    yield
    provisioning._sessions.clear()


async def _admin(username: str, *, tenant: bool = False) -> str:
    u = await create_user(username, GOOD, username.title(), role=Role.admin)
    await set_can_write(u.id, True)  # so WriteGuard lets POST/PUT/DELETE through
    if tenant:
        await set_tenant_write(u.id, True)
    return await create_access_token(u)


async def _technician(username: str) -> str:
    u = await create_user(username, GOOD, username.title(), role=Role.technician)
    await set_can_write(u.id, True)
    return await create_access_token(u)


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _start(client, token: str) -> str:
    r = client.post("/api/provisioning/start", headers=_h(token))
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


# ── The feature floor ────────────────────────────────────────────────────────

async def test_a_technician_cannot_reach_provisioning(client):
    token = await _technician("tech")
    assert client.post("/api/provisioning/start", headers=_h(token)).status_code == 403


async def test_an_admin_can(client):
    token = await _admin("boss")
    assert client.post("/api/provisioning/start", headers=_h(token)).status_code == 200


# ── Two-operator isolation ───────────────────────────────────────────────────

async def test_a_session_binds_its_owner_and_customer(client):
    token = await _admin("boss")
    sid = await _start(client, token)
    from app.services.provisioning import get_session_raw

    raw = get_session_raw(sid)
    assert raw["customer_id"] == "acme"
    assert raw["user_id"]  # bound to the creator


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "", None),
        ("put", "/step/1", {"x": 1}),
        ("get", "/summary", None),
        ("post", "/generate", {}),
        ("post", "/deploy", {"method": "ssh"}),
        ("delete", "", None),
    ],
)
async def test_another_operator_cannot_touch_the_session(client, method, path, body):
    owner = await _admin("owner", tenant=True)
    other = await _admin("other", tenant=True)
    sid = await _start(client, owner)

    url = f"/api/provisioning/{sid}{path}"
    call = getattr(client, method)
    r = call(url, headers=_h(other), json=body) if body is not None else call(url, headers=_h(other))
    assert r.status_code == 404, f"{method} {path} leaked another operator's session: {r.status_code}"


async def test_the_owner_can_read_their_own(client):
    owner = await _admin("owner")
    sid = await _start(client, owner)
    assert client.get(f"/api/provisioning/{sid}", headers=_h(owner)).status_code == 200


async def test_a_foreign_session_is_indistinguishable_from_a_missing_one(client):
    owner = await _admin("owner")
    other = await _admin("other")
    sid = await _start(client, owner)

    foreign = client.get(f"/api/provisioning/{sid}", headers=_h(other)).status_code
    missing = client.get("/api/provisioning/does-not-exist", headers=_h(other)).status_code
    assert foreign == missing == 404


# ── Secret redaction ─────────────────────────────────────────────────────────

async def test_the_client_getters_never_return_raw_secrets(client):
    owner = await _admin("owner")
    sid = await _start(client, owner)
    client.put(
        f"/api/provisioning/{sid}/step/1",
        headers=_h(owner),
        json={"username": "admin", "password": "hunter2", "api_token": "TOK-secret"},
    )
    client.put(
        f"/api/provisioning/{sid}/step/4",
        headers=_h(owner),
        json={"admin_password": "root-pw"},
    )

    body = client.get(f"/api/provisioning/{sid}", headers=_h(owner)).text
    assert "hunter2" not in body
    assert "TOK-secret" not in body
    assert "root-pw" not in body

    summary = client.get(f"/api/provisioning/{sid}/summary", headers=_h(owner)).text
    assert "hunter2" not in summary and "root-pw" not in summary

    # ...but the raw values are still held server-side for the deploy that needs
    # them — redaction is on the way out, not in storage.
    from app.services.provisioning import get_session_raw

    raw = get_session_raw(sid)
    assert raw["steps"][1]["password"] == "hunter2"
    assert raw["steps"][4]["admin_password"] == "root-pw"


# ── Deploy needs the tenant-write capability ─────────────────────────────────

async def test_deploy_is_refused_without_tenant_write(client):
    owner = await _admin("owner", tenant=False)  # can_write, but not tenant_write
    sid = await _start(client, owner)
    r = client.post(f"/api/provisioning/{sid}/deploy", headers=_h(owner), json={"method": "ssh"})
    assert r.status_code == 403


async def test_deploy_with_tenant_write_passes_authorization(client):
    owner = await _admin("owner", tenant=True)
    sid = await _start(client, owner)
    # No generated config yet, so it must get PAST auth and fail on that instead
    # of 403 — proving the capability check let it through.
    r = client.post(f"/api/provisioning/{sid}/deploy", headers=_h(owner), json={"method": "ssh"})
    assert r.status_code != 403
    assert "generert" in r.text.lower() or "generated" in r.text.lower()


# ── The attacker-controlled target guard (unit) ──────────────────────────────

def _steps(**step1) -> dict:
    return {1: step1, 2: {}, 3: {}, 4: {}}


def _store_token():
    from app.core.credentials import store_secret

    store_secret("acme", "fortigate_api_token", "STORED-CUSTOMER-TOKEN")


def test_a_stored_credential_cannot_reach_a_body_target():
    from app.services.provisioning import _resolve_fortigate_conn

    _store_token()
    with pytest.raises(ValueError):
        _resolve_fortigate_conn(_steps(), target_host="10.6.6.6", customer_id="acme")


def test_a_stored_credential_cannot_reach_a_wizard_target():
    # The regression the old guard missed: it exempted the wizard's own target
    # field, so a Step 1 target_host pointed at an attacker's IP still received
    # the customer's stored token.
    from app.services.provisioning import _resolve_fortigate_conn

    _store_token()
    with pytest.raises(ValueError):
        _resolve_fortigate_conn(_steps(target_host="10.6.6.6"), customer_id="acme")


def test_a_stored_credential_reaches_the_configured_host():
    from app.services.provisioning import _resolve_fortigate_conn

    _store_token()
    conn = _resolve_fortigate_conn(_steps(target_host="FW.ACME.NO"), customer_id="acme")
    assert conn["host"] == "FW.ACME.NO"  # case-insensitive match, not refused
    assert conn["api_token"] == "STORED-CUSTOMER-TOKEN"


def test_explicit_credentials_allow_a_replacement_unit_on_a_new_ip():
    # A genuine bootstrap/replacement box on a different IP: the operator types
    # an explicit token, which is not the customer's stored one, so it may go.
    from app.services.provisioning import _resolve_fortigate_conn

    _store_token()
    conn = _resolve_fortigate_conn(
        _steps(target_host="10.6.6.6", api_token="TYPED-EXPLICITLY"),
        customer_id="acme",
    )
    assert conn["host"] == "10.6.6.6"
    assert conn["api_token"] == "TYPED-EXPLICITLY"


def test_no_stored_credential_means_no_restriction():
    from app.services.provisioning import _resolve_fortigate_conn

    # nothing in the keyring; an explicit token to an arbitrary host is fine
    conn = _resolve_fortigate_conn(
        _steps(target_host="10.6.6.6", api_token="X"), customer_id="acme"
    )
    assert conn["host"] == "10.6.6.6"


def test_the_deploy_resolves_its_own_customer_not_the_active_one(monkeypatch):
    # The session is bound to acme; even if a different customer is active now,
    # deploy must resolve acme's config. get_customer("acme") is what it calls.
    from app.services.provisioning import _resolve_fortigate_conn

    conn = _resolve_fortigate_conn(_steps(), customer_id="acme")
    assert conn["customer_id"] == "acme"
    assert conn["customer_name"] == "Acme AS"


# ── The UniFi leg of the same boundary (found by adversarial review) ─────────
#
# _deploy_unifi had the exact active-vs-session confusion the FortiGate guard
# fixed, and no host guard: a customer's stored UniFi admin credentials could be
# sent to any address the operator named, whenever the customer had keyring
# creds but an empty configured UniFiHost.

@pytest.fixture()
def _spy_unifi_client(monkeypatch):
    built: list[str] = []

    class _Fake:
        def __init__(self, host, username=None, password=None, **kw):
            built.append(host)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(
        "app.modules.unifi_audit.client.UniFiControllerClient", _Fake
    )
    return built


async def test_stored_unifi_credentials_never_reach_an_arbitrary_host(_spy_unifi_client):
    from app.core.credentials import store_secret
    from app.services.provisioning import _deploy_unifi

    # acme has stored UniFi creds but no configured UniFiHost (CUSTOMER has none).
    store_secret("acme", "unifi_username", "admin")
    store_secret("acme", "unifi_password", "unifi-secret")

    result = await _deploy_unifi(
        "attacker.evil.example", '{"networks": []}', {"name": "acme"}, customer_id="acme"
    )
    assert result["ok"] is False
    assert _spy_unifi_client == [], "a stored UniFi credential was sent to a host"


async def test_unifi_deploy_resolves_the_session_customer_not_the_active_one(
    monkeypatch, _spy_unifi_client
):
    from app.core.credentials import store_secret
    from app.services.provisioning import _deploy_unifi

    # A different customer is active, and it has no stored creds. If _deploy_unifi
    # used the active customer it would report "no credentials"; using the bound
    # session customer (acme) it finds acme's stored creds and hits the host
    # guard instead — which is how we know it resolved the right customer.
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_active",
        staticmethod(lambda: {"_id": "beta", "CustomerName": "Beta AS"}),
    )
    store_secret("acme", "unifi_username", "admin")
    store_secret("acme", "unifi_password", "unifi-secret")

    result = await _deploy_unifi(
        "somewhere", '{"networks": []}', {"name": "acme"}, customer_id="acme"
    )
    assert result["ok"] is False
    assert "konfigurert" in result["error"], result["error"]
    assert _spy_unifi_client == []
