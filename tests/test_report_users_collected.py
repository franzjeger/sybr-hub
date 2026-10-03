"""User counts, stale accounts and the CA MFA analysis, read back from the Users and MFA collectors.

Each of these files now has a JSON twin (03_users_count.json,
03b_stale_accounts.json, 03c_stale_accounts_WARN.json, 04b_mfa_ca_analysis.json)
that the report reads first. The text stays for a person, and for runs from
before the sidecar. So every reader is run twice over what the real collectors
wrote against a fake tenant: from the sidecar, and from the text alone.

Where the text is precise the two must agree. Where it is not, the sidecar must
be right: the stale-account table trims names to 35 characters and UPNs to 45,
and the reader splits the rows on runs of spaces.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.m365_audit.sections.conditional_access import ConditionalAccessSection
from app.modules.m365_audit.sections.users_mfa import MFASection, UsersSection
from app.reports.parsers import _analyze_license_optimization, _parse_mfa, _parse_user_counts
from app.reports.parsers.common import _sidecar
from app.reports.recommendations import _build_recommendations
from tests.collector_rig import FakeGraph, refused, run_sections

LONG_NAME = "Anne-Marie Christoffersen Haugsland"
assert len(LONG_NAME) == 35
LONG_UPN = "anne-marie.christoffersen@kunde-a.acme.example"
assert len(LONG_UPN) > 45


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user(
    uid: str,
    name: str,
    *,
    upn: str | None = None,
    enabled: bool = True,
    guest: bool = False,
    licensed: bool = True,
    last_sign_in: str | None = None,
) -> dict:
    return {
        "id": uid,
        "displayName": name,
        "userPrincipalName": upn or f"{uid}@acme.example",
        "accountEnabled": enabled,
        "userType": "Guest" if guest else "Member",
        "onPremisesSyncEnabled": uid == "kari",
        "assignedLicenses": [{"skuId": "sku-1"}] if licensed else [],
        "signInActivity": {"lastSignInDateTime": last_sign_in} if last_sign_in else None,
    }


USERS = [
    _user("kari", "Kari Nordmann", last_sign_in=_ago(2)),
    # Stale, licensed, and both name and UPN wider than their columns.
    _user("annemarie", LONG_NAME, upn=LONG_UPN, last_sign_in=_ago(120)),
    # Stale and licensed, never signed in.
    _user("ola", "Ola Nordmann"),
    # Stale, unlicensed.
    _user("per", "Per Hansen", licensed=False, last_sign_in=_ago(200)),
    _user("gjest", "Gjest Bruker", guest=True),
    _user("sluttet", "Sluttet Ansatt", enabled=False),
]

MFA_POLICY = {
    "id": "policy-1",
    "displayName": "Krev MFA",
    "state": "enabled",
    "conditions": {
        "users": {
            "includeUsers": [],
            "includeGroups": ["group-mfa"],
            "excludeUsers": ["ola"],
            "excludeGroups": [],
        },
        "applications": {"includeApplications": ["All"]},
        "clientAppTypes": ["all"],
    },
    "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
}


def _routes(users: list[dict], policies: list[dict]) -> dict:
    routes: dict = {
        "users": users,
        "identity/conditionalAccess/policies": policies,
        "identity/conditionalAccess/namedLocations": [],
        "groups/group-mfa": {"id": "group-mfa", "displayName": "MFA-brukere", "groupTypes": []},
        "groups/group-mfa/members": [{"id": "kari"}, {"id": "annemarie"}, {"id": "ola"}],
    }
    for u in users:
        routes[f"users/{u['id']}/authentication/methods"] = {"value": []}
    return routes


async def _collect(tmp_path, *, sidecars: bool, users=USERS, policies=(MFA_POLICY,)) -> dict:
    async with FakeGraph(_routes(list(users), list(policies)), page_size=2) as fake:
        users_section = UsersSection(tmp_path, fake.client)
        ca = ConditionalAccessSection(tmp_path, fake.client)
        mfa = MFASection(tmp_path, fake.client, users_section.users, ca_section=ca)
        files = await run_sections(users_section, ca, mfa, sidecars=sidecars)
        assert fake.unrouted == []
    return files


def _stale_rec(files: dict) -> dict | None:
    recs = _build_recommendations(
        mfa={"has_data": False},
        spf_dmarc=[],
        secure_score={"has_data": False},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents=files,
    )
    return next((r for r in recs if r["finding_id"] == "finding-stale"), None)


# ── 03_users_count ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_user_counts_agree_from_either_file(tmp_path, sidecars):
    files = await _collect(tmp_path, sidecars=sidecars)
    sidecar = _sidecar(files, "03_users_count.txt")
    assert (sidecar is not None) is sidecars

    counts = _parse_user_counts(files["03_users_count.txt"], sidecar)

    assert counts == {
        "total": 6,
        "enabled": 5,
        "disabled": 1,
        "guests": 1,
        "hybrid": 1,
        "cloud": 5,
        "has_data": True,
    }


async def test_user_counts_are_read_from_the_sidecar(tmp_path):
    files = await _collect(tmp_path, sidecars=True)

    counts = _parse_user_counts("", _sidecar(files, "03_users_count.txt"))

    assert counts["total"] == 6
    assert counts["guests"] == 1
    assert counts["has_data"] is True


async def test_an_empty_tenant_is_zero_users_not_missing_data(tmp_path):
    files = await _collect(tmp_path, sidecars=True, users=[], policies=[])

    counts = _parse_user_counts(files["03_users_count.txt"], _sidecar(files, "03_users_count.txt"))

    assert counts["total"] == 0
    assert counts["has_data"] is False, "the same answer the text gives"


async def test_a_refused_user_read_writes_no_sidecar(tmp_path):
    async with FakeGraph({"users": refused()}) as fake:
        files = await run_sections(UsersSection(tmp_path, fake.client))

    assert "03_users_count.json" not in files
    counts = _parse_user_counts(files.get("03_users_count.txt", ""), None)
    assert counts["has_data"] is False


# ── 03b_stale_accounts / 03c_stale_accounts_WARN ──────────────────────────────


async def test_stale_accounts_from_the_sidecar_keep_names_and_upns_whole(tmp_path):
    files = await _collect(tmp_path, sidecars=True)

    result = _analyze_license_optimization([], files)

    assert result["has_data"] is True
    assert result["no_data_reason"] is None
    unused = {u["upn"]: u for u in result["unused_licenses"]}
    assert set(unused) == {LONG_UPN, "ola@acme.example"}, "licensed stale accounts only"
    assert unused[LONG_UPN]["name"] == LONG_NAME
    assert unused[LONG_UPN]["days_inactive"] == 120
    assert unused["ola@acme.example"]["days_inactive"] is None, "never signed in"


async def test_the_sidecar_is_what_the_stale_reader_reads(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    files["03b_stale_accounts.txt"] = ""

    result = _analyze_license_optimization([], files)

    assert result["has_data"] is True
    assert result["no_data_reason"] is None
    assert {u["upn"] for u in result["unused_licenses"]} == {LONG_UPN, "ola@acme.example"}


async def test_stale_accounts_from_the_text_alone_lose_only_what_the_table_cut(tmp_path):
    files = await _collect(tmp_path, sidecars=False)

    result = _analyze_license_optimization([], files)

    assert result["has_data"] is True
    unused = {u["name"]: u for u in result["unused_licenses"]}
    assert set(unused) == {LONG_NAME, "Ola Nordmann"}
    # A name filling its column is still one column, and its licence flag is
    # still read from the licence column.
    assert unused[LONG_NAME]["days_inactive"] == 120
    assert unused[LONG_NAME]["upn"] == LONG_UPN[:45], "the table cut it to 45 characters"


async def test_a_tenant_without_sign_in_data_reads_as_unmeasured_from_either_file(tmp_path):
    users = [_user("kari", "Kari Nordmann"), _user("ola", "Ola Nordmann")]
    for sidecars in (True, False):
        out = tmp_path / str(sidecars)
        out.mkdir()
        files = await _collect(out, sidecars=sidecars, users=users, policies=[])

        result = _analyze_license_optimization([], files)

        assert result["has_data"] is False
        assert result["no_data_reason"] == "license_p1_missing"
        assert result["unused_licenses"] == []


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_stale_licence_recommendation_counts_the_same_from_either_file(
    tmp_path, sidecars
):
    files = await _collect(tmp_path, sidecars=sidecars)
    assert ("03c_stale_accounts_WARN.json" in files) is sidecars

    rec = _stale_rec(files)

    assert rec is not None
    assert rec["title_params"]["count"] == 2


async def test_the_stale_licence_recommendation_reads_the_sidecar(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    files["03c_stale_accounts_WARN.txt"] = ""

    rec = _stale_rec(files)

    assert rec is not None
    assert rec["title_params"]["count"] == 2


# ── 04b_mfa_ca_analysis ───────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_ca_analysis_figures_agree_from_either_file(tmp_path, sidecars):
    """Read through the fallback _parse_mfa takes when it has no per-user rows."""
    files = await _collect(tmp_path, sidecars=sidecars)
    ca_sidecar = _sidecar(files, "04b_mfa_ca_analysis.txt")
    assert (ca_sidecar is not None) is sidecars

    mfa = _parse_mfa("", files["04b_mfa_ca_analysis.txt"], [], "", ca_sidecar)

    # Kari, Anne-Marie and Ola are in the policy's group; Ola is excluded; Per
    # is outside it. Guests and the disabled account are not in the base.
    assert mfa["covered"] == 2
    assert mfa["ca_covered"] == 2
    assert mfa["ca_excluded"] == 1
    assert mfa["total"] == 4


async def test_the_ca_analysis_figures_are_read_from_the_sidecar(tmp_path):
    files = await _collect(tmp_path, sidecars=True)
    ca_sidecar = _sidecar(files, "04b_mfa_ca_analysis.txt")

    mfa = _parse_mfa("", "", [], "", ca_sidecar)

    assert mfa["covered"] == 2
    assert mfa["total"] == 4
    assert ca_sidecar["not_covered_users"] == ["ola@acme.example", "per@acme.example"]
    assert ca_sidecar["mfa_policies"][0]["exclude_users"] == ["ola"]


async def test_no_mfa_policy_is_written_as_zero_coverage_not_left_out(tmp_path):
    files = await _collect(tmp_path, sidecars=True, policies=[])
    ca_sidecar = _sidecar(files, "04b_mfa_ca_analysis.txt")

    assert ca_sidecar is not None
    assert ca_sidecar["mfa_policies"] == []
    assert ca_sidecar["effectively_covered"] == 0
    assert ca_sidecar["not_covered"] == 4
