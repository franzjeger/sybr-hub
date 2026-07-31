"""Each collector writes what its report parser reads back.

Twenty parsers in the report read files that twenty-four collector sections
write, and until now almost nothing tested that seam. The tests that existed
fed the parsers fixtures written by hand — which cannot catch a drift between
the two sides, because the fixture *is* the assumption about what the collector
produces.

The first test of this shape, over Conditional Access, found within minutes
that every report-only policy was being counted as enforced. So these run the
real section against a fake Graph, take its actual output, and assert on what
the real parser makes of it.

Group 1: the identity core — licences, user counts, admin roles, MFA. These
feed the most prominent numbers in the report and the risk score.
"""

from __future__ import annotations

import pathlib
import re
import tempfile

import pytest

from app.core.encryption import encrypted_read_text
from app.reports import generator as g


class _FakeGraph:
    """Answers by endpoint prefix, the way GraphClient's callers use it."""

    def __init__(self, routes: dict, singles: dict | None = None):
        self._routes = routes
        self._singles = singles or {}

    async def get_all(self, path, **kwargs):
        for prefix, value in self._routes.items():
            if path.startswith(prefix):
                return value
        return []

    async def get(self, path, **kwargs):
        for prefix, value in self._singles.items():
            if path.startswith(prefix):
                return value
        return {}


async def _run(section) -> pathlib.Path:
    await section.collect()
    return section.out_dir


def _read(out_dir: pathlib.Path, name: str) -> str:
    return encrypted_read_text(out_dir / name)


def _tmp() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


# ── Licences ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_licence_inventory_survives_the_round_trip():
    from app.modules.m365_audit.sections.licenses import LicensesSection

    out = await _run(LicensesSection(_tmp(), _FakeGraph({"subscribedSkus": [
        {"skuPartNumber": "SPB", "consumedUnits": 42,
         "prepaidUnits": {"enabled": 42}},
        {"skuPartNumber": "EXCHANGESTANDARD", "consumedUnits": 10,
         "prepaidUnits": {"enabled": 100}},
    ]})))

    parsed = g._parse_licenses(_read(out, "02_licenses.txt"))
    by_part = {p["part"]: p for p in parsed}

    assert set(by_part) == {"SPB", "EXCHANGESTANDARD"}
    assert (by_part["SPB"]["used"], by_part["SPB"]["total"]) == (42, 42)
    assert by_part["SPB"]["pct"] == 100.0
    assert by_part["SPB"]["warn"] is True, "a fully consumed SKU is the finding"
    assert by_part["EXCHANGESTANDARD"]["warn"] is False


@pytest.mark.asyncio
async def test_a_licence_with_no_seats_does_not_divide_by_zero_or_warn():
    from app.modules.m365_audit.sections.licenses import LicensesSection

    out = await _run(LicensesSection(_tmp(), _FakeGraph({"subscribedSkus": [
        {"skuPartNumber": "FREE_TIER", "consumedUnits": 0,
         "prepaidUnits": {"enabled": 0}},
    ]})))

    parsed = g._parse_licenses(_read(out, "02_licenses.txt"))
    assert len(parsed) == 1
    assert parsed[0]["total"] == 0
    assert parsed[0]["warn"] is False


# ── User counts ──────────────────────────────────────────────────────────────


def _user(upn, enabled=True, guest=False, synced=False):
    return {
        "id": upn, "displayName": upn.split("@")[0], "userPrincipalName": upn,
        "accountEnabled": enabled, "userType": "Guest" if guest else "Member",
        "onPremisesSyncEnabled": synced, "assignedLicenses": [],
        "department": "", "signInActivity": {},
    }


