"""SQLite database module for MSP Toolkit.

Provides async database access via aiosqlite with schema versioning and
automatic migration.  New relational data (users, sessions, SSH hosts/keys,
VPN profiles) lives here; existing encrypted JSON files remain unchanged.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

from app.core.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "msp_toolkit.db"

# Current schema version — bump this when adding migrations.
SCHEMA_VERSION = 14

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


async def _get_connection() -> aiosqlite.Connection:
    """Open a new connection with the per-connection pragmas applied."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(DB_PATH), timeout=30)
    conn.row_factory = aiosqlite.Row
    await _ensure_journal_mode(conn)
    # Both of these are per-connection settings and must be re-applied each
    # time — unlike journal_mode above. Together they cost ~0.25 ms.
    #
    # wal_autocheckpoint caps WAL growth: SQLite checkpoints into the main DB
    # after this many pages of write-ahead log. Default is 1000 (~4 MiB at
    # 4 KiB pages). Without it the .db-wal file can grow unbounded between
    # explicit checkpoints and slow recovery on power loss.
    await conn.execute("PRAGMA wal_autocheckpoint=1000")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields a database connection."""
    conn = await _get_connection()
    try:
        yield conn
    finally:
        await conn.close()


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
