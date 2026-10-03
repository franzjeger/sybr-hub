"""Sign-in activity and failures, read back from what the sign-in collector writes.

05_signin_activity.txt and 05b_signin_failures.txt now have JSON twins, and
_parse_signin_risk reads them first. Over ordinary sign-ins the two must give
the same answer, and over the rows the text used to misread too: the per-user
tables were split on runs of spaces and a row counted as a user only when its
first column held an "@", so failures from sign-ins with no UPN (written as
"(unknown)") or with a bare account name were read as a "failure reason" and
left out of the failure total and the brute-force check. The rows are now read
by the collector's columns. What the text cannot carry is the breakdowns past
their top ten.
"""

from __future__ import annotations

import pytest

from app.modules.m365_audit.sections.signins import SignInsSection
from app.reports.parsers import _parse_signin_risk
from tests.collector_rig import FakeGraph, refused, run_sections


def _event(upn: str | None, code: int, *, reason: str = "", ip: str = "", country: str = ""):
    event = {
        "status": {"errorCode": code, "failureReason": reason},
        "ipAddress": ip,
        "location": {"countryOrRegion": country},
    }
    if upn is not None:
        event["userPrincipalName"] = upn
    return event


BAD_PASSWORD = "Invalid username or password or Invalid on-premise username or password."


def _ordinary_events() -> list[dict]:
    return (
        # A guessing attack: many failures, no successes.
        [
            _event("post@acme.example", 50126, reason=BAD_PASSWORD, ip="203.0.113.5", country="RU")
            for _ in range(60)
        ]
        # A device retrying an old password: failures between successes.
        + [
            _event("kari@acme.example", 50053, reason="Account is locked", ip="198.51.100.7")
            for _ in range(55)
        ]
        + [_event("kari@acme.example", 0) for _ in range(30)]
        + [_event("ola@acme.example", 0) for _ in range(3)]
        # One failure from each of twelve countries: the text keeps ten.
        + [
            _event("ola@acme.example", 50126, reason=BAD_PASSWORD, country=f"C{i:02d}")
            for i in range(12)
        ]
        # No status at all: neither a success nor a failure.
        + [{"userPrincipalName": "ola@acme.example", "status": None}]
    )


async def _collect(tmp_path, events, *, sidecars: bool) -> dict:
    async with FakeGraph({"auditLogs/signIns": events}, page_size=50) as fake:
        files = await run_sections(SignInsSection(tmp_path, fake.client), sidecars=sidecars)
        assert fake.unrouted == []
    return files


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_ordinary_sign_ins_read_the_same_from_either_file(tmp_path, sidecars):
    files = await _collect(tmp_path, _ordinary_events(), sidecars=sidecars)
    assert ("05_signin_activity.json" in files) is sidecars
    assert ("05b_signin_failures.json" in files) is sidecars

    risk = _parse_signin_risk(files)

    assert risk["has_data"] is True
    assert risk["total_signins"] == 161
    assert risk["unique_users"] == 3
    assert risk["total_failures"] == 127
    assert risk["top_failure_users"] == [
        {"user": "post@acme.example", "count": 60},
        {"user": "kari@acme.example", "count": 55},
        {"user": "ola@acme.example", "count": 12},
    ]
    assert risk["top_failure_reasons"] == []
    assert risk["top_error_codes"] == [
        {"code": "50126", "reason": BAD_PASSWORD, "count": 72},
        {"code": "50053", "reason": "Account is locked", "count": 55},
    ]
    assert len(risk["top_source_countries"]) == 10
    assert risk["top_source_countries"][0] == {"country": "RU", "count": 60}
    assert risk["top_source_ips"] == [
        {"ip": "203.0.113.5", "count": 60},
        {"ip": "198.51.100.7", "count": 55},
    ]
    assert risk["brute_force_suspects"] == ["post@acme.example"]
    assert risk["stale_credential_users"] == ["kari@acme.example"]


async def test_the_sidecars_are_what_the_reader_reads(tmp_path):
    files = await _collect(tmp_path, _ordinary_events(), sidecars=True)
    files["05_signin_activity.txt"] = ""
    files["05b_signin_failures.txt"] = ""

    risk = _parse_signin_risk(files)

    assert risk["has_data"] is True
    assert risk["no_data_reason"] is None
    assert risk["total_signins"] == 161
    assert risk["unique_users"] == 3
    assert risk["total_failures"] == 127
    assert risk["brute_force_suspects"] == ["post@acme.example"]
    assert risk["stale_credential_users"] == ["kari@acme.example"]


def _attack_without_upns() -> list[dict]:
    """A spray at a bare account name, and failures Graph logged with no UPN at all."""
    return (
        [_event("admin", 50126, reason=BAD_PASSWORD, ip="192.0.2.10") for _ in range(52)]
        + [_event(None, 50126, reason=BAD_PASSWORD, ip="192.0.2.11") for _ in range(70)]
        + [_event("kari@acme.example", 0) for _ in range(4)]
    )


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_failures_without_a_upn_are_counted_from_either_file(tmp_path, sidecars):
    """The text was read as "(unknown)" and "admin" being failure reasons.

    A run from before the sidecar reported no failures and no brute-force
    suspect for a spray at a bare account name. Its rows are now read by the
    collector's columns, so the text gives the sidecar's answer.
    """
    files = await _collect(tmp_path, _attack_without_upns(), sidecars=sidecars)

    risk = _parse_signin_risk(files)

    assert risk["total_failures"] == 122, "every failure, with a UPN or without"
    assert risk["top_failure_users"] == [{"user": "admin", "count": 52}]
    assert risk["top_failure_reasons"] == [], "neither name is a reason"
    assert risk["brute_force_suspects"] == ["admin"]
    assert risk["unique_users"] == 2, "kari and admin; a missing UPN is nobody"


@pytest.mark.parametrize("sidecars", [True, False], ids=["json", "text-only run"])
async def test_a_upn_longer_than_its_column_is_still_one_user(tmp_path, sidecars):
    """The UPN is written whole and pushes the counts right; they stay its own."""
    long_upn = "anne-marie.christoffersen-haugsland@kunde-a.acme.example"
    assert len(long_upn) > 50
    events = [_event(long_upn, 50126, reason=BAD_PASSWORD) for _ in range(51)]
    files = await _collect(tmp_path, [*events, _event(long_upn, 0)], sidecars=sidecars)

    risk = _parse_signin_risk(files)

    assert risk["total_failures"] == 51
    assert risk["top_failure_users"] == [{"user": long_upn, "count": 51}]
    assert risk["brute_force_suspects"] == [long_upn]
    assert risk["unique_users"] == 1


async def test_a_refused_read_writes_no_sidecar_and_reads_as_unmeasured(tmp_path):
    licence_gap = refused(
        403,
        "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
        "Neither tenant is B2C or tenant doesn't have premium license",
    )
    files = await _collect(tmp_path, licence_gap, sidecars=True)

    assert "05_signin_activity.json" not in files
    assert "05b_signin_failures.json" not in files
    risk = _parse_signin_risk(files)
    assert risk["has_data"] is False
    assert risk["no_data_reason"] == "license_p1_missing"
    assert risk["total_signins"] == 0
