"""The report e-mail is in the report's language, and says only what is true.

``build_report_body_html`` and its subject were Norwegian whatever language
the report was written in. The body also printed "None" for a score the audit
could not compute and "None%" for coverage it could not measure, and said "the
PDF report is attached" on every e-mail, while the scheduler renders HTML
only: most automatic e-mails carried no PDF at all.

The language is the attached report's own (its HTML says ``<html lang>``),
else the hub's language, which is the language the scheduler writes in.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import app.core.email_sender as email_sender
from app.core.email_sender import (
    auto_send_after_audit,
    build_report_body_html,
    report_email_subject,
    report_language,
)
from app.core.encryption import encrypted_write_json, encrypted_write_text
from app.models.user import Role
from tests.scope_fixtures import (  # autouse fixtures apply to this module
    ACME,
    _reset_middleware_state,
    _scope_env,
    client,
    login,
)
from tests.test_english_reports import _norwegian, _text_nodes
from tests.test_norwegian_reports import _english

METRICS = {
    "risk_grade": "B",
    "risk_score": 72,
    "mfa_coverage_pct": 91.7,
    "secure_score_pct": 55.0,
    "total_users": 40,
    "total_warns": 3,
}
# A run whose score could not be computed: the metrics file carries None.
UNSCORED = {**METRICS, "risk_grade": "?", "risk_score": None, "mfa_coverage_pct": None}
# Norwegian text is written without an em dash or an en dash.
_DASHES = re.compile(r"[\u2014\u2013]")


def _text(body: str) -> list[str]:
    return [n for n in _text_nodes(body) if n.strip()]


@pytest.mark.parametrize("metrics", [METRICS, UNSCORED, None], ids=["scored", "unscored", "none"])
def test_an_english_e_mail_is_english(metrics):
    body = build_report_body_html("Acme AS", "2026-01-01_0900", metrics, lang="en")
    assert "Audit report: Acme AS" in body
    assert not [n for n in _text(body) if _norwegian(n)], _text(body)
    assert report_email_subject("Acme AS", "2026-01-01_0900", "en") == (
        "Audit report: Acme AS (2026-01-01_0900)"
    )


@pytest.mark.parametrize("metrics", [METRICS, UNSCORED, None], ids=["scored", "unscored", "none"])
def test_a_norwegian_e_mail_is_norwegian_and_has_no_dashes(metrics):
    body = build_report_body_html("Acme AS", "2026-01-01_0900", metrics, lang="no")
    assert "Auditrapport: Acme AS" in body
    nodes = _text(body)
    assert not [n for n in nodes if _english(n)], nodes
    assert not [n for n in nodes if _DASHES.search(n)], nodes
    subject = report_email_subject("Acme AS", "2026-01-01_0900", "no")
    assert subject == "Auditrapport: Acme AS (2026-01-01_0900)"


def test_what_was_not_measured_is_said_not_printed_as_none():
    body = build_report_body_html("Acme AS", "2026-01-01_0900", UNSCORED, lang="en")
    assert "None" not in body
    assert "not measured" in body
    assert "has no grade" in body
    scored = build_report_body_html("Acme AS", "2026-01-01_0900", METRICS, lang="en")
    assert "92%" in scored and "has no grade" not in scored


def test_it_says_a_pdf_is_attached_only_when_one_is():
    with_pdf = build_report_body_html("Acme AS", "d", METRICS, lang="no", attached=True)
    without = build_report_body_html("Acme AS", "d", METRICS, lang="no", attached=False)
    assert "PDF-rapporten med alle detaljer er vedlagt." in with_pdf
    assert "PDF-rapporten med alle detaljer er vedlagt." not in without
    assert "ingen er vedlagt" in without and "ingen er vedlagt" not in with_pdf


def test_the_customer_name_is_escaped():
    body = build_report_body_html("<b>Acme</b>", "d", METRICS, lang="en")
    assert "<b>Acme</b>" not in body
    assert "&lt;b&gt;Acme&lt;/b&gt;" in body


# ── Which language ───────────────────────────────────────────────────────────


def _run_with_report(tmp_path: Path, lang: str | None) -> tuple[Path, Path]:
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    run.mkdir(parents=True)
    pdf = run / "audit_report_customer_2026-01-01.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    if lang is not None:
        encrypted_write_text(pdf.with_suffix(".html"), f'<!DOCTYPE html>\n<html lang="{lang}">')
    return run, pdf


@pytest.mark.parametrize("lang", ["no", "en"])
def test_the_language_is_the_attached_reports(tmp_path, monkeypatch, lang):
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {"ui_language": "no"})
    _, pdf = _run_with_report(tmp_path, lang)
    assert report_language(pdf) == lang


@pytest.mark.parametrize("hub", ["no", "en"])
def test_without_a_report_the_hubs_language_decides(tmp_path, monkeypatch, hub):
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {"ui_language": hub})
    _, pdf = _run_with_report(tmp_path, None)
    assert report_language(pdf) == hub
    assert report_language(None) == hub


# ── The automatic e-mail after an audit ──────────────────────────────────────


def _auto_send(tmp_path, monkeypatch, *, report_lang: str | None, hub: str) -> dict:
    settings = {
        "email_auto_send": True,
        "email_default_recipient": "ops@acme.example",
        "smtp_server": "smtp.acme.example",
        "ui_language": hub,
    }
    monkeypatch.setattr("app.core.config.load_app_settings", lambda: settings)
    sent: dict = {}
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.update(kw))
    run = tmp_path / "Acme_AS" / "2026-01-01_0900"
    if report_lang is None:
        run.mkdir(parents=True)
    else:
        run, _ = _run_with_report(tmp_path, report_lang)
    encrypted_write_json(run / "_audit_metrics.json", METRICS)
    assert auto_send_after_audit(run) is None
    return sent


def test_the_automatic_e_mail_follows_an_english_report(tmp_path, monkeypatch):
    sent = _auto_send(tmp_path, monkeypatch, report_lang="en", hub="no")
    assert sent["subject"] == "Audit report: Acme AS (2026-01-01_0900)"
    assert "The PDF report with every detail is attached." in sent["body_html"]
    assert sent["attachment_path"].suffix == ".pdf"


def test_without_a_pdf_the_automatic_e_mail_says_so_in_the_hubs_language(tmp_path, monkeypatch):
    sent = _auto_send(tmp_path, monkeypatch, report_lang=None, hub="no")
    assert sent["subject"] == "Auditrapport: Acme AS (2026-01-01_0900)"
    assert sent["attachment_path"] is None
    assert "ingen er vedlagt" in sent["body_html"]
    assert "PDF-rapporten med alle detaljer er vedlagt." not in sent["body_html"]


# ── Through the routes ───────────────────────────────────────────────────────


async def test_the_send_report_route_writes_in_the_reports_language(client, tmp_path, monkeypatch):
    from app.core import job_state as state

    run, _ = _run_with_report(tmp_path, "en")
    encrypted_write_json(run / "_audit_metrics.json", METRICS)

    async def selected(user, customer_id, *, require_results=False):
        return state.AuditRunContext(owner_user_id=user.id, customer_id=customer_id, out_dir=run)

    monkeypatch.setattr("app.web.routes.reports._selected_audit_run", selected)
    sent: dict = {}
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.update(kw))
    headers = await login("mail-tech", customers=(ACME,))

    r = client.post(
        "/api/email/send-report",
        headers=headers,
        json={"customer_id": ACME, "to": "ops@acme.example"},
    )
    assert r.status_code == 200, r.text
    assert sent["subject"] == "Audit report: Acme AS (2026-01-01_0900)"
    assert not _DASHES.search(sent["subject"])  # "Auditrapport — …" before
    assert "Grade" in sent["body_html"]


@pytest.mark.parametrize(
    ("accept", "subject", "body"),
    [
        ("en", "Sybr HUB: test e-mail", "The e-mail settings work."),
        ("nb-NO", "Sybr HUB: testepost", "E-postinnstillingene fungerer."),
    ],
)
async def test_the_test_e_mail_is_in_the_readers_language(
    client, monkeypatch, accept, subject, body
):
    sent: dict = {}
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.update(kw))
    headers = await login(f"mail-admin-{accept}", role=Role.admin, all_customers=True)
    r = client.post(
        "/api/email/test",
        headers={**headers, "Accept-Language": accept},
        json={"to": "ops@acme.example", "smtp_server": "smtp.acme.example"},
    )
    assert r.status_code == 200, r.text
    assert sent["subject"] == subject
    assert body in sent["body_html"]
    assert not _DASHES.search(sent["subject"] + sent["body_html"])


async def test_missing_smtp_settings_are_refused_in_the_readers_language(client):
    headers = await login("mail-admin-refused", role=Role.admin, all_customers=True)
    r = client.post(
        "/api/email/test",
        headers={**headers, "Accept-Language": "en"},
        json={"to": "ops@acme.example"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "The SMTP settings are missing the server, user or password"


async def test_scheduled_audit_renders_pdf_before_automatic_email(tmp_path, monkeypatch):
    from app.services.audit_scheduler import AuditScheduler

    monkeypatch.setattr(
        "app.core.config.load_app_settings",
        lambda: {
            "ui_language": "en",
            "email_auto_send": True,
            "smtp_server": "smtp.example",
            "email_default_recipient": "ops@example.invalid",
        },
    )
    calls = []

    def generate(**kwargs):
        assert kwargs["formats"] == ["html", "pdf"]
        assert kwargs["lang"] == "en"
        calls.append("generate")
        (kwargs["out_dir"] / "audit.pdf").write_bytes(b"%PDF-test")

    monkeypatch.setattr("app.reports.generator.generate_reports", generate)

    def send(out_dir):
        assert (out_dir / "audit.pdf").exists()
        calls.append("send")

    monkeypatch.setattr(email_sender, "auto_send_after_audit", send)
    await AuditScheduler()._auto_report_and_email("Acme", {"_id": "acme"}, tmp_path, [])
    assert calls == ["generate", "send"]


async def test_pdf_generation_failure_does_not_send_an_incomplete_scheduled_report(
    tmp_path, monkeypatch
):
    from app.services.audit_scheduler import AuditScheduler

    monkeypatch.setattr("app.core.config.load_app_settings", lambda: {"email_auto_send": True})

    def fail(**kwargs):
        raise RuntimeError("synthetic PDF failure")

    monkeypatch.setattr("app.reports.generator.generate_reports", fail)
    monkeypatch.setattr(
        email_sender, "auto_send_after_audit", lambda *a: pytest.fail("should not send")
    )
    await AuditScheduler()._auto_report_and_email("Acme", {}, tmp_path, [])
