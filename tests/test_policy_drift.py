"""Drift — what moved between two runs, and what "nothing moved" is allowed to mean.

The rule under every test here: *nothing to compare against is not "nothing
changed"*. A first run, a predecessor that predates snapshots, and a snapshot
that will not decrypt all look identical to a clean diff if you are careless,
and that reading is the dangerous one — "no policies were removed" is exactly
the reassurance a reader acts on.

So the totals are None rather than 0 whenever the comparison did not happen.
"""

from __future__ import annotations

import json
import pathlib

from app.core.policy_drift import (
    changed_fields,
    compute_drift,
    diff_items,
    previous_run_with_snapshots,
    snapshots_in,
)


def _write(root: pathlib.Path, run: str, name: str, items: list) -> pathlib.Path:
    from app.core.encryption import encrypted_write_text

    directory = root / run / "policy_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    encrypted_write_text(
        directory / f"{name}.json",
        json.dumps({"snapshot": name, "source": "x", "count": len(items), "items": items}),
    )
    return root / run


# ── The invariant ────────────────────────────────────────────────────────────

def test_a_first_run_is_not_measured_rather_than_drift_free(tmp_path):
    run = _write(tmp_path, "2026-01-01_0000", "conditional_access", [{"id": "a"}])

    d = compute_drift(run)

    assert d["measured"] is False
    assert "first measurement" in d["reason"]
    assert d["removed_total"] is None, "0 would read as 'no policy was removed'"
    assert d["added_total"] is None
    assert d["changed_total"] is None


def test_a_run_that_captured_nothing_is_not_measured(tmp_path):
    _write(tmp_path, "2026-01-01_0000", "conditional_access", [{"id": "a"}])
    barren = tmp_path / "2026-02-01_0000"
    barren.mkdir()

    d = compute_drift(barren)

    assert d["measured"] is False
    assert d["removed_total"] is None


def test_a_predecessor_without_that_snapshot_is_not_a_clean_diff(tmp_path):
    """The previous run captured something, just not this collection.

    Diffing against an absent file would report every policy as newly added,
    which is drift invented out of a gap in the evidence.
    """
    _write(tmp_path, "2026-01-01_0000", "named_locations", [{"id": "n"}])
    newer = _write(tmp_path, "2026-02-01_0000", "conditional_access", [{"id": "a"}])

    d = compute_drift(newer)

    assert d["measured"] is False, "nothing comparable means nothing measured"
    assert d["snapshots"][0]["comparable"] is False
    assert "did not capture" in d["snapshots"][0]["reason"]


def test_a_snapshot_that_will_not_read_costs_the_comparison_not_the_report(tmp_path):
    _write(tmp_path, "2026-01-01_0000", "conditional_access", [{"id": "a"}])
    newer = _write(tmp_path, "2026-02-01_0000", "conditional_access", [{"id": "a"}])
    (tmp_path / "2026-01-01_0000" / "policy_snapshots" / "conditional_access.json").write_bytes(
        b"not an envelope"
    )

    d = compute_drift(newer)

    assert d["measured"] is False
    assert d["snapshots"][0]["comparable"] is False


# ── The comparison itself ────────────────────────────────────────────────────

def test_a_removed_policy_is_named(tmp_path):
    """The one finding this whole feature exists for."""
    _write(tmp_path, "2026-01-01_0000", "conditional_access", [
        {"id": "a", "displayName": "Require MFA for admins", "state": "enabled"},
        {"id": "b", "displayName": "Block legacy auth", "state": "enabled"},
    ])
    newer = _write(tmp_path, "2026-02-01_0000", "conditional_access", [
        {"id": "a", "displayName": "Require MFA for admins", "state": "disabled"},
        {"id": "c", "displayName": "Require compliant device", "state": "enabled"},
    ])

    d = compute_drift(newer)

    assert d["measured"] is True
    assert d["compared_with"] == "2026-01-01_0000"
    assert d["removed_total"] == 1
    assert d["added_total"] == 1
    assert d["changed_total"] == 1

    snap = d["snapshots"][0]
    assert snap["removed"] == [{"id": "b", "name": "Block legacy auth"}]
    assert snap["added"] == [{"id": "c", "name": "Require compliant device"}]
    assert snap["changed"] == [
        {"id": "a", "name": "Require MFA for admins", "fields": ["state"]}
    ]