@pytest.mark.asyncio
async def test_user_counts_survive_the_round_trip():
    from app.modules.m365_audit.sections.users_mfa import UsersSection

    out = await _run(UsersSection(_tmp(), _FakeGraph({"users": [
        _user("a@x.no"),
        _user("b@x.no", enabled=False),
        _user("c@x.no", guest=True),
        _user("d@x.no", synced=True),
    ]})))

    parsed = g._parse_user_counts(_read(out, "03_users_count.txt"))
    assert parsed["total"] == 4
    assert parsed["enabled"] == 3
    assert parsed["disabled"] == 1
    assert parsed["guests"] == 1
    assert parsed["hybrid"] == 1
    assert parsed["cloud"] == 3


@pytest.mark.asyncio
async def test_an_empty_tenant_reads_back_as_zero_not_as_missing():
    from app.modules.m365_audit.sections.users_mfa import UsersSection

    out = await _run(UsersSection(_tmp(), _FakeGraph({"users": []})))
    parsed = g._parse_user_counts(_read(out, "03_users_count.txt"))
    assert parsed["total"] == 0
    assert parsed["enabled"] == 0


# ── Admin roles ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_role_assignments_survive_the_round_trip():
    from app.modules.m365_audit.sections.groups_roles import AdminRolesSection

    graph = _FakeGraph({
        "directoryRoles/ga/members": [
            {"id": "1", "displayName": "Admin Sybr", "userPrincipalName": "admin@x.no"},
            {"id": "2", "displayName": "Sybr Admin", "userPrincipalName": "sybr@x.no"},
        ],
        "directoryRoles/exo/members": [
            {"id": "3", "displayName": "Thorsten", "userPrincipalName": "thorsten@x.no"},
        ],
        "directoryRoles": [
            {"id": "ga", "displayName": "Global Administrator"},
            {"id": "exo", "displayName": "Exchange Administrator"},
        ],
    })
    out = await _run(AdminRolesSection(_tmp(), graph))

    parsed = g._parse_admin_roles(_read(out, "07_admin_roles.txt"))
    assert parsed["has_data"] is True
    assert parsed["total_assignments"] == 3
    assert parsed["global_admin_count"] == 2, "the number the report leads with"
    assert parsed["unique_roles"] == 2


@pytest.mark.asyncio
async def test_a_role_with_no_members_is_not_written_as_an_assignment():
    from app.modules.m365_audit.sections.groups_roles import AdminRolesSection

    graph = _FakeGraph({
        "directoryRoles/empty/members": [],
        "directoryRoles": [{"id": "empty", "displayName": "Helpdesk Administrator"}],
    })
    out = await _run(AdminRolesSection(_tmp(), graph))

    parsed = g._parse_admin_roles(_read(out, "07_admin_roles.txt"))
    assert parsed["total_assignments"] == 0
    assert parsed["global_admin_count"] == 0


@pytest.mark.asyncio
async def test_a_service_principal_holding_a_role_still_counts():
    """Members without a UPN are real assignments — several were, on a live tenant."""
    from app.modules.m365_audit.sections.groups_roles import AdminRolesSection

    graph = _FakeGraph({
        "directoryRoles/ga/members": [
            {"id": "sp-1", "displayName": "Inforcer Integration"},
        ],
        "directoryRoles": [{"id": "ga", "displayName": "Global Administrator"}],
    })
    out = await _run(AdminRolesSection(_tmp(), graph))

    parsed = g._parse_admin_roles(_read(out, "07_admin_roles.txt"))
    assert parsed["global_admin_count"] == 1


# ── SharePoint tenant settings ───────────────────────────────────────────────
#
# The seam that motivated the sweep. The parser read "legacy auth" and
# "unmanaged devices" out of this file; the collector wrote neither. So the
# control grading legacy protocols passed on every tenant regardless of the
# setting, and the report stated "unmanaged devices: blocked" without ever
# having looked. A fixture written by hand had both lines in it, because the
# person writing it read the parser.


def _sp_section(response):
    from app.modules.m365_audit.sections.sharepoint import SharePointSection

    return SharePointSection(_tmp(), _FakeGraph({}, {"admin/sharepoint/settings": response}))


