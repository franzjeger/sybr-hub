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
from app.modules.m365_audit.sections.azure_governance import AzureGovernanceSection
from app.modules.m365_audit.sections.azure_network import AzureNetworkSection
from app.modules.m365_audit.sections.azure_storage import AzureStorageSection
from app.reports.parsers import _parse_azure_overview
from app.reports.recommendations import _build_recommendations
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


# ── Storage accounts (35_azure_storage) ───────────────────────────────────────


def _account(name, *, kind="StorageV2", sku="Standard_LRS", tls="TLS1_2", https=True, public=False):
    return SimpleNamespace(
        name=name,
        sku=SimpleNamespace(name=sku),
        kind=kind,
        minimum_tls_version=tls,
        enable_https_traffic_only=https,
        allow_blob_public_access=public,
    )


async def _collect_storage(tmp_path, per_sub: dict, *, multi: bool) -> None:
    auth = FakeAzureAuth(
        subscriptions={
            sub: {"storage": {"storage_accounts.list": accounts}}
            for sub, accounts in per_sub.items()
        }
    )
    for sub, name in SUBS:
        if sub in per_sub:
            await AzureStorageSection(
                tmp_path, auth, sub_id=sub, sub_name=name, multi=multi
            )._collect_storage_accounts()


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_storage_accounts_survive_the_round_trip(tmp_path, sidecars):
    await _collect_storage(
        tmp_path,
        {
            SUB_A: [
                _account("stacmeprod01"),
                _account(
                    "stacmelogs",
                    sku="Standard_GRS",
                    kind="BlobStorage",
                    tls="TLS1_0",
                    https=False,
                    public=True,
                ),
            ]
        },
        multi=False,
    )

    accounts = _parse_azure_overview(_read(tmp_path, sidecars=sidecars))["storage_accounts"]

    assert accounts == [
        {"name": "stacmeprod01", "sku": "Standard_LRS", "kind": "StorageV2", "subscription": ""},
        {"name": "stacmelogs", "sku": "Standard_GRS", "kind": "BlobStorage", "subscription": ""},
    ]


async def test_a_kind_wider_than_its_column_is_kept_whole(tmp_path):
    """The text cuts the kind at 15 characters and "BlockBlobStorage" has 16."""
    await _collect_storage(
        tmp_path,
        {SUB_A: [_account("stacmepremium", sku="Premium_LRS", kind="BlockBlobStorage")]},
        multi=False,
    )

    with_json = _parse_azure_overview(_read(tmp_path, sidecars=True))["storage_accounts"]
    text_only = _parse_azure_overview(_read(tmp_path, sidecars=False))["storage_accounts"]

    assert with_json[0]["kind"] == "BlockBlobStorage"
    assert text_only[0]["kind"] == "BlockBlobStorag TLS1_2", "the text alone cannot carry it"


async def test_a_subscription_whose_storage_was_not_listed_is_not_hidden(tmp_path):
    await _collect_storage(
        tmp_path,
        {SUB_A: [_account("stacmea")], SUB_B: PermissionError("AuthorizationFailed")},
        multi=True,
    )
    files = _read(tmp_path, sidecars=True)

    assert "35_azure_storage_Prod-B.json" not in files
    accounts = _parse_azure_overview(files)["storage_accounts"]
    assert [(a["name"], a["subscription"]) for a in accounts] == [("stacmea", "Prod-A")]


async def test_each_subscription_reads_its_own_storage_files(tmp_path):
    await _collect_storage(
        tmp_path,
        {SUB_A: [_account("stacmea")], SUB_B: [_account("stacmeb", kind="BlockBlobStorage")]},
        multi=True,
    )
    files = _drop(_read(tmp_path, sidecars=True), "35_azure_storage_Prod-A")

    accounts = _parse_azure_overview(files)["storage_accounts"]

    assert [(a["name"], a["kind"], a["subscription"]) for a in accounts] == [
        ("stacmea", "StorageV2", "Prod-A"),
        ("stacmeb", "BlockBlobStorage", "Prod-B"),
    ]


# ── Network security groups (32_azure_nsgs, 32b_..._WARN) ─────────────────────


def _rule(name, priority, *, source, port, access="Allow", direction="Inbound"):
    return SimpleNamespace(
        name=name,
        priority=priority,
        access=access,
        direction=direction,
        source_address_prefix=source,
        destination_address_prefix="*",
        destination_port_range=port,
        destination_port_ranges=[],
    )


def _nsg(sub: str, name: str, rules: list) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        id=_id(sub, "rg-net", "Microsoft.Network/networkSecurityGroups", name),
        location="norwayeast",
        security_rules=rules,
    )


def _nsgs(sub: str) -> list:
    return [
        _nsg(
            sub,
            f"nsg-web-{sub[-2:]}",
            [
                _rule("allow-rdp", 100, source="Internet", port="3389"),
                _rule("allow-https", 110, source="*", port="443"),
                _rule("deny-all", 4000, source="*", port="*", access="Deny"),
            ],
        ),
        _nsg(
            sub,
            f"nsg-db-{sub[-2:]}",
            [
                _rule("allow-sql", 100, source="0.0.0.0/0", port="1433"),
                _rule("allow-ssh-internal", 110, source="10.0.0.0/8", port="22"),
            ],
        ),
    ]


async def _collect_nsgs(tmp_path, per_sub: dict, *, multi: bool) -> None:
    auth = FakeAzureAuth(
        subscriptions={
            sub: {"network": {"network_security_groups.list_all": nsgs}}
            for sub, nsgs in per_sub.items()
        }
    )
    for sub, name in SUBS:
        if sub in per_sub:
            await AzureNetworkSection(
                tmp_path, auth, sub_id=sub, sub_name=name, multi=multi
            )._collect_nsgs()


def _nsg_rec(files: dict) -> dict | None:
    recs = _build_recommendations(
        mfa={"has_data": True, "pct": 100.0, "no_mfa": 0},
        spf_dmarc=[],
        secure_score={"has_data": True, "pct": 90.0, "improvements": []},
        ext_fwd="",
        risky_users="",
        licenses=[],
        file_contents=files,
    )
    return next((r for r in recs if r.get("finding_id") == "finding-nsg"), None)


def _risky(sub: str) -> list[str]:
    return [
        f"NSG 'nsg-web-{sub[-2:]}' rule 'allow-rdp' (priority 100): "
        "allows inbound from Internet to port(s) 3389",
        f"NSG 'nsg-db-{sub[-2:]}' rule 'allow-sql' (priority 100): "
        "allows inbound from 0.0.0.0/0 to port(s) 1433",
    ]


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_nsgs_and_their_risky_rules_survive_the_round_trip(tmp_path, sidecars):
    await _collect_nsgs(tmp_path, {SUB_A: _nsgs(SUB_A)}, multi=False)
    files = _read(tmp_path, sidecars=sidecars)

    assert _parse_azure_overview(files)["nsgs"] == [{"subscription": "", "count": 2}]
    rec = _nsg_rec(files)
    assert rec["sub_items"] == _risky(SUB_A), "each rule once, not once per file"
    assert rec["evidence"] == ["32b_azure_nsg_risky_rules_WARN.txt"]


async def test_the_nsgs_are_read_from_the_sidecar(tmp_path):
    """With the text emptied, everything still comes from the sidecar."""
    await _collect_nsgs(tmp_path, {SUB_A: _nsgs(SUB_A)}, multi=False)
    files = _read(tmp_path, sidecars=True)
    files["32_azure_nsgs.txt"] = ""
    files["32b_azure_nsg_risky_rules_WARN.txt"] = ""

    assert _parse_azure_overview(files)["nsgs"] == [{"subscription": "", "count": 2}]
    assert _nsg_rec(files)["sub_items"] == _risky(SUB_A)


async def test_nsgs_with_nothing_open_raise_nothing(tmp_path):
    safe = [_nsg(SUB_A, "nsg-safe", [_rule("allow-https", 100, source="*", port="443")])]
    await _collect_nsgs(tmp_path, {SUB_A: safe}, multi=False)

    assert _nsg_rec(_read(tmp_path, sidecars=True)) is None


async def test_a_subscription_whose_nsgs_were_not_listed_is_not_hidden(tmp_path):
    await _collect_nsgs(
        tmp_path, {SUB_A: _nsgs(SUB_A), SUB_B: PermissionError("AuthorizationFailed")}, multi=True
    )
    files = _read(tmp_path, sidecars=True)

    assert "32_azure_nsgs_Prod-B.json" not in files
    assert _parse_azure_overview(files)["nsgs"] == [{"subscription": "Prod-A", "count": 2}]
    assert _nsg_rec(files)["sub_items"] == _risky(SUB_A)


async def test_each_subscription_reads_its_own_nsg_files(tmp_path):
    """Sub B without its sidecar is read from its WARN file, once."""
    await _collect_nsgs(tmp_path, {SUB_A: _nsgs(SUB_A), SUB_B: _nsgs(SUB_B)}, multi=True)
    files = _drop(_read(tmp_path, sidecars=True), "32_azure_nsgs_Prod-B")

    assert _parse_azure_overview(files)["nsgs"] == [
        {"subscription": "Prod-A", "count": 2},
        {"subscription": "Prod-B", "count": 2},
    ]
    assert sorted(_nsg_rec(files)["sub_items"]) == sorted(_risky(SUB_A) + _risky(SUB_B))


# ── Azure Advisor (51_azure_advisor) ──────────────────────────────────────────


def _advice(category, impact, problem, resource):
    return SimpleNamespace(
        category=category,
        impact=impact,
        short_description=SimpleNamespace(problem=problem, solution=problem),
        impacted_value=resource,
    )


ADVICE = [
    _advice("Security", "High", "Enable MFA for accounts with owner permissions", "sub-a"),
    _advice("Security", "Medium", "Restrict access through internet-facing endpoint", "vm-01"),
    _advice("Cost", "Low", "Right-size or shutdown underutilized virtual machines", "vm-02"),
    _advice("Cost", "Low", "Right-size or shutdown underutilized virtual machines", "vm-03"),
    _advice("Cost", "Medium", "Buy reserved instances to save money", "sub-a"),
]


async def _collect_advisor(tmp_path, per_sub: dict, *, multi: bool) -> None:
    auth = FakeAzureAuth(
        subscriptions={
            sub: {"advisor": {"recommendations.list": recs}} for sub, recs in per_sub.items()
        }
    )
    for sub, name in SUBS:
        if sub in per_sub:
            await AzureGovernanceSection(
                tmp_path, auth, sub_id=sub, sub_name=name, multi=multi
            )._collect_advisor()


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_advisor_recommendations_survive_the_round_trip(tmp_path, sidecars):
    await _collect_advisor(tmp_path, {SUB_A: ADVICE}, multi=False)
    files = _read(tmp_path, sidecars=sidecars)

    azure = _parse_azure_overview(files)

    assert azure["advisor_recs"] == 5
    assert [
        (a["category"], a["impact"], a["description"], a["resource"])
        for a in azure["advisor_details"]
    ] == [
        ("Cost", "Low", "Right-size or shutdown underutilized virtual machines", "vm-02"),
        ("Cost", "Low", "Right-size or shutdown underutilized virtual machines", "vm-03"),
        ("Cost", "Medium", "Buy reserved instances to save money", "sub-a"),
        ("Security", "High", "Enable MFA for accounts with owner permissions", "sub-a"),
        ("Security", "Medium", "Restrict access through internet-facing endpoint", "vm-01"),
    ]
    assert [(s["description"], s["count"]) for s in azure["advisor_summary"]] == [
        ("Enable MFA for accounts with owner permissions", 1),
        ("Buy reserved instances to save money", 1),
        ("Restrict access through internet-facing endpoint", 1),
        ("Right-size or shutdown underutilized virtual machines", 2),
    ]


async def test_two_recommendations_sharing_their_first_80_characters_stay_apart(tmp_path):
    """The text cuts a description at 80 characters, and the report groups
    Advisor items by description: two different actions became one, counted
    twice, and the second never reached the recommendation."""
    stem = "Enable soft delete for blob storage accounts that hold production data in region "
    assert len(stem) > 80
    long_resource = "/subscriptions/x/resourceGroups/rg-prod/providers/Microsoft.Storage/x"
    await _collect_advisor(
        tmp_path,
        {
            SUB_A: [
                _advice("HighAvailability", "High", stem + "norwayeast", long_resource),
                _advice("HighAvailability", "High", stem + "westeurope", long_resource),
            ]
        },
        multi=False,
    )

    with_json = _parse_azure_overview(_read(tmp_path, sidecars=True))
    text_only = _parse_azure_overview(_read(tmp_path, sidecars=False))

    assert [s["description"] for s in with_json["advisor_summary"]] == [
        stem + "norwayeast",
        stem + "westeurope",
    ]
    assert with_json["advisor_details"][0]["resource"] == long_resource
    assert len(text_only["advisor_summary"]) == 1, "the text alone cannot keep them apart"


async def test_a_subscription_whose_advisor_was_not_read_is_not_hidden(tmp_path):
    await _collect_advisor(
        tmp_path, {SUB_A: ADVICE[:2], SUB_B: PermissionError("AuthorizationFailed")}, multi=True
    )
    files = _read(tmp_path, sidecars=True)

    assert "51_azure_advisor_Prod-B.json" not in files
    azure = _parse_azure_overview(files)
    assert azure["advisor_recs"] == 2
    assert {a["subscription"] for a in azure["advisor_details"]} == {"Prod-A"}


async def test_each_subscription_reads_its_own_advisor_files(tmp_path):
    await _collect_advisor(tmp_path, {SUB_A: ADVICE[:2], SUB_B: ADVICE[2:]}, multi=True)
    files = _drop(_read(tmp_path, sidecars=True), "51_azure_advisor_Prod-B")

    azure = _parse_azure_overview(files)

    assert azure["advisor_recs"] == 5
    assert [a["subscription"] for a in azure["advisor_details"]] == ["Prod-A"] * 2 + ["Prod-B"] * 3
