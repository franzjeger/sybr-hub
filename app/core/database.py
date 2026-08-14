"""SQLite database module for MSP Toolkit.

Provides async database access via aiosqlite with schema versioning and
automatic migration.  New relational data (users, sessions, SSH hosts/keys,
VPN profiles) lives here; existing encrypted JSON files remain unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, NamedTuple, Optional

import aiosqlite

from app.core.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "msp_toolkit.db"

# Current schema version — bump this when adding migrations.
SCHEMA_VERSION = 18

# ── Schema migrations ────────────────────────────────────────────────────────
# Each entry is (version, description, body).  Migrations run sequentially
# from the stored version up to SCHEMA_VERSION.
#
# ``body`` is either a SQL script (run via executescript) or an async callable
# taking the connection. SQLite has no `ALTER TABLE ... ADD COLUMN IF NOT
# EXISTS`, so column additions have to inspect the schema first to stay
# re-runnable — which the runner requires, since a migration whose version
# bump fails is retried on the next boot.


async def _add_all_customers_column(conn: aiosqlite.Connection) -> None:
    """Add users.all_customers, defaulting existing accounts to unrestricted.

    Existing installs relied on 'a user with no customer_access rows can see
    everything'. Defaulting the new column to 1 preserves exactly that for
    accounts that already exist, while new accounts are created scoped —
    turning an implicit fail-open into an explicit, visible grant.
    """
    async with conn.execute("PRAGMA table_info(users)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "all_customers" in columns:
        return
    await conn.execute(
        "ALTER TABLE users ADD COLUMN all_customers INTEGER NOT NULL DEFAULT 1"
    )


async def _add_is_system_column(conn: aiosqlite.Connection) -> None:
    """Add users.is_system — an account the toolkit acts as, not a person.

    It exists so that work nobody is watching has an identity of its own. VPN
    tunnels held open to pull statistics from customer sites were previously
    opened under whichever technician happened to click, which made the
    activity log wrong about who did what and meant one person's session owned
    infrastructure everybody depended on.

    A system account cannot sign in. ``authenticate`` refuses it outright,
    because an account with no human behind it and no password is otherwise a
    standing invitation — the point is an identity for attribution and locking,
    not a second way through the front door.
    """
    cur = await conn.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in await cur.fetchall()}
    if "is_system" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")


async def _add_can_write_column(conn: aiosqlite.Connection) -> None:
    """Add users.can_write, defaulting every account to *off*.

    The system-wide half of the same idea as tenant_write below: read is what
    an account can do, and changing anything is a grant somebody made. It
    covers Sybr HUB itself — notes, tags, hosts, settings, users — while
    tenant_write stays the narrower power to write into a customer's Microsoft
    tenant, and now requires this one as well.

    Off for every existing account, admins included, because a capability that
    arrives switched on is not a capability. That has a consequence worth
    stating plainly: immediately after this migration nobody can grant it
    through the interface either, since granting is itself a write. That is
    what scripts/grant_write.py is for, and why it exists in the same change
    rather than being left for later.
    """
    cur = await conn.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in await cur.fetchall()}
    if "can_write" not in columns:
        await conn.execute("ALTER TABLE users ADD COLUMN can_write INTEGER NOT NULL DEFAULT 0")


async def _add_tenant_write_column(conn: aiosqlite.Connection) -> None:
    """Add users.tenant_write, defaulting every account to *off*.

    Note the default, and how it differs from all_customers above. That one
    defaulted to 1 because existing installs already behaved as if it were
    set, and flipping it would have locked people out. Nobody has ever been
    able to write into a customer tenant from here, so 0 is what preserves
    behaviour — and it is also the safe direction. A capability that arrives
    switched on for every existing account is not a capability, it is a
    change of blast radius announced in a release note.

    This is deliberately not a role. Administering Sybr HUB and changing
    configuration inside somebody's Microsoft tenant are different powers with
    different consequences, and rolling them together would mean every admin
    got the second one by accident on the day it shipped.
    """
    async with conn.execute("PRAGMA table_info(users)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "tenant_write" in columns:
        return
    await conn.execute(
        "ALTER TABLE users ADD COLUMN tenant_write INTEGER NOT NULL DEFAULT 0"
    )


_MIGRATIONS: list = [
    (
        1,
        "Initial schema — schema_version table",
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        );
        INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 0);
        """,
    ),
    (
        2,
        "Auth — users, sessions, customer_access, app_secrets",
        """
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            display_name  TEXT NOT NULL,
            email         TEXT,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'viewer',
            created_at    TEXT NOT NULL,
            last_login    TEXT,
            is_active     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            refresh_token_hash TEXT NOT NULL,
            created_at         TEXT NOT NULL,
            expires_at         TEXT NOT NULL,
            ip_address         TEXT,
            user_agent         TEXT
        );

        CREATE TABLE IF NOT EXISTS customer_access (
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            customer_id TEXT NOT NULL,
            PRIMARY KEY (user_id, customer_id)
        );

        CREATE TABLE IF NOT EXISTS app_secrets (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """,
    ),
    (
        3,
        "SSH — keys, hosts, deployments, audit log",
        """
        CREATE TABLE IF NOT EXISTS ssh_keys (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            key_type    TEXT NOT NULL,
            public_key  TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            tags        TEXT DEFAULT '[]',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            created_by  TEXT REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS ssh_hosts (
            id          TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            hostname    TEXT NOT NULL,
            port        INTEGER NOT NULL DEFAULT 22,
            username    TEXT NOT NULL,
            group_name  TEXT DEFAULT '',
            device_type TEXT NOT NULL DEFAULT 'linux',
            auth_method TEXT NOT NULL DEFAULT 'key',
            auth_key_id TEXT REFERENCES ssh_keys(id) ON DELETE SET NULL,
            customer_id TEXT,
            tags        TEXT DEFAULT '[]',
            notes       TEXT DEFAULT '',
            last_seen   TEXT,
            is_reachable INTEGER,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            created_by  TEXT REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS ssh_key_deployments (
            key_id      TEXT NOT NULL REFERENCES ssh_keys(id) ON DELETE CASCADE,
            host_id     TEXT NOT NULL REFERENCES ssh_hosts(id) ON DELETE CASCADE,
            deployed_at TEXT NOT NULL,
            deployed_by TEXT REFERENCES users(id),
            PRIMARY KEY (key_id, host_id)
        );

        CREATE TABLE IF NOT EXISTS ssh_audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            action          TEXT NOT NULL,
            key_name        TEXT,
            key_fingerprint TEXT,
            host_label      TEXT,
            hostname        TEXT,
            port            INTEGER,
            success         INTEGER NOT NULL,
            user_id         TEXT REFERENCES users(id),
            detail          TEXT DEFAULT ''
        );
        """,
    ),
    (
        4,
        "VPN — profiles",
        """
        CREATE TABLE IF NOT EXISTS vpn_profiles (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            protocol     TEXT NOT NULL,
            config       TEXT NOT NULL,  -- JSON blob
            full_tunnel  INTEGER NOT NULL DEFAULT 0,
            auto_connect INTEGER NOT NULL DEFAULT 0,
            kill_switch  INTEGER NOT NULL DEFAULT 0,
            customer_id  TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            created_by   TEXT REFERENCES users(id)
        );
        """,
    ),
    (
        5,
        "Audit metrics history — trend tracking over time",
        """
        CREATE TABLE IF NOT EXISTS audit_metrics (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id   TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            audit_date    TEXT NOT NULL,
            risk_grade    TEXT,
            risk_score    REAL,
            mfa_coverage_pct   REAL,
            secure_score_pct   REAL,
            total_users        INTEGER,
            users_no_mfa       INTEGER,
            ca_policies_enabled INTEGER,
            intune_compliance_pct REAL,
            admin_roles_ga_count  INTEGER,
            metrics_json  TEXT,     -- full metrics blob for future use
            created_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_metrics_customer
            ON audit_metrics(customer_id, audit_date);
        """,
    ),
    (
        6,
        "ALSO renewal cache — subscription tracking for renewal action lists",
        """
        CREATE TABLE IF NOT EXISTS also_renewals (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id      TEXT NOT NULL,
            customer_name    TEXT NOT NULL,
            subscription_id  TEXT NOT NULL,
            service_name     TEXT NOT NULL,
            service_display  TEXT NOT NULL,
            vendor           TEXT DEFAULT '',
            contract_id      TEXT DEFAULT '',
            contract_end     TEXT,
            billing_start    TEXT,
            account_state    TEXT DEFAULT 'Active',
            handled          INTEGER DEFAULT 0,
            notes            TEXT DEFAULT '',
            scanned_at       TEXT NOT NULL,
            UNIQUE(customer_id, subscription_id)
        );
        CREATE INDEX IF NOT EXISTS idx_also_renewals_end
            ON also_renewals(contract_end);
        CREATE INDEX IF NOT EXISTS idx_also_renewals_customer
            ON also_renewals(customer_id);
        """,
    ),
    (
        7,
        "ALSO subscription pricing cache — MRR tracking",
        """
        CREATE TABLE IF NOT EXISTS also_subscription_details (
            subscription_id  TEXT PRIMARY KEY,
            customer_id      TEXT NOT NULL,
            quantity         INTEGER DEFAULT 0,
            unit_price       REAL DEFAULT 0,
            monthly_cost     REAL DEFAULT 0,
            currency         TEXT DEFAULT '',
            fields_json      TEXT DEFAULT '[]',
            priceable_items_json TEXT DEFAULT '[]',
            cached_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_also_sub_details_customer
            ON also_subscription_details(customer_id);
        """,
    ),
    (
        8,
        "Remediation tracking — migrate from per-customer JSON to SQLite",
        """
        CREATE TABLE IF NOT EXISTS remediation_items (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id       TEXT NOT NULL,
            recommendation_id TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'open',
            notes             TEXT DEFAULT '',
            assigned_to       TEXT DEFAULT '',
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            UNIQUE(customer_id, recommendation_id)
        );
        CREATE INDEX IF NOT EXISTS idx_remediation_customer
            ON remediation_items(customer_id);
        CREATE INDEX IF NOT EXISTS idx_remediation_status
            ON remediation_items(customer_id, status);
        """,
    ),
    (
        9,
        "Uniweb hosting provider — account cache and customer matching",
        """
        CREATE TABLE IF NOT EXISTS uniweb_accounts (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            customer_id TEXT,
            last_sync   TEXT,
            data_json   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_uniweb_accounts_customer
            ON uniweb_accounts(customer_id);
        """,
    ),
    (
        10,
        "Health score snapshots for trend charts",
        """
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            risk_score  REAL,
            risk_grade  TEXT,
            mfa_pct     REAL,
            secure_score_pct REAL,
            health_score REAL,
            health_grade TEXT,
            total_users INTEGER,
            total_warns INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_health_snap_cust
            ON health_snapshots(customer_id, snapshot_date);
        """,
    ),
    (
        11,
        "Add indexes on ssh_hosts and vpn_profiles for customer_id lookups",
        """
        CREATE INDEX IF NOT EXISTS idx_ssh_hosts_customer
            ON ssh_hosts(customer_id);
        CREATE INDEX IF NOT EXISTS idx_vpn_profiles_customer
            ON vpn_profiles(customer_id);
        """,
    ),
    (
        12,
        "GDAP customer sync tracking — Partner Center integration",
        """
        CREATE TABLE IF NOT EXISTS gdap_customers (
            tenant_id         TEXT PRIMARY KEY,
            company_name      TEXT NOT NULL,
            domain            TEXT NOT NULL,
            gdap_status       TEXT DEFAULT 'active',
            last_synced       TEXT NOT NULL,
            imported          INTEGER DEFAULT 0,
            local_customer_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gdap_imported
            ON gdap_customers(imported);
        """,
    ),
    (
        13,
        "Persistent token blacklist — survives process restart so logged-out access tokens stay revoked",
        """
        CREATE TABLE IF NOT EXISTS token_blacklist (
            token_hash TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires
            ON token_blacklist(expires_at);
        """,
    ),
    (
        14,
        "Explicit all-customers grant — replaces 'no rows means unrestricted' in RBAC",
        _add_all_customers_column,
    ),
    (
        15,
        "Tenant-write capability — off for everyone, granted per user, never implied by a role",
        _add_tenant_write_column,
    ),
    (
        16,
        "System-wide write capability — read is the default for every account, admins included",
        _add_can_write_column,
    ),
    (
        17,
        "System account — an identity for work nobody is watching, which cannot sign in",
        _add_is_system_column,
    ),
    (
        18,
        "External tickets raised from a finding, so a second click does not raise a second ticket",
        """
        CREATE TABLE IF NOT EXISTS finding_tickets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id  TEXT NOT NULL,
            rec_id       TEXT NOT NULL,
            system       TEXT NOT NULL,
            external_id  TEXT NOT NULL,
            external_url TEXT NOT NULL DEFAULT '',
            title        TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL,
            created_by   TEXT NOT NULL DEFAULT '',
            UNIQUE(customer_id, rec_id, system)
        );
        CREATE INDEX IF NOT EXISTS idx_finding_tickets_customer
            ON finding_tickets(customer_id);
        """,
    ),
]


