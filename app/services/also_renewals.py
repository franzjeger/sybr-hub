"""ALSO subscription renewal cache.

Writes the renewal rows that the action list (``/also/renewals``) reads. Lives
in ``app/services`` rather than a web route because both the scheduled price
refresh and the manual sync call it — a service calling a route is a layering
inversion in both directions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.customer import CustomerManager
from app.core.database import get_db

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

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        for s in subs:
            sub_id = str(s.get("AccountId", ""))
            if not sub_id:
                continue
            await db.execute("""
                INSERT INTO also_renewals
                    (customer_id, customer_name, subscription_id, service_name, service_display,
                     vendor, contract_id, contract_end, billing_start, account_state, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, subscription_id) DO UPDATE SET
                    service_display = excluded.service_display,
                    vendor = excluded.vendor,
                    contract_end = excluded.contract_end,
                    account_state = excluded.account_state,
                    scanned_at = excluded.scanned_at
            """, (
                customer_id, customer_name, sub_id,
                s.get("ServiceName", ""),
                s.get("ServiceDisplayName", ""),
                s.get("VendorDisplayName", ""),
                s.get("ContractId", ""),
                s.get("ContractEndDate", ""),
                s.get("BillingStartDate", ""),
                s.get("AccountState", "Active"),
                now,
            ))
        await db.commit()
    logger.info("Cached %d renewals for %s", len(subs), customer_name)
