"""The whole identity domain, from the collectors to the report context.

Every identity collector runs, in the order the audit runs them and wired to
each other as the audit wires them, against one fake tenant. The run directory
is then read the way the report reads it, twice: as written, and with every
JSON sidecar removed, which is how a run from before the sidecars looks. Over a
tenant whose names all fit their columns, the report must say the same thing
either way; that proves build_report_context hands each reader its sidecar and
that the fallback still reads what the collectors write.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.modules.m365_audit.sections.groups_roles import AdminRolesSection, GroupsSection
from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection
from app.modules.m365_audit.sections.password_protection import PasswordProtectionSection
from app.modules.m365_audit.sections.pim import PIMSection
from app.modules.m365_audit.sections.secure_score import SecureScoreSection
from app.modules.m365_audit.sections.signins import SignInsSection
from app.modules.m365_audit.sections.tenant import TenantSection
from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection
from app.reports.generator import _jinja_env, build_report_context
from app.reports.i18n import T
from tests.collector_rig import FakeGraph

LONG_UPN = "anne-marie.christoffersen-haugsland@kunde-a.acme.example"
assert len(LONG_UPN) > 50
LONG_GROUP = "Alle ansatte i Kunde A, avdeling for økonomi og regnskap"
assert len(LONG_GROUP) > 50


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user(uid: str, name: str, *, last: int | None = 2, enabled: bool = True) -> dict:
    return {
        "id": uid,
        "displayName": name,
        "userPrincipalName": f"{uid}@acme.example",
        "accountEnabled": enabled,
        "userType": "Member",
        "onPremisesSyncEnabled": False,
        "assignedLicenses": [{"skuId": "sku-1"}],
        "signInActivity": {"lastSignInDateTime": _ago(last)} if last is not None else None,
    }


USERS = [
    _user("kari", "Kari Nordmann"),
    _user("ola", "Ola Nordmann", last=200),
    _user("per", "Per Hansen"),
    _user("bg", "Break Glass", last=None),
    _user("sluttet", "Sluttet Ansatt", enabled=False),
]

AUTHENTICATOR = {
    "value": [{"@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod"}]
}


def _routes(*, groups: list[dict], risky: list[dict]) -> dict:
    mfa_policy = {
        "id": "p-mfa",
        "displayName": "Krev MFA",
        "state": "enabled",
        "conditions": {
            "users": {"includeUsers": ["All"], "excludeUsers": ["bg"]},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": ["all"],
        },
        "grantControls": {"builtInControls": ["mfa"]},
    }
    legacy_block = {
        "id": "p-legacy",
        "displayName": "Blokker eldre autentisering",
        "state": "enabled",
        "conditions": {
            "users": {"includeUsers": ["All"]},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": ["exchangeActiveSync", "other"],
        },
        "grantControls": {"builtInControls": ["block"]},
    }
    return {
        "organization": {
            "value": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "displayName": "Acme AS",
                    "verifiedDomains": [{"name": "acme.example", "isVerified": True}],
                }
            ]
        },
        "users": USERS,
        "users/kari/authentication/methods": AUTHENTICATOR,
        "users/ola/authentication/methods": {"value": []},
        "users/per/authentication/methods": AUTHENTICATOR,
        "users/bg/authentication/methods": {"value": []},
        "identity/conditionalAccess/policies": [mfa_policy, legacy_block],
        "identity/conditionalAccess/namedLocations": [],
        "auditLogs/signIns": [
            {"userPrincipalName": "per@acme.example", "status": {"errorCode": 50126}}
            for _ in range(60)
        ]
        + [{"userPrincipalName": "kari@acme.example", "status": {"errorCode": 0}}] * 3,
        "groups": groups,
        **{f"groups/{g['id']}/members/$count": 4 for g in groups},
        "directoryRoles": [{"id": "r-ga", "displayName": "Global Administrator"}],
        "directoryRoles/r-ga/members": [USERS[0], USERS[3]],
        "security/secureScores": {
            "value": [
                {
                    "createdDateTime": "2026-10-01T03:00:00Z",
                    "currentScore": 42.0,
                    "maxScore": 100.0,
                    "controlScores": [
                        {
                            "controlName": "scid_mfa",
                            "scoreInPercentage": 50.0,
                            "controlCategory": "Identity",
                        }
                    ],
                }
            ]
        },
        "security/secureScoreControlProfiles": [
            {"id": "scid_mfa", "maxScore": 10.0, "title": "Ensure MFA is enabled for all users"}
        ],
        "policies/authenticationMethodsPolicy": {
            "authenticationMethodConfigurations": [
                {
                    "@odata.type": "#microsoft.graph.fido2AuthenticationMethodConfiguration",
                    "id": "Fido2",
                    "state": "enabled",
                }
            ]
        },
        "identity/conditionalAccess/authenticationStrength/policies": [],
        "riskyUsers": risky,
        "identityProtection/riskDetections": [],
        "policies/authorizationPolicy": {},
        "policies/crossTenantAccessPolicy/default": {
            "isServiceDefault": False,
            "b2bDirectConnectInbound": {"usersAndGroups": {"accessType": "blocked"}},
        },
        "roleManagement/directory/roleEligibilitySchedules": [],
        "auditLogs/directoryAudits": [],
        "security/alerts_v2": [
            {
                "title": "Suspicious inbox forwarding rule",
                "severity": "high",
                "status": "new",
                "createdDateTime": "2026-10-01T08:00:00Z",
            }
        ],
        "identityGovernance/accessReviews/definitions": [],
        "groupSettings": [],
        "beta/settings/passwords": {"enableCustomBannedPasswords": True},
        "policies/identitySecurityDefaultsEnforcementPolicy": {"isEnabled": False},
        "roleManagement/directory/roleEligibilityScheduleInstances": [],
        "roleManagement/directory/roleAssignmentScheduleInstances": [],
        "subscribedSkus": [],
    }


ORDINARY_GROUPS = [
    {"id": "g-1", "displayName": "Salg", "groupTypes": ["Unified"], "mailEnabled": True},
    {"id": "g-2", "displayName": "IT", "securityEnabled": True},
]
ORDINARY_RISKY = [
    {
        "userPrincipalName": "per@acme.example",
        "riskLevel": "high",
        "riskState": "atRisk",
        "riskLastUpdatedDateTime": "2026-09-30T12:00:00Z",
    }
]


async def _audit(
    tmp_path: Path, *, groups=ORDINARY_GROUPS, risky=ORDINARY_RISKY, routes: dict | None = None
) -> Path:
    """Run every identity collector into a run directory, as the audit wires them."""
    out = tmp_path / "Acme_AS" / "2026-10-03_0900"
    out.mkdir(parents=True)
    answers = {**_routes(groups=groups, risky=risky), **(routes or {})}
    async with FakeGraph(answers, page_size=3) as fake:
        graph = fake.client
        users = UsersSection(out, graph)
        ca = ConditionalAccessSection(out, graph)
        admins = AdminRolesSection(out, graph, users_ref=users.users)
        mfa = MFASection(out, graph, users.users, ca_section=ca)
        sections = [
            TenantSection(out, graph),
            users,
            ca,
            mfa,
            SignInsSection(out, graph),
            GroupsSection(out, graph),
            admins,
            SecureScoreSection(out, graph),
            IdentitySecuritySection(
                out,
                graph,
                global_admin_ids=admins.global_admin_ids,
                ca_exclusions=mfa.mfa_excluded_ids,
                users_ref=users.users,
                ca_section=ca,
                mfa_analysis_ran=lambda: mfa.mfa_analysis_ran,
            ),
            PasswordProtectionSection(out, graph),
            PIMSection(out, graph),
        ]
        for section in sections:
            await section.collect()
        assert fake.unrouted == []
    return out


def _copy(run: Path, tmp_path: Path, suffix: str) -> Path:
    """A copy of the run holding only its files with this suffix."""
    copy = tmp_path / f"Acme_AS{suffix.replace('.', '_')}" / run.name
    copy.mkdir(parents=True)
    for path in run.iterdir():
        if path.suffix == suffix:
            shutil.copy(path, copy / path.name)
    return copy


def _without_sidecars(run: Path, tmp_path: Path) -> Path:
    """A copy of the run as it would look from before the sidecars."""
    return _copy(run, tmp_path, ".txt")


def _context(run: Path) -> dict:
    return build_report_context("Acme AS", "acme.example", run, [], persist_metrics=False)


def _identity_view(ctx: dict) -> dict:
    """What the report says about identity, as plain data to compare."""
    controls = ("1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6", "1.1.7", "1.1.8")
    controls += ("1.1.9", "1.2.1", "1.4", "5.1.1", "9.2", "9.3")
    return {
        "users": ctx["users"],
        "mfa": {k: ctx["mfa"][k] for k in ("total", "measured", "pct", "no_mfa", "ca_excluded")},
        "ca": ctx["ca"],
        "admin_roles": {
            k: ctx["admin_roles"][k] for k in ("global_admin_count", "total_assignments", "roles")
        },
        "groups": {k: ctx["groups"][k] for k in ("total", "by_type", "empty_groups")},
        "secure_score": ctx["secure_score"],
        "signin_risk": {
            k: ctx["signin_risk"][k]
            for k in ("total_signins", "unique_users", "total_failures", "brute_force_suspects")
        },
        "stale": [u["upn"] for u in ctx["license_optimization"]["unused_licenses"]],
        "compliance": {
            c["cis_id"]: (c["status"], c["detail"])
            for c in ctx["compliance"]
            if c["cis_id"] in controls
        },
        "risk": (ctx["risk"]["score"], ctx["risk"]["grade"]),
        "recommendations": sorted(r["finding_id"] for r in ctx["recommendations"]),
    }


async def test_the_report_says_the_same_from_the_sidecars_and_from_the_text(tmp_path):
    run = await _audit(tmp_path)
    assert (run / "07_admin_roles.json").exists()

    with_sidecars = _identity_view(_context(run))
    text_only = _identity_view(_context(_without_sidecars(run, tmp_path)))

    assert with_sidecars == text_only
    # And it is a real reading, not two empty ones agreeing.
    assert with_sidecars["users"]["total"] == 5
    assert with_sidecars["admin_roles"]["global_admin_count"] == 2
    assert with_sidecars["groups"]["total"] == 2
    assert with_sidecars["signin_risk"]["brute_force_suspects"] == ["per@acme.example"]
    assert with_sidecars["stale"] == ["ola@acme.example", "bg@acme.example"]
    assert with_sidecars["compliance"]["1.1.6"][0] == "pass"
    assert with_sidecars["compliance"]["5.1.1"][0] == "pass"
    assert with_sidecars["compliance"]["9.3"][0] == "fail"
    assert "finding-risky" in with_sidecars["recommendations"]


async def test_every_identity_reader_is_handed_its_sidecar(tmp_path):
    """With only the sidecars on disk, the report must still say all of it.

    A reader the context builder forgot to hand its sidecar would read an empty
    text here and report nothing.
    """
    run = await _audit(tmp_path)

    full = _identity_view(_context(run))
    sidecars_only = _identity_view(_context(_copy(run, tmp_path, ".json")))

    assert sidecars_only == full


async def test_without_per_user_records_the_mfa_figures_come_from_the_ca_analysis(tmp_path):
    """_parse_mfa's own fallback, handed 04b_mfa_ca_analysis.json by the context builder."""
    run = await _audit(tmp_path)
    only = _copy(run, tmp_path, ".json")
    (only / "04_mfa_methods.json").unlink()

    mfa = _context(only)["mfa"]

    # Four active members, all in the policy, Break Glass excluded from it.
    assert (mfa["total"], mfa["covered"], mfa["ca_excluded"], mfa["pct"]) == (4, 3, 1, 75.0)


