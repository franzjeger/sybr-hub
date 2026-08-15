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
        # A fully-read, healthy SharePoint: sharing level established as clean and
        # legacy-auth known. A bare {"has_data": True} now (correctly) means "sites
        # read but settings unread" and raises a data-quality note of its own.
        sharepoint={"has_data": True, "sharing_level": "ok", "legacy_auth_known": True},
        oauth={"has_data": True}, network=None, lang="no",
    )


# ── no_mfa splits cleanly into unregistered vs registered-but-excluded (F1/F2) ─

def test_no_mfa_splits_into_unregistered_and_registered_but_excluded():
    users = json.dumps({"users": [
        {"display_name": "NoMfa", "upn": "no@acme.no", "mfa_registered": False,
         "ca_covered": False, "ca_excluded": False, "methods": []},
        {"display_name": "Excluded", "upn": "ex@acme.no", "mfa_registered": True,
         "ca_covered": False, "ca_excluded": True, "methods": ["app"]},
    ]})
    mfa = _parse_mfa("", "", [], users)
    assert mfa["no_mfa"] == 2
    assert mfa["no_mfa_registered"] == 1         # genuinely no method registered
    assert mfa["registered_but_excluded"] == 1   # has MFA, but CA-excluded from enforcement
    # The two are an exact partition of no_mfa.
    assert mfa["no_mfa_registered"] + mfa["registered_but_excluded"] == mfa["no_mfa"]


def test_partition_still_sums_to_no_mfa_for_a_ca_excluded_lookup_failure():
    # A CA-excluded admin whose method lookup was throttled: mfa_registered is
    # None (unknown) AND ca_excluded True. The coverage loop counts it in no_mfa
    # (an exclusion settles enforcement regardless of the failed lookup), and it
    # is NOT counted as unknown. The per-user partition must follow the same
    # rule, or no_mfa_registered + registered_but_excluded drops below no_mfa and
    # the finding-mfa detail breakdown under-accounts its own headline.
    users = json.dumps({"users": [
        {"display_name": "NoMfa", "upn": "no@acme.no", "mfa_registered": False,
         "ca_covered": False, "ca_excluded": False, "methods": []},
        {"display_name": "ExclReg", "upn": "er@acme.no", "mfa_registered": True,
         "ca_covered": False, "ca_excluded": True, "methods": ["app"]},
        {"display_name": "ExclUnknown", "upn": "eu@acme.no", "mfa_registered": None,
         "ca_covered": False, "ca_excluded": True, "methods": []},
    ]})
    mfa = _parse_mfa("", "", [], users)
    assert mfa["no_mfa"] == 3, "all three are not MFA-enforced"
    assert mfa["unknown"] == 0, "a CA-excluded user is known-unenforced, not unknown"
    assert mfa["no_mfa_registered"] + mfa["registered_but_excluded"] == mfa["no_mfa"]
    # The excluded-and-unknown user has no usable registered method → it belongs
    # with the "no method registered" bucket, not dropped from both.
    assert mfa["no_mfa_registered"] == 2      # NoMfa + ExclUnknown
    assert mfa["registered_but_excluded"] == 1  # ExclReg


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
