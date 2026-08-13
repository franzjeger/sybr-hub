"""Turning one audit finding into one ticket, exactly once.

Two things live here, and they are separate on purpose.

**Resolving a finding.** A recommendation is written when an audit runs and
read for months afterwards. Its identity is ``rec_id`` — language-independent,
built from the message key plus the params that identify *which* finding rather
than how big it is, so marking something done does not come undone when a count
moves. That is the same key ``remediation_items`` uses, so a ticket and a
remediation note attach to the same thing.

Deliberately *not* ``finding_id``: several recommendations share one
(``finding-email`` covers every domain missing DMARC), so a ticket keyed on it
would be one ticket for four domains and the second click would find the first
one already there.

**Recording it.** The ``UNIQUE(customer_id, rec_id, system)`` constraint is the
idempotency, not a check-then-insert in Python. A technician double-clicking, or
two technicians on the same finding, must not produce two tickets — and between
a ``SELECT`` that found nothing and an ``INSERT``, another request fits.

The order matters and is the uncomfortable part: the ticket is created in
Autotask *before* the row exists here, because there is no id to store until
Autotask answers. If the insert then loses the race, the ticket is real and this
process is not the one that owns it, so the winner's row is returned and the
loser's ticket is reported rather than hidden. That is a worse failure than a
duplicate row and a better one than a silent duplicate ticket.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.database import get_db

logger = logging.getLogger(__name__)

SYSTEM_AUTOTASK = "autotask"
SYSTEM_MYITPROCESS = "myitprocess"


@dataclass(frozen=True)
class Finding:
    """One recommendation from the customer's latest audit run."""

    rec_id: str
    title: str
    detail: str
    priority: str
    audit_date: str


@dataclass(frozen=True)
class TicketRecord:
    """A ticket this install has already raised for a finding."""

    rec_id: str
    system: str
    external_id: str
    external_url: str
    title: str
    created_at: str
    created_by: str

    def as_dict(self) -> dict:
        return {
            "rec_id": self.rec_id,
            "system": self.system,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "title": self.title,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }


def find_recommendation(customer_id: str, rec_id: str, lang: str) -> Finding | None:
    """The recommendation with this id in the customer's latest run.

    None when the run has no such recommendation. A ticket is a claim that the
    audit found something, so raising one for an id this run does not carry
    would put a sentence in a customer's PSA that no evidence supports.

    Reads the newest run only. An older run's finding may well have been fixed
    since, and "the audit says" has to mean the current audit.
    """
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager
    from app.core.encryption import encrypted_read_json
    from app.web.routes.dashboard_overview import relocalise_recommendations

    customer = CustomerManager.get_customer(customer_id) or {}
    name = customer.get("CustomerName", customer_id)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    root = get_audit_dir() / safe
    if not root.is_dir():
        return None

    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        path = run / "_audit_metrics.json"
        if not path.exists():
            continue
        try:
            metrics = relocalise_recommendations(encrypted_read_json(path), lang)
        except Exception as e:
            # Same reasoning as the remediation view: an unreadable run is not
            # an empty one, but there is nothing useful to do here except
            # decline, and the caller turns None into "finding not found".
            logger.warning("Could not read recommendations for %s: %s", customer_id, e)
            return None
        for rec in metrics.get("recommendations", []):
            if isinstance(rec, dict) and rec.get("rec_id") == rec_id:
                return Finding(
                    rec_id=rec_id,
                    title=str(rec.get("title", "")),
                    detail=str(rec.get("detail", "")),
                    priority=str(rec.get("priority", "")),
                    audit_date=run.name,
                )
        return None      # newest run read, id not in it
    return None


async def get_ticket(
    customer_id: str, rec_id: str, system: str = SYSTEM_AUTOTASK
) -> TicketRecord | None:
    """The ticket already raised for this finding, if there is one."""
    async with get_db() as conn, conn.execute(
        """SELECT rec_id, system, external_id, external_url, title,
                      created_at, created_by
               FROM finding_tickets
               WHERE customer_id = ? AND rec_id = ? AND system = ?""",
        (customer_id, rec_id, system),
    ) as cur:
        row = await cur.fetchone()
    return None if row is None else TicketRecord(*row)


async def list_tickets(
    customer_id: str, system: str = SYSTEM_AUTOTASK
) -> dict[str, dict]:
    """{rec_id: record} for one customer and one system, in one query.

    Scoped to a system rather than returning everything keyed on rec_id: a
    finding may legitimately have both an Autotask ticket and a myITprocess
    recommendation, and a single dict keyed on rec_id would silently drop one
    of them — whichever the database happened to return second.
    """
    async with get_db() as conn, conn.execute(
        """SELECT rec_id, system, external_id, external_url, title,
                      created_at, created_by
               FROM finding_tickets WHERE customer_id = ? AND system = ?""",
        (customer_id, system),
    ) as cur:
        rows = await cur.fetchall()
    return {r[0]: TicketRecord(*r).as_dict() for r in rows}


async def record_ticket(
    customer_id: str,
    rec_id: str,
    system: str,
    external_id: str,
    external_url: str,
    title: str,
    created_by: str,
) -> tuple[TicketRecord, bool]:
    """Store a raised ticket. Returns (record, is_ours).

    ``is_ours`` is False when another request won the race and its ticket is
    the one recorded. The caller has a real, orphaned ticket in that case and
    must say so rather than presenting the stored one as the one it just made.

    ``ON CONFLICT DO NOTHING`` rather than an upsert: overwriting would replace
    a live ticket id with a newer one and lose the reference to the first.
    """
    now = datetime.now(UTC).isoformat()
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO finding_tickets
                   (customer_id, rec_id, system, external_id, external_url,
                    title, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(customer_id, rec_id, system) DO NOTHING""",
            (customer_id, rec_id, system, external_id, external_url,
             title, now, created_by),
        )
        await conn.commit()

    stored = await get_ticket(customer_id, rec_id, system)
    if stored is None:
        # The insert did nothing and nothing is there — the row was deleted
        # between the two statements, which nothing in this app does.
        raise RuntimeError(
            f"finding_tickets row for {rec_id} vanished immediately after insert"
        )
    return stored, stored.external_id == external_id