@pytest.mark.asyncio
async def test_sharepoint_legacy_auth_reaches_the_parser():
    section = _sp_section({
        "sharingCapability": "externalUserSharingOnly",
        "isLegacyAuthProtocolsEnabled": True,
        "isUnmanagedSyncAppForTenantRestricted": True,
    })
    await section._collect_settings()

    parsed = g._parse_sharepoint_settings(_read(section.out_dir, "15b_sharepoint_settings.txt"), "")
    assert parsed["legacy_auth"] is True
    assert parsed["legacy_auth_known"] is True
    assert parsed["unmanaged_devices"] is False, "restricted sync means unmanaged is not allowed"


@pytest.mark.asyncio
async def test_sharepoint_legacy_auth_disabled_reads_back_as_disabled():
    section = _sp_section({
        "sharingCapability": "disabled",
        "isLegacyAuthProtocolsEnabled": False,
        "isUnmanagedSyncAppForTenantRestricted": False,
    })
    await section._collect_settings()

    parsed = g._parse_sharepoint_settings(_read(section.out_dir, "15b_sharepoint_settings.txt"), "")
    assert parsed["legacy_auth"] is False
    assert parsed["legacy_auth_known"] is True
    assert parsed["unmanaged_devices"] is True


@pytest.mark.asyncio
async def test_a_property_graph_omits_is_unknown_rather_than_false():
    """Graph omits what it has no value for, and absence is not a setting."""
    section = _sp_section({"sharingCapability": "disabled"})
    await section._collect_settings()

    text = _read(section.out_dir, "15b_sharepoint_settings.txt")
    assert "Legacy Auth                   : N/A" in text

    parsed = g._parse_sharepoint_settings(text, "")
    assert parsed["legacy_auth_known"] is False


@pytest.mark.asyncio
async def test_the_control_will_not_pass_on_a_field_it_never_saw():
    """The whole point: no verdict without the measurement."""
    section = _sp_section({"sharingCapability": "disabled"})
    await section._collect_settings()

    sp = g._parse_sharepoint_settings(_read(section.out_dir, "15b_sharepoint_settings.txt"), "")
    row = [c for c in g._build_compliance_map({"sharepoint": sp, "file_contents": {}})
           if c["cis_id"] == "7.2.3"][0]
    assert row["status"] == "info"


@pytest.mark.asyncio
async def test_every_property_asked_for_exists_on_the_v1_resource():
    """Graph omits properties you misname instead of erroring.

    Three of the five originally requested here were not on the v1.0
    sharepointSettings type, so they rendered as "N/A" — indistinguishable
    from a setting that is genuinely unset.
    """
    import inspect

    from app.modules.m365_audit.sections import sharepoint as sp_mod

    # Property names on microsoft.graph.sharepointSettings (v1.0), as published.
    known = {
        "allowedDomainGuidsForSyncApp", "availableManagedPathsForSiteCreation",
        "deletedUserPersonalSiteRetentionPeriodInDays", "excludedFileExtensionsForSyncApp",
        "idleSessionSignOut", "imageTaggingOption", "isCommentingOnSitePagesEnabled",
        "isFileActivityNotificationEnabled", "isLegacyAuthProtocolsEnabled", "isLoopEnabled",
        "isMacSyncAppEnabled", "isRequireAcceptingUserToMatchInvitedUserEnabled",
        "isResharingByExternalUsersEnabled", "isSharePointMobileNotificationEnabled",
        "isSharePointNewsfeedEnabled", "isSiteCreationEnabled", "isSiteCreationUIEnabled",
        "isSitePagesCreationEnabled", "isSitesStorageLimitAutomatic",
        "isSyncButtonHiddenOnPersonalSite", "isUnmanagedSyncAppForTenantRestricted",
        "personalSiteDefaultStorageLimitInMB", "sharingAllowedDomainList",
        "sharingBlockedDomainList", "sharingCapability", "sharingDomainRestrictionMode",
        "siteCreationDefaultManagedPath", "siteCreationDefaultStorageLimitInMB",
        "tenantDefaultTimezone",
    }
    src = inspect.getsource(sp_mod.SharePointSection._collect_settings)
    asked = set(re.findall(r"""data\.get\(\s*["']([A-Za-z]+)["']""", src))
    asked |= set(re.findall(r"""flag\(\s*["']([A-Za-z]+)["']""", src))

    unknown = sorted(asked - known)
    assert not unknown, f"not properties of sharepointSettings v1.0: {unknown}"


