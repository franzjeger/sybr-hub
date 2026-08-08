"""Shared mutable state for the MSP Toolkit web server.

This module centralises the global variables that were previously scattered
across server.py.  Route modules import from here instead of keeping their
own copies.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# ── Audit scheduling state ──────────────────────────────────────────────
# This flag serialises manual and scheduled collection. Result data must never
# be stored here: authenticated users have separate run contexts below.
audit_running: bool = False
setup_running: bool = False
bulk_audit_running: bool = False
audit_lock = asyncio.Lock()


@dataclass
class AuditRunContext:
    """The latest report-capable audit run selected by one web user."""

    owner_user_id: str
    customer_id: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    running: bool = False
    cancel_requested: bool = False
    results: list[dict] = field(default_factory=list)
    out_dir: Path | None = None
    progress: dict = field(
        default_factory=lambda: {
            "progress": 0,
            "current_section": "",
            "total_sections": 0,
            "completed": 0,
        }
    )


# One latest selection per user bounds memory while keeping result data out of
# every other user's request. A new audit or explicit history load replaces it.
_user_audit_runs: dict[str, AuditRunContext] = {}


def begin_user_audit(user_id: str, customer_id: str) -> AuditRunContext:
    """Create and select a fresh running context for one authenticated user."""
    run = AuditRunContext(owner_user_id=user_id, customer_id=customer_id, running=True)
    _user_audit_runs[user_id] = run
    return run


def select_user_audit(
    user_id: str,
    customer_id: str,
    *,
    out_dir: Path,
    results: list[dict],
) -> AuditRunContext:
    """Select a completed or historical run for report operations."""
    run = AuditRunContext(
        owner_user_id=user_id,
        customer_id=customer_id,
        results=results,
        out_dir=out_dir,
    )
    _user_audit_runs[user_id] = run
    return run


def get_user_audit(user_id: str, customer_id: str | None = None) -> AuditRunContext | None:
    """Return only this user's selected run, optionally for an exact customer."""
    run = _user_audit_runs.get(user_id)
    if run is None or (customer_id is not None and run.customer_id != customer_id):
        return None
    return run


def clear_user_audits() -> None:
    """Test/shutdown helper; never use it to switch customers."""
    _user_audit_runs.clear()