# ── Connection helpers ───────────────────────────────────────────────────────

# Journal mode is a property of the *database file*, not of a connection: once
# a database is in WAL it stays in WAL until something changes it back. Running
# `PRAGMA journal_mode=WAL` on every connection therefore bought nothing and
# cost ~0.56 ms a time — measured at 43% of the whole open/close cycle, on an
# authenticated request that opens four of them. Set it once per process
# instead, when the schema is prepared.
_journal_mode_set_for: str | None = None


async def _ensure_journal_mode(conn: aiosqlite.Connection) -> None:
    """Put the database into WAL mode once per process, per database file."""
    global _journal_mode_set_for
    path = str(DB_PATH)
    if _journal_mode_set_for == path:
        return
    await conn.execute("PRAGMA journal_mode=WAL")
    _journal_mode_set_for = path
    logger.debug("journal_mode=WAL applied to %s", path)


# Every connection whose worker thread may be running, from before the thread
# can start until the connection is disposed, mapped to the loop that opened
# it. A pool alone cannot cover this: aiosqlite starts the thread inside
# ``__await__``, so a connection is live for the whole of the connect handshake
# before any pool has a reference to it, and a task abandoned in that window is
# unreachable from everything else in this module. See _get_connection().
class _Opened(NamedTuple):
    """Who opened a connection, so teardown can tell an orphan from a borrow.

    ``task`` is the task that was inside the connect handshake. While it is
    still pending, the connection is not an orphan however it looks from here —
    that task is going to be handed the connection. Once it is done or
    cancelled without the connection reaching a pool, nothing will ever claim
    it, and it is safe to stop.
    """

    loop: asyncio.AbstractEventLoop
    task: Optional[asyncio.Task]


