"""Shared setup for the customer-scope tests.

Two customers, a fresh database per test, and a helper that signs in a user of
any role with any set of customer grants. Test modules import the fixtures
they need; the autouse ones apply to every test in an importing module.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_all_customers, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Str0ng-Passphrase-For-Scope-Tests!"

# Distinctive ids and names, so a test can assert the foreign customer appears
# nowhere in a response body rather than only in the field it expected.
ACME = "cust-acme"
BETA = "cust-beta"
CUSTOMERS = [
    {
        "_id": ACME,
        "CustomerName": "Acme AS",
        "PrimaryDomain": "acme.example",
        "AutotaskAccountId": 101,
        "ITGlueOrgId": "501",
    },
    {
        "_id": BETA,
        "CustomerName": "Beta AS",
        "PrimaryDomain": "beta.example",
        "AutotaskAccountId": 202,
        "ITGlueOrgId": "502",
    },
]


def _customer(cid: str) -> dict | None:
    return next((dict(c) for c in CUSTOMERS if c["_id"] == cid), None)


@pytest.fixture(autouse=True)
def _reset_middleware_state():
    import app.web.middleware.rate_limit as rl

    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()
    yield
    _reset_users_exist_cache()
    rl._hits.clear()
    rl._sensitive_hits.clear()


@pytest.fixture(autouse=True)
async def _scope_env(tmp_path, monkeypatch):
    import app.core.database as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS]),
    )
    monkeypatch.setattr("app.core.customer.CustomerManager.get_customer", staticmethod(_customer))
    await run_migrations()
    yield


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


async def login(
    username: str,
    *,
    role: Role = Role.technician,
    customers: tuple[str, ...] = (),
    all_customers: bool = False,
    write: bool = True,
) -> dict[str, str]:
    """Create a user and return request headers carrying its bearer token."""
    user = await create_user(username, PASSWORD, username.title(), role=role)
    if write:
        await set_can_write(user.id, True)
    if all_customers:
        await set_all_customers(user.id, True)
    for cid in customers:
        await grant_access(user.id, cid)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


def assert_no_foreign(text: str) -> None:
    """The response must not mention the customer the caller cannot see."""
    assert BETA not in text, "foreign customer id leaked"
    assert "Beta AS" not in text, "foreign customer name leaked"
