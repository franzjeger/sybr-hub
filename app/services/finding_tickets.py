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

**Recording it.** A durable unique operation is reserved before a remote
request. Successful objects are linked in finding_tickets. Pending and unknown
operations block another remote write across processes and restarts; they are
never expired automatically because a timeout can still have created an object.
Use scripts/reconcile_finding.py after checking the provider with the hub stopped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert
from sqlmodel import select

from app.core.orm import get_session
from app.models.ticket import FindingOperation, FindingTicket

logger = logging.getLogger(__name__)

SYSTEM_AUTOTASK = "autotask"
SYSTEM_MYITPROCESS = "myitprocess"


async def reserve_operation(customer_id: str, rec_id: str, system: str, username: str) -> str:
    """Reserve before a remote POST. Ambiguous outcomes never auto-expire.

    A crash may leave a pending operation even if the provider created its
    object. An operator must reconcile that outcome before another attempt.
    """
    from app.core.exceptions import ConflictError

    operation_id = uuid4().hex
    async with get_session() as session:
        stmt = (
            insert(FindingOperation)
            .values(
                operation_id=operation_id,
                customer_id=customer_id,
                rec_id=rec_id,
                system=system,
                status="pending",
                created_at=datetime.now(UTC).isoformat(),
                created_by=username,
            )
            .on_conflict_do_nothing(index_elements=["customer_id", "rec_id", "system"])
        )
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount != 1:
            q = select(FindingOperation).where(
                FindingOperation.customer_id == customer_id,
                FindingOperation.rec_id == rec_id,
                FindingOperation.system == system,
            )
            existing = (await session.execute(q)).scalar_one_or_none()
            if existing:
                raise ConflictError(
                    f"External write already reserved ({existing.operation_id}, {existing.status}). "
                    "Check the provider and reconcile this operation before retrying."
                )
            else:
                raise ConflictError(
                    "External write already reserved. Check the provider and reconcile this operation before retrying."
                )
    return operation_id


async def finish_operation(operation_id: str, *, succeeded: bool) -> None:
    async with get_session() as session:
        stmt = select(FindingOperation).where(FindingOperation.operation_id == operation_id)
        operation = (await session.execute(stmt)).scalar_one_or_none()
        if operation:
            operation.status = "succeeded" if succeeded else "unknown"
            session.add(operation)
            await session.commit()


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


def latest_recommendations(customer_id: str, lang: str) -> tuple[str | None, list[dict]]:
    """The newest run's name and its recommendations, in *lang*.

    ``(None, [])`` when the customer has no run with metrics. An unreadable
    newest run is also ``(None, [])``: it is not an empty run, but there is
    nothing trustworthy to show from it, and an older run's findings may have
    been fixed since, so "the audit says" has to mean the newest one.
    """
    from app.core.config import get_audit_dir
    from app.core.customer import CustomerManager, customer_dir_name
    from app.core.encryption import encrypted_read_json
    from app.reports.recommendations import relocalise_recommendations

    customer = CustomerManager.get_customer(customer_id) or {}
    root = get_audit_dir() / customer_dir_name(customer.get("CustomerName", customer_id))
    if not root.is_dir():
        return None, []

    for run in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        path = run / "_audit_metrics.json"
        if not path.exists():
            continue
        try:
            metrics = relocalise_recommendations(encrypted_read_json(path), lang)
        except Exception as e:
            logger.warning("Could not read recommendations for %s: %s", customer_id, e)
            return None, []
        recs = [r for r in metrics.get("recommendations", []) if isinstance(r, dict)]
        return run.name, recs
    return None, []


def find_recommendation(customer_id: str, rec_id: str, lang: str) -> Finding | None:
    """The recommendation with this id in the customer's latest run.

    None when the run has no such recommendation. A ticket is a claim that the
    audit found something, so raising one for an id this run does not carry
    would put a sentence in a customer's PSA that no evidence supports.
    """
    run_name, recs = latest_recommendations(customer_id, lang)
    for rec in recs:
        if rec.get("rec_id") == rec_id:
            return Finding(
                rec_id=rec_id,
                title=str(rec.get("title", "")),
                detail=str(rec.get("detail", "")),
                priority=str(rec.get("priority", "")),
                audit_date=run_name or "",
            )
    return None


async def get_ticket(
    customer_id: str, rec_id: str, system: str = SYSTEM_AUTOTASK
) -> TicketRecord | None:
    """The ticket already raised for this finding, if there is one."""
    async with get_session() as session:
        stmt = select(FindingTicket).where(
            FindingTicket.customer_id == customer_id,
            FindingTicket.rec_id == rec_id,
            FindingTicket.system == system,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        return None
    return TicketRecord(
        rec_id=row.rec_id,
        system=row.system,
        external_id=row.external_id,
        external_url=row.external_url,
        title=row.title,
        created_at=row.created_at,
        created_by=row.created_by,
    )


async def list_tickets(customer_id: str, system: str = SYSTEM_AUTOTASK) -> dict[str, dict]:
    """{rec_id: record} for one customer and one system, in one query."""
    async with get_session() as session:
        stmt = select(FindingTicket).where(
            FindingTicket.customer_id == customer_id, FindingTicket.system == system
        )
        rows = (await session.execute(stmt)).scalars().all()

    return {
        row.rec_id: TicketRecord(
            rec_id=row.rec_id,
            system=row.system,
            external_id=row.external_id,
            external_url=row.external_url,
            title=row.title,
            created_at=row.created_at,
            created_by=row.created_by,
        ).as_dict()
        for row in rows
    }


async def record_ticket(
    customer_id: str,
    rec_id: str,
    system: str,
    external_id: str,
    external_url: str,
    title: str,
    created_by: str,
) -> tuple[TicketRecord, bool]:
    """Store a raised ticket. Returns (record, is_ours)."""
    now = datetime.now(UTC).isoformat()
    async with get_session() as session:
        stmt = (
            insert(FindingTicket)
            .values(
                customer_id=customer_id,
                rec_id=rec_id,
                system=system,
                external_id=external_id,
                external_url=external_url,
                title=title,
                created_at=now,
                created_by=created_by,
            )
            .on_conflict_do_nothing(index_elements=["customer_id", "rec_id", "system"])
        )
        await session.execute(stmt)
        await session.commit()

    stored = await get_ticket(customer_id, rec_id, system)
    if stored is None:
        raise RuntimeError(f"finding_tickets row for {rec_id} vanished immediately after insert")
    return stored, stored.external_id == external_id
