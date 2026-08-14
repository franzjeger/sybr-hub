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
from app.core.utils import fire_and_forget


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


# ---------------------------------------------------------------------------
# Connections abandoned mid-connect — owned by no pool at all
# ---------------------------------------------------------------------------


def test_task_abandoned_while_connecting_does_not_leak_its_thread():
    """Regression: the suite passed every test, then never exited.

    A backgrounded write outlives the request that fired it. If the loop stops
    while that task is still inside aiosqlite.connect(), the task is never
    resumed, so Connection._connection is never assigned — and aiosqlite's
    __del__ returns early precisely when _connection is None, without stopping
    the worker thread. The thread stays parked on its queue, and because it is
    non-daemon, Python's shutdown blocks joining it forever.

    The pool cannot catch this on its own: the thread starts inside __await__,
    so the connection is live for the whole handshake before acquire() has a
    reference to it. Hence the registry that _get_connection() writes to before
    it awaits.
    """
    reset_pools_for_tests()
    before = _sqlite_threads()

    async def background():
        async with get_db() as conn:
            await _scalar(conn)

    async def fire():
        fire_and_forget(background())
        await asyncio.sleep(0)  # let it start and block on the connect future

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(fire())
        # The loop has stopped but is not yet closed — the ordinary teardown
        # window. The worker finishes sqlite3.connect() and posts its result
        # successfully, then parks; the callback that would resume the task
        # never runs. This is the timing that hung, and it is a race, so the
        # wait is what makes the test reproduce it rather than pass by luck.
        threading.Event().wait(0.3)
    finally:
        loop.close()

    assert db._started, "the connection should still be registered to be found"

    reset_pools_for_tests()
    threading.Event().wait(1.0)

    assert _sqlite_threads() <= before, "abandoned connect leaked a worker thread"
    assert not db._started, "registry should be empty once everything is stopped"


def test_failure_after_connect_stops_the_thread():
    """A pragma that fails leaves the connection owned by nobody."""
    reset_pools_for_tests()
    before = _sqlite_threads()

    async def boom(conn):
        raise RuntimeError("pragma failed")

    original = db._ensure_journal_mode
    db._ensure_journal_mode = boom

    async def borrow():
        with pytest.raises(RuntimeError):
            async with get_db():
                pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(borrow())
    finally:
        db._ensure_journal_mode = original
        loop.close()

    threading.Event().wait(1.0)
    assert _sqlite_threads() <= before, "failed setup leaked a worker thread"
    assert not db._started


async def test_pool_registry_is_emptied_by_normal_disposal():
    """The registry must not accumulate — it holds strong references."""
    async with get_db() as conn:
        await _scalar(conn)
    assert db._started, "an open connection should be registered"

    await close_pool()
    assert not db._started, "close_pool should deregister what it disposed"


async def test_sweep_spares_a_connection_that_is_checked_out():
    """An in-flight borrow must not be mistaken for an orphan."""
    async with get_db() as conn:
        # A sweep from another teardown path must leave this one alone: it is
        # owned by a live pool and its borrower is still using it.
        db._sweep_orphans(only_dead_loops=False)
        assert await _scalar(conn) == 1


async def test_close_pool_is_safe_to_call_twice():
    async with get_db() as conn:
        await _scalar(conn)
    await close_pool()
    await close_pool()  # must not raise


async def test_restore_mode_blocks_new_database_access():
    """A backup restore must durably quiesce the database.

    close_pool() alone is not enough: the next get_db() would lazily rebuild the
    pool and reopen the very file the restore is swapping underneath it. The
    maintenance flag makes any new borrow raise instead, so nothing reopens the
    database mid-swap (SR-003 review, HIGH).
    """
    try:
        db.enter_restore_mode()
        with pytest.raises(RuntimeError):
            _current_pool()
        with pytest.raises(RuntimeError):
            async with get_db():
                pass
        # And the quiesce is scoped, not a one-way latch: lifting it (as the
        # restore route's finally does on both success and rollback) re-enables
        # access, so a rolled-back restore does not brick the app until restart.
        db.exit_restore_mode()
        async with get_db() as conn:
            assert await _scalar(conn) == 1
    finally:
        db._restore_in_progress = False


def test_reset_pools_is_safe_when_empty():
    reset_pools_for_tests()
    reset_pools_for_tests()  # must not raise


async def test_sweep_spares_a_connection_that_is_still_being_opened():
    """An unconditional sweep must not shoot a borrower mid-handshake.

    ``test_sweep_spares_a_connection_that_is_checked_out`` only covers the
    already-acquired case, where a pool vouches for the connection. The window
    the registry exists for is earlier than that: between the worker thread
    starting and the hand-off in acquire(), nothing owns the connection, so it
    looked exactly like an orphan. Both unconditional callers —
    close_all_pools() and reset_pools_for_tests() — run on a live loop, and
    sweeping there stopped the connection under the task still opening it,
    which then failed with "no active connection".
    """
    released = asyncio.Event()
    swept = asyncio.Event()

    async def borrower():
        # Suspends inside _get_connection with the connection registered but
        # not yet owned by any pool.
        conn = await db._get_connection()
        await released.wait()
        return await (await conn.execute("SELECT 1")).fetchone()

    original = db._ensure_journal_mode

    async def _park(conn):
        await original(conn)
        swept.set()
        await released.wait()

    db._ensure_journal_mode = _park
    try:
        task = asyncio.create_task(borrower())
        await asyncio.wait_for(swept.wait(), timeout=5)

        # Registered, and no pool has it.
        assert any(c not in {x for p in db._pools.values() for x in p._live}
                   for c in db._started), "expected a connection mid-handshake"

        db._sweep_orphans(only_dead_loops=False)

        released.set()
        row = await asyncio.wait_for(task, timeout=5)
        assert row[0] == 1, "the sweep stopped a connection that was still being opened"
    finally:
        db._ensure_journal_mode = original
        released.set()


