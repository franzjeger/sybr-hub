"""Backup and restore route handlers."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.user import Role, User
from app.web.i18n import ui_t
from app.web.middleware.auth import require_role

router = APIRouter()
logger = logging.getLogger(__name__)

_admin = Depends(require_role(Role.admin))


def _get_default_backup_dir() -> Path:
    from platformdirs import user_documents_dir
    return Path(user_documents_dir()) / "MSPToolkit" / "Backups"


def _master_key_fingerprint() -> str:
    """Return a SHA-256 hash of the master key (NOT the key itself)."""
    import hashlib

    from app.core.encryption import _get_or_create_master_key
    key = _get_or_create_master_key()
    return hashlib.sha256(key).hexdigest()


def create_backup_sync(dest_path: str | None = None, backup_password: str | None = None) -> dict:
    """Create a ZIP backup of all customer data, audit data, and app settings.

    Files are already encrypted on disk — the ZIP simply bundles them.
    When *backup_password* is provided the master encryption key is wrapped
    with that password and stored inside the ZIP so the backup is fully
    self-contained and can be restored on any machine.
    Returns {"ok": True, "path": "<zip_path>", "manifest": {...}}.
    """
    import zipfile
    from datetime import datetime, timezone

    from app.core.config import CONFIG_DIR, DATA_DIR, VERSION, get_audit_dir
    from app.core.customer import CustomerManager

    backup_dir = Path(dest_path) if dest_path else _get_default_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"MSPToolkit_backup_{ts}.zip"

    customers_dir = DATA_DIR / "customers"
    audit_dir = get_audit_dir()
    config_dir = CONFIG_DIR
    from app.core.config import get_cert_dir
    cert_dir = get_cert_dir()
    db_path = DATA_DIR / "msp_toolkit.db"
    activity_log_path = DATA_DIR / "activity_log.jsonl"

    # Count customers
    customer_count = len(CustomerManager.list_customers())

    manifest = {
        "backup_date": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "customer_count": customer_count,
        "master_key_fingerprint": _master_key_fingerprint(),
        "key_included": backup_password is not None,
        "contents": {
            "customers_dir": str(customers_dir),
            "audit_dir": str(audit_dir),
            "config_dir": str(config_dir),
            "cert_dir": str(cert_dir),
            "database": str(db_path),
            "activity_log": str(activity_log_path),
        },
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        # Include password-wrapped master key if password provided
        if backup_password:
            from app.core.encryption import wrap_master_key
            wrapped = wrap_master_key(backup_password)
            zf.writestr("master_key.wrapped", wrapped)

        # Helper to add directory tree
        def add_tree(base_path: Path, archive_prefix: str):
            if not base_path.exists():
                return
            for file in base_path.rglob("*"):
                if file.is_file():
                    arc_name = f"{archive_prefix}/{file.relative_to(base_path)}"
                    zf.write(file, arc_name)

        add_tree(customers_dir, "customers")
        add_tree(audit_dir, "audits")
        add_tree(config_dir, "config")
        add_tree(cert_dir, "certs")

        # SQLite database — use sqlite3 backup API for a consistent snapshot
        if db_path.exists():
            import sqlite3
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp_path = Path(tmp.name)
            try:
                src = sqlite3.connect(str(db_path))
                dst = sqlite3.connect(str(tmp_path))
                src.backup(dst)
                dst.close()
                src.close()
                zf.write(tmp_path, "database/msp_toolkit.db")
            finally:
                tmp_path.unlink(missing_ok=True)

        # Activity log
        if activity_log_path.exists():
            zf.write(activity_log_path, "activity_log.jsonl")

    manifest["zip_size_bytes"] = zip_path.stat().st_size

    # Save last backup date in app settings
    from app.core.config import load_app_settings, save_app_settings
    settings = load_app_settings()
    settings["last_backup_date"] = manifest["backup_date"]
    settings["last_backup_path"] = str(zip_path)
    save_app_settings(settings)

    return {"ok": True, "path": str(zip_path), "manifest": manifest}


@router.post("/backup/create")
async def create_backup(request: Request, user: User = _admin):
    """Create a full backup ZIP of all customer data.

    Accepts optional JSON body:
      - dest_path: custom output directory
      - backup_password: when provided, the master encryption key is wrapped
        with this password and stored inside the ZIP so the backup can be
        restored on any machine.
    """
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    dest = body.get("dest_path", "").strip() or None
    backup_password = body.get("backup_password", "").strip() or None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: create_backup_sync(dest, backup_password))
        from app.core.activity_log import log_activity
        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity("backup_created", detail=result["path"], user=_user)
        return result
    except Exception as e:
        raise IntegrationError(f"{ui_t('err_backup_failed', request)}: {e}")


@router.post("/backup/restore")
async def restore_backup(request: Request, user: User = _admin):
    """Restore a backup from a ZIP file.

    Accepts JSON body:
      - zip_path: path to the backup ZIP
      - backup_password: required when the backup contains a wrapped master key
    """
    import zipfile

    from app.core.config import CONFIG_DIR, DATA_DIR, get_audit_dir

    body = await request.json()
    zip_path_str = body.get("zip_path", "").strip()
    backup_password = body.get("backup_password", "").strip() or None
    if not zip_path_str:
        raise ValidationError(ui_t("err_no_file_path", request))

    zip_path = Path(zip_path_str).resolve()

    # Restrict source to known safe directories
    _safe_parents = [
        _get_default_backup_dir().resolve(),
        Path.home().resolve(),
    ]
    if not any(str(zip_path).startswith(str(p)) for p in _safe_parents):
        raise AuthError("Backup-filen må ligge i backup-mappen eller hjemmemappen")

    if not zip_path.exists() or not zip_path.is_file():
        raise NotFoundError(ui_t("err_file_not_found", request))
    if not zip_path.suffix.lower() == ".zip":
        raise ValidationError(ui_t("err_file_must_be_zip", request))

    def do_restore() -> dict:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Validate manifest
            if "manifest.json" not in zf.namelist():
                raise ValidationError(ui_t("err_invalid_backup"))

            manifest = json.loads(zf.read("manifest.json"))

            # If backup contains a wrapped master key, unwrap it first
            key_match = True
            if "master_key.wrapped" in zf.namelist():
                if not backup_password:
                    raise ValidationError(
                        "Denne backupen inneholder en kryptert nøkkel. "
                        "Oppgi backup-passordet for å gjenopprette."
                    )
                from app.core.encryption import unwrap_master_key
                wrapped = zf.read("master_key.wrapped").decode("utf-8")
                if not unwrap_master_key(wrapped, backup_password):
                    raise ValidationError(
                        "Feil backup-passord. Kunne ikke dekryptere nøkkelen."
                    )
                logger.info("Master key restored from backup")
            else:
                # Legacy backup without wrapped key — check fingerprint
                try:
                    current_fp = _master_key_fingerprint()
                    backup_fp = manifest.get("master_key_fingerprint", "")
                    if backup_fp and current_fp != backup_fp:
                        key_match = False
                except Exception as e:
                    logger.debug("Failed to check master key fingerprint: %s", e)
                    key_match = False

            customers_dir = DATA_DIR / "customers"
            audit_dir = get_audit_dir()
            config_dir = CONFIG_DIR
            from app.core.config import get_cert_dir
            cert_dir = get_cert_dir()
            db_path = DATA_DIR / "msp_toolkit.db"
            activity_log_path = DATA_DIR / "activity_log.jsonl"

            restored = {"customers": 0, "audits": 0, "config": 0, "certs": 0,
                        "database": False, "activity_log": False}

            # Mapping of archive prefixes to target directories
            prefix_map = {
                "customers/": (customers_dir, "customers"),
                "audits/": (audit_dir, "audits"),
                "config/": (config_dir, "config"),
                "certs/": (cert_dir, "certs"),
            }

            for entry in zf.namelist():
                if entry in ("manifest.json", "master_key.wrapped") or entry.endswith("/"):
                    continue

                # Database restore — use sqlite3 backup API to safely overwrite
                if entry == "database/msp_toolkit.db":
                    import sqlite3
                    import tempfile
                    db_path.parent.mkdir(parents=True, exist_ok=True)
                    # Write backup data to temp file, then use backup API
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        tmp.write(zf.read(entry))
                        tmp_path = Path(tmp.name)
                    try:
                        src = sqlite3.connect(str(tmp_path))
                        dst = sqlite3.connect(str(db_path))
                        src.backup(dst)
                        dst.close()
                        src.close()
                    finally:
                        tmp_path.unlink(missing_ok=True)
                    # Remove stale WAL/SHM files left from previous connections
                    for suffix in (".db-wal", ".db-shm"):
                        wal_file = db_path.with_suffix(suffix)
                        if wal_file.exists():
                            wal_file.unlink()
                    restored["database"] = True
                    continue

                # Activity log restore
                if entry == "activity_log.jsonl":
                    activity_log_path.parent.mkdir(parents=True, exist_ok=True)
                    activity_log_path.write_bytes(zf.read(entry))
                    restored["activity_log"] = True
                    continue

                # Determine target from prefix map
                target = None
                target_base = None
                counter_key = None
                for prefix, (base_dir, key) in prefix_map.items():
                    if entry.startswith(prefix):
                        rel = entry[len(prefix):]
                        target = base_dir / rel
                        target_base = base_dir
                        counter_key = key
                        break

                if target is None:
                    continue

                # Security: prevent path traversal
                try:
                    target.resolve().relative_to(target_base.resolve())
                except (ValueError, Exception):
                    logger.warning("Skipping path traversal attempt in backup: %s", entry)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(entry))
                restored[counter_key] += 1

            result = {
                "ok": True,
                "key_match": key_match,
                "manifest": manifest,
                "restored_files": restored,
                "restart_required": restored.get("database", False),
            }
            if not key_match and "master_key.wrapped" not in zf.namelist():
                result["warning"] = ui_t("warn_master_key_mismatch", request)
            return result

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, do_restore)
        from app.core.activity_log import log_activity
        _user = getattr(getattr(request.state, "user", None), "username", "")
        log_activity("backup_restored", detail=zip_path_str, user=_user)
        return result
    except (ValidationError, NotFoundError, AuthError, IntegrationError):
        raise
    except Exception as e:
        raise IntegrationError(f"{ui_t('err_restore_failed', request)}: {e}")


@router.get("/backup/info")
async def backup_info(user: User = _admin):
    """Return last backup date and default backup dir."""
    from app.core.config import load_app_settings
    settings = load_app_settings()
    return {
        "last_backup_date": settings.get("last_backup_date", ""),
        "last_backup_path": settings.get("last_backup_path", ""),
        "default_backup_dir": str(_get_default_backup_dir()),
    }