# ── Secure Score ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secure_score_survives_the_round_trip():
    from app.modules.m365_audit.sections.secure_score import SecureScoreSection

    section = SecureScoreSection(_tmp(), _FakeGraph({}, {"security/secureScores": {
        "value": [
            {"createdDateTime": "2026-07-01T00:00:00Z", "currentScore": 100.0,
             "maxScore": 400.0, "controlScores": []},
            {"createdDateTime": "2026-07-30T00:00:00Z", "currentScore": 231.5,
             "maxScore": 400.0, "controlScores": [
                 {"controlName": "MFA for admins", "scoreInPercentage": 0.0,
                  "controlCategory": "Identity"},
                 {"controlName": "Block legacy auth", "scoreInPercentage": 100.0,
                  "controlCategory": "Identity"},
             ]},
        ]
    }}))
    await _run(section)

    parsed = g._parse_secure_score(_read(section.out_dir, "09_secure_score.txt"))
    assert parsed["has_data"] is True
    assert parsed["current"] == 231.5, "the most recent snapshot, not the first"
    assert parsed["max"] == 400.0
    assert parsed["pct"] == pytest.approx(57.9, abs=0.2)


@pytest.mark.asyncio
async def test_a_tenant_with_no_secure_score_reads_back_as_unknown():
    """Not as a zero score, which is a very different statement."""
    from app.modules.m365_audit.sections.secure_score import SecureScoreSection

    section = SecureScoreSection(_tmp(), _FakeGraph({}, {"security/secureScores": {"value": []}}))
    await _run(section)

    parsed = g._parse_secure_score(_read(section.out_dir, "09_secure_score.txt"))
    assert parsed["has_data"] is False


# ── Intune ───────────────────────────────────────────────────────────────────


def _device(name, state):
    return {
        "deviceName": name, "complianceState": state,
        "operatingSystem": "Windows", "osVersion": "10.0",
        "userPrincipalName": f"{name}@x.no", "enrolledDateTime": "2026-01-01T00:00:00Z",
        "lastSyncDateTime": "2026-07-30T00:00:00Z", "managedDeviceOwnerType": "company",
    }


@pytest.mark.asyncio
async def test_device_compliance_counts_survive_the_round_trip():
    from app.modules.m365_audit.sections.intune import IntuneSection

    section = IntuneSection(_tmp(), _FakeGraph({"deviceManagement/managedDevices": [
        _device("pc1", "compliant"),
        _device("pc2", "compliant"),
        _device("pc3", "noncompliant"),
        _device("pc4", "unknown"),
    ]}))
    await section._collect_devices()

    parsed = g._parse_intune_devices(_read(section.out_dir, "10_intune_devices_count.txt"),
                                     _read(section.out_dir, "10_intune_devices.txt"))
    assert parsed["total"] == 4
    assert parsed["compliant"] == 2
    assert parsed["noncompliant"] == 1
    assert parsed["unknown"] == 1
    assert parsed["compliance_pct"] == 50.0


@pytest.mark.asyncio
async def test_a_tenant_with_no_enrolled_devices_is_not_a_hundred_percent_compliant():
    """Zero of zero is not full marks; CIS 6.1.1 used to read it that way."""
    from app.modules.m365_audit.sections.intune import IntuneSection

    section = IntuneSection(_tmp(), _FakeGraph({"deviceManagement/managedDevices": []}))
    await section._collect_devices()

    parsed = g._parse_intune_devices(_read(section.out_dir, "10_intune_devices_count.txt"),
                                     _read(section.out_dir, "10_intune_devices.txt"))
    assert parsed["total"] == 0
    assert parsed["compliance_pct"] == 0.0


