"""Evidence quality for dashboard measurements; unknown never means passed."""

import re
from datetime import UTC, datetime
from typing import Literal

EvidenceState = Literal["passed", "failed", "unknown", "stale", "not_applicable"]
_FIRMWARE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:[, -].*)?", re.I)


def source_age(observed_at: str | None, now: datetime) -> int | None:
    if not observed_at:
        return None
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        days = (now - observed).days
        return days if days >= 0 else None
    except (ValueError, TypeError):
        return None


def firmware_assessment(version: str | None) -> dict[str, str | None]:
    """Parsing is metadata, not proof of support or absence of advisories.

    No maintained model-specific vendor policy is available in this project.
    Keep that uncertainty visible until such a policy is supplied.
    """
    match = _FIRMWARE.fullmatch(version or "")
    return {
        "state": "unknown",
        "parsed_version": ".".join(match.groups()) if match else None,
        "reason": "no_vendor_policy" if match else "unrecognised_version",
    }
