"""SharePoint, from the files its collector writes.

Read here as a run leaves them, through a real GraphClient answering from
tests/collector_rig.py, and through the report context itself.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.sharepoint import SharePointSection
from tests.collector_rig import FakeGraph, run_sections
from tests.report_from_run import report


def _site(sid: str, name: str, url: str) -> dict:
    return {
        "id": sid,
        "displayName": name,
        "webUrl": url,
        "createdDateTime": "2024-03-01T08:00:00Z",
    }


# A name longer than the 45-character column, and two that the shared row
# counter files as furniture by their first word: "Notes" reads as a NOTE line
# and "No Code Lab" as a "No ..." placeholder.
LONG_NAME = "Kunde A Prosjektrom for felles dokumentasjon og maler"
SITES = [
    _site("s-intra", "Kunde A Intranett", "https://acme.sharepoint.com/sites/intranett"),
    _site("s-notes", "Notes", "https://acme.sharepoint.com/sites/notes"),
    _site("s-nocode", "No Code Lab", "https://acme.sharepoint.com/sites/nocode"),
    _site("s-long", LONG_NAME, "https://acme.sharepoint.com/sites/prosjektrom"),
    _site("s-kari", "Kari Nordmann", "https://acme-my.sharepoint.com/personal/kari_acme_example"),
]

SETTINGS = {
    "sharingCapability": "ExternalUserAndGuestSharing",
    "sharingDomainRestrictionMode": "none",
    "sharingAllowedDomainList": [],
    "isResharingByExternalUsersEnabled": True,
    "isRequireAcceptingUserToMatchInvitedUserEnabled": False,
    "isLegacyAuthProtocolsEnabled": True,
    "isUnmanagedSyncAppForTenantRestricted": False,
}


def _sharepoint_routes(**overrides) -> dict:
    routes = {"sites": SITES, "admin/sharepoint/settings": SETTINGS}
    for site in SITES:
        routes[f"sites/{site['id']}"] = {"sharingCapability": "ExternalUserSharingOnly"}
        routes[f"sites/{site['id']}/permissions"] = []
        routes[f"sites/{site['id']}/drive/root/permissions"] = []
    routes.update(overrides)
    return routes


async def _sharepoint(tmp_path, **overrides) -> dict[str, str]:
    async with FakeGraph(_sharepoint_routes(**overrides), page_size=2) as fake:
        files = await run_sections(SharePointSection(tmp_path, fake.client))
    assert fake.unrouted == []
    return files


async def test_sites_named_like_table_furniture_are_counted(tmp_path):
    """Read from the text: the banner says five sites, and there are five."""
    await _sharepoint(tmp_path)

    assert report(tmp_path, sidecars=False)["sharepoint"]["site_count"] == 5