_started: dict[aiosqlite.Connection, _Opened] = {}


async def _get_connection() -> aiosqlite.Connection:
    """Open a new connection with the per-connection pragmas applied."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Registered *before* it is awaited, because awaiting is what starts the
    # worker thread. If the loop stops while a task is suspended here — a
    # backgrounded write whose request finished first, say — that task is never
    # resumed, so ``_connection`` is never assigned. aiosqlite's __del__ bails
    # out early in exactly that case:
    #
    #     def __del__(self):
    #         if self._connection is None:
    #             return
    #
    # …so nothing ever stops the thread, and it sits on its queue forever.
    # Being non-daemon, it then blocks interpreter exit indefinitely — a suite
    # that reports all tests passed and never returns to the shell. Holding the
    # reference here is what lets teardown find it anyway.
    conn = aiosqlite.connect(str(DB_PATH), timeout=30)
    _started[conn] = _Opened(asyncio.get_running_loop(), asyncio.current_task())
    try:
        await conn
        conn.row_factory = aiosqlite.Row
        await _ensure_journal_mode(conn)
        # Both of these are per-connection settings and must be re-applied each
        # time — unlike journal_mode above. Together they cost ~0.25 ms.
        #
        # wal_autocheckpoint caps WAL growth: SQLite checkpoints into the main
        # DB after this many pages of write-ahead log. Default is 1000 (~4 MiB
        # at 4 KiB pages). Without it the .db-wal file can grow unbounded
        # between explicit checkpoints and slow recovery on power loss.
        await conn.execute("PRAGMA wal_autocheckpoint=1000")
        await conn.execute("PRAGMA foreign_keys=ON")
    except BaseException:
        # Failed or cancelled with the thread already running, and no caller
        # holds the connection to close it. Includes CancelledError, hence
        # BaseException rather than Exception.
        _stop_connection(conn)
        raise
    return conn


# ── Connection pool ──────────────────────────────────────────────────────────
#
# Opening a connection costs ~0.5 ms, and an authenticated request makes four
# database calls, so the open/close cycle was a measurable share of every
# request. Reusing connections removes that — but a pool has to earn its
# keep against three hazards, all of which have bitten this codebase:
#
#   1. Loop affinity. An aiosqlite connection dispatches results back to the
#      event loop that created it. Handing one to a different loop raises
#      "Event loop is closed". Tests get a fresh loop per test, so the pool is
#      keyed on the running loop and rebuilt when it changes.
#   2. Path changes. Tests reassign DB_PATH per test, and MSP_DATA_DIR can
#      point elsewhere; the pool is keyed on the path too, so a connection to
#      the previous database is never served.
#   3. Leaked threads. aiosqlite starts one non-daemon thread per connection,
#      so an undisposed connection blocks interpreter exit forever — that is
#      exactly what wedged CI on this branch. Every path out of the pool
#      terminates the thread: close() when the loop is alive, and stop() —
#      which is synchronous and needs no loop — when it is not. The pool is
#      not sufficient on its own, though: a connection is already running its
#      thread before acquire() has a reference to it, so ownership starts at
#      the _started registry above, not here.

_POOL_SIZE = max(1, int(os.environ.get("MSP_DB_POOL_SIZE", "5")))


class _ConnectionPool:
    """A small pool of aiosqlite connections bound to one path and one loop."""

    def __init__(self, path: str, loop: asyncio.AbstractEventLoop, max_size: int) -> None:
        self.path = path
        self.loop = loop
        self._idle: list[aiosqlite.Connection] = []
        self._live: set[aiosqlite.Connection] = set()
        self._slots = asyncio.Semaphore(max_size)
        self._closed = False

    def matches(self, path: str, loop: asyncio.AbstractEventLoop) -> bool:
        return not self._closed and self.path == path and self.loop is loop

    async def acquire(self) -> aiosqlite.Connection:
        """Take an idle connection, or open one. Blocks when all slots are out."""
        await self._slots.acquire()
        try:
            if self._idle:
                return self._idle.pop()
            conn = await _get_connection()
            self._live.add(conn)
            return conn
        except BaseException:
            self._slots.release()
            raise

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Return a connection to the pool, or dispose it if it is unusable."""
        try:
            if self._closed:
                await self._dispose(conn)
                return
            # A borrower that raised — or simply forgot to commit — must not
            # hand its open transaction to whoever picks this connection up
            # next. Roll back; if even that fails, the connection is suspect,
            # so drop it rather than recycle it.
            try:
                if conn.in_transaction:
                    await conn.rollback()
            except Exception as e:
                logger.warning("Discarding pooled connection after failed rollback: %s", e)
                await self._dispose(conn)
                return
            self._idle.append(conn)
        finally:
            self._slots.release()

    async def _dispose(self, conn: aiosqlite.Connection) -> None:
        self._live.discard(conn)
        try:
            await conn.close()
        except Exception as e:
            logger.debug("close() failed on pooled connection, stopping thread: %s", e)
            _stop_connection(conn)
            return
        finally:
            # In a finally, not after the await: cancellation here is not an
            # Exception, so it would skip the deregistration while _live has
            # already let go — leaving an entry no pool vouches for and no
            # sweep on a live loop will collect. aiosqlite's close() stops the
            # worker from its own finally, so the thread does exit; what
            # leaked was this dict entry, pinning a Connection and a loop for
            # the life of the process.
            _started.pop(conn, None)

    async def close(self) -> None:
        """Close idle connections; those still checked out go on release."""
        self._closed = True
        idle, self._idle = self._idle, []
        for conn in idle:
            await self._dispose(conn)

    def abandon(self) -> None:
        """Terminate every connection without needing a live event loop.

        Used when the pool's loop has gone away, where awaiting close() is
        impossible. _stop_connection() covers that case: the worker closes its
        handle and breaks out of its loop without touching the dead loop, which
        is what stops the thread from outliving the process.
        """
        self._closed = True
        for conn in list(self._live):
            _stop_connection(conn)
        self._live.clear()
        self._idle.clear()


