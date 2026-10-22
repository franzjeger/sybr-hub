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

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.modules.m365_audit.sections.groups_roles import AdminRolesSection, GroupsSection
from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection
from app.reports.parsers import _parse_admin_roles, _parse_groups, _parse_mfa
from app.reports.parsers.common import _sidecar
from app.reports.recommendations import _build_recommendations
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
    # Codes, which the report words (TODO C15).
    assert groups["by_type"] == {"m365": 1, "dynamic": 1, "security": 2}
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
        "type": "security",
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
    assert by_name[LONG_GROUP[:50]]["type"] == "security"
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


# ── A Global Admin excluded from MFA, across two files ────────────────────────


async def _collect_excluded_admin(tmp_path) -> dict:
    """Users, Conditional Access, MFA and Admin Roles over one tenant.

    Kari is a Global Admin with a UPN longer than the roles table's column,
    and the only MFA policy excludes her.
    """
    users = [
        {
            "id": "u-kari",
            "displayName": LONG_DISPLAY,
            "userPrincipalName": LONG_UPN,
            "accountEnabled": True,
            "userType": "Member",
        }
    ]
    policy = {
        "id": "p-mfa",
        "displayName": "Krev MFA",
        "state": "enabled",
        "conditions": {
            "users": {"includeUsers": ["All"], "excludeUsers": ["u-kari"]},
            "applications": {"includeApplications": ["All"]},
            "clientAppTypes": ["all"],
        },
        "grantControls": {"builtInControls": ["mfa"]},
    }
    routes = {
        "users": users,
        "users/u-kari/authentication/methods": {"value": []},
        "identity/conditionalAccess/policies": [policy],
        "identity/conditionalAccess/namedLocations": [],
        "directoryRoles": [{"id": "r-ga", "displayName": "Global Administrator"}],
        "directoryRoles/r-ga/members": users,
    }
    async with FakeGraph(routes) as fake:
        users_section = UsersSection(tmp_path, fake.client)
        ca = ConditionalAccessSection(tmp_path, fake.client)
        mfa = MFASection(tmp_path, fake.client, users_section.users, ca_section=ca)
        roles = AdminRolesSection(tmp_path, fake.client, users_ref=users_section.users)
        files = await run_sections(users_section, ca, mfa, roles)
        assert fake.unrouted == []
    return files


def _excluded_admin_rec(files: dict) -> dict | None:
    mfa = _parse_mfa(
        files["04_mfa_methods.txt"],
        files["04b_mfa_ca_analysis.txt"],
        [],
        files.get("04_mfa_methods.json", ""),
    )
    admin_roles = _parse_admin_roles(
        files["07_admin_roles.txt"], _sidecar(files, "07_admin_roles.txt")
    )
    recs = _build_recommendations(
        mfa=mfa,
        spf_dmarc=[],
        secure_score={"has_data": False},
        ext_fwd="",
        risky_users="",
        licenses=[],
        admin_roles=admin_roles,
        file_contents=files,
    )
    return next((r for r in recs if r["finding_id"] == "finding-mfa-excluded"), None)


async def test_an_excluded_global_admin_with_a_long_upn_is_flagged(tmp_path):
    files = await _collect_excluded_admin(tmp_path)

    rec = _excluded_admin_rec(files)

    assert rec is not None
    assert LONG_UPN in rec["sub_items"][0]


async def test_it_is_flagged_on_a_run_whose_roles_predate_their_sidecar(tmp_path):
    """The MFA records carry the UPN whole; a roles table from before its sidecar cut it."""
    files = await _collect_excluded_admin(tmp_path)
    del files["07_admin_roles.json"]

    rec = _excluded_admin_rec(files)

    assert rec is not None, "the cut UPN must still match the whole one"
    assert LONG_UPN in rec["sub_items"][0]


# ── A group's kind is a code, worded by the report ────────────────────────────
#
# The collector wrote English labels ("Security", "Other") that the customer
# report used as its own row headings, and the customer report counted
# Microsoft 365 groups under a label no collector wrote, so it said 0 for
# every tenant (TODO C15).


@pytest.mark.parametrize(
    ("lang", "words"),
    [
        ("no", {"Microsoft 365", "Dynamisk", "Sikkerhet"}),
        ("en", {"Microsoft 365", "Dynamic", "Security"}),
    ],
)
async def test_the_customer_report_words_each_kind_and_counts_microsoft_365(tmp_path, lang, words):
    import re

    from app.reports.generator import _jinja_env, build_report_context
    from app.reports.i18n import T

    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    await _collect_groups(run, ORDINARY_GROUPS, sidecars=True)
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang=lang, persist_metrics=False)
    ctx.update(t=T(lang), lang=lang, theme="light")
    page = _jinja_env().get_template("report_customer.html.j2").render(**ctx)

    rows = dict(
        re.findall(r'<div class="env-row"><span>([^<]*)</span><span>(\d+)</span></div>', page)
    )
    assert words <= set(rows), rows
    assert "security" not in rows and "m365" not in rows
    assert re.search(
        re.escape(str(T(lang).m365_groups_incl_teams)) + r"</span>\s*<span>1</span>", page
    ), "one Microsoft 365 group"


@pytest.mark.parametrize("label", ["Security", "Microsoft 365", "Something new"])
def test_an_old_runs_labels_read_back_to_codes_and_an_unknown_one_is_kept(label):
    from app.reports.i18n import T
    from app.reports.parsers.identity import group_type_text

    line = f"  {'Acme Gruppe':<50} {label:<16} {'3':>8}"
    groups = _parse_groups(f"{line}\n")
    (group,) = groups["groups"]
    expected = {"Security": "Sikkerhet", "Microsoft 365": "Microsoft 365"}.get(label, label)
    assert group_type_text(group["type"], T("no")) == expected
