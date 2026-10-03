"""A report and its trend row belong to the run's customer, never "the active one".

``build_report_context`` merged in the remediation statuses of the caller's
active customer, whichever run it was given: customer A's report, built while
customer B was the one last opened, carried B's "done" and notes against A's
findings. ``_save_metrics_to_db`` took the trend row's customer from
``load_config()``, which in the audit job's executor thread (and in the
scheduler) is the setup staging file, so a finished audit's trend row could
land on whoever was set up last.

Now the caller passes the customer; without one the run's folder decides, and
only when exactly one customer has that folder name.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.reports.generator import build_report_context
from app.reports.metrics import _save_metrics_to_db


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "Acme_AS" / "2026-01-01_0900"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def remediation_asked(monkeypatch):
    asked: list[str] = []

    def _load(customer_id):
        asked.append(customer_id)
        return {}

    monkeypatch.setattr("app.services.remediation.load_remediation_sync", _load)
    return asked


def _registry(monkeypatch, customers):
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [dict(c) for c in customers]),
    )


def test_the_report_reads_the_named_customers_remediation(run_dir, remediation_asked, monkeypatch):
    _registry(monkeypatch, [{"_id": "acme-id", "CustomerName": "Acme AS"}])

    build_report_context("Acme AS", "", run_dir, [], persist_metrics=False, customer_id="other-id")

    assert remediation_asked == ["other-id"]


def test_without_a_customer_the_runs_folder_decides(run_dir, remediation_asked, monkeypatch):
    _registry(monkeypatch, [{"_id": "acme-id", "CustomerName": "Acme AS"}])

    build_report_context("Acme AS", "", run_dir, [], persist_metrics=False)

    assert remediation_asked == ["acme-id"]


def test_a_folder_two_customers_share_names_nobody(run_dir, remediation_asked, monkeypatch):
    # "Acme AS" and "Acme_AS" both write to the folder Acme_AS.
    _registry(
        monkeypatch,
        [{"_id": "a1", "CustomerName": "Acme AS"}, {"_id": "a2", "CustomerName": "Acme_AS"}],
    )

    build_report_context("Acme AS", "", run_dir, [], persist_metrics=False)

    assert remediation_asked == []


async def _metrics_db(tmp_path, monkeypatch):
    import app.core.database as database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "metrics.db")
    await database.run_migrations()
    await database.close_all_pools()
    return database.DB_PATH


def _row_customer(db_path) -> str:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT customer_id FROM audit_metrics").fetchone()[0]
    finally:
        con.close()


async def test_the_trend_row_carries_the_customer_it_was_given(tmp_path, run_dir, monkeypatch):
    db = await _metrics_db(tmp_path, monkeypatch)
    # The staging slot names someone else; it must not be read.
    monkeypatch.setattr(
        "app.core.credentials.load_config", lambda: {"_id": "staged", "TenantId": "staged"}
    )

    _save_metrics_to_db(run_dir, {"timestamp": "2026-01-01T09:00:00"}, "acme-id")

    assert _row_customer(db) == "acme-id"


async def test_a_trend_row_without_a_customer_takes_the_folders(tmp_path, run_dir, monkeypatch):
    db = await _metrics_db(tmp_path, monkeypatch)
    _registry(monkeypatch, [{"_id": "acme-id", "CustomerName": "Acme AS"}])
    monkeypatch.setattr(
        "app.core.credentials.load_config", lambda: {"_id": "staged", "TenantId": "staged"}
    )

    _save_metrics_to_db(run_dir, {"timestamp": "2026-01-01T09:00:00"})

    assert _row_customer(db) == "acme-id"
