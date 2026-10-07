"""Backup of the Microsoft 365 data, from what the collector actually writes.

Until this section the report said nothing about whether mail and files were
backed up; it only cross-referenced Azure VMs with their vaults. These tests
run the real collector (sections/m365_backup.py) against a fake Graph
(tests/collector_rig.py) and read back what a run leaves on disk, through the
real parser, recommendation rule, compliance control, baselines and templates.

The rule they hold to: a refusal is not a zero. A 403, a 404 or a failed read
of either source leaves a workload "could not be read"; only a source that was
read and showed nothing counts as nothing. And a vendor's app with access is
evidence the product is installed, never "backup OK".
"""

from __future__ import annotations

import pathlib

import pytest

from app.core.baseline import evaluate
from app.modules.base import SectionStatus
from app.modules.m365_audit.collector import AuditCollector
from app.modules.m365_audit.sections.m365_backup import (
    BACKUP_PRODUCTS,
    M365BackupSection,
    match_product,
)
from app.reports.compliance import _build_compliance_map
from app.reports.generator import _jinja_env, build_report_context
from app.reports.i18n import T
from app.reports.parsers import _parse_m365_backup
from app.reports.recommendations import _build_recommendations
from tests.collector_rig import FakeGraph, read_output, refused

GRAPH_SP = "res-graph"
EXO_SP = "res-exo"

# The resource service principals an app's role assignments point at, with
# the app roles that name the permission values.
_RESOURCES = {
    f"servicePrincipals/{GRAPH_SP}": {
        "id": GRAPH_SP,
        "appId": "00000003-0000-0000-c000-000000000000",
        "displayName": "Microsoft Graph",
        "appRoles": [
            {"id": "role-files-read", "value": "Files.Read.All"},
            {"id": "role-mail-read", "value": "Mail.Read"},
            {"id": "role-sites-fc", "value": "Sites.FullControl.All"},
            {"id": "role-user-read", "value": "User.Read.All"},
            {"id": "role-chat-read", "value": "Chat.Read.All"},
        ],
    },
    f"servicePrincipals/{EXO_SP}": {
        "id": EXO_SP,
        "appId": "00000002-0000-0ff1-ce00-000000000000",
        "displayName": "Office 365 Exchange Online",
        "appRoles": [{"id": "role-faa", "value": "full_access_as_app"}],
    },
}


def _policy(pid: str, kind: str, status: str = "active", name: str = "") -> dict:
    return {
        "@odata.type": f"#microsoft.graph.{kind}ProtectionPolicy",
        "id": pid,
        "displayName": name or f"{kind} policy",
        "status": status,
        "retentionSettings": [{"interval": "R/PT10M", "period": "P2W"}],
    }


def _counts(pid: str, total: int, completed: int, in_progress: int = 0, failed: int = 0) -> dict:
    return {
        f"beta/solutions/backupRestore/protectionPolicies/{pid}": {
            "id": pid,
            "status": "active",
            "protectionMode": "standard",
            "protectionPolicyArtifactCount": {
                "total": total,
                "completed": completed,
                "inProgress": in_progress,
                "failed": failed,
            },
        }
    }


def _sp(sp_id: str, name: str, *, enabled: bool = True, owner: str = "tenant-x") -> dict:
    return {
        "id": sp_id,
        "appId": f"app-{sp_id}",
        "displayName": name,
        "appDisplayName": name,
        "appOwnerOrganizationId": owner,
        "accountEnabled": enabled,
        "servicePrincipalType": "Application",
    }


def _assignment(resource: str, role: str) -> dict:
    return {"appRoleId": role, "resourceId": resource, "resourceDisplayName": ""}


_ENABLED = {"serviceStatus": {"status": "enabled", "disableReason": "none"}}
_DISABLED = {"serviceStatus": {"status": "disabled", "disableReason": "none"}}

