"""Policies in production are consolidated onto the customer card.

An audit captures the tenant's live policy objects as per-run snapshots; this
lifts the latest set onto the customer card with a plain-language line per
policy, so a technician always sees what is configured without opening a run.
"""

from __future__ import annotations

import json

import pytest

from app.core import customer as customer_module
from app.core.encryption import encrypted_write_text
from app.core.policy_inventory import (
    build_inventory,
    load_from_card,
    persist_from_run,
)


def _write_snapshot(run_dir, name, source, items):
    snap = run_dir / "policy_snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    envelope = {
        "snapshot": name,
        "source": source,
        "captured_at": "2026-08-18T10:38:00+00:00",
        "count": len(items),
        "items": items,
    }
    encrypted_write_text(snap / f"{name}.json", json.dumps(envelope))


_CA_POLICIES = [
    {
        "displayName": "Sybr — Require MFA for all users",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {
            "users": {"includeUsers": ["All"]},
            "clientAppTypes": ["all"],
        },
        "grantControls": {"builtInControls": ["mfa"]},
    },
    {
        "displayName": "Sybr — Block legacy authentication",
        "state": "enabled",
        "conditions": {
            "users": {"includeUsers": ["All"]},
            "clientAppTypes": ["exchangeActiveSync", "other"],
        },
        "grantControls": {"builtInControls": ["block"]},
    },
    {
        "displayName": "Sybr — Require MFA for administrators",
        "state": "disabled",
        "conditions": {
            "users": {"includeRoles": ["r1", "r2", "r3"]},
            "clientAppTypes": ["all"],
        },
        "grantControls": {"builtInControls": ["mfa"]},
    },
]


@pytest.fixture()
def run_dir(tmp_path):
    """An <audit>/<customer_id>/<run> directory with captured snapshots."""
    d = tmp_path / "audit" / "Acme_AS" / "2026-08-18_1038"
    d.mkdir(parents=True)
    _write_snapshot(d, "conditional_access_policies",
                    "identity/conditionalAccess/policies", _CA_POLICIES)
    _write_snapshot(d, "named_locations",
                    "identity/conditionalAccess/namedLocations",
                    [{"displayName": "Office", "isTrusted": True,
                      "ipRanges": [{"cidrAddress": "10.0.0.0/8"}]}])
    _write_snapshot(d, "intune_compliance_policies",
                    "deviceManagement/deviceCompliancePolicies",
                    [{"displayName": "Windows baseline",
                      "@odata.type": "#microsoft.graph.windows10CompliancePolicy"}])
    return d


# ── build_inventory ───────────────────────────────────────────────────────────

def test_it_groups_policies_by_workload(run_dir):
    inv = build_inventory(run_dir)
    assert inv is not None
    assert inv["run"] == "2026-08-18_1038"
    assert set(inv["workloads"]) == {
        "conditional_access", "named_locations", "intune_compliance"
    }
    assert inv["workloads"]["conditional_access"]["count"] == 3
    assert inv["total"] == 5


def test_conditional_access_state_is_mapped_and_described(run_dir):
    ca = build_inventory(run_dir)["workloads"]["conditional_access"]["items"]
    by_name = {i["name"]: i for i in ca}
    assert by_name["Sybr — Require MFA for all users"]["state"] == "report-only"
    assert by_name["Sybr — Block legacy authentication"]["state"] == "on"
    assert by_name["Sybr — Require MFA for administrators"]["state"] == "off"
    # Plain-language description, both languages, saying what it does + to whom.
    mfa_all = by_name["Sybr — Require MFA for all users"]["summary"]
    assert "MFA" in mfa_all["en"] and "all users" in mfa_all["en"]
    assert "MFA" in mfa_all["no"] and "alle brukere" in mfa_all["no"]
    legacy = by_name["Sybr — Block legacy authentication"]["summary"]
    assert "legacy authentication" in legacy["en"]
    admins = by_name["Sybr — Require MFA for administrators"]["summary"]
    assert "admin roles" in admins["en"]


def test_the_modern_intune_surfaces_become_card_workloads(tmp_path):
    """Settings Catalog, admin templates, app protection and endpoint security
    are lifted onto the card the same way compliance and config already are —
    each with a plain-language per-policy line."""
    d = tmp_path / "audit" / "Acme_AS" / "2026-08-19_0500"
    d.mkdir(parents=True)
    _write_snapshot(d, "intune_settings_catalog",
                    "deviceManagement/configurationPolicies",
                    [{"name": "Win — BitLocker", "platforms": "windows10", "technologies": "mdm"}])
    _write_snapshot(d, "intune_app_protection",
                    "deviceAppManagement/managedAppPolicies",
                    [{"displayName": "iOS MAM",
                      "@odata.type": "#microsoft.graph.iosManagedAppProtection"}])
    _write_snapshot(d, "intune_admin_templates",
                    "deviceManagement/groupPolicyConfigurations",
                    [{"displayName": "Edge hardening"}])
    _write_snapshot(d, "intune_endpoint_security",
                    "deviceManagement/intents (beta)",
                    [{"displayName": "Defender AV baseline"}])

    inv = build_inventory(d)
    assert inv is not None
    w = inv["workloads"]

    sc = w["intune_settings_catalog"]["items"][0]
    assert sc["name"] == "Win — BitLocker"
    assert "windows10" in sc["summary"]["en"] and "windows10" in sc["summary"]["no"]

    assert w["intune_app_protection"]["items"][0]["summary"]["en"] == "Platform: iOS"
    assert w["intune_admin_templates"]["items"][0]["summary"]["en"] == "Administrative templates"
    assert w["intune_endpoint_security"]["items"][0]["summary"]["en"] == "Endpoint security"
    assert inv["total"] == 4


def test_no_snapshots_yields_none(tmp_path):
    empty = tmp_path / "cust" / "run"
    empty.mkdir(parents=True)
    assert build_inventory(empty) is None


# ── persist to / load from the customer card ─────────────────────────────────

def test_persist_writes_to_the_customer_card_and_loads_back(run_dir, tmp_path, monkeypatch):
    customers_root = tmp_path / "customers"
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", customers_root)

    ok = persist_from_run(run_dir)
    assert ok is True

    # customer_id is the run's parent dir name — the card key.
    loaded = load_from_card("Acme_AS")
    assert loaded is not None
    assert loaded["total"] == 5
    assert loaded["workloads"]["conditional_access"]["count"] == 3
    assert (customers_root / "Acme_AS" / "policies_live.json").is_file()


def test_persist_with_no_snapshots_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(customer_module, "_CUSTOMERS_DIR", tmp_path / "customers")
    empty = tmp_path / "audit" / "Nobody" / "run"
    empty.mkdir(parents=True)
    assert persist_from_run(empty) is False
    assert load_from_card("Nobody") is None
