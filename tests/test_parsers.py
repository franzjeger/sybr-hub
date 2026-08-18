"""Tests for parser functions in app.reports.generator."""

from __future__ import annotations

from app.reports.generator import (
    _FRAMEWORK_MAP,
    _analyze_license_optimization,
    _build_compliance_map,
    _build_recommendations,
    _compute_risk,
    _count_data_lines,
    _is_audit_relevant_domain,
    _parse_groups,
    _parse_licenses,
    _parse_mfa,
    _parse_spf_dmarc,
    _parse_user_counts,
)

# ---------------------------------------------------------------------------
# _parse_user_counts
# ---------------------------------------------------------------------------

class TestParseUserCounts:
    SAMPLE = """\
=== User Statistics ===
Total users      : 45
Enabled          : 40
Disabled         : 5
Guest accounts   : 8
Hybrid (synced)  : 30
Cloud-only       : 10
"""

    def test_parses_all_fields(self):
        result = _parse_user_counts(self.SAMPLE)
        assert result["total"] == 45
        assert result["enabled"] == 40
        assert result["disabled"] == 5
        assert result["guests"] == 8
        assert result["hybrid"] == 30
        assert result["cloud"] == 10

    def test_empty_input(self):
        result = _parse_user_counts("")
        assert result["total"] == 0
        assert result["enabled"] == 0

    def test_partial_input(self):
        result = _parse_user_counts("Total users : 12\n")
        assert result["total"] == 12
        assert result["enabled"] == 0


# ---------------------------------------------------------------------------
# _parse_mfa
# ---------------------------------------------------------------------------

class TestParseMfa:
    PIPE_DATA = """\
=== MFA Methods Report ===
Display Name | UPN | MFA Status | CA Status
Alice Admin | alice@contoso.com | MFA:YES | CA:YES | Methods: Authenticator
Bob User | bob@contoso.com | MFA:NO | CA:YES | EXCL:NO | Methods: (none)
Carol Guest | carol@external.com | MFA:NO | CA:NO | Methods: (none)
"""

    def test_pipe_format_totals(self):
        result = _parse_mfa(self.PIPE_DATA, "", [])
        assert result["total"] == 3
        assert result["mfa_registered"] == 1  # Alice
        assert result["covered"] == 2  # Alice (MFA) + Bob (CA, not excluded)
        assert result["no_mfa"] == 1  # Carol

    def test_pipe_format_percentages(self):
        result = _parse_mfa(self.PIPE_DATA, "", [])
        assert result["pct"] == 66.7  # 2/3

    def test_unprotected_count(self):
        result = _parse_mfa(self.PIPE_DATA, "", [])
        assert result["fully_unprotected"] == 1  # Carol

    def test_empty_input(self):
        result = _parse_mfa("", "", [])
        assert result["total"] == 0
        assert result["pct"] == 0

    def test_user_details_populated(self):
        result = _parse_mfa(self.PIPE_DATA, "", [])
        assert len(result["users"]) == 3
        alice = result["users"][0]
        assert alice["name"] == "Alice Admin"
        assert alice["has_mfa"] is True
        assert alice["protected"] is True

    COLUMNAR_DATA = """\
=== MFA Methods Report ===
Display Name          UPN                    MFA   CA    EXCL
Dave Director         dave@contoso.com       YES   YES   NO
Eve Employee          eve@contoso.com        NO    NO    NO
"""

    def test_columnar_format(self):
        result = _parse_mfa(self.COLUMNAR_DATA, "", [])
        assert result["total"] == 2
        assert result["mfa_registered"] == 1
        assert result["covered"] == 1


# ---------------------------------------------------------------------------
# _parse_licenses
# ---------------------------------------------------------------------------

class TestParseLicenses:
    SAMPLE = """\
=== License Summary ===
License Name                Used  Total  Utilization
Microsoft 365 Business      45    50     90%
Exchange Online Plan 1      10    100    10%
Power BI Pro                5     5      100%*
"""

    def test_parses_licenses(self):
        result = _parse_licenses(self.SAMPLE)
        assert len(result) == 3

    def test_license_fields(self):
        result = _parse_licenses(self.SAMPLE)
        m365 = result[0]
        assert m365["part"] == "Microsoft 365 Business"
        assert m365["used"] == 45
        assert m365["total"] == 50
        assert m365["pct"] == 90.0
        assert m365["warn"] is True

    def test_low_utilization_no_warning(self):
        result = _parse_licenses(self.SAMPLE)
        exchange = result[1]
        assert exchange["warn"] is False

    def test_star_stripped_from_percent(self):
        result = _parse_licenses(self.SAMPLE)
        pbi = result[2]
        assert pbi["pct"] == 100.0

    def test_empty_input(self):
        assert _parse_licenses("") == []


# ---------------------------------------------------------------------------
# _parse_spf_dmarc
# ---------------------------------------------------------------------------

class TestParseSpfDmarc:
    SAMPLE = """\
Domain : contoso.com
  SPF   : v=spf1 include:spf.protection.outlook.com -all
  DMARC : v=DMARC1; p=reject; rua=mailto:dmarc@contoso.com
  DKIM sel1 : CNAME found
  DKIM sel2 : CNAME found
  MTA-STS   : enforce

Domain : fabrikam.com
  SPF   : v=spf1 include:spf.protection.outlook.com ~all
  DMARC : none
"""

    def test_parses_two_domains(self):
        result = _parse_spf_dmarc(self.SAMPLE)
        assert len(result) == 2

    def test_first_domain_fields(self):
        result = _parse_spf_dmarc(self.SAMPLE)
        d = result[0]
        assert d["domain"] == "contoso.com"
        assert "spf1" in d["spf"]
        assert "reject" in d["dmarc"]
        assert d["dkim1"] == "CNAME found"
        assert d["dkim2"] == "CNAME found"
        assert d["mta_sts"] == "enforce"

    def test_second_domain_missing_optional_fields(self):
        result = _parse_spf_dmarc(self.SAMPLE)
        d = result[1]
        assert d["domain"] == "fabrikam.com"
        assert "dkim1" not in d  # not present in input

    def test_empty_input(self):
        assert _parse_spf_dmarc("") == []


# ---------------------------------------------------------------------------
# _is_audit_relevant_domain
# ---------------------------------------------------------------------------

class TestIsAuditRelevantDomain:
    def test_real_domain_is_relevant(self):
        assert _is_audit_relevant_domain("contoso.com") is True

    def test_onmicrosoft_excluded(self):
        assert _is_audit_relevant_domain("contoso.onmicrosoft.com") is False

    def test_mail_onmicrosoft_excluded(self):
        assert _is_audit_relevant_domain("contoso.mail.onmicrosoft.com") is False

    def test_sharepoint_excluded(self):
        assert _is_audit_relevant_domain("contoso.sharepoint.com") is False

    def test_mimecast_excluded(self):
        assert _is_audit_relevant_domain("gateway.mimecast.com") is False

    def test_case_insensitive(self):
        assert _is_audit_relevant_domain("CONTOSO.ONMICROSOFT.COM") is False

    def test_proofpoint_excluded(self):
        assert _is_audit_relevant_domain("mail.pphosted.com") is False


# ---------------------------------------------------------------------------
# _compute_risk — must refuse to grade when essential inputs are missing.
# Locked in after a real audit produced "B / 70" for a tenant whose user
# enumeration had failed (User.Read.All consent missing).
# ---------------------------------------------------------------------------

