"""Teams external and guest access, from the files the Teams collectors write.

CIS 8.1.1 grades the tenant's default cross-tenant access from
16c_teams_external_access.txt, and 8.1.2 its guest settings from
30b_teams_guest_access.txt. Both are read here as a run leaves them, through
a real GraphClient answering from tests/collector_rig.py, and through the
report context itself.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.teams import TeamsSection
from app.modules.m365_audit.sections.teams_policies import TeamsPoliciesSection
from tests.collector_rig import FakeGraph, run_sections
from tests.report_from_run import report

PARTNER_TENANT = "00000000-0000-0000-0000-0000000000b2"
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
