"""Customer metrics preserve the scorer's real gaps, in either UI language."""

from app.reports.metrics import risk_coverage
from app.reports.risk import _compute_risk


def test_unknown_legacy_score_does_not_imply_complete_data():
    assert risk_coverage({"score": 100, "grade": "A"}) == {"state": "unknown", "issues": []}


def test_missing_mfa_blocks_score_and_preserves_bilingual_evidence():
    risk = _compute_risk({}, {}, [], [], "", "", "")
    coverage = risk_coverage(risk)
    assert risk["score"] is None
    assert coverage["state"] == "blocked"
    assert [x["no"] for x in coverage["issues"]] == risk["data_quality_issues"]
    assert all(x["en"] for x in coverage["issues"])


def test_partial_mfa_keeps_actual_counts_in_both_languages():
    risk = _compute_risk(
        {},
        {"has_data": True, "pct": 100, "no_mfa": 0, "unknown": 90, "measured": 10, "total": 100},
        [],
        [],
        "",
        "",
        "",
    )
    coverage = risk_coverage(risk)
    assert coverage["state"] == "partial"
    assert "10" in coverage["issues"][0]["en"]
    assert "90" in coverage["issues"][0]["no"]
