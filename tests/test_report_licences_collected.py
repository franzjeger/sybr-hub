"""Licences and their use, from the files the Licenses and Usage collectors write.

Both collectors write a fixed-width or "Key: value" text for a person and a
JSON sidecar for the report. The report reads the sidecar and falls back to
the text for runs recorded before it existed, so both must give the same
answer wherever the text is precise enough to carry it. Where it is not (the
table prints utilisation as a whole percent) the sidecar is what is right.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.licenses import LicensesSection
from app.modules.m365_audit.sections.usage_reports import UsageReportsSection
from app.reports.parsers import _parse_licenses
from app.web.routes.also import _licence_sidecar
from tests.collector_rig import CsvReport, FakeGraph, read_output, refused, run_sections
from tests.report_from_run import relabel, report


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


# ── Usage ────────────────────────────────────────────────────────────────────

_USAGE = "reports/getOffice365ActiveUserDetail(period='D90')"


def _usage_row(upn: str, *, last: str = "", products: str = "", deleted: bool = False) -> dict:
    return {
        "User Principal Name": upn,
        "Is Deleted": "True" if deleted else "False",
        "Exchange Last Activity Date": last,
        "OneDrive Last Activity Date": "",
        "SharePoint Last Activity Date": "",
        "Teams Last Activity Date": "",
        "Assigned Products": products,
    }


USAGE_ROWS = [
    _usage_row("kari@acme.example", last="2026-09-30", products="MICROSOFT 365 E3"),
    _usage_row("ola@acme.example", products="MICROSOFT 365 E3+MICROSOFT TEAMS"),  # licensed, idle
    _usage_row("per@acme.example"),  # unlicensed, idle
    _usage_row("sluttet@acme.example", last="2026-07-01", deleted=True),
]


async def _usage(tmp_path, routes: dict) -> dict[str, str]:
    async with FakeGraph(routes) as fake:
        return await run_sections(UsageReportsSection(tmp_path, fake.client))


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_the_usage_summary_survives_the_round_trip(tmp_path, sidecars):
    files = await _usage(tmp_path, {_USAGE: CsvReport(USAGE_ROWS)})
    assert "16_usage_summary.json" in files

    usage = report(tmp_path, sidecars=sidecars)["usage"]

    assert usage["has_data"] is True
    assert usage["total"] == 4
    assert usage["active"] == 1
    assert usage["no_activity"] == 2
    assert usage["licensed_idle"] == 1, "Ola: licensed, nothing in 90 days"
    assert usage["period_days"] == 90
    assert usage["concealed"] is False
    assert usage["unavailable"] is False


async def test_the_usage_figures_do_not_hang_on_the_summary_labels(tmp_path):
    """The point of the sidecar: the text can change its layout freely."""
    await _usage(tmp_path, {_USAGE: CsvReport(USAGE_ROWS)})
    relabel(tmp_path / "16_usage_summary.txt")

    usage = report(tmp_path)["usage"]
    assert (usage["total"], usage["licensed_idle"]) == (4, 1)

    assert report(tmp_path, sidecars=False)["usage"]["has_data"] is False, (
        "the relabelled text alone no longer parses"
    )


async def test_concealed_names_reach_the_report_either_way(tmp_path):
    rows = [_usage_row("8F1C2A9D0B7E", last="2026-09-30"), _usage_row("0A1B2C3D4E5F")]
    await _usage(tmp_path, {_USAGE: CsvReport(rows)})

    from_json = report(tmp_path)["usage"]
    assert from_json["concealed"] is True
    assert from_json == report(tmp_path, sidecars=False)["usage"]


async def test_a_refused_usage_report_writes_no_sidecar(tmp_path):
    files = await _usage(tmp_path, {_USAGE: refused()})

    assert "16_usage_summary.json" not in files
    usage = report(tmp_path)["usage"]
    assert usage["has_data"] is False
    assert usage["unavailable"] is True, "the refusal is explained, as before"
    assert "Reports.Read.All" in usage["unavailable_reason"]
