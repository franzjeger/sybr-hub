"""The weekly report task e-mails each customer's latest report.

It never sent one. It looked for runs as ``<audit_dir setting>/<name>_*``,
with the setting read raw (a relative "audit_data" when unset), while runs
live at ``<audit dir>/<customer_dir_name>/<run>``: the glob matched nothing
and every week ended "0 reports sent". Its subject was Norwegian with a dash.

These run the task against a real audit folder and the real sender, with only
the SMTP connection faked.
"""

from __future__ import annotations

import email
import re
from email.message import Message

import pytest

from app.core.encryption import encrypted_write_json, encrypted_write_text
from app.services.scheduler import _do_scheduled_reports

CUSTOMERS = {
    "acme": {"_id": "acme", "CustomerName": "Acme AS", "TenantId": "t-acme"},
    "beta": {"_id": "beta", "CustomerName": "Beta", "TenantId": "t-beta"},
    "gamma": {"_id": "gamma", "CustomerName": "Gamma", "TenantId": "t-gamma"},
}
METRICS = {"risk_grade": "B", "risk_score": 72, "mfa_coverage_pct": 91.7, "total_users": 40}


class _SMTP:
    """Stands in for smtplib.SMTP and keeps every message sent through it."""

    sent: list[Message] = []  # noqa: RUF012

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        _SMTP.sent.append(email.message_from_bytes(msg.as_bytes()))


@pytest.fixture()
def hub(monkeypatch, tmp_path):
    """A hub with three customers, e-mail set up and an empty audit folder."""
    import app.core.email_sender as email_sender

    _SMTP.sent = []
    settings = {
        "email_default_recipient": "ops@msp.example",
        "smtp_server": "smtp.msp.example",
        "smtp_port": 587,
        "smtp_user": "hub",
        "smtp_password": "app-password",
        "ui_language": "no",
        # The old code read this, relative to wherever the process ran.
        "audit_dir": "audit_data",
    }
    audits = tmp_path / "audits"
    audits.mkdir()
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: settings)
    monkeypatch.setattr("app.core.config.get_audit_dir", lambda: audits)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS.values()]),
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.get_customer",
        staticmethod(lambda cid: dict(CUSTOMERS[cid]) if cid in CUSTOMERS else None),
    )
    monkeypatch.setattr(email_sender.smtplib, "SMTP", _SMTP)
    return audits


def _run(audits, folder: str, name: str, *, metrics=True):
    run = audits / folder / name
    run.mkdir(parents=True)
    if metrics:
        encrypted_write_json(run / "_audit_metrics.json", METRICS)
    return run


async def test_a_customer_with_a_run_gets_its_report_and_one_without_is_skipped(hub):
    # Acme: an older run, and the newest finished one with an English report.
    _run(hub, "Acme_AS", "2026-09-01_0700")
    run = _run(hub, "Acme_AS", "2026-09-28_0700")
    pdf = run / "audit_report_customer_2026-09-28.pdf"
    pdf.write_bytes(b"%PDF-1.7 acme")
    (run / "audit_report_tech_2026-09-28.pdf").write_bytes(b"%PDF-1.7 tech")
    encrypted_write_text(pdf.with_suffix(".html"), '<!DOCTYPE html>\n<html lang="en">')
    # A run cut short is newer, and has no metrics: not the one reported.
    _run(hub, "Acme_AS", "2026-09-29_0700", metrics=False)
    # Beta has none at all. Gamma has only its network config backups.
    (hub / "Gamma" / "network_configs").mkdir(parents=True)

    result = await _do_scheduled_reports()

    assert len(_SMTP.sent) == 1, result
    msg = _SMTP.sent[0]
    assert msg["To"] == "ops@msp.example"
    assert msg["Subject"] == "Audit report: Acme AS (2026-09-28_0700)"
    attached = [p for p in msg.walk() if p.get_content_type() == "application/pdf"]
    assert [p.get_filename() for p in attached] == ["audit_report_customer_2026-09-28.pdf"]
    assert attached[0].get_payload(decode=True) == b"%PDF-1.7 acme"
    assert result.startswith("1 reports sent, 2 customers without a finished run, 0 errors")


async def test_a_run_without_a_pdf_is_reported_in_the_hubs_language_and_says_so(hub):
    _run(hub, "Beta", "2026-09-28_0700")

    await _do_scheduled_reports()

    assert len(_SMTP.sent) == 1
    msg = _SMTP.sent[0]
    assert msg["Subject"] == "Auditrapport: Beta (2026-09-28_0700)"
    assert not re.search(r"[\u2014\u2013]", msg["Subject"]), "a dash in the subject"
    assert not [p for p in msg.walk() if p.get_content_type() == "application/pdf"]
    body = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    assert "ingen er vedlagt" in body.get_payload(decode=True).decode("utf-8")


async def test_without_email_settings_nothing_is_sent(hub, monkeypatch):
    _run(hub, "Beta", "2026-09-28_0700")
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {"smtp_server": ""})

    result = await _do_scheduled_reports()

    assert _SMTP.sent == []
    assert result.startswith("skipped")


class _Webhook:
    """Stands in for httpx.AsyncClient and keeps what was posted."""

    posted: list[dict] = []  # noqa: RUF012

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        _Webhook.posted.append(json)


def _card_text(card: dict) -> list[str]:
    return [block["text"] for block in card["attachments"][0]["content"]["body"]]


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("no", ["Sybr HUB: ukentlige rapporter sendt", "Kunder: 1. Mottaker: ops@msp.example."]),
        ("en", ["Sybr HUB: weekly reports sent", "Customers: 1. Recipient: ops@msp.example."]),
    ],
)
async def test_the_teams_card_is_in_the_hubs_language_without_an_emoji(
    hub, monkeypatch, lang, expected
):
    """It said "📊 Ukentlig rapport sendt til 1 kunder" whatever the hub's language."""
    import app.core.config as config

    settings = dict(
        config.load_app_settings(), ui_language=lang, webhook_url="https://hooks.example/x"
    )
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: settings)
    monkeypatch.setattr("httpx.AsyncClient", _Webhook)
    _Webhook.posted = []
    _run(hub, "Beta", "2026-09-28_0700")

    await _do_scheduled_reports()

    assert len(_Webhook.posted) == 1
    text = _card_text(_Webhook.posted[0])
    assert text == expected
    assert not any(ord(ch) > 0x2FFF for line in text for ch in line), "an emoji in the card"
