"""Automatic alerts speak the hub's language, and the reader's on Varsler.

The alert e-mail was Norwegian whatever the hub was set to: its subject,
heading, column labels and severity words were literals. Worse, each check
wrote its detail as a finished Norwegian sentence at check time, so nothing
downstream could put it in another language, and the history kept it in
Norwegian for good. A check now records a key and the values behind it; the
e-mail and the chat card build the sentence in the hub's language when they
send, and the Varsler page builds it in the reader's.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.reports.i18n import TRANSLATIONS
from app.services import alert_engine as ae
from app.services import webhook_sender as ws

UI = json.loads(Path("app/web/static/ui_i18n.json").read_text(encoding="utf-8"))


def _drift_alert() -> dict:
    return ae._detailed(
        {
            "type": "policy_drift",
            "severity": "critical",
            "customer": "Acme AS",
            "item": "Require MFA for admins",
            "days_remaining": 0,
        },
        "alert_detail_policy_removed",
        policy="Require MFA for admins",
        since="2026-09-30",
    )


@pytest.fixture
def mail(monkeypatch):
    import app.core.email_sender as es

    sent: dict = {}
    monkeypatch.setattr(es, "send_report_email", lambda **kw: sent.update(kw))
    return sent


# ── The e-mail ───────────────────────────────────────────────────────────────


async def test_an_english_hub_sends_an_english_email(mail):
    assert await ae.send_email_alert({"ui_language": "en"}, "drift@example.com", [_drift_alert()])

    assert mail["subject"] == "Sybr HUB: new alerts (1)"
    body = mail["body_html"]
    for english in ("automatic alerts", "Severity", "Customer", "Details", "Critical"):
        assert english in body
    assert (
        "The security policy “Require MFA for admins” has been removed since 30 September 2026."
        in body
    )
    for norwegian in ("varsler", "Alvorlighet", "Kunde<", "Kritisk", "fjernet", "Sendt"):
        assert norwegian not in body, f"{norwegian!r} in an English hub's e-mail"
    assert 'lang="en"' in body


async def test_a_norwegian_hub_sends_a_norwegian_email(mail):
    await ae.send_email_alert({}, "drift@example.com", [_drift_alert()])

    assert mail["subject"] == "Sybr HUB: nye varsler (1)"
    assert (
        "Sikkerhetspolicyen «Require MFA for admins» er fjernet siden 30. september 2026."
        in (mail["body_html"])
    )
    assert "Alvorlighet" in mail["body_html"]


def test_an_alert_date_is_written_as_the_reader_writes_a_date():
    """The detail's days are kept as ISO dates and written for the reader.

    The e-mail and the chat card read "fjernet siden 2026-09-30" and "utløper
    om 5 dager (2026-10-13)": a date the reader has to parse, the same in
    both languages (TODO C16). The stored value stays ISO, so the history
    means the same whatever language reads it later.
    """
    expiring = ae._detailed(
        {
            "type": "ssl_expiry",
            "severity": "warning",
            "customer": "Acme AS",
            "item": "acme.example",
        },
        "alert_detail_ssl_expiring",
        days=5,
        date="2026-10-13",
    )
    assert (
        ae.render_detail(expiring, "no") == "SSL-sertifikatet utløper om 5 dager (13. oktober 2026)"
    )
    assert (
        ae.render_detail(expiring, "en")
        == "The SSL certificate expires in 5 days (13 October 2026)"
    )
    assert expiring["detail_params"]["date"] == "2026-10-13"
    # A value that is no date (an entry from before, a hand-edited history) is
    # shown as it is rather than dropped.
    expiring["detail_params"]["date"] = "snart"
    assert ae.render_detail(expiring, "en").endswith("(snart)")


def test_the_dates_the_browser_formats_are_the_ones_the_server_formats():
    """alertDetail() in app-integrations.js names the same date values."""
    script = Path("app/web/static/app-integrations.js").read_text(encoding="utf-8")
    browser = re.search(r"_ALERT_DATE_PARAMS = \{([^}]*)\}", script)
    assert browser, "alertDetail() no longer formats the alert's dates"
    assert set(re.findall(r"(\w+): true", browser.group(1))) == set(ae.DATE_PARAMS)


def test_the_cards_timestamp_is_written_for_the_reader(monkeypatch):
    """ "Sendt 2026-10-08 14:05 UTC" on the chat card, in either language."""

    class _Now:
        @staticmethod
        def now(_tz):
            import datetime as _dt

            return _dt.datetime(2026, 10, 8, 14, 5, tzinfo=_dt.UTC)

    monkeypatch.setattr(ws, "datetime", _Now)
    assert ws._sent_at(ws._labels("no")) == "Sendt 8. oktober 2026 kl. 14:05 UTC"
    assert ws._sent_at(ws._labels("en")) == "Sent 8 October 2026, 14:05 UTC"


async def test_an_alert_without_a_key_shows_its_own_text(mail):
    """A pentest finding's detail is the scanner's sentence, not ours."""
    finding = {
        "type": "pentest_critical",
        "severity": "critical",
        "customer": "Acme AS",
        "item": "Open SMB share",
        "detail": "SMBv1 is enabled on 192.0.2.10",
    }
    await ae.send_email_alert({"ui_language": "en"}, "drift@example.com", [finding])

    assert "SMBv1 is enabled on 192.0.2.10" in mail["body_html"]


# ── The sweep ────────────────────────────────────────────────────────────────


@pytest.fixture
def sweep(monkeypatch):
    """run_alert_check on an English hub, with every side effect captured."""
    history: list[dict] = []
    cards: list[dict] = []
    monkeypatch.setattr(ae, "_load_alert_history", lambda: list(history))
    monkeypatch.setattr(ae, "_save_alert_history", lambda h: (history.clear(), history.extend(h)))
    monkeypatch.setattr(
        ae,
        "load_app_settings",
        lambda: {"ui_language": "en", "scheduler": {"webhook_url": "https://example.invalid/h"}},
    )
    monkeypatch.setattr(
        ae,
        "get_alert_config",
        lambda: {
            "enabled": True,
            "notify_teams": True,
            "notify_email": False,
            "rules": {
                "policy_drift": {"enabled": True},
                "pentest_critical": {"enabled": False},
            },
        },
    )

    async def _drift(_changed):
        return [_drift_alert()]

    async def _send(url, title, alerts, **kw):
        cards.append({"title": title, "alerts": alerts, **kw})
        return True

    monkeypatch.setattr(ae, "_check_policy_drift", _drift)
    monkeypatch.setattr(ws, "send_webhook", _send)
    return history, cards


async def test_the_sweep_writes_in_the_hubs_language(sweep):
    _, cards = sweep

    result = await ae.run_alert_check()

    (card,) = cards
    assert card["title"] == "🚨 Sybr HUB: new alerts (1)"
    assert card["lang"] == "en"
    assert [k for k, _ in card["facts"]] == ["New alerts", "Critical", "Warnings"]
    (sent,) = card["alerts"]
    assert sent["detail"].startswith("The security policy")
    assert sent["recommendation"].startswith("Confirm that the removal was intended")
    assert result["alerts"][0]["detail"].startswith("The security policy")


async def test_the_history_keeps_the_key_for_the_reader(sweep):
    """The Varsler page shows the history in the reader's language, so the
    entry keeps what the sentence is built from, not only the sentence."""
    history, _ = sweep

    result = await ae.run_alert_check()

    (entry,) = history
    assert entry["detail_key"] == "alert_detail_policy_removed"
    assert entry["detail_params"] == {"policy": "Require MFA for admins", "since": "2026-09-30"}
    assert result["alerts"][0]["detail_key"] == "alert_detail_policy_removed"


# ── The chat card ────────────────────────────────────────────────────────────


def test_the_teams_card_labels_follow_the_language():
    card = ws._build_adaptive_card(
        "Sybr HUB", [_drift_alert()], dashboard_url="https://hub.example", lang="en"
    )
    text = json.dumps(card, ensure_ascii=False)
    assert "Critical (1)" in text
    assert "Sent " in text
    assert "Open Sybr HUB" in text
    for norwegian in ("Kritisk", "Sendt", "Åpne"):
        assert norwegian not in text


def test_the_slack_labels_follow_the_language():
    payload = ws._build_slack_payload("Sybr HUB", [_drift_alert()], lang="en")
    text = json.dumps(payload, ensure_ascii=False)
    assert "Critical (1)" in text
    assert "Kritisk" not in text


# ── One vocabulary ───────────────────────────────────────────────────────────


def test_every_detail_key_is_translated_in_both_tables():
    """A key with no translation renders as the key's own name."""
    missing = [
        f"{table}:{key}:{lang}"
        for key in ae.DETAIL_KEYS
        for lang in ("no", "en")
        for table, text in (
            ("reports", TRANSLATIONS.get(key, {}).get(lang, "")),
            ("ui", UI[lang].get(key, "")),
        )
        if not str(text).strip()
    ]
    assert not missing, missing


