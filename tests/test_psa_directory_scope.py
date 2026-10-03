"""PSA and documentation directories: listing for technicians, detail by binding.

Autotask companies, myITprocess accounts and IT Glue organizations are the
MSP's whole client list in another system. They are needed to bind a customer
to its record, so technicians may list them — by id and name when scoped to
some customers. Anything more (an Autotask company's contracts) is one
customer's business and is served only for a record bound to a customer the
caller holds, or to unrestricted callers. Viewers do not get the directories.
"""

from __future__ import annotations

import pytest

from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    CUSTOMERS,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)

# CUSTOMERS binds acme to Autotask company 101 / IT Glue org 501 and beta to
# 202 / 502.
COMPANIES = {
    101: {"id": 101, "companyName": "Acme AS", "classification": 1, "companyType": 1},
    202: {"id": 202, "companyName": "Beta AS", "classification": 2, "companyType": 1},
}


class _FakeAutotask:
    def __init__(self):
        self.asked: list[int] = []

    async def list_accounts(self, name_filter="", limit=50):
        return list(COMPANIES.values())

    async def get_account(self, account_id):
        self.asked.append(account_id)
        return COMPANIES.get(account_id)

    async def list_contracts_for_account(self, account_id):
        return [{"id": account_id * 10, "contractName": f"Contract {account_id}"}]

    async def close(self):
        return None


@pytest.fixture()
def autotask(monkeypatch) -> _FakeAutotask:
    fake = _FakeAutotask()
    monkeypatch.setattr("app.web.routes.autotask._client_from_settings", lambda request: fake)
    return fake


class _FakeMyITProcess:
    async def list_accounts(self, limit=200):
        return [{"id": "m1", "name": "Acme AS", "address": "Storgata 1"}]

    async def close(self):
        return None


class _FakeITGlue:
    def __init__(self, api_key="", region="eu"):
        pass

    async def list_organizations(self, name=""):
        return [
            {"id": "501", "attributes": {"name": "Acme AS", "short-name": "acme"}},
            {"id": "502", "attributes": {"name": "Beta AS", "short-name": "beta"}},
        ]

    async def inspect_all_types(self):
        return [{"id": 1, "name": "Network Inventory", "fields": []}]

    async def close(self):
        return None


@pytest.fixture()
def itglue(monkeypatch):
    synced: list[str] = []

    async def _sync(customer_id, client, request=None):
        synced.append(customer_id)
        return {
            "customer_id": customer_id,
            "customer_name": customer_id,
            "synced": [{"type": "license_summary", "mrr": 1.0}],
            "errors": [],
        }

    monkeypatch.setattr("app.web.routes.itglue.load_app_settings", lambda: {"itglue_api_key": "k"})
    monkeypatch.setattr("app.integrations.itglue.ITGlueClient", _FakeITGlue)
    monkeypatch.setattr("app.web.routes.itglue._sync_customer_documentation", _sync)
    return synced


async def _viewer():
    return await login("viewer-acme", role=Role.viewer, customers=(ACME,))


async def _tech():
    return await login("tech-acme", role=Role.technician, customers=(ACME,))


# ── Autotask ─────────────────────────────────────────────────────────────────


async def test_autotask_directory_is_refused_to_a_viewer(client, autotask):
    assert client.get("/api/autotask/accounts", headers=await _viewer()).status_code == 403


async def test_autotask_directory_gives_a_scoped_technician_id_and_name_only(client, autotask):
    r = client.get("/api/autotask/accounts", headers=await _tech())
    assert r.status_code == 200, r.text
    rows = r.json()["accounts"]
    assert {a["id"] for a in rows} == {101, 202}
    assert all(set(a) == {"id", "name"} for a in rows)


async def test_autotask_directory_keeps_its_full_shape_for_an_admin(client, autotask):
    rows = client.get(
        "/api/autotask/accounts", headers=await login("boss", role=Role.admin)
    ).json()["accounts"]
    assert all(set(a) == {"id", "name", "classification", "company_type"} for a in rows)


