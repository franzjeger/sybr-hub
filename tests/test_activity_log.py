"""Tests for the encrypted activity log.

Pagination previously sliced to the requested page *before* applying the
customer filter, so a filtered query returned short or empty pages while
matching entries sat further down the file.
"""

from __future__ import annotations

import pytest

import app.core.activity_log as alog


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(alog, "_LOG_PATH", tmp_path / "activity_log.jsonl")
    yield


def _seed(count: int, customer: str) -> None:
    for i in range(count):
        alog.log_activity("audit_completed", detail=f"run {i}", customer=customer)


def test_entries_round_trip():
    alog.log_activity("audit_started", detail="d", customer="Acme", user="tech")
    entries = alog.get_activity_log()
    assert len(entries) == 1
    assert entries[0]["action"] == "audit_started"
    assert entries[0]["customer"] == "Acme"
    assert entries[0]["user"] == "tech"


def test_entries_are_newest_first():
    _seed(3, "Acme")
    details = [e["detail"] for e in alog.get_activity_log()]
    assert details == ["run 2", "run 1", "run 0"]


def test_log_is_encrypted_on_disk():
    alog.log_activity("audit_started", detail="secret detail", customer="Acme")
    raw = alog._LOG_PATH.read_bytes()
    assert b"secret detail" not in raw


def test_limit_and_offset_paginate():
    _seed(10, "Acme")
    page1 = alog.get_activity_log(limit=4, offset=0)
    page2 = alog.get_activity_log(limit=4, offset=4)
    assert len(page1) == len(page2) == 4
    assert {e["detail"] for e in page1}.isdisjoint({e["detail"] for e in page2})


def test_customer_filter_paginates_over_matches_only():
    """Regression: the filter used to run after the page was already cut.

    Acme is seeded *first* so those entries are the oldest — results come back
    newest-first, which pushes them past the first page. Slicing before
    filtering therefore finds no Acme rows at all.
    """
    _seed(5, "Acme")
    _seed(30, "Beta")

    acme = alog.get_activity_log(limit=10, customer="Acme")
    assert len(acme) == 5
    assert {e["customer"] for e in acme} == {"Acme"}


def test_customer_filter_is_case_insensitive():
    _seed(2, "Acme")
    assert len(alog.get_activity_log(customer="acme")) == 2


def test_customer_filter_with_offset():
    _seed(6, "Acme")   # oldest — only reachable if filtering precedes slicing
    _seed(20, "Beta")
    first = alog.get_activity_log(limit=3, offset=0, customer="Acme")
    second = alog.get_activity_log(limit=3, offset=3, customer="Acme")
    assert len(first) == len(second) == 3
    assert {e["detail"] for e in first}.isdisjoint({e["detail"] for e in second})


def test_missing_log_returns_empty():
    assert alog.get_activity_log() == []


def test_offset_past_the_end_returns_empty():
    _seed(3, "Acme")
    assert alog.get_activity_log(limit=10, offset=99) == []


def test_unknown_actions_are_still_recorded():
    """VALID_ACTIONS is a label hint, not a filter — dropping audit rows is worse."""
    alog.log_activity("something_new", detail="d", customer="Acme")
    assert alog.get_activity_log()[0]["action"] == "something_new"


def test_actions_logged_by_routes_are_known():
    """Keep the label set in step with what the code actually emits."""
    for action in ("fortigate_bootstrapped", "fortigate_credentials_viewed"):
        assert action in alog.VALID_ACTIONS