_ALL_PROTECTED = {
    "solutions/backupRestore": _ENABLED,
    "solutions/backupRestore/protectionPolicies": [
        _policy("pol-exo", "exchange"),
        _policy("pol-sp", "sharePoint"),
        _policy("pol-od", "oneDriveForBusiness"),
    ],
    **_counts("pol-exo", 45, 42),
    **_counts("pol-sp", 12, 12),
    **_counts("pol-od", 40, 38, in_progress=2),
    "servicePrincipals": [_sp("sp-teams", "Microsoft Teams", owner="tenant-ms")],
}

# Microsoft 365 Backup off, and no backup vendor among the service principals.
_NOTHING = {
    "solutions/backupRestore": _DISABLED,
    "solutions/backupRestore/protectionPolicies": [],
    "servicePrincipals": [
        _sp("sp-zoom", "Zoom"),
        # A mail filter from a vendor that also sells backup: not a backup app.
        _sp("sp-barracuda", "Barracuda Email Protection"),
    ],
    "servicePrincipals/sp-barracuda/appRoleAssignments": [_assignment(GRAPH_SP, "role-mail-read")],
    "servicePrincipals/sp-barracuda/oauth2PermissionGrants": [],
    **_RESOURCES,
}

_KEEPIT = {
    "solutions/backupRestore": _DISABLED,
    "solutions/backupRestore/protectionPolicies": [],
    "servicePrincipals": [_sp("sp-keepit", "Keepit Microsoft 365 Backup")],
    "servicePrincipals/sp-keepit/appRoleAssignments": [
        _assignment(EXO_SP, "role-faa"),
        _assignment(GRAPH_SP, "role-files-read"),
        _assignment(GRAPH_SP, "role-user-read"),
    ],
    "servicePrincipals/sp-keepit/oauth2PermissionGrants": [],
    **_RESOURCES,
}


async def _collect(tmp_path: pathlib.Path, routes: dict, *, sidecars: bool = True):
    async with FakeGraph(routes, page_size=2) as fake:
        section = M365BackupSection(tmp_path, fake.client)
        await section.collect()
    return section, read_output(tmp_path, sidecars=sidecars)


def _verdicts(reading: dict) -> dict[str, str]:
    return {w["key"]: w["verdict"] for w in reading["workloads"]}


def _rec(files: dict, lang: str = "no") -> dict | None:
    recs = _build_recommendations(
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 90.0, "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents=files,
        lang=lang,
    )
    return next((r for r in recs if r.get("title_key") == "rec_m365_backup_title"), None)


def _control(files: dict, lang: str = "no") -> dict:
    rows = _build_compliance_map({"file_contents": files}, lang=lang)
    return next(r for r in rows if r["cis_id"] == "CIS v8 11.2")


# ── Microsoft 365 Backup enabled ──────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only"])
async def test_enabled_with_policies_covers_every_workload(tmp_path, sidecars):
    section, files = await _collect(tmp_path, _ALL_PROTECTED, sidecars=sidecars)

    reading = _parse_m365_backup(files, totals={"exchange": 45, "sharepoint": 12})

    assert section.result.status == SectionStatus.DONE
    assert reading["has_data"] and reading["assessed"]
    assert _verdicts(reading) == {
        "exchange": "native",
        "onedrive": "native",
        "sharepoint": "native",
        "teams": "files_only",
    }
    assert reading["gaps"] == [] and reading["workloads_without_backup"] == 0
    exchange = reading["workloads"][0]
    assert exchange["native_text"] == "Microsoft 365 Backup: 42 av 45 beskyttet"
    onedrive = reading["workloads"][1]
    assert "38 beskyttet" in onedrive["native_text"]
    assert "2 under oppsett" in onedrive["native_text"]
    assert _rec(files) is None
    assert _control(files)["status"] == "pass"