# ── OAuth consent grants ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_grants_survive_the_round_trip():
    """The section that lost eleven of twenty-eight grants to a header heuristic."""
    from app.modules.m365_audit.sections.apps_oauth import AppsOAuthSection

    graph = _FakeGraph(
        {"oauth2PermissionGrants": [
            {"clientId": "c1", "resourceId": "r1", "scope": "User.Read"},
            {"clientId": "c2", "resourceId": "r1", "scope": "Mail.ReadWrite Files.Read.All"},
            {"clientId": "c1", "resourceId": "r2", "scope": "Sites.FullControl.All"},
        ]},
        {
            "servicePrincipals/c1": {"displayName": "AvePoint Fly"},
            "servicePrincipals/c2": {"displayName": "Datto RMM integration"},
            "servicePrincipals/r1": {"displayName": "Microsoft Graph"},
            "servicePrincipals/r2": {"displayName": "Office 365 SharePoint Online"},
        },
    )
    section = AppsOAuthSection(_tmp(), graph)
    await section._collect_oauth_grants()

    text = _read(section.out_dir, "17b_oauth_consent_grants.txt")
    assert "AvePoint Fly" in text and "Datto RMM integration" in text

    parsed = g._parse_oauth_grants(text, "")
    assert parsed["has_data"] is True
    assert parsed["unique_apps"] == 2, "two distinct client apps across three grants"


@pytest.mark.asyncio
async def test_a_grant_whose_every_column_looks_like_a_heading_still_counts():
    """Capitalised, no digits, no @ / : — the shape that swallowed eleven rows."""
    from app.modules.m365_audit.sections.apps_oauth import AppsOAuthSection

    graph = _FakeGraph(
        {"oauth2PermissionGrants": [{"clientId": "c1", "resourceId": "r1", "scope": "User.Read"}]},
        {"servicePrincipals/c1": {"displayName": "AvePoint Fly"},
         "servicePrincipals/r1": {"displayName": "Microsoft Graph"}},
    )
    section = AppsOAuthSection(_tmp(), graph)
    await section._collect_oauth_grants()

    text = _read(section.out_dir, "17b_oauth_consent_grants.txt")
    assert g._count_data_lines(text) == 1
    assert g._parse_oauth_grants(text, "")["unique_apps"] == 1


# ── Groups ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_group_inventory_survives_the_round_trip():
    from app.modules.m365_audit.sections.groups_roles import GroupsSection

    graph = _FakeGraph(
        {"groups": [
            {"id": "g1", "displayName": "All Staff", "groupTypes": ["Unified"],
             "securityEnabled": False, "mailEnabled": True},
            {"id": "g2", "displayName": "SYBR - Exclude", "groupTypes": [],
             "securityEnabled": True, "mailEnabled": False},
            {"id": "g3", "displayName": "Dynamic Sales", "groupTypes": [],
             "securityEnabled": True, "mailEnabled": False,
             "membershipRule": 'user.department -eq "Sales"'},
        ]},
        {"groups/g1/members/$count": 42, "groups/g2/members/$count": 3,
         "groups/g3/transitiveMembers/$count": 7},
    )
    out = await _run(GroupsSection(_tmp(), graph))

    parsed = g._parse_groups(_read(out, "06_groups.txt"))
    assert parsed["total"] == 3
    assert parsed["has_data"] is True
    by_name = {gr["name"]: gr for gr in parsed["groups"]}
    assert by_name["All Staff"]["type"] == "Microsoft 365"
    assert by_name["Dynamic Sales"]["type"] == "Dynamic"
    assert by_name["All Staff"]["members"] == 42