def _stop_connection(conn: aiosqlite.Connection) -> None:
    """Terminate a connection's worker thread, whatever state its loop is in.

    aiosqlite's stop() builds a future on ``asyncio.get_event_loop()`` when it
    can find one, and the worker posts the result back to that loop:

        try:
            future = asyncio.get_event_loop().create_future()
        except Exception:
            future = None
        self._tx.put_nowait((future, close_and_stop))

    Nothing here ever awaits that future — teardown is synchronous — so the
    only thing it can do is go wrong. If the loop closes before the worker
    posts, the post raises inside the thread, the worker dies by exception
    instead of on the stop sentinel, and pytest reports an unhandled thread
    exception. Teardown closing a loop promptly is the normal case, not the
    exotic one, which is why that warning was a permanent fixture of this suite.

    So take the future-less branch every time, by calling stop() from a
    throwaway thread: a fresh thread has no running loop and no loop set, so
    get_event_loop() raises there and aiosqlite enqueues (None, close_and_stop).
    The worker closes the handle and breaks out of its loop without touching
    anything external. Masking the loop in *this* thread would not do — while a
    loop is running, get_event_loop() returns it regardless of set_event_loop().
    """
    _started.pop(conn, None)

    stopper = threading.Thread(
        target=_call_stop, args=(conn,), name="aiosqlite-stop", daemon=True
    )
    try:
        stopper.start()
    except RuntimeError:
        # No new threads during interpreter shutdown. Stopping in-line may
        # queue a future the worker cannot post to, but a noisy teardown beats
        # not stopping the thread at all.
        _call_stop(conn)
        return
    # Joined so the sentinel is definitely queued before the caller moves on —
    # callers such as abandon() treat the connection as finished on return.
    stopper.join(timeout=5)


