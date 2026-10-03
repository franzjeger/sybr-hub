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
from app.reports.generator import build_report_context
from tests.collector_rig import FakeGraph

# Longer than the 35-character device-name column in both tables.
LONG_NAME = "Kunde A sin iPad Pro 12,9 tommer (6. generasjon)"
assert len(LONG_NAME) > 35


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


REGISTERED = [
    _registered("LAPTOP-01", managed=True),
    _registered(LONG_NAME, managed=False),
    _registered("OLD-PC", managed=False, enabled=False, trust="ServerAd"),
    _registered("BYOD-PHONE", managed=None, trust=None),
]


def _routes() -> dict:
    return {"devices": REGISTERED}


async def _context(tmp_path, *, sidecars: bool) -> dict:
    """Run the section, then build the report context from what it left.

    The run sits two levels down so the trend loader finds no sibling runs.
    sidecars=False deletes the .json files first: a run from before them.
    """
    run = tmp_path / "Acme_AS" / "2026-10-03_0900"
    run.mkdir(parents=True)
    async with FakeGraph(_routes(), page_size=2) as fake:
        results = [await EntraDevicesSection(run, fake.client).collect()]
        assert fake.unrouted == [], "every call the sections made was answered"
    written = {p.name for p in run.glob("*.json")}
    assert "15_entra_devices.json" in written
    if not sidecars:
        for path in run.glob("*.json"):
            path.unlink()
    return build_report_context(
        "Acme AS", "acme.example", run, results, lang="en", persist_metrics=False
    )


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
