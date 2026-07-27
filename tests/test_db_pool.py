"""Tests for the SQLite connection pool.

The pool exists to stop paying ~0.5 ms of connection setup on every database
call. Its hazards are what these tests are mostly about: aiosqlite binds a
connection to the loop that created it and starts a non-daemon thread per
connection, so a pool that outlives its loop — or simply forgets to dispose —
hangs interpreter exit. That failure has already wedged CI once on this
branch, hence the explicit thread-accounting tests below.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

import app.core.database as db
from app.core.database import (
    _POOL_SIZE,
    _current_pool,
    _pools,
    close_all_pools,
    close_pool,
    get_db,
    reset_pools_for_tests,
    run_migrations,
)


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    db.DB_PATH = tmp_path / "pool.db"
    reset_pools_for_tests()
    await run_migrations()
    yield
    # Awaited, not fired-and-forgotten: this teardown runs while the loop is
    # still alive, and the synchronous path would let the loop close before the
    # worker thread posts its result.
    await close_all_pools()


async def _scalar(conn, sql="SELECT 1"):
    async with conn.execute(sql) as cur:
        return (await cur.fetchone())[0]


# ---------------------------------------------------------------------------
# Reuse — the entire point
# ---------------------------------------------------------------------------


async def test_sequential_acquires_reuse_one_connection():
    seen = []
    for _ in range(5):
        async with get_db() as conn:
            assert await _scalar(conn) == 1
            seen.append(id(conn))
    assert len(set(seen)) == 1, "sequential borrows should reuse the same connection"


async def test_pool_opens_more_than_one_only_under_concurrency():
    async def borrow(hold: asyncio.Event, ready: asyncio.Event):
        async with get_db() as conn:
            ready.set()
            await hold.wait()
            return id(conn)

    hold = asyncio.Event()
    readies = [asyncio.Event() for _ in range(3)]
    tasks = [asyncio.create_task(borrow(hold, r)) for r in readies]
    await asyncio.gather(*(r.wait() for r in readies))
    hold.set()
    ids = await asyncio.gather(*tasks)

    assert len(set(ids)) == 3, "concurrent borrowers must not share a connection"


async def test_connections_are_returned_after_use():
    pool = None
    async with get_db() as conn:
        pool = _current_pool()
        assert conn not in pool._idle, "a checked-out connection must not be idle"
    assert len(pool._idle) == 1


# ---------------------------------------------------------------------------
# Transaction hygiene between borrowers
# ---------------------------------------------------------------------------


async def test_uncommitted_write_is_rolled_back_before_reuse():
    """A borrower that forgets to commit must not leak its transaction."""
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO app_secrets (key, value) VALUES ('leaked', 'x')"
        )
        assert conn.in_transaction

    async with get_db() as conn:
        assert not conn.in_transaction, "next borrower inherited an open transaction"
        async with conn.execute(
            "SELECT COUNT(*) FROM app_secrets WHERE key = 'leaked'"
        ) as cur:
            assert (await cur.fetchone())[0] == 0, "uncommitted row should be gone"


async def test_exception_inside_the_block_still_returns_the_connection():
    pool = _current_pool()
    with pytest.raises(RuntimeError):
        async with get_db() as conn:
            await conn.execute("INSERT INTO app_secrets (key, value) VALUES ('x','y')")
            raise RuntimeError("boom")

    # Connection is back, clean, and usable.
    assert len(pool._idle) == 1
    async with get_db() as conn:
        assert not conn.in_transaction
        assert await _scalar(conn) == 1


async def test_committed_write_survives_reuse():
    async with get_db() as conn:
        await conn.execute("INSERT INTO app_secrets (key, value) VALUES ('kept','v')")
        await conn.commit()

    async with get_db() as conn, conn.execute(
        "SELECT value FROM app_secrets WHERE key = 'kept'"
    ) as cur:
        assert (await cur.fetchone())[0] == "v"


# ---------------------------------------------------------------------------
# Bounding and fairness
# ---------------------------------------------------------------------------


async def test_pool_size_is_bounded_and_does_not_deadlock():
    """More concurrent borrowers than slots: excess wait, none fail."""
    n = _POOL_SIZE * 3

    async def borrow(i):
        async with get_db() as conn:
            await asyncio.sleep(0)
            return await _scalar(conn, f"SELECT {i}")

    results = await asyncio.wait_for(
        asyncio.gather(*(borrow(i) for i in range(n))), timeout=30
    )
    assert results == list(range(n))
    assert len(_current_pool()._live) <= _POOL_SIZE


# ---------------------------------------------------------------------------
# Keying: per loop, per database path
# ---------------------------------------------------------------------------


async def test_changing_db_path_retires_the_old_pool(tmp_path):
    async with get_db() as conn:
        assert await _scalar(conn) == 1
    first = _current_pool()

    db.DB_PATH = tmp_path / "other.db"
    await run_migrations()
    async with get_db() as conn:
        assert await _scalar(conn) == 1
    second = _current_pool()

    assert second is not first
    assert second.path != first.path
    assert not first._live, "connections to the old database should be disposed"


def test_each_event_loop_gets_its_own_pool():
    """Regression: a single global pool thrashed when two loops alternated.

    TestClient drives the app on its own loop while the calling test uses
    another, so rebuilding on every switch doubled the web tests' runtime.
    """
    reset_pools_for_tests()
    pool_ids = []

    async def touch():
        async with get_db() as conn:
            await _scalar(conn)
        pool_ids.append(id(_current_pool()))
        return asyncio.get_running_loop()

    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        loop_a.run_until_complete(touch())
        loop_b.run_until_complete(touch())
        assert len(set(pool_ids)) == 2, "each loop should hold its own pool"
        assert len(_pools) == 2
    finally:
        reset_pools_for_tests()
        loop_a.close()
        loop_b.close()


def test_pools_for_closed_loops_are_pruned():
    reset_pools_for_tests()

    async def touch():
        async with get_db() as conn:
            await _scalar(conn)

    dead = asyncio.new_event_loop()
    dead.run_until_complete(touch())
    dead.close()
    assert len(_pools) == 1

    alive = asyncio.new_event_loop()
    try:
        alive.run_until_complete(touch())
        # Touching from a live loop prunes the dead one and keeps only its own.
        assert len(_pools) == 1
        assert next(iter(_pools)) is alive
    finally:
        reset_pools_for_tests()
        alive.close()


# ---------------------------------------------------------------------------
# Disposal — no thread may outlive the pool
# ---------------------------------------------------------------------------


def _sqlite_threads() -> int:
    return sum(1 for t in threading.enumerate() if t.is_alive())


async def _settle(deadline: float = 5.0) -> None:
    """Give worker threads a moment to exit after being told to stop."""
    step, waited = 0.02, 0.0
    while waited < deadline:
        await asyncio.sleep(step)
        waited += step


async def test_close_pool_leaves_no_live_connections():
    async with get_db() as conn:
        assert await _scalar(conn) == 1
    pool = _current_pool()
    assert pool._live

    await close_pool()
    assert not pool._live
    assert not pool._idle


async def test_disposal_terminates_worker_threads():
    """Regression: leaked non-daemon aiosqlite threads hang interpreter exit."""
    reset_pools_for_tests()
    await _settle(0.3)
    before = _sqlite_threads()

    # Force several connections open at once.
    async def borrow(hold, ready):
        async with get_db():
            ready.set()
            await hold.wait()

    hold = asyncio.Event()
    readies = [asyncio.Event() for _ in range(_POOL_SIZE)]
    tasks = [asyncio.create_task(borrow(hold, r)) for r in readies]
    await asyncio.gather(*(r.wait() for r in readies))
    during = _sqlite_threads()
    assert during > before, "expected a worker thread per open connection"
    hold.set()
    await asyncio.gather(*tasks)

    await close_pool()
    await _settle(1.0)

    after = _sqlite_threads()
    assert after <= before, (
        f"worker threads leaked: {before} before, {during} during, {after} after"
    )


def test_abandon_stops_threads_without_a_running_loop():
    """The dead-loop path: stop() must work with no loop to await on."""
    reset_pools_for_tests()
    before = _sqlite_threads()

    async def touch():
        async with get_db() as conn:
            await _scalar(conn)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(touch())
    loop.close()  # pool's loop is now gone; close() could not be awaited

    reset_pools_for_tests()  # must fall back to the synchronous stop()

    threading.Event().wait(1.0)
    assert _sqlite_threads() <= before, "threads outlived their closed loop"


def test_abandon_after_close_does_not_raise_inside_the_worker():
    """Regression: the worker died by exception instead of on the sentinel.

    Closing a loop does not unset it for the thread, so aiosqlite's stop()
    would hand the worker a future on a closed loop; posting to it raised in
    the thread. The connection still closed, but it surfaced as an unhandled
    thread exception — noisy, and the kind of thing people learn to ignore.
    """
    reset_pools_for_tests()
    errors: list[BaseException] = []
    original_hook = threading.excepthook

    def _record(args):
        errors.append(args.exc_value)
        original_hook(args)

    threading.excepthook = _record
    try:
        async def touch():
            async with get_db() as conn:
                await _scalar(conn)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(touch())
        loop.close()

        reset_pools_for_tests()
        threading.Event().wait(1.0)
    finally:
        threading.excepthook = original_hook

    assert not errors, f"worker thread raised during teardown: {errors!r}"


async def test_close_pool_is_safe_to_call_twice():
    async with get_db() as conn:
        await _scalar(conn)
    await close_pool()
    await close_pool()  # must not raise


def test_reset_pools_is_safe_when_empty():
    reset_pools_for_tests()
    reset_pools_for_tests()  # must not raise
