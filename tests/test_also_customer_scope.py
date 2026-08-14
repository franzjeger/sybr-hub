"""ALSO data is customer data, and must be scoped to who may see the customer.

Every ALSO route was authenticated but not authorized: any logged-in account
could read a company, subscription, renewal, invoice, or license-optimization
row for *any* customer by supplying the identifier, and the aggregate views
returned the whole provider estate. A renewal could be mutated by database id
with no customer check. This is textbook IDOR in a multi-tenant tool.

The fix scopes every ALSO read and write to the caller's accessible customers
(`get_accessible_customer_ids`, where None means unrestricted). An ALSO account
maps to a Sybr customer by `AlsoAccountId`; a renewal and a subscription-detail
row carry `customer_id`. A restricted caller reaching another customer's id
gets 404, not 403 — so the error cannot be used to enumerate which accounts
exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import get_db, run_migrations
from app.core.rbac import grant_access, set_all_customers, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"

# Two customers, each linked to an ALSO account. Customer A is "acme"
# (account 1001); customer B is "beta" (account 2002).
CUSTOMERS = [
    {"_id": "acme", "CustomerName": "Acme AS", "AlsoAccountId": "1001"},
    {"_id": "beta", "CustomerName": "Beta AS", "AlsoAccountId": "2002"},
]


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


class _FakeAlso:
    """Enough of the ALSO client for the routes under test."""

    async def get_companies(self):
        return [
            {"AccountId": "1001", "CompanyName": "Acme AS"},
            {"AccountId": "2002", "CompanyName": "Beta AS"},
        ]

    async def get_company(self, account_id):
        return {"AccountId": account_id, "name": f"company-{account_id}"}

    async def get_subscriptions(self, account_id):
        return [{"AccountId": f"sub-{account_id}", "ServiceName": "M365"}]

    async def get_subscription_with_addons(self, sub_id):
        return {"Fields": [], "PriceableItems": []}

    async def get_subscription(self, sub_id):
        return {"id": sub_id}

    async def get_preview_invoices(self):
        return [{"invoice": 1}, {"invoice": 2}]


@pytest.fixture(autouse=True)
def _patch_also(monkeypatch):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS]),
    )

    async def _client():
        return _FakeAlso()

    monkeypatch.setattr("app.web.routes.also._get_client", _client)
    # get_subscription_detail fires a background cache write; make it a no-op so
    # the test does not depend on task scheduling.
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr("app.web.routes.also._cache_subscription_pricing", _noop)
    monkeypatch.setattr("app.web.routes.also._cache_renewals", _noop)
    monkeypatch.setattr("app.web.routes.also._auto_cache_uncached_pricing", _noop)


async def _seed_renewals() -> dict[str, int]:
    """One active Microsoft renewal per customer. Returns {customer_id: row id}.

    The contract_end is in the past so the row is "expired", which
    get_renewals always includes in its returned list — a far-future date would
    land in the "beyond N days" bucket and never appear, making the scope
    assertion vacuous.
    """
    ids: dict[str, int] = {}
    async with get_db() as db:
        for cid, cname, sub in (("acme", "Acme AS", "subA"), ("beta", "Beta AS", "subB")):
            await db.execute(
                """INSERT INTO also_renewals
                   (customer_id, customer_name, subscription_id, service_name,
                    service_display, vendor, contract_end, account_state, scanned_at)
                   VALUES (?, ?, ?, ?, ?, 'Microsoft', '2020-01-01T00:00:00Z',
                           'Active', '2026-01-01T00:00:00Z')""",
                (cid, cname, sub, "M365", "Microsoft 365 Business Premium"),
            )
        await db.commit()
        async with db.execute("SELECT id, customer_id FROM also_renewals") as cur:
            for row in await cur.fetchall():
                ids[row["customer_id"]] = row["id"]
    return ids


async def _user(username, role=Role.technician, customers=(), write=False, all_customers=False):
    u = await create_user(username, GOOD_PASSWORD, username.title(), role=role)
    if write:
        await set_can_write(u.id, True)
    if all_customers:
        await set_all_customers(u.id, True)
    for cid in customers:
        await grant_access(u.id, cid)
    return await create_access_token(u)


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Direct-object reads: the identifier is not authorization ─────────────────

async def test_a_restricted_user_cannot_read_another_customers_company(client):
    token = await _user("tech", customers=("acme",))
    assert client.get("/api/also/company/2002", headers=_h(token)).status_code == 404


async def test_a_restricted_user_can_read_their_own_company(client):
    token = await _user("tech", customers=("acme",))
    r = client.get("/api/also/company/1001", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["company"]["AccountId"] == "1001"


async def test_the_denied_company_is_404_not_403(client):
    # 403 vs 404 would tell a restricted caller which account ids are real.
    token = await _user("tech", customers=("acme",))
    assert client.get("/api/also/company/2002", headers=_h(token)).status_code == 404
    assert client.get("/api/also/company/9999", headers=_h(token)).status_code == 404


async def test_a_restricted_user_cannot_list_another_customers_subscriptions(client):
    token = await _user("tech", customers=("acme",))
    assert client.get("/api/also/subscriptions/2002", headers=_h(token)).status_code == 404
    assert client.get("/api/also/subscriptions/1001", headers=_h(token)).status_code == 200


async def test_a_restricted_user_cannot_read_a_foreign_subscription_detail(client):
    await _seed_renewals()
    token = await _user("tech", customers=("acme",))
    # subB belongs to beta; resolved via also_renewals.subscription_id.
    assert client.get("/api/also/subscription/subB", headers=_h(token)).status_code == 404


# ── Aggregate reads: filtered to the accessible set ──────────────────────────

async def test_renewals_are_filtered_to_the_users_customers(client):
    await _seed_renewals()
    token = await _user("tech", customers=("acme",))
    body = client.get("/api/also/renewals", headers=_h(token)).json()
    names = {r["customer_name"] for r in body["renewals"]}
    assert names == {"Acme AS"}, f"leaked another customer's renewals: {names}"
    assert body["total"] == 1


async def test_license_optimization_is_filtered(client):
    await _seed_renewals()
    token = await _user("tech", customers=("acme",))
    body = client.get("/api/also/license-optimization", headers=_h(token)).json()
    ids = {c["customer_id"] for c in body["customers"]}
    assert ids <= {"acme"}, f"leaked another customer: {ids}"


async def test_companies_are_filtered(client):
    token = await _user("tech", customers=("acme",))
    body = client.get("/api/also/companies", headers=_h(token)).json()
    accounts = {c["AccountId"] for c in body["companies"]}
    assert accounts == {"1001"}


# ── Mutation by object id ────────────────────────────────────────────────────

async def test_a_restricted_user_cannot_handle_a_foreign_renewal(client):
    ids = await _seed_renewals()
    token = await _user("tech", customers=("acme",), write=True)
    r = client.post(f"/api/also/renewals/{ids['beta']}/handle",
                    headers=_h(token), json={"handled": 1, "notes": "x"})
    assert r.status_code == 404
    # and the row is untouched
    async with get_db() as db, db.execute(
        "SELECT handled FROM also_renewals WHERE id = ?", (ids["beta"],)
    ) as cur:
        assert (await cur.fetchone())["handled"] == 0


async def test_a_restricted_user_can_handle_their_own_renewal(client):
    ids = await _seed_renewals()
    token = await _user("tech", customers=("acme",), write=True)
    r = client.post(f"/api/also/renewals/{ids['acme']}/handle",
                    headers=_h(token), json={"handled": 1, "notes": "done"})
    assert r.status_code == 200, r.text
    async with get_db() as db, db.execute(
        "SELECT handled, notes FROM also_renewals WHERE id = ?", (ids["acme"],)
    ) as cur:
        row = await cur.fetchone()
        assert row["handled"] == 1 and row["notes"] == "done"


async def test_handling_a_nonexistent_renewal_is_404(client):
    token = await _user("tech", customers=("acme",), write=True)
    r = client.post("/api/also/renewals/99999/handle", headers=_h(token), json={"handled": 1})
    assert r.status_code == 404


# ── Provider-wide invoices are admin-only ────────────────────────────────────

async def test_invoices_are_denied_to_a_non_admin(client):
    token = await _user("tech", customers=("acme",))
    assert client.get("/api/also/invoices", headers=_h(token)).status_code == 403


async def test_invoices_are_allowed_for_an_admin(client):
    token = await _user("boss", role=Role.admin)
    r = client.get("/api/also/invoices", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2


# ── The unrestricted user still sees everything ──────────────────────────────

async def test_an_admin_reads_any_company(client):
    token = await _user("boss", role=Role.admin)
    assert client.get("/api/also/company/2002", headers=_h(token)).status_code == 200


async def test_an_admin_sees_every_renewal(client):
    await _seed_renewals()
    token = await _user("boss", role=Role.admin)
    body = client.get("/api/also/renewals", headers=_h(token)).json()
    assert {r["customer_name"] for r in body["renewals"]} == {"Acme AS", "Beta AS"}


async def test_the_all_customers_grant_is_unrestricted_too(client):
    # A technician with the blanket grant behaves like an admin for scope.
    await _seed_renewals()
    token = await _user("wide", customers=(), all_customers=True)
    body = client.get("/api/also/renewals", headers=_h(token)).json()
    assert body["total"] == 2


# ── A user assigned no customers sees nothing ────────────────────────────────

async def test_a_user_with_no_customers_sees_no_renewals(client):
    await _seed_renewals()
    token = await _user("nobody", customers=())
    assert client.get("/api/also/renewals", headers=_h(token)).json()["total"] == 0


async def test_a_user_with_no_customers_is_denied_every_company(client):
    token = await _user("nobody", customers=())
    assert client.get("/api/also/company/1001", headers=_h(token)).status_code == 404
