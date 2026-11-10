"""A Global Administrator role nobody could read is not a tenant without one.

The collector lists a role whose member read failed under ``failed_roles`` and
writes no assignment for it. The report ignored that list, so a refused read
of the Global Administrator role gave a count of 0: CIS 1.1.3 said "no standing
Global Admin (PIM)", the customer saw a green "0 global admins" card, the score
gave full marks for admin hygiene and a 0 was stored in the trend history.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.groups_roles import AdminRolesSection
from app.reports.compliance import _build_compliance_map
from app.reports.metrics import _ga_count
from app.reports.parsers import _parse_admin_roles
from app.reports.parsers.common import _sidecar
from app.reports.risk import _compute_risk
from tests.collector_rig import FakeGraph, refused, run_sections

KARI = {"id": "u-kari", "displayName": "Kari Nordmann", "userPrincipalName": "kari@acme.example"}
ROLES = [
    {"id": "r-ga", "displayName": "Global Administrator"},
    {"id": "r-exo", "displayName": "Exchange Administrator"},
]


async def _admin_roles(tmp_path, ga_members) -> dict:
    routes = {
        "directoryRoles": ROLES,
        "directoryRoles/r-ga/members": ga_members,
        "directoryRoles/r-exo/members": [KARI],
    }
    async with FakeGraph(routes) as fake:
        files = await run_sections(AdminRolesSection(tmp_path, fake.client), sidecars=True)
    return _parse_admin_roles(files["07_admin_roles.txt"], _sidecar(files, "07_admin_roles.txt"))


def _cis_113(admin_roles: dict) -> str:
    rows = _build_compliance_map({"admin_roles": admin_roles, "file_contents": {}})
    return next(r["status"] for r in rows if r["cis_id"] == "1.1.3")


def _risk(admin_roles: dict) -> dict:
    return _compute_risk(
        secure_score={"has_data": True, "pct": 100.0},
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        all_warns=[],
        ext_fwd="",
        risky_users="",
        defender="",
        admin_roles=admin_roles,
        file_contents={},
    )


async def test_a_refused_global_admin_read_is_unknown_everywhere(tmp_path):
    admin_roles = await _admin_roles(tmp_path, refused())

    assert admin_roles["has_data"] is True, "the other role was read"
    assert admin_roles["global_admin_unread"] is True
    assert _cis_113(admin_roles) == "info"
    assert _ga_count(admin_roles) is None, "no 0 in the trend history"

    read = await _admin_roles(tmp_path / "read", [KARI, KARI | {"id": "u-2"}])
    gaps = len(_risk(admin_roles)["data_quality_issues"])
    assert gaps == len(_risk(read)["data_quality_issues"]) + 1, "said as a data gap"


async def test_a_read_global_admin_role_is_counted_as_before(tmp_path):
    admin_roles = await _admin_roles(tmp_path, [KARI, KARI | {"id": "u-2"}])

    assert admin_roles["global_admin_unread"] is False
    assert admin_roles["global_admin_count"] == 2
    assert _cis_113(admin_roles) == "pass"
    assert _ga_count(admin_roles) == 2
