"""Shared webhook sender — rich formatting for Teams, Slack, and generic webhooks.

Replaces the duplicated webhook logic in alert_engine.py and scheduler.py.
Builds proper Adaptive Cards (Teams/Power Automate) and Slack blocks
instead of flat text.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

# ── Webhook type detection ──────────────────────────────────────────────────


def _detect_type(url: str) -> str:
    """Detect webhook type from URL."""
    low = url.lower()
    if "hooks.slack.com" in low or "slack" in low:
        return "slack"
    if "logic.azure.com" in low or "powerautomate" in low or "flow.microsoft.com" in low:
        return "power_automate"
    if "office.com" in low or "webhook.office" in low:
        return "teams"
    if "discord" in low:
        return "slack"  # Discord accepts Slack-format
    return "generic"


# ── Teams Adaptive Card builder ─────────────────────────────────────────────


def _severity_color(severity: str) -> str:
    return {"critical": "Attention", "warning": "Warning", "info": "Accent"}.get(
        severity, "Default"
    )


def _severity_emoji(severity: str) -> str:
    return {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")


def _literal(text: str, *, spacing: str = "Small", **run: object) -> dict:
    """A card paragraph shown exactly as written.

    A TextBlock renders markdown, and an alert's item and detail are the
    tenant's: a policy name, a domain, a scanner's finding. A policy named
    ``[Logg inn](https://phish.example)`` became a link in the channel. A
    TextRun inside a RichTextBlock is never parsed as markdown.
    """
    return {
        "type": "RichTextBlock",
        "spacing": spacing,
        "inlines": [{"type": "TextRun", "text": text, "size": "Small", **run}],
    }


def _slack_escape(text: object) -> str:
    """Text Slack shows as written, not as a mention or a link.

    Slack reads ``<!channel>``, ``<@U123>`` and ``<https://x|y>`` in mrkdwn,
    so a tenant's policy named ``<!channel>`` paged the whole channel. Slack
    asks for exactly these three characters to be escaped.
    """
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _labels(lang: str):
    """The card's own words in *lang* (app/reports/i18n.py, ``alert_*``)."""
    from app.reports.i18n import T

    return T(lang if lang in ("no", "en") else "no")


def _severity_groups(alerts: list[dict], t) -> list[tuple[list[dict], str, str]]:
    """The alerts by severity, most severe first: (group, label, severity)."""
    return [
        ([a for a in alerts if a.get("severity") == "critical"], t.alert_sev_critical, "critical"),
        ([a for a in alerts if a.get("severity") == "warning"], t.alert_sev_warning, "warning"),
        (
            [a for a in alerts if a.get("severity") not in ("critical", "warning")],
            t.alert_sev_info,
            "info",
        ),
    ]


def _sent_at(t) -> str:
    return str(t("alert_sent_at", when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")))


def _build_adaptive_card(
    title: str,
    alerts: list[dict],
    *,
    subtitle: str = "",
    facts: list[tuple[str, str]] | None = None,
    dashboard_url: str = "",
    lang: str = "no",
) -> dict:
    """Build a rich Adaptive Card for Teams / Power Automate.

    Alert dict shape: {type, severity, customer, item, detail, recommendation?}
    """
    t = _labels(lang)
    body: list[dict] = []

    # Header container
    header_items: list[dict] = [
        {
            "type": "TextBlock",
            "text": title,
            "wrap": True,
            "weight": "Bolder",
            "size": "Medium",
            "style": "heading",
        },
    ]
    if subtitle:
        header_items.append(
            {
                "type": "TextBlock",
                "text": subtitle,
                "wrap": True,
                "size": "Small",
                "isSubtle": True,
                "spacing": "None",
            }
        )
    body.append(
        {
            "type": "Container",
            "items": header_items,
            "style": "emphasis",
            "bleed": True,
            "spacing": "None",
        }
    )

    # KPI FactSet (risk score, grade, etc.)
    if facts:
        body.append(
            {
                "type": "FactSet",
                "facts": [{"title": k, "value": v} for k, v in facts],
                "spacing": "Medium",
            }
        )

    for group, label, severity in _severity_groups(alerts, t):
        if not group:
            continue
        color = _severity_color(severity)

        items: list[dict] = [
            {
                "type": "TextBlock",
                "text": f"{_severity_emoji(severity)} **{label} ({len(group)})**",
                "wrap": True,
                "weight": "Bolder",
                "size": "Small",
            }
        ]

        for a in group[:15]:
            # Two-column: customer | item + detail. Literal text, not markdown:
            # the item and detail are the tenant's (see _literal).
            cols: list[dict] = [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [_literal(str(a.get("customer", "")), weight="Bolder")],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        _literal(f"{a.get('item', '')}: {a.get('detail', '')}", isSubtle=True)
                    ],
                },
            ]
            items.append(
                {
                    "type": "ColumnSet",
                    "columns": cols,
                    "spacing": "Small",
                }
            )

            # Recommendation line (if present). A pentest finding's remediation
            # is the scanner's text, so it is literal too.
            rec = a.get("recommendation") or a.get("remediation")
            if rec:
                items.append(_literal(f"💡 {rec}", isSubtle=True, spacing="None"))

        if len(group) > 15:
            items.append(
                {
                    "type": "TextBlock",
                    "text": f"_{t('alert_and_more', count=len(group) - 15)}_",
                    "wrap": True,
                    "isSubtle": True,
                    "size": "Small",
                }
            )

        body.append(
            {
                "type": "Container",
                "items": items,
                "style": color.lower() if color in ("Attention", "Warning") else "default",
                "spacing": "Medium",
            }
        )

    # Timestamp
    body.append(
        {
            "type": "TextBlock",
            "text": _sent_at(t),
            "wrap": True,
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium",
        }
    )

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }

    # Dashboard action button
    if dashboard_url:
        card["actions"] = [
            {
                "type": "Action.OpenUrl",
                "title": str(t.alert_open_dashboard),
                "url": dashboard_url,
            }
        ]

    return card


