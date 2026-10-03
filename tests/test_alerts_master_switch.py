"""The scheduled sweep honours "Automatiske varsler er slått av".

Nothing read the master switch: with alerts switched off and a webhook stored,
the six-hourly sweep ran every rule and sent. The switch now stops the
unattended sweep; an admin's "check now" is not automatic and still runs.
"""

from __future__ import annotations

import pytest

from app.services import alert_engine as ae


@pytest.fixture
def sent(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ae, "_load_alert_history", lambda: [])
    monkeypatch.setattr(ae, "_save_alert_history", lambda h: None)
    monkeypatch.setattr(
        ae,
        "load_app_settings",
        lambda: {"scheduler": {"webhook_url": "https://example.invalid/hook"}},
    )

    async def _ssl(_days):
        return [
            {
                "type": "ssl_expiry",
                "severity": "critical",
                "customer": "Acme AS",
                "item": "acme.example",
                "detail": "SSL-sertifikat utløper om 2 dager",
                "days_remaining": 2,
            }
        ]

    async def _send(*a, **k):
        calls.append(k.get("title", ""))
        return True

    import app.services.webhook_sender as ws

    monkeypatch.setattr(ae, "_check_ssl_expiry", _ssl)
    monkeypatch.setattr(ws, "send_webhook", _send)
    return calls


def _config(monkeypatch, enabled: bool):
    monkeypatch.setattr(
        ae,
        "get_alert_config",
        lambda: {
            "enabled": enabled,
            "notify_teams": True,
            "notify_email": False,
            "rules": {
                "ssl_expiry": {"enabled": True, "days": 14},
                "policy_drift": {"enabled": False},
                "pentest_critical": {"enabled": False},
            },
        },
    )


async def test_the_scheduled_sweep_sends_nothing_while_alerts_are_off(sent, monkeypatch):
    _config(monkeypatch, enabled=False)
    result = await ae.run_alert_check(scheduled=True)
    assert sent == []
    assert result["disabled"] is True


async def test_the_scheduled_sweep_sends_while_alerts_are_on(sent, monkeypatch):
    _config(monkeypatch, enabled=True)
    await ae.run_alert_check(scheduled=True)
    assert sent == ["🚨 Sybr HUB: 1 nye varsler"]


async def test_check_now_runs_even_while_alerts_are_off(sent, monkeypatch):
    _config(monkeypatch, enabled=False)
    result = await ae.run_alert_check()
    assert result["total_found"] == 1
    assert len(sent) == 1


async def test_the_scheduler_runs_the_sweep_as_scheduled(monkeypatch):
    from app.services import scheduler
    from app.services.audit_scheduler import scheduler as audit_scheduler

    seen: list[dict] = []

    async def _check(**kwargs):
        seen.append(kwargs)
        return {"new_alerts": 2, "channels_notified": 1}

    async def _creds():
        return None

    monkeypatch.setattr(ae, "run_alert_check", _check)
    monkeypatch.setattr(audit_scheduler, "_check_credential_expiry", _creds)
    summary = await scheduler._do_alert_check()
    assert seen == [{"scheduled": True}]
    assert "2 alerts sent" in summary
