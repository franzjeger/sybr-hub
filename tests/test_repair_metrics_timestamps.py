"""The run directory is the authority on when a run happened."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "repair", pathlib.Path("scripts/repair_metrics_timestamps.py")
)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


def test_the_directory_name_is_read_as_utc():
    """make_output_dir names it in UTC, so it reconstructs exactly."""
    assert repair.timestamp_from_run_name("2026-07-30_0720") == "2026-07-30T07:20:00Z"


@pytest.mark.parametrize("name", ["latest", "2026-13-99_9999", "policy_snapshots", ""])
def test_anything_that_is_not_a_run_name_is_left_alone(name):
    assert repair.timestamp_from_run_name(name) is None


@pytest.fixture()
def run(tmp_path):
    from app.core.encryption import encrypted_write_json

    d = tmp_path / "2026-07-30_0720"
    d.mkdir(parents=True)
    encrypted_write_json(d / "_audit_metrics.json", {
        "timestamp": "2026-08-06T08:30:29Z",   # the moment it was *read*
        "risk_grade": "B",
        "recommendations": [{"title": "x"}],
    })
    return d


def _read(run):
    from app.core.encryption import encrypted_read_json
    return encrypted_read_json(run / "_audit_metrics.json")


def test_a_dry_run_reports_without_writing(run):
    before = _read(run)

    assert repair.repair_run(run, apply=False) == ("2026-08-06T08:30:29Z", "2026-07-30T07:20:00Z")
    assert _read(run) == before


def test_applying_restores_it(run):
    repair.repair_run(run, apply=True)

    assert _read(run)["timestamp"] == "2026-07-30T07:20:00Z"


def test_nothing_else_changes(run):
    before = _read(run)

    repair.repair_run(run, apply=True)
    after = _read(run)

    assert after["risk_grade"] == before["risk_grade"]
    assert after["recommendations"] == before["recommendations"]
    assert set(after) == set(before)


def test_a_run_already_correct_is_not_rewritten(run):
    repair.repair_run(run, apply=True)

    assert repair.repair_run(run, apply=True) is None
