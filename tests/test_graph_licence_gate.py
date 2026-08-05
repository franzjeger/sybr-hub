"""A refused Graph collection has two causes, and they need opposite fixes.

Graph answers "you may not read this" and "your tenant is not licensed for
this" with the same 403. The report has to tell them apart: one is a consent
to grant in our own app registration, the other is a SKU the customer has not
bought — which is a finding *about the customer*, and an actionable one.

auditLogs/signIns is the case that mattered. It is gated on Entra ID P1, so
AuditLog.Read.All can be granted and consented and the endpoint still answers
403. The collector wrote nothing at all on that 403, so the whole sign-in
analysis disappeared from the report with no heading and no note — a reader
could not tell it had ever been attempted.
"""

from __future__ import annotations

import json

import pytest

from app.core.encryption import encrypted_read_text
from app.modules.base import SectionStatus
from app.modules.m365_audit.graph_client import GraphPermissionError
from app.reports.generator import _evidence_unavailable, _parse_signin_risk

_LICENCE_BODY = json.dumps({
    "error": {
        "code": "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
        "message": "Neither tenant is B2C or tenant doesn't have premium license",
    }
})
_PERMISSION_BODY = json.dumps({
    "error": {
        "code": "Authorization_RequestDenied",
        "message": "Insufficient privileges to complete the operation.",
    }
})


def _read(path):
    """Collector output is written encrypted at rest."""
    return encrypted_read_text(path)


class TestTheRefusalNamesItsOwnCause:
    def test_a_licence_gap_is_recognised(self):
        err = GraphPermissionError("auditLogs/signIns", 403, _LICENCE_BODY)
        assert err.is_licence_gap
        assert err.code == "Authentication_RequestFromNonPremiumTenantOrB2CTenant"
        assert "licence" in str(err).lower()
        assert "missing a permission" not in str(err)

    def test_a_permission_refusal_is_not_called_a_licence_gap(self):
        err = GraphPermissionError("riskyUsers", 403, _PERMISSION_BODY)
        assert not err.is_licence_gap
        assert "permission or admin consent" in str(err)

    def test_an_unparseable_body_does_not_guess(self):
        err = GraphPermissionError("x", 403, "<html>gateway error</html>")
        assert not err.is_licence_gap
        assert err.code == ""
        assert "gateway error" in str(err)

    def test_the_status_and_path_survive_for_the_log(self):
        err = GraphPermissionError("auditLogs/signIns", 401, _LICENCE_BODY)
        assert err.status == 401
        assert err.path == "auditLogs/signIns"


class TestTheCollectorRecordsWhyThereIsNoData:
    def _section(self, tmp_path, body):
        from app.modules.m365_audit.sections.signins import SignInsSection

        class _Graph:
            async def get_all(self, path, **kw):
                raise GraphPermissionError(path, 403, body)

        return SignInsSection(tmp_path, _Graph())

    async def test_a_licence_gap_writes_both_files_and_names_the_tier(self, tmp_path):
        section = self._section(tmp_path, _LICENCE_BODY)
        result = await section.collect()

        activity = _read(tmp_path / "05_signin_activity.txt")
        failures = _read(tmp_path / "05b_signin_failures.txt")
        assert "(not available)" in activity and "(not available)" in failures
        assert "Entra ID P1" in activity
        assert "licence gap" in activity
        # Still not a measurement: the tenant's sign-in posture is unknown.
        assert result.status is SectionStatus.FAILED

    async def test_a_permission_refusal_does_not_blame_the_licence(self, tmp_path):
        section = self._section(tmp_path, _PERMISSION_BODY)
        await section.collect()

        activity = _read(tmp_path / "05_signin_activity.txt")
        assert "AuditLog.Read.All" in activity
        assert "licence gap" not in activity
        # The tier requirement is still worth stating — granting the permission
        # alone will not make it readable on a tenant without P1.
        assert "Entra ID P1" in activity


class TestTheReportReadsTheExplanationAsAnAbsence:
    @pytest.mark.parametrize("text", [
        "",
        "Error: could not collect\n",
        "  SIGN-IN ACTIVITY  (not available)\n  requires Microsoft Entra ID P1\n",
        "Risk detections krever Microsoft Entra ID P2.\n",
    ])
    def test_prose_about_an_absence_is_not_evidence(self, text):
        assert _evidence_unavailable(text)

    def test_a_real_reading_is_evidence(self):
        assert not _evidence_unavailable(
            "  SIGN-IN ACTIVITY  (last 30 days — 1234 events)\n"
            "  ola@acme.no    100    2    0    102\n"
        )

    def test_the_unavailable_file_does_not_become_a_tenant_with_zero_signins(self):
        """has_data was set by the file merely existing, so an explanation of
        why nothing was measured would have published 0 sign-ins and 0
        failures as findings about the customer."""
        out = _parse_signin_risk({
            "05_signin_activity.txt":
                "  SIGN-IN ACTIVITY  (not available)\n"
                "  Graph reported a licence gap: requires Microsoft Entra ID P1\n",
            "05b_signin_failures.txt": "  SIGN-IN FAILURES  (not available)\n",
        })
        assert out["has_data"] is False
        assert out["total_signins"] == 0
        assert out["no_data_reason"] == "license_p1_missing"

    def test_a_permission_gap_is_not_reported_as_a_licence_gap(self):
        out = _parse_signin_risk({
            "05_signin_activity.txt":
                "  SIGN-IN ACTIVITY  (not available)\n"
                "  The app registration is missing AuditLog.Read.All.\n",
        })
        assert out["no_data_reason"] == "not_collected"

    def test_a_missing_file_still_reads_as_not_collected(self):
        out = _parse_signin_risk({})
        assert out["has_data"] is False
        assert out["no_data_reason"] == "not_collected"

    def test_a_real_audit_still_parses(self):
        out = _parse_signin_risk({
            "05_signin_activity.txt":
                "=" * 90 + "\n"
                "  SIGN-IN ACTIVITY  (last 30 days — 4,210 events)\n"
                + "=" * 90 + "\n"
                "  ola@acme.no                    100        2        0    102\n",
        })
        assert out["has_data"] is True
        assert out["no_data_reason"] is None
        assert out["total_signins"] == 4210


class TestTheDocumentSaysSoRatherThanDroppingTheSection:
    def test_the_template_branches_on_the_reason(self):
        from pathlib import Path

        tpl = Path("app/reports/templates/report_tech.html.j2").read_text()
        assert "signin_risk.no_data_reason" in tpl
        assert "signin_no_data_license" in tpl
        assert "signin_no_data_not_collected" in tpl

    @pytest.mark.parametrize(
        "key", ["signin_no_data_license", "signin_no_data_not_collected"]
    )
    def test_both_strings_exist_in_both_languages(self, key):
        from app.reports.i18n import TRANSLATIONS

        assert key in TRANSLATIONS
        assert TRANSLATIONS[key]["no"] and TRANSLATIONS[key]["en"]
