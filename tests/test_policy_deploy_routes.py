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


# ── Restore, behind the same two locks ───────────────────────────────────────

RESTORE = {"kind": "deployment", "ref": "2026-08-06_101500"}


async def test_listing_restore_sources_needs_the_tenant_capability(client):
    """The list is a map of when this tenant changed, which a read-only
    account has no need for."""
    auth = await _auth("writer", write=True)

    assert client.get("/api/policy-restore/acme/sources", headers=auth).status_code == 403


async def test_planning_a_restore_needs_both_locks(client):
    auth = await _auth("reader")

    assert client.post("/api/policy-restore/acme/plan", headers=auth, json=RESTORE).status_code == 403


async def test_applying_a_restore_needs_both_locks(client):
    auth = await _auth("writer", write=True)

    r = client.post(
        "/api/policy-restore/acme/apply", headers=auth, json={**RESTORE, "fingerprint": "x"}
    )

    assert r.status_code == 403


async def test_a_restore_without_a_fingerprint_is_refused(client):
    """Same rule as a deployment: the confirmation is tied to the state that
    was reviewed."""
    auth = await _auth("deployer", write=True, tenant=True)

    r = client.post("/api/policy-restore/acme/apply", headers=auth, json=RESTORE)

    assert r.status_code in (400, 422)


def test_every_restore_route_carries_the_tenant_guard_too():
    """The module now holds six routes that reach a customer tenant. The one
    added without the guard is the one that matters, so this checks all of
    them by inspection rather than by eye."""
    from app.web.middleware.auth import require_tenant_write
    from app.web.routes.policy_deploy import router

    guarded = getattr(require_tenant_write(), "__qualname__", "")
    checked = 0
    for route in router.routes:
        path = getattr(route, "path", "")
        if "policy-restore" not in path:
            continue
        checked += 1
        names = [
            getattr(d.call, "__qualname__", "")
            for d in getattr(route, "dependant", None).dependencies
        ] if getattr(route, "dependant", None) else []
        assert any(n == guarded for n in names), f"{path} is unguarded"

    assert checked == 3, f"expected three restore routes, inspected {checked}"


# ── Adoption, behind the same locks ──────────────────────────────────────────

async def test_suggesting_adoptions_needs_the_tenant_capability(client):
    auth = await _auth("writer", write=True)

    r = client.post("/api/policy-deploy/acme/adoption/suggest", headers=auth, json=BODY)

    assert r.status_code == 403


async def test_confirming_an_adoption_needs_the_tenant_capability(client):
    """It decides which of the customer's policies we start overwriting."""
    auth = await _auth("writer", write=True)

    r = client.put(
        "/api/policy-deploy/acme/adoption", headers=auth, json={**BODY, "mapping": {}}
    )

    assert r.status_code == 403


async def test_reading_the_confirmed_adoptions_needs_it_too(client):
    auth = await _auth("reader")

    assert client.get("/api/policy-deploy/acme/adoption", headers=auth).status_code == 403


def test_every_adoption_route_carries_the_tenant_guard():
    """Three more routes that decide what happens to a customer's policies."""
    from app.web.middleware.auth import require_tenant_write
    from app.web.routes.policy_deploy import router

    guarded = getattr(require_tenant_write(), "__qualname__", "")
    checked = 0
    for route in router.routes:
        path = getattr(route, "path", "")
        if "adoption" not in path:
            continue
        checked += 1
        names = [
            getattr(d.call, "__qualname__", "")
            for d in getattr(route, "dependant", None).dependencies
        ] if getattr(route, "dependant", None) else []
        assert any(n == guarded for n in names), f"{path} is unguarded"

    assert checked == 3, f"expected three adoption routes, inspected {checked}"


# ── Asking for the permission ────────────────────────────────────────────────

async def test_starting_a_consent_sign_in_needs_the_tenant_capability(client):
    """It leads to widening what this application may do in a customer tenant."""
    auth = await _auth("writer", write=True)

    assert client.post("/api/policy-deploy/acme/consent/start", headers=auth).status_code == 403


async def test_completing_a_consent_needs_it_too(client):
    auth = await _auth("reader")

    assert client.post("/api/policy-deploy/acme/consent/complete", headers=auth).status_code == 403


async def test_completing_without_a_pending_sign_in_says_so(client):
    auth = await _auth("deployer", write=True, tenant=True)

    r = client.post("/api/policy-deploy/acme/consent/complete", headers=auth)

    assert r.status_code in (400, 422)


def test_the_consent_routes_carry_the_tenant_guard():
    from app.web.middleware.auth import require_tenant_write
    from app.web.routes.policy_deploy import router

    guarded = getattr(require_tenant_write(), "__qualname__", "")
    checked = 0
    for route in router.routes:
        if "consent" not in getattr(route, "path", ""):
            continue
        checked += 1
        names = [
            getattr(d.call, "__qualname__", "")
            for d in getattr(route, "dependant", None).dependencies
        ] if getattr(route, "dependant", None) else []
        assert any(n == guarded for n in names), f"{route.path} is unguarded"

    assert checked == 2, f"expected two consent routes, inspected {checked}"


def test_the_toolkit_still_cannot_widen_its_own_access():
    """The property this whole flow exists because of.

    If AppRoleAssignment.ReadWrite.All ever appears in what the app asks for
    app-only, a compromised Sybr HUB becomes a way into every customer tenant,
    and none of the guards elsewhere in this module matter.
    """
    from app.core.config import REQUIRED_GRAPH_PERMISSIONS

    # Named rather than pattern-matched. A first draft flagged
    # RoleManagement.Read.Directory — a read permission — on the substring
    # "RoleManagement", which is how a guard starts crying wolf and gets
    # deleted by whoever is trying to ship something.
    ESCALATION = {
        "AppRoleAssignment.ReadWrite.All",
        "Application.ReadWrite.All",
        "RoleManagement.ReadWrite.Directory",
        "Directory.ReadWrite.All",
    }
    granted = set(REQUIRED_GRAPH_PERMISSIONS)

    assert not (granted & ESCALATION), (
        f"the app-only set can now widen its own access: {sorted(granted & ESCALATION)}"
    )
    writes = sorted(p for p in granted if ".ReadWrite." in p or p.endswith(".Write"))
    assert not writes, (
        f"the app-only set is meant to be read-only; it now asks for: {writes}"
    )
