"""Checks belong to the tested credentials, never a later edit or an unsaved draft."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.integration_health import fingerprint, integration_health, record_check


def test_check_expiry_rotation_and_no_secret_in_response():
    now = datetime.now(UTC)
    settings = {"itglue_api_key": "synthetic", "itglue_region": "eu"}
    assert integration_health(settings, now=now)["itglue"]["state"] == "configured"
    settings["integration_check_itglue"] = {
        "fingerprint": fingerprint("itglue", settings),
        "ok": True,
        "checked_at": now.isoformat(),
    }
    assert integration_health(settings, now=now)["itglue"] == {
        "state": "verified",
        "checked_at": now.isoformat(),
    }
    assert integration_health(settings, now=now + timedelta(days=1))["itglue"]["state"] == "stale"
    settings["integration_check_itglue"]["ok"] = False
    assert integration_health(settings, now=now)["itglue"]["state"] == "failed"
    settings["itglue_region"] = "us"
    assert integration_health(settings, now=now)["itglue"] == {
        "state": "configured",
        "checked_at": None,
    }
    assert "synthetic" not in str(integration_health(settings))


def test_concurrent_credential_edit_cannot_acquire_old_verification(monkeypatch):
    tested = {"itglue_api_key": "old", "itglue_region": "eu"}
    current = {**tested, "itglue_api_key": "new", "unrelated": "kept"}
    monkeypatch.setattr(
        "app.core.integration_health.update_app_settings", lambda mutate: mutate(current)
    )
    record_check("itglue", tested, True)
    assert "integration_check_itglue" not in current
    record_check("itglue", current.copy(), True)
    assert integration_health(current)["itglue"]["state"] == "verified"
    assert current["unrelated"] == "kept"


@pytest.mark.parametrize("ok", [True, False])
async def test_unsaved_credentials_do_not_verify_or_break_saved_configuration(monkeypatch, ok):
    from app.models.integrations import ITGlueTestRequest
    from app.web.connection_checks import connection_check

    records = []
    monkeypatch.setattr(
        "app.core.config.load_app_settings",
        lambda: {"itglue_api_key": "saved", "itglue_region": "eu"},
    )
    monkeypatch.setattr(
        "app.web.connection_checks.record_check", lambda *args: records.append(args)
    )

    @connection_check("itglue", {"api_key": "itglue_api_key", "region": "itglue_region"})
    async def endpoint(body: ITGlueTestRequest) -> dict:
        return {"ok": ok}

    await endpoint(ITGlueTestRequest(api_key="draft"))
    assert records == []
    await endpoint(ITGlueTestRequest(api_key="••••••", region="eu"))
    assert records[-1][2] is ok
    await endpoint(ITGlueTestRequest(api_key="", region="us"))
    assert len(records) == 1
