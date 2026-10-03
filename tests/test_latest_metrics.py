"""latest_metrics_per_customer returns one row per customer: the newest."""

from __future__ import annotations

import pytest

from app.core.database import get_db, run_migrations
from app.services.latest_metrics import latest_metrics_per_customer


@pytest.fixture(autouse=True)
async def _db(tmp_path):
    import app.core.database as database_module

    database_module.DB_PATH = tmp_path / "test.db"
    await run_migrations()


async def _metric(customer_id: str, audit_date: str, score: float) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO audit_metrics (customer_id, customer_name, audit_date, risk_score, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (customer_id, f"Kunde {customer_id}", audit_date, score, audit_date),
        )
        await db.commit()


async def test_one_row_per_customer_and_it_is_the_newest():
    await _metric("a", "2026-01-01T10:00:00", 40)
    await _metric("a", "2026-03-01T10:00:00", 80)
    await _metric("a", "2026-02-01T10:00:00", 60)
    await _metric("b", "2025-12-01T10:00:00", 55)

    latest = await latest_metrics_per_customer()

    assert set(latest) == {"a", "b"}
    assert latest["a"].risk_score == 80
    assert latest["b"].risk_score == 55


async def test_a_tie_on_date_goes_to_the_row_written_last():
    await _metric("a", "2026-03-01T10:00:00", 70)
    await _metric("a", "2026-03-01T10:00:00", 90)

    assert (await latest_metrics_per_customer())["a"].risk_score == 90


async def test_no_audits_is_an_empty_map():
    assert await latest_metrics_per_customer() == {}
