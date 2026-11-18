"""A section that did not run keeps its points, and must say so.

The collector records a failure: Exchange writes EXCHANGE_ERROR.txt and reports
FAILED. The report counts skipped and failed sections for its summary. The
count never reached the score. So a tenant whose Exchange collection failed,
which the collector itself calls a routine outcome when PowerShell cannot
connect, scored as though Exchange were clean: no external forwarding, no
transport rule findings, nothing beside the score to say it was never looked at.
"""

from __future__ import annotations

from app.reports.risk import _compute_risk


def _score(**kwargs):
    base = dict(
        secure_score={"has_data": True, "pct": 80},
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[],
        all_warns="",
        ext_fwd="",
        risky_users="No risky",
        defender="No active",
        admin_roles={},
        intune={"has_data": True},
        sharepoint={},
        oauth={},
        network=None,
        lang="no",
    )
    base.update(kwargs)
    return _compute_risk(**base)


def test_a_skipped_section_is_declared_beside_the_score():
    result = _score(unavailable_sections=["Exchange Online"])
    joined = " ".join(result.get("data_quality_issues", []))
    assert "Exchange Online" in joined


def test_several_sections_are_each_named():
    result = _score(unavailable_sections=["Exchange Online", "Intune"])
    joined = " ".join(result.get("data_quality_issues", []))
    assert "Exchange Online" in joined
    assert "Intune" in joined


def test_a_complete_audit_declares_nothing():
    result = _score(unavailable_sections=[])
    assert not [g for g in result.get("data_quality_issues", []) if "ikke fullført" in g]


def test_none_is_the_same_as_none_skipped():
    # The parameter is optional so existing callers keep working; absent must
    # not be read as "everything failed".
    result = _score()
    assert not [g for g in result.get("data_quality_issues", []) if "ikke fullført" in g]


def test_it_does_not_invalidate_the_grade():
    # A skipped section is a hole, not a reason to refuse to grade. MFA still
    # owns that decision, and it has its own check.
    result = _score(unavailable_sections=["Exchange Online"])
    assert result.get("score") is not None
    assert not result.get("blocking_data_gaps")


# ── The wiring, not just the function ────────────────────────────────────────
#
# The gap was never that _compute_risk could not express this. It was that the
# caller had the list four lines away and did not pass it. A test that only
# calls _compute_risk directly would have passed against the broken code, so
# this one goes through build_report_context the way an audit does.


def test_a_real_run_with_a_skipped_section_says_so(tmp_path):
    from app.modules.base import SectionResult, SectionStatus
    from app.reports.generator import build_report_context
    from tests.audit_fixture import FULL_AUDIT

    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (d / name).write_text(content, encoding="utf-8")

    results = [
        SectionResult(name="Entra ID", status=SectionStatus.DONE),
        SectionResult(
            name="Exchange Online",
            status=SectionStatus.SKIPPED,
            error="Connect-ExchangeOnline failed",
        ),
    ]
    ctx = build_report_context(
        "Acme AS",
        "acme.no",
        d,
        results,
        lang="no",
        frameworks="all",
        persist_metrics=False,
    )
    joined = " ".join(ctx["risk"].get("data_quality_issues", []))
    assert "Exchange Online" in joined, (
        "the report counts skipped sections for its summary but the score never hears about them"
    )


def test_a_complete_run_stays_quiet(tmp_path):
    from app.modules.base import SectionResult, SectionStatus
    from app.reports.generator import build_report_context
    from tests.audit_fixture import FULL_AUDIT

    d = tmp_path / "Acme_AS" / "2026-01-01_0901"
    d.mkdir(parents=True)
    for name, content in FULL_AUDIT.items():
        (d / name).write_text(content, encoding="utf-8")

    results = [SectionResult(name="Entra ID", status=SectionStatus.DONE)]
    ctx = build_report_context(
        "Acme AS",
        "acme.no",
        d,
        results,
        lang="no",
        frameworks="all",
        persist_metrics=False,
    )
    assert not [g for g in ctx["risk"].get("data_quality_issues", []) if "ikke fullført" in g]


# ── The section is named in the report's language ─────────────────────────────
#
# A section's name is the collector's English, and the Norwegian sentence read
# "Sign-in Activity ble ikke fullført, ..." (TODO C15).


def test_the_section_is_named_in_the_reports_language():
    result = _score(unavailable_sections=["Sign-in Activity", "Usage Reports", "Something New"])
    issues = result["data_quality_issues"]

    assert any(i.startswith("Påloggingsaktivitet ble ikke fullført") for i in issues)
    assert any(i.startswith("Bruksrapporter ble ikke fullført") for i in issues)
    assert any(i.startswith("Something New ble ikke fullført") for i in issues), (
        "a section nobody named is still named, as it is"
    )


def test_the_stored_evidence_names_the_section_in_both_languages():
    """The run keeps both languages of each note, for the customer page."""
    from app.reports.metrics import risk_coverage

    coverage = risk_coverage(_score(unavailable_sections=["Sign-in Activity"]))

    (issue,) = [i for i in coverage["issues"] if "Sign-in" in i["en"] or "Pålogging" in i["no"]]
    assert issue["no"].startswith("Påloggingsaktivitet ble ikke fullført")
    assert issue["en"].startswith("Sign-in activity did not complete")


def test_the_technical_reports_status_table_names_each_section(tmp_path):
    from app.modules.base import SectionResult, SectionStatus
    from app.reports.generator import _jinja_env, build_report_context
    from app.reports.i18n import T

    d = tmp_path / "Acme_AS" / "2026-01-01_0902"
    d.mkdir(parents=True)
    results = [SectionResult(name="Sign-in Activity", status=SectionStatus.DONE)]
    ctx = build_report_context("Acme AS", "acme.no", d, results, lang="no", persist_metrics=False)
    ctx.update(t=T("no"), lang="no", theme="light")
    page = _jinja_env().get_template("report_tech.html.j2").render(**ctx)

    assert '<td style="font-weight:500;">Påloggingsaktivitet</td>' in page
