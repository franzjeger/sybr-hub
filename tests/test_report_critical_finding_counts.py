"""Two critical-finding penalties, counted from the collector's own header.

The score branched on the phrases "No risky" and "No active". No collector
writes either. They existed only in the test fixture, which had been written
to match the parser rather than the collector — so every test passed while the
real files went down the other branch.

What the collector actually writes is a header carrying the count:
``RISKY USERS  (0 total)``, ``DEFENDER ACTIVE ALERTS  (3 unresolved)``. The
score never looked at it. It counted rendered lines instead, which counted the
title and the column header as findings.

On a genuinely clean tenant that cost five points for having no risky users
and five more for having no Defender alerts — ten points, grade A to B, for
nothing being wrong. And because the two junk lines were counted every time,
one real alert scored one point worse than none.
"""

from __future__ import annotations

from app.reports.generator import _compute_risk, _reported_count

_R_COLS = f"  {'UPN':<50} {'Risk Level':<15} {'Risk State':<20} Last Updated"
_D_COLS = f"  {'Alert Title':<50} {'Severity':<12} {'Status':<15} Created"


def risky_file(*rows: str) -> str:
    return "\n".join([
        "=" * 90, f"  RISKY USERS  ({len(rows)} total)", "=" * 90,
        _R_COLS, "  " + "-" * 86, *rows, "=" * 90, "",
    ])


def defender_file(*rows: str) -> str:
    return "\n".join([
        "=" * 110, f"  DEFENDER ACTIVE ALERTS  ({len(rows)} unresolved)", "=" * 110,
        _D_COLS, "  " + "-" * 106, *rows, "=" * 110, "",
    ])


def _score(**kw) -> int:
    base = dict(
        secure_score={"has_data": True, "pct": 100},
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[], all_warns="", ext_fwd="",
        risky_users=risky_file(), defender=defender_file(),
        admin_roles={"has_data": True, "global_admin_count": 1},
        intune={"has_data": True, "total": 1, "compliance_pct": 100},
        sharepoint={"has_data": True}, oauth={"has_data": True},
        network=None, lang="no",
    )
    base.update(kw)
    return _compute_risk(**base)["score"]


# ── The header is the count ──────────────────────────────────────────────────

def test_a_clean_tenant_is_not_charged_for_being_clean():
    assert _score() == 100, (
        "the title line and the column header were counted as findings"
    )


def test_the_penalty_tracks_the_number_of_alerts():
    one = _score(defender=defender_file("  Malware on LAPTOP-07  high"))
    three = _score(defender=defender_file(
        "  Malware on LAPTOP-07      high",
        "  Suspicious sign-in        high",
        "  Mass download             medium",
    ))
    assert one < 100
    assert three < one, (
        f"three alerts must cost more than one; got {three} and {one}"
    )


def test_one_risky_user_costs_and_none_does_not():
    assert _score(risky_users=risky_file()) == 100
    assert _score(risky_users=risky_file("  user09@acme.no  high  atRisk")) < 100


def test_the_alert_penalty_is_still_capped():
    many = defender_file(*[f"  alert {i}  high" for i in range(50)])
    assert _score(defender=many) >= 90 - 1, "the cap of 10 points must hold"
    assert _score(defender=many) == 90


# ── The helper ───────────────────────────────────────────────────────────────

def test_it_reads_both_spellings():
    assert _reported_count("  RISKY USERS  (0 total)") == 0
    assert _reported_count("  DEFENDER ACTIVE ALERTS  (7 unresolved)") == 7


def test_no_header_means_no_answer():
    # A caller must be able to tell "the collector said zero" from "there is no
    # count here" — collapsing them is how zero became a penalty.
    assert _reported_count("No active alerts") is None
    assert _reported_count("") is None
    assert _reported_count(None) is None


def test_the_old_sentinels_still_work_where_they_appear():
    # Nothing writes these, but they are in older fixtures and stored runs.
    assert _score(defender="No active alerts", risky_users="No risky users") == 100