async def test_the_counts_fall_back_to_the_unit_listing_when_beta_gives_none(tmp_path):
    """The artifact count is beta. Without it the v1.0 units are counted."""
    routes = {
        "solutions/backupRestore": _ENABLED,
        "solutions/backupRestore/protectionPolicies": [_policy("pol-exo", "exchange")],
        "beta/solutions/backupRestore/protectionPolicies/pol-exo": refused(400, "BadRequest"),
        "solutions/backupRestore/exchangeProtectionPolicies/pol-exo/mailboxProtectionUnits": [
            {"id": "u1", "status": "protected"},
            {"id": "u2", "status": "protected"},
            {"id": "u3", "status": "protectRequested"},
            {"id": "u4", "status": "unprotected", "error": {"code": "QuotaExceeded"}},
            {"id": "u5", "status": "unprotected"},
        ],
        "servicePrincipals": [],
    }
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)
    policy = reading["policies"][0]

    assert policy["units"]["source"] == "protection_units"
    assert (policy["units"]["protected"], policy["units"]["in_progress"]) == (2, 1)
    assert (policy["units"]["failed"], policy["units"]["total"]) == (1, 5)
    exchange = reading["workloads"][0]
    assert exchange["verdict"] == "native"
    assert exchange["level"] == "warning", "a failed unit is not a clean pass"
    # OneDrive and SharePoint have no policy and no app: those are real gaps.
    assert reading["gaps"] == ["onedrive", "sharepoint"]


async def test_full_service_mode_covers_the_workload_whatever_the_count(tmp_path):
    routes = {
        "solutions/backupRestore": _ENABLED,
        "solutions/backupRestore/protectionPolicies": [_policy("pol-sp", "sharePoint")],
        "beta/solutions/backupRestore/protectionPolicies/pol-sp": {
            "id": "pol-sp",
            "protectionMode": "fullServiceBackup",
        },
        "solutions/backupRestore/sharePointProtectionPolicies/pol-sp/siteProtectionUnits": [],
        "servicePrincipals": [],
    }
    _, files = await _collect(tmp_path, routes)

    sharepoint = _parse_m365_backup(files)["workloads"][2]

    assert sharepoint["verdict"] == "native"
    assert "hele tjenesten" in sharepoint["native_text"]


async def test_an_inactive_policy_protects_nothing(tmp_path):
    routes = {
        **_NOTHING,
        "solutions/backupRestore": _ENABLED,
        "solutions/backupRestore/protectionPolicies": [
            _policy("pol-exo", "exchange", status="inactive")
        ],
        **_counts("pol-exo", 10, 0),
    }
    _, files = await _collect(tmp_path, routes)

    exchange = _parse_m365_backup(files)["workloads"][0]

    assert exchange["verdict"] == "none"
    assert exchange["native_text"] == "Policyen i Microsoft 365 Backup er inaktiv"


async def test_a_locked_service_takes_no_new_backups(tmp_path):
    routes = {
        **_NOTHING,
        "solutions/backupRestore": {
            "serviceStatus": {
                "status": "protectionChangeLocked",
                "disableReason": "invalidBillingProfile",
            }
        },
        "solutions/backupRestore/protectionPolicies": [_policy("pol-exo", "exchange")],
        **_counts("pol-exo", 10, 10),
    }
    section, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert reading["gaps"] == ["exchange", "onedrive", "sharepoint"]
    assert "låst (protectionChangeLocked)" in reading["workloads"][0]["native_text"]
    assert any("protectionChangeLocked" in w for w in section.result.warns)


# ── Not enabled, nothing found ────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only"])
async def test_nothing_enabled_and_no_app_is_a_finding(tmp_path, sidecars):
    section, files = await _collect(tmp_path, _NOTHING, sidecars=sidecars)

    reading = _parse_m365_backup(files)
    rec = _rec(files)

    assert section.result.status == SectionStatus.DONE
    assert reading["gaps"] == ["exchange", "onedrive", "sharepoint"]
    assert reading["assessed"] and reading["workloads_without_backup"] == 3
    assert _verdicts(reading)["teams"] == "files_only", "Teams is shown, never judged"
    assert rec is not None
    assert rec["priority"] == "high"
    assert rec["sub_items"] == [
        "E-post (Exchange): Microsoft 365 Backup er ikke aktivert",
        "OneDrive: Microsoft 365 Backup er ikke aktivert",
        "SharePoint: Microsoft 365 Backup er ikke aktivert",
    ]
    assert "34_m365_backup.txt" in rec["evidence"]
    assert _control(files)["status"] == "fail"


