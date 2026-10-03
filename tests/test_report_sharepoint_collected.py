"""SharePoint, from the files its collector writes.

The SharePoint section writes the site list and the tenant's sharing settings,
each as a text for a person and a JSON sidecar for the report, which reads the
sidecar first and the text for runs recorded before it. Both are read here as
a run leaves them, through a real GraphClient answering from
tests/collector_rig.py, and through the report context itself.
"""

from __future__ import annotations

import pytest

from app.core.encryption import encrypted_read_text, encrypted_write_text
from app.modules.m365_audit.sections.sharepoint import SharePointSection
from tests.collector_rig import FakeGraph, refused, run_sections
from tests.report_from_run import relabel, report


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


def _verdict(ctx: dict, cis_id: str) -> tuple[str, str]:
    row = next(r for r in ctx["compliance"] if r["cis_id"] == cis_id)
    return row["status"], str(row["detail"])


async def test_sites_named_like_table_furniture_are_counted(tmp_path):
    """Read from the text: the banner says five sites, and there are five."""
    await _sharepoint(tmp_path)

    assert report(tmp_path, sidecars=False)["sharepoint"]["site_count"] == 5


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_sharepoint_posture_survives_the_round_trip(tmp_path, sidecars):
    files = await _sharepoint(tmp_path)
    assert "15_sharepoint_sites.json" in files and "15b_sharepoint_settings.json" in files

    ctx = report(tmp_path, sidecars=sidecars)
    sp = ctx["sharepoint"]

    assert sp["has_data"] is True
    assert sp["sharing"] == "ExternalUserAndGuestSharing"
    assert sp["sharing_level"] == "warning" and sp["sharing_known"] is True
    assert sp["legacy_auth"] is True and sp["legacy_auth_known"] is True
    assert sp["unmanaged_devices"] is True, "the sync app is not restricted"
    assert sp["site_count"] == 5, "every page, Notes and No Code Lab included"
    assert sp["personal_sites"] == 1
    assert sp["team_sites"] == 4

    assert _verdict(ctx, "7.2.1")[0] == "fail", "anyone links are allowed"
    assert _verdict(ctx, "7.2.3")[0] == "fail", "legacy protocols are on"
    finding_ids = {r.get("finding_id") for r in ctx["recommendations"]}
    assert {"finding-sp", "finding-sp-legacy"} <= finding_ids


async def test_the_site_count_does_not_hang_on_the_table_layout(tmp_path):
    """Without the rule under its header the text goes to the shared row counter."""
    await _sharepoint(tmp_path)
    path = tmp_path / "15_sharepoint_sites.txt"
    text = encrypted_read_text(path)
    encrypted_write_text(path, "\n".join(ln for ln in text.splitlines() if "----" not in ln))

    assert report(tmp_path)["sharepoint"]["site_count"] == 5
    assert report(tmp_path, sidecars=False)["sharepoint"]["site_count"] == 3, (
        "the row counter reads 'Notes' and 'No Code Lab' as furniture"
    )


async def test_the_sharing_posture_does_not_hang_on_the_settings_labels(tmp_path):
    await _sharepoint(tmp_path)
    relabel(tmp_path / "15b_sharepoint_settings.txt")

    sp = report(tmp_path)["sharepoint"]
    assert (sp["sharing_level"], sp["legacy_auth"], sp["unmanaged_devices"]) == (
        "warning",
        True,
        True,
    )

    sp = report(tmp_path, sidecars=False)["sharepoint"]
    assert (sp["sharing_known"], sp["legacy_auth_known"]) == (False, False), (
        "the relabelled text alone says nothing"
    )


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_unanswered_settings_are_unknown_either_way(tmp_path, sidecars):
    """Graph leaves out a property it was not asked about well: unknown, not false."""
    await _sharepoint(tmp_path, **{"admin/sharepoint/settings": {"sharingCapability": "disabled"}})

    sp = report(tmp_path, sidecars=sidecars)["sharepoint"]
    assert sp["sharing_level"] == "ok"
    assert sp["legacy_auth_known"] is False
    assert sp["unmanaged_devices"] is False


async def test_refused_settings_write_no_sidecar(tmp_path):
    files = await _sharepoint(tmp_path, **{"admin/sharepoint/settings": refused()})
    assert "15b_sharepoint_settings.json" not in files
    assert "15_sharepoint_sites.json" in files, "the site list was read"

    ctx = report(tmp_path)
    assert ctx["sharepoint"]["sharing_level"] == "unknown"
    assert ctx["sharepoint"]["site_count"] == 5
    assert _verdict(ctx, "7.2.1")[0] == "info", "cannot verify, as before"
    assert "finding-sp" not in {r.get("finding_id") for r in ctx["recommendations"]}


async def test_a_refused_site_list_writes_no_sidecar(tmp_path):
    files = await _sharepoint(tmp_path, sites=refused())
    assert "15_sharepoint_sites.json" not in files

    sp = report(tmp_path)["sharepoint"]
    assert sp["site_count"] == 0
    assert sp["sharing_level"] == "warning", "the settings were read all the same"
