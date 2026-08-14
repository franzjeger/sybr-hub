"""A backup must round-trip, and a restore must be all-or-nothing.

Before SR-003 a backup was written straight to its final name (a crash left a
half file), could be pointed at a directory inside the tree it was archiving
(so the zip swept in its own growing self), and carried an unauthenticated
manifest with no per-file hashes. Restore imported the master key first, read
the archive with no size limits (a zip bomb filled the disk), and overwrote
live data file-by-file with no staging and no rollback — a failure halfway
through left a half-restored install and possibly a key that no longer matched
the data.

These tests build a small fake install, back it up, and restore it — and check
that every failure mode (corruption, wrong password, a tampered manifest, a zip
bomb, a self-including destination, an interrupted write, a mid-commit failure)
either never touches live data or is fully rolled back.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.web.routes import backup as bk


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "customers" / "acme").mkdir(parents=True)
    (data / "customers" / "acme" / "config.json").write_bytes(b"CUSTOMER-ENCRYPTED")
    audit = tmp_path / "audit"
    (audit / "Acme" / "run1").mkdir(parents=True)
    (audit / "Acme" / "run1" / "01_users.txt").write_bytes(b"AUDIT-DATA")
    config = tmp_path / "config"
    config.mkdir()
    (config / "branding.json").write_bytes(b"BRANDING")
    certs = tmp_path / "certs"
    certs.mkdir()
    (certs / "acme.pem").write_bytes(b"CERTIFICATE")
    db = data / "msp_toolkit.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()
    (data / "activity_log.jsonl").write_bytes(b'{"event":"one"}\n')
    backups = tmp_path / "backups"
    backups.mkdir()

    import app.core.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", data)
    monkeypatch.setattr(cfg, "CONFIG_DIR", config)
    monkeypatch.setattr(cfg, "get_audit_dir", lambda: audit)
    monkeypatch.setattr(cfg, "get_cert_dir", lambda: certs)
    monkeypatch.setattr(
        "app.core.customer.CustomerManager.list_customers",
        staticmethod(lambda: [{"_id": "acme"}]),
    )
    monkeypatch.setattr(bk, "_get_default_backup_dir", lambda: backups)
    return SimpleNamespace(data=data, audit=audit, config=config, certs=certs,
                           db=db, backups=backups, tmp=tmp_path)


def _make_backup(env, password=None) -> Path:
    res = bk.create_backup_sync(dest_path=str(env.backups), backup_password=password)
    assert res["ok"]
    return Path(res["path"])


# ── Create ───────────────────────────────────────────────────────────────────

def test_a_backup_is_published_atomically(env):
    zip_path = _make_backup(env)
    assert zip_path.exists() and zip_path.suffix == ".zip"
    # No leftover temp file, and the manifest carries per-file hashes.
    assert not list(env.backups.glob("*.tmp"))
    with zipfile.ZipFile(zip_path) as zf:
        assert "manifest.json" in zf.namelist()
        assert "manifest.mac" in zf.namelist()
        import json
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["files"]["customers/acme/config.json"]["sha256"]


def test_a_destination_inside_a_source_tree_is_refused(env):
    inside = env.audit / "sneaky"
    with pytest.raises(ValueError):
        bk.create_backup_sync(dest_path=str(inside))


def test_an_interrupted_write_publishes_nothing(env, monkeypatch):
    import os
    real = os.replace

    def fail_on_publish(src, dst):
        if str(dst).endswith(".zip"):
            raise OSError("crash during atomic publish")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", fail_on_publish)
    with pytest.raises(OSError):
        bk.create_backup_sync(dest_path=str(env.backups))
    assert not list(env.backups.glob("*.zip")), "a partial backup was published"
    assert not list(env.backups.glob("*.tmp")), "a temp file was left behind"


# ── Round-trip restore ───────────────────────────────────────────────────────

def test_restore_brings_every_data_class_back(env):
    zip_path = _make_backup(env)
    # Change every live data class, then restore over the top.
    (env.data / "customers" / "acme" / "config.json").write_bytes(b"TAMPERED")
    (env.certs / "acme.pem").write_bytes(b"TAMPERED")
    con = sqlite3.connect(str(env.db))
    con.execute("DELETE FROM t")
    con.commit()
    con.close()

    staged = bk._stage_restore(zip_path, None)
    restored = bk._commit_restore(staged)

    assert (env.data / "customers" / "acme" / "config.json").read_bytes() == b"CUSTOMER-ENCRYPTED"
    assert (env.certs / "acme.pem").read_bytes() == b"CERTIFICATE"
    assert restored["database"] is True
    con = sqlite3.connect(str(env.db))
    assert con.execute("SELECT x FROM t").fetchone() == (42,)
    con.close()


def test_the_staging_dir_is_cleaned_up(env):
    zip_path = _make_backup(env)
    staged = bk._stage_restore(zip_path, None)
    staging = staged["staging"]
    assert staging.exists()
    bk._commit_restore(staged)
    assert not staging.exists()


# ── Corruption, tampering, wrong password ────────────────────────────────────

def _rewrite_zip(zip_path: Path, edits: dict[str, bytes]) -> None:
    """Rewrite an archive, replacing named entries."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            data = edits.get(info.filename, src.read(info.filename))
            dst.writestr(info.filename, data)
    zip_path.write_bytes(buf.getvalue())


