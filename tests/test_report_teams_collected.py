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

from app.modules.base import SectionStatus
from app.modules.m365_audit.sections.teams import TeamsSection
from app.modules.m365_audit.sections.teams_policies import GUEST_ROLES, TeamsPoliciesSection
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
        "Inbound B2B Collaboration allows external access and should be restricted to policy",
    )
    assert _verdict(ctx, "8.1.2") == (
        "warn",
        "Invitations: Admins, Guest Inviters, and Members. "
        "Guest role: Limited access (default). Every employee can invite guests",
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
    assert detail.endswith("Guests have the same access as employees")


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_partner_configurations_alone_are_graded_either_way(tmp_path, sidecars):
    """A default with no access types: the partner list is all there is to go on."""
    await _teams(tmp_path, **{"policies/crossTenantAccessPolicy/default": {}})

    assert _verdict(report(tmp_path, sidecars=sidecars), "8.1.1") == (
        "pass",
        "External access is restricted",
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


@pytest.mark.parametrize(
    "setting", [None, {"usersAndGroups": None}, {"usersAndGroups": {"accessType": None}}]
)
async def test_null_teams_settings_do_not_crash_or_become_restricted(tmp_path, setting):
    """Real Graph nulls used to stop the section before its evidence was saved."""
    import json

    routes = _routes(
        **{
            "teamwork": {"messagingSettings": None},
            "policies/crossTenantAccessPolicy/default": {
                "b2bCollaborationInbound": setting,
                "b2bCollaborationOutbound": setting,
                "b2bDirectConnectInbound": setting,
            },
            "policies/crossTenantAccessPolicy/partners": [],
        }
    )
    async with FakeGraph(routes) as fake:
        sections = [
            TeamsSection(tmp_path, fake.client),
            TeamsPoliciesSection(tmp_path, fake.client),
        ]
        files = await run_sections(*sections)
    assert fake.unrouted == []
    assert all(section.result.status is SectionStatus.DONE for section in sections)
    assert "Allow User Edit Messages       : N/A" in files["16b_teams_settings.txt"]
    assert "Allow User Edit Messages        : N/A" in files["30c_teams_messaging_policies.txt"]
    access = json.loads(files["16c_teams_external_access.json"])
    assert access["b2b_collaboration_inbound"] is None
    assert access["b2b_direct_connect_inbound"] is None
    guest = json.loads(files["30b_teams_guest_access.json"])
    assert guest["cross_tenant_defaults"] == {
        "b2b_collaboration_inbound": None,
        "b2b_collaboration_outbound": None,
        "b2b_direct_connect_inbound": None,
    }
    for sidecars in (True, False):
        assert _verdict(report(tmp_path, sidecars=sidecars), "8.1.1")[0] == "info"


@pytest.mark.parametrize("setting", [None, {"usersAndGroups": None}])
async def test_null_partner_override_preserves_default_evidence(tmp_path, setting):
    """Partner null means inheritance, not a broken collection or blocked access.

    https://learn.microsoft.com/en-us/graph/api/resources/crosstenantaccesspolicy-overview
    """
    import json

    files = await _teams(
        tmp_path,
        **{
            "policies/crossTenantAccessPolicy/partners": [
                {"tenantId": PARTNER_TENANT, "b2bCollaborationInbound": setting},
            ],
        },
    )
    assert f"Tenant {PARTNER_TENANT} — inbound: N/A" in files["16c_teams_external_access.txt"]
    assert (
        json.loads(files["16c_teams_external_access.json"])["partners"][0][
            "b2b_collaboration_inbound"
        ]
        is None
    )
    assert _verdict(report(tmp_path), "8.1.1")[0] == "warn"


# ── The guest settings are Graph's values, worded by the report ─────────────
#
# teams_policies.py wrote its own English labels for them ("Admins and Guest
# Inviters", "Limited access (default)"), and CIS 8.1.2 set those inside a
# Norwegian sentence (TODO C15).


async def test_the_guest_settings_are_stored_as_graph_values(tmp_path):
    import json

    files = await _teams(tmp_path)

    guest = json.loads(files["30b_teams_guest_access.json"])
    assert guest["allow_invites_from"] == "adminsGuestInvitersAndAllMembers"
    assert guest["guest_user_role_id"] == LIMITED_ROLE
    assert "allow_invites_from_label" not in guest and "guest_user_role" not in guest
    text = files["30b_teams_guest_access.txt"]
    assert "Allow Invites From       : adminsGuestInvitersAndAllMembers" in text
    assert f"Guest User Role          : limited ({LIMITED_ROLE})" in text


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_norwegian_report_words_the_guest_settings(tmp_path, sidecars):
    await _teams(tmp_path)

    assert _verdict(report(tmp_path, sidecars=sidecars, lang="no"), "8.1.2") == (
        "warn",
        "Invitasjoner: Administratorer, gjesteinvitører og medlemmer. "
        "Gjesterolle: Begrenset tilgang (standard). Alle ansatte kan invitere gjester",
    )


# The two shapes a run written before the collector stored Graph's values
# left on disk: the sidecar beside its English labels, and the text alone.
_OLD_TEXT = (
    "==========================================================================================\n"
    "  TEAMS / ENTRA ID GUEST ACCESS SETTINGS\n"
    "==========================================================================================\n"
    "  Allow Invites From       : {invites}\n"
    "  Guest User Role          : {role}\n"
)


@pytest.mark.parametrize(
    ("invites", "role", "expected"),
    [
        (
            "Everyone (most open)",
            "Same as member users",
            (
                "fail",
                "Invitasjoner: Alle (mest åpent). Gjesterolle: Samme som medlemmer. "
                "Gjester har samme tilgang som ansatte",
            ),
        ),
        (
            "Admins and Guest Inviters",
            "Restricted access (most restrictive)",
            (
                "pass",
                "Invitasjoner: Administratorer og gjesteinvitører. "
                "Gjesterolle: Sterkt begrenset tilgang (mest restriktivt)",
            ),
        ),
        (
            "No one (most restrictive)",
            "Limited access (default)",
            (
                "pass",
                "Invitasjoner: Ingen (mest restriktivt). Gjesterolle: Begrenset tilgang (standard)",
            ),
        ),
    ],
)
@pytest.mark.parametrize("shape", ["old sidecar", "text only"])
def test_an_old_runs_english_labels_are_worded(tmp_path, invites, role, expected, shape):
    """A report regenerated from an old run reads its labels back to codes."""
    import json

    from app.core.encryption import encrypted_write_text

    encrypted_write_text(
        tmp_path / "30b_teams_guest_access.txt", _OLD_TEXT.format(invites=invites, role=role)
    )
    if shape == "old sidecar":
        ids = {v: k for k, v in GUEST_ROLES.items()}
        code = {"Same as member users": "member", "Limited access (default)": "limited"}
        encrypted_write_text(
            tmp_path / "30b_teams_guest_access.json",
            json.dumps(
                {
                    "allow_invites_from": {
                        "Everyone (most open)": "everyone",
                        "Admins and Guest Inviters": "adminsAndGuestInviters",
                        "No one (most restrictive)": "none",
                    }[invites],
                    "allow_invites_from_label": invites,
                    "guest_user_role_id": ids[code.get(role, "restricted")],
                    "guest_user_role": role,
                }
            ),
        )

    assert _verdict(report(tmp_path, lang="no"), "8.1.2") == expected


def test_a_value_nobody_names_is_shown_as_stored(tmp_path):
    """A setting Graph adds later, or an id that is not a built-in role, is
    neither dropped nor guessed at."""
    from app.core.encryption import encrypted_write_text

    other_role = "00000000-0000-0000-0000-00000000c0de"
    encrypted_write_text(
        tmp_path / "30b_teams_guest_access.txt",
        _OLD_TEXT.format(invites="adminsAndCertainGroups", role=other_role),
    )

    assert _verdict(report(tmp_path, lang="no"), "8.1.2") == (
        "pass",
        f"Invitasjoner: adminsAndCertainGroups. Gjesterolle: {other_role}",
    )
