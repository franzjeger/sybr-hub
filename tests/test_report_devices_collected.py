"""The Intune and Entra device registers, from the files their collectors write.

Each collector writes its register twice: the fixed-width text for a person,
and a JSON sidecar beside it for the report. Both are read here exactly as a
run leaves them, through a real GraphClient answering from
tests/collector_rig.py, and through build_report_context, which is what wires
each file to its parser. Where the text is precise enough the two must give
the same answer, since the text is the fallback for runs from before the
sidecar. Where it is not (a device name past the column width, a count the
text never carried) the sidecar must win.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.entra_devices import EntraDevicesSection
from app.modules.m365_audit.sections.intune import IntuneSection
from app.reports.generator import build_report_context
from tests.collector_rig import FakeGraph

# Longer than the 35-character device-name column in both tables.
LONG_NAME = "Kunde A sin iPad Pro 12,9 tommer (6. generasjon)"
assert len(LONG_NAME) > 35


def _managed(name: str, os: str, state: str) -> dict:
    return {
        "deviceName": name,
        "operatingSystem": os,
        "osVersion": "10.0.22631.4317",
        "managedDeviceOwnerType": "company",
        "complianceState": state,
        "lastSyncDateTime": "2026-10-01T08:00:00Z",
    }


def _registered(name: str, *, managed, enabled=True, trust="AzureAd") -> dict:
    return {
        "displayName": name,
        "operatingSystem": "Windows",
        "operatingSystemVersion": "10.0.22631.4317",
        "trustType": trust,
        "isManaged": managed,
        "isCompliant": None,
        "accountEnabled": enabled,
        "approximateLastSignInDateTime": "2026-10-01T08:00:00Z",
    }


MANAGED = [
    _managed("LAPTOP-01", "Windows", "compliant"),
    _managed(LONG_NAME, "iOS", "noncompliant"),
    _managed("ANDROID-01", "Android", "noncompliant"),
    _managed("MAC-01", "macOS", "inGracePeriod"),
    _managed("LAPTOP-02", "Windows", "unknown"),
]

REGISTERED = [
    _registered("LAPTOP-01", managed=True),
    _registered(LONG_NAME, managed=False),
    _registered("OLD-PC", managed=False, enabled=False, trust="ServerAd"),
    _registered("BYOD-PHONE", managed=None, trust=None),
]

POLICIES = [
    {
        "@odata.type": "#microsoft.graph.windows10CompliancePolicy",
        "displayName": "Windows 11 baseline",
        "createdDateTime": "2026-01-02T08:00:00Z",
    },
    {
        "@odata.type": "#microsoft.graph.iosCompliancePolicy",
        "displayName": "iOS minimum",
        "createdDateTime": "2026-01-02T08:00:00Z",
    },
]


def _routes(policies: list[dict]) -> dict:
    return {
        "deviceManagement/managedDevices": MANAGED,
        "deviceManagement/deviceCompliancePolicies": policies,
        "deviceManagement/deviceConfigurations": [],
        "deviceManagement/configurationPolicies": [],
        "deviceManagement/groupPolicyConfigurations": [],
        "deviceAppManagement/mobileApps": [],
        "deviceAppManagement/managedAppPolicies": [],
        "deviceManagement/detectedApps": [],
        "deviceManagement/windowsAutopilotDeviceIdentities": [],
        "deviceManagement/intents": [],
        "devices": REGISTERED,
    }


async def _context(tmp_path, *, sidecars: bool, policies: list[dict] = POLICIES) -> dict:
    """Run both sections, then build the report context from what they left.

    The run sits two levels down so the trend loader finds no sibling runs.
    sidecars=False deletes the .json files first: a run from before them.
    """
    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    async with FakeGraph(_routes(policies), page_size=2) as fake:
        results = [
            await IntuneSection(run, fake.client).collect(),
            await EntraDevicesSection(run, fake.client).collect(),
        ]
        assert fake.unrouted == [], "every call the sections made was answered"
    written = {p.name for p in run.glob("*.json")}
    assert {"10_intune_devices.json", "15_entra_devices.json"} <= written
    assert "11_intune_compliance_policies.json" in written
    if not sidecars:
        for path in run.glob("*.json"):
            path.unlink()
    return build_report_context(
        "Acme AS", "acme.example", run, results, lang="en", persist_metrics=False
    )


def _row(ctx: dict, cis_id: str) -> dict:
    return next(row for row in ctx["compliance"] if row["cis_id"] == cis_id)


# ── Intune ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_intune_counts_survive_the_round_trip(tmp_path, sidecars):
    intune = (await _context(tmp_path, sidecars=sidecars))["intune"]

    assert intune["has_data"] is True
    assert intune["total"] == 5
    assert intune["compliant"] == 1
    assert intune["noncompliant"] == 2
    assert intune["unknown"] == 2, "in grace period and unknown are neither"
    assert intune["compliance_pct"] == 20.0
    assert [d["compliance"] for d in intune["devices"]] == [
        "compliant",
        "noncompliant",
        "noncompliant",
        "inGracePeriod",
        "unknown",
    ]
    assert [d["os"] for d in intune["devices"]] == ["Windows", "iOS", "Android", "macOS", "Windows"]
    assert {d["user"] for d in intune["devices"]} == {"company"}
    assert len(intune["noncompliant_devices"]) == 4


async def test_the_sidecar_keeps_a_device_name_the_table_cuts(tmp_path):
    with_json = (await _context(tmp_path / "a", sidecars=True))["intune"]
    text_only = (await _context(tmp_path / "b", sidecars=False))["intune"]

    assert with_json["devices"][1]["name"] == LONG_NAME
    assert text_only["devices"][1]["name"] == LONG_NAME[:35]
    assert with_json["noncompliant_devices"][0]["name"] == LONG_NAME


async def test_the_sidecar_carries_the_platform_split(tmp_path):
    """The count file has never written a per-platform line, so a report read
    from it alone showed Windows 0, iOS 0, Android 0 for every tenant."""
    intune = (await _context(tmp_path, sidecars=True))["intune"]

    assert (intune["windows"], intune["ios"], intune["android"], intune["macos"]) == (2, 1, 1, 1)


async def test_the_unmanaged_gap_comes_from_the_entra_register(tmp_path):
    intune = (await _context(tmp_path, sidecars=True))["intune"]

    assert intune["entra_total"] == 4
    assert intune["entra_unmanaged"] == 3


# ── Compliance policies (CIS 6.1.1) ───────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_configured_policies_are_counted_either_way(tmp_path, sidecars):
    row = _row(await _context(tmp_path, sidecars=sidecars), "6.1.1")

    # Two policies configured, 20% of enrolled devices compliant.
    assert row["status"] == "partial"


async def test_a_policy_named_like_a_placeholder_still_counts(tmp_path):
    """The row counter skips a line starting with "No " as a "(none)"-style
    placeholder, so a tenant whose one policy is "No jailbroken devices" read
    as having no compliance policy at all, and failed 6.1.1 on it."""
    only = [{**POLICIES[1], "displayName": "No jailbroken devices"}]

    with_json = _row(await _context(tmp_path / "a", sidecars=True, policies=only), "6.1.1")
    text_only = _row(await _context(tmp_path / "b", sidecars=False, policies=only), "6.1.1")

    assert with_json["status"] == "partial"
    assert text_only["status"] == "fail", "the text alone cannot carry this policy"


# ── Entra register ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_entra_counts_survive_the_round_trip(tmp_path, sidecars):
    entra = (await _context(tmp_path, sidecars=sidecars))["entra_devices"]

    assert entra["has_data"] is True
    assert entra["total"] == 4
    assert entra["managed"] == 1
    assert entra["unmanaged"] == 3, "isManaged null is not managed"
    assert entra["enabled"] == 3


def test_the_entra_sidecar_alone_is_enough():
    """The reader takes the counts from the sidecar, not from the text beside it."""
    from app.reports.parsers import _parse_entra_devices

    sidecar = {"total": 4, "managed": 1, "unmanaged": 3, "enabled": 3, "devices": []}

    parsed = _parse_entra_devices("", "", sidecar)

    assert parsed["has_data"] is True
    assert (parsed["total"], parsed["managed"], parsed["unmanaged"]) == (4, 1, 3)
