"""Azure VM backup coverage, from the files the collectors actually write.

Coverage is a cross-reference between two independently collected files:
``30_azure_vms*`` for the VM list and ``52_azure_backup*`` for the items the
Recovery Services vaults protect.

These tests used to feed the parser a format the collector never wrote
("Vault: x" and a "Name  Type  Status" table). They passed while real output
failed: the collector writes each protected item as "      - <name>  Status:...",
and the parser skipped every line starting with "-". It read no items, so every
VM landed in a high-priority "these servers have no backup" finding, backed up
or not. The listing also stopped at 15 items per vault and cut names at 40
characters.

So the files here come from the collectors themselves, run against fake Azure
clients (tests/collector_rig.py), and the parser reads exactly what a real run
leaves on disk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.m365_audit.sections.azure_compute import AzureComputeSection
from app.modules.m365_audit.sections.azure_governance import AzureGovernanceSection
from app.reports.parsers import _parse_backup_coverage
from app.reports.recommendations import _build_recommendations
from tests.collector_rig import FakeAzureAuth, read_output

SUB = "00000000-0000-0000-0000-0000000000aa"


def _vm_id(name: str, rg: str = "rg-prod") -> str:
    return f"/subscriptions/{SUB}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{name}"


def _vm(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        id=_vm_id(name),
        location="westeurope",
        storage_profile=None,
        hardware_profile=None,
        instance_view=None,
    )


def _item(vm_name: str, state: str = "Protected") -> SimpleNamespace:
    return SimpleNamespace(
        name=f"VM;iaasvmcontainerv2;rg-prod;{vm_name}",
        properties=SimpleNamespace(
            friendly_name=vm_name,
            workload_type="VM",
            protection_state=state,
            protection_status="Healthy",
            health_status="Passed",
            last_backup_time=datetime(2026, 10, 2, 22, 0, tzinfo=UTC),
            source_resource_id=_vm_id(vm_name),
        ),
    )


def _vault(name: str = "rsv-prod") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        id=f"/subscriptions/{SUB}/resourceGroups/rg-backup/providers/Microsoft.RecoveryServices/vaults/{name}",
        location="westeurope",
        sku=SimpleNamespace(name="Standard"),
    )


async def _collect(tmp_path, monkeypatch, vms, vaults, items, *, sidecars=True) -> dict:
    """Run both collectors and return what they wrote, as the report reads it.

    ``items`` maps a vault name to the items it protects, or to the exception
    listing them raises.
    """

    def protected_items(vault_name, resource_group):
        found = items.get(vault_name, [])
        if isinstance(found, Exception):
            raise found
        return found

    auth = FakeAzureAuth(
        compute={"virtual_machines.list_all": vms},
        recovery={"vaults.list_by_subscription_id": vaults},
        backup={"backup_protected_items.list": protected_items},
    ).install(monkeypatch)
    await AzureComputeSection(tmp_path, auth, sub_id=SUB)._collect_vms()
    await AzureGovernanceSection(tmp_path, auth, sub_id=SUB)._collect_backup()
    return read_output(tmp_path, sidecars=sidecars)


# ── Coverage from real collector output ───────────────────────────────────────


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_backed_up_vms_are_not_reported_as_unprotected(tmp_path, monkeypatch, sidecars):
    vms = [_vm("vm-dc-01"), _vm("vm-app-01")]
    files = await _collect(
        tmp_path,
        monkeypatch,
        vms,
        [_vault()],
        {"rsv-prod": [_item("vm-dc-01"), _item("vm-app-01")]},
        sidecars=sidecars,
    )

    result = _parse_backup_coverage(files)

    assert result["coverage_known"] is True
    assert result["vms_not_backed_up"] == []
    assert result["vms_backed_up"] == 2
    assert result["backup_pct"] == 100.0
    assert result["vaults"] == 1


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_vm_without_a_protected_item_is_named(tmp_path, monkeypatch, sidecars):
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm("vm-dc-01"), _vm("vm-app-01")],
        [_vault()],
        {"rsv-prod": [_item("vm-dc-01")]},
        sidecars=sidecars,
    )

    result = _parse_backup_coverage(files)

    assert result["coverage_known"] is True
    assert result["vms_not_backed_up"] == ["vm-app-01"]
    assert result["backup_pct"] == 50.0


async def test_more_than_fifteen_items_in_a_vault_all_count(tmp_path, monkeypatch):
    """The listing used to stop at 15 items; VM 16 onwards read as unprotected."""
    names = [f"vm-{n:02d}" for n in range(20)]
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm(n) for n in names],
        [_vault()],
        {"rsv-prod": [_item(n) for n in names]},
    )

    result = _parse_backup_coverage(files)

    assert result["vms_backed_up"] == 20 and result["vms_not_backed_up"] == []


async def test_a_name_longer_than_the_listing_columns_still_matches(tmp_path, monkeypatch):
    long_name = "vm-" + "x" * 50
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm(long_name)],
        [_vault()],
        {"rsv-prod": [_item(long_name)]},
    )

    assert _parse_backup_coverage(files)["vms_not_backed_up"] == []


async def test_stopped_protection_does_not_count_as_backup(tmp_path, monkeypatch):
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm("vm-dc-01"), _vm("vm-app-01")],
        [_vault()],
        {"rsv-prod": [_item("vm-dc-01"), _item("vm-app-01", state="ProtectionStopped")]},
    )

    result = _parse_backup_coverage(files)

    assert result["vms_not_backed_up"] == ["vm-app-01"]
    assert result["vms_backup_stopped"] == ["vm-app-01"]


async def test_a_vault_whose_items_could_not_be_read_leaves_coverage_unknown(tmp_path, monkeypatch):
    """A VM missing from an unread list may well be protected: do not name it."""
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm("vm-dc-01"), _vm("vm-app-01")],
        [_vault("rsv-a"), _vault("rsv-b")],
        {"rsv-a": [_item("vm-dc-01")], "rsv-b": PermissionError("AuthorizationFailed")},
    )

    result = _parse_backup_coverage(files)

    assert result["coverage_known"] is False
    assert result["vms_not_backed_up"] == []


async def test_no_vaults_at_all_is_a_real_finding(tmp_path, monkeypatch):
    files = await _collect(tmp_path, monkeypatch, [_vm("vm-dc-01")], [], {})

    result = _parse_backup_coverage(files)

    assert result["coverage_known"] is True
    assert result["vms_not_backed_up"] == ["vm-dc-01"]


# ── Backup data that was never read ───────────────────────────────────────────


@pytest.mark.parametrize(
    "backup_files",
    [
        {},  # section never ran
        {"52_azure_backup.txt": ""},  # ran, wrote nothing
        {"52_azure_backup.txt": "   \n"},
        {"52_azure_backup.txt": "Error: insufficient privileges"},
    ],
    ids=["absent", "empty", "whitespace", "error"],
)
async def test_unread_backup_data_does_not_mark_every_vm_unprotected(
    tmp_path, monkeypatch, backup_files
):
    files = await _collect(tmp_path, monkeypatch, [_vm("vm-dc-01"), _vm("vm-app-01")], [], {})
    files = {n: t for n, t in files.items() if not n.startswith("52_azure_backup")}

    result = _parse_backup_coverage({**files, **backup_files})

    assert result["vms_not_backed_up"] == []
    assert result["vms_backed_up"] == 0
    assert result["vms_total"] == 2, "the VM list itself was readable"
    assert result["coverage_known"] is False
    assert result["backup_pct"] == 0.0


def test_no_vms_means_nothing_to_cross_reference():
    result = _parse_backup_coverage({"52_azure_backup.json": '{"vaults": []}'})
    assert result["coverage_known"] is False
    assert result["vms_not_backed_up"] == []


# ── The recommendation ────────────────────────────────────────────────────────


def _backup_rec(backup_coverage: dict):
    recs = _build_recommendations(
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 90.0, "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        backup_coverage=backup_coverage,
    )
    return next((r for r in recs if "backup" in r.get("title", "").lower()), None)


async def test_fully_backed_up_vms_raise_no_recommendation(tmp_path, monkeypatch):
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm("vm-dc-01"), _vm("vm-app-01")],
        [_vault()],
        {"rsv-prod": [_item("vm-dc-01"), _item("vm-app-01")]},
        sidecars=False,
    )
    assert _backup_rec(_parse_backup_coverage(files)) is None


async def test_a_real_gap_still_raises_the_recommendation(tmp_path, monkeypatch):
    files = await _collect(
        tmp_path,
        monkeypatch,
        [_vm("vm-dc-01"), _vm("vm-app-01")],
        [_vault()],
        {"rsv-prod": [_item("vm-dc-01")]},
    )
    rec = _backup_rec(_parse_backup_coverage(files))
    assert rec is not None
    assert rec["priority"] == "high"
    assert rec["sub_items"] == ["vm-app-01"]


def test_a_stale_coverage_dict_without_the_flag_is_treated_as_unknown():
    """Defensive: a dict from an older code path must not resurrect the claim."""
    assert _backup_rec({"vms_total": 2, "vms_not_backed_up": ["vm-dc-01"]}) is None


# ── More than one subscription ────────────────────────────────────────────────

SUB_A = "00000000-0000-0000-0000-0000000000a1"
SUB_B = "00000000-0000-0000-0000-0000000000b2"


def _vm_in(sub: str, name: str) -> SimpleNamespace:
    vm = _vm(name)
    vm.id = vm.id.replace(SUB, sub)
    return vm


def _item_in(sub: str, name: str) -> SimpleNamespace:
    item = _item(name)
    item.properties.source_resource_id = item.properties.source_resource_id.replace(SUB, sub)
    return item


async def _collect_two(tmp_path, monkeypatch, a: dict, b: dict, *, sidecars=True) -> dict:
    """Two subscriptions, each {"vms", "vaults", "items"}; a vaults value may raise."""

    def kinds(spec: dict) -> dict:
        def protected_items(vault_name, resource_group):
            found = spec["items"].get(vault_name, [])
            if isinstance(found, Exception):
                raise found
            return found

        return {
            "compute": {"virtual_machines.list_all": spec["vms"]},
            "recovery": {"vaults.list_by_subscription_id": spec["vaults"]},
            "backup": {"backup_protected_items.list": protected_items},
        }

    auth = FakeAzureAuth(subscriptions={SUB_A: kinds(a), SUB_B: kinds(b)}).install(monkeypatch)
    for sub, name in ((SUB_A, "Prod-A"), (SUB_B, "Prod-B")):
        await AzureComputeSection(
            tmp_path, auth, sub_id=sub, sub_name=name, multi=True
        )._collect_vms()
        await AzureGovernanceSection(
            tmp_path, auth, sub_id=sub, sub_name=name, multi=True
        )._collect_backup()
    return read_output(tmp_path, sidecars=sidecars)


async def test_a_subscription_whose_vaults_were_not_read_is_not_hidden_by_another(
    tmp_path, monkeypatch
):
    """Sub B's vault listing is refused, so it writes only a text error and no
    sidecar. Sub A's sidecar used to make the parser ignore B, and B's VMs were
    named as having no backup from vaults nobody had read."""
    files = await _collect_two(
        tmp_path,
        monkeypatch,
        {
            "vms": [_vm_in(SUB_A, "vm-a")],
            "vaults": [_vault("rsv-a")],
            "items": {"rsv-a": [_item_in(SUB_A, "vm-a")]},
        },
        {
            "vms": [_vm_in(SUB_B, "vm-b")],
            "vaults": PermissionError("AuthorizationFailed"),
            "items": {},
        },
    )

    result = _parse_backup_coverage(files)

    assert result["vms_total"] == 2
    assert result["coverage_known"] is False
    assert result["vms_not_backed_up"] == []


async def test_a_protected_vm_does_not_cover_a_namesake_in_another_subscription(
    tmp_path, monkeypatch
):
    files = await _collect_two(
        tmp_path,
        monkeypatch,
        {
            "vms": [_vm_in(SUB_A, "vm-dc-01")],
            "vaults": [_vault("rsv-a")],
            "items": {"rsv-a": [_item_in(SUB_A, "vm-dc-01")]},
        },
        {"vms": [_vm_in(SUB_B, "vm-dc-01")], "vaults": [_vault("rsv-b")], "items": {"rsv-b": []}},
    )

    result = _parse_backup_coverage(files)

    assert result["coverage_known"] is True
    assert result["vms_backed_up"] == 1
    assert result["vms_not_backed_up"] == ["vm-dc-01"]
