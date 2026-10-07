"""Read cooldown shared by clients for the same tenant on one event loop."""

from __future__ import annotations

import asyncio
import time
import weakref
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

MAX_WAIT_SECONDS = 120.0


class GraphThrottledError(httpx.HTTPError):
    """A bounded read could not resume; its data is unavailable, not empty."""


def retry_delay(header: str | None, attempt: int) -> float:
    """Accept delta seconds or HTTP dates, with backoff for invalid headers."""
    if header:
        try:
            seconds = int(header)
            if seconds >= 0:
                return float(seconds)
        except (ValueError, OverflowError):
            pass
        try:
            when = parsedate_to_datetime(header)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0.0, (when - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return float(min(2**attempt, 30))


class ReadCooldown:
    def __init__(self) -> None:
        self.until = 0.0

    def defer(self, seconds: float) -> None:
        # A later response may extend the cooldown but never shorten it.
        self.until = max(self.until, time.monotonic() + seconds)

    async def wait(self, deadline: float) -> None:
        while (remaining := self.until - time.monotonic()) > 0:
            budget = deadline - time.monotonic()
            if remaining > budget:
                raise GraphThrottledError(
                    "Graph read unavailable: tenant cooldown exceeds the bounded wait"
                )
            await asyncio.sleep(remaining)


# Weak values disappear when the last client closes. Neither old tenants nor
# completed test/server loops are retained indefinitely. No cross-loop locks.
_COOLDOWNS: weakref.WeakValueDictionary[tuple[asyncio.AbstractEventLoop, str], ReadCooldown] = (
    weakref.WeakValueDictionary()
)


def tenant_cooldown(tenant_id: str) -> ReadCooldown:
    key = (asyncio.get_running_loop(), tenant_id.lower())
    cooldown = _COOLDOWNS.get(key)
    if cooldown is None:
        cooldown = ReadCooldown()
        _COOLDOWNS[key] = cooldown
    return cooldown
