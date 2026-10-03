"""Teams external and guest access, from the files the Teams collectors write.

CIS 8.1.1 grades the tenant's default cross-tenant access from
16c_teams_external_access.txt, and 8.1.2 its guest settings from
30b_teams_guest_access.txt. Each collector writes a text for a person and a
JSON sidecar for the report, which reads the sidecar first and the text for
runs recorded before it. Both are read here as a run leaves them, through a
real GraphClient answering from tests/collector_rig.py, and through the report
context itself.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.teams import TeamsSection
from app.modules.m365_audit.sections.teams_policies import TeamsPoliciesSection
from tests.collector_rig import FakeGraph, refused, run_sections
from tests.report_from_run import relabel, report

PARTNER_TENANT = "00000000-0000-0000-0000-0000000000b2"
MEMBER_ROLE = "a0b1b346-4d3e-4e8b-98f8-753987be4970"  # guests see what members see
LIMITED_ROLE = "10dae51f-b6af-4016-8d66-8c2a99b929b3"


def _access(access_type: str) -> dict:
    return {"usersAndGroups": {"accessType": access_type, "targets": []}}


DEFAULT = {
    "isServiceDefault": False,
    "b2bCollaborationInbound": _access("allowed"),
    "b2bCollaborationOutbound": _access("allowed"),
    "b2bDirectConnectInbound": _access("blocked"),
    "b2bDirectConnectOutbound": _access("blocked"),
}
PARTNERS = [{"tenantId": PARTNER_TENANT, "b2bCollaborationInbound": _access("blocked")}]


def _routes(**overrides) -> dict:
    routes = {
        "groups": [
            {
                "id": "t1",
                "displayName": "Kunde A Ledelse",
                "visibility": "Private",
                "mail": "ledelse@acme.example",
                "createdDateTime": "2025-01-10T08:00:00Z",
            }
        ],
        "teamwork": {"isSkypeForBusinessInteropEnabled": False, "messagingSettings": {}},
        "teamwork/teamTemplates": {"value": []},
        "teamwork/teamsAppSettings": {"isChatResourceSpecificConsentEnabled": False},
        # What a GET on the policy itself returns: its relationships are not in it.
        "policies/crossTenantAccessPolicy": {
            "displayName": "CrossTenantAccessPolicy",
            "allowedCloudEndpoints": [],
        },
        "policies/crossTenantAccessPolicy/default": DEFAULT,
        "policies/crossTenantAccessPolicy/partners": PARTNERS,
        "policies/authorizationPolicy": {
            "allowInvitesFrom": "adminsGuestInvitersAndAllMembers",
            "guestUserRoleId": LIMITED_ROLE,
        },
    }
    routes.update(overrides)
    return routes


async def _teams(tmp_path, **overrides) -> dict[str, str]:
    async with FakeGraph(_routes(**overrides)) as fake:
        files = await run_sections(
            TeamsSection(tmp_path, fake.client), TeamsPoliciesSection(tmp_path, fake.client)
        )
    assert fake.unrouted == []
    return files


def _verdict(ctx: dict, cis_id: str) -> tuple[str, str]:
    row = next(r for r in ctx["compliance"] if r["cis_id"] == cis_id)
    return row["status"], str(row["detail"])


async def test_cross_tenant_access_comes_from_its_own_endpoints(tmp_path):
    """The policy's default and partners are relationships, not properties."""
    files = await _teams(tmp_path)

    external = files["16c_teams_external_access.txt"]
    assert "B2B Collaboration  : allowed" in external
    assert "B2B Direct Connect : blocked" in external
    assert f"Tenant {PARTNER_TENANT} — inbound: blocked" in external
    assert (
        "External Federation Partners    : 1 configured"
        in files["30c_teams_messaging_policies.txt"]
    )

    status, _ = _verdict(report(tmp_path, sidecars=False), "8.1.1")
    assert status == "warn", "graded from the text, not 'cannot verify'"


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_teams_access_verdicts_survive_the_round_trip(tmp_path, sidecars):
    files = await _teams(tmp_path)
    assert "16c_teams_external_access.json" in files and "30b_teams_guest_access.json" in files

    ctx = report(tmp_path, sidecars=sidecars)

    assert _verdict(ctx, "8.1.1") == (
        "warn",
        "B2B Collaboration innkommende tillater ekstern tilgang og bør begrenses mot policy",
    )
    assert _verdict(ctx, "8.1.2") == (
        "warn",
        "Invitasjoner: Admins, Guest Inviters, and Members. "
        "Gjesterolle: Limited access (default). Alle ansatte kan invitere gjester",
    )


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_open_settings_fail_either_way(tmp_path, sidecars):
    await _teams(
        tmp_path,
        **{
            "policies/crossTenantAccessPolicy/default": {
                **DEFAULT,
                "b2bDirectConnectInbound": _access("allowed"),
            },
            "policies/authorizationPolicy": {
                "allowInvitesFrom": "everyone",
                "guestUserRoleId": MEMBER_ROLE,
            },
        },
    )
    ctx = report(tmp_path, sidecars=sidecars)

    assert _verdict(ctx, "8.1.1")[0] == "fail", "Direct Connect inbound is open"
    status, detail = _verdict(ctx, "8.1.2")
    assert status == "fail"
    assert detail.endswith("Gjester har samme tilgang som ansatte")


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_partner_configurations_alone_are_graded_either_way(tmp_path, sidecars):
    """A default with no access types: the partner list is all there is to go on."""
    await _teams(tmp_path, **{"policies/crossTenantAccessPolicy/default": {}})

    assert _verdict(report(tmp_path, sidecars=sidecars), "8.1.1") == (
        "pass",
        "Ekstern tilgang er begrenset",
    )


async def test_the_teams_verdicts_do_not_hang_on_the_text_labels(tmp_path):
    await _teams(tmp_path, **{"policies/crossTenantAccessPolicy/partners": []})
    relabel(tmp_path / "16c_teams_external_access.txt")
    relabel(tmp_path / "30b_teams_guest_access.txt")

    ctx = report(tmp_path)
    assert _verdict(ctx, "8.1.1")[0] == "warn"
    assert _verdict(ctx, "8.1.2")[0] == "warn"

    ctx = report(tmp_path, sidecars=False)
    assert _verdict(ctx, "8.1.1")[0] == "info", "the relabelled text alone says nothing"
    assert _verdict(ctx, "8.1.2")[0] == "info"


async def test_refused_policies_write_no_sidecar(tmp_path):
    files = await _teams(
        tmp_path,
        **{
            "policies/crossTenantAccessPolicy/default": refused(),
            "policies/authorizationPolicy": refused(),
        },
    )
    assert "16c_teams_external_access.json" not in files
    assert "30b_teams_guest_access.json" not in files

    ctx = report(tmp_path)
    assert _verdict(ctx, "8.1.1")[0] == "info", "cannot verify, as before"
    assert _verdict(ctx, "8.1.2")[0] == "info"


async def test_unread_partners_are_unknown_not_none(tmp_path):
    import json

    files = await _teams(tmp_path, **{"policies/crossTenantAccessPolicy/partners": refused()})

    assert "Partner Configurations: not available" in files["16c_teams_external_access.txt"]
    assert json.loads(files["16c_teams_external_access.json"])["partners"] is None
    assert _verdict(report(tmp_path), "8.1.1")[0] == "warn", "the default was still read"
