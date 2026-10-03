"""The activity log and alert history are scoped to the caller's customers.

/api/activity-log took an optional, caller-supplied ``customer`` filter and
otherwise returned every entry — every customer's audits, pentests, switches
and deploys, to any signed-in user. /api/alerts/history did the same with the
alerts sent about every customer. A scoped caller now sees entries about
customers they hold, plus (for the activity log) their own actions.
"""

from __future__ import annotations

import json

import pytest

import app.core.activity_log as alog
from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    BETA,
    _reset_middleware_state,
    _scope_env,
    assert_no_foreign,
    client,
    login,
)


@pytest.fixture(autouse=True)
def _activity(tmp_path, monkeypatch):
    monkeypatch.setattr(alog, "_LOG_PATH", tmp_path / "activity_log.jsonl")
    # Routes log by name or by id depending on who wrote the entry.
    alog.log_activity("audit_completed", detail="acme by name", customer="Acme AS", user="ops")
    alog.log_activity("pentest_tls", detail="acme by id", customer=ACME, user="ops")
    alog.log_activity("audit_completed", detail="beta by name", customer="Beta AS", user="ops")
    alog.log_activity("pentest_tls", detail="beta by id", customer=BETA, user="ops")
    alog.log_activity("settings_changed", detail="someone else's", user="boss")
    alog.log_activity("mfa_enabled", detail="mine", user="viewer-acme")


@pytest.fixture(autouse=True)
def _alert_history(tmp_path, monkeypatch):
    path = tmp_path / "alert_history.json"
    entries = [
        {"type": "cert", "customer": "Acme AS", "item": "a", "sent_at": "2026-10-01T00:00:03"},
        {"type": "cert", "customer": "Beta AS", "item": "b", "sent_at": "2026-10-01T00:00:02"},
        {"type": "domain", "customer": "Orphan Web", "item": "o", "sent_at": "2026-10-01T00:00:01"},
    ]
    path.write_text(json.dumps(entries), "utf-8")
    monkeypatch.setattr("app.services.alert_engine._ALERT_HISTORY_PATH", path)


async def _viewer():
    return await login("viewer-acme", role=Role.viewer, customers=(ACME,), write=False)


def _details(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [e["detail"] for e in r.json()["entries"]]


async def test_a_scoped_caller_sees_their_customers_and_their_own_actions(client):
    r = client.get("/api/activity-log", headers=await _viewer())
    assert _details(r) == ["mine", "acme by id", "acme by name"]
    assert_no_foreign(r.text)


async def test_the_customer_filter_cannot_reach_past_the_scope(client):
    headers = await _viewer()
    assert _details(client.get("/api/activity-log?customer=Beta AS", headers=headers)) == []
    assert _details(client.get("/api/activity-log?customer=Acme AS", headers=headers)) == [
        "acme by name"
    ]


async def test_scoped_paging_runs_over_the_visible_entries(client):
    headers = await _viewer()
    r = client.get("/api/activity-log?limit=1&offset=1", headers=headers)
    assert _details(r) == ["acme by id"]


async def test_an_admin_sees_the_whole_activity_log(client):
    r = client.get("/api/activity-log", headers=await login("boss", role=Role.admin))
    assert len(_details(r)) == 6


async def test_alert_history_only_holds_the_callers_customers(client):
    r = client.get("/api/alerts/history", headers=await _viewer())
    assert r.status_code == 200, r.text
    assert [e["customer"] for e in r.json()["entries"]] == ["Acme AS"]
    assert r.json()["total"] == 1
    assert_no_foreign(r.text)


async def test_alert_history_is_whole_for_an_unrestricted_caller(client):
    headers = await login("wide", role=Role.technician, all_customers=True)
    entries = client.get("/api/alerts/history", headers=headers).json()["entries"]
    assert [e["customer"] for e in entries] == ["Acme AS", "Beta AS", "Orphan Web"]
