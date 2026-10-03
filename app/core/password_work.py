"""Bound expensive password work without blocking the ASGI event loop."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import ToolkitError

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sybr-password")
_admission = threading.BoundedSemaphore(8)


class PasswordServiceBusy(ToolkitError):
    status_code = 503
    error_type = "authentication_busy"


async def run_password_work(function, *args):
    if not _admission.acquire(blocking=False):
        raise PasswordServiceBusy("Innlogging er opptatt. Prøv igjen om litt.")
    try:
        future = _executor.submit(function, *args)
    except BaseException:
        _admission.release()
        raise
    # concurrent.futures only cancels queued work. A disconnected request must
    # retain its slot until an already-running Argon2 operation really finishes.
    future.add_done_callback(lambda _: _admission.release())
    return await asyncio.wrap_future(future)
