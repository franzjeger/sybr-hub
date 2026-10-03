"""Shared setup for the request-body contract tests.

The route layer used to read ``await request.json()`` and pick fields with
``body.get(...)``. A JSON list, a value of the wrong type or a misspelt key
then became a 500 or a field silently dropped. The tests that import this pin
each converted route three ways: a body the front-end sends still works, a
value of the wrong type is a 4xx rather than a 500, and an unknown key is
answered the way the route's model decided.

Importing modules get a fresh database per test and signed-in admin,
technician and viewer clients that hold can_write and every customer.
``raise_server_exceptions=False`` so a 500 shows up as a status a test can
assert on instead of the original exception.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import set_all_customers, set_can_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

PASSWORD = "Str0ng-Passphrase-For-Body-Tests!"


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
async def _init_db(tmp_path, monkeypatch):
    """A database, a customer store and a GDAP config of the test's own.

    The customer store is written under the per-test master key, so one left
    over from an earlier test is unreadable rather than merely stale.
    """
    import app.core.credentials as credentials_module
    import app.core.customer as customer_module
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    (tmp_path / "customers").mkdir()
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")
    # Fixed at import under the shared sandbox, and encrypted under this
    # test's key: left behind, it makes every later GET /api/settings a 500.
    monkeypatch.setattr(credentials_module, "_GDAP_CONFIG_PATH", tmp_path / "gdap_config.json")
    customer_module._tags_cache.clear()
    await run_migrations()
    yield


async def _token(name: str, role: Role, *, tenant_write: bool = False) -> str:
    user = await create_user(name, PASSWORD, name.title(), role=role)
    await set_all_customers(user.id, True)
    await set_can_write(user.id, True)
    if tenant_write:
        from app.core.rbac import set_tenant_write

        await set_tenant_write(user.id, True)
    return await create_access_token(await get_user_by_id(user.id))


def _client(token: str):
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture()
async def admin_client():
    token = await _token("bodyadmin", Role.admin)
    with _client(token) as c:
        yield c


@pytest.fixture()
async def tech_client():
    token = await _token("bodytech", Role.technician)
    with _client(token) as c:
        yield c


@pytest.fixture()
async def tenant_writer_client():
    """An admin who may also change customer tenants (setup, provisioning)."""
    token = await _token("bodytenant", Role.admin, tenant_write=True)
    with _client(token) as c:
        yield c


def assert_refused(response, *statuses: int) -> dict:
    """A shaped 4xx — never a 500, and always something the SPA can show."""
    allowed = statuses or (400, 422)
    assert response.status_code in allowed, (response.status_code, response.text)
    body = response.json()
    assert body.get("ok") is False, body
    assert isinstance(body.get("error"), str) and body["error"], body
    return body
