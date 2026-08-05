"""Retry the calls that are safe to retry, and raise when they run out.

GraphClient has waited on Retry-After and backed off since it was written, and
it earns that on every audit — a busy tenant throttles hard enough that the
sign-in section alone can spend a minute in 429s. The write-side clients had
nothing. A throttled IT Glue upload returned an empty result and the audit
carried on, which reads exactly like "there was nothing to upload".

Two rules, and the second is the one worth stating:

**429 is always safe.** The request was refused before it was processed, so
repeating it changes nothing but the timing, whatever the method.

**5xx is not.** The server may have applied a write and then failed on the way
out. Repeating a POST that already created an IT Glue document creates a
second one, and nobody reconciles those. So 5xx is retried for GET alone, and
a write that fails that way fails once and says so.

Retry-After is honoured when the server sends it. Guessing a backoff while
being told the number is how a client gets throttled twice for one mistake.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_MAX_BACKOFF = 30.0


class RetryExhausted(Exception):
    """Every attempt was throttled or failed.

    Its own type so a caller cannot mistake it for an empty result. That
    mistake is the reason this module exists.
    """

    def __init__(self, target: str, attempts: int, last_status: int | None):
        self.target = target
        self.attempts = attempts
        self.last_status = last_status
        super().__init__(
            f"{target} failed after {attempts} attempts "
            f"(last status: {last_status})"
        )


def _backoff(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait. The server's own figure wins when it gives one."""
    if retry_after:
        try:
            # Retry-After is seconds in every API here; an HTTP-date form
            # would parse as garbage, so fall through to the computed value.
            return min(float(int(retry_after)), _MAX_BACKOFF)
        except (TypeError, ValueError):
            pass
    # Jittered, because several sections hit the same API at once and a fixed
    # backoff just re-synchronises them into the next wall.
    return min(2 ** attempt + random.uniform(0, 1), _MAX_BACKOFF)


async def send_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
    *,
    method: str,
    target: str,
    attempts: int = _MAX_ATTEMPTS,
) -> httpx.Response:
    """Run ``send`` until it gives an answer worth returning.

    ``send`` is a zero-argument coroutine factory so the request is rebuilt
    each time rather than a spent one being replayed.

    Returns the response for anything that is not retryable — including 4xx,
    which the caller still has to check. Raises RetryExhausted when the
    attempts run out.
    """
    idempotent = method.upper() in ("GET", "HEAD", "OPTIONS")
    last_status: int | None = None

    for attempt in range(attempts):
        try:
            resp = await send()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # A connection that never opened carries no risk of a half-applied
            # write, so this one is safe for any method.
            last_status = None
            if attempt == attempts - 1:
                raise RetryExhausted(target, attempts, None) from exc
            wait = _backoff(attempt, None)
            logger.warning("%s unreachable (%s) — retrying in %.1fs", target, type(exc).__name__, wait)
            await asyncio.sleep(wait)
            continue

        last_status = resp.status_code

        if resp.status_code == 429:
            if attempt == attempts - 1:
                break
            wait = _backoff(attempt, resp.headers.get("Retry-After"))
            logger.warning("%s throttled — waiting %.1fs", target, wait)
            await asyncio.sleep(wait)
            continue

        if resp.status_code >= 500 and idempotent:
            if attempt == attempts - 1:
                break
            wait = _backoff(attempt, resp.headers.get("Retry-After"))
            logger.warning("%s answered %d — retrying in %.1fs", target, resp.status_code, wait)
            await asyncio.sleep(wait)
            continue

        return resp

    raise RetryExhausted(target, attempts, last_status)
