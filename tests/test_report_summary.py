"""Regression tests for the executive summary bullets.

The executive summary is the part of a customer report that gets read aloud in
a meeting, so a wrong bullet there costs more than a wrong table row. Three
defects lived in ``_build_executive_summary``:

  * MFA branched on ``pct`` instead of ``has_data``, so a tenant where *every*
    user is unprotected (0% coverage) got "MFA data is not available for this
    customer" — the worst identity finding the product can make, announced as
    a non-measurement.
  * Secure Score did the same, silently dropping the bullet at 0%.
  * The closing bullet formatted ``risk["score"]`` into "{score}/100" without
    checking for the ``None`` that ``_compute_risk`` deliberately returns when
    a blocking data gap makes the grade fiction — printing "None/100".
"""

from __future__ import annotations

import pytest

from app.reports.generator import T, _build_executive_summary


def _ctx(**overrides) -> dict:
    ctx = {
        "users": {"total": 40, "enabled": 38, "guests": 2},
        "mfa": {"has_data": True, "pct": 97.0, "no_mfa": 1},
        "ca": {"has_data": True, "enabled": 4},
        "secure_score": {"has_data": True, "pct": 80.0, "improvements": []},
        "intune": {"has_data": True, "total": 20, "noncompliant": 0, "compliance_pct": 100},
        "azure": {"has_data": True, "total_resources": 12, "subscriptions": ["s1"]},
        "admin_roles": {"has_data": True, "global_admin_count": 3},
        "risk": {"score": 82, "grade": "A", "blocking_data_gaps": []},
        "recommendations": [],
    }
    ctx.update(overrides)
    return ctx


# ── MFA: 0% is a finding, not a missing measurement ───────────────────────────


@pytest.mark.parametrize("lang", ["no", "en"])
def test_zero_percent_mfa_is_reported_as_a_finding_not_as_unavailable(lang):
    t = T(lang)
    bullets = _build_executive_summary(
        _ctx(mfa={"has_data": True, "pct": 0.0, "no_mfa": 38}), lang=lang
    )

    assert t.exec_mfa_unavailable not in bullets, (
        "a measured 0% must not be presented as an unavailable measurement"
    )
    mfa_bullet = next(b for b in bullets if "MFA" in b)
    assert "0%" in mfa_bullet
    assert "38" in mfa_bullet


def test_genuinely_missing_mfa_data_still_says_unavailable():
    t = T("no")
    bullets = _build_executive_summary(
        _ctx(mfa={"has_data": False, "pct": 0.0, "no_mfa": 0})
    )
    assert t.exec_mfa_unavailable in bullets


def test_high_mfa_coverage_still_gets_the_good_bullet():
    bullets = _build_executive_summary(_ctx())
    assert any("97" in b for b in bullets)


def test_partial_mfa_coverage_still_reports_the_gap():
    bullets = _build_executive_summary(
        _ctx(mfa={"has_data": True, "pct": 60.0, "no_mfa": 16})
    )
    mfa_bullet = next(b for b in bullets if "MFA" in b)
    assert "60%" in mfa_bullet and "16" in mfa_bullet


# ── Secure Score ──────────────────────────────────────────────────────────────


def test_zero_secure_score_still_produces_a_bullet():
    bullets = _build_executive_summary(
        _ctx(secure_score={"has_data": True, "pct": 0.0, "improvements": [{"a": 1}]})
    )
    assert any("0%" in b for b in bullets)


def test_missing_secure_score_produces_no_bullet_rather_than_a_zero():
    ctx = _ctx(secure_score={"has_data": False, "pct": 0.0, "improvements": []})
    bullets = _build_executive_summary(ctx)
    assert not any("Secure Score" in b or "sikkerhetspoeng" in b.lower() for b in bullets)


# ── Overall grade: never print "None/100" ─────────────────────────────────────


@pytest.mark.parametrize("lang", ["no", "en"])
def test_ungradeable_audit_does_not_print_none_out_of_100(lang):
    """_compute_risk returns score=None on a blocking gap; honour it."""
    t = T(lang)
    bullets = _build_executive_summary(
        _ctx(
            mfa={"has_data": False, "pct": 0.0, "no_mfa": 0},
            risk={
                "score": None,
                "grade": "?",
                "blocking_data_gaps": ["MFA-dekning utilgjengelig"],
            },
        ),
        lang=lang,
    )

    joined = "\n".join(bullets)
    assert "None" not in joined
    assert "None/100" not in joined
    assert t.exec_overall_invalid in bullets


def test_graded_audit_still_states_the_score():
    bullets = _build_executive_summary(_ctx())
    assert any("82/100" in b for b in bullets)


def test_a_zero_score_is_still_printed_rather_than_swallowed():
    """0 is falsy — the guard must test `is None`, not truthiness."""
    bullets = _build_executive_summary(
        _ctx(risk={"score": 0, "grade": "F", "blocking_data_gaps": []})
    )
    assert any("0/100" in b for b in bullets)
