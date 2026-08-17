"""The permission list has to be one list.

It was written out three times — app/core/config.py, GraphClient, and the
PowerShell that actually grants the consent — with a "keep in sync" comment
standing in for a mechanism. All three agreed, which is what a drift hazard
looks like right up until it doesn't: a permission added to two of the three
either grants a consent nothing validates, or makes the validator demand one
the setup wizard never asks for. Both fail as "insufficient permissions" long
after the commit that caused it.
"""

from __future__ import annotations

import json
import pathlib
import re

from app.core.config import REQUIRED_GRAPH_PERMISSIONS
from app.modules.m365_audit.graph_client import GraphClient

PS1 = pathlib.Path("app/helpers/setup_helper.ps1")


def test_the_client_validates_against_the_declared_list():
    assert list(GraphClient.REQUIRED_PERMISSIONS) == list(REQUIRED_GRAPH_PERMISSIONS)


def test_the_setup_helper_is_handed_the_list_rather_than_holding_one():
    """Its own array is a fallback for an older caller, not the source."""
    src = PS1.read_text(encoding="utf-8")
    assert "$permsIn" in src, "the helper does not read a list from its input"
    assert re.search(r"\$requiredPerms\s*=\s*if\s*\(\s*\$permsIn", src), (
        "the helper does not prefer the list it was given"
    )


def test_setup_sends_the_list_the_client_will_check():
    src = pathlib.Path("app/modules/m365_audit/setup.py").read_text()
    assert '"required_permissions"' in src, (
        "setup does not pass the permission list to the helper"
    )
    assert "REQUIRED_GRAPH_PERMISSIONS" in src


def test_the_fallback_has_not_drifted_from_the_source():
    """If the fallback ever runs, it must grant what the validator wants."""
    src = PS1.read_text(encoding="utf-8")
    block = re.search(r"\$fallbackPerms = @\((.*?)\n\)", src, re.S)
    assert block, "no fallback array found"
    ps_perms = set(re.findall(r"'([A-Za-z][A-Za-z.]*\.[A-Za-z.]+)'", block.group(1)))
    assert ps_perms == set(REQUIRED_GRAPH_PERMISSIONS), (
        f"only in PowerShell: {sorted(ps_perms - set(REQUIRED_GRAPH_PERMISSIONS))}; "
        f"only in config: {sorted(set(REQUIRED_GRAPH_PERMISSIONS) - ps_perms)}"
    )


def test_every_declared_permission_has_something_that_uses_it():
    """A permission nobody calls for is privilege the app need not hold.

    PrivilegedAssignmentSchedule.Read.AzureADGroup sat in all three lists
    while PIM-for-groups was never queried, so every install of this tool
    asked its customers' tenants to consent to a read it never performed.
    """
    mod = pathlib.Path("app/modules/m365_audit")
    src = "\n".join(
        p.read_text(encoding="utf-8") for p in mod.rglob("*.py")
    )
    # The resource each permission governs, where the name does not say it.
    probes = {
        "AuditLog.Read.All": "auditLogs",
        "Application.Read.All": "applications",
        "DeviceManagementApps.Read.All": "deviceAppManagement",
        "DeviceManagementConfiguration.Read.All": "deviceCompliancePolicies",
        "DeviceManagementManagedDevices.Read.All": "managedDevices",
        "DeviceManagementServiceConfig.Read.All": "windowsAutopilot",
        "Device.Read.All": '"devices"',
        "Directory.Read.All": "directoryRoles",
        "Group.Read.All": "groups",
        "IdentityRiskyUser.Read.All": "riskyUsers",
        "Organization.Read.All": "organization",
        "Policy.Read.All": "policies",
        "Reports.Read.All": "getOffice365ActiveUserDetail",
        "RoleManagement.Read.Directory": "roleManagement",
        "SecurityEvents.Read.All": "secureScores",
        "Sites.Read.All": "sites",
        "SharePointTenantSettings.Read.All": "admin/sharepoint",
        "User.Read.All": "users",
        "UserAuthenticationMethod.Read.All": "authentication/methods",
        "SensitivityLabels.Read.All": "dataSecurityAndGovernance",
        "AccessReview.Read.All": "accessReviews",
        "SecurityAlert.Read.All": "alerts_v2",
        "SecurityIncident.Read.All": "security/incidents",
    }
    unused = [
        perm for perm in REQUIRED_GRAPH_PERMISSIONS
        if perm in probes and probes[perm] not in src
    ]
    assert not unused, f"declared but never called for: {unused}"

    unmapped = [p for p in REQUIRED_GRAPH_PERMISSIONS if p not in probes]
    assert not unmapped, (
        f"no probe for {unmapped} — add one so an unused grant cannot hide"
    )