class TestComputeRiskDataGaps:
    def _good_inputs(self):
        return {
            "secure_score": {"has_data": True, "pct": 80},
            "mfa": {"has_data": True, "pct": 100, "no_mfa": 0},
            "spf_dmarc": [],
            "all_warns": [],
            "ext_fwd": "",
            "risky_users": "No risky users",
            "defender": "No active alerts",
        }

    def test_grade_invalid_when_mfa_data_missing(self):
        args = self._good_inputs()
        args["mfa"] = {"has_data": False}
        result = _compute_risk(**args)
        assert result["grade"] == "?"
        assert result["score"] is None
        assert result["has_full_data"] is False
        assert any("MFA" in g for g in result["blocking_data_gaps"])

    def test_grade_assigned_when_data_complete(self):
        result = _compute_risk(**self._good_inputs())
        assert result["grade"] in {"A", "B", "C", "D", "F"}
        assert isinstance(result["score"], int)
        assert result["blocking_data_gaps"] == []

    def test_secure_score_missing_alone_does_not_invalidate(self):
        # Secure Score is only 20/100 weight — its absence is a data-quality
        # warning but should not blank the grade.
        args = self._good_inputs()
        args["secure_score"] = {"has_data": False}
        result = _compute_risk(**args)
        assert result["grade"] != "?"
        assert result["score"] is not None
        assert any("Secure Score" in g for g in result["data_quality_issues"])


# ---------------------------------------------------------------------------
# _parse_user_counts.has_data — empty file (audit aborted) must not be
# rendered as "0 users" in the report.
# ---------------------------------------------------------------------------

class TestUserCountsHasData:
    def test_empty_file_marks_no_data(self):
        result = _parse_user_counts("")
        assert result["has_data"] is False
        assert result["total"] == 0

    def test_populated_file_marks_has_data(self):
        sample = "Total users: 45\nEnabled: 40\nDisabled: 5\n"
        result = _parse_user_counts(sample)
        assert result["has_data"] is True
        assert result["total"] == 45


# ---------------------------------------------------------------------------
# _analyze_license_optimization.no_data_reason — distinguish "audit didn't
# collect this" from "tenant lacks P1" so we don't blame licensing falsely.
# ---------------------------------------------------------------------------

class TestLicenseOptimizationNoDataReason:
    def test_missing_file_reports_not_collected(self):
        # Empty/missing 03b_stale_accounts.txt → audit didn't run this check
        result = _analyze_license_optimization([], {"03b_stale_accounts.txt": ""})
        assert result["has_data"] is False
        assert result["no_data_reason"] == "not_collected"

    def test_p1_note_reports_license_p1_missing(self):
        note_text = (
            "STALE ACCOUNT DETECTION\n"
            "  NOTE: signInActivity data is null for all users. "
            "This field requires at minimum an Azure AD Premium P1 license.\n"
        )
        result = _analyze_license_optimization(
            [], {"03b_stale_accounts.txt": note_text}
        )
        assert result["has_data"] is False
        assert result["no_data_reason"] == "license_p1_missing"

    def test_real_data_reports_no_reason(self):
        real_text = (
            "STALE ACCOUNT DETECTION\n"
            "  Stale accounts found: 0\n"
        )
        result = _analyze_license_optimization(
            [], {"03b_stale_accounts.txt": real_text}
        )
        assert result["has_data"] is True
        assert result["no_data_reason"] is None


# ---------------------------------------------------------------------------
# _analyze_license_optimization shared/room mailboxes — a shared mailbox never
# signs in by design, so a licensed one reads as a "stale account". Counting it
# as an inactive *user* to deprovision is false advice (you would break mail
# flow) and inflates the kr/mnd estimate. It gets its own, correctly framed
# finding instead: a shared mailbox under 50 GB needs no licence.
# ---------------------------------------------------------------------------

class TestLicenseOptimizationSharedMailbox:
    _STALE = (
        "STALE ACCOUNT DETECTION\n"
        "  Display Name          UPN                    Last Sign-In    Days   Licensed\n"
        "  ------------------------------------------------------------------------\n"
        "  Kari Nordmann         kari@acme.no           2025-01-01      120    Yes\n"
        "  Felles Support        support@acme.no        Never           400    Yes\n"
    )
    _MAILBOXES = (
        "====\n"
        "  EXCHANGE MAILBOXES  (2 total)\n"
        "====\n"
        "  Display Name          UPN               Type            Quota\n"
        "  ----\n"
        "  Kari Nordmann         kari@acme.no      UserMailbox     1.2 GB\n"
        "  Felles Support        support@acme.no   SharedMailbox   5 GB\n"
    )

    def test_shared_mailbox_is_not_counted_as_an_inactive_user(self):
        result = _analyze_license_optimization(
            [],
            {"03b_stale_accounts.txt": self._STALE,
             "20_exchange_mailboxes.txt": self._MAILBOXES},
        )
        # The real inactive user is the only "remove licence from inactive user".
        upns = {u["upn"] for u in result["unused_licenses"]}
        assert upns == {"kari@acme.no"}, "a shared mailbox is not an inactive user"

        types = {s["type"] for s in result["optimization_suggestions"]}
        assert "unused" in types
        # The licensed shared mailbox is flagged separately, not silently dropped.
        assert "shared_mailbox_licensed" in types
        shared = next(s for s in result["optimization_suggestions"]
                      if s["type"] == "shared_mailbox_licensed")
        assert shared["savings"] > 0

    def test_without_the_mailbox_file_the_split_cannot_be_made(self):
        """The join is what separates the two. Absent the Exchange evidence a
        licensed shared mailbox can only be read as any other stale licensed
        account — so the fix must not fabricate the classification from nothing.
        """
        result = _analyze_license_optimization(
            [], {"03b_stale_accounts.txt": self._STALE},
        )
        upns = {u["upn"] for u in result["unused_licenses"]}
        assert upns == {"kari@acme.no", "support@acme.no"}
        types = {s["type"] for s in result["optimization_suggestions"]}
        assert "shared_mailbox_licensed" not in types


# ---------------------------------------------------------------------------
# Regression: parsers must match what the collectors actually write.
# Pre-v10.10.3 these silently produced "0 groups" / "0 licenses with high
# utilisation" because parser and collector disagreed on format.
# ---------------------------------------------------------------------------


