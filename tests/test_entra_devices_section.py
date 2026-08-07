"""The devices the directory knows, separated from the service that manages them.

Intune reads deviceManagement — a separate service behind a separate
subscription. This reads /devices, a directory endpoint that answers on every
tenant. On Fonnafly every Intune call returns 401 and this one returns 126
devices, and while the two shared a section the overview said "Failed" and the
most useful finding in it was invisible: 125 endpoints the directory knows and
nobody governs.
"""

from __future__ import annotations

import pytest

from app.modules.base import SectionStatus
from app.modules.m365_audit.sections.entra_devices import EntraDevicesSection
from app.modules.m365_audit.sections.intune import IntuneSection


class _Graph:
    def __init__(self, devices=None, fail=False):
        self._devices, self._fail = devices or [], fail

    async def get_all(self, path, **kw):
        if self._fail:
            raise RuntimeError("Graph refused devices")
        return self._devices


def _device(name, managed):
    return {
        "displayName": name, "operatingSystem": "Windows", "trustType": "AzureAd",
        "isManaged": managed, "accountEnabled": True,
    }


async def test_it_succeeds_when_intune_is_unavailable(tmp_path):
    """The whole reason for the split. This must not inherit Intune's status."""
    section = EntraDevicesSection(
        tmp_path, _Graph([_device("PC1", False), _device("PC2", True)])
    )

    result = await section.collect()

    assert result.status == SectionStatus.DONE


async def test_the_unmanaged_count_reaches_the_file(tmp_path):
    from app.core.encryption import encrypted_read_text

    section = EntraDevicesSection(
        tmp_path, _Graph([_device("PC1", False), _device("PC2", False), _device("PC3", True)])
    )
    await section.collect()

    written = encrypted_read_text(tmp_path / "15_entra_devices_count.txt")
    assert "Total: 3" in written
    assert "2" in written


async def test_a_refusal_fails_the_section_rather_than_reporting_none(tmp_path):
    """"No devices" and "nobody answered" are different claims."""
    section = EntraDevicesSection(tmp_path, _Graph(fail=True))

    result = await section.collect()

    assert result.status == SectionStatus.FAILED


def test_intune_no_longer_collects_the_directory():
    """Two data sources with independent failure modes should not share a
    status, and the way that regresses is one quietly moving back."""
    assert not hasattr(IntuneSection, "_collect_entra_devices")
    source = __import__("pathlib").Path(
        "app/modules/m365_audit/sections/intune.py"
    ).read_text(encoding="utf-8")
    assert "15_entra_devices" not in source


def test_the_collector_runs_both_sections():
    from pathlib import Path

    source = Path("app/modules/m365_audit/collector.py").read_text(encoding="utf-8")

    assert "EntraDevicesSection" in source
    assert '"Entra Devices"' in source, "a section absent from the list is one nothing shows"
