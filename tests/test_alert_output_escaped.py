"""Tenant data in an alert arrives as text, never as markup.

An alert's item and detail come from the tenant: a Conditional Access
policy's name, a certificate's domain, a scanner's finding. The e-mail put
them into its HTML as they were, the Teams card put them into markdown, and
the Slack message into mrkdwn, where ``<!channel>`` pages everyone.
"""

from __future__ import annotations

import json

from app.services import alert_engine as ae
from app.services import webhook_sender as ws

HOSTILE = "<img src=x onerror=alert(1)>"


def _alert(**over) -> dict:
    alert = {
        "type": "policy_drift",
        "severity": "critical",
        "customer": "Acme AS",
        "item": HOSTILE,
        "detail": f"Sikkerhetspolicyen «{HOSTILE}» er fjernet.",
        "recommendation": "[Logg inn](https://phish.example)",
    }
    alert.update(over)
    return alert


async def test_a_hostile_policy_name_arrives_escaped_in_the_email(monkeypatch):
    import app.core.email_sender as es

    sent: dict = {}
    monkeypatch.setattr(es, "send_report_email", lambda **kw: sent.update(kw))

    assert await ae.send_email_alert({}, "drift@example.com", [_alert()]) is True

    body = sent["body_html"]
    assert HOSTILE not in body, "the policy name became markup in the mail client"
    assert "&lt;img src=x onerror=alert(1)&gt;" in body


async def test_the_customer_name_is_escaped_as_well(monkeypatch):
    import app.core.email_sender as es

    sent: dict = {}
    monkeypatch.setattr(es, "send_report_email", lambda **kw: sent.update(kw))

    await ae.send_email_alert({}, "drift@example.com", [_alert(customer="Kunde <b>A</b>")])

    assert "Kunde <b>A</b>" not in sent["body_html"]
    assert "Kunde &lt;b&gt;A&lt;/b&gt;" in sent["body_html"]


def _text_blocks(node):
    """Every TextBlock in a card: the elements that render markdown."""
    if isinstance(node, dict):
        if node.get("type") == "TextBlock":
            yield node["text"]
        for value in node.values():
            yield from _text_blocks(value)
    elif isinstance(node, list):
        for value in node:
            yield from _text_blocks(value)


def test_the_teams_card_shows_tenant_text_literally():
    card = ws._build_adaptive_card("Sybr HUB", [_alert()])

    markdown = " ".join(_text_blocks(card))
    assert HOSTILE not in markdown
    assert "phish.example" not in markdown, "a policy name became a link in the channel"
    # The text is still there, in a run that is never parsed.
    assert HOSTILE in json.dumps(card, ensure_ascii=False)


def test_the_slack_message_cannot_mention_or_link():
    payload = ws._build_slack_payload(
        "Sybr HUB", [_alert(item="<!channel>", detail="<https://phish.example|Logg inn>")]
    )

    text = json.dumps(payload, ensure_ascii=False)
    assert "<!channel>" not in text, "a policy name paged the whole channel"
    assert "<https://phish.example" not in text
    assert "&lt;!channel&gt;" in text