class TestParseGroupsMatchesCollectorFormat:
    """The collector at app/modules/m365_audit/sections/groups_roles.py writes
    columnar rows: `Name  Type  Members`. The parser used to expect pipes
    only, so every group was silently dropped from the report."""

    SAMPLE = (
        "================================================================================\n"
        "  GROUPS  (3 total)\n"
        "================================================================================\n"
        "  Group Name                                       Type             Members\n"
        "  ----------------------------------------------------------------------------\n"
        "  Sales Team                                       Microsoft 365         25\n"
        "  Engineering                                      Security              42\n"
        "  Dynamic All Users                                Dynamic              N/A\n"
        "================================================================================\n"
    )

    def test_columnar_groups_are_parsed(self):
        result = _parse_groups(self.SAMPLE)
        assert result["total"] == 3
        assert result["has_data"] is True
        names = {g["name"] for g in result["groups"]}
        assert names == {"Sales Team", "Engineering", "Dynamic All Users"}

    def test_member_counts_are_correct(self):
        result = _parse_groups(self.SAMPLE)
        by_name = {g["name"]: g for g in result["groups"]}
        assert by_name["Sales Team"]["members"] == 25
        assert by_name["Engineering"]["members"] == 42

    def test_unknown_member_count_not_treated_as_empty(self):
        """A 'N/A' member count means the fetch failed, not that the group
        is empty. Reporting it as 'empty group' would be a false finding."""
        result = _parse_groups(self.SAMPLE)
        assert result["empty_groups"] == 0  # 'Dynamic All Users' has N/A, not 0

    def test_group_type_with_internal_space_preserved(self):
        """'Microsoft 365' is a single type with a space in it — the
        columnar parser must rejoin the middle columns."""
        result = _parse_groups(self.SAMPLE)
        by_name = {g["name"]: g for g in result["groups"]}
        assert by_name["Sales Team"]["type"] == "Microsoft 365"

    def test_legacy_pipe_format_still_parses(self):
        legacy = "Old Team | Microsoft 365 | 12\n"
        result = _parse_groups(legacy)
        assert result["total"] == 1
        assert result["groups"][0]["members"] == 12


class TestParseLicensesOverUtilisation:
    """The collector at app/modules/m365_audit/sections/licenses.py appends
    '  *** OVER 90% ***' to lines with ≥90% utilisation. The parser used
    rsplit which then grabbed 'OVER'/'90%'/'***' as fields and silently
    dropped the row — precisely the rows the auditor most cares about."""

    def test_over_90_percent_license_is_not_dropped(self):
        sample = (
            "  SKU / Part Number                          Used  Total    Pct  Status\n"
            "  ----------------------------------------------------------------------\n"
            "  SPE_E3                                     190    200    95%  *** OVER 90% ***\n"
        )
        result = _parse_licenses(sample)
        assert len(result) == 1
        assert result[0]["part"] == "SPE_E3"
        assert result[0]["used"] == 190
        assert result[0]["total"] == 200
        assert result[0]["pct"] == 95.0
        assert result[0]["warn"] is True

    def test_under_90_percent_license_still_parsed(self):
        sample = "  SPE_E1   50  100   50%\n"
        result = _parse_licenses(sample)
        assert len(result) == 1
        assert result[0]["warn"] is False


class TestComputeRiskAdminRolesDataGap:
    """admin_roles fetch failure used to score as '0 admins, no penalty'.
    A tenant with 8 Global Admins whose audit can't reach Graph would have
    received the same score as one with no admins at all — silent
    misclassification."""

    _MFA_OK = {
        "has_data": True, "pct": 100, "no_mfa": 0, "covered": 10, "total": 10,
    }
    _SS_OK = {"has_data": True, "pct": 80, "current": 80, "max": 100}

    def test_admin_roles_missing_flagged_as_data_quality_issue(self):
        admin_roles = {
            "roles": [], "global_admin_count": 0, "global_admin_users": [],
            "total_assignments": 0, "unique_roles": 0, "role_summary": [],
            "has_data": False,
        }
        risk = _compute_risk(
            self._SS_OK, self._MFA_OK, [], [], "", "", "",
            admin_roles=admin_roles,
        )
        assert any("Admin-roller" in issue for issue in risk["data_quality_issues"])

    def test_admin_roles_present_with_few_admins_no_issue(self):
        admin_roles = {
            "roles": [{"role": "Global Administrator", "user": "X", "email": "x@y"}],
            "global_admin_count": 1, "global_admin_users": [],
            "total_assignments": 1, "unique_roles": 1, "role_summary": [],
            "has_data": True,
        }
        risk = _compute_risk(
            self._SS_OK, self._MFA_OK, [], [], "", "", "",
            admin_roles=admin_roles,
        )
        assert not any("Admin-roller" in issue for issue in risk["data_quality_issues"])


# ---------------------------------------------------------------------------
# Regression: recommendations must be grounded in real findings, not in
# "the file exists". An empty/header-only file used to surface bare
# "Risky users detected" lines and inflated credential counts.
# ---------------------------------------------------------------------------


class TestRiskyUsersRecommendationGrounding:
    """The risky-users recommendation used to fire whenever the file had
    content — even if the only content was the header. That produced an
    empty 'Risky users detected' card with no count and no list, which
    is unfalsifiable and looks alarmist to the customer."""

    _BASE_KW = dict(
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 80, "current": 80, "max": 100,
                      "improvements": []},
        ext_fwd="",
        licenses=[],
        admin_roles=None,
        intune=None,
        sharepoint=None,
        oauth=None,
        azure=None,
        file_contents={},
    )

    def test_header_only_risky_users_file_does_not_emit_rec(self):
        # Collector header without any data rows
        header_only = (
            "==========================================================\n"
            "  RISKY USERS  (0 total)\n"
            "==========================================================\n"
            "  UPN                                                Risk Level\n"
            "  --------------------------------------------------------\n"
            "==========================================================\n"
        )
        recs = _build_recommendations(risky_users=header_only, **self._BASE_KW)
        assert not any(r.get("finding_id") == "finding-risky" for r in recs), \
            "risky-users rec should not fire when no rows were parsed"

    def test_parsed_risky_users_do_emit_rec(self):
        with_rows = (
            "==========================================================\n"
            "  RISKY USERS  (2 total)\n"
            "==========================================================\n"
            "  bob@example.com                                  high          atRisk\n"
            "  alice@example.com                                medium        confirmed\n"
            "==========================================================\n"
        )
        recs = _build_recommendations(risky_users=with_rows, **self._BASE_KW)
        risky = [r for r in recs if r.get("finding_id") == "finding-risky"]
        assert len(risky) == 1
        assert len(risky[0]["sub_items"]) == 2


