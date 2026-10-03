"""SharePoint and OneDrive, from the files their collectors write.

The SharePoint section writes the site list and the tenant's sharing settings,
the OneDrive section what its sharing scan found and how far it got. Each
writes a text for a person and a JSON sidecar for the report, which reads the
sidecar first and the text for runs recorded before it. Both are read here as
a run leaves them, through a real GraphClient answering from
tests/collector_rig.py, and through the report context itself.
"""

from __future__ import annotations

import pytest

from app.core.encryption import encrypted_read_text, encrypted_write_text
from app.modules.m365_audit.sections.onedrive_sharing import OneDriveSharingSection
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
    # The shared row counter used to read 'Notes' and 'No Code Lab' as furniture.
    assert report(tmp_path, sidecars=False)["sharepoint"]["site_count"] == 5


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


# ── OneDrive sharing ─────────────────────────────────────────────────────────

USERS = [{"id": "kari", "userPrincipalName": "kari@acme.example"}]
LONG_FILE = "Kontrakt med leverandor for drift av nettverk og servere 2026.docx"


def _anonymous(url: str) -> dict:
    return {"link": {"scope": "anonymous", "type": "edit", "webUrl": url}, "roles": ["write"]}


def _external(upn: str) -> dict:
    return {
        "link": {"scope": "users", "type": "view"},
        "roles": ["read"],
        "grantedToV2": {"user": {"id": "g1", "userPrincipalName": upn}},
    }


ANON_URL = "https://acme.sharepoint.com/:w:/s/intranett/EaBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
EXT_UPN = "ola_partner.example#EXT#@acme.onmicrosoft.com"


def _onedrive_routes(**overrides) -> dict:
    routes = {
        "sites": [SITES[0]],
        "sites/s-intra/drives": [{"id": "d-intra", "name": "Dokumenter"}],
        "users/kari/drives": [{"id": "d-kari", "name": "OneDrive"}],
        "drives/d-intra/root/permissions": [],
        "drives/d-intra/items/root/children": [
            {"id": "f1", "name": "Prosjekter", "folder": {"childCount": 1}, "permissions": []},
            {"id": "i1", "name": "Budsjett.xlsx", "permissions": [_anonymous(ANON_URL)]},
        ],
        "drives/d-intra/items/f1/children": [
            {"id": "i2", "name": LONG_FILE, "permissions": [_external(EXT_UPN)]},
        ],
        "drives/d-kari/root/permissions": [],
        "drives/d-kari/items/root/children": [],
    }
    routes.update(overrides)
    return routes


async def _onedrive(tmp_path, **overrides) -> dict[str, str]:
    async with FakeGraph(_onedrive_routes(**overrides)) as fake:
        section = OneDriveSharingSection(
            tmp_path, fake.client, users_ref=USERS, users_complete=lambda: True
        )
        files = await run_sections(section)
    assert fake.unrouted == []
    return files


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_an_anonymous_link_fails_the_control_either_way(tmp_path, sidecars):
    files = await _onedrive(tmp_path)
    assert "25_onedrive_sharing.json" in files

    status, detail = _verdict(report(tmp_path, sidecars=sidecars), "7.2.4")
    assert status == "fail"
    assert detail.startswith("1 anonym")


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_clean_complete_scan_passes_either_way(tmp_path, sidecars):
    clean = [{"id": "i1", "name": "Budsjett.xlsx", "permissions": []}]
    await _onedrive(tmp_path, **{"drives/d-intra/items/root/children": clean})

    status, detail = _verdict(report(tmp_path, sidecars=sidecars), "7.2.4")
    assert status == "pass"
    assert "2 stasjon" in detail, "both drives were read"


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_refused_drive_keeps_absence_unproven_either_way(tmp_path, sidecars):
    """A refused drive is a gap in the scan, which the sidecar records as such."""
    clean = [{"id": "i1", "name": "Budsjett.xlsx", "permissions": []}]
    files = await _onedrive(
        tmp_path,
        **{
            "drives/d-intra/items/root/children": clean,
            "drives/d-kari/root/permissions": refused(),
        },
    )
    assert "25_onedrive_sharing.json" in files

    status, detail = _verdict(report(tmp_path, sidecars=sidecars), "7.2.4")
    assert status == "info"
    assert "1 stasjon(er) kunne ikke leses" in detail


async def test_the_scan_verdict_does_not_hang_on_the_text_labels(tmp_path):
    await _onedrive(tmp_path)
    relabel(tmp_path / "25_onedrive_sharing.txt")

    assert _verdict(report(tmp_path), "7.2.4")[0] == "fail"
    assert _verdict(report(tmp_path, sidecars=False), "7.2.4")[0] == "info", (
        "the relabelled text alone has no 'Anyone' count to read"
    )


async def test_the_sidecar_keeps_each_finding_whole(tmp_path):
    """The text trims path and link to fit its columns; the sidecar does not."""
    import json

    files = await _onedrive(tmp_path)
    data = json.loads(files["25_onedrive_sharing.json"])

    assert ANON_URL not in files["25_onedrive_sharing.txt"], "trimmed to 40 characters"
    assert [a["link"] for a in data["anyone_links"]] == [ANON_URL]
    assert [e["path"] for e in data["external_shares"]] == [f"/Prosjekter/{LONG_FILE}"]
    grantee = data["external_shares"][0]["granted_to"][0]["user"]
    assert grantee["userPrincipalName"] == EXT_UPN
    assert data["complete"] is True and data["drives_scanned"] == 2
