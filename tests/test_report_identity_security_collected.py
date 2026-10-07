"""Risky users, PIM, break-glass, access reviews, cross-tenant access and Defender
alerts, read back from what the Identity Security collector writes.

Six of its files now have JSON twins, and every reader of them prefers it:
CIS 1.1.5, 1.1.6, 1.1.8, 1.1.9, 9.2 and 9.3, the risk score, and the risky-users
recommendation. Over the same tenant each must reach the same verdict from the
sidecar as from the text. The risky-users table is where the text fell short:
it cuts a UPN to 50 characters and pads it to that width, so a UPN that long
runs into the risk level, and every reader took the state for the level until
the rows were read by the collector's columns. The text still cuts the UPN.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
from app.reports.compliance import _build_compliance_map
from app.reports.recommendations import _build_recommendations
from app.reports.risk import _compute_risk
from tests.collector_rig import FakeGraph, refused, run_sections

LONG_UPN = "anne-marie.christoffersen-haugsland@kunde-a.acme.example"
assert len(LONG_UPN) > 50

LICENCE_GAP = refused(
    403,
    "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
    "Tenant does not have a SKU required by this API.",
)


def _risky(upn: str, level: str, state: str) -> dict:
    return {
        "userPrincipalName": upn,
        "userDisplayName": upn.split("@")[0],
        "riskLevel": level,
        "riskState": state,
        "riskDetail": "none",
        "riskLastUpdatedDateTime": "2026-09-30T12:00:00Z",
    }


ORDINARY_RISKY = [
    _risky("kari@acme.example", "high", "atRisk"),
    _risky("ola@acme.example", "low", "atRisk"),
    _risky("per@acme.example", "medium", "remediated"),
]


def _eligibility(role: str, principal: str) -> dict:
    return {
        "roleDefinition": {"displayName": role},
        "principal": {
            "@odata.type": "#microsoft.graph.user",
            "displayName": principal,
            "userPrincipalName": f"{principal.lower()}@acme.example",
        },
        "scheduleInfo": {"expiration": {"endDateTime": None}},
    }


def _alert(title: str, severity: str) -> dict:
    return {
        "id": f"alert-{title[:4]}",
        "title": title,
        "severity": severity,
        "status": "new",
        "createdDateTime": "2026-10-01T08:00:00Z",
    }


def _cross_tenant(direct_in: str, *, service_default: bool = False) -> dict:
    return {
        "isServiceDefault": service_default,
        "b2bCollaborationInbound": {"usersAndGroups": {"accessType": "allowed"}},
        "b2bCollaborationOutbound": {"usersAndGroups": {"accessType": "allowed"}},
        "b2bDirectConnectInbound": {"usersAndGroups": {"accessType": direct_in}},
    }


def _routes(**overrides) -> dict:
    routes = {
        "identityProtection/riskyUsers": ORDINARY_RISKY,
        "identityProtection/riskDetections": [],
        "policies/authorizationPolicy": {"allowInvitesFrom": "everyone"},
        "policies/crossTenantAccessPolicy/default": _cross_tenant("blocked"),
        "roleManagement/directory/roleEligibilitySchedules": [
            _eligibility("Global Administrator", "Kari"),
            _eligibility("Exchange Administrator", "Ola"),
        ],
        "auditLogs/directoryAudits": [],
        "security/alerts_v2": [
            _alert("Suspicious inbox forwarding rule", "high"),
            _alert("Unusual sign-in activity", "medium"),
        ],
        "identityGovernance/accessReviews/definitions": [
            {
                "id": "rev-1",
                "displayName": "Kvartalsvis gjennomgang av gjester",
                "status": "InProgress",
                "settings": {"recurrence": {"pattern": {"type": "absoluteMonthly"}}},
                "createdDateTime": "2026-01-10T09:00:00Z",
            }
        ],
        # Break-glass: one Global Admin with no MFA method and excluded from CA,
        # one with an authenticator.
        "users/u-bg/authentication/methods": {"value": []},
        "users/u-kari/authentication/methods": {
            "value": [
                {"@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod"}
            ]
        },
    }
    routes.update(overrides)
    return routes


USERS = [
    {"id": "u-bg", "userPrincipalName": "breakglass@acme.example", "signInActivity": None},
    {
        "id": "u-kari",
        "userPrincipalName": "kari@acme.example",
        "signInActivity": {"lastSignInDateTime": "2020-01-01T00:00:00Z"},
    },
]


async def _collect(tmp_path, *, sidecars: bool, admins=("u-bg", "u-kari"), **overrides) -> dict:
    async with FakeGraph(_routes(**overrides)) as fake:
        section = IdentitySecuritySection(
            tmp_path,
            fake.client,
            global_admin_ids=list(admins),
            ca_exclusions={"u-bg"},
            users_ref=USERS,
            ca_section=SimpleNamespace(policies=[{"id": "p-mfa"}]),
            mfa_analysis_ran=lambda: True,
        )
        files = await run_sections(section, sidecars=sidecars)
        assert fake.unrouted == []
    return files


def _context(files: dict) -> dict:
    """What build_report_context hands the checks: the files, and two of them as text."""
    return {
        "file_contents": files,
        "risky_users": files.get("18_risky_users.txt", ""),
        "defender_alerts": files.get("19b_defender_active_alerts.txt", ""),
    }


def _verdicts(files: dict) -> dict[str, tuple[str, str]]:
    return {r["cis_id"]: (r["status"], r["detail"]) for r in _build_compliance_map(_context(files))}


def _risk(files: dict) -> dict:
    """The risk score with every other input clean, so only these two move it."""
    return _compute_risk(
        secure_score={"has_data": True, "pct": 100.0},
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        all_warns=[],
        ext_fwd="",
        risky_users=files.get("18_risky_users.txt", ""),
        defender=files.get("19b_defender_active_alerts.txt", ""),
        file_contents=files,
    )


def _risky_rec(files: dict) -> dict | None:
    recs = _build_recommendations(
        mfa={"has_data": False},
        spf_dmarc=[],
        secure_score={"has_data": False},
        ext_fwd="",
        risky_users=files.get("18_risky_users.txt", ""),
        licenses=[],
        file_contents=files,
    )
    return next((r for r in recs if r["finding_id"] == "finding-risky"), None)


SIDECARS = (
    "18_risky_users.json",
    "07b_pim_eligible_assignments.json",
    "07c_emergency_access_check.json",
    "07d_access_reviews.json",
    "18c_cross_tenant_access_policy.json",
    "19b_defender_active_alerts.json",
)


# ── The same tenant, read from either file ────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_every_verdict_agrees_from_either_file(tmp_path, sidecars):
    files = await _collect(tmp_path, sidecars=sidecars)
    assert {name for name in SIDECARS if name in files} == (set(SIDECARS) if sidecars else set())

    verdicts = _verdicts(files)

    assert verdicts["1.1.5"] == ("pass", "2 PIM-berettigede rolletildelinger funnet")
    assert verdicts["1.1.6"] == ("pass", "1 nødtilgangskonto(er) (break glass) oppdaget")
    assert verdicts["1.1.8"] == ("pass", "1 tilgangsgjennomgang(er) definert")
    assert verdicts["1.1.9"][0] == "pass"
    assert verdicts["9.2"] == ("warn", "2 aktive Defender-varsler krever oppfølging")
    assert verdicts["9.3"] == (
        "fail",
        "2 brukere med høy eller middels risiko er oppdaget og må undersøkes",
    )
    # Five for the risky users, three plus one per open alert.
    assert _risk(files)["score"] == 100 - 5 - (3 + 2)
    rec = _risky_rec(files)
    assert rec is not None
    assert [item.split()[0] for item in rec["sub_items"]] == [
        "kari@acme.example",
        "ola@acme.example",
    ], "a remediated user is not a live risk"


async def test_the_sidecars_are_what_the_readers_read(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    for name in SIDECARS:
        files[name.replace(".json", ".txt")] = ""

    verdicts = _verdicts(files)

    assert verdicts["1.1.5"][0] == "pass"
    assert verdicts["1.1.6"][0] == "pass"
    assert verdicts["1.1.8"][0] == "pass"
    assert verdicts["1.1.9"][0] == "pass"
    assert verdicts["9.2"][0] == "warn"
    assert verdicts["9.3"][0] == "fail"
    assert _risk(files)["score"] == 90
    assert _risky_rec(files) is not None


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_clean_tenant_passes_from_either_file(tmp_path, sidecars):
    files = await _collect(
        tmp_path,
        sidecars=sidecars,
        **{"identityProtection/riskyUsers": []},
        **{
            "security/alerts_v2": [],
            "identityGovernance/accessReviews/definitions": [],
            "roleManagement/directory/roleEligibilitySchedules": [],
        },
    )

    verdicts = _verdicts(files)

    assert verdicts["9.3"][0] == "pass"
    assert verdicts["9.2"][0] == "pass"
    assert verdicts["1.1.8"][0] == "warn"
    assert verdicts["1.1.5"][0] == "warn"
    assert _risk(files)["score"] == 100
    assert _risky_rec(files) is None


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
@pytest.mark.parametrize(
    "policy, expected",
    [
        (_cross_tenant("allowed"), "warn"),
        (_cross_tenant("blocked", service_default=True), "warn"),
        (_cross_tenant("blocked"), "pass"),
    ],
    ids=["direct connect allowed", "service default", "decided"],
)
async def test_cross_tenant_access_agrees_from_either_file(tmp_path, policy, expected, sidecars):
    files = await _collect(
        tmp_path, sidecars=sidecars, **{"policies/crossTenantAccessPolicy/default": policy}
    )

    assert _verdicts(files)["1.1.9"][0] == expected


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_break_glass_check_without_admins_is_unverified_from_either_file(
    tmp_path, sidecars
):
    files = await _collect(tmp_path, sidecars=sidecars, admins=())

    assert _verdicts(files)["1.1.6"][0] == "info"


# ── What only the sidecar can carry ───────────────────────────────────────────

RISKY_WITH_LONG_UPN = [
    _risky("kari@acme.example", "high", "atRisk"),
    # Medium risk, already remediated: counted by 9.3, not listed as a live risk.
    _risky(LONG_UPN, "medium", "remediated"),
]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_long_upn_keeps_its_risk_level_and_state(tmp_path, sidecars):
    """The table cuts the UPN to 50 and pads it to that width.

    A UPN that long left one space before the level, and the text was split on
    runs of spaces: the medium level went uncounted by 9.3 and the remediated
    user was listed as a live risk. Its rows are now read by the collector's
    columns, so the text gives the sidecar's answer.
    """
    files = await _collect(
        tmp_path, sidecars=sidecars, **{"identityProtection/riskyUsers": RISKY_WITH_LONG_UPN}
    )

    assert _verdicts(files)["9.3"] == (
        "fail",
        "2 brukere med høy eller middels risiko er oppdaget og må undersøkes",
    )
    rec = _risky_rec(files)
    assert rec is not None
    assert len(rec["sub_items"]) == 1 and rec["sub_items"][0].startswith("kari@acme.example")


# ── Failed reads write no sidecar ─────────────────────────────────────────────


async def test_failed_reads_write_no_sidecar_and_stay_unverified(tmp_path):
    files = await _collect(
        tmp_path,
        sidecars=True,
        **{"identityProtection/riskyUsers": LICENCE_GAP},
        **{
            "roleManagement/directory/roleEligibilitySchedules": refused(),
            "identityGovernance/accessReviews/definitions": refused(),
            "policies/crossTenantAccessPolicy/default": refused(),
            "security/alerts_v2": refused(),
        },
    )

    for name in SIDECARS:
        if name != "07c_emergency_access_check.json":
            assert name not in files, name
    verdicts = _verdicts(files)
    for cis_id in ("1.1.5", "1.1.8", "1.1.9", "9.2", "9.3"):
        assert verdicts[cis_id][0] == "info", cis_id
    risk = _risk(files)
    assert risk["score"] == 100
    assert any("Risikobrukere ikke vurdert" in issue for issue in risk["data_quality_issues"])
    assert _risky_rec(files) is None
