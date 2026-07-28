"""Shared webhook sender — rich formatting for Teams, Slack, and generic webhooks.

Replaces the duplicated webhook logic in alert_engine.py and scheduler.py.
Builds proper Adaptive Cards (Teams/Power Automate) and Slack blocks
instead of flat text.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

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


def _build_adaptive_card(
    title: str,
    alerts: list[dict],
    *,
    subtitle: str = "",
    facts: list[tuple[str, str]] | None = None,
    dashboard_url: str = "",
) -> dict:
    """Build a rich Adaptive Card for Teams / Power Automate.

    Alert dict shape: {type, severity, customer, item, detail, recommendation?}
    """
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

    # Group alerts by severity
    critical = [a for a in alerts if a.get("severity") == "critical"]
    warnings = [a for a in alerts if a.get("severity") == "warning"]
    info = [a for a in alerts if a.get("severity") not in ("critical", "warning")]

    for group, label, color in [
        (critical, "Kritisk", "Attention"),
        (warnings, "Advarsel", "Warning"),
        (info, "Info", "Accent"),
    ]:
        if not group:
            continue

        items: list[dict] = [
            {
                "type": "TextBlock",
                "text": f"{_severity_emoji(group[0]['severity'])} **{label} ({len(group)})**",
                "wrap": True,
                "weight": "Bolder",
                "size": "Small",
            }
        ]

        for a in group[:15]:
            # Two-column: customer | item + detail
            cols: list[dict] = [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"**{a.get('customer', '')}**",
                            "wrap": True,
                            "size": "Small",
                        }
                    ],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"{a.get('item', '')}: {a.get('detail', '')}",
                            "wrap": True,
                            "size": "Small",
                            "isSubtle": True,
                        }
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

            # Recommendation line (if present)
            rec = a.get("recommendation") or a.get("remediation")
            if rec:
                items.append(
                    {
                        "type": "TextBlock",
                        "text": f"💡 {rec}",
                        "wrap": True,
                        "size": "Small",
                        "isSubtle": True,
                        "spacing": "None",
                    }
                )

        if len(group) > 15:
            items.append(
                {
                    "type": "TextBlock",
                    "text": f"_...og {len(group) - 15} flere_",
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
            "text": f"Sendt {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
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
                "title": "Åpne dashboard",
                "url": dashboard_url,
            }
        ]

    return card


# ── Slack blocks builder ────────────────────────────────────────────────────


def _build_slack_payload(
    title: str,
    alerts: list[dict],
    *,
    subtitle: str = "",
    facts: list[tuple[str, str]] | None = None,
    dashboard_url: str = "",
) -> dict:
    """Build Slack blocks instead of flat text."""
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

    # Grouped alerts
    critical = [a for a in alerts if a.get("severity") == "critical"]
    warnings = [a for a in alerts if a.get("severity") == "warning"]
    info = [a for a in alerts if a.get("severity") not in ("critical", "warning")]

    for group, emoji, label in [
        (critical, ":red_circle:", "Kritisk"),
        (warnings, ":large_yellow_circle:", "Advarsel"),
        (info, ":large_blue_circle:", "Info"),
    ]:
        if not group:
            continue

        lines = [f"{emoji} *{label} ({len(group)})*"]
        for a in group[:15]:
            line = f"• *{a.get('customer', '')}* — {a.get('item', '')}: {a.get('detail', '')}"
            rec = a.get("recommendation") or a.get("remediation")
            if rec:
                line += f"\n   _💡 {rec}_"
            lines.append(line)

        if len(group) > 15:
            lines.append(f"_...og {len(group) - 15} flere_")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(lines)},
            }
        )

    # Timestamp + dashboard link
    ctx_elements: list[dict] = [
        {
            "type": "mrkdwn",
            "text": f"Sendt {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        }
    ]
    if dashboard_url:
        ctx_elements.append(
            {"type": "mrkdwn", "text": f"<{dashboard_url}|Åpne dashboard>"}
        )
    blocks.append({"type": "context", "elements": ctx_elements})

    return {"blocks": blocks}


# ── Plain text fallback ─────────────────────────────────────────────────────


def _build_plain_text(
    title: str,
    alerts: list[dict],
    *,
    facts: list[tuple[str, str]] | None = None,
) -> str:
    """Build plain text for generic webhooks."""
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
        lines.append(f"...og {len(alerts) - 30} flere")
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

    Returns True if the webhook responded 2xx, False otherwise.
    """
    if not webhook_url or not alerts:
        return False

    wh_type = _detect_type(webhook_url)

    if wh_type == "slack":
        payload = _build_slack_payload(
            title, alerts, subtitle=subtitle, facts=facts, dashboard_url=dashboard_url
        )
    elif wh_type in ("teams", "power_automate"):
        card = _build_adaptive_card(
            title, alerts, subtitle=subtitle, facts=facts, dashboard_url=dashboard_url
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
        text = _build_plain_text(title, alerts, facts=facts)
        payload = {"text": text}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
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
    """Send a simple text message (for test messages, audit-completed, etc.)."""
    if not webhook_url:
        return False

    wh_type = _detect_type(webhook_url)

    if wh_type in ("teams", "power_automate"):
        body = [
            {
                "type": "TextBlock",
                "text": line.strip(),
                "wrap": True,
                "weight": "Bolder" if i == 0 else "Default",
                "size": "Medium" if i == 0 else "Default",
                "spacing": "None" if i > 0 else "Default",
            }
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
                    "text": {"type": "mrkdwn", "text": message},
                }
            ],
        }
    else:
        payload = {"text": message}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                logger.warning("Webhook failed: %d %s", resp.status_code, resp.text[:200])
                return False
            return True
    except Exception as exc:
        logger.error("Webhook error: %s", exc)
        return False
