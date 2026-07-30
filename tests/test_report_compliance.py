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


# ── CIS 4.4: the control read the wrong files, in both directions ─────────────


def _fwd_ctx(**files) -> dict:
    return {"mfa": {"has_data": True, "pct": 100.0, "no_mfa": 0}, "file_contents": files}


_FWD_CLEAN = (
    "MAILBOX FORWARDING\n"
    "==================\n"
    "No mailboxes with external forwarding configured.\n"
)


def test_the_unconditional_forwarding_file_is_not_evidence_of_forwarding():
    """28_exchange_mailbox_forwarding.txt is written on every run and is
    titled "MAILBOX FORWARDING", so `"forwarding" in text` was true for every
    tenant whose Exchange section ran — a guaranteed false positive on a
    control about an exfiltration path.
    """
    ctrl = _control(_build_compliance_map(_fwd_ctx(**{
        "28_exchange_mailbox_forwarding.txt": _FWD_CLEAN,
        "29_exchange_inbox_rules_external_fwd.txt": "INBOX RULES\n===========\nNone.\n",
    })), "4.4")
    assert ctrl["status"] == "pass"


def test_the_clean_inbox_rules_file_is_not_evidence_either():
    """The collector writes 29_..._WARN.txt when rules are found and the
    plain name when they are not, so the plain file is the all-clear.
    """
    ctrl = _control(_build_compliance_map(_fwd_ctx(**{
        "28_exchange_mailbox_forwarding.txt": _FWD_CLEAN,
        "29_exchange_inbox_rules_external_fwd.txt":
            "INBOX RULES WITH EXTERNAL FORWARDING\n====================================\nNone found.\n",
    })), "4.4")
    assert ctrl["status"] == "pass"


def test_real_external_forwarding_is_still_caught():
    """The WARN file is the one that carries the finding — and the old code
    never opened it, so a genuine detection relied on a substring accident.
    """
    ctrl = _control(_build_compliance_map(_fwd_ctx(**{
        "28_exchange_mailbox_forwarding.txt": _FWD_CLEAN,
        "28b_exchange_external_forwarding_WARN.txt":
            "EXTERNAL MAILBOX FORWARDING WARNING  (1 mailboxes)\n  ola@acme.no  →  ola@gmail.com\n",
    })), "4.4")
    assert ctrl["status"] == "warn"


def test_a_forwarding_inbox_rule_is_caught_from_its_warn_file():
    ctrl = _control(_build_compliance_map(_fwd_ctx(**{
        "28_exchange_mailbox_forwarding.txt": _FWD_CLEAN,
        "29_exchange_inbox_rules_external_fwd_WARN.txt":
            "INBOX RULES WITH EXTERNAL FORWARDING\n  Rule 'archive' → ext@example.com\n",
    })), "4.4")
    assert ctrl["status"] == "warn"


def test_no_forwarding_files_at_all_cannot_be_verified():
    assert _control(_build_compliance_map(_fwd_ctx()), "4.4")["status"] == "info"


# ── CIS 5.2.3: a DKIM lookup that did not run is not a missing record ─────────


def _dns_ctx(domain_entry: dict) -> dict:
    return {
        "mfa": {"has_data": True, "pct": 100.0, "no_mfa": 0},
        "spf_dmarc": [domain_entry],
        "file_contents": {},
    }


def test_a_domain_whose_dkim_was_never_looked_up_is_not_a_failure():
    """Per domain, so a multi-domain tenant collected a column of these."""
    ctrl = _control(_build_compliance_map(
        _dns_ctx({"domain": "acme.no", "spf": "OK", "dmarc": "OK"})
    ), "5.2.3")
    assert ctrl["status"] == "info"
    assert "No DKIM record found" not in ctrl["detail"]


def test_a_domain_checked_with_no_dkim_record_still_fails():
    ctrl = _control(_build_compliance_map(
        _dns_ctx({"domain": "acme.no", "spf": "OK", "dmarc": "OK", "dkim1": ""})
    ), "5.2.3")
    assert ctrl["status"] == "fail"


def test_a_domain_with_dkim_passes():
    ctrl = _control(_build_compliance_map(
        _dns_ctx({"domain": "acme.no", "spf": "OK", "dmarc": "OK",
                  "dkim1": "CNAME selector1._domainkey.acme.no OK"})
    ), "5.2.3")
    assert ctrl["status"] == "pass"


# ---------------------------------------------------------------------------
# A DNS lookup that failed is not a DNS record that is missing. The DNS
# section keeps them apart on purpose; 5.2.1 and 5.2.2 used to collapse both
# into a failed control, which reads as "configure SPF" for a domain that may
# already have it. 5.2.3 already guarded against this.
# ---------------------------------------------------------------------------

def _controls(spf_rows, cid):
    rows = _build_compliance_map({"spf_dmarc": spf_rows, "file_contents": {}})
    return [r for r in rows if r["cis_id"] == cid]


