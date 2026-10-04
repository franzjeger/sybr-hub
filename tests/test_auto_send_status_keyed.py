"""What sending the report after an audit came to, in the reader's language.

auto_send_after_audit returned Norwegian sentences ("Auto-send aktivert, men
ingen standard mottaker konfigurert", "E-post feilet: ..."), and the audit
route added its own ("Rapport sendt til ..."). The audit screen showed them
to every reader as they were. They are keys now: the function says why, the
route passes the key and the values on, and the screen words them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core import email_sender
from app.core.email_sender import AutoSendFailure, auto_send_after_audit
from app.web.i18n import _UI_STRINGS, ui_t
from app.web.routes import audit as audit_route

UI = json.loads(Path("app/web/static/ui_i18n.json").read_text(encoding="utf-8"))
KEYS = ("err_auto_send_no_recipient", "err_auto_send_no_smtp", "err_auto_send_failed")


def _settings(monkeypatch, **over) -> dict:
    settings = {
        "email_auto_send": True,
        "email_default_recipient": "ops@acme.example",
        "smtp_server": "smtp.acme.example",
    }
    settings.update(over)
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: settings)
    return settings


def test_a_missing_recipient_is_a_key(tmp_path, monkeypatch):
    _settings(monkeypatch, email_default_recipient="")

    failure = auto_send_after_audit(tmp_path)

    assert isinstance(failure, AutoSendFailure)
    assert failure.key == "err_auto_send_no_recipient"
    # The scheduler logs it; the log keeps the Norwegian text it always had.
    assert "standardmottaker" in str(failure)


def test_a_missing_smtp_server_is_a_key(tmp_path, monkeypatch):
    _settings(monkeypatch, smtp_server="")

    assert auto_send_after_audit(tmp_path).key == "err_auto_send_no_smtp"


def test_a_refused_send_carries_the_servers_answer(tmp_path, monkeypatch):
    _settings(monkeypatch)

    def _refuse(**kw):
        raise OSError("535 authentication failed")

    monkeypatch.setattr(email_sender, "send_report_email", _refuse)

    failure = auto_send_after_audit(tmp_path)

    assert failure.key == "err_auto_send_failed"
    assert failure.params == {"error": "535 authentication failed"}


def test_auto_send_off_is_nothing_to_report(tmp_path, monkeypatch):
    _settings(monkeypatch, email_auto_send=False)

    assert auto_send_after_audit(tmp_path) is None


# ── Through the audit's completion ───────────────────────────────────────────


@pytest.fixture
def completion(monkeypatch, tmp_path):
    """_post_audit_side_effects with the report, the mail and the webhook stubbed."""

    def _no_context(**kw):
        raise RuntimeError("not needed here")

    async def _quiet(*a, **kw):
        return None

    from app.services.audit_scheduler import scheduler

    monkeypatch.setattr("app.reports.generator.build_report_context", _no_context)
    monkeypatch.setattr(scheduler, "_notify_audit_completed", _quiet)

    async def run() -> dict | None:
        return await audit_route._post_audit_side_effects({}, [], tmp_path, "Acme AS", "acme")

    return run


async def test_a_sent_report_is_keyed_for_the_screen(monkeypatch, completion):
    _settings(monkeypatch)
    monkeypatch.setattr(email_sender, "auto_send_after_audit", lambda out_dir: None)

    status = await completion()

    assert status["ok"] is True
    assert status["msg_key"] == "audit_report_sent"
    assert status["msg_params"] == {"recipient": "ops@acme.example"}
    assert status["msg"] == "Rapport sendt til ops@acme.example"


async def test_a_failure_is_keyed_for_the_screen(monkeypatch, completion):
    _settings(monkeypatch)
    monkeypatch.setattr(
        email_sender,
        "auto_send_after_audit",
        lambda out_dir: AutoSendFailure("err_auto_send_no_smtp"),
    )

    status = await completion()

    assert status == {
        "ok": False,
        "msg": "Automatisk utsending er slått på, men ingen SMTP-server er satt",
        "msg_key": "err_auto_send_no_smtp",
        "msg_params": {},
    }


# ── One vocabulary ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", [*KEYS, "audit_report_sent"])
def test_the_server_and_the_screen_say_the_same(key):
    for lang in ("no", "en"):
        browser = UI[lang][key]
        server = _UI_STRINGS[lang].get(key, browser)
        assert server == browser, f"{key} ({lang})"
        assert "\N{EM DASH}" not in browser and "\N{EN DASH}" not in browser
    assert set(re.findall(r"\{(\w+)\}", UI["no"][key])) == set(
        re.findall(r"\{(\w+)\}", UI["en"][key])
    )


def test_an_english_reader_gets_english():
    from types import SimpleNamespace

    request = SimpleNamespace(query_params={"lang": "en"}, headers={})

    assert ui_t("err_auto_send_no_smtp", request) == (
        "Automatic sending is on, but no SMTP server is set"
    )


def test_the_audit_screen_words_the_key():
    source = Path("app/web/static/app-audit.js").read_text(encoding="utf-8")
    assert "esc(_emailStatusText(d.email_status))" in source
    assert "esc(d.email_status.msg)" not in source
