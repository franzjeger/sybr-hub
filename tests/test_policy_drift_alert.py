"""Telling somebody a security policy disappeared.

Drift has been computed at every audit since the snapshots landed, and nobody
was told. A tenant can hold the same Secure Score for six months while somebody
disables the policy requiring MFA for administrators — Microsoft raises
nothing, the score barely notices, and the only record was a section of a
report nobody had reason to open.
"""

from __future__ import annotations

import pytest

from app.services.alert_engine import _check_policy_drift


@pytest.fixture()
def tenant(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [{"_id": "Acme", "CustomerName": "Acme AS"}]),
    )
    # The audit tree is named after the customer with anything unusual folded
    # to an underscore — "Acme AS" becomes Acme_AS. Getting that wrong in a
    # fixture tests the fallback rather than the mapping.
    (tmp_path / "Acme_AS" / "2026-01-01_0000").mkdir(parents=True)
    return tmp_path


def _drift(**kw):
    base = {"measured": True, "compared_with": "2026-01-01_0000", "snapshots": []}
    base.update(kw)
    return base


def _snapshot(removed=(), changed=()):
    return [{
        "name": "conditional_access_policies", "comparable": True,
        "removed": list(removed), "changed": list(changed), "added": [],
    }]


async def test_a_removed_policy_is_critical(tenant, monkeypatch):
    """And it is reported under the customer's real name, not the directory's."""
    monkeypatch.setattr(
        "app.core.policy_drift.compute_drift",
        lambda run: _drift(snapshots=_snapshot(removed=[{"id": "1", "name": "Require MFA for admins"}])),
    )

    alerts = await _check_policy_drift()

    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["customer"] == "Acme AS"
    assert "Require MFA for admins" in alerts[0]["detail"]


async def test_changes_are_silent_unless_asked_for(tenant, monkeypatch):
    """Alerting on every edit is how a channel becomes something people mute.

    A policy that is gone is gone; a policy whose fields moved is usually
    somebody working.
    """
    monkeypatch.setattr(
        "app.core.policy_drift.compute_drift",
        lambda run: _drift(snapshots=_snapshot(changed=[{"id": "1", "name": "X", "fields": ["state"]}])),
    )

    assert await _check_policy_drift() == []
    assert len(await _check_policy_drift(alert_on_changed=True)) == 1


async def test_unmeasured_drift_wakes_nobody(tenant, monkeypatch):
    """"No policy was removed" and "there was nothing to compare against" are
    different claims, and only the first is worth an alert."""
    monkeypatch.setattr(
        "app.core.policy_drift.compute_drift",
        lambda run: {"measured": False, "reason_code": "no_earlier_snapshots", "snapshots": []},
    )

    assert await _check_policy_drift() == []


async def test_an_uncomparable_snapshot_is_not_read_as_removal(tenant, monkeypatch):
    monkeypatch.setattr(
        "app.core.policy_drift.compute_drift",
        lambda run: _drift(snapshots=[{
            "name": "conditional_access_policies", "comparable": False,
            "reason_code": "predecessor_lacked_snapshot",
        }]),
    )

    assert await _check_policy_drift() == []


async def test_a_customer_with_no_runs_is_skipped(tenant, monkeypatch):
    import shutil

    shutil.rmtree(tenant / "Acme_AS" / "2026-01-01_0000")
    monkeypatch.setattr("app.core.policy_drift.compute_drift", lambda run: _drift())

    assert await _check_policy_drift() == []


async def test_a_failure_reading_one_tenant_does_not_lose_the_run(tenant, monkeypatch):
    """An alert engine that raises stops every other check behind it."""
    def _boom(run):
        raise RuntimeError("unreadable")

    monkeypatch.setattr("app.core.policy_drift.compute_drift", _boom)

    assert await _check_policy_drift() == []


def test_the_rule_is_on_by_default_and_carries_a_recommendation():
    """A finding nobody is told about was the whole problem."""
    from app.services.alert_engine import _RECOMMENDATIONS, DEFAULT_ALERT_CONFIG

    rule = DEFAULT_ALERT_CONFIG["rules"]["policy_drift"]
    assert rule["enabled"] is True
    assert rule["alert_on_changed"] is False
    assert "gjenopprettingspunkt" in _RECOMMENDATIONS["policy_drift"]


def test_the_check_actually_runs():
    """A check nothing calls is a check that reports nothing, forever."""
    import pathlib

    source = pathlib.Path("app/services/alert_engine.py").read_text(encoding="utf-8")
    after_definition = source.split("async def _check_policy_drift")[1]

    assert "_check_policy_drift(" in after_definition, "defined but never invoked"