class TestAppCredentialCountNotInflated:
    """The credential-expiry recommendation used to count substrings
    ("expired", "critical") across the entire WARN file. The header word
    "EXPIRED", the explicit summary line, and each per-row Status all
    matched — inflating the user-visible count by ~3 every time."""

    _BASE_KW = dict(
        mfa={"has_data": True, "pct": 100, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 80, "current": 80, "max": 100,
                      "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        admin_roles=None,
        intune=None,
        sharepoint=None,
        oauth=None,
        azure=None,
    )

    def _warn_file(self, expired_rows: int, critical_rows: int) -> str:
        """Build a realistic WARN file with explicit summary + rows."""
        lines = [
            "=" * 140,
            "  WARNING: EXPIRED OR SOON-EXPIRING APP CREDENTIALS",
            "=" * 140,
            "",
            f"  {expired_rows} expired, {critical_rows} expiring within 30 days.",
            "",
            f"  {'App Name':<40} {'Type':<12} {'Credential Name':<30} "
            f"{'Expiry Date':<22} {'Days Left':>9}  Status",
            "  " + "-" * 136,
        ]
        for i in range(expired_rows):
            lines.append(
                f"  AppE{i:<35} Secret       cred{i:<26} "
                f"2025-01-01 00:00       -30   EXPIRED"
            )
        for i in range(critical_rows):
            lines.append(
                f"  AppC{i:<35} Secret       cred{i:<26} "
                f"2026-06-01 00:00         5   CRITICAL"
            )
        return "\n".join(lines)

    def test_count_matches_summary_line(self):
        warn = self._warn_file(expired_rows=3, critical_rows=2)
        recs = _build_recommendations(
            file_contents={"17c_app_credential_expiry_WARN.txt": warn},
            **self._BASE_KW,
        )
        cred_recs = [r for r in recs if "rec_cred_expiry_title" in str(r.get("title", "")) or "credential" in str(r.get("title", "")).lower() or "legitimasjon" in str(r.get("title", "")).lower()]
        # The title is i18n'd; just assert count appears in detail or title
        assert len(cred_recs) == 1
        title_or_detail = (cred_recs[0]["title"] + " " + cred_recs[0]["detail"]).lower()
        # The true total is 3+2 = 5. Old substring counting would have
        # produced ~14 (one per "expired"/"critical" hit including header,
        # subline and rows). Anything in (3, 9) means the bug is back.
        import re as _re
        nums = [int(n) for n in _re.findall(r"\d+", title_or_detail)]
        assert 5 in nums, f"expected count 5 to appear in rec, got numbers: {nums}"
        assert not any(n > 9 for n in nums if n != 30), (
            f"recommendation contains an inflated count (got {nums}); "
            "expected at most 5 (3 expired + 2 critical)"
        )

    def test_zero_credentials_no_rec(self):
        recs = _build_recommendations(
            file_contents={"17c_app_credential_expiry_WARN.txt": ""},
            **self._BASE_KW,
        )
        assert not any("credential" in str(r.get("title", "")).lower() for r in recs)


class TestCountDataLinesSkipsBanner:
    """_count_data_lines used to count the section banner ('TRANSPORT RULES
    (5 total)') as a data row. Transport_rules, connectors and
    forwarding_count all flow through this helper, so even +1 here biases
    every Exchange-overview number."""

    def test_banner_with_total_not_counted(self):
        text = (
            "================================\n"
            "  TRANSPORT RULES  (3 total)\n"
            "================================\n"
            "  Block external forwarding\n"
            "  Quarantine inbound spam\n"
            "  Strip auto-reply\n"
            "================================\n"
        )
        assert _count_data_lines(text) == 3  # not 4

    def test_alerts_found_banner_not_counted(self):
        """A tabular section counts its rows; the banner is never a row.

        One record per line, so the row count decides and the banner is only a
        sanity check. The mismatch here (banner 12, one row present) means
        truncated output — the smaller honest number is reported and the
        disagreement is logged.
        """
        text = (
            "================================\n"
            "  SECURITY ALERTS  (12 found)\n"
            "================================\n"
            "  Suspicious sign-in\n"
            "================================\n"
        )
        assert _count_data_lines(text) == 1  # not 2, and not the banner's 12

    def test_no_banner_still_counts_correctly(self):
        text = "  Row one\n  Row two\n  Row three\n"
        assert _count_data_lines(text) == 3


# ---------------------------------------------------------------------------
# Regression: compliance verdicts must be grounded, not hardcoded.
# Pre-v10.10.5 several controls always passed (false attestations) or were
# silently omitted (audit looks N/A when it should be FAIL).
# ---------------------------------------------------------------------------


def _ctx(**overrides) -> dict:
    """Build a minimal context for _build_compliance_map.

    All sections default to "has_data: False" / empty so each test sets only
    the inputs it cares about.
    """
    base = {
        "mfa": {"has_data": False, "pct": 0, "no_mfa": 0},
        "ca": {"has_data": False, "enabled": 0},
        "secure_score": {"has_data": False, "pct": 0, "improvements": []},
        "admin_roles": {"has_data": False, "global_admin_count": 0},
        "spf_dmarc": [],
        "sharepoint": {"has_data": False},
        "intune": {"has_data": False, "total": 0},
        "exchange": {},
        "oauth": {"has_data": False},
        "purview": {},
        "groups": {},
        "signin_risk": {},
        "risky_users": "",
        "file_contents": {},
    }
    base.update(overrides)
    return base


class TestComplianceUnifiedAuditLog:
    """CIS 9.1 must not draw a verdict from the Entra directoryAudits log.

    It was first hardcoded 'pass' (a false attestation for every tenant), then
    graded on the Entra directoryAudits row count — but that log is ALWAYS on and
    is independent of the Exchange/Purview Unified Audit Log ingestion toggle the
    control is about, so counting its rows produced a false PASS on a UAL-off
    tenant and a false FAIL on a quiet-but-enabled one. The verdict now comes from
    the real setting (Get-AdminAuditLogConfig | UnifiedAuditLogIngestionEnabled,
    file 27d) — see tests/test_report_compliance.py for the pass/fail cases. These
    tests pin the other half: with only the directoryAudits log present, the
    honest verdict is cannot-verify, in every case (accuracy sweep)."""

    def test_missing_audit_log_reports_info_not_pass(self):
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "9.1"]
        assert len(ctrl) == 1
        assert ctrl[0]["status"] == "info"

    # The Entra directoryAudits log this control reads is ALWAYS on and is
    # independent of the Exchange/Purview Unified Audit Log ingestion toggle CIS
    # 9.1 is actually about. Its event count therefore neither confirms nor
    # denies UAL ingestion: a populated log was a false PASS on a UAL-off tenant,
    # an empty one a false FAIL on a quiet-but-enabled tenant. Both are now
    # "info" (cannot verify) until the real setting is collected (accuracy sweep).
    def test_empty_audit_log_is_info_not_fail(self):
        # File exists but contains no events — that does NOT prove UAL is off.
        text = (
            "================================================================\n"
            "  ENTRA DIRECTORY AUDIT LOG  (last 14 days — 0 events)\n"
            "================================================================\n"
            "================================================================\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"19_entra_audit_log_admin_activity.txt": text})
        ) if c["cis_id"] == "9.1"]
        assert ctrl[0]["status"] == "info"

    def test_populated_audit_log_is_info_not_pass(self):
        # Directory-audit events do not attest that the Unified Audit Log is on.
        text = (
            "================================================================\n"
            "  ENTRA DIRECTORY AUDIT LOG  (last 14 days — 3 events)\n"
            "================================================================\n"
            "  2026-05-12 10:00       Add user                      success   admin@example.com\n"
            "  2026-05-12 10:05       Update conditional access     success   admin@example.com\n"
            "  2026-05-12 10:10       Update directory role         success   admin@example.com\n"
            "================================================================\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"19_entra_audit_log_admin_activity.txt": text})
        ) if c["cis_id"] == "9.1"]
        assert ctrl[0]["status"] == "info"


