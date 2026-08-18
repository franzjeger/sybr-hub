"""Read-only and write-but-not-tenant accounts should not be *offered* controls
the server will refuse. The refusal itself is the real boundary (write_guard
middleware + require_tenant_write) and is tested elsewhere; this file covers the
UX layer on top of it:

* the two capability tiers are distinct and both reach the browser via /auth/me,
* the CSS/JS plumbing that hides each tier exists,
* the controls rendered by the JS view modules carry the marker, so a read-only
  or write-only account does not see a button whose only outcome is a 403.

The controls in index.html are covered by test_write_controls_are_marked.py;
that test cannot see the innerHTML-built controls in the app-*.js modules, which
is exactly what the static assertions here pin.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user, get_user_by_id
from app.core.database import run_migrations
from app.core.rbac import set_all_customers, set_can_write, set_tenant_write
from app.models.user import Role
from app.web.middleware.auth import _reset_users_exist_cache
from app.web.server import create_app

STATIC = pathlib.Path("app/web/static")
GOOD_PASSWORD = "Str0ng-Passphrase-For-Tests!"


# ── The two tiers reach the browser distinctly (the contract the UI gates on) ──

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


async def _me(client, *, write: bool, tenant: bool) -> dict:
    user = await create_user("op", GOOD_PASSWORD, "Op", role=Role.technician)
    await set_all_customers(user.id, True)
    if write:
        await set_can_write(user.id, True)
    if tenant:
        await set_tenant_write(user.id, True)
    user = await get_user_by_id(user.id)
    headers = {"Authorization": f"Bearer {await create_access_token(user)}"}
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json()["user"]


async def test_read_only_account_reports_neither_capability(client):
    u = await _me(client, write=False, tenant=False)
    assert u["can_write"] is False
    assert u["tenant_write"] is False


async def test_write_but_not_tenant_is_a_distinct_reported_state(client):
    u = await _me(client, write=True, tenant=False)
    assert u["can_write"] is True
    assert u["tenant_write"] is False


async def test_tenant_write_reports_both(client):
    u = await _me(client, write=True, tenant=True)
    assert u["can_write"] is True
    assert u["tenant_write"] is True


# ── The plumbing that acts on those flags ─────────────────────────────────────

def test_css_hides_each_tier():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert "body.is-readonly [data-write]" in css, "the can_write tier rule is gone"
    assert 'body.is-no-tenant-write [data-write="tenant"]' in css, (
        "the tenant_write tier rule is gone — a write-but-not-tenant account "
        "would be offered tenant controls"
    )


def test_js_toggles_both_body_classes():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function canTenantWrite" in js
    assert "'is-readonly'" in js and "'is-no-tenant-write'" in js


# ── The JS-rendered controls carry the marker (regression for the sweep) ──────

def _every_call_is_marked(src: str, handler: str, tier: str) -> bool:
    """True if every onclick=handler( in *src* is preceded by the right marker.

    Handles both quote forms the templates use: single-quoted JS strings write
    onclick="H(, double-quoted ones write onclick=\\"H(.
    """
    marker = 'data-write="tenant"' if tier == "tenant" else "data-write"
    for onclick in (f'onclick="{handler}(', f'onclick=\\"{handler}('):
        idx = 0
        while True:
            i = src.find(onclick, idx)
            if i == -1:
                break
            # the marker sits just before onclick, within the same tag
            preceding = src[max(0, i - 40):i]
            if marker not in preceding:
                return False
            idx = i + len(onclick)
    return True


TENANT_CONTROLS = [
    "policyDeployApply", "policyEnforce", "policyRestoreApply",
    "policyAdoptionSave", "policyConsentStart",
]
WRITE_CONTROLS = {
    "app-infra.js": ["vpnConnect", "vpnDisconnect", "vpnDeleteProfile",
                     "sshDeleteHost", "sshDoAddHost", "rdpStart"],
    "app-tailscale.js": ["tsRemoveDevice", "tsRevokeKey", "tsAuthorizeDevice"],
    "app-integrations.js": ["uniwebDoImport", "taskSchedRunNow"],
    "app-also.js": ["alsoBulkHandled", "alsoCombinedSync"],
    "app-dashboard.js": ["dashArchiveDelete", "dashArchiveCleanup"],
}


@pytest.mark.parametrize("handler", TENANT_CONTROLS)
def test_tenant_controls_carry_the_tenant_marker(handler):
    src = (STATIC / "app-policy-deploy.js").read_text(encoding="utf-8")
    assert f"{handler}(" in src, f"{handler} vanished from the module"
    assert _every_call_is_marked(src, handler, "tenant"), (
        f'{handler} reaches a require_tenant_write route but a call is not '
        f'marked data-write="tenant"'
    )


@pytest.mark.parametrize("fname,handlers", list(WRITE_CONTROLS.items()))
def test_write_controls_carry_the_write_marker(fname, handlers):
    src = (STATIC / fname).read_text(encoding="utf-8")
    for handler in handlers:
        assert f"{handler}(" in src, f"{handler} vanished from {fname}"
        assert _every_call_is_marked(src, handler, "write"), (
            f"{handler} in {fname} reaches a write route but a call is not "
            f"marked data-write"
        )