def test_a_permission_a_section_says_it_needs_is_actually_declared():
    """The forward direction: a section that documents needing a permission
    must have it in the declared set — otherwise setup never asks for it, the
    consent is never granted, and the call 403s on every live tenant while the
    audit tool quietly under-reports.

    This is the direction the reverse test above does not cover, and the gap it
    guards is not hypothetical: SecurityIncident.Read.All shipped for months
    with defender_office.py calling security/incidents and printing
    "requires SecurityIncident.Read.All" in its own error note — the note and
    the grant simply disagreed, and nothing failed until a live 403.

    The enforced convention is the inline note a section writes when a call is
    refused: "... requires X.Read.All [or Y.Read.All] ..." / "... needs
    X.Read.All". Whatever a section says it needs, the app must actually ask a
    customer's tenant to consent to.
    """
    mod = pathlib.Path("app/modules/m365_audit")
    src = "\n".join(p.read_text(encoding="utf-8") for p in mod.rglob("*.py"))

    declared = set(REQUIRED_GRAPH_PERMISSIONS)

    # A permission a section may *attempt* but does not *require*: an optional
    # enrichment with a documented fallback when it is absent. Consenting to it
    # is a choice, not a prerequisite, so it is deliberately not in the required
    # set — and naming it here keeps this test from demanding it.
    optional = {"ComplianceManager.Read.All"}

    note = re.compile(
        r"(?:requires|needs)\s+([A-Za-z]+\.Read\.[A-Za-z]+)"
        r"(?:\s+or\s+([A-Za-z]+\.Read\.[A-Za-z]+))?"
    )
    undeclared: list[str] = []
    for primary, alt in note.findall(src):
        # An "or" note is satisfied by either permission; a bare note by the one.
        options = {primary} | ({alt} if alt else set())
        if options & optional:
            continue
        if not (options & declared):
            undeclared.append(" or ".join(sorted(o for o in options if o)))

    assert not undeclared, (
        f"a section documents needing {undeclared}, but it is not in "
        f"REQUIRED_GRAPH_PERMISSIONS — setup will never request it and the call "
        f"will 403 on every tenant"
    )


def test_get_report_reads_the_csv_these_endpoints_actually_return():
    """It asked for JSON. Graph answers "JSON format is not supported", 400.

    Measured against a live tenant: getOffice365ActiveUserDetail serves CSV
    behind a redirect and refuses $format=application/json outright. The URL
    was wrong too — _GRAPH_BASE for a constant named _GRAPH_V1 — and neither
    showed up in tests, because the only code path that touches either is a
    real request.
    """
    import asyncio

    from app.modules.m365_audit.graph_client import GraphClient

    CSV = (
        "\ufeffReport Refresh Date,User Principal Name,Is Deleted,"
        "Exchange Last Activity Date,OneDrive Last Activity Date,Assigned Products\r\n"
        "2026-08-01,a@b.no,False,2026-07-31,,EXCHANGE ONLINE (PLAN 1)+TEAMS\r\n"
        "2026-08-01,c@d.no,True,,,\r\n"
    )

    class _Resp:
        status_code = 200
        headers: dict = {}
        content = CSV.encode("utf-8")

        def raise_for_status(self):
            return None

    seen: dict = {}

    class _Http:
        async def get(self, url, headers=None, follow_redirects=False, **kw):
            seen["url"] = url
            seen["accept"] = (headers or {}).get("Accept")
            seen["follow"] = follow_redirects
            return _Resp()

    client = GraphClient.__new__(GraphClient)
    client._http = _Http()

    async def _headers():
        return {}

    client._headers = _headers

    rows = asyncio.run(client.get_report("getOffice365ActiveUserDetail", "D90"))

    assert seen["url"] == (
        "https://graph.microsoft.com/v1.0/reports/"
        "getOffice365ActiveUserDetail(period='D90')"
    )
    assert seen["accept"] == "text/csv"
    assert seen["follow"] is True, "the report redirects to storage"

    assert len(rows) == 2
    # the BOM must not ride along on the first column name
    assert rows[0]["reportRefreshDate"] == "2026-08-01"
    assert rows[0]["userPrincipalName"] == "a@b.no"
    # "True"/"False" are strings in CSV and booleans in the JSON form
    assert rows[0]["isDeleted"] is False
    assert rows[1]["isDeleted"] is True
    # and Assigned Products is an array there, a plus-separated string here
    assert rows[0]["assignedProducts"] == ["EXCHANGE ONLINE (PLAN 1)", "TEAMS"]
    assert rows[1]["assignedProducts"] == []
    assert rows[0]["oneDriveLastActivityDate"] == ""


