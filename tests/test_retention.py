"""Retirement is reversible; offline purge is scoped and rolls back failures."""

import json
import sqlite3
import sys

import pytest

from app.core.customer import CustomerManager
from app.core.encryption import encrypted_write_json
from app.core.exceptions import ConflictError
from scripts import purge_customer


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from app.core import config, customer, database

    data = tmp_path / "data"
    audits = tmp_path / "audits"
    certs = tmp_path / "certs"
    data.mkdir()
    audits.mkdir()
    certs.mkdir()
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(customer, "_CUSTOMERS_DIR", data / "customers")
    monkeypatch.setattr(config, "get_audit_dir", lambda: audits)
    monkeypatch.setattr(config, "get_cert_dir", lambda: certs)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    for name in ("Retire Me", "Keep Me"):
        cid = CustomerManager.save_customer({"CustomerName": name}, create=True)
        (audits / cid).mkdir()
        (audits / cid / "report.txt").write_text("customer evidence")
        (certs / f"{cid}.pfx").write_bytes(b"certificate")
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, customer_id TEXT)")
        db.executemany("INSERT INTO evidence VALUES (?, ?)", [(1, "Retire_Me"), (2, "Keep_Me")])
    return data, audits, certs, db_path


def test_colliding_customer_names_cannot_replace_identity(registry):
    cid = CustomerManager.save_customer({"CustomerName": "A&B", "TenantId": "first"}, create=True)
    with pytest.raises(ConflictError):
        CustomerManager.save_customer({"CustomerName": "A?B", "TenantId": "second"}, create=True)
    assert CustomerManager.get_customer(cid)["TenantId"] == "first"
    customer = CustomerManager.get_customer(cid)
    customer["CustomerName"] = "Renamed"
    assert CustomerManager.save_customer(customer) == cid


def test_retire_dry_run_and_apply_preserve_other_customer(registry, monkeypatch, capsys):
    data, audits, certs, db_path = registry
    CustomerManager.delete_customer("Retire_Me")
    assert CustomerManager.get_customer("Retire_Me") is None
    with pytest.raises(ConflictError, match="arkivert"):
        CustomerManager.save_customer({"CustomerName": "Retire Me"}, create=True)
    monkeypatch.setattr(sys, "argv", ["purge_customer.py", "Retire_Me"])
    purge_customer.main()
    plan = json.loads(capsys.readouterr().out)
    assert str(audits / "Retire_Me") in plan["paths"]
    assert (data / "retired_customers/Retire_Me/config.json").exists()
    assert (audits / "Retire_Me/report.txt").exists()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "purge_customer.py",
            "Retire_Me",
            "--apply",
            "--confirm",
            "Retire_Me",
            "--service-stopped",
        ],
    )
    purge_customer.main()
    assert not (data / "retired_customers/Retire_Me").exists()
    assert not (audits / "Retire_Me").exists()
    assert not (certs / "Retire_Me.pfx").exists()
    assert CustomerManager.get_customer("Keep_Me")
    assert (audits / "Keep_Me/report.txt").exists()
    assert (certs / "Keep_Me.pfx").exists()
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT customer_id FROM evidence").fetchall() == [("Keep_Me",)]


def test_purge_restores_paths_if_a_shared_database_reference_blocks_commit(registry, monkeypatch):
    data, audits, certs, db_path = registry
    CustomerManager.delete_customer("Retire_Me")
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE shared_reference(evidence_id INTEGER REFERENCES evidence(id))")
        db.execute("INSERT INTO shared_reference VALUES (1)")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "purge_customer.py",
            "Retire_Me",
            "--apply",
            "--confirm",
            "Retire_Me",
            "--service-stopped",
        ],
    )
    with pytest.raises(sqlite3.IntegrityError):
        purge_customer.main()
    assert (data / "retired_customers/Retire_Me/config.json").exists()
    assert (audits / "Retire_Me/report.txt").exists()
    assert (certs / "Retire_Me.pfx").exists()
    assert not list(data.rglob(".sybr-purge-*"))
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 2


def test_invalid_legacy_name_cannot_purge_the_audit_root(registry, monkeypatch):
    data, audits, _certs, _db = registry
    CustomerManager.delete_customer("Retire_Me")
    encrypted_write_json(data / "retired_customers/Retire_Me/config.json", {"CustomerName": ""})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "purge_customer.py",
            "Retire_Me",
            "--apply",
            "--confirm",
            "Retire_Me",
            "--service-stopped",
        ],
    )
    with pytest.raises(SystemExit):
        purge_customer.main()
    assert (audits / "Keep_Me/report.txt").exists()
