"""A Uniweb DNS zone is customer data, and must be scoped to who may see it.

GET /uniweb/dns/{domain} was authenticated (viewer) but not authorized: the
domain came straight from the path and the full zone came back. Uniweb's
clustered-zone API returns the MSP's own customers, and a domain is public and
guessable, so a technician scoped to customer A could read customer B's entire
zone — internal hostnames, mail routing, SPF/DKIM/service records — by passing
B's domain. It slipped past the scoping-coverage test because that test only
introspects routes spelled with {customer_id}/{host_id}, and this one is {domain}.

The route now resolves the domain to its owning customer (via the synced
uniweb_accounts cache) and, for a restricted caller, serves the zone only if the
caller may access that customer. A domain the caller may not see returns the
same empty zone as a domain Uniweb does not host — so the response cannot be
used to read another customer's records or to enumerate which domains exist.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import get_db, run_migrations
from app.core.rbac import grant_access, set_all_customers
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


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
def _patch_uniweb(monkeypatch):
    # Credentials present, so the route does not short-circuit to an empty zone.
    monkeypatch.setattr(
        "app.web.routes.uniweb._get_uniweb_config",
        lambda: {"email": "partner@sybr.no", "password": "pw"},
    )

    # The Partner API is not reached in tests; any allowed call yields one record.
    async def _fake_partner_call(fn):
        return [{"hostname": "@", "type": "A", "value": "1.2.3.4", "ttl": 3600}]

    monkeypatch.setattr("app.web.routes.uniweb._partner_call", _fake_partner_call)
    # Keep the projection out of the assertion — identity is enough here.
    monkeypatch.setattr("app.services.uniweb_partner.dns_record_view", lambda r: r)


async def _seed_accounts():
    """Two synced accounts: acme owns acme.no, beta owns beta.no."""
    async with get_db() as db:
        for acct, cid, dom in (("uwA", "acme", "acme.no"), ("uwB", "beta", "beta.no")):
            await db.execute(
                "INSERT INTO uniweb_accounts (id, name, customer_id, last_sync, data_json) "
                "VALUES (?, ?, ?, '2026-01-01T00:00:00Z', ?)",
                (acct, cid.title(), cid, json.dumps({"domains": [{"domain": dom}]})),
            )
        await db.commit()


async def _user(username, role=Role.technician, customers=(), all_customers=False):
    u = await create_user(username, GOOD_PASSWORD, username.title(), role=role)
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


def _records(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["records"]


# ── The domain is not authorization ──────────────────────────────────────────


async def test_a_restricted_user_cannot_read_another_customers_zone(client):
    await _seed_accounts()
    token = await _user("tech", customers=("acme",))
    # beta.no belongs to customer beta — the caller may not see it.
    assert _records(client.get("/api/uniweb/dns/beta.no", headers=_h(token))) == []


async def test_a_restricted_user_can_read_their_own_zone(client):
    await _seed_accounts()
    token = await _user("tech", customers=("acme",))
    assert len(_records(client.get("/api/uniweb/dns/acme.no", headers=_h(token)))) == 1


async def test_an_unknown_domain_is_empty_for_a_restricted_user(client):
    # Not in the synced cache -> ownership cannot be confirmed -> empty, so a
    # guessable domain nobody has synced still cannot be read on trust.
    await _seed_accounts()
    token = await _user("tech", customers=("acme",))
    assert _records(client.get("/api/uniweb/dns/unknown.example", headers=_h(token))) == []


async def test_a_user_with_no_customers_sees_no_zone(client):
    await _seed_accounts()
    token = await _user("nobody", customers=())
    assert _records(client.get("/api/uniweb/dns/acme.no", headers=_h(token))) == []


# ── The unrestricted caller still sees everything ────────────────────────────


async def test_an_admin_reads_any_zone(client):
    await _seed_accounts()
    token = await _user("boss", role=Role.admin)
    assert len(_records(client.get("/api/uniweb/dns/beta.no", headers=_h(token)))) == 1


async def test_the_all_customers_grant_is_unrestricted(client):
    await _seed_accounts()
    token = await _user("wide", customers=(), all_customers=True)
    assert len(_records(client.get("/api/uniweb/dns/beta.no", headers=_h(token)))) == 1


async def test_an_admin_reads_a_domain_not_in_the_cache(client):
    # Unrestricted callers are not gated on the cache at all.
    token = await _user("boss", role=Role.admin)
    assert len(_records(client.get("/api/uniweb/dns/whatever.example", headers=_h(token)))) == 1
