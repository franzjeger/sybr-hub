"""A collector's explanation of why it could not look is not a measurement.

When a fetch fails, the collector does not delete the file — it writes prose
into it. ``19b_defender_active_alerts.txt`` gets ``Error: {ex}``; the sign-in
and risky-user files get a "(not available)" block naming the licence or
permission that is missing. Every reader in the report already knew to check
for that shape. The score did not.

So a 403 on the Defender endpoint was counted as one active alert and cost
four points — the same score as a tenant with a live phishing alert, and with
nothing beside it to say the alert was invented. And a tenant without Entra ID
P2 scored identically on risky users to one that was verified clean.

Note this is not the same gap as a *deleted* file, which is what
``test_report_partial_audit.py`` exercises. Deletion gives an empty string and
scores as absent. Collectors do not delete on failure; they write stubs. The
partial-audit invariant could not see this class at all.
"""

from __future__ import annotations

import pytest

from app.reports.generator import _compute_risk, _evidence_unavailable

_HEALTHY = dict(
    secure_score={"has_data": True, "pct": 100},
    mfa={"has_data": True, "pct": 100, "no_mfa": 0},
    spf_dmarc=[], all_warns="", ext_fwd="",
    risky_users="No risky users found",
    defender="No active alerts",
    admin_roles={"has_data": True, "global_admin_count": 1},
    intune={"has_data": True, "total": 1, "compliance_pct": 100},
    sharepoint={"has_data": True}, oauth={"has_data": True},
    network=None, lang="no",
)


def _score(**kw):
    d = dict(_HEALTHY)
    d.update(kw)
    return _compute_risk(**d)


def _gaps(result) -> str:
    return " ".join(result.get("data_quality_issues", []))


def test_the_healthy_tenant_scores_100_with_nothing_to_declare():
    result = _score()
    assert result["score"] == 100
    assert result["data_quality_issues"] == []


# ── Defender ─────────────────────────────────────────────────────────────────

def test_a_refused_defender_fetch_does_not_invent_an_alert():
    # This is what the collector writes at identity_security.py:349.
    result = _score(defender="Error: HTTP 403 Forbidden\n")
    assert result["score"] == 100, (
        "the error stub was counted as an alert — a permission failure cost "
        "the customer points for a finding that does not exist"
    )


def test_a_refused_defender_fetch_is_declared():
    result = _score(defender="Error: HTTP 403 Forbidden\n")
    assert "Defender" in _gaps(result)


def test_a_real_alert_still_costs_points():
    # The guard must not swallow the finding it was added to protect.
    result = _score(defender="  Alert: phishing campaign detected\n")
    assert result["score"] < 100
    assert "Defender" not in _gaps(result)


def test_an_absent_defender_file_declares_nothing():
    # Section never ran; that is unavailable_sections' job to name, not this.
    result = _score(defender="")
    assert result["score"] == 100
    assert result["data_quality_issues"] == []


# ── Risky users ──────────────────────────────────────────────────────────────

def test_a_licence_gap_on_risky_users_is_declared():
    result = _score(risky_users=(
        "=" * 70 + "\n  RISKY USERS  (not available)\n" + "=" * 70 + "\n"
        "  This data requires Entra ID P2; the tenant may not have it.\n"
    ))
    assert result["score"] == 100, "a licence gap must not manufacture a penalty"
    assert "Risikobruker" in _gaps(result)


def test_verified_clean_risky_users_declares_nothing():
    result = _score(risky_users="No risky users found")
    assert result["data_quality_issues"] == []


def test_a_real_risky_user_still_costs_points():
    result = _score(risky_users="  user@acme.no  riskLevel: high\n")
    assert result["score"] < 100


# ── The head window ──────────────────────────────────────────────────────────
#
# _evidence_unavailable searched the whole file for "requires" / "not
# available". Collectors only ever write those in the title line or the cause
# block under it. Over a long list of findings the odds of one of them
# containing the word are not small, and the cost is silent: the file reads as
# unmeasured and its penalty disappears.

def test_the_marker_is_recognised_in_the_header():
    assert _evidence_unavailable(
        "=" * 70 + "\n  SIGN-IN ACTIVITY  (not available)\n" + "=" * 70 + "\n"
        "  auditLogs/signIns requires Entra ID P1, and Graph refused.\n"
    )


def test_an_error_stub_is_recognised_wherever_it_is_anchored():
    assert _evidence_unavailable("Error: HTTP 403\n")


@pytest.mark.parametrize("blank", ["", "   \n\n", None, 42])
def test_nothing_to_read_is_unavailable(blank):
    assert _evidence_unavailable(blank)


def test_a_finding_that_merely_mentions_the_word_is_still_a_finding():
    text = "\n".join(
        ["=" * 70, "  RISKY USERS", "=" * 70]
        + [f"  user{i}@acme.no  riskLevel: medium" for i in range(30)]
        + ["  admin@acme.no  Sign-in requires review by the security team"]
    )
    assert not _evidence_unavailable(text), (
        "one row saying 'requires' made the whole file read as unmeasured"
    )


def test_a_real_finding_list_keeps_its_penalty():
    text = "\n".join(
        ["=" * 70, "  RISKY USERS", "=" * 70]
        + [f"  user{i}@acme.no  riskLevel: high" for i in range(20)]
        + ["  admin@acme.no  this account requires immediate attention"]
    )
    assert _score(risky_users=text)["score"] < 100
