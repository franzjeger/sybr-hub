"""Contract test: an audit that collected nothing must claim nothing.

This is the systemic version of a bug that had been found and fixed one
instance at a time — in the collectors (DNS, Graph, sign-ins, MFA methods)
and then all over the report layer (risk radar, executive summary, CIS 1.1.1,
UniFi WLAN security, Azure backup coverage). Every instance had the same
shape: a section produced no data, a default filled the gap, and the default
was rendered as a finding about the customer.

Rather than keep finding those by reading, render a full report context from
an empty directory and assert the whole surface stays silent. When this test
was written it immediately caught seven more:

  * a "SharePoint external sharing is at its most permissive level"
    recommendation, because sharing_level defaults to "warning"
  * CIS 4.3 graded **fail** — "no anti-spam policies found"
  * CIS 2.1.2, 4.4 and 9.2 graded **pass** — attesting that credentials are
    not expired, that no external forwarding exists, and that there are no
    Defender alerts, all from files that were never written
  * CIS 3.1.1, 3.2.1, 4.2, 4.5, 4.6 and 7.2.2 graded **warn**
  * an executive summary opening with "the environment has 0 users
    (0 active, 0 guests)"

and one that outlived the report: save_audit_metrics persisted 0 for every
unread metric, into _audit_metrics.json and the audit_metrics table, where
_compute_trends — which skips None but not 0 — would draw MFA coverage
collapsing to 0% and recovering in the customer's history. A later correct
audit adds a row but cannot retract that one.

A failure here is not necessarily a bug in the code this test names. It means
some part of the report grew a new claim that survives having no input. Fix
the claim, not the assertion.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.reports.generator import build_report_context, save_audit_metrics


@pytest.fixture
def audit_dir(tmp_path):
    """An empty audit run directory, nested so pytest's other tmp dirs are
    not treated as sibling audit runs by the trend loader."""
    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def empty_context(audit_dir):
    """A report context built from an audit directory with no output files."""
    return build_report_context(
        "Acme AS", "acme.no", audit_dir, [], lang="no", frameworks="all"
    )


# ── Findings ──────────────────────────────────────────────────────────────────


def test_no_recommendations_are_raised(empty_context):
    recs = empty_context.get("recommendations", [])
    assert recs == [], (
        "an audit that read nothing recommended: "
        + "; ".join(r.get("title", "?") for r in recs)
    )


def test_no_compliance_control_is_graded(empty_context):
    graded = [
        f"{c['cis_id']} {c['status']}: {c['detail']}"
        for c in empty_context.get("compliance", [])
        if c["status"] != "info"
    ]
    assert graded == [], "controls graded without evidence:\n  " + "\n  ".join(graded)


def test_controls_are_still_listed_rather_than_omitted(empty_context):
    """Silence is not the same as absence — the rows must still be there.

    Dropping a control entirely reads as "not applicable" to the customer,
    which is its own false claim. This is why CIS 4.3 was made
    unconditional in the first place; only its status was wrong.
    """
    statuses = Counter(c["status"] for c in empty_context.get("compliance", []))
    assert statuses["info"] > 20, f"too few controls emitted: {statuses}"


def test_nothing_is_counted_as_assessed(empty_context):
    assert empty_context.get("compliance_assessed") == 0
    assert empty_context.get("compliance_pass") == 0
    assert empty_context.get("compliance_fail") == 0


# ── Scores ────────────────────────────────────────────────────────────────────


def test_no_risk_grade_is_invented(empty_context):
    risk = empty_context["risk"]
    assert risk["score"] is None
    assert risk["grade"] == "?"
    assert risk["has_full_data"] is False


def test_the_risk_radar_is_empty_rather_than_flat(empty_context):
    assert empty_context.get("risk_radar") == {}
    assert empty_context.get("radar_svg") == ""


def test_the_executive_summary_says_so_instead_of_reporting_zeroes(empty_context):
    joined = "\n".join(empty_context.get("executive_summary", []))
    assert "0 brukere" not in joined, "reported a tenant with zero users"
    assert "None" not in joined
    # It should still say something — silence here would be its own problem.
    assert len(empty_context.get("executive_summary", [])) >= 3


# ── Persistence: the one that outlives the report ─────────────────────────────


def test_unread_metrics_persist_as_null_not_zero(empty_context, audit_dir, monkeypatch):
    """A zero here poisons the trend chart of every later audit."""
    written: dict = {}
    monkeypatch.setattr(
        "app.core.encryption.encrypted_write_json",
        lambda path, data: written.update(data),
    )
    monkeypatch.setattr("app.reports.generator._save_metrics_to_db", lambda *a, **k: None)

    save_audit_metrics(audit_dir, empty_context)

    for key in (
        "mfa_coverage_pct",
        "secure_score_pct",
        "total_users",
        "users_no_mfa",
        "ca_policies_enabled",
        "intune_compliance_pct",
        "intune_total_devices",
        "admin_roles_ga_count",
        "risk_score",
        "network_devices",
        "network_default_creds",
        "network_outdated_fw",
    ):
        assert written[key] is None, f"{key} persisted as {written[key]!r}, not None"


def test_measured_zeroes_are_still_persisted_as_zero(tmp_path, monkeypatch):
    """None means unknown. A real, measured zero must survive as 0."""
    written: dict = {}
    monkeypatch.setattr(
        "app.core.encryption.encrypted_write_json",
        lambda path, data: written.update(data),
    )
    monkeypatch.setattr("app.reports.generator._save_metrics_to_db", lambda *a, **k: None)

    save_audit_metrics(tmp_path, {
        "mfa": {"has_data": True, "pct": 0.0, "no_mfa": 40},
        "secure_score": {"has_data": True, "pct": 0.0},
        "users": {"has_data": True, "total": 40},
        "ca": {"has_data": True, "enabled": 0},
        "risk": {"score": 0, "grade": "F"},
    })

    assert written["mfa_coverage_pct"] == 0.0
    assert written["users_no_mfa"] == 40
    assert written["ca_policies_enabled"] == 0
    assert written["risk_score"] == 0
    assert written["total_users"] == 40


# ── An unreadable previous run must not take the report down ──────────────────


def test_an_undecryptable_previous_metrics_file_does_not_break_the_report(audit_dir):
    """Found by this very test file leaking tmp dirs between runs.

    load_previous_metrics caught (json.JSONDecodeError, OSError), which does
    not include cryptography's InvalidTag. A metrics file that could not be
    decrypted — after a master-key rotation, a recreated keyring entry, or
    plain corruption — propagated out of build_report_context and took the
    whole report with it. Losing the trend chart is the acceptable cost;
    losing the report is not.
    """
    previous = audit_dir.parent / "2025-12-01_0900"
    previous.mkdir()
    (previous / "_audit_metrics.json").write_bytes(b"MSPTK\x02" + b"\x00" * 64)

    ctx = build_report_context(
        "Acme AS", "acme.no", audit_dir, [], lang="no", frameworks="all"
    )

    assert ctx["risk"]["score"] is None      # still a complete context
    assert ctx.get("trends", {}) == {}       # just no trend comparison


def test_a_truncated_previous_metrics_file_is_also_survivable(audit_dir):
    previous = audit_dir.parent / "2025-12-01_0900"
    previous.mkdir()
    (previous / "_audit_metrics.json").write_bytes(b"")

    ctx = build_report_context(
        "Acme AS", "acme.no", audit_dir, [], lang="no", frameworks="all"
    )
    assert ctx.get("trends", {}) == {}