async def test_cancelled_disposal_still_deregisters():
    """Cancellation must not strand an entry in the registry.

    _dispose discards from _live first and deregistered after the await, under
    `except Exception` — which CancelledError is not. The connection then
    belonged to no pool and sat in _started forever, where the only sweep a
    running application performs (dead loops only) will never look. aiosqlite
    stops the worker from its own finally, so no thread leaked; what leaked was
    a Connection and an event loop pinned for the life of the process.
    """
    pool = _current_pool()
    conn = await pool.acquire()
    assert conn in db._started

    async def slow_close():
        # Mirror what aiosqlite's own close() guarantees in its finally before
        # anything can be cancelled — otherwise the worker thread only survives
        # this test by GC calling __del__, and the test would be asserting
        # refcount timing rather than the teardown path production relies on.
        conn._connection = None
        conn.stop()
        await asyncio.sleep(3600)

    conn.close = slow_close
    task = asyncio.create_task(pool._dispose(conn))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert conn not in db._started, "cancelled disposal left the connection registered"
    assert conn not in pool._live


def test_sweep_reclaims_a_task_parked_on_a_stopped_but_open_loop():
    """A pending task only protects a connection while its loop is running.

    ``test_task_abandoned_while_connecting_does_not_leak_its_thread`` closes the
    loop before sweeping, which settles the question outright. The harder case
    is the one reset_pools_for_tests() actually documents — teardown running
    while the test's loop is stopped but still open. There the task stays
    pending forever and is_closed() is False, so keying only on task.done()
    spared a connection nobody would ever claim, and its non-daemon thread went
    on blocking interpreter exit.
    """
    reset_pools_for_tests()
    before = _sqlite_threads()

    async def background():
        async with get_db() as conn:
            await _scalar(conn)

    async def fire():
        fire_and_forget(background())
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(fire())
        threading.Event().wait(0.3)

        # Deliberately NOT closed: stopped, open, task still pending.
        assert not loop.is_closed()
        assert not loop.is_running()
        assert db._started, "expected a connection registered to the parked loop"

        reset_pools_for_tests()
        threading.Event().wait(1.0)

        assert not db._started, "sweep spared a connection on a loop that had stopped"
        assert _sqlite_threads() <= before, "parked loop leaked a worker thread"
    finally:
        loop.close()
        reset_pools_for_tests()


async def test_close_all_pools_leaves_a_running_loops_pool_alone():
    """Reaping a live foreign loop's pool hangs the thread that owns it.

    close_all_pools() used to abandon every pool that was not its own, on the
    reasoning that another loop "is not the one about to close underneath
    them". That holds only if the other loop has stopped. Abandon a running
    one and its borrower's next statement waits on a worker that has already
    taken the stop sentinel — the thread blocks forever, and being non-daemon
    it takes interpreter exit with it.
    """
    started = threading.Event()
    finish = threading.Event()
    foreign: dict = {}

    def run_foreign():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def hold():
            foreign["pool"] = _current_pool()
            foreign["loop"] = asyncio.get_running_loop()
            started.set()
            while not finish.is_set():
                await asyncio.sleep(0.01)

        try:
            loop.run_until_complete(hold())
        finally:
            loop.close()

    thread = threading.Thread(target=run_foreign, name="foreign-loop")
    thread.start()
    try:
        assert started.wait(timeout=5)
        assert _pools.get(foreign["loop"]) is foreign["pool"]

        await close_all_pools()

        assert _pools.get(foreign["loop"]) is foreign["pool"], (
            "close_all_pools reaped a pool whose loop is still running"
        )
        assert not foreign["pool"]._closed
    finally:
        finish.set()
        thread.join(timeout=5)
        # The foreign pool was spared on purpose, and its loop is closed now —
        # nothing else in this test's teardown owns it, so reclaim it here or
        # its worker thread outlives the session and hangs interpreter exit.
        reset_pools_for_tests()


def test_pruning_the_same_dead_pool_twice_is_safe():
    """A dead pool is abandoned once, and pruning again is a no-op.

    Covers the half of that guarantee a test can pin down. The other half —
    that the removal uses pop() rather than del, so a second caller racing
    between the scan and the delete gets None instead of KeyError — needs two
    threads interleaved inside _prune_dead_pools() and has no deterministic
    test; sequentially the first call empties the entry and del would do just
    as well. Verified only under the stress harness described in the commit.
    """
    reset_pools_for_tests()

    loop = asyncio.new_event_loop()
    loop.close()
    pool = db._ConnectionPool(str(db.DB_PATH), loop, _POOL_SIZE)
    _pools[loop] = pool

    calls = []
    original = pool.abandon
    pool.abandon = lambda: (calls.append(1), original())[1]

    db._prune_dead_pools()
    db._prune_dead_pools()  # must not raise

    assert loop not in _pools
    assert len(calls) == 1, f"dead pool abandoned {len(calls)} times"
