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
        "Directory.Read.All": "directoryRoles",
        "Group.Read.All": "groups",
        "IdentityRiskyUser.Read.All": "riskyUsers",
        "Organization.Read.All": "organization",
        "Policy.Read.All": "policies",
        "RoleManagement.Read.Directory": "roleManagement",
        "SecurityEvents.Read.All": "secureScores",
        "Sites.Read.All": "sites",
        "SharePointTenantSettings.Read.All": "admin/sharepoint",
        "User.Read.All": "users",
        "UserAuthenticationMethod.Read.All": "authentication/methods",
        "InformationProtectionPolicy.Read.All": "informationProtection",
        "AccessReview.Read.All": "accessReviews",
        "SecurityAlert.Read.All": "alerts_v2",
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