@pytest.mark.asyncio
async def test_a_group_whose_member_count_failed_is_not_reported_as_empty():
    """N/A means the count call failed; an empty group is a finding, so the
    two must not be confused."""
    from app.modules.m365_audit.sections.groups_roles import GroupsSection

    graph = _FakeGraph(
        {"groups": [{"id": "g1", "displayName": "Mystery", "groupTypes": [],
                     "securityEnabled": True, "mailEnabled": False}]},
        {},  # every $count call returns {} → member_count stays "N/A"
    )
    out = await _run(GroupsSection(_tmp(), graph))

    parsed = g._parse_groups(_read(out, "06_groups.txt"))
    assert parsed["total"] == 1
    assert parsed["groups"][0]["members_known"] is False
    assert parsed["empty_groups"] == 0, "unknown is not empty"


# ── DNS / email security ─────────────────────────────────────────────────────
#
# The seam behind CIS 5.2.1 and 5.2.2. The section is careful to keep a failed
# lookup ("ERROR (...)") apart from an absent record ("MISSING"), and the two
# controls used to collapse both into a failed control — telling a customer to
# configure SPF for a domain that may well have it.


def _dns_result(domain, spf="OK (-all hardfail)", dmarc="OK (p=reject)"):
    """The shape _check_domain really returns."""
    return {
        "domain": domain, "spf_status": spf, "spf_record": "v=spf1 -all",
        "dmarc_status": dmarc, "dmarc_record": "v=DMARC1; p=reject;",
        "dkim_selector1": "CNAME -> selector1._domainkey", "dkim_selector2": "MISSING",
        "dkim_third_party": {}, "mta_sts": "MISSING",
    }


async def _run_dns(monkeypatch, results):
    from app.modules.m365_audit.sections import dns as dns_mod

    async def fake_check(client, domain):
        return next(r for r in results if r["domain"] == domain)

    monkeypatch.setattr(dns_mod, "_check_domain", fake_check)
    section = dns_mod.DnsSection(_tmp(), [r["domain"] for r in results])
    await _run(section)
    return _read(section.out_dir, "26_email_dns_spf_dmarc.txt")


@pytest.mark.asyncio
async def test_dns_statuses_survive_the_round_trip(monkeypatch):
    text = await _run_dns(monkeypatch, [_dns_result("example.no")])

    parsed = g._parse_spf_dmarc(text)
    assert len(parsed) == 1
    assert parsed[0]["domain"] == "example.no"
    assert "OK" in parsed[0]["spf"]
    assert "reject" in parsed[0]["dmarc"].lower() or "OK" in parsed[0]["dmarc"]


@pytest.mark.asyncio
async def test_a_failed_lookup_reaches_the_control_as_unverifiable(monkeypatch):
    """End to end: a SERVFAIL must not become "configure SPF"."""
    text = await _run_dns(monkeypatch, [
        _dns_result("example.no", spf="ERROR (SERVFAIL)", dmarc="ERROR (SERVFAIL)"),
    ])

    parsed = g._parse_spf_dmarc(text)
    assert parsed[0]["spf"].startswith("ERROR")

    rows = {c["cis_id"]: c for c in
            g._build_compliance_map({"spf_dmarc": parsed, "file_contents": {}})
            if c["cis_id"] in ("5.2.1", "5.2.2")}
    assert rows["5.2.1"]["status"] == "info"
    assert rows["5.2.2"]["status"] == "info"


@pytest.mark.asyncio
async def test_a_genuinely_absent_record_still_fails_the_control(monkeypatch):
    """The guard must not turn a real finding into a shrug."""
    text = await _run_dns(monkeypatch, [
        _dns_result("example.no", spf="MISSING", dmarc="MISSING"),
    ])

    parsed = g._parse_spf_dmarc(text)
    rows = {c["cis_id"]: c for c in
            g._build_compliance_map({"spf_dmarc": parsed, "file_contents": {}})
            if c["cis_id"] in ("5.2.1", "5.2.2")}
    assert rows["5.2.1"]["status"] == "fail"
    assert rows["5.2.2"]["status"] == "fail"


