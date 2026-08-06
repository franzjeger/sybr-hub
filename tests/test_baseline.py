"""A baseline is a standard to measure against, and it must know what it did
not measure.

The rule this whole file exists to hold: a check whose evidence was not
collected reports not_measured, never fail. This codebase found that same
mistake in the Intune section, the MFA figure, CIS 6.1.1, password protection
and Purview inside one week — a standard that judges those sections is not
going to reintroduce it one layer up.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.core.baseline import (
    FAIL,
    NOT_MEASURED,
    PASS,
    BaselineError,
    evaluate_check,
    list_baselines,
    load_baseline,
)

CHECK = {
    "id": "mfa", "title": "MFA", "path": "mfa.registered_pct",
    "op": "gte", "value": 95, "measured_when": "mfa.has_data",
    "severity": "high",
}


def test_a_conformant_tenant_passes():
    ctx = {"mfa": {"has_data": True, "registered_pct": 98.0}}
    assert evaluate_check(CHECK, ctx)["status"] == PASS


def test_a_tenant_below_the_bar_fails():
    ctx = {"mfa": {"has_data": True, "registered_pct": 75.3}}
    r = evaluate_check(CHECK, ctx)
    assert r["status"] == FAIL
    assert "75.3" in r["detail"] and "95" in r["detail"]


def test_evidence_that_was_never_collected_is_not_a_failure():
    """The rule the file exists for.

    Scoring an unreadable section as non-conformant hands the customer a
    remediation task for something nobody looked at. Scoring it as conformant
    is worse.
    """
    ctx = {"mfa": {"has_data": False}}
    r = evaluate_check(CHECK, ctx)
    assert r["status"] == NOT_MEASURED
    assert "never collected" in r["detail"]


def test_a_missing_field_is_not_a_failure_either():
    """The section said it had data and then did not carry the field.

    That is a collector defect or a renamed key, and calling it a failure
    blames the customer for our bug.
    """
    ctx = {"mfa": {"has_data": True}}
    r = evaluate_check(CHECK, ctx)
    assert r["status"] == NOT_MEASURED
    assert "collector problem" in r["detail"]


def test_a_null_figure_is_not_a_zero():
    """None is what an unmeasured number legitimately holds here."""
    ctx = {"mfa": {"has_data": True, "registered_pct": None}}
    assert evaluate_check(CHECK, ctx)["status"] == NOT_MEASURED


def test_a_zero_really_is_a_zero():
    """The counterpart — 0% registered must fail, not go quiet."""
    ctx = {"mfa": {"has_data": True, "registered_pct": 0}}
    assert evaluate_check(CHECK, ctx)["status"] == FAIL


def test_conformance_is_quoted_over_what_was_assessed(tmp_path, monkeypatch):
    """A percentage that folds in the unassessed describes the audit."""
    import app.core.baseline as bl

    doc = {
        "id": "t", "version": "1", "name": "T",
        "checks": [
            {"id": "a", "path": "x.v", "op": "gte", "value": 1, "measured_when": "x.ok"},
            {"id": "b", "path": "x.v", "op": "gte", "value": 999, "measured_when": "x.ok"},
            {"id": "c", "path": "y.v", "op": "gte", "value": 1, "measured_when": "y.ok"},
        ],
    }
    (tmp_path / "t.json").write_text(json.dumps(doc))
    monkeypatch.setattr(bl, "BASELINE_DIR", tmp_path)

    out = bl.evaluate("t", {"x": {"ok": True, "v": 5}, "y": {"ok": False}})
    assert out["passed"] == 1
    assert out["failed"] == 1
    assert out["not_measured"] == 1
    assert out["assessed"] == 2
    assert out["conformance_pct"] == 50.0, "the unassessed check must not count against"
    assert out["total_checks"] == 3


def test_conformance_is_none_when_nothing_could_be_assessed():
    """Not 0%. Zero conformance is a verdict; this is the absence of one."""
    import app.core.baseline as bl

    out = bl.evaluate("sybr-standard", {})
    assert out["conformance_pct"] is None
    assert out["assessed"] == 0
    assert out["not_measured"] == out["total_checks"]


def test_the_shipped_baseline_is_well_formed():
    doc = load_baseline("sybr-standard")
    assert doc["version"], "a baseline without a version cannot be cited later"
    for check in doc["checks"]:
        assert check.get("measured_when"), (
            f"{check['id']} has no guard — it would fail a tenant on evidence "
            f"nobody read"
        )
        assert check.get("why"), f"{check['id']} has no rationale for the customer"
        assert check.get("severity") in ("critical", "high", "medium")


def test_every_shipped_check_reads_a_path_the_report_actually_produces(tmp_path):
    """Measured against a real context, not against intent.

    Two checks in the first draft named paths that resolve on no tenant at
    all: intune.entra_unmanaged is only set when both the Intune and Entra
    sides were read, so it was absent on exactly the tenants the check was
    for. The guard would have reported them not_measured forever — safe, and
    silently useless.

    This builds a context the way the report does, from an empty run. Every
    parser lands in its no-data branch, which is the harshest case: a path
    that survives that exists unconditionally, and the ones that led to this
    test do not. The earlier version of this test grepped generator.py for the
    leaf name, and quietly stopped covering anything the moment a context key
    began life in another module — which the drift check promptly did.
    """
    from app.core.baseline import _MISSING, _resolve
    from app.reports.generator import build_report_context

    run = tmp_path / "Acme" / "2026-01-01_0000"
    run.mkdir(parents=True)
    context = build_report_context("Acme", "", run, [], lang="no")

    doc = load_baseline("sybr-standard")
    for check in doc["checks"]:
        for label, path in (("path", check["path"]), ("measured_when", check["measured_when"])):
            assert not isinstance(_resolve(context, path), type(_MISSING)), (
                f"{check['id']} names {label} {path!r}, which resolves nowhere in "
                f"a report context — the check can never do anything"
            )


def test_an_unmeasured_drift_reaches_the_baseline_as_none_not_zero(tmp_path):
    """The belt under the measured_when guard.

    drift.removed_total is None on a run with nothing to compare against, so
    a check reading it reports not_measured even if whoever wrote that check
    forgot the guard. Were it 0, the same check would report "no policy was
    removed" — a reassurance derived from never having looked.
    """
    from app.reports.generator import build_report_context

    run = tmp_path / "Acme" / "2026-01-01_0000"
    run.mkdir(parents=True)
    context = build_report_context("Acme", "", run, [], lang="no")

    assert context["drift"]["measured"] is False
    assert context["drift"]["removed_total"] is None

    verdict = evaluate_check(
        {"id": "x", "path": "drift.removed_total", "op": "eq", "value": 0},
        context,
    )
    assert verdict["status"] == NOT_MEASURED


def test_a_duplicate_check_id_is_refused(tmp_path, monkeypatch):
    import app.core.baseline as bl

    doc = {"id": "d", "version": "1", "name": "D", "checks": [
        {"id": "same", "path": "a.b"}, {"id": "same", "path": "a.c"},
    ]}
    (tmp_path / "d.json").write_text(json.dumps(doc))
    monkeypatch.setattr(bl, "BASELINE_DIR", tmp_path)
    with pytest.raises(BaselineError, match="Duplicate"):
        bl.load_baseline("d")


def test_the_shipped_baseline_is_listed():
    ids = {b["id"] for b in list_baselines()}
    assert "sybr-standard" in ids