def test_a_genuinely_quiet_month_reports_zero_not_none(tmp_path):
    """The distinction only means anything if a real zero survives it."""
    items = [{"id": "a", "displayName": "One", "state": "enabled"}]
    _write(tmp_path, "2026-01-01_0000", "conditional_access", items)
    newer = _write(tmp_path, "2026-02-01_0000", "conditional_access", items)

    d = compute_drift(newer)

    assert d["measured"] is True
    assert (d["added_total"], d["removed_total"], d["changed_total"]) == (0, 0, 0)


def test_only_the_display_name_travels_with_a_diff(tmp_path):
    """A drift summary is read where a policy dump should not appear.

    The bodies carry group memberships and exclusion lists. Field *names* say
    what moved; field values would say who is exempt from it.
    """
    secret = ["group-that-bypasses-mfa"]
    _write(tmp_path, "2026-01-01_0000", "conditional_access", [
        {"id": "a", "displayName": "One", "excludeGroups": []},
    ])
    newer = _write(tmp_path, "2026-02-01_0000", "conditional_access", [
        {"id": "a", "displayName": "One", "excludeGroups": secret},
    ])

    d = compute_drift(newer)

    assert d["snapshots"][0]["changed"] == [
        {"id": "a", "name": "One", "fields": ["excludeGroups"]}
    ]
    assert "group-that-bypasses-mfa" not in json.dumps(d)


def test_a_timestamp_graph_rewrote_is_not_drift():
    before = [{"id": "a", "displayName": "One", "modifiedDateTime": "2026-01-01"}]
    after = [{"id": "a", "displayName": "One", "modifiedDateTime": "2026-08-05"}]

    assert diff_items(before, after)["changed"] == []
    assert diff_items(before, after)["unchanged"] == 1
    assert changed_fields(before[0], after[0]) == []


def test_an_object_without_an_id_is_dropped_rather_than_churned():
    """It cannot be tracked across runs, so it would be added-then-removed forever."""
    d = diff_items([{"displayName": "nameless"}], [{"displayName": "nameless"}])

    assert d == {"added": [], "removed": [], "changed": [], "unchanged": 0}


# ── Choosing what to compare against ─────────────────────────────────────────

def test_one_failed_audit_does_not_break_the_chain(tmp_path):
    """Compare against the last run that has something, not the last run.

    Otherwise a single 403 last night costs the drift reading entirely, at
    exactly the moment somebody is most likely to be looking.
    """
    _write(tmp_path, "2026-01-01_0000", "conditional_access", [{"id": "a", "displayName": "One"}])
    (tmp_path / "2026-02-01_0000").mkdir()
    newest = _write(tmp_path, "2026-03-01_0000", "conditional_access", [])

    assert previous_run_with_snapshots(newest).name == "2026-01-01_0000"
    d = compute_drift(newest)
    assert d["measured"] is True
    assert d["compared_with"] == "2026-01-01_0000"
    assert d["removed_total"] == 1


def test_a_later_run_is_never_compared_against(tmp_path):
    _write(tmp_path, "2026-05-01_0000", "conditional_access", [{"id": "z"}])
    run = _write(tmp_path, "2026-01-01_0000", "conditional_access", [{"id": "a"}])

    assert previous_run_with_snapshots(run) is None


def test_the_most_security_relevant_snapshot_is_listed_first(tmp_path):
    """A reader who stops after the first block should have read the CA policies."""
    run = tmp_path / "r"
    for name in ("intune_compliance", "named_locations", "conditional_access"):
        _write(tmp_path, "r", name, [])

    assert snapshots_in(run)[0] == "conditional_access"