def _call_stop(conn: aiosqlite.Connection) -> None:
    try:
        conn.stop()
    except Exception as e:  # pragma: no cover - best-effort teardown
        logger.debug("Failed to stop aiosqlite worker thread: %s", e)


# One pool per event loop, not one pool overall. More than one loop is
# routine: Starlette's TestClient drives the app on its own loop in a worker
# thread while the calling code uses another, and anything run via
# asyncio.run() in a thread adds more. A single pool would be torn down and
# rebuilt on every alternation between them — measured at roughly double the
# runtime of the web tests before this was keyed per loop.
_pools: dict[asyncio.AbstractEventLoop, _ConnectionPool] = {}


def _sweep_orphans(*, only_dead_loops: bool) -> None:
    """Terminate started connections that no pool ever took ownership of.

    An orphan is a connection that was opened but never made it into a pool —
    the caller was cancelled, or its loop stopped, somewhere between the worker
    thread starting and the hand-off in acquire(). Nothing else will ever close
    it, so its non-daemon thread would otherwise outlive the process.

    Two things make a started connection safe to stop: no pool vouches for it,
    and whoever opened it can no longer finish. The second is what the recorded
    task answers. A pending task on a *running* loop is still inside the
    handshake and is going to be handed this connection, so stopping it would
    break a caller in flight — it fails its next statement with "no active
    connection". A done or cancelled task will never claim it, and a closed
    loop settles the question outright.

    The loop must be checked for running, not merely for open. A loop whose
    run_until_complete() has returned is neither: its tasks stay pending
    forever and is_closed() is False, so a pending task there protected a
    connection nothing would ever claim — the non-daemon thread survived and
    blocked interpreter exit, which is the failure this registry exists to
    prevent. Requiring is_running() keeps the in-flight case safe (the only
    caller that sweeps a live loop, close_all_pools, runs inside a coroutine on
    it) while letting a parked loop's connections go.

    ``only_dead_loops`` narrows this further to closed loops alone. It is not
    needed for correctness now that the task is tracked; it stays because the
    application-facing path has no reason to touch a live loop's connections at
    all, and the narrowest teardown that works is the one to run in production.

    Both collections are snapshotted before iterating. ``_pools`` is keyed by
    loop and reachable from any thread that runs one, so a bare comprehension
    over it can raise "dictionary changed size during iteration" mid-teardown.
    """
    with _pools_lock:
        owned = {conn for pool in _pools.values() for conn in list(pool._live)}
    for conn, opened in list(_started.items()):
        if conn in owned:
            continue
        if opened.loop.is_closed():
            _stop_connection(conn)
            continue
        if only_dead_loops:
            continue
        # Open loop: an orphan unless someone is still opening it, which
        # requires both a pending task and a loop actually driving it.
        if (
            opened.task is not None
            and not opened.task.done()
            and opened.loop.is_running()
        ):
            continue
        _stop_connection(conn)


