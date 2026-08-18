"""The Viva Engage (Yammer) usage section.

The section reads one Graph usage report (getYammerActivityUserDetail) and turns
it into an audit signal: is the enterprise social layer actually used, or is it a
provisioned, ungoverned surface nobody watches? These run the real section
against a fake Graph and assert on the files it writes and the status/warnings it
records — the same seam-testing shape as tests/test_section_seams.py.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from app.core.encryption import encrypted_read_text
from app.modules.base import SectionStatus
from app.modules.m365_audit.graph_client import GraphPermissionError
from app.modules.m365_audit.sections.viva_engage import VivaEngageSection


class _ReportGraph:
    """A Graph whose only method the section uses is get_report."""

    def __init__(self, rows=None, error=None):
        self._rows = rows if rows is not None else []
        self._error = error

    async def get_report(self, name, period="D90"):
        assert name == "getYammerActivityUserDetail"
        if self._error is not None:
            raise self._error
        return self._rows


def _tmp() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


def _read(out_dir: pathlib.Path, name: str) -> str:
    return encrypted_read_text(out_dir / name)


async def _run(rows=None, error=None) -> tuple[VivaEngageSection, pathlib.Path]:
    section = VivaEngageSection(_tmp(), _ReportGraph(rows=rows, error=error))
    await section.collect()
    return section, section.out_dir


def _active(upn: str) -> dict:
    return {"userPrincipalName": upn, "displayName": upn.split("@")[0],
            "lastActivityDate": "2026-08-10", "postedCount": "5",
            "readCount": "40", "likedCount": "3",
            "assignedProducts": ["OFFICE 365 E3"], "userState": "active"}


def _idle(upn: str) -> dict:
    return {"userPrincipalName": upn, "displayName": upn.split("@")[0],
            "lastActivityDate": "", "postedCount": "0", "readCount": "0",
            "likedCount": "0", "assignedProducts": ["OFFICE 365 E3"],
            "userState": "active"}


@pytest.mark.asyncio
async def test_provisioned_but_unused_is_flagged_and_not_a_failure():
    """Users are in the report but none has any activity — enabled but unused.

    That is the finding worth raising, and it is a warning on a *completed*
    section, never a failure (the data was read fine; it just says nobody uses
    it).
    """
    section, out = await _run(rows=[_idle("ola@acme.no"), _idle("per@acme.no")])
    assert section.result.status == SectionStatus.DONE
    assert any("unused" in w.lower() for w in section.result.warns)
    summary = _read(out, "33_viva_engage_summary.txt")
    assert "In use: no" in summary
    assert "Active (any activity): 0" in summary
    assert "Present but inactive: 2" in summary


@pytest.mark.asyncio
async def test_active_usage_is_reported_without_a_warning():
    section, out = await _run(rows=[_active("kari@acme.no"), _idle("ola@acme.no")])
    assert section.result.status == SectionStatus.DONE
    assert not any("unused" in w.lower() for w in section.result.warns)
    summary = _read(out, "33_viva_engage_summary.txt")
    assert "In use: yes" in summary
    assert "Active (any activity): 1" in summary
    assert "Posters (created content): 1" in summary
    activity = _read(out, "33_viva_engage_activity.txt")
    assert "kari@acme.no" in activity


@pytest.mark.asyncio
async def test_an_empty_report_is_not_in_use_and_not_a_failure():
    """Graph answered with nothing: the service is simply not in use. That must
    read as a clean result, not as a collection that failed or a zero to alarm
    on.
    """
    section, out = await _run(rows=[])
    assert section.result.status == SectionStatus.DONE
    assert section.result.warns == []
    activity = _read(out, "33_viva_engage_activity.txt")
    assert "not in use" in activity.lower()
    summary = _read(out, "33_viva_engage_summary.txt")
    assert "In use: no" in summary
    assert "Total users in report: 0" in summary


@pytest.mark.asyncio
async def test_a_refused_report_is_recorded_as_unavailable_not_empty():
    """A 403 is 'we could not look', not 'there is nothing there'."""
    err = GraphPermissionError("reports/getYammerActivityUserDetail", 403)
    section, out = await _run(error=err)
    assert section.result.status == SectionStatus.FAILED
    activity = _read(out, "33_viva_engage_activity.txt")
    assert "not available" in activity.lower()
    assert "Reports.Read.All" in activity


@pytest.mark.asyncio
async def test_a_deleted_user_with_activity_is_not_counted_active():
    """A removed account's old activity must not read as a live, active user."""
    gone = {"userPrincipalName": "gone@acme.no", "lastActivityDate": "2026-07-01",
            "postedCount": "2", "readCount": "1", "likedCount": "0",
            "userState": "deleted"}
    _section, out = await _run(rows=[gone, _idle("ola@acme.no")])
    summary = _read(out, "33_viva_engage_summary.txt")
    assert "Deleted: 1" in summary
    assert "Active (any activity): 0" in summary  # gone is deleted, ola is idle


@pytest.mark.asyncio
async def test_concealed_user_names_are_flagged():
    concealed = {"userPrincipalName": "AB12CD34", "lastActivityDate": "2026-08-01",
                 "postedCount": "1", "readCount": "2", "likedCount": "0",
                 "userState": "active"}
    _section, out = await _run(rows=[concealed])
    activity = _read(out, "33_viva_engage_activity.txt")
    assert "conceals user names" in activity
    summary = _read(out, "33_viva_engage_summary.txt")
    assert "Names concealed: yes" in summary
