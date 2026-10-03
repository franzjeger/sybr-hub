"""Request models on the smaller routers: AI console settings and the dashboard.

Same three cases as the other request-model tests: what the SPA sends still
works, a value of the wrong type is a 422 rather than a 500, and an unknown
key is refused.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
    tech_client,
)

# ── AI console settings ──────────────────────────────────────────────────────


async def test_the_ai_settings_card_still_saves_cli_mode(admin_client):
    """claudeSaveSettings() sends all three fields; CLI mode leaves the key empty."""
    from app.core.config import load_app_settings

    r = admin_client.post(
        "/api/claude/settings", json={"api_key": "", "mode": "cli", "model": "claude-x"}
    )

    assert r.status_code == 200, r.text
    stored = load_app_settings()
    assert stored["claude_mode"] == "cli"
    assert stored["claude_model"] == "claude-x"


async def test_api_mode_without_a_key_keeps_its_message(admin_client):
    body = assert_refused(
        admin_client.post("/api/claude/settings", json={"api_key": " ", "mode": "api"}), 400
    )
    assert "API-nøkkel" in body["error"]


@pytest.mark.parametrize("body", [{"mode": "local"}, {"mode": "cli", "model": 3}, {"key": "x"}])
async def test_a_malformed_ai_settings_body_stores_nothing(admin_client, body):
    from app.core.config import load_app_settings

    assert_refused(admin_client.post("/api/claude/settings", json=body), 422)
    assert "claude_mode" not in load_app_settings()


# ── Dashboard: remediation and credential reset ──────────────────────────────


def _activate(client) -> str:
    from app.core.customer import CustomerManager

    cid = CustomerManager.save_customer({"CustomerName": "Customer A", "TenantId": "t-a"})
    assert client.post("/api/customers/switch", json={"customer_id": cid}).status_code == 200
    return cid


async def test_a_remediation_update_still_saves_and_takes_the_legacy_title(tech_client):
    _activate(tech_client)

    for body in ({"rec_id": "rec-1", "status": "done"}, {"title": "Old title", "status": "open"}):
        r = tech_client.post("/api/remediation", json=body)
        assert r.status_code == 200, r.text


async def test_an_unknown_remediation_status_keeps_its_message(tech_client):
    _activate(tech_client)

    body = assert_refused(
        tech_client.post("/api/remediation", json={"rec_id": "rec-1", "status": "later"}), 400
    )
    assert body["error"] != "err_invalid_status"


@pytest.mark.parametrize("body", [{"rec_id": 5}, {"rec_id": "r", "notes": ["x"]}, {"recId": "r"}])
async def test_a_malformed_remediation_update_is_a_422(tech_client, body):
    _activate(tech_client)
    assert_refused(tech_client.post("/api/remediation", json=body), 422)


@pytest.mark.parametrize("path", ["/api/customer/wipe", "/api/customer/renew"])
async def test_a_credential_reset_with_no_body_still_means_the_active_customer(tech_client, path):
    """The setup page posts with no body at all."""
    _activate(tech_client)

    r = tech_client.post(path)

    assert r.status_code == 200, r.text


@pytest.mark.parametrize("path", ["/api/customer/wipe", "/api/customer/renew"])
@pytest.mark.parametrize("body", [{"customer_id": 5}, {"customer": "c"}, ["c"]])
async def test_a_malformed_credential_reset_deletes_nothing(tech_client, monkeypatch, path, body):
    from app.core import credentials

    deleted = []
    monkeypatch.setattr(credentials, "delete_all_secrets", lambda tenant: deleted.append(tenant))
    _activate(tech_client)

    assert_refused(tech_client.post(path, json=body), 422)
    assert deleted == []


# ── Device dashboard poll interval ───────────────────────────────────────────


async def test_the_poll_interval_is_still_set_and_clamped(admin_client):
    from app.services.dashboard_poller import poller

    before = poller._interval
    try:
        r = admin_client.post("/api/dashboard/interval", json={"interval": 5})
        assert r.status_code == 200, r.text
        assert r.json()["interval"] == 10
    finally:
        poller.set_interval(before)


@pytest.mark.parametrize("body", [{"interval": "fast"}, {"seconds": 30}, [30]])
async def test_a_malformed_poll_interval_is_a_422_not_a_500(admin_client, body):
    """``int(body["interval"])`` on a word was a 500."""
    assert_refused(admin_client.post("/api/dashboard/interval", json=body), 422)