# _pools is read and written from every thread that runs a loop, so each
# read-decide-remove sequence has to be atomic. It is an RLock because
# _current_pool() takes it and then calls _prune_dead_pools(), which takes it
# again. Nothing in here awaits while holding it: an asyncio.Lock would bind to
# whichever loop touched it first, which is the affinity problem _pools is keyed
# by loop to avoid in the first place.
#
# Pools are always abandoned *after* the lock is released. abandon() joins a
# worker thread with a timeout, and holding a process-wide lock across that
# would let one slow teardown stall every other loop.
_pools_lock = threading.RLock()


def _prune_dead_pools() -> None:
    """Abandon pools whose loop has closed, so their threads don't outlive it."""
    with _pools_lock:
        dead = [loop for loop in _pools if loop.is_closed()]
        # pop, not del: another thread may have reaped the same entry between
        # the scan and here, and only the caller that actually removed a pool
        # may abandon it — otherwise two threads stop the same connections.
        pools = [p for p in (_pools.pop(loop, None) for loop in dead) if p is not None]
    for pool in pools:
        pool.abandon()
    _sweep_orphans(only_dead_loops=True)


_restore_in_progress = False


def enter_restore_mode() -> None:
    """Block new database access while a backup restore swaps the DB file.

    close_pool() alone is not a durable quiesce: the next get_db() would lazily
    rebuild a pool and reopen the very file the restore is moving. With this set
    _current_pool refuses, so nothing reopens the database mid-swap (SR-003 #8).

    Scope this narrowly around the swap and pair it with exit_restore_mode() in
    a finally: a restore that fails and rolls the data fully back leaves the
    original database in place and safe to reopen, so leaving the flag latched
    would brick the whole app until a restart for no reason (SR-003 review)."""
    global _restore_in_progress
    _restore_in_progress = True


