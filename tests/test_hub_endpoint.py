"""The Hub aggregate: four sources, each saying which of them it is.

This route returned a fixed shape of nulls and described itself as the
front-end's single source of truth. A customer with no Autotask, a customer
whose Autotask call failed, and a customer whose record is genuinely empty
all looked the same on the page, so the front end guessed — and "Cannot read
properties of null (reading 'toFixed')" is what guessing wrong looked like.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"
CUSTOMER = {"CustomerName": "Acme AS", "TenantId": "t-1", "ClientId": "c-1"}


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


@pytest.fixture()
def customer(tmp_path, monkeypatch):
    """A customer on disk, with CustomerManager pointed at it."""
    import app.core.customer as cm

    root = tmp_path / "customers"
    root.mkdir()
    monkeypatch.setattr(cm, "_CUSTOMERS_DIR", root)
    cid = cm.CustomerManager.save_customer(dict(CUSTOMER))
    return cid


@pytest.fixture()
async def auth():
    user = await create_user("hubop", GOOD_PASSWORD, "Hub Op", role=Role.admin)
    from app.core.rbac import set_can_write

    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _no_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {})


def test_an_unconfigured_integration_says_so(client, auth, customer, monkeypatch):
    _no_settings(monkeypatch)
    body = client.get(f"/api/hub/{customer}", headers=auth).json()

    assert body["autotask"]["status"] == "not_configured"
    assert body["itglue"]["status"] == "not_configured"
    assert body["rmm"]["status"] == "not_implemented"
    assert body["audit"]["status"] == "never_run"


def test_configured_but_unlinked_is_a_different_answer(client, auth, customer, monkeypatch):
    """The distinction that decides whether a technician goes looking."""
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {
        "autotask_integration_code": "code",
        "autotask_username": "u", "autotask_secret": "s",
        "itglue_api_key": "k",
    })
    body = client.get(f"/api/hub/{customer}", headers=auth).json()

    assert body["autotask"]["status"] == "not_linked"
    assert body["itglue"]["status"] == "not_linked"


def test_a_failed_read_is_unavailable_with_a_reason(client, auth, customer, monkeypatch):
    """Not an empty classification. That was the whole bug."""
    import app.core.customer as cm
    from app.integrations.autotask import AutotaskError

    record = cm.CustomerManager.get_customer(customer)
    record["AutotaskAccountId"] = 99
    cm.CustomerManager.save_customer({k: v for k, v in record.items() if not k.startswith("_")})

    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {
        "autotask_integration_code": "code",
        "autotask_username": "u", "autotask_secret": "s",
    })

    async def _boom(self, account_id):
        raise AutotaskError("Autotask refused the credentials (401).")

    monkeypatch.setattr("app.integrations.autotask.AutotaskClient.get_account", _boom)

    block = client.get(f"/api/hub/{customer}", headers=auth).json()["autotask"]
    assert block["status"] == "unavailable"
    assert "401" in block["reason"]
    assert "classification" not in block, "a failed read must not report a value"


def test_a_stale_link_is_named_as_stale(client, auth, customer, monkeypatch):
    """The id is bound but Autotask has no such company."""
    import app.core.customer as cm

    record = cm.CustomerManager.get_customer(customer)
    record["AutotaskAccountId"] = 4242
    cm.CustomerManager.save_customer({k: v for k, v in record.items() if not k.startswith("_")})

    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {
        "autotask_integration_code": "code",
        "autotask_username": "u", "autotask_secret": "s",
    })

    async def _none(self, account_id):
        return None

    monkeypatch.setattr("app.integrations.autotask.AutotaskClient.get_account", _none)

    block = client.get(f"/api/hub/{customer}", headers=auth).json()["autotask"]
    assert block["status"] == "unavailable"
    assert "4242" in block["reason"] and "stale" in block["reason"]


def test_an_unmeasured_metric_stays_null(client, auth, customer, monkeypatch):
    """0 and "not measured" are different facts, and a tile cannot tell them
    apart once one has been turned into the other."""
    import sqlite3

    import app.core.database as db_mod

    _no_settings(monkeypatch)

    # Written with sqlite3 rather than the pool: the pool keys connections on
    # the running loop, and this test drives the app through a sync client.
    con = sqlite3.connect(str(db_mod.DB_PATH))
    con.execute(
        "INSERT INTO audit_metrics (customer_id, customer_name, audit_date, "
        "risk_grade, risk_score, mfa_coverage_pct, intune_compliance_pct, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (customer, "Acme AS", "2026-08-05T18:00:00Z", "B", 64, 99.5, None,
         "2026-08-05T18:00:00Z"),
    )
    con.commit()
    con.close()

    audit = client.get(f"/api/hub/{customer}", headers=auth).json()["audit"]
    assert audit["status"] == "ok"
    assert audit["mfa_coverage_pct"] == 99.5
    assert audit["intune_compliance_pct"] is None, "an unmeasured metric became a number"


def test_linking_binds_and_unlinking_clears(client, auth, customer, monkeypatch):
    _no_settings(monkeypatch)

    r = client.post(f"/api/hub/{customer}/link", headers=auth,
                    json={"autotask_account_id": 77, "itglue_org_id": "org-9"})
    assert r.status_code == 200, r.text

    import app.core.customer as cm
    record = cm.CustomerManager.get_customer(customer)
    assert record["AutotaskAccountId"] == 77
    assert record["ITGlueOrgId"] == "org-9"

    client.post(f"/api/hub/{customer}/link", headers=auth,
                json={"autotask_account_id": None})
    assert "AutotaskAccountId" not in cm.CustomerManager.get_customer(customer)


def test_linking_rejects_a_non_numeric_account_id(client, auth, customer, monkeypatch):
    _no_settings(monkeypatch)
    r = client.post(f"/api/hub/{customer}/link", headers=auth,
                    json={"autotask_account_id": "not-a-number"})
    assert r.status_code == 400, r.text


def test_an_unknown_customer_is_a_404(client, auth, customer, monkeypatch):
    _no_settings(monkeypatch)
    assert client.get("/api/hub/Nope_AS", headers=auth).status_code == 404
