"""Backup and restore route handlers.

Confidentiality model (SR-003 criterion 5). Every file in the archive is
already encrypted at rest with the master key, so the *payload* is confidential
to anyone without that key. What the archive does NOT hide is metadata: the
manifest, the file names and the directory structure are stored in clear. A
portable backup adds ``master_key.wrapped`` — the master key sealed with the
operator's password (PBKDF2 + AES-GCM) — so the payload can be decrypted on
another machine by whoever knows that password. We therefore promise
portability and payload confidentiality, not metadata confidentiality; the
manifest is authenticated (HMAC under the master key) for integrity, not
secrecy. Whole-archive authenticated encryption would be needed to hide the
metadata too, and is deliberately not attempted here.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import shutil
import threading
import zipfile
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

# Serialize backup creation: a scheduled and a manual backup that overlap would
# write two archives into the same directory at once and, worse, each read a
# database mid-write by the other (SR-003 criterion 3).
_BACKUP_LOCK = threading.Lock()

# Archive-extraction limits, checked before anything is read out (SR-003 #6).
_MAX_ENTRIES = 500_000
_MAX_ENTRY_BYTES = 4 * 1024**3          # 4 GiB for the largest single file (the DB)
_MAX_TOTAL_BYTES = 50 * 1024**3         # 50 GiB uncompressed in total
_MAX_COMPRESSION_RATIO = 500            # per entry; a zip bomb inflates far more
_CHUNK = 1 << 20


def _get_default_backup_dir() -> Path:
    from platformdirs import user_documents_dir
    return Path(user_documents_dir()) / "MSPToolkit" / "Backups"


def _master_key_fingerprint() -> str:
    """Return a SHA-256 hash of the master key (NOT the key itself)."""
    from app.core.encryption import _get_or_create_master_key
    return hashlib.sha256(_get_or_create_master_key()).hexdigest()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


# ── Create ───────────────────────────────────────────────────────────────────


def create_backup_sync(dest_path: str | None = None, backup_password: str | None = None) -> dict:
    """Create a ZIP backup of all customer data, audit data, and app settings.

    Files are already encrypted on disk — the ZIP bundles them, records a
    hash of each in an authenticated manifest, is written under a temporary
    name and atomically renamed on success, and refuses a destination inside a
    source tree so the archive cannot include itself while it is being written.
    Returns {"ok": True, "path": "<zip_path>", "manifest": {...}}.
    """
    import os
    from datetime import datetime, timezone

    from app.core.config import (
        CONFIG_DIR,
        DATA_DIR,
        VERSION,
        get_audit_dir,
        get_cert_dir,
        update_app_settings,
    )
    from app.core.customer import CustomerManager
    from app.core.encryption import manifest_mac, wrap_master_key

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

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_path = backup_dir / f"MSPToolkit_backup_{ts}.zip"
        tmp_path = zip_path.with_name(zip_path.name + ".tmp")   # SR-003 #2
        zip_path_r, tmp_path_r = zip_path.resolve(), tmp_path.resolve()

        files: dict[str, dict] = {}
        customer_count = len(CustomerManager.list_customers())

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if backup_password:
                    zf.writestr("master_key.wrapped", wrap_master_key(backup_password))

                def add(on_disk: Path, arc: str) -> None:
                    zf.write(on_disk, arc)
                    files[arc] = {"size": on_disk.stat().st_size, "sha256": _hash_file(on_disk)}

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
                add_tree(audit_dir, "audits")
                add_tree(config_dir, "config")
                add_tree(cert_dir, "certs")

                if db_path.exists():
                    import sqlite3
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        db_snapshot = Path(tmp.name)
                    try:
                        src_con = sqlite3.connect(str(db_path))
                        dst_con = sqlite3.connect(str(db_snapshot))
                        src_con.backup(dst_con)
                        dst_con.close()
                        src_con.close()
                        add(db_snapshot, "database/msp_toolkit.db")
                    finally:
                        db_snapshot.unlink(missing_ok=True)

                if activity_log_path.exists():
                    add(activity_log_path, "activity_log.jsonl")

                manifest = {
                    "format": 2,
                    "backup_date": datetime.now(timezone.utc).isoformat(),
                    "version": VERSION,
                    "customer_count": customer_count,
                    "master_key_fingerprint": _master_key_fingerprint(),
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
                zf.writestr("manifest.mac", manifest_mac(manifest_bytes))
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        os.replace(tmp_path, zip_path)   # SR-003 #2: atomic publish
        manifest["zip_size_bytes"] = zip_path.stat().st_size

        update_app_settings(lambda s: s.update({
            "last_backup_date": manifest["backup_date"],
            "last_backup_path": str(zip_path),
        }))
        return {"ok": True, "path": str(zip_path), "manifest": manifest}


@router.post("/backup/create")
async def create_backup(request: Request, user: User = _admin):
    """Create a full backup ZIP of all customer data.

    Optional JSON body: ``dest_path`` (output directory) and
    ``backup_password`` (wraps the master key into the archive for a portable,
    restore-anywhere backup).
    """
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    dest = body.get("dest_path", "").strip() or None
    backup_password = body.get("backup_password", "").strip() or None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: create_backup_sync(dest, backup_password))
    except ValueError as exc:
        raise ValidationError(str(exc))
    except Exception as e:
        raise IntegrationError(f"{ui_t('err_backup_failed', request)}: {e}")
    from app.core.activity_log import log_activity
    _user = getattr(getattr(request.state, "user", None), "username", "")
    log_activity("backup_created", detail=result["path"], user=_user)
    return result


# ── Restore ───────────────────────────────────────────────────────────────────


def _enforce_archive_limits(zf: zipfile.ZipFile) -> None:
    """Refuse a decompression bomb before a single byte is extracted (SR-003 #6)."""
    infos = zf.infolist()
    if len(infos) > _MAX_ENTRIES:
        raise ValidationError("Backupen inneholder for mange filer.")
    total = 0
    for info in infos:
        if info.file_size > _MAX_ENTRY_BYTES:
            raise ValidationError(f"En fil i backupen er for stor: {info.filename}")
        total += info.file_size
        if total > _MAX_TOTAL_BYTES:
            raise ValidationError("Backupen er for stor til å pakkes ut trygt.")
        if info.compress_size > 0 and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
            raise ValidationError(
                f"Mistenkelig kompresjonsforhold på {info.filename} — avvist som mulig zip-bombe."
            )


def _extract_entry(zf: zipfile.ZipFile, entry: str, staging: Path) -> None:
    """Extract one entry under *staging*, guarding traversal and re-checking size."""
    target = (staging / entry).resolve()
    staging_r = staging.resolve()
    if target != staging_r and staging_r not in target.parents:
        raise ValidationError(f"Ugyldig sti i backup (path traversal): {entry}")
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zf.open(entry) as src, target.open("wb") as dst:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > _MAX_ENTRY_BYTES:
                raise ValidationError(f"Filen {entry} overskrider størrelsesgrensen (mulig zip-bombe).")
            dst.write(chunk)


def _stage_restore(zip_path: Path, backup_password: str | None) -> dict:
    """Open, validate and stage a restore into a temp dir — no live mutation.

    Everything that can fail — a wrong password, a corrupt archive, a mismatched
    hash, a broken database — is caught here, before any live data is touched
    (SR-003 #7). Returns the staging directory and what was found.
    """
    import base64 as _b64
    import tempfile

    from app.core.encryption import manifest_mac, unwrap_master_key_to_bytes

    staging = Path(tempfile.mkdtemp(prefix="sybr-restore-"))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise ValidationError(ui_t("err_invalid_backup"))
            _enforce_archive_limits(zf)

            manifest_bytes = zf.read("manifest.json")
            manifest = json.loads(manifest_bytes)

            new_key_bytes: bytes | None = None
            new_key_b64: str | None = None
            key_match = True
            if "master_key.wrapped" in names:
                if not backup_password:
                    raise ValidationError(
                        "Denne backupen inneholder en kryptert nøkkel. "
                        "Oppgi backup-passordet for å gjenopprette."
                    )
                wrapped = zf.read("master_key.wrapped").decode("utf-8")
                new_key_bytes = unwrap_master_key_to_bytes(wrapped, backup_password)
                if new_key_bytes is None:
                    raise ValidationError("Feil backup-passord. Kunne ikke dekryptere nøkkelen.")
                new_key_b64 = _b64.urlsafe_b64encode(new_key_bytes).decode()
            else:
                try:
                    backup_fp = manifest.get("master_key_fingerprint", "")
                    if backup_fp and _master_key_fingerprint() != backup_fp:
                        key_match = False
                except Exception as e:
                    logger.debug("Failed to check master key fingerprint: %s", e)
                    key_match = False

            # SR-003 #4: authenticate the manifest under the key that owns this
            # backup (the one from the archive, else the current one). A manifest
            # without a MAC is a pre-format-2 backup and is allowed for
            # compatibility — its files simply are not hash-verified below.
            if "manifest.mac" in names:
                expected = zf.read("manifest.mac").decode("utf-8").strip()
                got = manifest_mac(manifest_bytes, key=new_key_bytes)
                if not hmac.compare_digest(got, expected):
                    raise ValidationError(
                        "Manifest-signaturen stemmer ikke — backupen kan være endret. Avbrutt."
                    )

            for entry in names:
                if entry.endswith("/") or entry in ("manifest.json", "manifest.mac", "master_key.wrapped"):
                    continue
                _extract_entry(zf, entry, staging)

        # Verify each staged file against the authenticated manifest (SR-003 #7).
        for arc, meta in (manifest.get("files") or {}).items():
            staged = staging / arc
            if not staged.exists():
                raise ValidationError(f"Backupen mangler en fil den lover: {arc}")
            if _hash_file(staged) != meta.get("sha256"):
                raise ValidationError(f"Filen {arc} er skadet — hash stemmer ikke med manifestet.")

        staged_db = staging / "database" / "msp_toolkit.db"
        if staged_db.exists():
            import sqlite3
            con = sqlite3.connect(str(staged_db))
            try:
                row = con.execute("PRAGMA integrity_check").fetchone()
            finally:
                con.close()
            if not row or row[0] != "ok":
                raise ValidationError(f"Databasen i backupen består ikke integritetssjekken: {row}")
    except Exception:
        _remove(staging)
        raise

    return {"staging": staging, "manifest": manifest, "new_key_b64": new_key_b64, "key_match": key_match}


def _commit_restore(staged: dict) -> dict:
    """Swap staged data into place atomically, rolling back on any failure (SR-003 #8/#9).

    The database pool must already be closed by the caller. Every data class the
    backup touches is moved aside before its replacement lands; if anything
    fails partway, the moved-aside originals are put back, so a failed restore
    leaves the install exactly as it was.
    """
    from app.core.config import CONFIG_DIR, DATA_DIR, get_audit_dir, get_cert_dir
    from app.core.encryption import import_master_key

    staging: Path = staged["staging"]
    db_path = DATA_DIR / "msp_toolkit.db"
    targets = [
        (DATA_DIR / "customers", staging / "customers", "customers"),
        (get_audit_dir(), staging / "audits", "audits"),
        (CONFIG_DIR, staging / "config", "config"),
        (get_cert_dir(), staging / "certs", "certs"),
        (db_path, staging / "database" / "msp_toolkit.db", "database"),
        (DATA_DIR / "activity_log.jsonl", staging / "activity_log.jsonl", "activity_log"),
    ]

    rollback: list[tuple[Path, Path]] = []
    restored = {"customers": 0, "audits": 0, "config": 0, "certs": 0,
                "database": False, "activity_log": False}
    try:
        for live, src, key in targets:
            if not src.exists():
                continue
            if live.exists():
                bak = live.parent / (live.name + ".sybr-rollback")
                _remove(bak)
                shutil.move(str(live), str(bak))
                rollback.append((live, bak))
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(live))
            if key in ("database", "activity_log"):
                restored[key] = True
            else:
                restored[key] = sum(1 for p in live.rglob("*") if p.is_file())

        # Stale WAL/SHM from the connections that were just closed.
        for sidecar in ("-wal", "-shm"):
            wal = db_path.with_name(db_path.name + sidecar)
            if wal.exists():
                wal.unlink()

        # Adopt the backup's master key last — after the files it decrypts are
        # in place, so a key/data mismatch cannot arise mid-restore.
        if staged["new_key_b64"]:
            if not import_master_key(staged["new_key_b64"]):
                raise RuntimeError("Kunne ikke ta i bruk nøkkelen fra backupen.")

        for _live, bak in rollback:
            _remove(bak)
    except Exception:
        # Put every moved-aside original back, newest first.
        for live, bak in reversed(rollback):
            _remove(live)
            shutil.move(str(bak), str(live))
        raise
    finally:
        _remove(staging)

    return restored


