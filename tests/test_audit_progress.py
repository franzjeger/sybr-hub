"""The audit progress counter must never claim more than it can.

A run reported "21 / 18" in the section counter and a bar past 100%. The
numerator counted every terminal progress event; the denominator counted the
selected sections once each. Anything that reported twice, or reported while
unselected, pushed them apart.
"""

from __future__ import annotations

import pytest

from app.modules.base import SectionStatus
from app.web.routes.audit import _ProgressTracker


def _run(tracker, names, status=SectionStatus.DONE):
    snap = tracker.snapshot()
    for name in names:
        tracker.record(name, SectionStatus.RUNNING)
        snap = tracker.record(name, status)
    return snap


def test_counts_selected_sections():
    tracker = _ProgressTracker({"Users", "Groups", "Admin Roles"})
    snap = _run(tracker, ["Users", "Groups", "Admin Roles"])
    assert snap["completed"] == 3
    assert snap["total_sections"] == 3
    assert snap["progress"] == 100


def test_running_alone_does_not_count():
    tracker = _ProgressTracker({"Users", "Groups"})
    tracker.record("Users", SectionStatus.RUNNING)
    snap = tracker.snapshot()
    assert snap["completed"] == 0
    assert snap["current_section"] == "Users"


@pytest.mark.parametrize(
    "status", [SectionStatus.DONE, SectionStatus.SKIPPED, SectionStatus.FAILED]
)
def test_every_terminal_status_counts(status):
    tracker = _ProgressTracker({"Users"})
    assert _run(tracker, ["Users"], status)["completed"] == 1


def test_repeated_terminal_report_counts_once():
    """The Azure sections run once per subscription under the same name."""
    tracker = _ProgressTracker({"Azure Compute", "Azure Network"})
    for _ in range(3):  # three subscriptions
        _run(tracker, ["Azure Compute", "Azure Network"])
    snap = tracker.snapshot()
    assert snap["completed"] == 2
    assert snap["progress"] == 100


def test_unselected_section_widens_the_total_instead_of_overflowing():
    """This is the "21 / 18" shape: more reported than was ever selected."""
    tracker = _ProgressTracker({"Users", "Groups"})
    snap = _run(tracker, ["Users", "Groups", "Tenant Information"])
    assert snap["completed"] == 3
    assert snap["total_sections"] == 3, "the estimate should widen, not be exceeded"
    assert snap["progress"] == 100


def test_progress_never_exceeds_one_hundred():
    tracker = _ProgressTracker({"Users"})
    for name in ("Users", "Groups", "Intune", "SharePoint", "Tenant Information"):
        snap = tracker.record(name, SectionStatus.DONE)
        assert snap["progress"] <= 100
        assert snap["completed"] <= snap["total_sections"]


def test_no_filter_means_every_declared_section():
    from app.modules.m365_audit.collector import AuditCollector

    expected = len(AuditCollector.GRAPH_SECTION_NAMES) + len(AuditCollector.AZURE_SECTION_NAMES)
    assert _ProgressTracker(None).snapshot()["total_sections"] == expected


def test_empty_selection_does_not_divide_by_zero():
    tracker = _ProgressTracker({"Not A Real Section"})
    assert tracker.snapshot()["progress"] == 0
    assert tracker.record("Users", SectionStatus.DONE)["progress"] == 100
