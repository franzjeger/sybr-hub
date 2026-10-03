"""Uniweb account data and bindings are scoped to the caller's customers.

The account list, the full account record (domains, mail, hosting), the
match overview and the expiry alerts went to any signed-in user. And a
technician could relink any Uniweb account to any customer: the binding is
what /uniweb/dns checks, so relinking another customer's account to one of
your own handed you that customer's zones. Unbound accounts are MSP-wide —
technicians see them by id and name so they can bind them, nothing more.
"""

from __future__ import annotations

import json

import pytest
from sqlmodel import select

from app.core.orm import get_session
from app.models.integrations import UniwebAccount
from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)


def _data(domain: str) -> str:
    return json.dumps(
        {
            "parent_name": "Sybr Partner",
            "domains": [{"domain": domain}],
            "email": [{"domain": domain, "username": f"post@{domain}"}],
            "hosting": [{"domain": domain}],
        }
    )


@pytest.fixture(autouse=True)
async def _seed():
    async with get_session() as s:
        s.add(
            UniwebAccount(
                id="uw-acme", name="Acme Web", customer_id=ACME, data_json=_data("acme.no")
            )
        )
        s.add(
            UniwebAccount(
                id="uw-beta", name="Beta Web", customer_id=BETA, data_json=_data("beta.no")
            )
        )
        s.add(
            UniwebAccount(
                id="uw-orphan", name="Orphan Web", customer_id=None, data_json=_data("orphan.no")
            )
        )
        await s.commit()
    yield


@pytest.fixture(autouse=True)
def _uniweb_offline(monkeypatch):
    monkeypatch.setattr(
        "app.web.routes.uniweb._get_uniweb_config",
        lambda: {"email": "partner@example.test", "password": "pw"},
    )

    # Live subscriptions, one expiring per account (the Partner API calls the
    # Uniweb account a subscription's "customer").
    async def _partner_call(fn):
        return [
            {
                "customer": acct,
                "username": f"{acct}.no",
                "product": {"code": "dns", "text": "Domain"},
                "period": {"to": "2026-10-20"},
            }
            for acct in ("uw-acme", "uw-beta", "uw-orphan")
        ]

    monkeypatch.setattr("app.web.routes.uniweb._partner_call", _partner_call)


async def _binding(account_id: str) -> str | None:
    async with get_session() as s:
        result = await s.execute(
            select(UniwebAccount.customer_id).where(UniwebAccount.id == account_id)
        )
        return result.scalar_one()


async def _viewer():
    return await login("viewer-acme", role=Role.viewer, customers=(ACME,), write=False)


async def _tech():
    return await login("tech-acme", role=Role.technician, customers=(ACME,))


# ── Reads ────────────────────────────────────────────────────────────────────


async def test_accounts_list_only_the_callers_accounts(client):
    r = client.get("/api/uniweb/accounts", headers=await _viewer())
    assert r.status_code == 200, r.text
    assert {a["id"] for a in r.json()["accounts"]} == {"uw-acme"}
    assert_no_foreign(r.text)


async def test_accounts_list_everything_for_an_admin(client):
    headers = await login("boss", role=Role.admin)
    accounts = client.get("/api/uniweb/accounts", headers=headers).json()["accounts"]
    assert {a["id"] for a in accounts} == {"uw-acme", "uw-beta", "uw-orphan"}


async def test_account_detail_is_404_outside_the_callers_customers(client):
    headers = await _viewer()
    assert client.get("/api/uniweb/account/uw-beta", headers=headers).status_code == 404
    assert client.get("/api/uniweb/account/uw-orphan", headers=headers).status_code == 404
    # Same answer as an id that does not exist, so ids cannot be enumerated.
    assert client.get("/api/uniweb/account/uw-nope", headers=headers).status_code == 404
    own = client.get("/api/uniweb/account/uw-acme", headers=headers)
    assert own.status_code == 200
    assert own.json()["domains"] == [{"domain": "acme.no"}]


async def test_matches_for_a_viewer_hold_only_their_bound_accounts(client):
    r = client.get("/api/uniweb/matches", headers=await _viewer())
    body = r.json()
    assert [m["uniweb_id"] for m in body["matched"]] == ["uw-acme"]
    assert body["unmatched"] == []
    assert [c["id"] for c in body["available_customers"]] == [ACME]
    assert_no_foreign(r.text)