async def test_the_finding_reads_in_english_for_an_english_report(tmp_path):
    _, files = await _collect(tmp_path, _NOTHING)

    rec = _rec(files, lang="en")
    row = _control(files, lang="en")

    assert rec["title"] == "Microsoft 365: no backup found for 3 workload(s)"
    assert rec["sub_items"][0] == "Email (Exchange): Microsoft 365 Backup is not enabled"
    assert row["detail"] == "No sign of backup for Email (Exchange), OneDrive and SharePoint"


async def test_a_mail_filter_from_a_backup_vendor_is_not_a_backup_app(tmp_path):
    """Barracuda sells mail filtering too; its filter reads mail."""
    _, files = await _collect(tmp_path, _NOTHING)

    reading = _parse_m365_backup(files)

    assert reading["apps"] == []
    assert reading["workloads"][0]["third_state"] == "none"


# ── Refusals are not zeros ────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only"])
async def test_a_403_on_microsoft_365_backup_is_unreadable_not_no_backup(tmp_path, sidecars):
    """A registration from before the permissions were added: the common case."""
    routes = {
        **_NOTHING,
        "solutions/backupRestore": refused(),
        "solutions/backupRestore/protectionPolicies": refused(),
    }
    section, files = await _collect(tmp_path, routes, sidecars=sidecars)

    reading = _parse_m365_backup(files)

    assert section.result.status == SectionStatus.DONE, "the vendor-app read still worked"
    assert reading["gaps"] == [] and reading["unknown"] == ["exchange", "onedrive", "sharepoint"]
    assert reading["assessed"] is False
    assert all(w["verdict"] == "unknown" for w in reading["workloads"][:3])
    assert reading["workloads"][0]["native_text"] == "Ikke lest: Graph avviste lesingen"
    assert "BackupRestore-Control.Read.All" in reading["unread_notes"][0]
    assert "BackupRestore-Configuration.Read.All" in reading["unread_notes"][1]
    assert _rec(files) is None
    row = _control(files)
    assert row["status"] == "info"
    assert "BackupRestore-Control.Read.All" in row["detail"]
    assert any(level == "info" for level in section.result.warn_levels)


async def test_a_refused_policy_read_names_its_own_permission(tmp_path):
    routes = {**_NOTHING, "solutions/backupRestore": _ENABLED}
    routes["solutions/backupRestore/protectionPolicies"] = refused()
    _, files = await _collect(tmp_path, routes)

    exchange = _parse_m365_backup(files)["workloads"][0]

    assert exchange["verdict"] == "unknown"
    assert "BackupRestore-Configuration.Read.All" in exchange["reason"]
    assert "BackupRestore-Configuration.Read.All" in _control(files)["detail"]


async def test_a_404_is_unknown_with_its_reason(tmp_path):
    routes = {**_NOTHING}
    del routes["solutions/backupRestore"]  # unrouted: the fake answers 404
    del routes["solutions/backupRestore/protectionPolicies"]
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert reading["unknown"] == ["exchange", "onedrive", "sharepoint"]
    assert reading["workloads"][0]["native_text"] == "Ikke lest: Graph svarte 404"
    assert "404" in reading["unread_notes"][0]
    assert _rec(files) is None


async def test_nothing_readable_at_all_fails_the_section_and_claims_nothing(tmp_path):
    routes = {
        "solutions/backupRestore": refused(),
        "solutions/backupRestore/protectionPolicies": refused(),
        "servicePrincipals": refused(),
    }
    section, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert section.result.status == SectionStatus.FAILED
    assert reading["gaps"] == []
    assert _verdicts(reading)["teams"] == "unknown"
    assert _rec(files) is None
    assert _control(files)["status"] == "info"


