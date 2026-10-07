"""Transport-neutral state for audit/setup jobs and their subscribers.

This module centralises the global variables that were previously scattered
across server.py.  Route modules import from here instead of keeping their
own copies.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

# ── Audit scheduling state ──────────────────────────────────────────────
# This flag serialises manual and scheduled collection. Result data must never
# be stored here: authenticated users have separate run contexts below.
audit_running: bool = False
setup_running: bool = False
bulk_audit_running: bool = False
audit_lock = asyncio.Lock()
setup_lock = asyncio.Lock()


@dataclass
class AuditRunContext:
    """The latest report-capable audit run selected by one web user.

    The run is owned by the server, not by the browser that started it. The
    collector runs as a background task that publishes progress here and writes
    its results on completion whether or not a stream is still connected — a
    dropped connection is a lost *view*, not a lost run. A reconnecting client
    re-subscribes and is replayed the current state.
    """

    owner_user_id: str
    customer_id: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    customer_name: str = ""
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
    # The final event (done/error/cancelled), kept so a client that attaches
    # *after* the run has finished still learns the outcome instead of hanging.
    terminal: dict | None = None
    # Live subscribers (one asyncio.Queue per connected stream) and the running
    # collector task. Runtime plumbing, not data: kept out of repr and equality.
    _subscribers: set = field(default_factory=set, repr=False, compare=False)
    task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def subscribe(self) -> asyncio.Queue:
        """Register a live subscriber; the caller drains it and unsubscribes."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        """Fan an event out to every current subscriber.

        A terminal event is also remembered, so a subscriber that attaches after
        the run has finished is replayed the outcome. Publishing with no
        subscribers is fine — the job keeps running and saving regardless, which
        is the whole point of moving the run off the stream.
        """
        if event.get("type") in ("done", "error", "cancelled"):
            self.terminal = event
        for q in list(self._subscribers):
            q.put_nowait(event)


# Server-owned collection and legacy API selections are per user and customer.
# Browser history selections additionally carry a per-document identity below.
_user_audit_runs: dict[tuple[str, str], AuditRunContext] = {}

# A tab's history choice is separate from the server-owned collecting run.
# The authenticated user and customer remain part of the key: the opaque tab
# header selects a view, never grants access. Bound memory to 32 selections per
# user; an evicted tab gets the collecting/latest run until it selects again.
request_audit_tab: ContextVar[str] = ContextVar("request_audit_tab", default="")
_tab_audit_runs: OrderedDict[tuple[str, str, str], AuditRunContext] = OrderedDict()


def _select_tab(run: AuditRunContext) -> None:
    tab = request_audit_tab.get()
    if not tab:
        return
    key = (run.owner_user_id, run.customer_id, tab)
    _tab_audit_runs[key] = run
    _tab_audit_runs.move_to_end(key)
    owned = [k for k in _tab_audit_runs if k[0] == run.owner_user_id]
    for old in owned[:-32]:
        del _tab_audit_runs[old]


def begin_user_audit(user_id: str, customer_id: str) -> AuditRunContext:
    """Create and select a fresh running context for one user and customer."""
    run = AuditRunContext(owner_user_id=user_id, customer_id=customer_id, running=True)
    _user_audit_runs[(user_id, customer_id)] = run
    _select_tab(run)
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
    if request_audit_tab.get():
        _select_tab(run)
    else:
        _user_audit_runs[(user_id, customer_id)] = run
    return run


def get_user_audit(user_id: str, customer_id: str) -> AuditRunContext | None:
    """Return this user's selected run for exactly this customer."""
    collecting = _user_audit_runs.get((user_id, customer_id))
    if collecting and collecting.running:
        return collecting
    tab = request_audit_tab.get()
    if tab:
        selected = _tab_audit_runs.get((user_id, customer_id, tab))
        if selected is not None:
            return selected
    return collecting


def get_running_user_audit(user_id: str) -> AuditRunContext | None:
    """The audit this user has running, whichever customer it is for.

    Collection is serialised server-wide (``audit_running``), so there is at
    most one. Cancelling and the header's progress follow the run's owner, not
    a customer the caller happens to be looking at.
    """
    for (owner, _customer), run in _user_audit_runs.items():
        if owner == user_id and run.running:
            return run
    return None


def clear_user_audits() -> None:
    """Test/shutdown helper; never use it to switch customers."""
    _user_audit_runs.clear()
    _tab_audit_runs.clear()


# ── First-run setup state ────────────────────────────────────────────────
# Setup is a singleton (one at a time, guarded by setup_running). Like the
# audit, the run is server-owned: the PowerShell device-code sign-in and the
# cert/credential write run as a background task that finishes and *persists*
# regardless of the browser, and a reconnecting client re-attaches to it. The
# old flow ran it inside the SSE stream, so a disconnect mid-sign-in tore it
# down before the credentials were written.


@dataclass
class SetupRunContext:
    """A first-run setup owned by the server, not the browser that started it."""

    running: bool = False
    # The latest device-code prompt, replayed to a client that re-attaches so it
    # can still complete the Microsoft sign-in after a dropped connection.
    device_code: dict | None = None
    terminal: dict | None = None  # the final {"type": "done", "success": bool}
    _subscribers: set = field(default_factory=set, repr=False, compare=False)
    task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        """Fan an event out; remember the device-code and terminal ones so a
        client that attaches later is replayed both (the code to finish signing
        in, the outcome to stop waiting)."""
        if event.get("type") == "device_code":
            self.device_code = event
        if event.get("type") == "done":
            self.terminal = event
        for q in list(self._subscribers):
            q.put_nowait(event)


_setup_run: SetupRunContext | None = None


def begin_setup() -> SetupRunContext:
    """Create and select a fresh running setup context."""
    global _setup_run
    _setup_run = SetupRunContext(running=True)
    return _setup_run


def get_setup_run() -> SetupRunContext | None:
    return _setup_run
