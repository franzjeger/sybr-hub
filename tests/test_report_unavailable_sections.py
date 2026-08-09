"""A section that did not run keeps its points, and must say so.

The collector records a failure — Exchange writes EXCHANGE_ERROR.txt and reports
SKIPPED — and the report counts skipped and failed sections for its summary. The
count never reached the score. So a tenant whose Exchange collection failed,
which the collector itself calls a routine outcome when PowerShell cannot
connect, scored as though Exchange were clean: no external forwarding, no
transport rule findings, nothing beside the score to say it was never looked at.
"""

from __future__ import annotations

from app.reports.generator import _compute_risk


def _score(**kwargs):
    base = dict(
        secure_score={"has_data": True, "pct": 80},
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[], all_warns="", ext_fwd="", risky_users="No risky",
        defender="No active", admin_roles={}, intune={"has_data": True},
        sharepoint={}, oauth={}, network=None, lang="no",
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