# ── Slack blocks builder ────────────────────────────────────────────────────

_SLACK_EMOJI = {
    "critical": ":red_circle:",
    "warning": ":large_yellow_circle:",
    "info": ":large_blue_circle:",
}


def _build_slack_payload(
    title: str,
    alerts: list[dict],
    *,
    subtitle: str = "",
    facts: list[tuple[str, str]] | None = None,
    dashboard_url: str = "",
    lang: str = "no",
) -> dict:
    """Build Slack blocks instead of flat text."""
    t = _labels(lang)
    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
    ]

    if subtitle:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": subtitle}],
            }
        )

    # KPI fields
    if facts:
        fields = [{"type": "mrkdwn", "text": f"*{k}:* {v}"} for k, v in facts[:10]]
        blocks.append({"type": "section", "fields": fields})

    blocks.append({"type": "divider"})

    for group, label, severity in _severity_groups(alerts, t):
        if not group:
            continue

        lines = [f"{_SLACK_EMOJI[severity]} *{label} ({len(group)})*"]
        for a in group[:15]:
            customer = _slack_escape(a.get("customer", ""))
            item = _slack_escape(a.get("item", ""))
            detail = _slack_escape(a.get("detail", ""))
            line = f"• *{customer}* — {item}: {detail}"
            rec = a.get("recommendation") or a.get("remediation")
            if rec:
                line += f"\n   _💡 {_slack_escape(rec)}_"
            lines.append(line)

        if len(group) > 15:
            lines.append(f"_{t('alert_and_more', count=len(group) - 15)}_")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(lines)},
            }
        )

    # Timestamp + dashboard link
    ctx_elements: list[dict] = [{"type": "mrkdwn", "text": _sent_at(t)}]
    if dashboard_url:
        ctx_elements.append(
            {"type": "mrkdwn", "text": f"<{dashboard_url}|{_slack_escape(t.alert_open_dashboard)}>"}
        )
    blocks.append({"type": "context", "elements": ctx_elements})

    return {"blocks": blocks}