async def test_an_unreadable_vendor_list_leaves_a_disabled_service_unknown(tmp_path):
    """Microsoft 365 Backup off says nothing about a vendor product."""
    routes = {**_NOTHING, "servicePrincipals": refused()}
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert reading["gaps"] == []
    assert reading["unknown"] == ["exchange", "onedrive", "sharepoint"]
    assert _rec(files) is None


@pytest.mark.parametrize("payload", ["", "Error: HTTP 403 Forbidden\n"], ids=["absent", "stub"])
def test_a_file_that_never_carried_data_is_no_reading(payload):
    files = {"34_m365_backup.txt": payload} if payload else {}

    reading = _parse_m365_backup(files)

    assert reading["has_data"] is False and reading["gaps"] == []
    assert _rec(files) is None
    assert _control(files)["status"] == "info"


# ── Third-party products ──────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only"])
async def test_a_vendor_app_with_access_is_evidence_not_proof(tmp_path, sidecars):
    _, files = await _collect(tmp_path, _KEEPIT, sidecars=sidecars)

    reading = _parse_m365_backup(files)
    row = _control(files)

    assert _verdicts(reading) == {
        "exchange": "third_party",
        "onedrive": "third_party",
        "sharepoint": "third_party",
        "teams": "files_only",
    }
    assert reading["workloads"][0]["third_text"] == "Fant backupappen Keepit med tilgang"
    app = reading["apps"][0]
    assert app["name"] == "Keepit"
    assert app["access"] == "e-post, OneDrive og SharePoint"
    assert _rec(files) is None
    # Not a pass: the tenant cannot say whether the product's backups run.
    assert row["status"] == "info"
    assert "Keepit" in row["detail"] and "kan ikke leses" in row["detail"]


async def test_the_app_records_what_it_may_read(tmp_path):
    _, files = await _collect(tmp_path, _KEEPIT)

    app = _parse_m365_backup(files)["apps"][0]

    assert {"value": "full_access_as_app", "resource": "Office 365 Exchange Online"} in (
        app["application_permissions"]
    )
    assert app["workloads"] == ["exchange", "onedrive", "sharepoint"]


async def test_chat_access_puts_teams_in_the_vendor_column(tmp_path):
    routes = {**_KEEPIT}
    routes["servicePrincipals/sp-keepit/appRoleAssignments"] = [
        _assignment(GRAPH_SP, "role-chat-read")
    ]
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert _verdicts(reading)["teams"] == "third_party"
    assert reading["gaps"] == ["exchange", "onedrive", "sharepoint"]


async def test_a_delegated_grant_counts_as_access(tmp_path):
    routes = {**_KEEPIT}
    routes["servicePrincipals/sp-keepit/appRoleAssignments"] = []
    routes["servicePrincipals/sp-keepit/oauth2PermissionGrants"] = [
        {"resourceId": EXO_SP, "scope": "EWS.AccessAsUser.All"}
    ]
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert _verdicts(reading)["exchange"] == "third_party"
    assert reading["gaps"] == ["onedrive", "sharepoint"]


async def test_a_disabled_vendor_app_is_no_evidence(tmp_path):
    routes = {**_KEEPIT}
    routes["servicePrincipals"] = [_sp("sp-keepit", "Keepit", enabled=False)]
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert reading["gaps"] == ["exchange", "onedrive", "sharepoint"]
    assert reading["apps"][0]["enabled"] is False


async def test_a_vendor_app_whose_permissions_cannot_be_read_leaves_it_unknown(tmp_path):
    routes = {**_KEEPIT, "servicePrincipals/sp-keepit/appRoleAssignments": refused()}
    _, files = await _collect(tmp_path, routes)

    reading = _parse_m365_backup(files)

    assert reading["gaps"] == []
    assert reading["unknown"] == ["exchange", "onedrive", "sharepoint"]
    assert "Keepit" in reading["workloads"][0]["third_text"]
    assert "Keepit" in _control(files)["detail"]