@pytest.mark.asyncio
async def test_each_domain_is_graded_separately(monkeypatch):
    """One broken lookup must not drag a healthy domain down with it."""
    text = await _run_dns(monkeypatch, [
        _dns_result("good.no"),
        _dns_result("broken.no", spf="ERROR (timeout)", dmarc="ERROR (timeout)"),
    ])

    parsed = g._parse_spf_dmarc(text)
    assert {d["domain"] for d in parsed} == {"good.no", "broken.no"}

    spf_rows = [c for c in g._build_compliance_map({"spf_dmarc": parsed, "file_contents": {}})
                if c["cis_id"] == "5.2.1"]
    by_domain = {r["title"].split("— ")[-1]: r["status"] for r in spf_rows}
    assert by_domain["good.no"] == "pass"
    assert by_domain["broken.no"] == "info"


# ── Exchange ─────────────────────────────────────────────────────────────────
#
# This section takes its input from the PowerShell helper rather than Graph, so
# the seam is the same but the fake is a dict of records. It held the connector
# count that read three where the tenant had one: a single record spread over
# three lines, counted as three, and printed on the customer-facing report.


def _exchange(exo_data):
    from app.modules.m365_audit.sections.exchange import ExchangeSection

    return ExchangeSection(_tmp(), exo_data, ["example.no"], graph=_FakeGraph({}))


@pytest.mark.asyncio
async def test_a_single_connector_is_counted_once(monkeypatch):
    """One record, three lines. It was read as three connectors."""
    section = _exchange({"connectors": [
        {"Name": "Inbound from scanner", "ConnectorType": "OnPremises",
         "Enabled": True, "SmartHosts": "10.0.0.5"},
    ]})
    section._save_connectors()

    fc = {"22_exchange_connectors.txt": _read(section.out_dir, "22_exchange_connectors.txt")}
    assert g._parse_exchange_overview(fc)["connectors"] == 1


@pytest.mark.asyncio
async def test_several_connectors_are_all_counted():
    section = _exchange({"connectors": [
        {"Name": "A", "Enabled": True},
        {"Name": "B", "Enabled": False},
        {"Name": "C", "Enabled": True},
    ]})
    section._save_connectors()

    fc = {"22_exchange_connectors.txt": _read(section.out_dir, "22_exchange_connectors.txt")}
    assert g._parse_exchange_overview(fc)["connectors"] == 3


@pytest.mark.asyncio
async def test_no_connectors_reads_back_as_none():
    section = _exchange({"connectors": []})
    section._save_connectors()

    fc = {"22_exchange_connectors.txt": _read(section.out_dir, "22_exchange_connectors.txt")}
    assert g._parse_exchange_overview(fc)["connectors"] == 0


@pytest.mark.asyncio
async def test_inbox_rules_finding_is_counted_from_the_renamed_file():
    """The collector signals this finding by renaming the file, not by its
    contents, and the report read only the all-clear name."""
    section = _exchange({"inbox_rules_external": [
        {"Name": "Send to Gmail", "Mailbox": "anna@example.no",
         "ForwardTo": "anna@gmail.com", "Enabled": True},
        {"Name": "Copy out", "Mailbox": "bjorn@example.no",
         "ForwardTo": "bjorn@outlook.com", "Enabled": True},
    ]})
    section._save_inbox_rules()

    written = list(section.out_dir.glob("29_*.txt"))
    assert len(written) == 1
    assert written[0].name.endswith("_WARN.txt"), "a finding renames the file"

    fc = {written[0].name: _read(section.out_dir, written[0].name)}
    assert g._parse_exchange_overview(fc)["inbox_rules_external"] == 2


@pytest.mark.asyncio
async def test_no_inbox_rules_writes_the_all_clear_name_and_counts_zero():
    section = _exchange({"inbox_rules_external": []})
    section._save_inbox_rules()

    written = list(section.out_dir.glob("29_*.txt"))
    assert len(written) == 1
    assert not written[0].name.endswith("_WARN.txt")

    fc = {written[0].name: _read(section.out_dir, written[0].name)}
    assert g._parse_exchange_overview(fc)["inbox_rules_external"] == 0


