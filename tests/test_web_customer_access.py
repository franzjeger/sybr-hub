"""Per-customer access enforcement on customer-scoped routes.

RBAC helpers existed and were tested, but only one route ever called them —
so a technician assigned to customer A could read customer B's dashboard,
config backups and threat logs by editing the URL.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import grant_access, set_all_customers
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app
from tests.test_web_auth import _iter_api_routes

GOOD_PASSWORD = "Test1234!xyz"


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
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


async def _token_for(username: str, role: Role, customers: list[str] | None = None) -> str:
    user = await create_user(username, GOOD_PASSWORD, username.title(), role=role)
    for cid in customers or []:
        await grant_access(user.id, cid)
    return await create_access_token(user)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Coverage: every {customer_id} route is scoped
# ---------------------------------------------------------------------------


def _has_customer_access_dep(route: APIRoute) -> bool:
    from tests.fastapi_introspect import has_dependency_named

    return has_dependency_named(route, "require_customer_access")


def test_every_customer_scoped_route_enforces_access(app):
    """Any route with a {customer_id} segment must check access to it."""
    scoped = [(p, r) for p, r in _iter_api_routes(app) if "{customer_id}" in p]
    assert len(scoped) > 15, f"expected many customer-scoped routes, found {len(scoped)}"

    unscoped = [
        f"{sorted(r.methods)} {p}" for p, r in scoped if not _has_customer_access_dep(r)
    ]
    assert not unscoped, (
        "customer-scoped routes not enforcing customer access:\n  " + "\n  ".join(unscoped)
    )


def test_every_host_scoped_route_enforces_access(app):
    """A route naming a {host_id} reaches one customer's device, so it is
    customer-scoped even though the path never says "customer".

    This test exists because the one above could not have caught the gap it is
    named for. Selecting routes by the literal string "{customer_id}" made the
    guard's coverage a property of URL spelling: hosts identify their customer
    through ssh_hosts.customer_id, so the entire SSH surface — stored device
    passwords, batch exec, key push, the interactive terminal — sat outside
    both the guard and the test that was supposed to enforce it.
    """
    from tests.fastapi_introspect import has_dependency_named

    scoped = [(p, r) for p, r in _iter_api_routes(app) if "{host_id}" in p]
    assert scoped, "expected routes with a {host_id} segment"

    unscoped = [
        f"{sorted(r.methods)} {p}"
        for p, r in scoped
        if not has_dependency_named(r, "require_host_access")
    ]
    assert not unscoped, (
        "host-scoped routes not enforcing host access:\n  " + "\n  ".join(unscoped)
    )


def test_every_audit_path_route_enforces_access(app):
    """Routes serving the audit tree name the customer as a path segment.

    Same blind spot, different spelling: /audit_data/{path:path} hands back
    decrypted audit artefacts, and the first segment of that path is the
    customer's directory.
    """
    from tests.fastapi_introspect import has_dependency_named

    scoped = [
        (p, r)
        for p, r in _iter_api_routes(app)
        if "{path:path}" in p and "audit" in p
    ]
    assert scoped, "expected the audit_data route to be present"

    unscoped = [
        f"{sorted(r.methods)} {p}"
        for p, r in scoped
        if not has_dependency_named(r, "require_audit_path_access")
    ]
    assert not unscoped, (
        "audit-tree routes not enforcing customer access:\n  " + "\n  ".join(unscoped)
    )


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/hub/{cid}",
        "/api/fortigate/dashboard/{cid}",
        "/api/fortigate/backups/{cid}",
        "/api/fortigate/compliance/{cid}",
        "/api/fortigate/threats/{cid}",
        "/api/unifi/clients/{cid}",
        "/api/unifi/dashboard/{cid}",
        "/api/unifi/firmware-check/{cid}",
    ],
)
async def test_technician_cannot_read_an_unassigned_customer(client, path):
    token = await _token_for("tech", Role.technician, customers=["acme"])
    resp = client.get(path.format(cid="other-corp"), headers=_h(token))
    assert resp.status_code == 403, f"{path} returned {resp.status_code}"


async def test_technician_can_read_an_assigned_customer(client):
    """The assigned customer must get past RBAC (404/400 from the handler is fine)."""
    token = await _token_for("tech", Role.technician, customers=["acme"])
    resp = client.get("/api/hub/acme", headers=_h(token))
    assert resp.status_code == 200


async def test_unassigned_technician_is_refused(client):
    """Fails closed: no assignments means no customers, not all of them."""
    token = await _token_for("tech", Role.technician)
    assert client.get("/api/hub/acme", headers=_h(token)).status_code == 403


async def test_all_customers_grant_reaches_any_customer(client):
    user = await create_user("tech", GOOD_PASSWORD, "Tech", role=Role.technician)
    await set_all_customers(user.id, True)
    token = await create_access_token(user)
    assert client.get("/api/hub/anything", headers=_h(token)).status_code == 200


async def test_admin_bypasses_customer_scoping(client):
    token = await _token_for("admin", Role.admin)
    assert client.get("/api/hub/any-customer", headers=_h(token)).status_code == 200


async def test_role_floor_still_applies_alongside_customer_scoping(client):
    """A viewer assigned the customer still can't reach a technician route."""
    token = await _token_for("viewer", Role.viewer, customers=["acme"])
    resp = client.get("/api/fortigate/dashboard/acme", headers=_h(token))
    assert resp.status_code == 403


async def test_customer_scoping_runs_before_the_handler(client):
    """A refused request must not reach the handler or touch the device."""
    token = await _token_for("tech", Role.technician, customers=["acme"])
    # 'other-corp' does not exist; a 404 would mean the handler ran anyway.
    resp = client.get("/api/fortigate/dashboard/other-corp", headers=_h(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Credential disclosure
# ---------------------------------------------------------------------------


async def test_credentials_endpoint_is_admin_only(client):
    """It returns a firewall's plaintext admin password — technicians are out."""
    token = await _token_for("tech", Role.technician, customers=["acme"])
    resp = client.get("/api/fortigate/credentials/acme", headers=_h(token))
    assert resp.status_code == 403