def exit_restore_mode() -> None:
    """Re-enable database access after a restore's swap window closes.

    Safe to call on both the success and the rollback path: in either case the
    file at DB_PATH is a complete, consistent database (the freshly restored one
    or the original put back), so a rebuilt pool will open a valid file."""
    global _restore_in_progress
    _restore_in_progress = False


def _current_pool() -> _ConnectionPool:
    """Return the pool for the running loop and current DB_PATH.

    Contains no await, so it is atomic against other coroutines on this loop;
    _pools_lock covers the other threads.
    """
    if _restore_in_progress:
        raise RuntimeError(
            "Databasen gjenopprettes fra en backup — start applikasjonen på nytt."
        )
    loop = asyncio.get_running_loop()
    path = str(DB_PATH)

    with _pools_lock:
        pool = _pools.get(loop)
        if pool is not None and pool.matches(path, loop):
            return pool

    _prune_dead_pools()

    with _pools_lock:
        # Re-read: another thread may have pruned or replaced this loop's entry
        # while the lock was released above.
        existing = _pools.get(loop)
        if existing is not None and existing.matches(path, loop):
            return existing
        stale = _pools.pop(loop, None)
        pool = _ConnectionPool(path, loop, _POOL_SIZE)
        _pools[loop] = pool

    if stale is not None:
        # Same loop, different database (tests reassign DB_PATH, and
        # MSP_DATA_DIR can move it) — the old connections point at the wrong
        # file, so retire them. Safe to abandon unlocked: this loop is the only
        # one that could have been borrowing from it, and it is us.
        stale.abandon()
    return pool


