"""Evidence for stored integration credentials; never a live availability promise."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import update_app_settings

# Every field that changes the account or endpoint invalidates its check.
FIELDS: dict[str, tuple[str, ...]] = {
    "itglue": ("itglue_api_key", "itglue_region"),
    "autotask": (
        "autotask_integration_code",
        "autotask_username",
        "autotask_secret",
        "autotask_zone_url",
    ),
    "myitprocess": ("myitprocess_api_key", "myitprocess_base_url"),
    "also": ("also_username", "also_password", "also_country"),
    "tailscale": ("tailscale_api_key", "tailscale_tailnet"),
    "email": ("smtp_server", "smtp_port", "smtp_user", "smtp_password", "smtp_from"),
}
DEFAULTS: dict[str, Any] = {
    "itglue_region": "eu",
    "also_country": "no",
    "tailscale_tailnet": "-",
    "smtp_port": 587,
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "itglue": ("itglue_api_key",),
    "autotask": ("autotask_integration_code", "autotask_username", "autotask_secret"),
    "myitprocess": ("myitprocess_api_key",),
    "also": ("also_username", "also_password"),
    "tailscale": ("tailscale_api_key",),
    "email": ("smtp_server",),
}


def fingerprint(provider: str, settings: dict[str, Any]) -> str:
    payload = [settings.get(key, DEFAULTS.get(key, "")) for key in FIELDS[provider]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def record_check(provider: str, tested: dict[str, Any], ok: bool) -> None:
    """Record only the configuration actually tested, under the settings lock."""
    stamp = datetime.now(UTC).isoformat()
    checked = fingerprint(provider, tested)

    def mutate(settings: dict[str, Any]) -> None:
        if fingerprint(provider, settings) == checked:
            settings["integration_check_" + provider] = {
                "fingerprint": checked,
                "ok": ok,
                "checked_at": stamp,
            }

    update_app_settings(mutate)


def integration_health(
    settings: dict[str, Any], *, now: datetime | None = None
) -> dict[str, dict[str, Any]]:
    """Expose no credentials or hashes. Checks expire after 24 hours."""
    now = now or datetime.now(UTC)
    out: dict[str, dict[str, Any]] = {}
    for provider in FIELDS:
        state = "configured" if all(settings.get(key) for key in REQUIRED[provider]) else "off"
        check = settings.get("integration_check_" + provider)
        checked_at = None
        if (
            state != "off"
            and isinstance(check, dict)
            and check.get("fingerprint") == fingerprint(provider, settings)
        ):
            try:
                checked = datetime.fromisoformat(check["checked_at"])
                if checked.tzinfo is None or checked > now:
                    raise ValueError("Invalid check timestamp")
                checked_at = checked.isoformat()
                state = "verified" if check.get("ok") is True else "failed"
                if now - checked >= timedelta(hours=24):
                    state = "stale"
            except (KeyError, TypeError, ValueError):
                pass
        out[provider] = {"state": state, "checked_at": checked_at}
    return out
