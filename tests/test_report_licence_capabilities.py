"""What a tenant is licensed for is read from what its SKUs contain.

A licence-gated CIS control answers "not licensed" (info, no finding) when the
tenant holds no seat that carries the feature. That was decided from a table of
a dozen part numbers, and a SKU the table did not know counted as carrying
nothing. Microsoft has sold the suites under new part numbers in the EEA since
2023 ("Microsoft_365_E5_(no_Teams)"), so a Norwegian tenant on Microsoft 365 E5
with PIM never set up was told PIM was not licensed, instead of being told to
configure it. The same table gave Office 365 E5 Entra ID P2 and Intune, which
it does not include.

The collector now records each SKU's service plans and the gate reads those. A
run without them falls back to the table, and an assigned suite the table does
not know makes the answer unknown rather than "absent".
"""

from __future__ import annotations

import json

import pytest

from app.modules.m365_audit.sections.licenses import LicensesSection
from app.reports.compliance import _build_compliance_map
from app.reports.evidence import _lacks, _licensed_capabilities
from tests.collector_rig import FakeGraph, run_sections
from tests.report_from_run import report


def _sku(part: str, used: int, plans: dict[str, str]) -> dict:
    return {
        "skuId": f"00000000-0000-0000-0000-{len(part):012d}",
        "skuPartNumber": part,
        "consumedUnits": used,
        "prepaidUnits": {"enabled": max(used, 1), "suspended": 0, "warning": 0},
        "servicePlans": [
            {"servicePlanName": name, "provisioningStatus": status}
            for name, status in plans.items()
        ],
    }


E5_NO_TEAMS = _sku(
    "Microsoft_365_E5_EEA_(no_Teams)_2026",  # a part number no table will have
    25,
    {
        "AAD_PREMIUM": "Success",
        "AAD_PREMIUM_P2": "Success",
        "INTUNE_A": "Success",
        "THREAT_INTELLIGENCE": "Success",
        "EXCHANGE_S_ENTERPRISE": "Success",
    },
)
FREE_FLOW = _sku("FLOW_FREE", 3, {"FLOW_P2_VIRAL": "Success"})


async def _licences(tmp_path, skus: list[dict], *, sidecars: bool) -> list[dict]:
    async with FakeGraph({"subscribedSkus": skus}) as fake:
        await run_sections(LicensesSection(tmp_path, fake.client))
    return report(tmp_path, sidecars=sidecars)["licenses"]


def _pim_status(licenses: list[dict]) -> str:
    """CIS 1.1.5 for a tenant whose PIM read succeeded and found no assignments."""
    context = {
        "licenses": licenses,
        "file_contents": {
            "07b_pim_eligible_assignments.txt": "  PIM ELIGIBLE ASSIGNMENTS  (0 total)\n",
            "07b_pim_eligible_assignments.json": json.dumps({"count": 0, "assignments": []}),
        },
    }
    return next(r["status"] for r in _build_compliance_map(context) if r["cis_id"] == "1.1.5")


async def test_a_new_part_number_is_read_by_the_plans_it_contains(tmp_path):
    licenses = await _licences(tmp_path, [E5_NO_TEAMS, FREE_FLOW], sidecars=True)

    capabilities = _licensed_capabilities(licenses)

    assert capabilities == {"entra_p1", "entra_p2", "intune", "defender_office"}
    # Licensed and not configured is a finding, not "not licensed".
    assert _pim_status(licenses) == "warn"


async def test_a_plan_switched_off_in_the_sku_is_not_a_capability(tmp_path):
    sku = _sku("SOME_BUNDLE", 5, {"AAD_PREMIUM": "Success", "AAD_PREMIUM_P2": "Disabled"})
    licenses = await _licences(tmp_path, [sku], sidecars=True)

    assert _licensed_capabilities(licenses) == {"entra_p1"}
    assert _pim_status(licenses) == "info"


async def test_an_unknown_suite_without_plans_is_unknown_not_absent(tmp_path):
    """A run from before the plans were recorded has only the part number."""
    licenses = await _licences(tmp_path, [E5_NO_TEAMS, FREE_FLOW], sidecars=False)
    assert all("plans" not in lic for lic in licenses)

    capabilities = _licensed_capabilities(licenses)

    assert capabilities is None
    assert _lacks(capabilities, "entra_p2") is False
    assert _pim_status(licenses) == "warn"


@pytest.mark.parametrize(
    ("part", "expected"),
    [
        ("Microsoft_365_E3_(no_Teams)", {"entra_p1", "intune"}),
        ("Microsoft_365_Business_Premium_(no_Teams)", {"entra_p1", "intune", "defender_office"}),
        # Office 365 E5 has no Entra ID Premium and no Intune.
        ("ENTERPRISEPREMIUM", {"defender_office", "purview"}),
        # Known, and carries nothing: still "absent", not "unknown".
        ("O365_BUSINESS_PREMIUM", set()),
        ("FLOW_FREE", set()),
        ("POWER_BI_STANDARD", set()),
    ],
)
def test_the_part_number_table_for_runs_without_plans(part, expected):
    assert _licensed_capabilities([{"part": part, "used": 4, "total": 5}]) == expected