# ── Plain text fallback ─────────────────────────────────────────────────────


def _build_plain_text(
    title: str,
    alerts: list[dict],
    *,
    facts: list[tuple[str, str]] | None = None,
    lang: str = "no",
) -> str:
    """Build plain text for generic webhooks."""
    t = _labels(lang)
    lines = [title, ""]
    if facts:
        for k, v in facts:
            lines.append(f"  {k}: {v}")
        lines.append("")

    for a in alerts[:30]:
        emoji = _severity_emoji(a.get("severity", ""))
        line = f"{emoji} [{a.get('customer', '')}] {a.get('item', '')}: {a.get('detail', '')}"
        rec = a.get("recommendation") or a.get("remediation")
        if rec:
            line += f"\n   💡 {rec}"
        lines.append(line)

    if len(alerts) > 30:
        lines.append(str(t("alert_and_more", count=len(alerts) - 30)))
    return "\n".join(lines)


# ── Public API ──────────────────────────────────────────────────────────────


async def send_webhook(
    webhook_url: str,
    title: str,
    alerts: list[dict],
    *,
    subtitle: str = "",
    facts: list[tuple[str, str]] | None = None,
    dashboard_url: str = "",
    lang: str = "no",
) -> bool:
    """Send a rich notification to Teams, Slack, or generic webhook.

    Args:
        webhook_url: The incoming webhook URL.
        title: Notification title / header.
        alerts: List of alert dicts. Expected keys:
            type, severity, customer, item, detail, recommendation? (optional)
        subtitle: Optional second line under the title.
        facts: Optional KPI list of (label, value) tuples for the FactSet / fields.
        dashboard_url: Optional link to the dashboard (rendered as action button).
        lang: The language of the card's own words (severity headings, "sent",
            the button). They were Norwegian whatever the hub was set to.

    Returns True if the webhook responded 2xx, False otherwise.
    """
    if not webhook_url or not alerts:
        return False

    wh_type = _detect_type(webhook_url)

    if wh_type == "slack":
        payload = _build_slack_payload(
            title, alerts, subtitle=subtitle, facts=facts, dashboard_url=dashboard_url, lang=lang
        )
    elif wh_type in ("teams", "power_automate"):
        card = _build_adaptive_card(
            title, alerts, subtitle=subtitle, facts=facts, dashboard_url=dashboard_url, lang=lang
        )
        if wh_type == "power_automate":
            payload = card
        else:
            payload = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card,
                    }
                ],
            }
    else:
        text = _build_plain_text(title, alerts, facts=facts, lang=lang)
        payload = {"text": text}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            if not resp.is_success:
                logger.warning(
                    "Webhook failed (%s): %d %s",
                    wh_type,
                    resp.status_code,
                    resp.text[:300],
                )
                return False
            return True
    except Exception as exc:
        logger.error("Webhook error (%s): %s", wh_type, exc)
        return False


async def send_simple_message(webhook_url: str, message: str) -> bool:
    """Send literal text; tenant names and exceptions cannot create links or mentions."""
    if not webhook_url:
        return False

    wh_type = _detect_type(webhook_url)

    if wh_type in ("teams", "power_automate"):
        body = [
            _literal(
                line.strip(),
                weight="Bolder" if i == 0 else "Default",
                size="Medium" if i == 0 else "Default",
                spacing="None" if i > 0 else "Default",
            )
            for i, line in enumerate(message.split("\n"))
            if line.strip()
        ]
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body,
        }
        if wh_type == "power_automate":
            payload = card
        else:
            payload = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card,
                    }
                ],
            }
    elif wh_type == "slack":
        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "plain_text", "text": message, "emoji": False},
                }
            ],
        }
    else:
        payload = {"text": message}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            if not resp.is_success:
                logger.warning("Webhook failed: %d %s", resp.status_code, resp.text[:200])
                return False
            return True
    except Exception as exc:
        logger.error("Webhook error: %s", exc)
        return False
