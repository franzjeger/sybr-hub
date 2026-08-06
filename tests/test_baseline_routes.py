"""The baseline and drift endpoints as the customer card actually calls them.

The card fires both on every open, and `apiFetch` raises a toast on any 4xx.
So the shape of "nothing to measure yet" matters as much as the arithmetic: a
customer we have not audited is a state, not a bad request, and answering it
with a 404 puts an error in a technician's face for a customer who is simply
new.
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


@pytest.fixture()
async def auth():
    user = await create_user("op", GOOD_PASSWORD, "Op", role=Role.admin)
    await set_all_customers(user.id, True)
    return {"Authorization": f"Bearer {await create_access_token(user)}"}


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _snapshot(root: pathlib.Path, customer: str, run: str, name: str, items: list):
    from app.core.encryption import encrypted_write_text

    directory = root / customer / run / "policy_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(
        directory / f"{name}.json",
        json.dumps({"snapshot": name, "source": "x", "count": len(items), "items": items}),
    )


# ── The baseline endpoint ────────────────────────────────────────────────────

def test_a_customer_with_no_runs_answers_200_not_404(client, auth, audit_root):
    """The card calls this on every open; a 404 would toast at the technician."""
    r = client.get("/api/baselines/default/evaluate/Acme/latest", headers=auth)

    assert r.status_code == 200
    body = r.json()
    assert body["evaluated"] is False
    assert body["reason_code"] == "no_runs"
    assert "conformance_pct" not in body, "no verdict without a run to judge"


def test_latest_resolves_to_the_newest_run(client, auth, audit_root):
    for run in ("2026-01-01_0000", "2026-08-05_1843", "2026-03-01_0000"):
        (audit_root / "Acme" / run).mkdir(parents=True)

    body = client.get("/api/baselines/default/evaluate/Acme/latest", headers=auth).json()

    assert body["evaluated"] is True
    assert body["run"] == "2026-08-05_1843"


def test_an_explicitly_named_missing_run_is_still_a_404(client, auth, audit_root):
    """Asking for a run by name and getting the wrong one silently is worse."""
    (audit_root / "Acme" / "2026-01-01_0000").mkdir(parents=True)

    r = client.get("/api/baselines/default/evaluate/Acme/2026-02-02_0000", headers=auth)

    assert r.status_code == 404


def test_the_default_sentinel_names_the_house_standard(client, auth, audit_root):
    from app.core.baseline import default_baseline_id

    (audit_root / "Acme" / "2026-01-01_0000").mkdir(parents=True)

    body = client.get("/api/baselines/default/evaluate/Acme/latest", headers=auth).json()

    assert body["baseline"]["id"] == default_baseline_id()


def test_the_listing_marks_which_baseline_is_the_default(client, auth):
    body = client.get("/api/baselines", headers=auth).json()

    assert body["default"]
    assert [b for b in body["baselines"] if b["is_default"]], "no baseline is marked default"


def test_an_unread_section_is_not_measured_rather_than_failed(client, auth, audit_root):
    """A run with no evidence must not come back as 0 % conformance.

    That percentage would describe the audit, not the tenant — and it is a
    remediation task for something nobody looked at.
    """
    (audit_root / "Acme" / "2026-01-01_0000").mkdir(parents=True)

    body = client.get("/api/baselines/default/evaluate/Acme/latest", headers=auth).json()

    assert body["not_measured"] == body["total_checks"]
    assert body["assessed"] == 0
    assert body["conformance_pct"] is None, "0 % is a verdict; there was none to give"


# ── The drift endpoint ───────────────────────────────────────────────────────

def test_drift_for_a_customer_with_no_runs_is_not_measured(client, auth, audit_root):
    body = client.get("/api/policy-backup/Acme/drift", headers=auth).json()

    assert body["measured"] is False
    assert body["removed_total"] is None, "0 would read as 'no policy was removed'"


def test_drift_names_the_policy_that_disappeared(client, auth, audit_root):
    _snapshot(audit_root, "Acme", "2026-01-01_0000", "conditional_access", [
        {"id": "a", "displayName": "Require MFA for admins"},
        {"id": "b", "displayName": "Block legacy auth"},
    ])
    _snapshot(audit_root, "Acme", "2026-02-01_0000", "conditional_access", [
        {"id": "a", "displayName": "Require MFA for admins"},
    ])

    body = client.get("/api/policy-backup/Acme/drift", headers=auth).json()

    assert body["measured"] is True
    assert body["run"] == "2026-02-01_0000"
    assert body["compared_with"] == "2026-01-01_0000"
    assert body["removed_total"] == 1
    assert body["snapshots"][0]["removed"] == [{"id": "b", "name": "Block legacy auth"}]


def test_a_removed_policy_reaches_the_baseline_as_a_deviation(client, auth, audit_root):
    """The whole point of wiring drift into the context.

    Secure Score barely moves when a policy is deleted and Microsoft raises no
    alert. The baseline names it.
    """
    _snapshot(audit_root, "Acme", "2026-01-01_0000", "conditional_access", [
        {"id": "a", "displayName": "Block legacy auth"},
    ])
    _snapshot(audit_root, "Acme", "2026-02-01_0000", "conditional_access", [])

    body = client.get("/api/baselines/default/evaluate/Acme/latest", headers=auth).json()
    check = next(c for c in body["checks"] if c["id"] == "no-policy-removed")

    assert check["status"] == "fail"
    assert check["why"], "a deviation the customer reads needs a reason"