class TestComplianceAntiSpamNotSilent:
    """CIS 4.3 used to be omitted entirely when the policy file was empty,
    making the missing entry look like N/A in the customer report.

    Keeping the row is still the requirement. Grading it FAIL was the part
    that was wrong: an absent 24_exchange_antispam.txt means the Exchange
    section did not run, not that the tenant has no anti-spam policy, and
    "info" is how every neighbouring control reports that (see
    TestComplianceLegacyAuthDataGap below). It also keeps the control out of
    the compliance_pct denominator, which excludes "info" for this reason."""

    def test_empty_antispam_emits_an_entry_but_does_not_grade_it(self):
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "4.3"]
        assert len(ctrl) == 1, "CIS 4.3 must always be emitted, even if anti-spam file is empty"
        assert ctrl[0]["status"] == "info"
        assert ctrl[0]["status"] != "fail", "no data is not a compliance failure"

    def test_an_error_stub_is_not_a_reading_either(self):
        """A non-empty file is not automatically a successful collection.

        The first cut of this fix tested `antispam.strip()` for the positive
        branch, so "Error: access denied" — non-empty — attested that
        anti-spam policies were configured.
        """
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"24_exchange_antispam.txt": "Error: access denied"})
        ) if c["cis_id"] == "4.3"]
        assert ctrl[0]["status"] == "info"
        assert ctrl[0]["status"] != "pass", "an error stub must not attest compliance"

    def test_populated_antispam_emits_pass(self):
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"24_exchange_antispam.txt": "Standard policy: enabled\n"})
        ) if c["cis_id"] == "4.3"]
        assert ctrl[0]["status"] == "pass"


class TestComplianceLegacyAuthDataGap:
    """SharePoint's legacy-protocol flag, and the guard on missing input.

    This used to be graded as CIS 5.1.1, "Ensure legacy authentication is
    blocked" — a control about Entra, answered with a SharePoint setting. The
    SharePoint question is now 7.2.3 under its own name and 5.1.1 reads
    Conditional Access, so these move with the behaviour they describe.

    The guard they pin is unchanged and still worth pinning: legacy_auth
    defaults to False, so without a has_data check an audit that never reached
    SharePoint admin settings reported a pass.
    """

    def test_missing_sharepoint_data_reports_info(self):
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "7.2.3"]
        assert ctrl[0]["status"] == "info"

    def test_legacy_auth_enabled_reports_fail(self):
        ctrl = [c for c in _build_compliance_map(
            _ctx(sharepoint={"has_data": True, "legacy_auth": True, "legacy_auth_known": True})
        ) if c["cis_id"] == "7.2.3"]
        assert ctrl[0]["status"] == "fail"

    def test_legacy_auth_disabled_reports_pass(self):
        ctrl = [c for c in _build_compliance_map(
            _ctx(sharepoint={"has_data": True, "legacy_auth": False, "legacy_auth_known": True})
        ) if c["cis_id"] == "7.2.3"]
        assert ctrl[0]["status"] == "pass"


class TestComplianceSharePointSharingFailsOnAnyone:
    """CIS 7.2.1 used to report 'warn' for any non-'ok' sharing level,
    including the worst case (ExternalUserAndGuestSharing, i.e. anyone-
    with-the-link). That's amber for the most permissive config, which
    understates the risk."""

    def test_anyone_with_the_link_reports_fail(self):
        ctrl = [c for c in _build_compliance_map(
            _ctx(sharepoint={
                "has_data": True,
                "sharing": "ExternalUserAndGuestSharing",
                "sharing_level": "warning",
                "sharing_label": "anyone-with-the-link",
            })
        ) if c["cis_id"] == "7.2.1"]
        assert ctrl[0]["status"] == "fail"

    def test_existing_guests_only_still_passes(self):
        ctrl = [c for c in _build_compliance_map(
            _ctx(sharepoint={
                "has_data": True,
                "sharing": "ExistingExternalUserSharingOnly",
                "sharing_level": "ok",
                "sharing_label": "existing guests only",
            })
        ) if c["cis_id"] == "7.2.1"]
        assert ctrl[0]["status"] == "pass"


class TestComplianceFrameworkMappings:
    """ISO 27001:2022 control IDs must actually correspond to what the
    underlying CIS control checks. The pre-v10.10.5 mappings cited
    A.8.11 (data masking) for app credential expiry — auditors reviewing
    against the real standard would find these to be misclassified."""

    def test_app_credentials_maps_to_identity_management(self):
        fw = _FRAMEWORK_MAP["2.1.2"]
        assert fw["iso_id"] == "A.5.16", \
            f"CIS 2.1.2 (app credentials) must map to A.5.16 Identity management, not {fw['iso_id']}"

    def test_dlp_maps_to_data_leakage_prevention(self):
        fw = _FRAMEWORK_MAP["3.1.1"]
        assert fw["iso_id"] == "A.8.12", \
            f"CIS 3.1.1 (DLP policies) must map to A.8.12 DLP, not {fw['iso_id']}"

    def test_antispam_maps_to_anti_malware(self):
        fw = _FRAMEWORK_MAP["4.3"]
        assert fw["iso_id"] == "A.8.7", \
            f"CIS 4.3 (anti-spam) must map to A.8.7 Protection against malware, not {fw['iso_id']}"


# NOTE: The UniFi controller-mode firmware-audit regression test from
# MSP-Toolkit-V2 v10.10.5 lived here. It's been removed from sybr-hub
# v0.1.0 because the network-audit consolidation module isn't part of
# the minimum scope (see ROADMAP.md — FortiGate / UniFi audits land in
# a later release). The fix it locked in is still in m365_audit
# section code where applicable; when the network audit module is
# brought across, restore this test alongside it.


# ---------------------------------------------------------------------------
# Regression: compliance verdicts must count actual rows, not match
# substrings against the section banner. The banner always contains the
# noun the control is named after, so substring matching always passed.
# ---------------------------------------------------------------------------


