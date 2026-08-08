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


# ---------------------------------------------------------------------------
# Every CIS verdict names the collected file it was formed from. The report
# already carries all 72 files, but nothing said which one backed a given
# control, so checking a verdict meant reading the generator.
# ---------------------------------------------------------------------------

def test_every_control_declares_where_its_verdict_comes_from():
    from app.reports.generator import _EVIDENCE_MAP, _build_compliance_map

    produced = {c["cis_id"] for c in _build_compliance_map({"file_contents": {}})}
    undeclared = sorted(produced - set(_EVIDENCE_MAP))
    assert not undeclared, f"controls with no evidence source: {undeclared}"


def test_every_named_file_is_one_a_collector_actually_writes():
    """Guards against drift: a link to a file no run produces is worse than none."""
    import pathlib
    from app.reports.generator import _EVIDENCE_MAP

    written = " ".join(
        p.read_text() for p in pathlib.Path("app/modules").rglob("*.py")
    )
    missing = sorted({
        f for files in _EVIDENCE_MAP.values() for f in files if f not in written
    })
    assert not missing, f"evidence files no collector writes: {missing}"


def test_evidence_lists_only_files_this_run_collected():
    """A link into the appendix must land on a section that is there."""
    from app.reports.generator import _build_compliance_map

    fc = {"30b_teams_guest_access.txt": "  Allow Invites From       : Everyone (most open)\n"}
    rows = _build_compliance_map({"file_contents": fc})
    for r in rows:
        for f in r["evidence"]:
            assert f in fc, f"{r['cis_id']} points at {f}, which this run has not got"


def test_the_guest_control_points_at_the_file_it_reads():
    from app.reports.generator import _build_compliance_map

    fc = {"30b_teams_guest_access.txt": "  Allow Invites From       : Everyone (most open)\n"}
    row = [r for r in _build_compliance_map({"file_contents": fc}) if r["cis_id"] == "8.1.2"][0]
    assert row["evidence"] == ["30b_teams_guest_access.txt"]


# ---------------------------------------------------------------------------
# 5.1.1 claimed to check that legacy authentication was blocked, and measured
# SharePoint's legacy-protocol flag instead. Two different settings on two
# different services — and nothing anywhere checked the Entra side.
# ---------------------------------------------------------------------------

def _ca(*policies):
    """Build a section file in the collector's own format."""
    lines = ["=" * 120, "  CONDITIONAL ACCESS POLICIES", "=" * 120,
             "  State        Policy Name      Users   Groups   Apps", "  " + "-" * 116]
    for state, name, grants, apps in policies:
        lines.append(f"  [{state:<10}] {name:<45} All  -  All")
        lines.append(f"               Grant controls: {grants}")
        lines.append(f"               Client apps: {apps}")
    return "\n".join(lines) + "\n"


def _ctrl(fc, cid):
    """Parse the files the way build_report_context does, then grade."""
    from app.reports.generator import (
        _build_compliance_map, _parse_ca_policies, _parse_sharepoint_settings,
    )
    ctx = {
        "file_contents": fc,
        "ca": _parse_ca_policies(fc.get("08_conditional_access.txt", "")),
        "sharepoint": _parse_sharepoint_settings(
            fc.get("15b_sharepoint_settings.txt", ""), fc.get("15_sharepoint_sites.txt", "")),
    }
    rows = [r for r in _build_compliance_map(ctx) if r["cis_id"] == cid]
    assert rows, f"{cid} missing"
    return rows[0]


def test_legacy_auth_block_recognised_from_client_app_scope():
    fc = {"08_conditional_access.txt": _ca(
        ("enabled", "Block legacy authentication", "block", "exchangeActiveSync, other"))}
    assert _ctrl(fc, "5.1.1")["status"] == "pass"


def test_no_legacy_block_is_a_failure():
    fc = {"08_conditional_access.txt": _ca(
        ("enabled", "All users require MFA", "mfa", "all"))}
    assert _ctrl(fc, "5.1.1")["status"] == "fail"


def test_a_disabled_legacy_policy_does_not_count():
    fc = {"08_conditional_access.txt": _ca(
        ("disabled", "Block legacy authentication", "block", "exchangeActiveSync, other"))}
    assert _ctrl(fc, "5.1.1")["status"] == "fail"


def test_the_name_alone_proves_nothing():
    """A policy named for the job but scoped to all clients and granting MFA."""
    fc = {"08_conditional_access.txt": _ca(
        ("enabled", "Block legacy authentication", "mfa", "all"))}
    assert _ctrl(fc, "5.1.1")["status"] == "fail"


def test_audit_without_client_app_scope_cannot_be_verified():
    """Older output has no "Client apps:" line; that is not a failure."""
    old = ("=" * 120 + "\n  CONDITIONAL ACCESS POLICIES\n" + "=" * 120 + "\n"
           "  [enabled   ] Block legacy authentication   All  -  All\n"
           "               Grant controls: block\n")
    assert _ctrl({"08_conditional_access.txt": old}, "5.1.1")["status"] == "info"