async def test_matches_offer_unbound_accounts_to_a_technician_by_name_only(client):
    r = client.get("/api/uniweb/matches", headers=await _tech())
    body = r.json()
    assert [m["uniweb_id"] for m in body["matched"]] == ["uw-acme"]
    assert body["unmatched"] == [
        {
            "uniweb_id": "uw-orphan",
            "uniweb_name": "Orphan Web",
            "customer_id": None,
            "customer_name": None,
            "parent_name": "",
        }
    ]
    assert_no_foreign(r.text)


async def test_matches_for_an_admin_cover_every_account(client):
    body = client.get("/api/uniweb/matches", headers=await login("boss", role=Role.admin)).json()
    assert {m["uniweb_id"] for m in body["matched"]} == {"uw-acme", "uw-beta"}
    assert [m["uniweb_id"] for m in body["unmatched"]] == ["uw-orphan"]


async def test_alerts_only_carry_the_callers_services(client):
    r = client.get("/api/uniweb/alerts", headers=await _viewer())
    assert r.status_code == 200, r.text
    assert {i["customer_id"] for i in r.json()["items"]} == {ACME}
    assert_no_foreign(r.text)


async def test_alerts_for_an_admin_include_unbound_services(client):
    items = client.get("/api/uniweb/alerts", headers=await login("boss", role=Role.admin)).json()
    assert {i["customer_id"] for i in items["items"]} == {ACME, BETA, ""}


async def test_status_does_not_name_the_account_being_synced_to_a_scoped_caller(
    client, monkeypatch
):
    from app.services import uniweb_sync

    monkeypatch.setitem(uniweb_sync._sync_status, "current_account", "Beta AS")
    assert client.get("/api/uniweb/status", headers=await _viewer()).json()["current_account"] == ""
    admin = await login("boss", role=Role.admin)
    assert client.get("/api/uniweb/status", headers=admin).json()["current_account"] == "Beta AS"


# ── Bindings ─────────────────────────────────────────────────────────────────


async def test_a_scoped_technician_cannot_link_an_account_to_a_foreign_customer(client):
    r = client.post(
        "/api/uniweb/match",
        headers=await _tech(),
        json={"uniweb_account_id": "uw-acme", "customer_id": BETA},
    )
    assert r.status_code == 403
    assert await _binding("uw-acme") == ACME


async def test_a_scoped_technician_cannot_take_over_a_foreign_account(client):
    # The attack: rebind beta's account to acme, then read beta's zones.
    headers = await _tech()
    r = client.post(
        "/api/uniweb/match",
        headers=headers,
        json={"uniweb_account_id": "uw-beta", "customer_id": ACME},
    )
    assert r.status_code == 404
    assert await _binding("uw-beta") == BETA
    r = client.post(
        "/api/uniweb/match",
        headers=headers,
        json={"uniweb_account_id": "uw-beta", "customer_id": ""},
    )
    assert r.status_code == 404
    assert await _binding("uw-beta") == BETA


async def test_a_scoped_technician_can_bind_an_unbound_account_to_their_customer(client):
    headers = await _tech()
    r = client.post(
        "/api/uniweb/match",
        headers=headers,
        json={"uniweb_account_id": "uw-orphan", "customer_id": ACME},
    )
    assert r.status_code == 200, r.text
    assert await _binding("uw-orphan") == ACME
    r = client.post(
        "/api/uniweb/match",
        headers=headers,
        json={"uniweb_account_id": "uw-orphan", "customer_id": ""},
    )
    assert r.status_code == 200, r.text
    assert await _binding("uw-orphan") is None


async def test_an_admin_can_rebind_any_account(client):
    r = client.post(
        "/api/uniweb/match",
        headers=await login("boss", role=Role.admin),
        json={"uniweb_account_id": "uw-beta", "customer_id": ACME},
    )
    assert r.status_code == 200, r.text
    assert await _binding("uw-beta") == ACME


async def test_import_does_not_link_to_a_foreign_customer_by_name(client):
    async with get_session() as s:
        s.add(UniwebAccount(id="uw-named", name="Beta AS", customer_id=None))
        await s.commit()
    r = client.post(
        "/api/uniweb/import-customers", headers=await _tech(), json={"account_ids": ["uw-named"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 0
    assert await _binding("uw-named") is None
