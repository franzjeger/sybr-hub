"""Background notifications in the configured Hub language, as plain text."""

from __future__ import annotations

from typing import Any

from app.core.config import load_app_settings
from app.reports.i18n import T, format_date


def _hub_language(settings: dict[str, Any]) -> str:
    lang = settings.get("ui_language", "no")
    return lang if lang in ("no", "en") else "no"


def notification_text(key: str, *, settings: dict[str, Any] | None = None, **params: object) -> str:
    settings = load_app_settings() if settings is None else settings
    return str(T(_hub_language(settings))(key, **params))


def notification_date(value: object, *, settings: dict[str, Any] | None = None) -> str:
    """A day ("2026-10-08") in a notification, written as the Hub's language writes it."""
    settings = load_app_settings() if settings is None else settings
    return format_date(value, _hub_language(settings))


def bulk_audit_message(summary: list[dict[str, Any]], total: int, parallel: int) -> str:
    settings = load_app_settings()

    def word(key: str, **params: object) -> str:
        return notification_text(key, settings=settings, **params)

    completed = sum(item.get("status") == "done" for item in summary)
    lines = [word("background_bulk_done", done=completed, total=total, parallel=parallel)]
    for item in summary:
        name = item["customer"]
        if item.get("status") == "done":
            lines.append(
                word(
                    "background_bulk_customer",
                    customer=name,
                    grade=item.get("grade", "-"),
                    score=item.get("risk_score", 0),
                )
            )
        elif item.get("status") == "error":
            lines.append(
                word(
                    "background_audit_failed",
                    customer=name,
                    error=item.get("error") or word("background_unknown_error"),
                )
            )
        elif item.get("status") == "skipped":
            lines.append(word("background_customer_skipped", customer=name))
    return "\n".join(lines)
