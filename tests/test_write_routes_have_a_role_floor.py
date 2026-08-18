"""can_write is granted independently of role, so it is not a role floor.

The global write guard stops a read-only account changing anything, but a
handful of mutating routes carried only that guard and no role check. Because
can_write can be granted to a viewer, that left those routes reachable by a
viewer-with-write — someone who may save a note but, by role, has no business
importing customers, deleting audit history, or saving an integration's
credentials. These tests pin the role floor that now sits under them.

The scenario that matters is deliberately the awkward one: a viewer who *does*
hold can_write. Without can_write the write guard answers first (also 403) and
the role floor is never exercised, so every account below is granted write.
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


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


async def _writer(name: str, role: Role) -> dict:
    """A logged-in account of *role* that holds can_write and every customer."""
    user = await create_user(name, GOOD_PASSWORD, name.title(), role=role)
    await set_all_customers(user.id, True)
    await set_can_write(user.id, True)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


# A representative sample across the files that were hardened. Body is minimal:
# require_role runs as a dependency, before the handler, so a refused role is a
# 403 whatever the body is, and an accepted role falls through to validation
# (some other status) — never a role 403.
TECHNICIAN_ROUTES = [
    ("post", "/api/customer/notes"),
    ("post", "/api/customer/tags"),
    ("post", "/api/customers/add-manual"),
    ("post", "/api/audit/scope"),
    ("post", "/api/audit/presets"),
    ("post", "/api/workshop/notes"),
    ("post", "/api/history/delete"),
    ("post", "/api/uniweb/sync"),
    ("post", "/api/itglue/sync-all"),
    ("post", "/api/remediation"),
]

# These handle credentials/integration config, so the floor is admin, not tech.
ADMIN_ROUTES = [
    ("post", "/api/uniweb/settings"),
    ("post", "/api/itglue/upload/credentials"),
]


def _call(client, headers, method, path):
    return client.request(method.upper(), path, headers=headers, json={})


@pytest.mark.parametrize("method,path", TECHNICIAN_ROUTES)
async def test_a_viewer_with_write_is_refused_a_technician_route(client, method, path):
    headers = await _writer("view", Role.viewer)
    assert _call(client, headers, method, path).status_code == 403, (
        f"{path} let a viewer-with-write through — the role floor is missing"
    )


@pytest.mark.parametrize("method,path", TECHNICIAN_ROUTES)
async def test_a_technician_clears_the_role_floor(client, method, path):
    headers = await _writer("tech", Role.technician)
    # Past the floor: whatever the handler then does (400/404/422/200), it is not
    # the role 403. A lingering 403 would mean the floor is set too high.
    assert _call(client, headers, method, path).status_code != 403, (
        f"{path} refused a technician-with-write — the floor is set too high"
    )


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
async def test_a_technician_with_write_is_refused_an_admin_route(client, method, path):
    headers = await _writer("tech2", Role.technician)
    assert _call(client, headers, method, path).status_code == 403, (
        f"{path} handles credentials and must require admin, not technician"
    )


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
async def test_an_admin_clears_the_admin_floor(client, method, path):
    headers = await _writer("boss", Role.admin)
    assert _call(client, headers, method, path).status_code != 403, (
        f"{path} refused an admin-with-write — the floor is set too high"
    )
