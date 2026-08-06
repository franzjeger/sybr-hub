#!/usr/bin/env python3
"""Grant or revoke write capabilities from the server.

Every account starts read-only, admins included, and granting is itself a
write — so immediately after the migration there is no way to hand out the
first grant through the interface. This is that way. It exists in the same
change as the capability rather than being left for later, because a lock with
no key is not a security model, it is an outage.

    python scripts/grant_write.py --list
    python scripts/grant_write.py --user frank --write
    python scripts/grant_write.py --user frank --write --tenant-write
    python scripts/grant_write.py --user frank --revoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _run(args) -> int:
    from app.core.database import get_db, run_migrations
    from app.core.rbac import set_can_write, set_tenant_write

    await run_migrations()

    async with get_db() as conn, conn.execute(
        "SELECT id, username, role, can_write, tenant_write FROM users ORDER BY username"
    ) as cur:
        users = [dict(r) for r in await cur.fetchall()]

    if args.list or not args.user:
        print(f"{'username':22} {'role':12} {'write':7} {'tenant_write'}")
        for u in users:
            print(f"{u['username']:22} {u['role']:12} "
                  f"{'yes' if u['can_write'] else 'no':7} "
                  f"{'yes' if u['tenant_write'] else 'no'}")
        if not args.user:
            print("\nPass --user NAME with --write / --tenant-write / --revoke to change one.")
        return 0

    target = next((u for u in users if u["username"] == args.user), None)
    if not target:
        print(f"No user {args.user!r}. Known: {', '.join(u['username'] for u in users)}")
        return 1

    if args.revoke:
        # tenant_write first: leaving it set on an account that may not write
        # at all is a contradiction the middleware would resolve safely and a
        # reader would not.
        await set_tenant_write(target["id"], False)
        await set_can_write(target["id"], False)
        print(f"{args.user}: write and tenant_write revoked")
        return 0

    if args.tenant_write and not args.write:
        print("--tenant-write requires --write: writing into a customer's tenant "
              "is the far end of writing at all.")
        return 1

    if args.write:
        await set_can_write(target["id"], True)
        print(f"{args.user}: write granted")
    if args.tenant_write:
        await set_tenant_write(target["id"], True)
        print(f"{args.user}: tenant_write granted")
    return 0


async def _run_and_close(args) -> int:
    """aiosqlite's worker threads are not daemons.

    Left running they hang interpreter exit — the script does its work, prints
    nothing because stdout is still buffered, and looks like it froze on the
    first query. tests/conftest.py disposes them for exactly this reason; a
    one-shot script has to do the same.
    """
    from app.core.database import close_all_pools

    try:
        return await _run(args)
    finally:
        await close_all_pools()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tenant-write", action="store_true", dest="tenant_write")
    parser.add_argument("--revoke", action="store_true")
    return asyncio.run(_run_and_close(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
