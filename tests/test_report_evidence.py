"""Controls must not attest to more than the evidence supports.

Each case here is a place the report said something reassuring on the
strength of a file that did not contain the reassurance: a control graded
"pass" because a section ran rather than because it found anything, a role
counted under a name Graph does not use, a total quietly equal to a
different total, and an absence established only where nobody looked.
"""

from __future__ import annotations

import pytest

from app.reports.generator import (
    _parse_admin_roles,
    _parse_signin_risk,
    build_report_context,
)
from tests.audit_fixture import FULL_AUDIT, _entry_block


@pytest.fixture()
def controls(tmp_path):
    """Build the real report context, then index its compliance rows by id."""
    def _build(overrides: dict[str, str]) -> dict[str, dict]:
        d = tmp_path / "Acme_AS" / "2026-01-01_0900"
        d.mkdir(parents=True, exist_ok=True)
        for name, content in {**FULL_AUDIT, **overrides}.items():
            (d / name).write_text(content, encoding="utf-8")
        ctx = build_report_context("Acme AS", "acme.no", d, [], lang="no", frameworks="all")
        return {c["cis_id"]: c for c in ctx["compliance"]}
    return _build


class TestAControlNeedsEvidenceNotJustAFile:
    """`_section_ran` says a reading exists, not that it found anything.

    A tenant with no anti-phishing policy at all writes "(0 entries)" over a
    "(none)" placeholder — a real reading of an unprotected tenant — and that
    was graded as a pass.
    """

    def test_zero_antiphishing_policies_is_a_failure_not_a_pass(self, controls):
        empty = _entry_block("EXCHANGE ANTI-PHISHING POLICIES", [])
        got = controls({"23_exchange_antiphish.txt": empty})["4.2"]
        assert got["status"] == "fail", got

    def test_zero_antispam_policies_is_a_failure_not_a_pass(self, controls):
        empty = _entry_block("EXCHANGE ANTI-SPAM POLICIES", [])
        got = controls({"24_exchange_antispam.txt": empty})["4.3"]
        assert got["status"] == "fail", got

    def test_a_configured_policy_still_passes(self, controls):
        assert controls({})["4.2"]["status"] == "pass"
        assert controls({})["4.3"]["status"] == "pass"

    def test_a_missing_section_is_unverifiable_rather_than_failed(self, controls):
        """No file means the Exchange section did not run. "No policies" and
        "no data" are different claims and must not share a grade."""
        got = controls({"23_exchange_antiphish.txt": ""})["4.2"]
        assert got["status"] == "info", got


class TestGlobalAdminsUnderTheNameGraphActuallyUses:
    """Graph's displayName for the role is "Company Administrator".

    The collector counts both spellings; the report counted one. On a tenant
    reporting the legacy name the count was zero, so CIS 1.1.3 emitted no row
    — every branch tests a count that could not be reached — and the
    admin-sprawl penalty dropped out of the risk score.
    """

    def test_the_legacy_role_name_is_counted(self):
        text = (
            "ADMIN ROLE ASSIGNMENTS\n"
            "======================\n"
            "  Company Administrator                    Ola Nordmann    ola@acme.no\n"
            "  Company Administrator                    Kari Nordmann   kari@acme.no\n"
        )
        out = _parse_admin_roles(text)
        assert out["global_admin_count"] == 2
        assert len(out["global_admin_users"]) == 2

    def test_the_friendly_name_still_counts(self):
        text = (
            "ADMIN ROLE ASSIGNMENTS\n"
            "======================\n"
            "  Global Administrator                     Ola Nordmann    ola@acme.no\n"
        )
        assert _parse_admin_roles(text)["global_admin_count"] == 1


class TestSignInTotalIsNotJustTheUserCount:
    """The collector puts the event count in a banner with no colon, so the
    key/value branch never saw it and the fallback used the number of rows —
    which is the user count. The two figures were always identical."""

    def test_the_banner_event_count_is_read(self):
        text = (
            "=" * 90 + "\n"
            "  SIGN-IN ACTIVITY  (last 30 days — 4821 events)\n"
            + "=" * 90 + "\n"
            "  User                           Last sign-in\n"
            "  " + "-" * 86 + "\n"
            "  ola@acme.no                    2026-01-02\n"
            "  kari@acme.no                   2026-01-03\n"
        )
        out = _parse_signin_risk({"05_signin_activity.txt": text})
        assert out["total_signins"] == 4821
        assert out["unique_users"] == 2
        assert out["total_signins"] != out["unique_users"]


class TestAbsenceIsOnlyEstablishedWhereWeLooked:
    """The OneDrive scan reads permissions on each drive's *root*, so a link
    on a file inside a folder never appears. Zero there is "none at the
    roots", not "none in the tenant"."""

    def test_a_root_only_scan_does_not_attest_a_clean_tenant(self, controls):
        text = (
            "=" * 100 + "\n"
            "  ONEDRIVE / SHAREPOINT EXTERNAL SHARING AUDIT\n"
            + "=" * 100 + "\n"
            "  Drives scanned       : 12\n"
            "  Total shared items   : 3\n"
            "  'Anyone' links       : 0\n"
            "  External user shares : 0\n"
            "  Scan scope           : drive roots only (items within folders not enumerated)\n"
        )
        got = controls({"25_onedrive_sharing.txt": text})["7.2.4"]
        assert got["status"] == "info", got

    def test_a_link_that_was_found_is_still_a_finding(self, controls):
        text = (
            "  'Anyone' links       : 2\n"
            "  Scan scope           : drive roots only (items within folders not enumerated)\n"
        )
        got = controls({"25_onedrive_sharing.txt": text})["7.2.4"]
        assert got["status"] == "fail", got
