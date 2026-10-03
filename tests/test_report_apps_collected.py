"""App registrations, credentials and consent grants, from the Apps collector's files.

CIS 2.1 and the OAuth recommendation read the tenant-wide consent grants in
17b_oauth_consent_grants.txt and the registration count in
17_app_registrations.txt; CIS 2.1.2, the credential recommendation and the
scheduler's alert read the expiry counts. The collector writes each as a text
for a person and a JSON sidecar for the report, which reads the sidecar first
and the text for runs recorded before it. Both are read here as a run leaves
them, through a real GraphClient answering from tests/collector_rig.py, and
through the report context itself.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.core.encryption import encrypted_write_text
from app.modules.m365_audit.sections.apps_oauth import AppsOAuthSection
from tests.collector_rig import FakeGraph, refused, run_sections
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


def _when(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


LONG_APP = "Kunde A Lønn og personal, integrasjon mot regnskap"
LONG_CERT = "Signeringssertifikat for Kunde A produksjon"
APPS = [
    {
        "id": "a1",
        "appId": "00000000-0000-0000-0000-0000000000a1",
        "displayName": "Kunde A Portal",
        "signInAudience": "AzureADMyOrg",
        "createdDateTime": "2024-02-01T08:00:00Z",
        "passwordCredentials": [{"displayName": "Gammel nøkkel", "endDateTime": _when(-10)}],
        "keyCredentials": [{"displayName": LONG_CERT, "endDateTime": _when(10)}],
    },
    {
        "id": "a2",
        "appId": "00000000-0000-0000-0000-0000000000a2",
        "displayName": LONG_APP,
        "signInAudience": "AzureADMultipleOrgs",
        "createdDateTime": "2025-06-01T08:00:00Z",
        "passwordCredentials": [{"displayName": "Hoved", "endDateTime": _when(400)}],
        "keyCredentials": [],
    },
    {
        "id": "a3",
        "appId": "00000000-0000-0000-0000-0000000000a3",
        "displayName": "Kunde A Uten Nøkler",
        "signInAudience": "AzureADMyOrg",
        "createdDateTime": "2025-09-01T08:00:00Z",
        "passwordCredentials": [],
        "keyCredentials": [],
    },
]


def _routes(**overrides) -> dict:
    routes = {
        "applications": APPS,
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


def _verdict(ctx: dict, cis_id: str) -> tuple[str, str]:
    row = next(r for r in ctx["compliance"] if r["cis_id"] == cis_id)
    return row["status"], str(row["detail"])


def _finding(ctx: dict, finding_id: str) -> dict | None:
    return next((r for r in ctx["recommendations"] if r.get("finding_id") == finding_id), None)


# ── Consent grants and registrations ─────────────────────────────────────────


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


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_grants_and_registrations_survive_the_round_trip(tmp_path, sidecars):
    files = await _apps(tmp_path)
    assert "17b_oauth_consent_grants.json" in files and "17_app_registrations.json" in files

    ctx = report(tmp_path, sidecars=sidecars)
    oauth = ctx["oauth"]

    assert oauth["total_grants"] == 6
    assert oauth["unique_apps"] == 6
    assert len(oauth["high_privilege_apps"]) == 3
    assert oauth["app_registrations"] == 3
    assert oauth["grants_read"] is True and oauth["has_data"] is True
    assert _verdict(ctx, "2.1") == (
        "info",
        "6 apps with 6 grants. 3 app registrations.",
    )
    assert _finding(ctx, "finding-oauth")["sub_items"] == oauth["high_privilege_apps"]


async def test_the_sidecar_keeps_app_names_whole(tmp_path):
    """Two apps the table cannot tell apart: their names share 40 characters."""
    await _apps(
        tmp_path,
        oauth2PermissionGrants=[*GRANTS, _grant("c-erp-test", "r-graph", "Sites.Read.All")],
        **{"servicePrincipals/c-erp-test": {"displayName": LONG_CLIENT + " (test)"}},
    )

    oauth = report(tmp_path)["oauth"]
    assert oauth["unique_apps"] == 7
    assert LONG_CLIENT in oauth["high_privilege_apps"]
    assert {g["app"] for g in oauth["admin_consent"]} >= {LONG_CLIENT, LONG_CLIENT + " (test)"}

    oauth = report(tmp_path, sidecars=False)["oauth"]
    assert oauth["unique_apps"] == 6, "both read as the same 40 characters"
    assert LONG_CLIENT[:40] in oauth["high_privilege_apps"]


async def test_the_registration_count_does_not_hang_on_the_banner(tmp_path):
    files = await _apps(tmp_path)
    path = tmp_path / "17_app_registrations.txt"
    encrypted_write_text(path, files["17_app_registrations.txt"].replace("(3 total)", ""))

    assert report(tmp_path)["oauth"]["app_registrations"] == 3
    assert report(tmp_path, sidecars=False)["oauth"]["app_registrations"] == 0


async def test_refused_grants_write_no_sidecar(tmp_path):
    files = await _apps(tmp_path, oauth2PermissionGrants=refused())
    assert "17b_oauth_consent_grants.json" not in files

    oauth = report(tmp_path)["oauth"]
    assert oauth["grants_read"] is False, "the refusal is not 'no high-privilege apps'"
    assert oauth["total_grants"] == 0
    assert oauth["app_registrations"] == 3


# ── Credential expiry ────────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_expired_credentials_are_found_either_way(tmp_path, sidecars):
    files = await _apps(tmp_path)
    assert "17c_app_credential_expiry.json" in files

    ctx = report(tmp_path, sidecars=sidecars)

    assert _verdict(ctx, "2.1.2") == ("fail", "1 utløpte app-credentials oppdaget")
    finding = _finding(ctx, "finding-cred-expiry")
    assert finding["priority"] == "high"
    assert str(finding["title"]).startswith("App registrations: 2 credential(s)")


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_healthy_credentials_pass_either_way(tmp_path, sidecars):
    healthy = [
        {**app, "passwordCredentials": [], "keyCredentials": []} if app["id"] == "a1" else app
        for app in APPS
    ]
    files = await _apps(tmp_path, applications=healthy)
    assert "17c_app_credential_expiry_WARN.txt" not in files, "nothing to warn about"

    ctx = report(tmp_path, sidecars=sidecars)
    assert _verdict(ctx, "2.1.2") == ("pass", "Ingen utløpte app-credentials")
    assert _finding(ctx, "finding-cred-expiry") is None


async def test_the_expiry_counts_do_not_hang_on_the_warning_text(tmp_path):
    await _apps(tmp_path)
    encrypted_write_text(tmp_path / "17c_app_credential_expiry_WARN.txt", "(layout changed)\n")

    ctx = report(tmp_path)
    assert _verdict(ctx, "2.1.2")[0] == "fail"
    assert _finding(ctx, "finding-cred-expiry") is not None

    ctx = report(tmp_path, sidecars=False)
    assert _verdict(ctx, "2.1.2")[0] == "pass", "no summary line left to read"
    assert _finding(ctx, "finding-cred-expiry") is None


async def test_the_sidecar_keeps_credential_names_whole(tmp_path):
    files = await _apps(tmp_path)
    data = json.loads(files["17c_app_credential_expiry.json"])

    assert (data["total"], data["expired"], data["critical"], data["ok"]) == (3, 1, 1, 1)
    assert LONG_APP not in files["17c_app_credential_expiry.txt"], "trimmed to 40"
    by_name = {c["name"]: c for c in data["credentials"]}
    assert by_name[LONG_CERT]["status"] == "CRITICAL"
    assert by_name["Hoved"]["app"] == LONG_APP


async def test_refused_registrations_leave_credentials_unverified(tmp_path):
    files = await _apps(tmp_path, applications=refused())
    assert "17_app_registrations.json" not in files
    assert "17c_app_credential_expiry.json" not in files

    assert _verdict(report(tmp_path), "2.1.2")[0] == "info", "cannot verify, as before"


@pytest.mark.parametrize("warning", ["as written", "relaid out"])
async def test_the_scheduler_alerts_on_expired_credentials_from_the_sidecar(
    tmp_path, monkeypatch, warning
):
    from app.services import audit_scheduler

    await _apps(tmp_path)
    if warning == "relaid out":
        path = tmp_path / "17c_app_credential_expiry_WARN.txt"
        encrypted_write_text(path, "(layout changed)\n")
    alert_on = {
        "risk_score_drop": False,
        "secure_score_drop": False,
        "new_risky_users": False,
        "expired_credentials": True,
        "new_nsg_warnings": False,
        "mfa_below_threshold": False,
    }
    monkeypatch.setattr(
        audit_scheduler,
        "get_scheduler_config",
        lambda: {"webhook_url": "https://hooks.example/alerts", "alert_on": alert_on},
    )
    sent: list[str] = []
    scheduler = audit_scheduler.AuditScheduler()

    async def capture(message: str) -> None:
        sent.append(message)

    monkeypatch.setattr(scheduler, "_send_webhook", capture)

    await scheduler._check_and_alert(report(tmp_path), "Acme AS")

    assert len(sent) == 1 and "App-credentials har utløpt" in sent[0]
