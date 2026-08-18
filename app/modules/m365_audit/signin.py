"""Shared sign-in-recency logic for the M365 audit sections.

``signInActivity`` carries two timestamps: ``lastSignInDateTime`` (interactive)
and ``lastNonInteractiveSignInDateTime``. An account used daily from an
already-signed-in client keeps producing non-interactive sign-ins but no NEW
interactive ones, so keying on the interactive date — or taking non-interactive
only as a null fallback — reports a plainly-active account as long-idle. That one
mistake over-counted stale licences, mis-flagged break-glass admins, and printed
stale "last sign-in" dates in three different sections (M365 review). The correct
signal is the LATER of the two, computed here once so the three call sites cannot
drift apart again.
"""

from __future__ import annotations

from datetime import datetime


def latest_signin(activity: dict | None) -> datetime | None:
    """The most recent of interactive and non-interactive sign-in, or None.

    None when ``signInActivity`` is absent (tenants without Entra ID P1/P2) or
    neither timestamp parses — callers treat that as "no evidence of recent use".
    """
    latest: datetime | None = None
    for key in ("lastSignInDateTime", "lastNonInteractiveSignInDateTime"):
        raw = (activity or {}).get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest
