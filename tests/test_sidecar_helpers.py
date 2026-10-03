"""The sidecar pair: what a collector writes, the report reads back."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.base import BaseSection, SectionResult
from app.reports.parsers.common import _sidecar
from tests.collector_rig import read_output


class _Section(BaseSection):
    name = "Probe"

    async def collect(self) -> SectionResult:
        return self.result


def test_a_sidecar_round_trips_with_non_json_values(tmp_path):
    when = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    _Section(tmp_path)._save_sidecar("90_probe.txt", {"rows": [{"at": when, "n": 3}]})

    data = _sidecar(read_output(tmp_path), "90_probe.txt")

    assert data == {"rows": [{"at": str(when), "n": 3}]}


@pytest.mark.parametrize("raw", [None, "", "   ", "not json", "[1, 2]"])
def test_a_missing_or_unusable_sidecar_means_read_the_text(raw):
    files = {"90_probe.txt": "text"} | ({} if raw is None else {"90_probe.json": raw})
    assert _sidecar(files, "90_probe.txt") is None


def test_the_sidecar_name_follows_the_text_file():
    with pytest.raises(ValueError):
        _sidecar({}, "90_probe.json")
    with pytest.raises(ValueError):
        _Section(None)._save_sidecar("90_probe.csv", {})
