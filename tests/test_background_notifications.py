"""Background activity and delivery use the configured language and literal data."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import notification_text as words
from app.services import webhook_sender
from app.services.audit_scheduler import AuditScheduler


@pytest.mark.parametrize(
    "lang,done,failed,skipped",
    [
        ("no", "Bulk-audit fullført", "Audit feilet", "Hoppet over"),
        ("en", "Bulk audit completed", "Audit failed", "Skipped"),
    ],
)
def test_bulk_summary_language_and_measured_counts(monkeypatch, lang, done, failed, skipped):
    monkeypatch.setattr(words, "load_app_settings", lambda: {"ui_language": lang})
    result = words.bulk_audit_message(
        [
            {"customer": "Customer A", "status": "done", "grade": "B", "risk_score": 42},
            {
                "customer": "Customer B",
                "status": "error",
                "error": "[x](https://example.test) <!channel>",
            },
            {"customer": "Customer C", "status": "skipped"},
        ],
        3,
        2,
    )
    assert done in result and "1/3" in result and failed in result and skipped in result
    assert "[x](https://example.test) <!channel>" in result


@pytest.mark.parametrize(
    "lang,expected",
    [("en", "Audit completed"), ("no", "Audit fullført"), ("invalid", "Audit fullført")],
)
async def test_completion_keeps_failed_sections_visible(monkeypatch, lang, expected):
    monkeypatch.setattr(words, "load_app_settings", lambda: {"ui_language": lang})
    monkeypatch.setattr("app.services.audit_scheduler.get_scheduler_config", lambda: {})
    scheduler = AuditScheduler()
    scheduler._send_webhook = AsyncMock()
    await scheduler._notify_audit_completed(
        "Customer A", {"done_sections": 2, "failed_sections": 1, "total_sections": 3}
    )
    result = scheduler._send_webhook.call_args.args[0]
    assert expected in result and "2/3" in result
    assert ("1 sections failed" if lang == "en" else "1 seksjoner feilet") in result


@pytest.mark.parametrize(
    "kind,url",
    [
        ("teams", "https://example.webhook.office.com/test"),
        ("power_automate", "https://example.logic.azure.com/test"),
        ("slack", "https://hooks.slack.com/test"),
    ],
)
async def test_simple_notifications_cannot_turn_data_into_links_or_mentions(monkeypatch, kind, url):
    delivered = []
    client_class = httpx.AsyncClient

    def handler(request):
        delivered.append(json.loads(request.content))
        return httpx.Response(200)

    monkeypatch.setattr(
        webhook_sender.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    message = "Customer [Login](https://example.test)\n<!channel> <@U123> *Exception*"
    assert await webhook_sender.send_simple_message(url, message)
    payload = delivered[0]
    if kind == "slack":
        assert payload["blocks"][0]["text"] == {
            "type": "plain_text",
            "text": message,
            "emoji": False,
        }
    else:
        card = payload if kind == "power_automate" else payload["attachments"][0]["content"]
        assert all(block["type"] == "RichTextBlock" for block in card["body"])
        assert [block["inlines"][0]["text"] for block in card["body"]] == message.splitlines()


@pytest.mark.parametrize(
    "lang,label,title",
    [("no", "Oppgave", "deaktivert automatisk"), ("en", "Task", "automatically disabled")],
)
async def test_disabled_task_uses_language_and_checks_delivery(
    monkeypatch, caplog, lang, label, title
):
    from app.services import scheduler

    monkeypatch.setattr(
        "app.core.config.load_app_settings",
        lambda: {"ui_language": lang, "scheduler": {"webhook_url": "https://example.test/webhook"}},
    )
    monkeypatch.setattr(
        scheduler,
        "get_task_scheduler_config",
        lambda: {"test": {"label_no": "Oppgave", "label_en": "Task"}},
    )
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(webhook_sender, "send_simple_message", send)
    await scheduler._notify_task_failure("test", 3, "[Exception](https://example.test)")
    result = send.call_args.args[1]
    assert title in result and f"{label} (test)" in result and "3" in result
    assert "[Exception](https://example.test)" in result
    assert "not delivered" in caplog.text


@pytest.mark.parametrize(
    "lang,found,failed",
    [("no", "Fant 0 varsler", "Sjekker som feilet"), ("en", "Found 0 alerts", "Failed checks")],
)
async def test_alert_activity_preserves_failed_checks_and_system_actor(
    monkeypatch, lang, found, failed
):
    from app.core import activity_log, system_user
    from app.services import alert_engine

    settings = {"ui_language": lang}
    monkeypatch.setattr(alert_engine, "load_app_settings", lambda: settings)
    monkeypatch.setattr(
        alert_engine,
        "get_alert_config",
        lambda: {
            "rules": {
                "ssl_expiry": {"enabled": True},
                "policy_drift": {"enabled": False},
                "pentest_critical": {"enabled": False},
            }
        },
    )

    async def broken(_days):
        raise alert_engine.AlertCheckFailed("ssl_expiry")

    monkeypatch.setattr(alert_engine, "_check_ssl_expiry", broken)
    monkeypatch.setattr(alert_engine, "_load_alert_history", lambda: [])
    written = []
    monkeypatch.setattr(
        activity_log, "log_activity", lambda *args, **kwargs: written.append((args, kwargs))
    )
    result = await alert_engine.run_alert_check()
    assert result["failed_checks"] == ["ssl_expiry"]
    assert found in written[0][1]["detail"] and failed in written[0][1]["detail"]
    assert written[0][1]["user"] == system_user.USERNAME
