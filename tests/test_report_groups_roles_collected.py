"""Groups and admin roles, read back from what the Groups and Admin Roles collectors write.

06_groups.txt and 07_admin_roles.txt now have JSON twins that the report reads
first. Both tables cut their text columns to a width (group names to 50; role
names to 40, display names to 30, UPNs to 45) and the readers find the columns
again by splitting on runs of spaces or by offset. Over ordinary data the text
and the sidecar must agree; over names that fill or overflow their columns
only the sidecar can be right.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.groups_roles import AdminRolesSection, GroupsSection
from app.reports.parsers import _parse_admin_roles, _parse_groups
from app.reports.parsers.common import _sidecar
from tests.collector_rig import FakeGraph, refused, run_sections

LONG_GROUP = "Alle ansatte i Kunde A, avdeling for økonomi og regnskap"
assert len(LONG_GROUP) > 50


def _group(gid: str, name: str, *, unified=False, security=True, mail=False, rule=None) -> dict:
    return {
        "id": gid,
        "displayName": name,
        "groupTypes": (["Unified"] if unified else []) + (["DynamicMembership"] if rule else []),
        "securityEnabled": security,
        "mailEnabled": mail,
        "membershipRule": rule,
    }


ORDINARY_GROUPS = [
    _group("g-salg", "Salg", unified=True, security=False, mail=True),
    _group("g-dyn", "Alle i Oslo", rule='user.city -eq "Oslo"'),
    _group("g-tom", "Tom gruppe"),
    _group("g-ukjent", "Ukjent størrelse"),
]

GROUP_ROUTES = {
    "groups/g-salg/members/$count": 5,
    # A dynamic group is counted through transitiveMembers first.
    "groups/g-dyn/transitiveMembers/$count": 7,
    "groups/g-tom/members/$count": 0,
    "groups/g-tom/transitiveMembers/$count": 0,
    "groups/g-ukjent/members/$count": refused(),
    "groups/g-ukjent/transitiveMembers/$count": refused(),
    "groups/g-lang/members/$count": 12,
}


async def _collect_groups(tmp_path, groups, *, sidecars: bool) -> dict:
    async with FakeGraph({"groups": groups, **GROUP_ROUTES}) as fake:
        files = await run_sections(GroupsSection(tmp_path, fake.client), sidecars=sidecars)
        assert fake.unrouted == []
    return files


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_ordinary_groups_read_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect_groups(tmp_path, ORDINARY_GROUPS, sidecars=sidecars)
    sidecar = _sidecar(files, "06_groups.txt")
    assert (sidecar is not None) is sidecars

    groups = _parse_groups(files["06_groups.txt"], sidecar)

    assert groups["total"] == 4
    assert groups["by_type"] == {"Microsoft 365": 1, "Dynamic": 1, "Security": 2}
    assert groups["empty_groups"] == 1, "a count that failed is not an empty group"
    assert groups["dynamic_groups"] == 1
    by_name = {g["name"]: g for g in groups["groups"]}
    assert by_name["Alle i Oslo"]["members"] == 7
    assert by_name["Ukjent størrelse"]["members_known"] is False


async def test_a_group_name_longer_than_its_column_is_still_a_group(tmp_path):
    groups_in = [*ORDINARY_GROUPS, _group("g-lang", LONG_GROUP)]
    files = await _collect_groups(tmp_path, groups_in, sidecars=True)

    groups = _parse_groups(files["06_groups.txt"], _sidecar(files, "06_groups.txt"))

    assert groups["total"] == 5
    by_name = {g["name"]: g for g in groups["groups"]}
    assert by_name[LONG_GROUP] == {
        "name": LONG_GROUP,
        "type": "Security",
        "members": 12,
        "members_known": True,
    }


async def test_the_text_alone_still_counts_a_group_whose_name_fills_its_column(tmp_path):
    """A run from before the sidecar: the name is cut, the group is still counted."""
    groups_in = [*ORDINARY_GROUPS, _group("g-lang", LONG_GROUP)]
    files = await _collect_groups(tmp_path, groups_in, sidecars=False)

    groups = _parse_groups(files["06_groups.txt"])

    assert groups["total"] == 5
    by_name = {g["name"]: g for g in groups["groups"]}
    assert by_name[LONG_GROUP[:50]]["type"] == "Security"
    assert by_name[LONG_GROUP[:50]]["members"] == 12


async def test_the_groups_sidecar_is_what_the_reader_reads(tmp_path):
    files = await _collect_groups(tmp_path, ORDINARY_GROUPS, sidecars=True)

    groups = _parse_groups("", _sidecar(files, "06_groups.txt"))

    assert groups["total"] == 4
    assert groups["has_data"] is True


async def test_a_refused_group_read_writes_no_sidecar(tmp_path):
    async with FakeGraph({"groups": refused()}) as fake:
        files = await run_sections(GroupsSection(tmp_path, fake.client))

    assert "06_groups.json" not in files
    assert _parse_groups(files.get("06_groups.txt", ""), None)["has_data"] is False


# ── Admin roles ───────────────────────────────────────────────────────────────

LONG_UPN = "kari.nordmann-administrator@kunde-a.acme.example"
assert len(LONG_UPN) > 45
LONG_DISPLAY = "Kari Nordmann (administratorkonto)"
assert len(LONG_DISPLAY) > 30
LONG_ROLE = "Azure Information Protection Administrator"
assert len(LONG_ROLE) > 40

ROLES = [
    {"id": "r-ga", "displayName": "Global Administrator"},
    {"id": "r-aip", "displayName": LONG_ROLE},
    {"id": "r-helpdesk", "displayName": "Helpdesk Administrator"},
    {"id": "r-refused", "displayName": "Exchange Administrator"},
]

ROLE_ROUTES = {
    "directoryRoles": ROLES,
    "directoryRoles/r-ga/members": [
        {
            "@odata.type": "#microsoft.graph.user",
            "id": "u-kari",
            "displayName": LONG_DISPLAY,
            "userPrincipalName": LONG_UPN,
        },
        {
            "@odata.type": "#microsoft.graph.servicePrincipal",
            "id": "sp-0000",
            "displayName": "Integrasjon",
        },
    ],
    "directoryRoles/r-aip/members": [
        {"id": "u-ola", "displayName": "Ola Nordmann", "userPrincipalName": "ola@acme.example"}
    ],
    "directoryRoles/r-helpdesk/members": [],
    "directoryRoles/r-refused/members": refused(),
}


async def _collect_roles(tmp_path, *, sidecars: bool, routes=ROLE_ROUTES) -> dict:
    async with FakeGraph(routes) as fake:
        files = await run_sections(AdminRolesSection(tmp_path, fake.client), sidecars=sidecars)
        assert fake.unrouted == []
    return files


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_admin_role_counts_read_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect_roles(tmp_path, sidecars=sidecars)
    sidecar = _sidecar(files, "07_admin_roles.txt")
    assert (sidecar is not None) is sidecars

    roles = _parse_admin_roles(files["07_admin_roles.txt"], sidecar)

    assert roles["has_data"] is True
    assert roles["global_admin_count"] == 2, "a service principal holding the role counts"
    assert roles["total_assignments"] == 3
    assert roles["unique_roles"] == 2
    assert {r["email"] for r in roles["global_admin_users"]} >= {"sp-0000"}


async def test_the_sidecar_keeps_what_the_table_cuts(tmp_path):
    files = await _collect_roles(tmp_path, sidecars=True)

    roles = _parse_admin_roles(files["07_admin_roles.txt"], _sidecar(files, "07_admin_roles.txt"))

    ga = {r["email"]: r for r in roles["global_admin_users"]}
    assert ga[LONG_UPN]["user"] == LONG_DISPLAY
    assert {r["role"] for r in roles["roles"]} == {"Global Administrator", LONG_ROLE}

    text_only = _parse_admin_roles(files["07_admin_roles.txt"])
    assert LONG_UPN[:45] in {r["email"] for r in text_only["global_admin_users"]}
    assert LONG_ROLE not in {r["role"] for r in text_only["roles"]}


async def test_the_admin_roles_sidecar_is_what_the_reader_reads(tmp_path):
    files = await _collect_roles(tmp_path, sidecars=True)
    sidecar = _sidecar(files, "07_admin_roles.txt")

    roles = _parse_admin_roles("", sidecar)

    assert roles["global_admin_count"] == 2
    assert sidecar["failed_roles"][0]["role"] == "Exchange Administrator"
    assert sidecar["global_admin_count"] == 2


async def test_a_refused_role_list_writes_no_sidecar(tmp_path):
    files = await _collect_roles(tmp_path, sidecars=True, routes={"directoryRoles": refused()})

    assert "07_admin_roles.json" not in files
    assert _parse_admin_roles(files.get("07_admin_roles.txt", ""), None)["has_data"] is False
