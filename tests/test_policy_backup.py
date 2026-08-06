"""Policy snapshots — the backup half of the audit.

The audit has always collected Conditional Access policies and Intune
profiles, as evidence: columns trimmed to a width a person reads. A trimmed
policy cannot be put back, so nothing collected before this was a backup of
anything. The snapshots keep the objects exactly as Graph returned them.

Restore is deliberately absent. It writes into a customer's tenant, needs the
tenant_write capability and Graph permissions this app does not hold — every
one it asks for ends in .Read.All.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, create_user
from app.core.database import run_migrations
from app.core.rbac import set_all_customers
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
def audit_root(tmp_path, monkeypatch):
    root = tmp_path / "audits"
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: root)
    return root


def _write_snapshot(root: pathlib.Path, customer: str, run: str, name: str, items: list):
    from app.core.encryption import encrypted_write_text

    directory = root / customer / run / "policy_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(
        directory / f"{name}.json",
        json.dumps({"snapshot": name, "source": "x", "captured_at": "t",
                    "count": len(items), "items": items}),
    )


@pytest.fixture()
async def auth():
    user = await create_user("op", GOOD_PASSWORD, "Op", role=Role.admin)
    await set_all_customers(user.id, True)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_a_snapshot_keeps_the_object_whole(client, auth, audit_root):
    """Fidelity is the point. A trimmed policy cannot be restored."""
    policy = {
        "id": "p1", "displayName": "Require MFA", "state": "enabled",
        "conditions": {"users": {"includeUsers": ["All"]}},
        "grantControls": {"builtInControls": ["mfa"]},
    }
    _write_snapshot(audit_root, "Acme", "2026-08-05_1000", "conditional_access_policies", [policy])

    body = client.get(
        "/api/policy-backup/Acme/2026-08-05_1000/conditional_access_policies",
        headers=auth,
    ).json()
    assert body["items"][0] == policy, "the snapshot must not reshape what Graph gave"
    assert body["count"] == 1
    assert body["source"] == "x"


def test_a_run_with_no_snapshots_is_listed_not_hidden(client, auth, audit_root):
    """"Captured nothing" and "did not happen" are different runs."""
    (audit_root / "Acme" / "2026-08-05_0900").mkdir(parents=True)
    _write_snapshot(audit_root, "Acme", "2026-08-05_1000", "named_locations", [])

    runs = client.get("/api/policy-backup/Acme/runs", headers=auth).json()["runs"]
    by_name = {r["run"]: r for r in runs}
    assert by_name["2026-08-05_0900"]["captured"] is False
    assert by_name["2026-08-05_1000"]["captured"] is True
    assert runs[0]["run"] == "2026-08-05_1000", "newest first"


def test_the_diff_reports_what_moved(client, auth, audit_root):
    before = [
        {"id": "a", "displayName": "One", "state": "enabled"},
        {"id": "b", "displayName": "Two", "state": "enabled"},
    ]
    after = [
        {"id": "a", "displayName": "One", "state": "disabled"},
        {"id": "c", "displayName": "Three", "state": "enabled"},
    ]
    _write_snapshot(audit_root, "Acme", "run1", "conditional_access_policies", before)
    _write_snapshot(audit_root, "Acme", "run2", "conditional_access_policies", after)

    d = client.get(
        "/api/policy-backup/Acme/diff/run1/run2/conditional_access_policies",
        headers=auth,
    ).json()
    assert d["added"] == ["c"]
    assert d["removed"] == ["b"]
    assert d["changed"] == [{"id": "a", "fields": ["state"]}]
    assert d["unchanged"] == 0


def test_a_policy_that_only_gained_a_timestamp_is_not_drift(client, auth, audit_root):
    """Graph rewrites these on its own.

    Reporting them trains a reader to skim the diff, which is how a real
    change goes unread.
    """
    before = [{"id": "a", "displayName": "One", "modifiedDateTime": "2026-01-01"}]
    after = [{"id": "a", "displayName": "One", "modifiedDateTime": "2026-08-05"}]
    _write_snapshot(audit_root, "Acme", "r1", "conditional_access_policies", before)
    _write_snapshot(audit_root, "Acme", "r2", "conditional_access_policies", after)

    d = client.get(
        "/api/policy-backup/Acme/diff/r1/r2/conditional_access_policies", headers=auth
    ).json()
    assert d["changed"] == []
    assert d["unchanged"] == 1


def test_a_missing_snapshot_is_a_404_not_an_empty_diff(client, auth, audit_root):
    """An empty diff would read as "nothing changed", which is a claim."""
    _write_snapshot(audit_root, "Acme", "r1", "conditional_access_policies", [])
    resp = client.get(
        "/api/policy-backup/Acme/diff/r1/r2/conditional_access_policies", headers=auth
    )
    assert resp.status_code == 404


def test_the_snapshot_path_cannot_escape_the_customer(client, auth, audit_root):
    _write_snapshot(audit_root, "Acme", "r1", "conditional_access_policies", [])
    (audit_root / "Other" / "r1" / "policy_snapshots").mkdir(parents=True)
    resp = client.get(
        "/api/policy-backup/Acme/r1/..%2F..%2F..%2FOther%2Fr1%2Fpolicy_snapshots%2Fx",
        headers=auth,
    )
    assert resp.status_code in (400, 404)


def test_the_router_is_read_only():
    """Restore writes into a customer's tenant.

    It needs the tenant_write capability and .ReadWrite Graph permissions this
    app does not hold — every one it asks for ends in .Read.All. Backing up is
    the half that is safe today, and this asserts the other half did not
    arrive quietly alongside it: any route here that is not a GET is one.
    """
    from app.web.routes.policy_backup import router

    offenders = []
    for route in router.routes:
        methods = set(getattr(route, "methods", []) or [])
        if methods - {"GET", "HEAD", "OPTIONS"}:
            offenders.append((getattr(route, "path", "?"), sorted(methods)))
    assert not offenders, (
        f"policy-backup gained a mutating route without the capability guard: {offenders}"
    )