async def close_pool() -> None:
    """Dispose the running loop's pool. Called on application shutdown."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    with _pools_lock:
        pool = _pools.pop(loop, None)
    if pool is not None:
        await pool.close()
    _prune_dead_pools()


async def close_all_pools() -> None:
    """Await proper closure of every pool belonging to the running loop.

    Prefer this over ``reset_pools_for_tests()`` wherever a loop is available.
    The synchronous path can only fire stop() and return, so if the loop is
    torn down before the worker thread posts its result, that post lands on a
    closed loop and the thread dies by exception. Awaiting close() removes the
    race entirely.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        reset_pools_for_tests()
        return

    # Before the pools are dismantled, while they still vouch for the
    # connections they hold — otherwise a connection legitimately checked out
    # of a pool would look like an orphan and be stopped under its borrower.
    _sweep_orphans(only_dead_loops=False)

    with _pools_lock:
        mine = _pools.pop(loop, None)
    if mine is not None:
        await mine.close()

    # A pool on another loop cannot be awaited from here, so it gets the
    # synchronous treatment — but only if that loop has stopped. Reaping a
    # *running* foreign loop's pool stops connections a live thread is
    # borrowing, and its next statement then waits on a worker that has already
    # taken the stop sentinel: that thread hangs forever, and being non-daemon
    # it blocks interpreter exit. Whoever owns a running loop closes its own
    # pool; there is nothing here to clean up on its behalf.
    with _pools_lock:
        reapable = [
            other for other in _pools
            if other is not loop and not other.is_running()
        ]
        pools = [p for p in (_pools.pop(o, None) for o in reapable) if p is not None]
    for pool in pools:
        pool.abandon()


def reset_pools_for_tests() -> None:
    """Drop every pool synchronously, terminating all worker threads.

    Sweeps orphans unconditionally rather than only on closed loops. A test's
    loop is usually still open when its teardown runs, and nothing is going to
    reclaim an orphan afterwards — the suite would carry it to the end of the
    session and hang on exit.
    """
    _sweep_orphans(only_dead_loops=False)
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.abandon()


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields a pooled database connection."""
    pool = _current_pool()
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        await pool.release(conn)


# ── Migration runner ─────────────────────────────────────────────────────────

async def _current_version(conn: aiosqlite.Connection) -> int:
    """Return the current schema version, or 0 if the table doesn't exist."""
    try:
        async with conn.execute("SELECT version FROM schema_version WHERE id = 1") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
    except aiosqlite.OperationalError:
        return 0


async def run_migrations() -> None:
    """Apply any pending schema migrations, each inside its own transaction.

    If a migration fails partway through, its changes are rolled back so the
    database never ends up in a half-migrated state. The exception is
    re-raised so startup fails loudly rather than silently leaving a stale
    schema behind.
    """
    async with get_db() as conn:
        current = await _current_version(conn)

        for version, description, body in _MIGRATIONS:
            if version <= current:
                continue

            logger.info("Applying migration %d: %s", version, description)
            try:
                # executescript() issues its own COMMIT, so we cannot wrap the
                # whole migration in a single BEGIN..COMMIT. Instead: run the
                # DDL (which auto-commits), then update schema_version inside
                # an explicit transaction. If the version bump fails we roll
                # back — the migration will be re-attempted next boot, so every
                # migration body must be re-runnable (CREATE TABLE IF NOT
                # EXISTS, or an explicit schema check before ALTER).
                if callable(body):
                    await body(conn)
                    await conn.commit()
                else:
                    await conn.executescript(body)
                await conn.execute("BEGIN")
                await conn.execute(
                    "UPDATE schema_version SET version = ? WHERE id = 1",
                    (version,),
                )
                await conn.commit()
            except Exception:
                try:
                    await conn.rollback()
                except Exception:
                    pass
                logger.exception(
                    "Migration %d (%s) failed — database left at version %d",
                    version, description, current,
                )
                raise
            current = version

        if current < SCHEMA_VERSION:
            logger.warning(
                "Schema version %d is behind target %d — missing migrations?",
                current,
                SCHEMA_VERSION,
            )
        else:
            logger.debug("Database schema is at version %d", current)


# ── Initialisation ───────────────────────────────────────────────────────────

async def init_db() -> None:
    """Initialise the database and apply all pending migrations.

    Call this once during application startup.
    """
    await run_migrations()
    logger.info("Database ready at %s", DB_PATH)