def test_sharepoint_legacy_protocols_kept_as_their_own_control():
    fc = {"15b_sharepoint_settings.txt": "  Legacy Auth: true\n  Sharing: ExternalUserSharingOnly\n"}
    row = _ctrl(fc, "7.2.3")
    assert row["status"] == "fail"
    assert row["evidence"] == ["15b_sharepoint_settings.txt"]


def test_the_two_controls_read_different_files():
    from app.reports.generator import _EVIDENCE_MAP
    assert _EVIDENCE_MAP["5.1.1"] == ("08_conditional_access.txt",)
    assert _EVIDENCE_MAP["7.2.3"] == ("15b_sharepoint_settings.txt",)


def test_a_broad_block_policy_is_not_a_legacy_auth_block():
    """Scoped to every client app, so it is some other policy entirely.

    This is the case that decides whether the verdict reads the client-app
    scope at all; without it a mutation removing that check passed the suite.
    """
    fc = {"08_conditional_access.txt": _ca(("enabled", "Block all access", "block", "all"))}
    assert _ctrl(fc, "5.1.1")["status"] == "fail"


def test_legacy_scope_without_a_denying_grant_is_a_failure():
    """Legacy clients targeted, but the policy only demands a compliant device.

    Pairs with the test above: this one decides whether the grant control is
    read. A mutation ignoring it passed the suite until this existed.
    """
    fc = {"08_conditional_access.txt": _ca(
        ("enabled", "Legacy clients", "compliantDevice", "exchangeActiveSync, other"))}
    assert _ctrl(fc, "5.1.1")["status"] == "fail"


def test_requiring_mfa_of_legacy_clients_counts_as_blocking():
    """The older way of writing it, and it does close the hole.

    Legacy protocols cannot perform a second factor, so the grant can never be
    satisfied. Failing such a tenant would be a false finding.
    """
    fc = {"08_conditional_access.txt": _ca(
        ("enabled", "Legacy auth requires MFA", "mfa", "exchangeActiveSync, other"))}
    assert _ctrl(fc, "5.1.1")["status"] == "pass"


# ---------------------------------------------------------------------------
# Three files the collectors had written since the sections existed, and no
# parser ever read. Their signals are unambiguous, so they are now graded.
# ---------------------------------------------------------------------------

def _grade(fc, cid, **ctx):
    from app.reports.generator import _build_compliance_map
    rows = [c for c in _build_compliance_map({"file_contents": fc, **ctx}) if c["cis_id"] == cid]
    assert rows, f"{cid} missing"
    return rows[0]


SD_ON = "  SMART LOCKOUT & SECURITY DEFAULTS\n  Security Defaults Enabled       : True\n"
SD_OFF = "  SMART LOCKOUT & SECURITY DEFAULTS\n  Security Defaults Enabled       : False\n"


def test_security_defaults_on_is_baseline_protection():
    assert _grade({"31b_smart_lockout.txt": SD_ON}, "1.1.7")["status"] == "pass"


def test_security_defaults_off_with_conditional_access_is_the_recommended_state():
    """Turning them off is correct once CA is in place, so the flag alone
    cannot decide this."""
    row = _grade({"31b_smart_lockout.txt": SD_OFF}, "1.1.7",
                 ca={"has_data": True, "enabled": 4})
    assert row["status"] == "pass"


def test_security_defaults_off_with_no_conditional_access_is_a_failure():
    row = _grade({"31b_smart_lockout.txt": SD_OFF}, "1.1.7",
                 ca={"has_data": True, "enabled": 0})
    assert row["status"] == "fail"


def test_security_defaults_unreadable_is_not_a_verdict():
    assert _grade({"31b_smart_lockout.txt": "  NOTE: nothing here\n"}, "1.1.7")["status"] == "info"


def test_access_reviews_absent_without_p2_describes_the_licence():
    """Access reviews need Entra ID P2; failing a tenant that cannot buy the
    feature is a finding about the price list, not the configuration."""
    fc = {"07d_access_reviews.txt": "  ACCESS REVIEW DEFINITIONS  (0 total)\n"}
    row = _grade(fc, "1.1.8", licenses=[{"part": "SPB", "used": 40, "total": 40}])
    assert row["status"] == "info"
    assert "P2" in row["detail"]


def test_access_reviews_absent_with_p2_is_a_real_gap():
    fc = {"07d_access_reviews.txt": "  ACCESS REVIEW DEFINITIONS  (0 total)\n"}
    row = _grade(fc, "1.1.8", licenses=[{"part": "AAD_PREMIUM_P2", "used": 5, "total": 10}])
    assert row["status"] == "warn"


