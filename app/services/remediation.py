"""Per-customer remediation tracking.

Records which audit recommendations an operator has actioned, so a report
can show progress since the previous run rather than repeating the same
findings verbatim. Backed by the ``remediation_items`` table (migration 8).

Both a sync and an async accessor exist: the report generator runs
synchronously inside WeasyPrint's render path, while the web routes are
async.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from app.core import database
from app.core.database import get_db

log = logging.getLogger(__name__)

VALID_STATUSES = frozenset({"open", "in_progress", "done", "ignored"})


def _row_to_entry(row) -> dict:
    return {
        "status": row["status"],
        "notes": row["notes"] or "",
        "updated_by": row["assigned_to"] or "",
        "updated_date": row["updated_at"] or "",
    }


def load_remediation_sync(customer_id: str) -> dict[str, dict]:
    """Return ``{recommendation_id: entry}`` for one customer.

    Synchronous by design — called from the report generator, which is not
    async. Read-only, so a short-lived sqlite3 connection is enough; failures
    are non-fatal because a report without remediation data is still useful.
    """
    # Read database.DB_PATH at call time — it is reassigned by tests and by
    # MSP_DATA_DIR, so a module-level import would freeze the wrong path.
    db_path = database.DB_PATH
    if not customer_id or not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT recommendation_id, status, notes, assigned_to, updated_at "
                "FROM remediation_items WHERE customer_id = ?",
                (customer_id,),
            )
            return {row["recommendation_id"]: _row_to_entry(row) for row in cur.fetchall()}
        finally:
            conn.close()
    except sqlite3.Error as e:
        log.warning("Could not load remediation data for %s: %s", customer_id, e)
        return {}


async def load_remediation(customer_id: str) -> dict[str, dict]:
    """Async counterpart of :func:`load_remediation_sync`."""
    async with get_db() as conn, conn.execute(
        "SELECT recommendation_id, status, notes, assigned_to, updated_at "
        "FROM remediation_items WHERE customer_id = ?",
        (customer_id,),
    ) as cur:
        rows = await cur.fetchall()
    return {row["recommendation_id"]: _row_to_entry(row) for row in rows}


async def set_remediation(
    customer_id: str,
    recommendation_id: str,
    status: str,
    notes: str = "",
    assigned_to: str | None = None,
) -> dict:
    """Create or update one remediation entry. Returns the stored entry."""
    from app.core.exceptions import ValidationError

    if status not in VALID_STATUSES:
        raise ValidationError(
            f"Ugyldig status '{status}' — må være en av: {', '.join(sorted(VALID_STATUSES))}"
        )
    if not customer_id or not recommendation_id:
        raise ValidationError("customer_id og recommendation_id er påkrevd")

    now = datetime.now(UTC).isoformat()
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO remediation_items
                   (customer_id, recommendation_id, status, notes, assigned_to,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(customer_id, recommendation_id) DO UPDATE SET
                   status      = excluded.status,
                   notes       = excluded.notes,
                   assigned_to = excluded.assigned_to,
                   updated_at  = excluded.updated_at""",
            (customer_id, recommendation_id, status, notes, assigned_to or "", now, now),
        )
        await conn.commit()

    return {
        "status": status,
        "notes": notes,
        "updated_by": assigned_to or "",
        "updated_date": now,
    }


async def clear_remediation(customer_id: str, recommendation_id: str) -> bool:
    """Delete one entry. Returns True if a row was removed."""
    async with get_db() as conn:
        cur = await conn.execute(
            "DELETE FROM remediation_items WHERE customer_id = ? AND recommendation_id = ?",
            (customer_id, recommendation_id),
        )
        await conn.commit()
        return cur.rowcount > 0