def test_spf_lookup_error_is_not_reported_as_missing():
    rows = _controls(
        [{"domain": "example.com", "spf": "ERROR (SERVFAIL)", "dmarc": "ERROR (SERVFAIL)"}],
        "5.2.1",
    )
    assert rows, "the control should still appear"
    assert rows[0]["status"] == "info"
    assert "Kan ikke verifiseres" in rows[0]["detail"]


def test_dmarc_lookup_error_is_not_reported_as_missing():
    rows = _controls(
        [{"domain": "example.com", "spf": "ERROR (SERVFAIL)", "dmarc": "ERROR (timeout)"}],
        "5.2.2",
    )
    assert rows[0]["status"] == "info"
    assert "Kan ikke verifiseres" in rows[0]["detail"]


def test_genuinely_missing_spf_still_fails():
    """The guard must not turn a real finding into a shrug."""
    rows = _controls([{"domain": "example.com", "spf": "MISSING", "dmarc": "MISSING"}], "5.2.1")
    assert rows[0]["status"] == "fail"


def test_valid_spf_still_passes():
    rows = _controls(
        [{"domain": "example.com", "spf": "OK (-all hardfail)", "dmarc": "OK (p=reject)"}],
        "5.2.1",
    )
    assert rows[0]["status"] == "pass"


# ---------------------------------------------------------------------------
# 8.1.2 used to read 16b_teams_settings.txt — a file holding messaging
# settings, every value N/A, and nothing about guests — and emit a permanent
# "info" claiming the settings had been fetched. It was the only control of
# the thirty that could never pass or fail.
# ---------------------------------------------------------------------------

def _guest(text):
    rows = _build_compliance_map({"file_contents": {"30b_teams_guest_access.txt": text}})
    return [r for r in rows if r["cis_id"] == "8.1.2"][0]


_GUEST_FILE = (
    "=" * 60 + "\n"
    "  TEAMS / ENTRA ID GUEST ACCESS SETTINGS\n"
    + "=" * 60 + "\n"
    "  Allow Invites From       : {invites}\n"
    "  Guest User Role          : {role}\n"
)


def test_everyone_can_invite_guests_is_a_failure():
    """Fonnafly's real setting. Previously invisible in the report."""
    c = _guest(_GUEST_FILE.format(invites="Everyone (most open)",
                                  role="Limited access (default)"))
    assert c["status"] == "fail"
    assert "gjester kan invitere flere gjester" in c["detail"]


def test_guests_with_member_access_fails_whatever_the_invite_setting():
    c = _guest(_GUEST_FILE.format(invites="No one (most restrictive)",
                                  role="Same as member users"))
    assert c["status"] == "fail"


def test_members_may_invite_is_a_warning_not_a_failure():
    c = _guest(_GUEST_FILE.format(invites="Admins, Guest Inviters, and Members",
                                  role="Limited access (default)"))
    assert c["status"] == "warn"


def test_restricted_invites_pass():
    c = _guest(_GUEST_FILE.format(invites="Admins and Guest Inviters",
                                  role="Restricted access (most restrictive)"))
    assert c["status"] == "pass"


def test_missing_guest_data_cannot_be_verified():
    c = _guest("")
    assert c["status"] == "info"
    assert "Kan ikke verifiseres" in c["detail"]


def test_na_values_count_as_missing_not_as_an_answer():
    """The old file's every field was N/A; that must not read as a verdict."""
    c = _guest(_GUEST_FILE.format(invites="N/A", role="N/A"))
    assert c["status"] == "info"


def test_the_control_can_actually_reach_a_verdict():
    """Guards the property that was wrong: it was info-only."""
    import re, pathlib
    src = pathlib.Path("app/reports/generator.py").read_text()
    i = src.find("def _build_compliance_map")
    body = src[i:src.find("\ndef ", i + 10)]
    statuses = {
        st for cid, st in
        re.findall(r'add\(\s*"([^"]+)"[^)]*?"(pass|warn|fail|info|partial)"', body, re.S)
        if cid == "8.1.2"
    }
    assert statuses != {"info"}, "8.1.2 must be able to pass or fail, not only shrug"


# ---------------------------------------------------------------------------
# The compliance percentage excludes controls that could not be assessed.
# That is the right arithmetic, but both reports printed the rate without the
# basis, so a reader had no way to tell 94% of 30 from 94% of 17.
# ---------------------------------------------------------------------------

def test_unassessed_count_reaches_the_template_context(tmp_path):
    from app.reports.generator import build_report_context

    ctx = build_report_context("Tom Tenant", "tom.example", tmp_path, [])
    assert "compliance_info" in ctx, "the reports cannot show what they never receive"
    assert ctx["compliance_info"] >= 1, "an empty audit assesses nothing"
    assert ctx["compliance_assessed"] + ctx["compliance_info"] == ctx["compliance_total"]


def test_the_percentage_is_taken_over_the_assessed_controls(tmp_path):
    from app.reports.generator import build_report_context

    ctx = build_report_context("Tom Tenant", "tom.example", tmp_path, [])
    if ctx["compliance_assessed"]:
        expected = round(ctx["compliance_pass"] / ctx["compliance_assessed"] * 100, 0)
        assert ctx["compliance_pct"] == expected