async def test_an_unknown_product_called_backup_counts_only_with_data_access(tmp_path):
    routes = {
        **_NOTHING,
        "servicePrincipals": [
            _sp("sp-contoso", "Contoso Cloud Backup"),
            _sp("sp-intune", "Intune Config Backup Tool"),
            _sp(
                "sp-ms",
                "Microsoft 365 Backup Storage",
                owner="f8cdef31-a31e-4b4a-93e4-5f571e91255a",
            ),
        ],
        "servicePrincipals/sp-contoso/appRoleAssignments": [
            _assignment(GRAPH_SP, "role-mail-read")
        ],
        "servicePrincipals/sp-contoso/oauth2PermissionGrants": [],
        "servicePrincipals/sp-intune/appRoleAssignments": [_assignment(GRAPH_SP, "role-user-read")],
        "servicePrincipals/sp-intune/oauth2PermissionGrants": [],
    }
    async with FakeGraph(routes) as fake:
        await M365BackupSection(tmp_path, fake.client).collect()
        asked = {r.url.path for r in fake.requests}
    files = read_output(tmp_path)

    reading = _parse_m365_backup(files)

    assert [a["display_name"] for a in reading["apps"]] == ["Contoso Cloud Backup"]
    assert reading["apps"][0]["match"] == "generic"
    assert _verdicts(reading)["exchange"] == "third_party"
    # Microsoft's own backup service principal is the native service, not a vendor.
    assert not any("sp-ms" in path for path in asked)


@pytest.mark.parametrize(
    ("name", "product"),
    [
        ("Veeam Backup for Microsoft 365", "Veeam Backup for Microsoft 365"),
        ("Backupify", "Datto SaaS Protection"),
        ("AvePoint Cloud Backup", "AvePoint Cloud Backup"),
        ("Barracuda Cloud-to-Cloud Backup", "Barracuda Cloud-to-Cloud Backup"),
        ("Spanning Backup for Office 365", "Spanning Backup"),
        ("SkyKick Cloud Backup", "SkyKick Cloud Backup"),
        ("Metallic Office 365 Backup", "Commvault Metallic"),
        ("Druva inSync", "Druva"),
        ("CloudAlly Backup", "CloudAlly"),
        ("Synology Active Backup for Microsoft 365", "Synology Active Backup"),
        ("Redstor Backup", "Redstor"),
        ("Acronis Cyber Protect", "Acronis Cyber Protect"),
        ("Dropsuite", "Dropsuite / NinjaOne SaaS Backup"),
        ("Keepit", "Keepit"),
    ],
)
def test_each_named_product_is_recognised(name, product):
    matched = match_product({"displayName": name})
    assert matched is not None and matched[0].name == product


@pytest.mark.parametrize(
    "name",
    [
        "AvePoint Fly",  # migration
        "Barracuda Email Protection",  # mail filtering
        "SkyKick Migration Suite",  # migration
        "Hornetsecurity Email Security",  # mail filtering
        "Zoom",
    ],
)
def test_a_vendors_other_products_are_not_backup(name):
    assert match_product({"displayName": name}) is None


def test_every_product_pattern_is_a_valid_expression():
    import re

    for product in BACKUP_PRODUCTS:
        for pattern in product.patterns:
            re.compile(pattern)


# ── Registration and permissions ──────────────────────────────────────────────


def test_the_section_is_selectable_and_runs():
    assert "Microsoft 365 Backup" in AuditCollector.GRAPH_SECTION_NAMES
    src = pathlib.Path("app/modules/m365_audit/collector.py").read_text()
    assert "M365BackupSection(" in src


def test_existing_registrations_without_the_backup_permissions_stay_valid():
    """Warn-only: a registration from before keeps auditing, the section says why."""
    from app.core.config import REQUIRED_GRAPH_PERMISSIONS
    from app.modules.m365_audit.graph_client import GraphClient

    for perm in ("BackupRestore-Control.Read.All", "BackupRestore-Configuration.Read.All"):
        assert perm in REQUIRED_GRAPH_PERMISSIONS
        assert perm in GraphClient._WARN_ONLY_PERMISSIONS