def test_an_intune_service_refusal_is_not_reported_as_missing_consent():
    """Measured against a tenant with all four DeviceManagement roles granted.

    Graph wraps the Intune service's own refusal in a 401 with code
    UnknownError, and the body carries a manage.microsoft.com URL with a
    nested ErrorCode of Forbidden. Read as a permission failure it sends a
    technician to inspect a grant that is already there; what it means is
    that the service will not answer for this tenant at all.
    """
    from app.modules.m365_audit.graph_client import GraphPermissionError

    body = (
        '{"error":{"code":"UnknownError","message":"{\\"ErrorCode\\":\\"Forbidden\\",'
        '\\"Message\\":\\"... Url: https://proxy.msub09.manage.microsoft.com/DeviceFE/'
        'StatelessDeviceFEService/deviceManagement/managedDevices\\"}"}}'
    )
    err = GraphPermissionError("deviceManagement/managedDevices", 401, body)

    assert err.is_service_refusal is True
    assert err.is_licence_gap is False
    assert "permission is not the problem" in str(err)
    assert "admin consent" not in str(err)


def test_a_plain_403_is_still_reported_as_missing_consent():
    """The counterpart: a real permission refusal must keep saying so."""
    from app.modules.m365_audit.graph_client import GraphPermissionError

    body = '{"error":{"code":"Authorization_RequestDenied","message":"Insufficient privileges."}}'
    err = GraphPermissionError("users", 403, body)

    assert err.is_service_refusal is False
    assert err.is_licence_gap is False
    assert "missing a permission or admin consent" in str(err)


def test_get_raises_on_refusal_instead_of_returning_an_error_dict():
    """A 401/403 on a single-object read must raise, not return ``{"error": ...}``.

    The old contract returned an error dict, so a caller doing
    ``data.get("value", [])`` read "you may not read this" as "the tenant has
    none of these" — a 403 on a user's auth methods became "no MFA registered"
    and a clean CIS pass on evidence nobody was ever allowed to see. Raising
    (as ``get_paged`` and ``get_report`` already do) lets the section record
    itself as failed and the report say "cannot verify".
    """
    import asyncio

    from app.modules.m365_audit.graph_client import GraphClient, GraphPermissionError

    class _Resp:
        status_code = 403
        text = '{"error":{"code":"Authorization_RequestDenied","message":"Insufficient privileges."}}'

        def raise_for_status(self):
            raise AssertionError("a refusal must not be treated as a success")

    class _Http:
        async def get(self, url, headers=None, **kw):
            return _Resp()

    client = GraphClient.__new__(GraphClient)
    client._http = _Http()

    async def _headers():
        return {}

    client._headers = _headers

    async def _call():
        return await client.get("users/u1/authentication/methods")

    try:
        asyncio.run(_call())
    except GraphPermissionError as err:
        assert err.status == 403
        assert "authentication/methods" in err.path
    else:
        raise AssertionError("a 403 must raise GraphPermissionError, not return a dict")


def test_the_section_name_list_matches_the_sections_that_run():
    """The scope selector is driven by a hand-written list of names.

    It is a second list of what the collector builds, and Usage Reports had
    already been left out of it: the section ran on every audit and could not
    be deselected, because the picker did not know it existed.
    """
    import re

    from app.modules.m365_audit.collector import AuditCollector

    declared = set(AuditCollector.GRAPH_SECTION_NAMES) | set(AuditCollector.AZURE_SECTION_NAMES)

    src = pathlib.Path("app/modules/m365_audit/collector.py").read_text()
    constructed = set(re.findall(r"(\w+Section)\(", src))
    assert constructed, "no sections found — the pattern no longer matches"

    # Section classes carry the display name the picker uses.
    import importlib

    built: set[str] = set()
    for cls_name in constructed:
        for mod in pathlib.Path("app/modules/m365_audit/sections").glob("*.py"):
            module = importlib.import_module(f"app.modules.m365_audit.sections.{mod.stem}")
            cls = getattr(module, cls_name, None)
            if cls is not None and getattr(cls, "name", None):
                built.add(cls.name)
                break

    missing = sorted(built - declared)
    assert not missing, f"sections that run but the picker cannot see: {missing}"
