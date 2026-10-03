"""The newest audit metrics row for each customer, in one query.

The dashboards, the alert engine and the licence view all want "the latest
audit per customer". Each used to read the whole audit_metrics table,
metrics_json blobs included, and keep the first row per customer in Python,
so the cost grew with every audit ever run. A window function over the
(customer_id, audit_date) index lets SQLite hand back one row per customer.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import aliased
from sqlmodel import select

from app.core.orm import get_session
from app.models.audit import AuditMetric


async def latest_metrics_per_customer() -> dict[str, AuditMetric]:
    """Map each customer_id to its newest AuditMetric row.

    Two rows with the same audit_date resolve to the one written last.
    """
    rank = (
        func.row_number()
        .over(
            partition_by=AuditMetric.customer_id,
            order_by=(AuditMetric.audit_date.desc(), AuditMetric.id.desc()),
        )
        .label("rank")
    )
    ranked = select(AuditMetric, rank).subquery()
    newest = aliased(AuditMetric, ranked)
    async with get_session() as session:
        result = await session.execute(select(newest).where(ranked.c.rank == 1))
        return {m.customer_id: m for m in result.scalars().all()}