async def test_the_healthy_fixture_is_what_the_collector_writes(tmp_path):
    """tests/audit_fixture.py carries 34_m365_backup by hand; it must not drift."""
    import json

    from tests.audit_fixture import FULL_AUDIT

    routes = {
        "solutions/backupRestore": {
            "serviceStatus": {
                "status": "enabled",
                "disableReason": "none",
                "backupServiceConsumer": "firstparty",
            }
        },
        "solutions/backupRestore/protectionPolicies": [
            _policy("pol-exchange", "exchange", name="Acme e-post"),
            _policy("pol-sharepoint", "sharePoint", name="Acme SharePoint"),
            _policy("pol-onedrive", "oneDriveForBusiness", name="Acme OneDrive"),
        ],
        **_counts("pol-exchange", 12, 12),
        **_counts("pol-sharepoint", 6, 6),
        **_counts("pol-onedrive", 10, 10),
        "servicePrincipals": [_sp("sp-teams", "Microsoft Teams", owner="tenant-ms")],
    }
    _, files = await _collect(tmp_path, routes)

    assert files["34_m365_backup.txt"] == FULL_AUDIT["34_m365_backup.txt"]
    assert json.loads(files["34_m365_backup.json"]) == json.loads(FULL_AUDIT["34_m365_backup.json"])
    assert _parse_m365_backup(FULL_AUDIT)["gaps"] == []
    assert _control(FULL_AUDIT)["status"] == "pass"


# ── Baselines ─────────────────────────────────────────────────────────────────


def _baseline_check(baseline_id: str, check_id: str, m365_backup: dict) -> dict:
    result = evaluate(baseline_id, {"m365_backup": m365_backup})
    return next(c for c in result["checks"] if c["id"] == check_id)


@pytest.mark.parametrize(
    ("baseline_id", "check_id"),
    [("essential-8-l1", "e8-m365-backup"), ("nis2-hardening", "nis2-m365-backup")],
)
async def test_the_baselines_judge_m365_backup_and_skip_an_unread_one(
    tmp_path, baseline_id, check_id
):
    nothing = tmp_path / "nothing"
    keepit = tmp_path / "keepit"
    refusal = tmp_path / "refused"
    for directory in (nothing, keepit, refusal):
        directory.mkdir()
    _, nothing_files = await _collect(nothing, _NOTHING)
    _, keepit_files = await _collect(keepit, _KEEPIT)
    _, refused_files = await _collect(
        refusal,
        {
            **_NOTHING,
            "solutions/backupRestore": refused(),
            "solutions/backupRestore/protectionPolicies": refused(),
        },
    )

    failed = _baseline_check(baseline_id, check_id, _parse_m365_backup(nothing_files))
    passed = _baseline_check(baseline_id, check_id, _parse_m365_backup(keepit_files))
    unread = _baseline_check(baseline_id, check_id, _parse_m365_backup(refused_files))

    assert failed["status"] == "fail"
    assert passed["status"] == "pass"
    assert unread["status"] == "not_measured"


# ── The report ────────────────────────────────────────────────────────────────


def _context(run: pathlib.Path, lang: str = "no") -> dict:
    ctx = build_report_context("Acme AS", "acme.example", run, [], lang=lang, persist_metrics=False)
    ctx["t"] = T(lang)
    ctx["lang"] = lang
    ctx["theme"] = "light"
    return ctx


def _render(ctx: dict, template: str) -> str:
    return _jinja_env().get_template(template).render(**ctx)


async def test_the_report_context_carries_the_reading(tmp_path):
    await _collect(tmp_path, _NOTHING)

    ctx = _context(tmp_path)

    assert ctx["m365_backup"]["gaps"] == ["exchange", "onedrive", "sharepoint"]
    titles = [r["title"] for r in ctx["recommendations"]]
    assert "Microsoft 365: ingen backup funnet for 3 arbeidslast(er)" in titles
    row = next(c for c in ctx["compliance"] if c["cis_id"] == "CIS v8 11.2")
    assert row["status"] == "fail"
    assert row["evidence"] == ["34_m365_backup.json", "34_m365_backup.txt"]
    assert row["nist_id"].startswith("PR.DS-11")
    assert row["iso_id"].startswith("A.8.13")


