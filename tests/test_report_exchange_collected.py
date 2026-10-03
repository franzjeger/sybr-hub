"""Exchange Online, from the files the Exchange collector actually writes.

The section takes its data from the PowerShell helper as a dict, so these tests
hand ExchangeSection that dict in the shape exo_collector.ps1 emits it and read
the run back as the report does (tests/collector_rig.py). Sensitivity labels
come from Graph, through a real GraphClient over the rig's fake transport.
"""

from __future__ import annotations

from app.modules.m365_audit.sections.exchange import ExchangeSection
from app.reports.parsers import _parse_exchange_overview
from tests.collector_rig import FakeGraph, run_sections

LABELS_PATH = "beta/security/dataSecurityAndGovernance/sensitivityLabels"


async def _collect(
    tmp_path, exo: dict, *, domains=("acme.example",), labels=None, sidecars=True
) -> tuple[dict, ExchangeSection]:
    """Run the whole section on one helper dict and read the run back."""
    async with FakeGraph({LABELS_PATH: labels if labels is not None else []}) as fake:
        section = ExchangeSection(tmp_path, exo, list(domains), graph=fake.client)
        files = await run_sections(section, sidecars=sidecars)
    return files, section


# ── Connectors ────────────────────────────────────────────────────────────────


async def test_a_tenant_without_connectors_has_none(tmp_path):
    """The helper writes {"inbound": null, "outbound": null} for a tenant with none.

    That dict was written as one record, "inbound: N/A / outbound: N/A", and
    counted as one connector on the customer report.
    """
    files, _ = await _collect(tmp_path, {"connectors": {"inbound": None, "outbound": None}})

    assert _parse_exchange_overview(files)["connectors"] == 0


async def test_every_inbound_and_outbound_connector_counts(tmp_path):
    """One inbound (a single object, as ConvertTo-Json writes one) and two outbound."""
    exo = {
        "connectors": {
            "inbound": {"Name": "Fra skanner", "Enabled": True, "Type": "OnPremises"},
            "outbound": [
                {"Name": "Til partner", "Enabled": True, "Type": "Partner"},
                {"Name": "Til arkiv", "Enabled": False, "Type": "Partner"},
            ],
        }
    }
    files, _ = await _collect(tmp_path, exo)

    assert _parse_exchange_overview(files)["connectors"] == 3
    text = files["22_exchange_connectors.txt"]
    assert "Name: Fra skanner" in text and "Direction: Inbound" in text
    assert "Name: Til arkiv" in text and "Direction: Outbound" in text
