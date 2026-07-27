"""Regression tests for the CIS compliance map.

The report scores compliance as ``compliance_pass / compliance_assessed``,
where ``compliance_assessed`` deliberately excludes controls with status
``info``. That is the framework's way of saying "we could not check this, so
it does not count for or against you" — and every control in the map honoured
it except CIS 1.1.1.

1.1.1 collapsed "we could not read MFA state" and "we read it and nobody has
MFA" into a single ``fail``; its translation string admitted as much, reading
"MFA data not available or 0% coverage". That put an unverifiable control in
the failure bucket *and* kept it in the percentage denominator, so a tenant
whose Graph permissions blocked the user list came out looking non-compliant
rather than un-assessed.
"""

from __future__ import annotations

import pytest

from app.reports.generator import T, _build_compliance_map


def _control(controls: list[dict], cis_id: str) -> dict:
    return next(c for c in controls if c["cis_id"] == cis_id)


def _ctx(mfa: dict) -> dict:
    return {"mfa": mfa, "file_contents": {}}


def test_unreadable_mfa_is_info_not_fail():
    controls = _build_compliance_map(_ctx({"has_data": False, "pct": 0.0, "no_mfa": 0}))
    c = _control(controls, "1.1.1")
    assert c["status"] == "info", (
        "an unverifiable control must not count as a CIS failure"
    )
    assert c["detail"] == T("no").cis_mfa_unavailable


def test_unreadable_mfa_is_excluded_from_the_compliance_denominator():
    """Mirrors the arithmetic in build_report_context."""
    controls = _build_compliance_map(_ctx({"has_data": False, "pct": 0.0, "no_mfa": 0}))
    assessed = [c for c in controls if c["status"] != "info"]
    assert _control(controls, "1.1.1") not in assessed


def test_measured_zero_percent_mfa_is_a_real_failure():
    controls = _build_compliance_map(_ctx({"has_data": True, "pct": 0.0, "no_mfa": 38}))
    c = _control(controls, "1.1.1")
    assert c["status"] == "fail"
    assert "38" in c["detail"]
    assert c["detail"] != T("no").cis_mfa_unavailable


@pytest.mark.parametrize("lang", ["no", "en"])
def test_zero_percent_detail_does_not_claim_data_was_missing(lang):
    controls = _build_compliance_map(
        _ctx({"has_data": True, "pct": 0.0, "no_mfa": 38}), lang=lang
    )
    detail = _control(controls, "1.1.1")["detail"].lower()
    for claim in ("utilgjengelig", "ikke tilgjengelig", "not available", "unavailable"):
        assert claim not in detail, f"0% coverage described as {claim!r}: {detail!r}"


@pytest.mark.parametrize(
    ("pct", "expected"),
    [(100.0, "pass"), (95.0, "pass"), (94.0, "partial"), (1.0, "partial")],
)
def test_measured_coverage_keeps_its_existing_grading(pct, expected):
    controls = _build_compliance_map(_ctx({"has_data": True, "pct": pct, "no_mfa": 2}))
    assert _control(controls, "1.1.1")["status"] == expected


def test_unavailable_string_no_longer_conflates_two_conditions():
    """The old text hard-coded the conflation; keep it from coming back."""
    for lang in ("no", "en"):
        text = T(lang).cis_mfa_unavailable.lower()
        assert " or " not in text
        assert " eller " not in text
