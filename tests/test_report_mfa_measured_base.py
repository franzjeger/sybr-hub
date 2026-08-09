"""An MFA percentage is only as good as the users it was measured on.

The collector is careful: a user whose method lookup failed is *unknown*, not
"no MFA", and it keeps them out of both sides of the fraction. That is right.
What was missing is that nothing downstream said which subset the surviving
percentage came from.

Two failures, opposite directions, same root — ``has_data`` was ``total > 0``,
and ``total`` counts records, not readings:

  * Ninety of a hundred lookups fail. The ten that answered all have MFA. The
    report says 100% coverage, score 100, grade A, and declares nothing. The
    customer is told they have full MFA coverage on the strength of ten users.
  * All hundred fail. ``measured`` is 0, so ``pct`` is 0 — but ``has_data``
    was still True, so the score applied the full 35-point MFA weight and
    returned grade B as a measurement of a tenant nobody managed to read. The
    blocking-gap path written for exactly this case was unreachable.
"""

from __future__ import annotations

import json

from app.reports.generator import _compute_risk, _parse_mfa


def _records(with_mfa: int = 0, unknown: int = 0, without_mfa: int = 0) -> str:
    def rec(i, state, prefix):
        return {
            "display_name": f"{prefix}{i}", "upn": f"{prefix}{i}@acme.no",
            "mfa_registered": state, "ca_covered": False, "ca_excluded": False,
            "methods": ["app"] if state else [],
        }
    users = (
        [rec(i, True, "ok") for i in range(with_mfa)]
        + [rec(i, None, "unknown") for i in range(unknown)]
        + [rec(i, False, "no") for i in range(without_mfa)]
    )
    return json.dumps({"users": users})


def _mfa(**kw) -> dict:
    return _parse_mfa("", "", [], _records(**kw))


def _score(mfa: dict) -> dict:
    return _compute_risk(
        secure_score={"has_data": True, "pct": 100}, mfa=mfa, spf_dmarc=[],
        all_warns="", ext_fwd="", risky_users="No risky", defender="No active",
        admin_roles={"has_data": True, "global_admin_count": 1},
        intune={"has_data": True, "total": 1, "compliance_pct": 100},
        sharepoint={"has_data": True}, oauth={"has_data": True},
        network=None, lang="no",
    )


# ── A complete reading still behaves exactly as before ───────────────────────

def test_a_fully_read_tenant_is_unchanged():
    mfa = _mfa(with_mfa=100)
    assert mfa["has_data"] is True
    assert mfa["pct"] == 100.0
    result = _score(mfa)
    assert result["score"] == 100
    assert result["data_quality_issues"] == []


def test_a_genuinely_unprotected_tenant_still_scores_badly():
    # 0% must stay a reading, not become a missing reading. This is the case
    # the has_data guard exists to protect, and narrowing the predicate must
    # not swallow it.
    mfa = _mfa(without_mfa=100)
    assert mfa["has_data"] is True
    assert mfa["pct"] == 0
    assert _score(mfa)["score"] < 100


# ── The subset ───────────────────────────────────────────────────────────────

def test_a_percentage_from_a_subset_names_the_subset():
    mfa = _mfa(with_mfa=10, unknown=90)
    assert mfa["pct"] == 100.0, "unknowns must stay out of the fraction"
    joined = " ".join(_score(mfa)["data_quality_issues"])
    assert "10" in joined and "100" in joined and "90" in joined, (
        f"the score reported 100% coverage from ten users without saying so: {joined}"
    )


def test_a_small_gap_is_declared_too():
    mfa = _mfa(with_mfa=70, unknown=30)
    assert " ".join(_score(mfa)["data_quality_issues"]).strip()


def test_no_unknowns_declares_nothing():
    assert _score(_mfa(with_mfa=50, without_mfa=50))["data_quality_issues"] == []


def test_the_subset_note_does_not_block_the_grade():
    result = _score(_mfa(with_mfa=70, unknown=30))
    assert result["score"] is not None
    assert not result["blocking_data_gaps"]


# ── Nothing read at all ──────────────────────────────────────────────────────

def test_a_run_where_every_lookup_failed_is_not_data():
    mfa = _mfa(unknown=100)
    assert mfa["measured"] == 0
    assert mfa["has_data"] is False, (
        "total counts records; a record whose lookup failed is not a reading"
    )


def test_and_it_refuses_to_grade_rather_than_returning_B():
    result = _score(_mfa(unknown=100))
    assert result["score"] is None, (
        "the full 35-point MFA weight was applied to a tenant nobody read, "
        "and the result was published as grade B"
    )
    assert result["blocking_data_gaps"]
