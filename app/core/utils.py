"""Shared utility functions used across multiple modules."""

from __future__ import annotations

import asyncio
from typing import Coroutine

_bg_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro: Coroutine) -> asyncio.Task:
    """Schedule a background task and keep a strong reference until it finishes.

    asyncio only weakly references tasks created by ``create_task``, so without
    a strong reference the task can be garbage-collected mid-flight (RUF006).
    """
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def format_uptime(seconds: int | float) -> str:
    """Format seconds into a human-readable uptime string.

    Examples: "5d 3t", "12t 45m", "23m"
    """
    secs = int(seconds)
    if secs <= 0:
        return "0m"
    days = secs // 86400
    hours = (secs % 86400) // 3600
    minutes = (secs % 3600) // 60
    if days > 0:
        return f"{days}d {hours}t"
    if hours > 0:
        return f"{hours}t {minutes}m"
    return f"{minutes}m"
