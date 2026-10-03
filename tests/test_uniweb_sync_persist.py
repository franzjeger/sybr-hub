"""One unreadable Uniweb account must not discard the whole sync.

`_do_sync` deliberately marks an account it could not open with an
``unavailable`` reason and *no* ``data`` key — so "we could not read this page"
never gets written as "this customer has no domains". The persist loop then
has to honour that: skip the account it cannot describe, keep every account it
*could* read, and commit.

The bug this pins: the loop used to do ``dict(account["data"])`` for every
account unconditionally. The first unavailable account raised ``KeyError`` inside
the ``get_db()`` block, before the commit, and the broad ``except`` in the caller
swallowed it as ``last_error = "'data'"`` — so a single un-openable account in a
multi-account run threw away every account that had been scraped successfully.
"""

from __future__ import annotations

import json

import pytest

from app.core.database import get_db, run_migrations
from app.web.routes.uniweb import _persist_sync_results


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


async def _stored() -> dict[str, dict]:
    """Every uniweb_accounts row, keyed by id, data_json parsed."""
    out: dict[str, dict] = {}
    async with (
        get_db() as db,
        db.execute("SELECT id, name, last_sync, data_json FROM uniweb_accounts") as cur,
    ):
        for row in await cur.fetchall():
            out[row["id"]] = {
                "name": row["name"],
                "last_sync": row["last_sync"],
                "data": json.loads(row["data_json"]) if row["data_json"] else None,
            }
    return out


async def test_a_good_account_persists_even_when_an_earlier_one_was_unavailable():
    """The whole point: the unavailable account is listed *first*, so the old
    KeyError would have aborted the batch before the good account was written."""
    results = [
        {"id": "u1", "name": "Broken AS", "unavailable": "Could not enter the account page."},
        {"id": "u2", "name": "Good AS", "data": {"domains": [{"domain": "good.no"}]}},
    ]

    stored = await _persist_sync_results(results, "2026-08-24T00:00:00Z")

    assert stored == 1
    rows = await _stored()
    # The good account is committed and readable.
    assert "u2" in rows
    assert rows["u2"]["data"]["domains"] == [{"domain": "good.no"}]
    # The unreadable account is not written as an empty customer.
    assert "u1" not in rows


async def test_an_unavailable_account_leaves_its_prior_row_intact():
    """A refusal is not a zero: the account was readable yesterday, unreadable
    today. Today's failure must not blank out yesterday's good data."""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO uniweb_accounts (id, name, customer_id, last_sync, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "u1",
                "Broken AS",
                "cust-1",
                "2026-08-01T00:00:00Z",
                json.dumps({"domains": [{"domain": "still-here.no"}]}),
            ),
        )
        await db.commit()

    stored = await _persist_sync_results(
        [{"id": "u1", "name": "Broken AS", "unavailable": "timeout"}],
        "2026-08-24T00:00:00Z",
    )

    assert stored == 0
    rows = await _stored()
    # Prior row untouched — data kept, last_sync not advanced to today.
    assert rows["u1"]["data"]["domains"] == [{"domain": "still-here.no"}]
    assert rows["u1"]["last_sync"] == "2026-08-01T00:00:00Z"


async def test_existing_customer_mapping_is_preserved_on_update():
    """A re-sync must not orphan the account from the customer it was matched to."""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO uniweb_accounts (id, name, customer_id, last_sync, data_json) "
            "VALUES (?, ?, ?, ?, ?)",
            ("u2", "Good AS", "cust-9", "2026-08-01T00:00:00Z", json.dumps({"domains": []})),
        )
        await db.commit()

    await _persist_sync_results(
        [{"id": "u2", "name": "Good AS", "data": {"domains": [{"domain": "good.no"}]}}],
        "2026-08-24T00:00:00Z",
    )

    async with (
        get_db() as db,
        db.execute(
            "SELECT customer_id, last_sync FROM uniweb_accounts WHERE id = ?", ("u2",)
        ) as cur,
    ):
        row = await cur.fetchone()
    assert row["customer_id"] == "cust-9"  # mapping kept
    assert row["last_sync"] == "2026-08-24T00:00:00Z"  # fresh data did advance it


async def test_parent_info_is_folded_into_sub_customer_data():
    await _persist_sync_results(
        [
            {
                "id": "sub1",
                "name": "Sub AS",
                "parent_id": "p1",
                "parent_name": "Partner AS",
                "data": {"domains": []},
            }
        ],
        "2026-08-24T00:00:00Z",
    )
    rows = await _stored()
    assert rows["sub1"]["data"]["parent_id"] == "p1"
    assert rows["sub1"]["data"]["parent_name"] == "Partner AS"


async def test_all_unavailable_still_commits_and_stores_nothing():
    """No exception, no rows, and specifically not the KeyError that used to
    escape the whole function."""
    stored = await _persist_sync_results(
        [
            {"id": "a", "name": "A", "unavailable": "x"},
            {"id": "b", "name": "B", "unavailable": "y"},
        ],
        "2026-08-24T00:00:00Z",
    )
    assert stored == 0
    assert await _stored() == {}