async def test_autotask_company_detail_is_404_unless_bound_to_the_callers_customer(
    client, autotask
):
    headers = await _viewer()
    r = client.get("/api/autotask/accounts/202", headers=headers)
    assert r.status_code == 404
    assert_no_foreign(r.text)
    # Refused before Autotask is asked, so the answer cannot tell real ids apart.
    assert autotask.asked == []
    assert client.get("/api/autotask/accounts/999", headers=headers).status_code == 404

    own = client.get("/api/autotask/accounts/101", headers=headers)
    assert own.status_code == 200, own.text
    assert own.json()["contracts"][0]["id"] == 1010


@pytest.mark.parametrize(
    "who", [{"role": Role.admin}, {"role": Role.technician, "all_customers": True}]
)
async def test_autotask_company_detail_is_open_to_unrestricted_callers(client, autotask, who):
    r = client.get("/api/autotask/accounts/202", headers=await login("wide", **who))
    assert r.status_code == 200, r.text
    assert r.json()["account"]["name"] == "Beta AS"


# ── myITprocess ──────────────────────────────────────────────────────────────


async def test_myitprocess_directory_is_technician_and_id_name_only(client, monkeypatch):
    monkeypatch.setattr(
        "app.web.routes.myitprocess._client_from_settings", lambda: _FakeMyITProcess()
    )
    assert client.get("/api/myitprocess/accounts", headers=await _viewer()).status_code == 403
    r = client.get("/api/myitprocess/accounts", headers=await _tech())
    assert r.status_code == 200, r.text
    assert r.json()["accounts"] == [{"id": "m1", "name": "Acme AS"}]


# ── IT Glue ──────────────────────────────────────────────────────────────────


async def test_itglue_directory_is_refused_to_a_viewer(client, itglue):
    headers = await _viewer()
    assert client.post("/api/itglue/organizations", headers=headers).status_code == 403
    assert client.get("/api/itglue/inspect", headers=headers).status_code == 403


async def test_itglue_directory_gives_a_technician_id_and_name(client, itglue):
    headers = await _tech()
    r = client.post("/api/itglue/organizations", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["organizations"] == [
        {"id": "501", "name": "Acme AS"},
        {"id": "502", "name": "Beta AS"},
    ]
    assert client.get("/api/itglue/inspect", headers=headers).status_code == 200


async def test_itglue_sync_all_only_syncs_and_reports_the_callers_customers(client, itglue):
    r = client.post("/api/itglue/sync-all", headers=await _tech())
    assert r.status_code == 200, r.text
    assert {x["customer_id"] for x in r.json()["results"]} == {ACME}
    assert itglue == [ACME]
    assert_no_foreign(r.text)


async def test_itglue_sync_all_covers_every_bound_customer_for_an_admin(client, itglue):
    r = client.post("/api/itglue/sync-all", headers=await login("boss", role=Role.admin))
    assert r.status_code == 200, r.text
    assert sorted(itglue) == sorted([ACME, BETA])


# ── IT Glue uploads go to the active customer's own organization ────────────


@pytest.fixture()
def acme_is_active(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_active", staticmethod(lambda: dict(CUSTOMERS[0]))
    )


@pytest.mark.parametrize("path", ["/api/itglue/upload/audit", "/api/itglue/upload/reports"])
async def test_a_scoped_technician_cannot_upload_into_a_foreign_org(
    client, itglue, acme_is_active, path
):
    # 502 is beta's organization; the upload would carry acme's audit into it.
    r = client.post(path, headers=await _tech(), json={"org_id": "502"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", ["/api/itglue/upload/audit", "/api/itglue/upload/reports"])
async def test_the_active_customers_own_org_passes_the_check(client, itglue, acme_is_active, path):
    # No audit run exists here, so the request fails later — just not on scope.
    r = client.post(path, headers=await _tech(), json={"org_id": "501"})
    assert r.status_code != 403


async def test_an_upload_with_no_audit_says_so_rather_than_blaming_it_glue(
    client, itglue, acme_is_active
):
    # The refusal is raised inside the upload's try block, where a bare
    # "except Exception" turned it into "IT Glue upload failed" and a 502.
    r = client.post("/api/itglue/upload/audit", headers=await _tech(), json={"org_id": "501"})
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "Ingen audit-data tilgjengelig"
    assert r.json()["error_key"] == "err_no_audit_data"


async def test_an_admin_may_upload_into_any_org(client, itglue, acme_is_active):
    r = client.post(
        "/api/itglue/upload/reports",
        headers=await login("boss", role=Role.admin),
        json={"org_id": "502"},
    )
    assert r.status_code != 403