def test_a_corrupted_file_is_caught_before_any_live_change(env):
    zip_path = _make_backup(env)
    _rewrite_zip(zip_path, {"customers/acme/config.json": b"SWAPPED-OUT"})
    original = (env.data / "customers" / "acme" / "config.json").read_bytes()

    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)
    # live data untouched
    assert (env.data / "customers" / "acme" / "config.json").read_bytes() == original


def test_a_tampered_manifest_is_rejected(env):
    zip_path = _make_backup(env)
    import json
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    manifest["customer_count"] = 9999  # edit under the MAC
    _rewrite_zip(zip_path, {"manifest.json": json.dumps(manifest).encode()})
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)


def test_a_portable_backup_needs_the_right_password(env):
    zip_path = _make_backup(env, password="correct horse battery")
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, "wrong password")
    # right password stages cleanly
    staged = bk._stage_restore(zip_path, "correct horse battery")
    assert staged["new_key_b64"]
    bk._remove(staged["staging"])


def test_a_portable_backup_without_a_password_is_refused(env):
    zip_path = _make_backup(env, password="secret")
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)


# ── ZIP bomb ─────────────────────────────────────────────────────────────────

def test_a_declared_zip_bomb_is_refused(env, monkeypatch):
    zip_path = _make_backup(env)
    # Lower the ceiling so the ordinary backup trips the entry-size guard,
    # standing in for a file that claims a huge uncompressed size.
    monkeypatch.setattr(bk, "_MAX_ENTRY_BYTES", 4)
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)


def test_too_many_entries_is_refused(env, monkeypatch):
    zip_path = _make_backup(env)
    monkeypatch.setattr(bk, "_MAX_ENTRIES", 1)
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)


# ── Integrity ────────────────────────────────────────────────────────────────

def test_a_broken_database_is_rejected(env):
    zip_path = _make_backup(env)
    _rewrite_zip(zip_path, {"database/msp_toolkit.db": b"SQLite format 3\x00 but truncated garbage"})
    with pytest.raises(ValidationError):
        bk._stage_restore(zip_path, None)


# ── Rollback ─────────────────────────────────────────────────────────────────

def test_a_failure_mid_commit_rolls_everything_back(env, monkeypatch):
    zip_path = _make_backup(env)
    staged = bk._stage_restore(zip_path, None)

    original_customer = (env.data / "customers" / "acme" / "config.json").read_bytes()
    original_cert = (env.certs / "acme.pem").read_bytes()

    # Fail the move on the *last* target (activity_log), after customers/certs/db
    # have already been swapped, to prove the earlier ones are put back.
    real_move = bk.shutil.move
    calls = {"n": 0}

    def flaky_move(src, dst):
        calls["n"] += 1
        if "activity_log" in str(src):
            raise OSError("disk full mid-commit")
        return real_move(src, dst)

    monkeypatch.setattr(bk.shutil, "move", flaky_move)
    with pytest.raises(OSError):
        bk._commit_restore(staged)

    # Everything is back exactly as it was.
    assert (env.data / "customers" / "acme" / "config.json").read_bytes() == original_customer
    assert (env.certs / "acme.pem").read_bytes() == original_cert
    con = sqlite3.connect(str(env.db))
    assert con.execute("SELECT x FROM t").fetchone() == (42,)
    con.close()
    # no rollback residue
    assert not list(env.data.rglob("*.sybr-rollback"))
    assert not list(env.certs.rglob("*.sybr-rollback"))


# ── Serialization ────────────────────────────────────────────────────────────

def test_backup_creation_is_serialized():
    # A single module-level lock guards create_backup_sync, so a scheduled and a
    # manual backup cannot write into the same directory at once.
    import threading
    assert isinstance(bk._BACKUP_LOCK, type(threading.Lock()))
