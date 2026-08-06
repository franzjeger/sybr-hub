"""The only routes in this application that change something outside it.

require_tenant_write has existed since the capability was added and guarded
nothing — a gate in a field. These are the endpoints it now stands in front of,
and there are two locks: can_write, which the middleware checks for every
mutating request, and tenant_write on top of it.
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


async def _auth(name, *, write=False, tenant=False):
    user = await create_user(name, GOOD_PASSWORD, name.title(), role=Role.admin)
    await set_all_customers(user.id, True)
    if write:
        await set_can_write(user.id, True)
    if tenant:
        await set_tenant_write(user.id, True)
    user = await get_user_by_id(user.id)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


BODY = {"template": "sybr-baseline-ca", "values": {"break_glass_group": "g-1"}}


async def test_a_read_only_account_cannot_even_plan(client):
    """Stopped by the middleware, before tenant_write is consulted."""
    auth = await _auth("reader")

    r = client.post("/api/policy-deploy/acme/plan", headers=auth, json=BODY)

    assert r.status_code == 403


async def test_write_alone_is_not_enough_to_touch_a_tenant(client):
    """The distinction the two capabilities exist for: saving a note here and
    changing configuration in somebody's Microsoft tenant."""
    auth = await _auth("writer", write=True)

    r = client.post("/api/policy-deploy/acme/plan", headers=auth, json=BODY)

    assert r.status_code == 403
    assert "skriv" in r.json().get("detail", r.json().get("error", "")).lower()


async def test_applying_needs_the_same_two_locks(client):
    auth = await _auth("writer", write=True)

    r = client.post(
        "/api/policy-deploy/acme/apply", headers=auth,
        json={**BODY, "fingerprint": "whatever"},
    )

    assert r.status_code == 403


async def test_the_template_list_is_readable_without_the_capability(client):
    """Knowing the standard exists is not the same as being able to push it."""
    auth = await _auth("reader")

    r = client.get("/api/policy-deploy/templates", headers=auth)

    assert r.status_code == 200
    assert any(t["id"] == "sybr-baseline-ca" for t in r.json()["templates"])


async def test_applying_without_a_fingerprint_is_refused(client, monkeypatch):
    """It is what ties the confirmation to the tenant that was reviewed."""
    auth = await _auth("deployer", write=True, tenant=True)

    r = client.post("/api/policy-deploy/acme/apply", headers=auth, json=BODY)

    assert r.status_code in (400, 422)


def test_the_router_carries_the_tenant_guard_on_every_mutating_route():
    """Asserting on the dependency rather than trusting the reading of it.

    This is the module where forgetting one costs a customer's production
    tenant, so it is checked by inspection rather than by eye.
    """
    from app.web.middleware.auth import require_tenant_write
    from app.web.routes.policy_deploy import router

    guarded = getattr(require_tenant_write(), "__qualname__", "")
    for route in router.routes:
        methods = set(getattr(route, "methods", []) or []) - {"HEAD", "OPTIONS"}
        if not methods - {"GET"}:
            continue
        names = [
            getattr(d.call, "__qualname__", "") for d in getattr(route, "dependant", None).dependencies
        ] if getattr(route, "dependant", None) else []
        assert any(n == guarded for n in names), (
            f"{sorted(methods)} {route.path} changes a customer tenant without "
            f"require_tenant_write"
        )


# ── Behind the locks ─────────────────────────────────────────────────────────

async def test_the_tenant_is_read_through_the_credential_not_the_auth_manager(monkeypatch):
    """The bug the guard tests could never have found.

    Every test above stops at a 403, so nothing exercised the Graph call behind
    them — and it was constructed with the AuthManager rather than its
    credential, which every other caller in the codebase gets right. It would
    have failed on the first real deployment with AttributeError: 'AuthManager'
    object has no attribute 'get_token'.

    Locks tested thoroughly, and the thing behind them not at all.
    """
    import app.web.routes.policy_deploy as mod

    seen: dict = {}
    sentinel = object()

    class _Auth:
        """Refuses its credential until entered, exactly as AuthManager does.

        The first version of this stub exposed it as a plain attribute, which
        is what I assumed the contract was. The test passed and production
        raised "AuthManager not entered as async context manager" — a stub that
        encodes the assumption rather than the contract tests nothing.
        """

        entered = False

        async def __aenter__(self):
            self.entered = True
            return self

        async def __aexit__(self, *a):
            return False

        @property
        def credential(self):
            if not self.entered:
                raise RuntimeError("AuthManager not entered as async context manager")
            return sentinel

    class _Graph:
        def __init__(self, credential, *a, **kw):
            seen["credential"] = credential

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_all(self, path):
            return []

        async def validate_permissions(self):
            return {"granted": []}

    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: {"CustomerName": "Acme", "TenantId": "t", "ClientId": "c"}),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_cert_path", staticmethod(lambda cid: "cert")
    )
    made = _Auth()
    monkeypatch.setattr(
        "app.modules.m365_audit.auth.get_auth_for_customer", lambda c, p: made
    )
    monkeypatch.setattr("app.modules.m365_audit.graph_client.GraphClient", _Graph)

    policies, missing_consent = await mod._live_policies("acme")

    assert made.entered, "the AuthManager was never entered, so it owns no credential yet"
    assert seen["credential"] is sentinel, "GraphClient was handed the AuthManager itself"
    assert policies == []
    assert missing_consent is True, "no granted roles means the write permission is absent"


def test_no_caller_hands_graphclient_an_auth_manager():
    """The same slip, guarded across the codebase rather than in one route."""
    import pathlib
    import re

    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        for m in re.finditer(r"GraphClient\(\s*(\w+)\s*[,)]", path.read_text(encoding="utf-8")):
            if m.group(1) in {"auth", "auth_manager"}:
                offenders.append(f"{path}: GraphClient({m.group(1)})")

    assert not offenders, (
        "GraphClient takes a credential, not an AuthManager:\n  " + "\n  ".join(offenders)
    )
