"""Sign-in activity and failures, read back from what the sign-in collector writes.

05_signin_activity.txt and 05b_signin_failures.txt now have JSON twins, and
_parse_signin_risk reads them first. Over ordinary sign-ins the two must give
the same answer. The sidecar must also get right what the text cannot carry:
the per-user failure table is split on runs of spaces and a row counts as a
user only when its first column holds an "@", so failures from sign-ins with no
UPN (written as "(unknown)") or with a bare account name were read as a
"failure reason" and left out of the failure total and the brute-force check.
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


async def test_the_sidecar_counts_failures_the_text_reads_as_reasons(tmp_path):
    files = await _collect(tmp_path, _attack_without_upns(), sidecars=True)

    risk = _parse_signin_risk(files)

    assert risk["total_failures"] == 122, "every failure, with a UPN or without"
    assert risk["top_failure_users"] == [{"user": "admin", "count": 52}]
    assert risk["top_failure_reasons"] == [], "neither name is a reason"
    assert risk["brute_force_suspects"] == ["admin"]
    assert risk["unique_users"] == 2, "kari and admin; a missing UPN is nobody"


async def test_the_text_alone_misreads_those_failures(tmp_path):
    """What a run from before the sidecar still reports, kept as it was."""
    files = await _collect(tmp_path, _attack_without_upns(), sidecars=False)

    risk = _parse_signin_risk(files)

    assert risk["total_failures"] == 0
    assert {r["reason"] for r in risk["top_failure_reasons"]} == {"admin", "(unknown)"}
    assert risk["brute_force_suspects"] == []


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
