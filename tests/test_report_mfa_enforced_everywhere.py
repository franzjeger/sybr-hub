"""Two MFA figures: who is covered at all, and who is asked at every sign-in.

"MFA coverage" counts a user who has a method registered, or whom any enabled
Conditional Access policy with an MFA grant reaches. "Require MFA for Azure
management" for all users is such a policy, and it leaves Outlook and Teams
open with a password; a risk-based policy asks only when Entra scores the
sign-in as risky. The report now names a second figure beside the first: users
an enabled MFA policy for *all* apps reaches, judged policy by policy.

Group assignments are read transitively, as Conditional Access applies them, and
a group whose members no read returned is said to be unread instead of empty.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.modules.m365_audit.sections.users_mfa import (
    MFASection,
    UsersSection,
    _policy_applies_to_every_sign_in,
)
from app.reports.parsers import _parse_mfa
from app.reports.parsers.common import _sidecar
from tests.collector_rig import FakeGraph, refused, run_sections


def _user(uid: str) -> dict:
    return {
        "id": uid,
        "displayName": uid.title(),
        "userPrincipalName": f"{uid}@acme.example",
        "accountEnabled": True,
        "userType": "Member",
        "onPremisesSyncEnabled": False,
        "assignedLicenses": [{"skuId": "sku-1"}],
    }


def _policy(pid: str, *, apps=("All",), users=None, risk=(), state="enabled") -> dict:
    return {
        "id": pid,
        "displayName": pid,
        "state": state,
        "conditions": {
            "users": {
                "includeUsers": [],
                "includeGroups": [],
                "excludeUsers": [],
                "excludeGroups": [],
                **(users or {"includeUsers": ["All"]}),
            },
            "applications": {"includeApplications": list(apps)},
            "clientAppTypes": ["all"],
            "signInRiskLevels": list(risk),
        },
        "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
    }


AZURE_MANAGEMENT = "797f4846-ba00-4fd7-ba43-dac1f8f63013"
USERS = [_user("kari"), _user("ola"), _user("per"), _user("nina")]
NO_METHODS = {
    f"users/{u['id']}/authentication/methods": {
        "value": [{"@odata.type": "#microsoft.graph.passwordAuthenticationMethod"}]
    }
    for u in USERS
}


async def _run(tmp_path, policies: list[dict], **routes) -> tuple[dict, dict]:
    all_routes = {
        "users": USERS,
        **NO_METHODS,
        "identity/conditionalAccess/policies": policies,
        "identity/conditionalAccess/namedLocations": [],
        **routes,
    }
    async with FakeGraph(all_routes) as fake:
        users = UsersSection(tmp_path, fake.client)
        ca = ConditionalAccessSection(tmp_path, fake.client)
        mfa_section = MFASection(tmp_path, fake.client, users.users, ca_section=ca)
        files = await run_sections(users, ca, mfa_section, sidecars=True)
    mfa = _parse_mfa(
        files["04_mfa_methods.txt"],
        files["04b_mfa_ca_analysis.txt"],
        [],
        files["04_mfa_methods.json"],
    )
    return mfa, files


async def test_a_policy_for_one_app_is_coverage_but_not_enforcement_everywhere(tmp_path):
    mfa, _ = await _run(tmp_path, [_policy("Azure only", apps=(AZURE_MANAGEMENT,))])

    assert mfa["pct"] == 100.0, "the first figure is unchanged"
    assert mfa["enforced_all_apps"] == 0
    assert mfa["enforced_all_apps_pct"] == 0.0


async def test_a_risk_based_policy_is_not_enforcement_everywhere(tmp_path):
    mfa, _ = await _run(tmp_path, [_policy("Risky sign-ins", risk=("high", "medium"))])

    assert mfa["pct"] == 100.0
    assert mfa["enforced_all_apps"] == 0


async def test_exclusions_are_judged_per_policy(tmp_path):
    """Ola is excluded from the baseline policy and reached only by the app one."""
    policies = [
        _policy("Baseline", users={"includeUsers": ["All"], "excludeUsers": ["ola"]}),
        _policy("Azure only", apps=(AZURE_MANAGEMENT,)),
    ]

    mfa, _ = await _run(tmp_path, policies)

    assert mfa["enforced_all_apps"] == 3
    assert mfa["enforced_all_apps_pct"] == 75.0


async def test_a_nested_group_puts_its_members_in_scope(tmp_path):
    """The policy names a group whose only direct member is another group."""
    policies = [_policy("Baseline", users={"includeGroups": ["outer"]})]
    routes = {
        "groups/outer": {"id": "outer", "displayName": "Alle ansatte", "groupTypes": []},
        "groups/outer/transitiveMembers": [
            {"@odata.type": "#microsoft.graph.group", "id": "inner", "displayName": "Salg"},
            {"@odata.type": "#microsoft.graph.user", "id": "kari", "displayName": "Kari"},
            {"@odata.type": "#microsoft.graph.user", "id": "ola", "displayName": "Ola"},
        ],
    }

    mfa, files = await _run(tmp_path, policies, **routes)

    assert mfa["ca_covered"] == 2
    assert mfa["enforced_all_apps"] == 2
    assert _sidecar(files, "04b_mfa_ca_analysis.txt")["unread_groups"] == []


async def test_a_group_nobody_could_read_is_reported_unread(tmp_path):
    policies = [_policy("Baseline", users={"includeUsers": ["All"], "excludeGroups": ["unntak"]})]
    routes = {
        "groups/unntak": {"id": "unntak", "displayName": "MFA-unntak", "groupTypes": []},
        "groups/unntak/transitiveMembers": refused(),
        "groups/unntak/members": refused(),
    }

    _, files = await _run(tmp_path, policies, **routes)

    unread = _sidecar(files, "04b_mfa_ca_analysis.txt")["unread_groups"]
    assert unread == [{"id": "unntak", "name": "MFA-unntak"}]
    assert "MFA-unntak" in files["04b_mfa_ca_analysis.txt"]


def test_a_run_without_the_field_has_no_second_figure():
    """Older runs carry no answer: the report shows nothing rather than 0%."""
    old = '{"users": [{"display_name": "Kari", "upn": "kari@acme.example", "mfa_registered": true, "ca_covered": true, "ca_excluded": false, "methods": ["Authenticator App"]}]}'
    mfa = _parse_mfa("", "", [], old)
    assert mfa["enforced_all_apps"] is None
    assert mfa["enforced_all_apps_pct"] is None


def test_the_rule_for_a_policy_that_applies_everywhere():
    assert _policy_applies_to_every_sign_in(_policy("p"))
    assert not _policy_applies_to_every_sign_in(_policy("p", apps=("Office365",)))
    assert not _policy_applies_to_every_sign_in(_policy("p", risk=("high",)))
    legacy_only = _policy("p")
    legacy_only["conditions"]["clientAppTypes"] = ["exchangeActiveSync", "other"]
    assert not _policy_applies_to_every_sign_in(legacy_only)
