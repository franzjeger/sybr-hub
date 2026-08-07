"""The account the toolkit acts as when nobody is watching.

Work that runs on a schedule still does things to customer systems, and those
things want an identity. VPN tunnels held open to pull statistics from customer
sites used to be opened under whichever technician happened to click, which made
two problems: the activity log was wrong about who did it, and one person's
session owned infrastructure everybody else depended on.

So there is an account. It holds customer access and capabilities like any
other, appears in the activity log by name, and owns the tunnels the collectors
need. It cannot sign in — ``authenticate`` refuses it — because an account with
no human behind it and no password would otherwise be a standing invitation.

It is created on demand rather than by a migration. A migration that inserted a
privileged account into every existing install is the kind of thing that should
be a decision somebody made.
"""

from __future__ import annotations

import logging

from app.models.user import Role, User

logger = logging.getLogger(__name__)

USERNAME = "sybr-system"
DISPLAY_NAME = "Sybr HUB (system)"


async def get() -> User | None:
    """The system account, or None if this install has not created one."""
    from app.core.auth import get_user_by_username

    user = await get_user_by_username(USERNAME)
    return user if user and user.is_system else None


async def ensure() -> User:
    """The system account, created if this install has none.

    Given technician rather than admin: it opens tunnels and reads, and nothing
    it does needs to administer the toolkit. can_write is granted because the
    collectors record what they find; tenant_write is not, because nothing
    running unattended should be able to change a customer's Microsoft tenant.
    """
    import secrets

    from app.core.auth import create_user
    from app.core.database import get_db
    from app.core.rbac import set_all_customers, set_can_write

    existing = await get()
    if existing:
        return existing

    # A password it can never use, so no code path is tempted to reuse one.
    # The suffix satisfies the complexity policy deterministically:
    # token_urlsafe only sometimes contains a symbol, which made account
    # creation fail on roughly half of installs and pass on the rest.
    password = secrets.token_urlsafe(48) + "aA1!"
    user = await create_user(USERNAME, password, DISPLAY_NAME, role=Role.technician)
    async with get_db() as conn:
        await conn.execute("UPDATE users SET is_system = 1 WHERE id = ?", (user.id,))
        await conn.commit()
    await set_all_customers(user.id, True)
    await set_can_write(user.id, True)

    logger.warning("Created the system account %r", USERNAME)
    return await get()
