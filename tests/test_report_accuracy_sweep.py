"""Recommendation and parser accuracy — the second-verdict-surface sweep.

The recommendations list and the numbers feeding the grade are the first thing a
customer reads. These regressions each made that surface lie: a finding that
never fired, a rec that named a remediated account as still-at-risk, a count
that disagreed with its own evidence file, or a threshold that tripped a seat
early. Each test below fails if its fix is reverted.
"""

from __future__ import annotations

from app.reports.generator import (
    _build_recommendations,
    _parse_licenses,
    _parse_signin_risk,
)

_MFA_CLEAN = {"has_data": True, "no_mfa": 0, "mfa_registered": 1, "ca_covered": 0, "users": []}


def _recs(**over):
    base = dict(
        mfa=_MFA_CLEAN, spf_dmarc=[], secure_score={}, ext_fwd="", risky_users="",
        licenses=[], file_contents={},
    )
    base.update(over)
    return _build_recommendations(**base)


# ── finding-email: every offending domain, and WEAK SPF too (F5/F14) ──────────

def test_dmarc_finding_is_emitted_for_every_offending_domain():
    recs = _recs(spf_dmarc=[{"domain": "a.no", "dmarc": "MISSING", "spf": "OK"},
                            {"domain": "b.no", "dmarc": "MISSING", "spf": "OK"}])
    domains = {r.get("title_params", {}).get("domain")
               for r in recs if r.get("title_key") == "rec_dmarc_title"}
    assert {"a.no", "b.no"} <= domains, "the break hid every domain after the first"


def test_weak_spf_produces_a_recommendation_to_match_the_grade():
    recs = _recs(spf_dmarc=[{"domain": "a.no", "spf": "WEAK (~all softfail)", "dmarc": "reject"}])
    assert any(r.get("title_key") == "rec_spf_title" for r in recs), \
        "the grade penalises WEAK SPF but raised no recommendation"


# ── finding-risky: only currently-at-risk users (F4) ──────────────────────────

def test_remediated_risky_users_are_not_listed_as_at_risk():
    risky = ("=" * 40 + "\n  RISKY USERS\n" + "=" * 40 + "\n"
             "atrisk@acme.no    high    atRisk\n"
             "fixed@acme.no     high    remediated\n")
    recs = _recs(risky_users=risky)
    named = " ".join(i for r in recs if r.get("finding_id") == "finding-risky"
                     for i in r.get("sub_items", []))
    assert "atrisk@acme.no" in named
    assert "fixed@acme.no" not in named, "a remediated account must not be listed as at risk"


# ── finding-stale: fires on the collector's real summary line (F6) ────────────

def test_finding_stale_fires_on_the_collector_summary_line():
    stale = ("=" * 40 + "\n  WARNING: LICENSED STALE ACCOUNTS\n" + "=" * 40 + "\n"
             "  7 enabled account(s) with licenses have not signed in for 90+ days (or never).\n")
    recs = _recs(file_contents={"03c_stale_accounts_WARN.txt": stale})
    stale_recs = [r for r in recs if r.get("finding_id") == "finding-stale"]
    assert len(stale_recs) == 1, "the regexes never matched the collector's line"
    assert stale_recs[0]["title_params"].get("count") == 7


# ── licences: warn boundary from the true ratio, not the rounded pct (F18) ────

def test_license_warn_uses_the_true_ratio_not_the_rounded_pct():
    # 179/200 = 89.5% (the collector prints "90%") — one seat below the warning.
    assert _parse_licenses("SPE_E5 179 200 90%\n")[0]["warn"] is False
    # 180/200 = 90.0% — exactly at the boundary, warns.
    assert _parse_licenses("SPE_E5 180 200 90%\n")[0]["warn"] is True


# ── brute-force: strict > 50 to match the evidence file (F16) ─────────────────

def test_brute_force_suspects_use_strict_greater_than_50():
    text = ("SIGN-IN FAILURES (last 30 days)\n" + "=" * 40 + "\n"
            "exactly50@acme.no | 50 | invalidUserNameOrPassword\n"
            "over50@acme.no | 51 | invalidUserNameOrPassword\n")
    suspects = _parse_signin_risk({"05b_signin_failures.txt": text})["brute_force_suspects"]
    assert "over50@acme.no" in suspects
    assert "exactly50@acme.no" not in suspects, \
        "50 is not > 50 — the finding disagreed with the evidence file's flag"
