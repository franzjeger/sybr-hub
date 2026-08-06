"""Putting a tenant back, and why it gets no gentler rules than a deployment.

Restore is a write into somebody's production tenant. A restore path with its
own softer rails would be a deployment path with softer rails, one POST away —
so it shares the planner, the fingerprint, the lockout guard and the
report-only default with the deployment it undoes.
"""

from __future__ import annotations

import json

import pytest

from app.core.policy_restore import (
    AUDIT,
    DEPLOYMENT,
    RestoreError,
    list_sources,
    load_source,
)
from app.modules.m365_audit.policy_deploy import build_plan, lockout_risk


def _policy(name, *, state="enabledForReportingButNotEnforced", exclude=("bg",)):
    return {
        "id": f"id-{name}", "displayName": name, "state": state,
        "conditions": {"users": {"includeUsers": ["All"], "excludeGroups": list(exclude)}},
        "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
    }


@pytest.fixture()
def audits(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    return tmp_path


def _write(path, items, **extra):
    from app.core.encryption import encrypted_write_text

    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(path, json.dumps({"count": len(items), "items": items, **extra}))


def _point(root, customer, stamp, items):
    _write(root / customer / "policy_restore_points" / f"{stamp}.json", items,
           captured_at=stamp, reason="taken immediately before a policy deployment")


def _snapshot(root, customer, run, items):
    _write(root / customer / run / "policy_snapshots" / "conditional_access_policies.json", items)


# ── Finding something to go back to ──────────────────────────────────────────

def test_both_kinds_of_source_are_offered(audits):
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])
    _snapshot(audits, "Acme", "2026-08-05_1843", [_policy("One"), _policy("Two")])

    kinds = {s.kind for s in list_sources("Acme")}

    assert kinds == {DEPLOYMENT, AUDIT}


def test_a_deployment_point_is_listed_before_the_audit_snapshots(audits):
    """When both could answer, the one taken at the moment of a change is the
    one somebody reaching for a rollback means."""
    _snapshot(audits, "Acme", "2026-08-05_1843", [_policy("One")])
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])

    assert list_sources("Acme")[0].kind == DEPLOYMENT


def test_a_customer_with_nothing_stored_offers_nothing(audits):
    assert list_sources("Nobody") == []


def test_an_unreadable_source_is_skipped_not_fatal(audits):
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])
    (audits / "Acme" / "policy_restore_points" / "broken.json").write_bytes(b"not an envelope")

    assert [s.ref for s in list_sources("Acme")] == ["2026-08-06_101500"]


def test_a_run_directory_that_is_not_a_run_is_ignored(audits):
    """policy_restore_points sits beside the runs and is not one."""
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])

    assert all(s.kind == DEPLOYMENT or s.ref[:4].isdigit() for s in list_sources("Acme"))


# ── Reading one ──────────────────────────────────────────────────────────────

def test_a_restore_point_yields_the_policies_it_stored(audits):
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One"), _policy("Two")])

    assert [p["displayName"] for p in load_source("Acme", DEPLOYMENT, "2026-08-06_101500")] == [
        "One", "Two"
    ]


def test_an_audit_snapshot_yields_its_policies(audits):
    _snapshot(audits, "Acme", "2026-08-05_1843", [_policy("One")])

    assert len(load_source("Acme", AUDIT, "2026-08-05_1843")) == 1


def test_a_reference_that_climbs_out_of_the_customer_is_refused(audits):
    """It would hand another customer's policies to a planner pointed here."""
    _point(audits, "Other", "2026-08-06_101500", [_policy("Theirs")])

    with pytest.raises(RestoreError):
        load_source("Acme", DEPLOYMENT, "../Other/policy_restore_points/2026-08-06_101500")


def test_an_unknown_kind_is_refused(audits):
    with pytest.raises(RestoreError, match="Unknown restore source"):
        load_source("Acme", "whatever", "x")


def test_a_missing_source_says_so(audits):
    with pytest.raises(RestoreError, match="No deployment restore source"):
        load_source("Acme", DEPLOYMENT, "2026-01-01_000000")


# ── The rails, unchanged ─────────────────────────────────────────────────────

def test_restoring_uses_the_same_planner_as_deploying(audits):
    """Same diff, same fingerprint, same refusals — the reuse is the point."""
    stored = [_policy("One"), _policy("Gone")]
    _point(audits, "Acme", "2026-08-06_101500", stored)
    live = [{**_policy("One", state="disabled"), "modifiedDateTime": "t"}]

    plan = build_plan("Acme", live, load_source("Acme", DEPLOYMENT, "2026-08-06_101500"))

    actions = {c.name: c.action for c in plan.changes}
    assert actions == {"One": "update", "Gone": "create"}
    assert plan.fingerprint


def test_a_stored_policy_that_would_lock_the_tenant_out_is_still_refused(audits):
    """The deliberate trade.

    It was presumably working when captured, so refusing is inconvenient. But
    "it worked before" is not a guarantee it works now — the break-glass
    account may have been deleted since — and a restore that waives the guard
    is a deployment that waives the guard, one POST away.
    """
    dangerous = _policy("Lockout", state="enabled", exclude=[])
    _point(audits, "Acme", "2026-08-06_101500", [dangerous])

    assert lockout_risk(dangerous) is not None
    plan = build_plan("Acme", [], load_source("Acme", DEPLOYMENT, "2026-08-06_101500"))
    assert plan.applicable == []
    assert plan.refused[0].refused


def test_policies_added_since_are_left_alone_by_default(audits):
    """A restore that removed everything added since would roll back other
    people's work as well as the deployment."""
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])
    live = [{**_policy("One"), "modifiedDateTime": "t"}, {**_policy("Added"), "modifiedDateTime": "t"}]

    plan = build_plan("Acme", live, load_source("Acme", DEPLOYMENT, "2026-08-06_101500"))

    assert plan.changes == []


def test_removing_what_was_added_is_possible_when_asked(audits):
    _point(audits, "Acme", "2026-08-06_101500", [_policy("One")])
    live = [{**_policy("One"), "modifiedDateTime": "t"}, {**_policy("Added"), "modifiedDateTime": "t"}]

    plan = build_plan(
        "Acme", live, load_source("Acme", DEPLOYMENT, "2026-08-06_101500"), allow_delete=True
    )

    assert [(c.action, c.name) for c in plan.changes] == [("delete", "Added")]