class TestComplianceSubstringBugs:
    """Each of these controls used to match a banner word like 'eligible',
    'emergency', 'expired', etc. against the entire file — so the banner
    line itself (which every collector writes) triggered a PASS regardless
    of whether the audit found any actual data rows."""

    def test_pim_empty_does_not_pass_on_banner(self):
        # Banner emitted by identity_security.py:222 even with 0 assignments
        text = (
            "====================================================================================================\n"
            "  PIM ELIGIBLE ROLE ASSIGNMENTS  (0 total)\n"
            "====================================================================================================\n"
            "  Role                                          Principal                                Type            Expiry\n"
            "  ------------------------------------------------------------------------------------------------\n"
            "====================================================================================================\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"07b_pim_eligible_assignments.txt": text})
        ) if c["cis_id"] == "1.1.5"]
        assert ctrl[0]["status"] == "warn"

    def test_pim_populated_passes(self):
        text = (
            "  PIM ELIGIBLE ROLE ASSIGNMENTS  (1 total)\n"
            "  Role                                          Principal                                Type            Expiry\n"
            "  ------------------------------------------------------------------------------------------------\n"
            "  Global Administrator                          alice@example.com                        user            Permanent\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"07b_pim_eligible_assignments.txt": text})
        ) if c["cis_id"] == "1.1.5"]
        assert ctrl[0]["status"] == "pass"

    def test_emergency_access_empty_does_not_pass_on_banner(self):
        text = (
            "==========================================================================================\n"
            "  EMERGENCY / BREAK-GLASS ACCOUNT CHECK\n"
            "==========================================================================================\n"
            "  No Global Admin IDs provided — skipping check.\n"
            "==========================================================================================\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"07c_emergency_access_check.txt": text})
        ) if c["cis_id"] == "1.1.6"]
        # The header word "EMERGENCY" used to make this pass; the verdict must
        # come from actual user rows, not from the banner.
        #
        # This fixture is the section reporting that it skipped — it had no
        # admin ids to check. That is not a pass, and it is not a warning
        # either: "no break-glass accounts found" would be a negative finding
        # asserted from a check that never ran. The assertion allowed "warn"
        # because cannot-verify was not yet an outcome here; the invariant it
        # was protecting is that a skipped check never reads as a pass.
        assert ctrl[0]["status"] == "info", \
            "a skipped check must report cannot-verify, not a finding"
        assert "Kan ikke verifiseres" in ctrl[0]["detail"]

    def test_banned_passwords_reads_correct_file(self):
        """Pre-v10.10.6 the check read 09c_auth_strength_policies.txt
        (wrong file — that's FIDO2/auth-strength, unrelated to banned
        passwords). The actual banned-password config is in
        31_password_protection.txt."""
        # Empty 31_ file → info
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "1.2.1"]
        assert ctrl[0]["status"] == "info"

    def test_banned_passwords_enabled_passes(self):
        pwd_text = (
            "===========================================================\n"
            "  ENTRA ID PASSWORD PROTECTION\n"
            "===========================================================\n"
            "  Custom Banned Passwords Enabled : True\n"
            "  Banned Password List            : password1, qwerty\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"31_password_protection.txt": pwd_text})
        ) if c["cis_id"] == "1.2.1"]
        assert ctrl[0]["status"] == "pass"

    def test_banned_passwords_disabled_fails(self):
        pwd_text = (
            "  Custom Banned Passwords Enabled : False\n"
            "  Banned Password List            : N/A\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"31_password_protection.txt": pwd_text})
        ) if c["cis_id"] == "1.2.1"]
        assert ctrl[0]["status"] == "fail"

    def test_secure_score_data_gap_info_not_fail(self):
        """ss.get('pct', 0) → 0 → FAIL when secure_score has no data.
        Should be info instead."""
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "1.4"]
        assert ctrl[0]["status"] == "info"

    def test_app_credentials_use_summary_line_not_substring(self):
        # WARN file with explicit "0 expired, 2 expiring" — substring "expired"
        # appears 3 times (header, summary, status column). Old code would FAIL.
        warn = (
            "=" * 140 + "\n"
            "  WARNING: EXPIRED OR SOON-EXPIRING APP CREDENTIALS\n"
            "=" * 140 + "\n"
            "\n"
            "  0 expired, 2 expiring within 30 days.\n"
            "\n"
            "  App                                      Type         Cred                          Expiry                  Days  Status\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"17c_app_credential_expiry_WARN.txt": warn})
        ) if c["cis_id"] == "2.1.2"]
        assert ctrl[0]["status"] == "warn"  # critical only, no expired


class TestComplianceMailboxAuditValueParsing:
    """The previous check did `'AuditDisabled' in text and 'False' in text` —
    independent substring searches. A config containing `AuditDisabled: False`
    plus any unrelated `SomethingElse: True` line could flip the verdict."""

    def test_audit_disabled_false_passes(self):
        config = (
            "AuditDisabled: False\n"
            "DirSyncEnabled: True\n"  # unrelated True — must not flip verdict
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"27c_exchange_org_config.txt": config})
        ) if c["cis_id"] == "4.1"]
        assert ctrl[0]["status"] == "pass"

    def test_audit_disabled_true_fails(self):
        config = (
            "AuditDisabled: True\n"
            "SomethingElse: False\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"27c_exchange_org_config.txt": config})
        ) if c["cis_id"] == "4.1"]
        assert ctrl[0]["status"] == "fail"


class TestComplianceDeviceCompliancePolicies:
    """CIS 6.1.1 is *about* having policies configured, not about device
    compliance %. A tenant with 0 policies but 0 devices used to PASS."""

    _POLICY_TEXT = (
        "===============================\n"
        "  INTUNE COMPLIANCE POLICIES  (2 total)\n"
        "===============================\n"
        "  Windows 10 baseline                 Win10                2026-01-01 10:00:00\n"
        "  macOS baseline                      macOS                2026-01-01 10:00:00\n"
    )

    _EMPTY_POLICY_TEXT = (
        "===============================\n"
        "  INTUNE COMPLIANCE POLICIES  (0 total)\n"
        "===============================\n"
    )

    def test_devices_present_and_policy_file_lists_none_fails(self):
        """The real finding: we read the policy list and it was empty."""
        ctrl = [c for c in _build_compliance_map(_ctx(
            intune={"has_data": True, "total": 50, "compliance_pct": 100, "noncompliant": 0},
            file_contents={"11_intune_compliance_policies.txt": self._EMPTY_POLICY_TEXT},
        )) if c["cis_id"] == "6.1.1"]
        assert ctrl[0]["status"] == "fail"

    def test_devices_present_but_policy_file_absent_cannot_be_verified(self):
        """Devices enrolled and no policy file is a *half-collected* Intune
        section, not a tenant without compliance policies.

        Only reachable when devices are present, so the empty-audit contract
        test cannot see it — it took the partial-audit one.
        """
        ctrl = [c for c in _build_compliance_map(
            _ctx(intune={"has_data": True, "total": 50, "compliance_pct": 100, "noncompliant": 0})
        ) if c["cis_id"] == "6.1.1"]
        assert ctrl[0]["status"] == "info"
        assert ctrl[0]["status"] != "fail", "an unread policy list is not a CIS failure"

    def test_policies_present_and_compliant_passes(self):
        ctrl = [c for c in _build_compliance_map(_ctx(
            intune={"has_data": True, "total": 50, "compliance_pct": 95, "noncompliant": 0},
            file_contents={"11_intune_compliance_policies.txt": self._POLICY_TEXT},
        )) if c["cis_id"] == "6.1.1"]
        assert ctrl[0]["status"] == "pass"

    def test_no_devices_no_policies_info(self):
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "6.1.1"]
        assert ctrl[0]["status"] == "info"


class TestComplianceSafeLinksAttachments:
    """CIS 4.5 / 4.6 used to match the substring "safe links" / "safe attach"
    anywhere in the defender-policies file. A `Name: Safe Links policy`
    line on a disabled policy made the tenant PASS — a false attestation
    on the policy actually being active."""

    def _policies(self, *, sl_enabled=False, sa_enabled=False) -> str:
        out = ["==========", "  MICROSOFT DEFENDER FOR OFFICE 365 POLICIES", "==========", ""]
        if sl_enabled is not None:
            out += [
                "Name: Safe Links policy",
                "PolicyType: SafeLinksPolicy",
                f"Enabled: {str(sl_enabled)}",
                "",
            ]
        if sa_enabled is not None:
            out += [
                "Name: Safe Attachments policy",
                "PolicyType: SafeAttachmentsPolicy",
                f"Enabled: {str(sa_enabled)}",
                "",
            ]
        return "\n".join(out)

    def test_disabled_safe_links_policy_does_not_pass(self):
        text = self._policies(sl_enabled=False, sa_enabled=False)
        ctrl_sl = [c for c in _build_compliance_map(
            _ctx(file_contents={"27_exchange_defender_policies.txt": text})
        ) if c["cis_id"] == "4.5"]
        assert ctrl_sl[0]["status"] == "fail", \
            "Safe Links present but disabled must FAIL, not PASS on substring"

    def test_enabled_safe_links_policy_passes(self):
        text = self._policies(sl_enabled=True, sa_enabled=False)
        ctrl_sl = [c for c in _build_compliance_map(
            _ctx(file_contents={"27_exchange_defender_policies.txt": text})
        ) if c["cis_id"] == "4.5"]
        assert ctrl_sl[0]["status"] == "pass"

    def test_no_safe_links_at_all_warns(self):
        # File exists but no Safe Links / Safe Attachments policies in it
        text = "Name: AntiPhishing\nPolicyType: AntiPhishPolicy\nEnabled: True\n"
        ctrl_sl = [c for c in _build_compliance_map(
            _ctx(file_contents={"27_exchange_defender_policies.txt": text})
        ) if c["cis_id"] == "4.5"]
        assert ctrl_sl[0]["status"] == "warn"

    def test_enabled_safe_attachments_passes(self):
        text = self._policies(sl_enabled=False, sa_enabled=True)
        ctrl_sa = [c for c in _build_compliance_map(
            _ctx(file_contents={"27_exchange_defender_policies.txt": text})
        ) if c["cis_id"] == "4.6"]
        assert ctrl_sa[0]["status"] == "pass"