async def test_protected_mailboxes_are_set_against_the_mailboxes_the_audit_counted(tmp_path):
    import json

    await _collect(tmp_path, _ALL_PROTECTED)
    (tmp_path / "20_exchange_mailboxes_count.json").write_text(
        json.dumps({"total": 45, "user": 40, "shared": 5}), encoding="utf-8"
    )

    exchange = _context(tmp_path)["m365_backup"]["workloads"][0]

    assert exchange["native_text"] == "Microsoft 365 Backup: 42 av 45 beskyttet"


async def test_an_unread_mailbox_count_is_no_total(tmp_path):
    await _collect(tmp_path, _ALL_PROTECTED)

    exchange = _context(tmp_path)["m365_backup"]["workloads"][0]

    assert exchange["native_text"] == "Microsoft 365 Backup: 42 beskyttet"


@pytest.mark.parametrize("lang", ["no", "en"])
async def test_both_reports_show_the_backup_section(tmp_path, lang):
    await _collect(tmp_path, _KEEPIT)
    ctx = _context(tmp_path, lang)
    t = T(lang)

    customer = _render(ctx, "report_customer.html.j2")
    tech = _render(ctx, "report_tech.html.j2")

    for html in (customer, tech):
        assert str(t.m365_backup_title) in html
        assert str(t.m365_backup_verdict_third_party) in html
        assert str(t.m365_backup_proof_note) in html
        assert "None" not in html.split(str(t.m365_backup_title), 1)[1].split("</table>", 1)[0]
    assert 'href="#m365backup"' in customer and 'id="m365backup"' in customer
    assert 'id="m365backup"' in tech
    # The technical report names the app as it is registered, and its access.
    assert "Keepit Microsoft 365 Backup" in tech
    assert "full_access_as_app" in tech


async def test_the_technical_report_says_which_permission_to_grant(tmp_path):
    routes = {
        **_NOTHING,
        "solutions/backupRestore": refused(),
        "solutions/backupRestore/protectionPolicies": refused(),
    }
    await _collect(tmp_path, routes)
    ctx = _context(tmp_path)

    tech = _render(ctx, "report_tech.html.j2")
    customer = _render(ctx, "report_customer.html.j2")

    assert str(T("no").m365_backup_grant_hint) in tech
    assert "Authorization_RequestDenied" in tech, "the raw Graph answer, for the technician"
    assert str(T("no").m365_backup_verdict_unknown) in customer
    assert str(T("no").m365_backup_verdict_none) not in customer


async def test_a_run_without_the_section_shows_no_backup_section(tmp_path):
    (tmp_path / "01_tenant.txt").write_text("TENANT\n", encoding="utf-8")
    ctx = _context(tmp_path)

    customer = _render(ctx, "report_customer.html.j2")

    assert ctx["m365_backup"]["has_data"] is False
    assert 'id="m365backup"' not in customer


def test_backup_service_registration_is_distinct_from_graph_consent(tmp_path):
    import json

    from app.modules.m365_audit.graph_client import GraphPermissionError
    from app.modules.m365_audit.sections.m365_backup import _failure

    error = GraphPermissionError(
        "solutions/backupRestore",
        403,
        json.dumps(
            {"error": {"code": "AppNotRegistered", "message": "Application is not registered."}}
        ),
    )
    kind, detail = _failure(error)
    assert kind == "not_registered"
    assert "separate from Graph permissions" in detail
    section = M365BackupSection(tmp_path, None)
    section._warn_findings(
        {
            "service": {"read": False, "error_kind": kind, "error": detail},
            "policies": {"read": False, "error_kind": kind, "error": detail},
        },
        {"read": True},
    )
    assert all(
        "needs BackupRestore" not in str(w) and "need BackupRestore" not in str(w)
        for w in section.result.warns
    )
    assert any("AppNotRegistered" in str(w) for w in section.result.warns)