async def test_the_sidecars_reach_the_report_where_the_text_falls_short(tmp_path):
    run = await _audit(
        tmp_path,
        groups=[
            *ORDINARY_GROUPS,
            {"id": "g-3", "displayName": LONG_GROUP, "securityEnabled": True},
        ],
        risky=[
            {
                "userPrincipalName": LONG_UPN,
                "riskLevel": "high",
                "riskState": "atRisk",
                "riskLastUpdatedDateTime": "2026-09-30T12:00:00Z",
            }
        ],
    )

    ctx = _context(run)

    assert ctx["groups"]["total"] == 3
    assert ctx["risky_user_rows"] == [{"upn": LONG_UPN, "level": "high", "state": "atRisk"}]
    assert ctx["compliance"] and next(c for c in ctx["compliance"] if c["cis_id"] == "9.3")[
        "detail"
    ].startswith("1 brukere med høy eller middels risiko")

    # The customer report's risky-user table shows the whole UPN and its level.
    html = _render(ctx, "report_customer.html.j2")
    assert f'<td style="font-size:12px;">{LONG_UPN}</td>' in html
    assert '<span class="tag tag-no">høy</span>' in html  # Graph's "high", in Norwegian


def _render(ctx: dict, template: str) -> str:
    ctx["t"], ctx["lang"], ctx["theme"] = T("no"), "no", "light"
    return _jinja_env().get_template(template).render(**ctx)


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_clean_tenant_shows_no_risky_users_and_no_defender_alerts(tmp_path, sidecars):
    """The collectors write a "(0 total)" table for a clean tenant, not "No risky users".

    The templates treated any such file as a finding unless it held "No risky"
    or "No active", phrases no collector writes: every clean tenant's customer
    report carried a "risky users detected" card, and its technical report
    listed Defender alerts and risky users under critical findings and never
    said there were none.
    """
    run = await _audit(tmp_path, risky=[], routes={"security/alerts_v2": []})
    ctx = _context(run if sidecars else _without_sidecars(run, tmp_path))
    t = T("no")

    customer = _render(dict(ctx), "report_customer.html.j2")
    tech = _render(dict(ctx), "report_tech.html.j2")

    assert 'id="finding-risky"' not in customer
    assert t.active_defender_alerts not in tech
    assert t.risky_users_idp not in tech
    assert t.no_critical_findings in tech


async def test_a_tenant_with_alerts_and_risky_users_still_shows_them(tmp_path):
    run = await _audit(tmp_path)
    ctx = _context(run)
    t = T("no")

    customer = _render(dict(ctx), "report_customer.html.j2")
    tech = _render(dict(ctx), "report_tech.html.j2")

    assert 'id="finding-risky"' in customer
    assert t.active_defender_alerts in tech
    assert t.risky_users_idp in tech
    assert t.no_critical_findings not in tech
