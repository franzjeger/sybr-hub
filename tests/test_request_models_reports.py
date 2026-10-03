"""Request models on the report, archive and e-mail routes.

``/email/test`` handed the whole raw body to the mailer as its SMTP config,
``/report/generate`` passed any value through to the generator, and
``/reports/archive/cleanup`` turned ``int(body["months"])`` into a cutoff — so
``0`` or ``-1`` deleted every report there was.
"""

from __future__ import annotations

import pytest

from tests.request_body_fixtures import (  # autouse fixtures apply to this module
    _init_db,
    _reset_middleware_state,
    admin_client,
    assert_refused,
)

# What app-settings.js testEmail() sends.
EMAIL_FORM = {
    "smtp_server": "smtp.example.no",
    "smtp_port": 587,
    "smtp_user": "mailer@example.no",
    "smtp_password": "app-password",
    "smtp_from": "hub@example.no",
    "to": "ops@example.no",
}


@pytest.fixture()
def sent(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "app.core.email_sender.send_report_email", lambda **kwargs: calls.append(kwargs)
    )
    return calls


async def test_the_email_test_form_still_reaches_the_mailer(admin_client, sent):
    r = admin_client.post("/api/email/test", json=EMAIL_FORM)

    assert r.status_code == 200, r.text
    [call] = sent
    assert call["to"] == "ops@example.no"
    assert call["smtp_config"]["smtp_server"] == "smtp.example.no"
    assert call["smtp_config"]["smtp_port"] == 587


async def test_the_smtp_user_is_still_the_fallback_recipient(admin_client, sent):
    body = {k: v for k, v in EMAIL_FORM.items() if k != "to"}

    assert admin_client.post("/api/email/test", json=body).status_code == 200
    assert sent[0]["to"] == "mailer@example.no"


async def test_an_email_test_without_any_recipient_keeps_its_message(admin_client, sent):
    body = assert_refused(admin_client.post("/api/email/test", json={}), 400)
    assert body["error"] != "err_no_recipient"
    assert sent == []


@pytest.mark.parametrize(
    "over", [{"smtp_port": "submission"}, {"smtp_password": None}, {"smtp_host": "x"}]
)
async def test_a_malformed_email_test_never_reaches_the_mailer(admin_client, sent, over):
    assert_refused(admin_client.post("/api/email/test", json={**EMAIL_FORM, **over}), 422)
    assert sent == []


async def test_send_report_refuses_a_malformed_recipient(admin_client, sent):
    for body in (
        {"customer_id": "c1", "to": ["a@example.no"]},
        {"customer_id": "c1", "recipient": "a@example.no"},
        {"to": "a@example.no"},
    ):
        assert_refused(admin_client.post("/api/email/send-report", json=body), 422)
    assert sent == []


async def test_a_report_the_screen_offers_gets_past_the_body(admin_client):
    """No audit is loaded here, so the answer is the handler's own 400."""
    r = admin_client.post(
        "/api/report/generate",
        json={
            "customer_id": "c1",
            "format": "pdf",
            "report_type": "customer",
            "lang": "en",
            "frameworks": "cis+nist",
            "theme": "dark",
        },
    )
    assert r.status_code == 400, r.text


@pytest.mark.parametrize(
    "body",
    [{"lang": "de"}, {"format": "docx"}, {"frameworks": ["cis"]}, {"report_type": "x"}, {"x": 1}],
)
async def test_a_report_option_the_generator_does_not_know_is_refused(admin_client, body):
    assert_refused(
        admin_client.post("/api/report/generate", json={"customer_id": "c1", **body}), 422
    )


async def test_a_report_names_its_customer(admin_client):
    assert_refused(admin_client.post("/api/report/generate", json={"format": "html"}), 422)


async def test_archive_delete_keeps_its_messages(admin_client):
    body = assert_refused(admin_client.post("/api/reports/archive/delete", json={}), 400)
    assert body["error"] == "Sti er påkrevd"
    assert body["error_key"] == "err_reports_path_required"
    assert_refused(admin_client.post("/api/reports/archive/delete", json={"path": 1}), 422)
    assert_refused(
        admin_client.post("/api/reports/archive/delete", json={"path": "Customer_A/none"}), 404
    )


@pytest.mark.parametrize("months", [0, -1, "six", None])
async def test_a_cleanup_that_would_delete_everything_is_refused(admin_client, months):
    assert_refused(admin_client.post("/api/reports/archive/cleanup", json={"months": months}), 422)


async def test_the_cleanup_buttons_still_work(admin_client):
    for months in (3, 6, 12):
        r = admin_client.post("/api/reports/archive/cleanup", json={"months": months})
        assert r.status_code == 200, r.text


async def test_the_qbr_summary_customer_list_is_typed(admin_client):
    assert_refused(admin_client.post("/api/reports/batch-summary", json={}), 404)
    assert_refused(admin_client.post("/api/reports/batch-summary", json={"customer_ids": "a"}), 422)