class TestCompliancePhishingResistantMFA:
    """CIS 1.1.2 used to PASS based on an invented 50%-of-users threshold.
    The actual CIS control is about policy configuration: are phishing-
    resistant methods (FIDO2, Windows Hello) enabled in the
    authenticationMethodsPolicy?"""

    def test_fido2_enabled_passes(self):
        # The format secure_score.py writes for 09b_auth_methods_policy.txt
        text = (
            "==========\n"
            "  AUTHENTICATION METHODS POLICY\n"
            "==========\n"
            "  Method                                   State\n"
            "  ------------------------------------------------\n"
            "  Fido2                                    enabled\n"
            "  MicrosoftAuthenticator                   enabled\n"
            "  Sms                                      disabled\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"09b_auth_methods_policy.txt": text})
        ) if c["cis_id"] == "1.1.2"]
        assert ctrl[0]["status"] == "pass"
        assert "Fido2" in ctrl[0]["detail"]

    def test_only_weak_methods_warns(self):
        text = (
            "  Method                                   State\n"
            "  ----------------\n"
            "  Fido2                                    disabled\n"
            "  Sms                                      enabled\n"
            "  Voice                                    enabled\n"
        )
        ctrl = [c for c in _build_compliance_map(
            _ctx(file_contents={"09b_auth_methods_policy.txt": text})
        ) if c["cis_id"] == "1.1.2"]
        assert ctrl[0]["status"] == "warn"

    def test_missing_auth_methods_policy_reports_info(self):
        ctrl = [c for c in _build_compliance_map(_ctx()) if c["cis_id"] == "1.1.2"]
        assert ctrl[0]["status"] == "info"

    def test_user_count_threshold_no_longer_drives_verdict(self):
        """Pre-v10.10.7 a tenant with 0 users with strong methods got
        'info', regardless of whether the policy itself enabled FIDO2.
        Now the verdict is driven by policy config, not user counts."""
        text = (
            "  Method                                   State\n"
            "  Fido2                                    enabled\n"
        )
        # mfa stats deliberately set to "0 users with strong methods"
        ctrl = [c for c in _build_compliance_map(_ctx(
            file_contents={"09b_auth_methods_policy.txt": text},
            mfa={"has_data": True, "pct": 100, "no_mfa": 0,
                 "strong_method_count": 0, "registered_count": 50},
        )) if c["cis_id"] == "1.1.2"]
        assert ctrl[0]["status"] == "pass", \
            "policy-level configuration should PASS independently of user adoption"


def test_multiline_record_with_lowercase_fields_trusts_its_banner():
    """22_exchange_connectors.txt writes its fields in lower case.

    The multi-line detector required a capitalised field name, so a file
    holding one record across three lines was treated as a plain table and
    counted as three. The connector count is printed verbatim on the
    customer-facing report, so the tenant's single connector was reported as
    three of them.
    """
    from app.reports.generator import _count_data_lines, _is_multiline_record_format

    text = (
        "=" * 80 + "\n"
        "  EXCHANGE CONNECTORS  (1 entries)\n"
        + "=" * 80 + "\n"
        "\n"
        "  [1]\n"
        "    outbound: N/A\n"
        "    inbound: N/A\n"
        "\n"
        + "=" * 80 + "\n"
    )

    assert _is_multiline_record_format(text), "lower-case field names are still fields"
    assert _count_data_lines(text) == 1


def test_capitalised_fields_still_detected():
    """The original shape must keep working."""
    from app.reports.generator import _count_data_lines

    text = (
        "  TRANSPORT RULES  (2 entries)\n"
        "  [1]\n"
        "    Name: Scanner spam-bypass\n"
        "    State: Enabled\n"
        "  [2]\n"
        "    Name: External warning\n"
        "    State: Enabled\n"
    )
    assert _count_data_lines(text) == 2


def test_plain_table_is_not_pulled_into_the_multiline_branch():
    """Relaxing the field regex must not let a tabular file trust its banner.

    The "[n]" index line is the gate on that branch, and it is what makes the
    relaxation safe. So this file is the awkward case: every row is shaped
    like a field, "label: value", but there are no index lines and each row is
    a whole record. Without the gate the over-claiming banner would win and
    the section would report nine domains where two were collected.
    """
    from app.reports.generator import _count_data_lines, _is_multiline_record_format

    text = (
        "  TEAMS POLICIES  (9 total)\n"
        "  " + "-" * 40 + "\n"
        "  Global: Enabled\n"
        "  Restricted guests: Disabled\n"
    )
    assert not _is_multiline_record_format(text), "no [n] lines means no records span lines"
    assert _count_data_lines(text) == 2


def test_data_row_shaped_like_a_header_is_still_data():
    """A column header is underlined by a rule; a data row is not.

    Real rows land on the header shape — every column capitalised, no digits,
    no @ / :. Two did: an OAuth consent grant reading "AvePoint Fly |
    Microsoft Graph | User.Read", and a PIM assignment whose principal name
    was truncated to exactly the column width, closing the gap that would
    otherwise have exposed the lower-case "servicePrinc" beside it. Eleven
    consent grants were dropped from a security-relevant count.
    """
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 70 + "\n"
        "  OAUTH TENANT-WIDE CONSENT GRANTS  (3 total)\n"
        + "=" * 70 + "\n"
        "  Client App                Resource                 Scopes\n"
        "  " + "-" * 66 + "\n"
        "  AvePoint Fly              Microsoft Graph          User.Read\n"
        "  Datto RMM integration     Microsoft Graph          User.Read\n"
        "  Autotask PSA AD Sync      Microsoft Graph          User.Read\n"
        + "=" * 70 + "\n"
    )
    assert _count_data_lines(text) == 3


def test_the_first_data_row_is_not_eaten_by_the_rule_above_it():
    """Being next to a rule is not enough — the first row always is.

    This is the case that survived the first attempt at the fix: the rule that
    underlines the header sits directly above row one.
    """
    from app.reports.generator import _count_data_lines

    text = (
        "  GRANTS  (2 total)\n"
        "  Client App           Resource\n"
        "  " + "-" * 40 + "\n"
        "  AvePoint Fly         Microsoft Graph\n"
        "  Inforcer Integration Microsoft Graph\n"
    )
    assert _count_data_lines(text) == 2


