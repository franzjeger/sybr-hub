"""Per-customer role-based access control.

Uses the ``customer_access`` table to restrict which customers each user
can view and modify.  Admins bypass all checks.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.database import get_db
from app.models.user import Role, User

logger = logging.getLogger(__name__)


async def check_customer_access(user: User, customer_id: str) -> bool:
    """Return True if user may access the given customer.

    Admins always have access.  For other roles, a matching row in
    ``customer_access`` is required.  If no rows exist at all for a user,
    access is granted (backwards-compatible: RBAC not yet configured).
    """
    if user.role == Role.admin:
        return True

    async with get_db() as conn:
        # Check if user has *any* customer_access rows (RBAC configured)
        async with conn.execute(
            "SELECT COUNT(*) FROM customer_access WHERE user_id = ?",
            (user.id,),
        ) as cur:
            total = (await cur.fetchone())[0]

        if total == 0:
            # RBAC not configured for this user — allow all (backwards compat)
            return True

        async with conn.execute(
            "SELECT 1 FROM customer_access WHERE user_id = ? AND customer_id = ?",
            (user.id, customer_id),
        ) as cur:
            return await cur.fetchone() is not None


async def get_accessible_customer_ids(user: User) -> Optional[set[str]]:
    """Return the set of customer IDs this user may access.

    Returns None if the user is admin or has no RBAC rows configured
    (meaning "all customers").  Returns a set otherwise.
    """
    if user.role == Role.admin:
        return None  # no restriction

    async with get_db() as conn:
        async with conn.execute(
            "SELECT customer_id FROM customer_access WHERE user_id = ?",
            (user.id,),
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        return None  # RBAC not configured — allow all

    return {r[0] for r in rows}


def filter_customers(customers: list[dict], allowed: Optional[set[str]]) -> list[dict]:
    """Filter a customer list to only those the user may access.

    If *allowed* is None (admin / unconfigured), returns the full list.
    """
    if allowed is None:
        return customers
    return [c for c in customers if c.get("_id") in allowed]


async def grant_access(user_id: str, customer_id: str) -> None:
    """Grant a user access to a customer."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO customer_access (user_id, customer_id) VALUES (?, ?)",
            (user_id, customer_id),
        )
        await conn.commit()


async def revoke_access(user_id: str, customer_id: str) -> None:
    """Revoke a user's access to a customer."""
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM customer_access WHERE user_id = ? AND customer_id = ?",
            (user_id, customer_id),
        )
        await conn.commit()


async def set_user_customers(user_id: str, customer_ids: list[str]) -> None:
    """Replace a user's customer access list."""
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM customer_access WHERE user_id = ?", (user_id,)
        )
        for cid in customer_ids:
            await conn.execute(
                "INSERT INTO customer_access (user_id, customer_id) VALUES (?, ?)",
                (user_id, cid),
            )
        await conn.commit()


async def get_user_customer_ids(user_id: str) -> list[str]:
    """Return list of customer IDs assigned to a user."""
    async with get_db() as conn:
        async with conn.execute(
            "SELECT customer_id FROM customer_access WHERE user_id = ?",
            (user_id,),
        ) as cur:
            return [r[0] for r in await cur.fetchall()]
