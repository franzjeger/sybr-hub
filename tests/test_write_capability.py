"""Read is what an account can do. Changing anything is a grant somebody made.

The rule is enforced in one middleware rather than on 163 mutating endpoints,
because a decorator per route is 163 chances to forget one and the forgotten
one is the one that matters. A request that changes something is denied unless
nothing exempted it.

So the tests that matter are about the *shape* of the rule: that the default is
closed, that the exemption list describes real routes, and that it cannot widen
by accident.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import set_all_customers, set_can_write, set_tenant_write
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


async def _account(name="op", role=Role.admin, *, write=False):
    user = await create_user(name, GOOD_PASSWORD, name.title(), role=role)
    await set_all_customers(user.id, True)
    if write:
        await set_can_write(user.id, True)
        user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}, user


# ── The default ──────────────────────────────────────────────────────────────

async def test_a_new_admin_cannot_change_anything(client):
    """Admins included. A capability implied by a role is not a capability."""
    auth, _ = await _account(role=Role.admin)

    r = client.post("/api/customer/notes", headers=auth, json={"notes": "hei"})

    assert r.status_code == 403
    assert "lesetilgang" in r.json()["error"]


async def test_reading_is_unaffected(client):
    auth, _ = await _account()

    assert client.get("/api/health", headers=auth).status_code == 200
    assert client.get("/api/auth/me", headers=auth).status_code == 200


async def test_the_grant_is_what_opens_it(client):
    """Past the guard, into the handler.

    The endpoint is chosen for having an answer that needs no active customer:
    a 422 means the request reached validation, which is as far as this test
    cares to go.
    """
    auth, _ = await _account(write=True)

    r = client.post("/api/auth/users", headers=auth, json={})

    assert r.status_code == 422, "the guard should have let this reach validation"


async def test_revoking_closes_it_again(client):
    auth, user = await _account(write=True)
    await set_can_write(user.id, False)

    assert client.post("/api/customer/notes", headers=auth, json={"notes": "x"}).status_code == 403


async def test_the_capability_is_reported_to_the_client(client):
    """The interface has to know which menus to show."""
    auth, _ = await _account(write=True)

    me = client.get("/api/auth/me", headers=auth).json()["user"]

    assert me["can_write"] is True
    assert me["tenant_write"] is False


# ── What stays open ──────────────────────────────────────────────────────────

async def test_you_can_still_change_your_own_password_without_write(client):
    """Otherwise a read-only account can never rotate its own credential."""
    auth, _ = await _account()

    r = client.post(
        "/api/auth/change-password", headers=auth,
        json={"current_password": GOOD_PASSWORD, "new_password": "An0ther-Str0ng-One!"},
    )

    assert r.status_code != 403


async def test_you_can_still_switch_customer_without_write(client):
    """It changes what you are looking at, not what is.

    Gating it would leave a read-only account able to read exactly one tenant.
    """
    auth, _ = await _account()

    r = client.post("/api/customers/switch", headers=auth, json={"customer_id": "nope"})

    assert r.status_code != 403


# ── The shape of the rule ────────────────────────────────────────────────────

def test_every_exemption_names_a_route_that_exists():
    """An exemption for a path nothing serves is a list that has stopped
    describing what it exempts — and the next reader trusts it anyway."""
    from app.web.middleware.write_guard import ALLOWED_WITHOUT_WRITE

    def walk(routes, prefix=""):
        for r in routes:
            if type(r).__name__ == "_IncludedRouter":
                ctx = getattr(r, "include_context", None)
                yield from walk(r.original_router.routes, prefix + (getattr(ctx, "prefix", "") if ctx else ""))
            elif hasattr(r, "routes"):
                yield from walk(r.routes, prefix + getattr(r, "path", ""))
            else:
                methods = set(getattr(r, "methods", []) or []) - {"HEAD", "OPTIONS"}
                if methods - {"GET"}:
                    yield prefix + getattr(r, "path", "")

    served = set(walk(create_app().routes))
    phantom = sorted(ALLOWED_WITHOUT_WRITE - served)

    assert not phantom, f"exempted paths that no mutating route serves: {phantom}"


def test_the_exemption_list_stays_small_enough_to_read():
    """It is the whole security argument. If it needs scrolling, it is not
    being reviewed, and default-deny has quietly become default-allow."""
    from app.web.middleware.write_guard import ALLOWED_WITHOUT_WRITE

    assert len(ALLOWED_WITHOUT_WRITE) <= 30, (
        f"{len(ALLOWED_WITHOUT_WRITE)} exemptions — each one is a mutating "
        f"endpoint open to every account"
    )


def test_an_exemption_does_not_cover_paths_beneath_it():
    """Prefix matching is how an exemption silently grows a subtree."""
    from app.web.middleware.write_guard import _is_exempt

    assert _is_exempt("/api/auth/login")
    assert not _is_exempt("/api/auth/login/escalate")
    assert not _is_exempt("/api/auth/users")


# ── Layering ─────────────────────────────────────────────────────────────────

async def test_tenant_write_needs_write_underneath_it(client):
    """An account that may not save a note here has no business changing
    configuration inside somebody's Microsoft tenant."""
    from app.web.middleware.auth import require_tenant_write

    auth, user = await _account(write=False)
    await set_tenant_write(user.id, True)
    refreshed = await get_user_by_id(user.id)

    assert refreshed.tenant_write is True
    assert refreshed.can_write is False

    check = require_tenant_write()
    with pytest.raises(Exception) as exc:
        await check(customer_id="acme", user=refreshed)
    assert "403" in str(exc.value) or "skriv" in str(exc.value).lower()
