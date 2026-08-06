"""The trend table is a cache of the runs; the runs are the record.

Three things had drifted it apart from them: a row written twice per run, rows
holding figures from a parser since fixed — including an impossible 101.6% MFA
coverage — and an audit_date set minutes after the run it belongs to, so a row
could not be matched back to its run by time.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3

import pytest

_spec = importlib.util.spec_from_file_location(
    "rebuild", pathlib.Path("scripts/rebuild_metrics_trend.py")
)
rebuild = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rebuild)

SCHEMA = """
CREATE TABLE audit_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL, audit_date TEXT NOT NULL, risk_grade TEXT,
    risk_score REAL, mfa_coverage_pct REAL, secure_score_pct REAL,
    total_users INTEGER, users_no_mfa INTEGER, ca_policies_enabled INTEGER,
    intune_compliance_pct REAL, admin_roles_ga_count INTEGER,
    metrics_json TEXT, created_at TEXT NOT NULL)
"""


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    # Two rows for one run, minutes after it, with the buggy reading.
    for date, pct in (("2026-07-30T07:24:00Z", 101.6), ("2026-07-30T07:24:15Z", 101.6)):
        conn.execute(
            "INSERT INTO audit_metrics (customer_id, customer_name, audit_date, "
            "mfa_coverage_pct, users_no_mfa, created_at) VALUES (?,?,?,?,?,?)",
            ("acme", "Acme", date, pct, 0, date),
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def audits(tmp_path):
    from app.core.encryption import encrypted_write_json

    run = tmp_path / "audits" / "Acme" / "2026-07-30_0720"
    run.mkdir(parents=True)
    encrypted_write_json(run / "_audit_metrics.json", {
        "timestamp": "2026-07-30T07:20:00Z",
        "mfa_coverage_pct": 99.5, "users_no_mfa": 1, "risk_grade": "B",
    })
    return tmp_path / "audits"


def _rows(db):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_metrics ORDER BY audit_date")]
    finally:
        conn.close()


def test_a_dry_run_changes_nothing(db, audits):
    before = _rows(db)

    result = rebuild.rebuild(db, rebuild.rows_from_runs(audits, {"Acme": "acme"}), apply=False)

    assert result["dropped"] == 2
    assert _rows(db) == before


def test_one_row_per_run(db, audits):
    rebuild.rebuild(db, rebuild.rows_from_runs(audits, {"Acme": "acme"}), apply=True)

    rows = _rows(db)
    assert len(rows) == 1, "the duplicate survived"
    assert rows[0]["audit_date"] == "2026-07-30T07:20:00Z", "dated from the run, not the save"


def test_the_impossible_reading_is_replaced_by_the_current_one(db, audits):
    """101.6% coverage was a bug. Keeping it in a trend charts the bug."""
    rebuild.rebuild(db, rebuild.rows_from_runs(audits, {"Acme": "acme"}), apply=True)

    assert _rows(db)[0]["mfa_coverage_pct"] == 99.5
    assert _rows(db)[0]["users_no_mfa"] == 1


def test_the_full_metrics_blob_travels_with_the_row(db, audits):
    rebuild.rebuild(db, rebuild.rows_from_runs(audits, {"Acme": "acme"}), apply=True)

    assert json.loads(_rows(db)[0]["metrics_json"])["risk_grade"] == "B"


def test_rows_from_a_run_directory_that_is_gone_are_left_alone(db, audits):
    """Its rows are the last trace of something that was cleaned up.

    They share a customer_id with the live rows — the tenant id — so the link
    that matters is the name derived from the run directory.
    """
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO audit_metrics (customer_id, customer_name, audit_date, created_at) "
        "VALUES ('acme','Gone','2026-01-01T00:00:00Z','x')"
    )
    conn.commit()
    conn.close()

    result = rebuild.rebuild(db, rebuild.rows_from_runs(audits, {"Acme": "acme"}), apply=True)

    assert result["left_alone"] == 1, "a run directory that no longer exists lost its row"
    assert any(r["customer_name"] == "Gone" for r in _rows(db))


def test_a_run_whose_metrics_will_not_read_is_skipped_not_fatal(audits, capsys):
    (audits / "Acme" / "2026-07-31_0900").mkdir(parents=True)
    (audits / "Acme" / "2026-07-31_0900" / "_audit_metrics.json").write_bytes(b"not an envelope")

    rows = rebuild.rows_from_runs(audits, {"Acme": "acme"})

    assert [r["run"] for r in rows] == ["2026-07-30_0720"]
    assert "unreadable" in capsys.readouterr().out
