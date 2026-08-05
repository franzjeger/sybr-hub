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

    Access is granted when the user is an admin, or holds the explicit
    ``all_customers`` grant, or has a matching ``customer_access`` row.

    Previously an *absence* of rows meant "unrestricted", so a technician
    nobody had assigned customers to could read every customer in the system —
    the failure mode of a mis-configuration was full access rather than none.
    The grant is now a column on the user (see migration 14), which preserves
    the old behaviour for accounts that already existed while making it a
    visible, revocable decision rather than a side effect of an empty table.
    """
    if user.role == Role.admin or user.all_customers:
        return True

    async with get_db() as conn:
        async with conn.execute(
            "SELECT 1 FROM customer_access WHERE user_id = ? AND customer_id = ?",
            (user.id, customer_id),
        ) as cur:
            return await cur.fetchone() is not None


async def get_accessible_customer_ids(user: User) -> Optional[set[str]]:
    """Return the set of customer IDs this user may access.

    Returns None for "no restriction" (admin, or the explicit all-customers
    grant). Otherwise returns the assigned set, which may be empty — an empty
    set means "no customers", not "all customers".
    """
    if user.role == Role.admin or user.all_customers:
        return None  # no restriction

    async with get_db() as conn:
        async with conn.execute(
            "SELECT customer_id FROM customer_access WHERE user_id = ?",
            (user.id,),
        ) as cur:
            rows = await cur.fetchall()

    return {r[0] for r in rows}


async def set_all_customers(user_id: str, allowed: bool) -> None:
    """Grant or revoke the blanket all-customers access for a user."""
    async with get_db() as conn:
        await conn.execute(
            "UPDATE users SET all_customers = ? WHERE id = ?",
            (int(allowed), user_id),
        )
        await conn.commit()


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


async def check_audit_path_access(user: User, path: str) -> bool:
    """Whether *user* may touch this path inside the audit tree.

    The audit tree stores each customer's runs under a directory named after
    the customer, so the first segment is the customer selector. Routes that
    serve or delete files out of that tree were guarded by authentication
    alone, which let any logged-in account read every customer's decrypted
    reports and raw tenant dumps by walking the paths that /api/history and
    /api/reports/archive hand out.

    Fails closed: a segment that matches no customer is refused for anyone who
    is not unrestricted, and a segment that matches several customers (the
    directory transform is lossy) requires access to all of them.
    """
    from pathlib import Path

    from app.core.config import get_audit_dir
    from app.core.customer import customers_for_dir_name

    allowed = await get_accessible_customer_ids(user)
    if allowed is None:
        return True  # admin or explicit all-customers grant

    # Resolve before selecting the customer segment. Taking the first segment
    # of the raw string judged a different file than the one that gets opened:
    # the containment check downstream resolves the path, so "Alpha/../Beta"
    # presented an allowed first segment while reading — and, through the
    # delete routes, removing — Beta's directory. Resolving here makes both
    # guards agree on the same file, and covers "..", absolute paths, encoded
    # separators and symlinks in one move.
    audit_dir = get_audit_dir().resolve()
    candidate = Path(str(path).replace("\\", "/"))
    target = candidate.resolve() if candidate.is_absolute() else (audit_dir / candidate).resolve()
    try:
        rel = target.relative_to(audit_dir)
    except ValueError:
        logger.info("403 audit-path: user=%s path=%r escapes the audit tree", user.username, str(path))
        return False
    if not rel.parts:
        return False

    segment = rel.parts[0]
    matches = customers_for_dir_name(segment)
    if not matches:
        logger.info(
            "403 audit-path: user=%s segment=%r matches no customer", user.username, segment
        )
        return False
    return all(c.get("_id") in allowed for c in matches)