def test_both_tables_ask_for_the_same_values():
    """The browser fills the placeholders the server's sentence has."""
    for key in ae.DETAIL_KEYS:
        for lang in ("no", "en"):
            server = set(re.findall(r"\{(\w+)\}", TRANSLATIONS[key][lang]))
            browser = set(re.findall(r"\{(\w+)\}", UI[lang][key]))
            assert server == browser, f"{key} ({lang}): {server} vs {browser}"


def test_every_key_a_check_uses_is_declared():
    """A key used and not declared is one nothing checks is translated."""
    used = set(re.findall(r'"(alert_detail_\w+)"', inspect.getsource(ae)))
    assert used - set(ae.DETAIL_KEYS) == set()
    assert used == set(ae.DETAIL_KEYS)


def test_no_check_writes_a_finished_sentence():
    """The checks hand over a key; a detail they write themselves is a
    sentence in one language again. The one exception is a pentest finding,
    whose detail is the scanner's own text."""
    source = inspect.getsource(ae)
    checks = source[source.index("# ── Data source checks") : source.index("# ── Recommendation")]
    written = re.findall(r'"detail":\s*([^\n]*)', checks) + re.findall(
        r"\bdetail = ([^\n]*)", checks
    )
    assert written == ['f.get("detail", "")[:200],']
