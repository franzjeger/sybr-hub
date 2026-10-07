"""Per-customer role-based access control.

Uses the ``customer_access`` table to restrict which customers each user
can view and modify.  Admins bypass all checks.
"""

from __future__ import annotations

import logging

from sqlmodel import delete, select

from app.core import access_events
from app.core.orm import get_session
from app.models.user import CustomerAccess, Role, User

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

    async with get_session() as session:
        result = await session.execute(
            select(CustomerAccess).where(
                CustomerAccess.user_id == user.id, CustomerAccess.customer_id == customer_id
            )
        )
        return result.first() is not None


async def get_accessible_customer_ids(user: User) -> set[str] | None:
    """Return the set of customer IDs this user may access.

    Returns None for "no restriction" (admin, or the explicit all-customers
    grant). Otherwise returns the assigned set, which may be empty — an empty
    set means "no customers", not "all customers".
    """
    if user.role == Role.admin or user.all_customers:
        return None  # no restriction

    async with get_session() as session:
        result = await session.execute(
            select(CustomerAccess.customer_id).where(CustomerAccess.user_id == user.id)
        )
        rows = result.scalars().all()

    return set(rows)


async def set_can_write(user_id: str, enabled: bool) -> None:
    """Grant or revoke the system-wide write capability for one user.

    Revoking is the interesting direction: an account left without it can read
    its permitted parts of the toolkit and change none of it. Additional
    accounts start this way; first-run setup grants the initial administrator
    full access. Logged at warning level either way — this is the switch that
    decides whether somebody can alter anything at all.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.can_write = enabled
            await session.commit()
        access_events.invalidate(user_id=user_id)
    logger.warning("can_write %s for user %s", "granted" if enabled else "revoked", user_id)


async def set_tenant_write(user_id: str, enabled: bool) -> None:
    """Grant or revoke the tenant-write capability for one user.

    Logged either way, at warning level. A capability that reaches a
    customer's production is one where "who turned this on, and when" gets
    asked, and the answer should be in the log without anyone having planned
    for the question.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.tenant_write = enabled
            await session.commit()
        access_events.invalidate(user_id=user_id)
    logger.warning(
        "Tenant-write capability %s user %s",
        "GRANTED to" if enabled else "REVOKED from",
        user_id,
    )


async def set_all_customers(user_id: str, allowed: bool) -> None:
    """Grant or revoke the blanket all-customers access for a user."""
    async with get_session() as session:
        user = await session.get(User, user_id)
        if user:
            user.all_customers = allowed
            await session.commit()
        access_events.invalidate(user_id=user_id)


def filter_customers(customers: list[dict], allowed: set[str] | None) -> list[dict]:
    """Filter a customer list to only those the user may access.

    If *allowed* is None (admin / unconfigured), returns the full list.
    """
    if allowed is None:
        return customers
    return [c for c in customers if c.get("_id") in allowed]


def customer_in_scope(customer_id: str | None, allowed: set[str] | None) -> bool:
    """Whether a row owned by *customer_id* is visible under *allowed*.

    A row with no owning customer (an unlinked provider account, a host nobody
    assigned) is MSP-wide data, so only an unrestricted caller sees it.
    """
    if allowed is None:
        return True
    return bool(customer_id) and customer_id in allowed


async def grant_access(user_id: str, customer_id: str) -> None:
    """Grant a user access to a customer."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    async with get_session() as session:
        stmt = (
            sqlite_insert(CustomerAccess)
            .values(user_id=user_id, customer_id=customer_id)
            .on_conflict_do_nothing(index_elements=["user_id", "customer_id"])
        )
        await session.execute(stmt)
        await session.commit()
        access_events.invalidate(user_id=user_id)


async def revoke_access(user_id: str, customer_id: str) -> None:
    """Revoke a user's access to a customer."""
    async with get_session() as session:
        await session.execute(
            delete(CustomerAccess).where(
                CustomerAccess.user_id == user_id, CustomerAccess.customer_id == customer_id
            )
        )
        await session.commit()
        access_events.invalidate(user_id=user_id)


async def set_user_customers(
    user_id: str,
    customer_ids: list[str],
    *,
    all_customers: bool = False,
) -> None:
    """Atomically replace both the access mode and its grants. Empty is no access."""
    async with get_session() as session:
        try:
            from sqlalchemy import text

            await session.commit()
            await session.execute(text("BEGIN IMMEDIATE"))
        except Exception:
            # Without the write lock the replace below is still correct, but it
            # is no longer isolated from a concurrent grant change. Worth
            # knowing about if two operators ever disagree on what they saved.
            logger.warning("Could not take SQLite write lock for grant replace", exc_info=True)

        try:
            user = await session.get(User, user_id)
            if user:
                user.all_customers = all_customers

            await session.execute(delete(CustomerAccess).where(CustomerAccess.user_id == user_id))
            for cid in dict.fromkeys(customer_ids):
                session.add(CustomerAccess(user_id=user_id, customer_id=cid))
            await session.commit()
            access_events.invalidate(user_id=user_id)
        except Exception:
            await session.rollback()
            raise


async def get_user_customer_ids(user_id: str) -> list[str]:
    """Return list of customer IDs assigned to a user."""
    async with get_session() as session:
        result = await session.execute(
            select(CustomerAccess.customer_id).where(CustomerAccess.user_id == user_id)
        )
        return list(result.scalars().all())


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
        logger.info(
            "403 audit-path: user=%s path=%r escapes the audit tree", user.username, str(path)
        )
        return False
    if not rel.parts:
        return False

    allowed = await get_accessible_customer_ids(user)
    if allowed is None:
        return True  # admin or explicit all-customers grant inside audit root

    segment = rel.parts[0]
    matches = customers_for_dir_name(segment)
    if not matches:
        logger.info(
            "403 audit-path: user=%s segment=%r matches no customer", user.username, segment
        )
        return False
    return all(c.get("_id") in allowed for c in matches)
