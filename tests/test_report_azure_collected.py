"""The Azure overview, from the files the Azure collectors write.

Each collector writes one text file per subscription for a person, and a JSON
sidecar beside it for the report. These tests run the real collectors against
fake Azure SDK clients (tests/collector_rig.py) and read back exactly what they
leave on disk. Where the text is precise enough, the report must give the same
answer from the sidecar as from the text alone (a run from before the
sidecar). Where it is not (a column cut at its width, or a full column running
into the next) the sidecar must win. With two subscriptions, one whose read
failed writes only its text error, and must not be hidden by the other's
sidecar or read as empty.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.modules.m365_audit.sections.azure_compute import AzureComputeSection
from app.reports.parsers import _parse_azure_overview
from tests.collector_rig import FakeAzureAuth, read_output

SUB_A = "00000000-0000-0000-0000-0000000000a1"
SUB_B = "00000000-0000-0000-0000-0000000000b2"
SUBS = ((SUB_A, "Prod-A"), (SUB_B, "Prod-B"))


def _id(sub: str, rg: str, provider: str, name: str) -> str:
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{name}"


def _read(tmp_path, *, sidecars: bool) -> dict:
    return read_output(tmp_path, sidecars=sidecars)


def _drop(files: dict, prefix: str) -> dict:
    """The run without one subscription's sidecar: read before it existed."""
    return {n: t for n, t in files.items() if not (n.startswith(prefix) and n.endswith(".json"))}


# ── Virtual machines (30_azure_vms) ───────────────────────────────────────────


def _vm(sub: str, name: str, *, rg="rg-prod", location="westeurope", size="Standard_D2s_v3"):
    return SimpleNamespace(
        name=name,
        id=_id(sub, rg, "Microsoft.Compute/virtualMachines", name),
        location=location,
        storage_profile=SimpleNamespace(os_disk=SimpleNamespace(os_type="Windows")),
        hardware_profile=SimpleNamespace(vm_size=size),
        instance_view=SimpleNamespace(statuses=[SimpleNamespace(code="PowerState/running")]),
    )


async def _collect_vms(tmp_path, per_sub: dict, *, multi: bool) -> None:
    auth = FakeAzureAuth(
        subscriptions={
            sub: {"compute": {"virtual_machines.list_all": vms}} for sub, vms in per_sub.items()
        }
    )
    for sub, name in SUBS:
        if sub in per_sub:
            await AzureComputeSection(
                tmp_path, auth, sub_id=sub, sub_name=name, multi=multi
            )._collect_vms()


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_vm_table_survives_the_round_trip(tmp_path, sidecars):
    await _collect_vms(
        tmp_path, {SUB_A: [_vm(SUB_A, "vm-dc-01"), _vm(SUB_A, "vm-app-01")]}, multi=False
    )

    vms = _parse_azure_overview(_read(tmp_path, sidecars=sidecars))["vms"]

    assert vms == [
        {
            "name": name,
            "rg": "rg-prod",
            "location": "westeurope",
            "os": "Windows",
            "size": "Standard_D2s_v3",
            "status": "running",
            "subscription": "",
        }
        for name in ("vm-dc-01", "vm-app-01")
    ]


async def test_a_full_column_does_not_shift_the_rest_of_the_row(tmp_path):
    """The table cuts each column at its width and pads with one space, so a
    column that fills it runs into the next. With one long column the text
    reads the next column's value in its place; with all of them full the row
    has no double space left, and the text reader drops the VM altogether."""
    long_rg = "rg-prod-avd-sessionhosts-weu-001"
    long_name = "vm-" + "sessionhost-" * 3 + "01"
    await _collect_vms(
        tmp_path,
        {
            SUB_A: [
                _vm(
                    SUB_A,
                    long_name,
                    rg=long_rg,
                    location="germanywestcentral",
                    size="Standard_NC24ads_A100_v4",
                )
            ]
        },
        multi=False,
    )

    with_json = _parse_azure_overview(_read(tmp_path, sidecars=True))["vms"]
    text_only = _parse_azure_overview(_read(tmp_path, sidecars=False))["vms"]

    assert with_json == [
        {
            "name": long_name,
            "rg": long_rg,
            "location": "germanywestcentral",
            "os": "Windows",
            "size": "Standard_NC24ads_A100_v4",
            "status": "running",
            "subscription": "",
        }
    ]
    assert text_only == [], "the text alone cannot carry this row"


async def test_a_subscription_whose_vms_were_not_listed_is_not_hidden(tmp_path):
    await _collect_vms(
        tmp_path,
        {SUB_A: [_vm(SUB_A, "vm-a")], SUB_B: PermissionError("AuthorizationFailed")},
        multi=True,
    )
    files = _read(tmp_path, sidecars=True)

    assert "30_azure_vms_Prod-B.json" not in files, "a failed listing writes no sidecar"
    assert [(vm["name"], vm["subscription"]) for vm in _parse_azure_overview(files)["vms"]] == [
        ("vm-a", "Prod-A")
    ]


async def test_each_subscription_is_read_from_its_own_files(tmp_path):
    """One subscription with a sidecar and one without: both are read."""
    await _collect_vms(
        tmp_path, {SUB_A: [_vm(SUB_A, "vm-a")], SUB_B: [_vm(SUB_B, "vm-b")]}, multi=True
    )
    files = _drop(_read(tmp_path, sidecars=True), "30_azure_vms_Prod-B")

    vms = _parse_azure_overview(files)["vms"]

    assert [(vm["name"], vm["subscription"], vm["size"]) for vm in vms] == [
        ("vm-a", "Prod-A", "Standard_D2s_v3"),
        ("vm-b", "Prod-B", "Standard_D2s_v3"),
    ]


async def test_a_sidecar_from_v1_2_0_reads_the_table_from_the_text(tmp_path):
    """That sidecar held only name and id, for the backup cross-reference."""
    await _collect_vms(tmp_path, {SUB_A: [_vm(SUB_A, "vm-dc-01")]}, multi=False)
    files = _read(tmp_path, sidecars=True)
    files["30_azure_vms.json"] = json.dumps(
        {"vms": [{"name": "vm-dc-01", "id": _id(SUB_A, "rg-prod", "x", "vm-dc-01")}]}
    )

    assert (
        _parse_azure_overview(files)["vms"]
        == _parse_azure_overview(_read(tmp_path, sidecars=False))["vms"]
    )
