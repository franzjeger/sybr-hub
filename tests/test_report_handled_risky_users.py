"""A risky user that has been remediated or dismissed is not a finding.

Entra keeps every user it has ever flagged in identityProtection/riskyUsers,
with the riskState saying what became of it. The recommendations already left
the handled ones out, but the risk score took the collector's row count, CIS 9.3
counted every row, and the customer's card listed them all. A tenant that had
dealt with each of its risky users still lost five points, failed the control
on a remediated medium-risk user, and was shown the users under "critical
findings" with no recommendation beside them.

The collector runs here, so every reader sees what a real run leaves on disk,
with the sidecar and from the text alone.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
from app.reports.compliance import _build_compliance_map
from app.reports.generator import _live_risky_rows
from app.reports.recommendations import _build_recommendations
from app.reports.risk import _compute_risk, _live_risky_count
from tests.collector_rig import FakeGraph, run_sections


def _risky(upn: str, level: str, state: str) -> dict:
    return {
        "userPrincipalName": upn,
        "userDisplayName": upn.split("@")[0],
        "riskLevel": level,
        "riskState": state,
        "riskDetail": "none",
        "riskLastUpdatedDateTime": "2026-09-30T12:00:00Z",
    }


ALL_HANDLED = [
    _risky("kari@acme.example", "high", "remediated"),
    _risky("ola@acme.example", "medium", "dismissed"),
    _risky("per@acme.example", "low", "confirmedSafe"),
]
ONE_STILL_OPEN = [*ALL_HANDLED, _risky("nina@acme.example", "low", "atRisk")]
COMPROMISED = [*ALL_HANDLED, _risky("nina@acme.example", "high", "confirmedCompromised")]


async def _collect(tmp_path, users: list[dict], *, sidecars: bool) -> dict:
    routes = {
        "identityProtection/riskyUsers": users,
        "identityProtection/riskDetections": [],
        "policies/authorizationPolicy": {"allowInvitesFrom": "everyone"},
        "policies/crossTenantAccessPolicy/default": {"isServiceDefault": True},
        "roleManagement/directory/roleEligibilitySchedules": [],
        "auditLogs/directoryAudits": [],
        "security/alerts_v2": [],
        "identityGovernance/accessReviews/definitions": [],
    }
    async with FakeGraph(routes) as fake:
        section = IdentitySecuritySection(
            tmp_path,
            fake.client,
            global_admin_ids=[],
            ca_exclusions=set(),
            users_ref=[],
            ca_section=SimpleNamespace(policies=[]),
            mfa_analysis_ran=lambda: True,
        )
        return await run_sections(section, sidecars=sidecars)


def _score(files: dict) -> int:
    return _compute_risk(
        secure_score={"has_data": True, "pct": 100.0},
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        all_warns=[],
        ext_fwd="",
        risky_users=files.get("18_risky_users.txt", ""),
        defender=files.get("19b_defender_active_alerts.txt", ""),
        file_contents=files,
    )["score"]


def _cis_93(files: dict) -> str:
    context = {
        "file_contents": files,
        "risky_users": files.get("18_risky_users.txt", ""),
        "defender_alerts": files.get("19b_defender_active_alerts.txt", ""),
    }
    return next(r["status"] for r in _build_compliance_map(context) if r["cis_id"] == "9.3")


def _recommended(files: dict) -> bool:
    recs = _build_recommendations(
        mfa={"has_data": False},
        spf_dmarc=[],
        secure_score={"has_data": False},
        ext_fwd="",
        risky_users=files.get("18_risky_users.txt", ""),
        licenses=[],
        file_contents=files,
    )
    return any(r["finding_id"] == "finding-risky" for r in recs)


BOTH = pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])


@BOTH
async def test_a_tenant_whose_risky_users_are_all_handled_is_clean(tmp_path, sidecars):
    handled = await _collect(tmp_path / "handled", ALL_HANDLED, sidecars=sidecars)
    nobody = await _collect(tmp_path / "nobody", [], sidecars=sidecars)

    assert _score(handled) == _score(nobody)
    assert _cis_93(handled) == "pass"
    assert _live_risky_count(handled, handled["18_risky_users.txt"]) == 0
    # And the score agrees with the recommendations, which never listed them.
    assert _recommended(handled) is False


@BOTH
async def test_one_user_still_at_risk_is_the_only_one_counted(tmp_path, sidecars):
    files = await _collect(tmp_path / "open", ONE_STILL_OPEN, sidecars=sidecars)
    nobody = await _collect(tmp_path / "nobody", [], sidecars=sidecars)

    assert _score(files) == _score(nobody) - 5
    # Low risk and open: a warning. The handled high and medium ones used to
    # make this a failure.
    assert _cis_93(files) == "warn"
    assert _live_risky_count(files, files["18_risky_users.txt"]) == 1
    assert _recommended(files) is True


@BOTH
async def test_a_confirmed_compromise_still_fails_the_control(tmp_path, sidecars):
    files = await _collect(tmp_path, COMPROMISED, sidecars=sidecars)
    assert _cis_93(files) == "fail"
    assert _live_risky_count(files, files["18_risky_users.txt"]) == 1


async def test_the_customer_card_lists_only_the_users_still_at_risk(tmp_path):
    files = await _collect(tmp_path, ONE_STILL_OPEN, sidecars=True)
    assert [u["upn"] for u in _live_risky_rows(files)] == ["nina@acme.example"]
