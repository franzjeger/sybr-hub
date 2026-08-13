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

**A transport error is whichever of those two the timing makes it.** This
module used to retry every transport failure for every method, on the reasoning
that a connection which never opened cannot have applied a write. That
reasoning is right and the code did not implement it: ``httpx.TimeoutException``
covers ``ReadTimeout`` as well as ``ConnectTimeout``, and a read timeout means
the request *was* sent and the answer never came back. Retrying a device
configuration write after one is how a firewall gets the same change twice.

So transport errors are split by whether the request can have reached the
server. ``ConnectTimeout``, ``ConnectError`` and ``PoolTimeout`` happen before
anything is sent and stay safe for any method. Everything else — read and write
timeouts, protocol errors, a proxy that gave up mid-flight — is treated like a
5xx: retried for idempotent methods, raised once for the rest. It matters more
now than when this was written, because the FortiGate and UniFi clients push
configuration through here.

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

# Transport failures that happen before any byte of the request leaves. Only
# these are safe to repeat for a method that changes something.
#
# Deliberately a tuple of concrete classes rather than a base: httpx's
# hierarchy puts ConnectTimeout and ReadTimeout under one TimeoutException, and
# catching the base is exactly the mistake this replaces. PoolTimeout is
# waiting for a free connection, so nothing has been sent either.
_PRE_SEND_ERRORS = (httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout)


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
        except httpx.TransportError as exc:
            # Safe for any method only when nothing can have been sent yet.
            # A read timeout is the dangerous one: the request went out and the
            # answer did not come back, so the server may well have applied it.
            unsent = isinstance(exc, _PRE_SEND_ERRORS)
            last_status = None
            if not (unsent or idempotent):
                logger.warning(
                    "%s failed after the request went out (%s) — not retrying a %s",
                    target, type(exc).__name__, method.upper(),
                )
                raise RetryExhausted(target, attempt + 1, None) from exc
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