@router.post("/backup/restore")
async def restore_backup(request: Request, user: User = _admin):
    """Restore a backup from a ZIP file.

    Validates and stages the whole archive first; only once it is proven
    complete and consistent does it quiesce the database and swap the data in,
    with rollback if the swap fails (SR-003).

    JSON body: ``zip_path`` (path to the backup) and ``backup_password``
    (required when the backup carries a wrapped master key).
    """
    from app.core.database import close_pool

    body = await request.json()
    zip_path_str = body.get("zip_path", "").strip()
    backup_password = body.get("backup_password", "").strip() or None
    if not zip_path_str:
        raise ValidationError(ui_t("err_no_file_path", request))

    zip_path = Path(zip_path_str).resolve()
    _safe_parents = [_get_default_backup_dir().resolve(), Path.home().resolve()]
    if not any(str(zip_path).startswith(str(p)) for p in _safe_parents):
        raise AuthError("Backup-filen må ligge i backup-mappen eller hjemmemappen")
    if not zip_path.exists() or not zip_path.is_file():
        raise NotFoundError(ui_t("err_file_not_found", request))
    if zip_path.suffix.lower() != ".zip":
        raise ValidationError(ui_t("err_file_must_be_zip", request))

    loop = asyncio.get_event_loop()
    try:
        # Phase 1: validate + stage. No live data is touched.
        staged = await loop.run_in_executor(None, lambda: _stage_restore(zip_path, backup_password))
        # Phase 2: quiesce — nothing may hold the live database open during the swap.
        await close_pool()
        # Phase 3: commit atomically, rolling back on any failure.
        restored = await loop.run_in_executor(None, lambda: _commit_restore(staged))
    except (ValidationError, NotFoundError, AuthError, ConflictError, IntegrationError):
        raise
    except Exception as e:
        raise IntegrationError(f"{ui_t('err_restore_failed', request)}: {e}")

    from app.core.activity_log import log_activity
    _user = getattr(getattr(request.state, "user", None), "username", "")
    log_activity("backup_restored", detail=zip_path_str, user=_user)

    result = {
        "ok": True,
        "key_match": staged["key_match"],
        "manifest": staged["manifest"],
        "restored_files": restored,
        "restart_required": restored.get("database", False),
    }
    if not staged["key_match"] and not staged["new_key_b64"]:
        result["warning"] = ui_t("warn_master_key_mismatch", request)
    return result


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
