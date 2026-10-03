"""In-process revocation notifications, independent of HTTP and WebSockets.

The supported deployment has one worker. Consumers also revalidate persisted
state so expiry and out-of-process administration cannot retain live access.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(eq=False)
class Watch:
    user_id: str
    session_id: str | None
    token_hash: str
    loop: asyncio.AbstractEventLoop
    event: asyncio.Event
    revoked: bool = False


_lock = threading.Lock()
_watches: set[Watch] = set()


@contextmanager
def watch(user_id: str, session_id: str | None, token_hash: str):
    item = Watch(user_id, session_id, token_hash, asyncio.get_running_loop(), asyncio.Event())
    with _lock:
        _watches.add(item)
    try:
        yield item
    finally:
        with _lock:
            _watches.discard(item)


def invalidate(
    *, user_id: str | None = None, session_id: str | None = None, token_hash: str | None = None
) -> None:
    """Stop subscribers before their next operation, including across test loops."""
    with _lock:
        for item in _watches:
            if (
                (user_id is not None and item.user_id == user_id)
                or (session_id is not None and item.session_id == session_id)
                or (token_hash is not None and item.token_hash == token_hash)
            ):
                item.revoked = True
                if not item.loop.is_closed():
                    item.loop.call_soon_threadsafe(item.event.set)