def test_access_reviews_present_passes():
    fc = {"07d_access_reviews.txt": "  ACCESS REVIEW DEFINITIONS  (2 total)\n"}
    assert _grade(fc, "1.1.8", licenses=[{"part": "AAD_PREMIUM_P2", "used": 5, "total": 10}])["status"] == "pass"


def test_anonymous_links_are_a_finding_whatever_the_tenant_setting():
    fc = {"25_onedrive_sharing.txt": "  Drives scanned : 3\n  'Anyone' links       : 2\n"}
    row = _grade(fc, "7.2.4")
    assert row["status"] == "fail"
    assert "2" in row["detail"]


def _onedrive_evidence(anyone=0, refused=0, discovery=0, folders=0, scope="complete"):
    return {"25_onedrive_sharing.txt": (
        "  Drives scanned       : 12\n"
        f"  'Anyone' links       : {anyone}\n"
        f"  Drives refused       : {refused}\n"
        f"  Discovery failures   : {discovery}\n"
        f"  Folder failures      : {folders}\n"
        f"  Scan scope           : {scope} (depth 3)\n"
    )}


def test_no_anonymous_links_passes_only_for_a_complete_scan():
    row = _grade(_onedrive_evidence(), "7.2.4")
    assert row["status"] == "pass"
    assert "12" in row["detail"]


@pytest.mark.parametrize("evidence", [
    _onedrive_evidence(refused=1),
    _onedrive_evidence(discovery=1),
    _onedrive_evidence(folders=1),
    _onedrive_evidence(scope="partial"),
])
def test_a_clean_verdict_is_held_back_by_any_coverage_gap(evidence):
    assert _grade(evidence, "7.2.4")["status"] == "info"


def test_a_finding_still_fails_on_a_partial_scan():
    assert _grade(_onedrive_evidence(anyone=2, refused=1), "7.2.4")["status"] == "fail"


def test_legacy_output_without_coverage_is_not_a_pass():
    fc = {"25_onedrive_sharing.txt": "  Drives scanned : 1\n  'Anyone' links       : 0\n"}
    assert _grade(fc, "7.2.4")["status"] == "info"


def test_missing_onedrive_data_is_not_a_pass():
    assert _grade({}, "7.2.4")["status"] == "info"


def test_security_defaults_off_with_no_ca_data_is_not_a_failure():
    """Absence of the CA file must not manufacture a finding.

    Whether Security Defaults being off is acceptable depends entirely on
    what Conditional Access is doing. With that file missing there is no
    verdict to give — the first version of this control called it a failure,
    which the partial-audit test caught.
    """
    row = _grade({"31b_smart_lockout.txt": SD_OFF}, "1.1.7")   # no ca in context
    assert row["status"] == "info"


# ---------------------------------------------------------------------------
# Cross-tenant access. Allowed B2B collaboration is how most organisations
# work; grading it as a failure would tell a customer to break their own
# collaboration. Only two things here are worth saying.
# ---------------------------------------------------------------------------

def _xt(dc_in="blocked", service_default="false", inbound="allowed"):
    return {"18c_cross_tenant_access_policy.txt": (
        "=" * 70 + "\n  CROSS-TENANT ACCESS POLICY\n" + "=" * 70 + "\n"
        "  Default Settings:\n"
        f"    B2B Collab Inbound     : {inbound}\n"
        f"    B2B Collab Outbound    : allowed\n"
        f"    B2B Direct Connect In  : {dc_in}\n"
        f"    System Default         : {service_default}\n"
        + "=" * 70 + "\n"
    )}


def test_allowed_b2b_collaboration_is_not_a_finding():
    """It is normal and required; the control must not punish it."""
    row = _grade(_xt(inbound="allowed"), "1.1.9")
    assert row["status"] == "pass"


def test_direct_connect_inbound_is_flagged():
    row = _grade(_xt(dc_in="allowed"), "1.1.9")
    assert row["status"] == "warn"
    assert "direct connect" in row["detail"].lower()


def test_a_tenant_still_on_the_system_default_has_not_decided():
    row = _grade(_xt(service_default="true"), "1.1.9")
    assert row["status"] == "warn"
    assert "systemstandard" in row["detail"].lower()


def test_direct_connect_outranks_the_system_default_notice():
    """Both apply; the specific exposure is the one to lead with."""
    row = _grade(_xt(dc_in="allowed", service_default="true"), "1.1.9")
    assert "direct connect" in row["detail"].lower()


def test_missing_cross_tenant_data_is_not_a_verdict():
    assert _grade({}, "1.1.9")["status"] == "info"


def test_the_old_all_na_output_reads_as_unverifiable():
    """What every tenant produced before the collector was pointed at the
    right endpoint. It must not be graded as a configured state."""
    old = {"18c_cross_tenant_access_policy.txt": (
        "  CROSS-TENANT ACCESS POLICY\n  Default Settings:\n"
        "    B2B Collab Inbound  : N/A\n    B2B Collab Outbound : N/A\n"
    )}
    assert _grade(old, "1.1.9")["status"] == "info"
