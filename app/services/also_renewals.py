"""ALSO subscription renewal cache.

Writes the renewal rows that the action list (``/also/renewals``) reads. Lives
in ``app/services`` rather than a web route because both the scheduled price
refresh and the manual sync call it — a service calling a route is a layering
inversion in both directions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select

from app.core.customer import CustomerManager
from app.core.orm import get_session
from app.models.integrations import AlsoRenewal

logger = logging.getLogger(__name__)


async def cache_renewals(account_id: str, subs: list[dict]) -> None:
    """Cache subscription renewal data in the DB for the renewals action list."""
    # Find customer name from account_id
    customer_name = ""
    customer_id = ""
    for c in CustomerManager.list_customers():
        if str(c.get("AlsoAccountId", "")) == str(account_id):
            customer_name = c.get("CustomerName", "")
            customer_id = c.get("_id", "")
            break

    if not customer_id:
        return

    now = datetime.now(UTC).isoformat()
    async with get_session() as session:
        for s in subs:
            sub_id = str(s.get("AccountId", ""))
            if not sub_id:
                continue

            result = await session.execute(
                select(AlsoRenewal).where(
                    AlsoRenewal.customer_id == customer_id, AlsoRenewal.subscription_id == sub_id
                )
            )
            existing = result.scalars().first()
            if existing:
                existing.service_display = s.get("ServiceDisplayName", "")
                existing.vendor = s.get("VendorDisplayName", "")
                existing.contract_end = s.get("ContractEndDate", "")
                existing.account_state = s.get("AccountState", "Active")
                existing.scanned_at = now
            else:
                new_renewal = AlsoRenewal(
                    customer_id=customer_id,
                    customer_name=customer_name,
                    subscription_id=sub_id,
                    service_name=s.get("ServiceName", ""),
                    service_display=s.get("ServiceDisplayName", ""),
                    vendor=s.get("VendorDisplayName", ""),
                    contract_id=s.get("ContractId", ""),
                    contract_end=s.get("ContractEndDate", ""),
                    billing_start=s.get("BillingStartDate", ""),
                    account_state=s.get("AccountState", "Active"),
                    scanned_at=now,
                )
                session.add(new_renewal)
        await session.commit()
    logger.info("Cached %d renewals for %s", len(subs), customer_name)
