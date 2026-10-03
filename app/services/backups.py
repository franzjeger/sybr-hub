"""Encrypted backup creation shared by schedulers and HTTP."""

import hashlib
import json
import logging
import threading
import zipfile
from datetime import UTC
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)
_BACKUP_LOCK = threading.Lock()


def _get_default_backup_dir() -> Path:
    from platformdirs import user_documents_dir

    return Path(user_documents_dir()) / "MSPToolkit" / "Backups"


def create_backup_sync(dest_path: str | None = None, backup_password: str | None = None) -> dict:
    """Create a ZIP backup of all customer data, audit data, and app settings.

    Every payload is encrypted while streaming into the ZIP, which records a
    hash of those exact bytes in an authenticated manifest, is written under a temporary
    name and atomically renamed on success, and refuses a destination inside a
    source tree so the archive cannot include itself while it is being written.
    Returns {"ok": True, "path": "<zip_path>", "manifest": {...}}.
    """
    import os
    from datetime import datetime

    from app.core.backup_crypto import encrypt_member
    from app.core.config import (
        CONFIG_DIR,
        DATA_DIR,
        VERSION,
        get_audit_dir,
        get_cert_dir,
        update_app_settings,
    )
    from app.core.customer import CustomerManager
    from app.core.encryption import _get_or_create_master_key, manifest_mac, wrap_master_key

    with _BACKUP_LOCK:
        backup_dir = Path(dest_path) if dest_path else _get_default_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_dir_r = backup_dir.resolve()

        customers_dir = DATA_DIR / "customers"
        audit_dir = get_audit_dir()
        config_dir = CONFIG_DIR
        cert_dir = get_cert_dir()
        db_path = DATA_DIR / "msp_toolkit.db"
        activity_log_path = DATA_DIR / "activity_log.jsonl"

        # SR-003 #1: the destination must not sit inside anything we are about to
        # archive, or add_tree would sweep the half-written zip into itself.
        for src in (customers_dir, audit_dir, config_dir, cert_dir, DATA_DIR):
            try:
                srcr = src.resolve()
            except OSError:
                continue
            if backup_dir_r == srcr or srcr in backup_dir_r.parents:
                raise ValueError(
                    "Backup-mappen kan ikke ligge inne i en mappe som "
                    "sikkerhetskopieres. Velg en mappe utenfor dataområdet."
                )

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:12]
        zip_path = backup_dir / f"MSPToolkit_backup_{ts}.zip"
        tmp_path = zip_path.with_name(zip_path.name + ".tmp")  # SR-003 #2
        zip_path_r, tmp_path_r = zip_path.resolve(), tmp_path.resolve()

        files: dict[str, dict] = {}
        customer_count = len(CustomerManager.list_customers())
        archive_key = _get_or_create_master_key()

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if backup_password:
                    zf.writestr(
                        "master_key.wrapped", wrap_master_key(backup_password, key=archive_key)
                    )

                def add(on_disk: Path, arc: str) -> None:
                    with zf.open(arc, "w", force_zip64=True) as member:
                        files[arc] = encrypt_member(on_disk, member, archive_key, arc)

                def add_tree(base: Path, prefix: str) -> None:
                    if not base.exists():
                        return
                    for file in base.rglob("*"):
                        if not file.is_file():
                            continue
                        # Belt-and-suspenders against self-inclusion even if the
                        # destination check let something through.
                        if file.resolve() in (zip_path_r, tmp_path_r):
                            continue
                        add(file, f"{prefix}/{file.relative_to(base)}")

                add_tree(customers_dir, "customers")
                add_tree(DATA_DIR / "retired_customers", "retired_customers")
                add_tree(audit_dir, "audits")
                add_tree(config_dir, "config")
                add_tree(cert_dir, "certs")

                if db_path.exists():
                    import sqlite3
                    import tempfile

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        db_snapshot = Path(tmp.name)
                    src_con = dst_con = None
                    try:
                        src_con = sqlite3.connect(str(db_path))
                        dst_con = sqlite3.connect(str(db_snapshot))
                        src_con.backup(dst_con)
                        dst_con.close()
                        dst_con = None
                        src_con.close()
                        src_con = None
                        add(db_snapshot, "database/msp_toolkit.db")
                    finally:
                        # Close on any failure too, or a failed snapshot leaks a
                        # sqlite handle (SR-003 review, LOW).
                        if dst_con is not None:
                            dst_con.close()
                        if src_con is not None:
                            src_con.close()
                        db_snapshot.unlink(missing_ok=True)

                if activity_log_path.exists():
                    add(activity_log_path, "activity_log.jsonl")

                manifest = {
                    "format": 3,
                    "backup_date": datetime.now(UTC).isoformat(),
                    "version": VERSION,
                    "customer_count": customer_count,
                    "master_key_fingerprint": hashlib.sha256(archive_key).hexdigest(),
                    "key_included": backup_password is not None,
                    "files": files,
                    "contents": {
                        "customers_dir": str(customers_dir),
                        "audit_dir": str(audit_dir),
                        "config_dir": str(config_dir),
                        "cert_dir": str(cert_dir),
                        "database": str(db_path),
                        "activity_log": str(activity_log_path),
                    },
                }
                manifest_bytes = json.dumps(
                    manifest, indent=2, ensure_ascii=False, sort_keys=True
                ).encode("utf-8")
                zf.writestr("manifest.json", manifest_bytes)
                # SR-003 #4: authenticate the manifest (and, through its file
                # hashes, the whole payload) under the master key.
                zf.writestr("manifest.mac", manifest_mac(manifest_bytes, key=archive_key))
            os.replace(tmp_path, zip_path)  # SR-003 #2: atomic publish
        except Exception:
            # A failure anywhere — including the rename — leaves no half file.
            tmp_path.unlink(missing_ok=True)
            raise
        manifest["zip_size_bytes"] = zip_path.stat().st_size

        update_app_settings(
            lambda s: s.update(
                {
                    "last_backup_date": manifest["backup_date"],
                    "last_backup_path": str(zip_path),
                }
            )
        )
        return {"ok": True, "path": str(zip_path), "manifest": manifest}
