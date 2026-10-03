"""Licences, from the file the Licenses collector writes.

The collector writes a fixed-width table for a person and a JSON sidecar for
the report. The report reads the sidecar and falls back to
the text for runs recorded before it existed, so both must give the same
answer wherever the text is precise enough to carry it. Where it is not (the
table prints utilisation as a whole percent) the sidecar is what is right.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.licenses import LicensesSection
from app.reports.parsers import _parse_licenses
from app.web.routes.also import _licence_sidecar
from tests.collector_rig import FakeGraph, read_output, refused, run_sections
from tests.report_from_run import report


def _sku(part: str, used: int, total: int) -> dict:
    return {
        "skuId": f"00000000-0000-0000-0000-{len(part):012d}",
        "skuPartNumber": part,
        "consumedUnits": used,
        "prepaidUnits": {"enabled": total, "suspended": 0, "warning": 0},
    }


SKUS = [
    _sku("SPE_E3", 15, 20),  # 75%, exactly
    _sku("SPB", 180, 200),  # 90%: over the warning line
    # 16 of 23 is 69.6%. The table prints "70%", which is not below the 70%
    # line licence optimisation draws, so the seven idle E1 seats vanish.
    _sku("STANDARDPACK", 16, 23),
    _sku("FLOW_FREE", 3, 0),  # a free SKU with no prepaid units
]


async def _licences(tmp_path) -> dict[str, str]:
    async with FakeGraph({"subscribedSkus": SKUS}, page_size=3) as fake:
        files = await run_sections(LicensesSection(tmp_path, fake.client))
    assert fake.unrouted == []
    return files


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_licence_inventory_survives_the_round_trip(tmp_path, sidecars):
    files = await _licences(tmp_path)
    assert "02_licenses.json" in files

    by_part = {lic["part"]: lic for lic in report(tmp_path, sidecars=sidecars)["licenses"]}

    assert list(by_part) == ["SPE_E3", "SPB", "STANDARDPACK", "FLOW_FREE"], "every page, in order"
    assert by_part["SPE_E3"] == {
        "part": "SPE_E3",
        "name": "Microsoft 365 E3",
        "used": 15,
        "total": 20,
        "pct": 75.0,
        "warn": False,
    }
    assert by_part["SPB"]["warn"] is True and by_part["SPB"]["pct"] == 90.0
    assert by_part["FLOW_FREE"]["total"] == 0 and by_part["FLOW_FREE"]["pct"] == 0.0
    assert by_part["STANDARDPACK"]["used"] == 16 and by_part["STANDARDPACK"]["total"] == 23


async def test_the_sidecar_keeps_the_utilisation_the_table_rounds(tmp_path):
    await _licences(tmp_path)

    def read(ctx: dict) -> tuple[float, list[str]]:
        pct = next(lic["pct"] for lic in ctx["licenses"] if lic["part"] == "STANDARDPACK")
        over = [o["part"] for o in ctx["license_optimization"]["over_provisioned"]]
        return pct, over

    pct, over = read(report(tmp_path))
    assert pct == pytest.approx(69.565, abs=0.001)
    assert over == ["STANDARDPACK"], "seven idle E1 seats at 69.6%"

    pct, over = read(report(tmp_path, sidecars=False))
    assert pct == 70.0, "the table can only say 70%"
    assert over == [], "what a run from before the sidecar says"


async def test_the_also_licence_view_prefers_the_sidecar(tmp_path):
    await _licences(tmp_path)
    text = read_output(tmp_path, sidecars=False)["02_licenses.txt"]
    lic_path = tmp_path / "02_licenses.txt"

    parsed = {lic["part"]: lic for lic in _parse_licenses(text, _licence_sidecar(lic_path))}
    assert parsed["STANDARDPACK"]["pct"] == pytest.approx(69.565, abs=0.001)

    (tmp_path / "02_licenses.json").unlink()
    assert _licence_sidecar(lic_path) is None, "a run from before the sidecar reads the table"


async def test_a_refused_licence_read_writes_nothing_to_misread(tmp_path):
    async with FakeGraph({"subscribedSkus": refused()}) as fake:
        files = await run_sections(LicensesSection(tmp_path, fake.client))

    assert "02_licenses.json" not in files
    assert report(tmp_path)["licenses"] == [], "no inventory, as before: not an empty one"