def test_column_header_is_still_excluded():
    """The rule must not swing the other way and start counting headers."""
    from app.reports.generator import _count_data_lines

    text = (
        "  DEVICES  (1 total)\n"
        "  " + "-" * 40 + "\n"
        "  Device Name          Platform\n"
        "  " + "-" * 40 + "\n"
        "  laptop-01            Windows\n"
    )
    assert _count_data_lines(text) == 1


# ---------------------------------------------------------------------------
# The collector signals some findings by renaming the file. A reader that
# knows only the all-clear name reports "nothing found" exactly when
# something was.
# ---------------------------------------------------------------------------

def _exchange(file_contents):
    from app.reports.generator import _parse_exchange_overview
    return _parse_exchange_overview(file_contents)


def test_inbox_rules_counted_from_the_warn_file():
    """Rules found go to 29_..._WARN.txt; the plain name is the all-clear.

    This count is printed on the customer-facing report. Reading only the
    plain name showed zero external-forwarding inbox rules to a tenant that
    had two, while CIS 4.4 on the same report flagged them.
    """
    warn = (
        "=" * 80 + "\n"
        "  INBOX RULES WITH EXTERNAL FORWARDING  (2 entries)\n"
        + "=" * 80 + "\n"
        "\n  [1]\n"
        "    Name: Send to Gmail\n"
        "    Mailbox: anna@example.com\n"
        "    ForwardTo: anna.private@gmail.com\n"
        "\n  [2]\n"
        "    Name: Copy to personal\n"
        "    Mailbox: bjorn@example.com\n"
        "    ForwardTo: bjorn@outlook.com\n"
    )
    result = _exchange({"29_exchange_inbox_rules_external_fwd_WARN.txt": warn})
    assert result["inbox_rules_external"] == 2


def test_inbox_rules_all_clear_still_reads_zero():
    """The clean file must keep reporting nothing."""
    clean = (
        "=" * 80 + "\n"
        "  INBOX RULES WITH EXTERNAL FORWARDING  (0 entries)\n"
        + "=" * 80 + "\n"
        "  (none)\n"
    )
    result = _exchange({"29_exchange_inbox_rules_external_fwd.txt": clean})
    assert result["inbox_rules_external"] == 0


def test_inbox_rules_missing_section_reads_zero():
    """No Exchange data at all must not invent a finding."""
    assert _exchange({})["inbox_rules_external"] == 0


def test_unmeasured_legacy_auth_is_not_a_pass():
    """The field was never collected at all until this was found.

    _parse_sharepoint_settings read "legacy auth" out of a file the collector
    did not write, so the flag was False on every tenant and the control that
    grades it passed unconditionally. Absence now reads as unmeasured.
    """
    from app.reports.generator import _build_compliance_map

    ctx = {"sharepoint": {"has_data": True, "legacy_auth": False}, "file_contents": {}}
    row = [c for c in _build_compliance_map(ctx) if c["cis_id"] == "7.2.3"][0]
    assert row["status"] == "info"


# ---------------------------------------------------------------------------
# A section file carries more than its table. Counting the whole file made four
# sections disagree with their own headers.
# ---------------------------------------------------------------------------

def test_a_summary_block_after_the_table_is_not_counted():
    """PIM writes a SUMMARY block and a findings list below its rows."""
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 60 + "\n"
        "  PRIVILEGED IDENTITY MANAGEMENT (PIM) — ROLE ASSIGNMENTS\n"
        + "=" * 60 + "\n\n"
        "  ELIGIBLE (Just-In-Time) ASSIGNMENTS  (0 total)\n"
        "  " + "-" * 56 + "\n"
        "  Role          Principal      Type      Expiry\n"
        "  " + "-" * 56 + "\n\n"
        "  ACTIVE ASSIGNMENTS  (2 total: 2 permanent, 0 time-bound)\n"
        "  " + "-" * 56 + "\n"
        "  Role          Principal      Type      Assignment   End\n"
        "  " + "-" * 56 + "\n"
        "  Global Administrator   Admin Sybr    user   Assigned  PERMANENT\n"
        "  Exchange Administrator Thorsten      user   Assigned  PERMANENT\n\n"
        "  " + "=" * 40 + "\n"
        "  SUMMARY\n"
        "  " + "=" * 40 + "\n"
        "    Eligible (JIT) assignments   : 0\n"
        "    Active assignments           : 2\n"
        "      Permanent                  : 2\n\n"
        "  PERMANENT CRITICAL ROLE ASSIGNMENTS (should be eligible/JIT):\n"
        "    - Global Administrator: Admin Sybr\n"
        + "=" * 60 + "\n"
    )
    assert _count_data_lines(text) == 2


def test_a_tally_above_the_table_is_not_counted():
    """Defender writes "High: 3 | Medium: 0 | Low: 0" before its rows."""
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 60 + "\n"
        "  DEFENDER FOR OFFICE 365 — SECURITY ALERTS  (2 total)\n"
        + "=" * 60 + "\n"
        "  High: 2  |  Medium: 0  |  Low: 0\n\n"
        "  Title                 Severity   Status     Created\n"
        "  " + "-" * 56 + "\n"
        "  Malicious IP address  high       resolved   2026-06-17\n"
        "  Anonymous IP address  high       resolved   2026-06-17\n"
        + "=" * 60 + "\n"
    )
    assert _count_data_lines(text) == 2


def test_a_trailing_summary_line_is_not_a_record():
    """Mailbox delegations end with "Summary: 0 FullAccess, 84 SendAs"."""
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 60 + "\n"
        "  MAILBOX DELEGATIONS (SendAs / FullAccess)  (2 entries)\n"
        + "=" * 60 + "\n"
        "  Mailbox              Type      Delegate\n"
        "  " + "-" * 56 + "\n"
        "  post@x.no            SendAs    kenneth@x.no\n"
        "  brann@x.no           SendAs    thorsten@x.no\n\n"
        "  Summary: 0 FullAccess, 2 SendAs delegation(s)\n"
        + "=" * 60 + "\n"
    )
    assert _count_data_lines(text) == 2


def test_two_tables_under_one_banner_are_both_counted():
    """The compliance score holds a control list and an improvement list."""
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 60 + "\n"
        "  MICROSOFT COMPLIANCE SCORE\n"
        + "=" * 60 + "\n"
        "  Overall Score : 156.0 / 273.0  (57.1%)\n"
        "  As of         : 2026-07-30\n\n"
        "  ── Compliance-Related Controls (2 found) ──\n"
        "  Control              Score%  Category\n"
        "  " + "-" * 50 + "\n"
        "  dlp_datalossprevention    0.0%  Data\n"
        "  mip_purviewlabelconsent   0.0%  Data\n\n"
        "  ── Top Improvement Actions ──\n"
        "  Control              Score%  Category\n"
        "  " + "-" * 50 + "\n"
        "  McasFirewallLogUpload     0.0%  Apps\n"
        + "=" * 60 + "\n"
    )
    assert _count_data_lines(text) == 3, "two controls plus one improvement action"


def test_a_file_with_no_table_still_counts_its_lines():
    """Count files are all summary and no table; they must not read as empty."""
    from app.reports.generator import _count_data_lines

    text = (
        "=" * 40 + "\n"
        "  USER COUNT SUMMARY\n"
        + "=" * 40 + "\n"
        "  Total users    : 216\n"
        "  Enabled        : 202\n"
        "  Disabled       : 14\n"
        + "=" * 40 + "\n"
    )
    assert _count_data_lines(text) == 3
