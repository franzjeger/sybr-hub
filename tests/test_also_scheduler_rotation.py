"""The daily ALSO price refresh must rotate through the whole linked base.

It used to scan ``linked[:25]`` with no recency filter, so every day it
re-scanned the same first 25 customers and never reached number 26+. Any MSP
with more than 25 ALSO-linked customers got permanently stale contract_end for
the tail, and upcoming-renewal alerts silently missed them.

The manual endpoint (routes/also.py) already rotated correctly by skipping
customers refreshed in the last 24h; the scheduled path had simply diverged.
These tests pin the scheduled path to that same rotation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from app.core.database import get_db, run_migrations
from app.services import scheduler as sched


@pytest.fixture(autouse=True)
async def _init_db(tmp_path):
    import app.core.database as db_mod

    db_mod.DB_PATH = tmp_path / "test.db"
    await run_migrations()
    yield


# 30 linked customers: _id c0..c29, AlsoAccountId "0".."29".
CUSTOMERS = [
    {"_id": f"c{i}", "CustomerName": f"Cust {i}", "AlsoAccountId": str(i)} for i in range(30)
]


class _FakeAlso:
    """Records which ALSO account ids the refresh asked to scan."""

    asked: ClassVar[list[str]] = []

    def __init__(self, *a, **k):
        pass

    async def get_subscriptions(self, account_id):
        _FakeAlso.asked.append(str(account_id))
        return [{"AccountId": f"sub-{account_id}"}]


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _FakeAlso.asked = []

    monkeypatch.setattr(
        "app.core.config.load_app_settings",
        lambda: {"also_password": "pw", "also_username": "u", "also_country": "no"},
    )
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in CUSTOMERS]),
    )
    monkeypatch.setattr("app.integrations.also_cloud.AlsoCloudClient", _FakeAlso)

    async def _noop_cache(*a, **k):
        return None

    monkeypatch.setattr("app.services.also_renewals.cache_renewals", _noop_cache)

    async def _noop_sleep(*a, **k):
        return None

    monkeypatch.setattr("app.services.scheduler.asyncio.sleep", _noop_sleep)


async def _mark_scanned(customer_ids, when_iso):
    async with get_db() as db:
        for cid in customer_ids:
            await db.execute(
                "INSERT INTO also_renewals "
                "(customer_id, customer_name, subscription_id, service_name, "
                " service_display, contract_end, account_state, scanned_at) "
                "VALUES (?, ?, ?, 'M365', 'Microsoft 365', '', 'Active', ?)",
                (cid, cid, f"sub-{cid}", when_iso),
            )
        await db.commit()


async def test_recently_scanned_customers_are_skipped_and_the_tail_is_reached():
    recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    # c0..c24 were refreshed an hour ago; the scheduled run must move on to the
    # tail (c25..c29) rather than re-scanning the same first 25 forever.
    await _mark_scanned([f"c{i}" for i in range(25)], recent)

    await sched._do_also_price_refresh()

    # AlsoAccountId equals the index, so the tail is "25".."29".
    assert _FakeAlso.asked == ["25", "26", "27", "28", "29"]


async def test_a_stale_scan_does_not_count_as_recent():
    stale = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    # c0..c24 were scanned 30h ago — past the 24h window — so they are due again.
    await _mark_scanned([f"c{i}" for i in range(25)], stale)

    await sched._do_also_price_refresh()

    # Falls back to the first 25 by list order because nothing is "recent".
    assert _FakeAlso.asked == [str(i) for i in range(25)]


async def test_day_one_with_no_history_scans_the_first_batch():
    await sched._do_also_price_refresh()
    assert _FakeAlso.asked == [str(i) for i in range(25)]


async def test_all_recent_scans_nothing():
    recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    await _mark_scanned([f"c{i}" for i in range(30)], recent)

    result = await sched._do_also_price_refresh()

    assert _FakeAlso.asked == []
    assert "within 24h" in result
