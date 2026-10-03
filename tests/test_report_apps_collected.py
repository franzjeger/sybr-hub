"""App registrations and consent grants, from the files the Apps collector writes.

CIS 2.1 and the OAuth recommendation read the tenant-wide consent grants in
17b_oauth_consent_grants.txt and the registration count in
17_app_registrations.txt. Both are read here as a run leaves them, through a
real GraphClient answering from tests/collector_rig.py, and through the report
context itself.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.apps_oauth import AppsOAuthSection
from tests.collector_rig import FakeGraph, run_sections
from tests.report_from_run import report

# Longer than the 40-character columns of the grants table.
LONG_CLIENT = "Kunde A Enterprise Resource Planning Integration"
LONG_RESOURCE = "Office 365 SharePoint Online Extended Services API"


def _grant(client: str, resource: str, scope: str) -> dict:
    return {
        "id": f"grant-{client}-{resource}",
        "clientId": client,
        "resourceId": resource,
        "consentType": "AllPrincipals",
        "scope": scope,
    }


GRANTS = [
    _grant("c-portal", "r-graph", "User.Read"),
    _grant("c-erp", "r-graph", "Sites.FullControl.All"),
    _grant("c-empty", "r-graph", ""),
    _grant("c-hr", "r-graph", "Mail.ReadWrite"),
    _grant("c-backup", "r-graph", "Files.ReadWrite.All"),
    _grant("c-arkiv", "r-spo", "AllSites.Manage"),
]

NAMES = {
    "c-portal": "Kunde A Portal",
    "c-erp": LONG_CLIENT,  # fills its column: one space to the next
    "c-empty": "Kunde A Innlogging",  # a grant with no scopes
    "c-hr": "Acme  HR Sync",  # a doubled space inside the name
    "c-backup": "Backup App: Nightly",  # "App:" is the pipe format's marker
    "c-arkiv": "Kunde A Arkiv",
    "r-graph": "Microsoft Graph",
    "r-spo": LONG_RESOURCE,
}


def _routes(**overrides) -> dict:
    routes = {
        "applications": [],
        "oauth2PermissionGrants": GRANTS,
        **{f"servicePrincipals/{sp}": {"displayName": name} for sp, name in NAMES.items()},
    }
    routes.update(overrides)
    return routes


async def _apps(tmp_path, **overrides) -> dict[str, str]:
    async with FakeGraph(_routes(**overrides), page_size=4) as fake:
        files = await run_sections(AppsOAuthSection(tmp_path, fake.client))
    assert fake.unrouted == []
    return files


async def test_every_consent_grant_is_read_from_the_table(tmp_path):
    """Six grants the old reader cut to three, losing every high-privilege one."""
    await _apps(tmp_path)

    oauth = report(tmp_path, sidecars=False)["oauth"]

    assert oauth["total_grants"] == 6
    by_app = {g["app"]: g["scopes"] for g in oauth["admin_consent"]}
    assert by_app == {
        "Kunde A Portal": ["User.Read"],
        LONG_CLIENT[:40]: ["Sites.FullControl.All"],
        "Kunde A Innlogging": [],
        "Acme  HR Sync": ["Mail.ReadWrite"],
        "Backup App: Nightly": ["Files.ReadWrite.All"],
        "Kunde A Arkiv": ["AllSites.Manage"],
    }
    assert oauth["high_privilege_apps"] == [
        "Backup App: Nightly",
        "Kunde A Arkiv",
        LONG_CLIENT[:40],
    ]