@pytest.mark.asyncio
async def test_transport_rules_survive_the_round_trip():
    section = _exchange({"transport_rules": [
        {"Name": "Scanner spam-bypass", "State": "Enabled",
         "Description": "A description that\nwraps across lines"},
        {"Name": "External warning", "State": "Enabled", "Description": "short"},
    ]})
    section._save_transport_rules()

    fc = {"21_exchange_transport_rules.txt":
          _read(section.out_dir, "21_exchange_transport_rules.txt")}
    assert g._parse_exchange_overview(fc)["transport_rules"] == 2, (
        "a wrapped description must not read as extra rules"
    )


@pytest.mark.asyncio
async def test_a_connector_whose_fields_are_lower_case_is_still_one_record():
    """What the helper actually returned on a live tenant.

    The record was {"outbound": ..., "inbound": ...} — lower case — and the
    multi-line detector required a capitalised field name, so the file was read
    as a plain table and its one connector counted as three lines of one. That
    number is printed on the customer-facing report.

    The first version of the test above used capitalised keys and let a
    mutation reverting the fix pass, which is the same assumption-as-fixture
    trap these tests exist to close.
    """
    section = _exchange({"connectors": [{"outbound": "N/A", "inbound": "N/A"}]})
    section._save_connectors()

    text = _read(section.out_dir, "22_exchange_connectors.txt")
    assert "outbound: N/A" in text, "lower case is what the helper produces"
    assert g._parse_exchange_overview({"22_exchange_connectors.txt": text})["connectors"] == 1


# ── Cross-tenant access ──────────────────────────────────────────────────────
#
# Third instance of the same shape as the SharePoint settings: a value read off
# a response that never carried it. "default" is a relationship on
# crossTenantAccessPolicy, not a property, so a GET on the policy returns only
# displayName and allowedCloudEndpoints — and both settings read "N/A" on every
# tenant since the day they were written.


@pytest.mark.asyncio
async def test_cross_tenant_settings_come_from_the_default_endpoint():
    from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection

    graph = _FakeGraph({}, {
        # What a GET on the policy itself actually returns.
        "policies/crossTenantAccessPolicy/default": {
            "isServiceDefault": False,
            "b2bCollaborationInbound": {"usersAndGroups": {"accessType": "allowed"}},
            "b2bCollaborationOutbound": {"usersAndGroups": {"accessType": "blocked"}},
            "b2bDirectConnectInbound": {"usersAndGroups": {"accessType": "blocked"}},
        },
        "policies/crossTenantAccessPolicy": {"displayName": "X", "allowedCloudEndpoints": []},
    })
    section = IdentitySecuritySection(_tmp(), graph, global_admin_ids=[])
    await section._collect_cross_tenant_policy()

    text = _read(section.out_dir, "18c_cross_tenant_access_policy.txt")
    assert "B2B Collab Inbound     : allowed" in text
    assert "B2B Collab Outbound    : blocked" in text
    assert "System Default         : false" in text


@pytest.mark.asyncio
async def test_the_policy_container_alone_would_yield_nothing():
    """Guards the actual regression: reading the wrong endpoint.

    The container carries no settings, so a collector pointed at it can only
    ever write N/A — indistinguishable from a tenant that has not configured
    cross-tenant access.
    """
    from app.modules.m365_audit.sections.identity_security import IdentitySecuritySection

    graph = _FakeGraph({}, {
        "policies/crossTenantAccessPolicy": {"displayName": "X", "allowedCloudEndpoints": []},
    })
    section = IdentitySecuritySection(_tmp(), graph, global_admin_ids=[])
    await section._collect_cross_tenant_policy()

    text = _read(section.out_dir, "18c_cross_tenant_access_policy.txt")
    assert "B2B Collab Inbound     : N/A" in text, (
        "with no default endpoint answering, N/A is the honest output"
    )
